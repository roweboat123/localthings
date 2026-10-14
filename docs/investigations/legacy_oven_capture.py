"""Read native legacy oven responses without resource mapping or appliance writes."""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ENDPOINTS = (
    "/devices",
    "/devices/0",
    "/devices/0/mode",
    "/devices/0/configuration",
    "/devices/1",
    "/devices/1/mode",
    "/devices/1/configuration",
)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REDACTED = "**REDACTED**"


def select_entry(config_dir: Path, entry_id: str | None = None) -> dict:
    storage = json.loads((config_dir / ".storage/core.config_entries").read_text())
    matches = [
        entry
        for entry in storage["data"]["entries"]
        if entry.get("domain") == "localthings"
        and entry.get("data", {}).get("transport") == "legacy_http"
        and entry.get("data", {}).get("legacy_family") == "LCD_OV_WALL_16K"
        and (entry_id is None or entry.get("entry_id") == entry_id)
    ]
    if len(matches) != 1:
        raise ValueError("Expected one LCD_OV_WALL_16K entry; use --entry-id if there are several.")
    data = matches[0]["data"]
    for key in ("host", "device_token", "leaf_cert_pem", "leaf_key_pem"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"The oven entry is missing {key}.")
    if int(data.get("port", 8888)) != 8888:
        raise ValueError("The selected oven entry does not use the legacy port 8888.")
    return data


def load_support(config_dir: Path, relative: str):
    path = config_dir / "custom_components/localthings" / relative
    spec = importlib.util.spec_from_file_location("oven_capture_" + path.stem, path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load LocalThings capture support.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scrub(value, data: dict, redact_resources):
    """Keep unknown state fields while removing aggregate identity scalars."""
    secrets = sorted(
        {
            value
            for key, value in data.items()
            if isinstance(value, str)
            and len(value) >= 4
            and (key in {"host", "serial", "device_key", "mac"} or "token" in key or "pem" in key)
        },
        key=len,
        reverse=True,
    )

    def walk(item):
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                tail = key.lower().rsplit(".", 1)[-1]
                identifying = tail in {"name", "description", "ip", "host", "di", "pi"}
                identifying |= tail == "id" and not str(child).isdigit()
                result[key] = REDACTED if identifying else walk(child)
            return result
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, REDACTED)
            return re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", REDACTED, item)
        return item

    return walk(redact_resources(value))


def read_native(host: str, context, token: str, path: str) -> dict:
    # Fixed GET paths only: never follow links or send a control payload.
    if path not in ENDPOINTS:
        raise ValueError("Endpoint is not in the capture list.")
    connection = http.client.HTTPSConnection(host, 8888, context=context, timeout=8)
    try:
        connection.request(
            "GET", path, headers={"Authorization": f"Bearer {token}", "Accept": "*/*"}
        )
        response = connection.getresponse()
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        result = {"http_status": response.status}
        if len(raw) > MAX_RESPONSE_BYTES:
            return {**result, "error": "response_too_large"}
        if not raw:
            return {**result, "body": None}
        try:
            return {**result, "body": json.loads(raw)}
        except (ValueError, UnicodeDecodeError):
            # An HTML error may echo request information; do not export it.
            return {**result, "error": "non_json_response", "bytes": len(raw)}
    except (OSError, http.client.HTTPException) as error:
        return {"error": type(error).__name__}
    finally:
        connection.close()


def capture(data: dict, context, redact_resources, label: str) -> dict:
    records = []
    for path in ENDPOINTS:
        print(f"Reading {path} ...", file=sys.stderr, flush=True)
        result = read_native(data["host"], context, data["device_token"], path)
        records.append(
            {
                "path": path,
                "captured_at": datetime.now(UTC).isoformat(),
                **scrub(result, data, redact_resources),
            }
        )
    return {"format_version": 1, "light": label, "method": "GET", "responses": records}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", choices=("off", "on"), help="Observed physical light state")
    parser.add_argument("--config-dir", type=Path, default=Path("/config"))
    parser.add_argument("--entry-id")
    args = parser.parse_args(argv)
    output = args.config_dir / f"oven-light-{args.label}-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.json"
    try:
        data = select_entry(args.config_dir, args.entry_id)
        tls = load_support(args.config_dir, "legacy_http_tls.py")
        redactor = load_support(args.config_dir, "registry/redact.py")
        context = tls.client_context(data["leaf_cert_pem"], data["leaf_key_pem"])
        report = capture(data, context, redactor.redact_resources, args.label)
        with output.open("x", encoding="utf-8") as stream:
            output.chmod(0o600)
            json.dump(report, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        print(f"Saved: {output}", file=sys.stderr)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if any(r.get("http_status") == 200 for r in report["responses"]) else 1
    except (OSError, ValueError, KeyError, ImportError) as error:
        # Credential parsing/TLS errors must not echo private values.
        print(f"Capture could not complete ({type(error).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
