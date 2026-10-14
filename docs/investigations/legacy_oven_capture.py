"""Read native legacy oven responses without resource mapping or appliance writes."""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
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
# These wrappers are in both captured resources lists and the legacy map.
ALL_ENDPOINTS = ENDPOINTS + tuple(
    f"/devices/{index}/{resource}"
    for index in (0, 1)
    for resource in (
        "oven",
        "operation",
        "temperatures",
        "doors",
        "information",
        "diagnosis",
        "alarms",
    )
)
# The uploaded Samsung oven plug-in defines this path; board support is unverified.
LIGHT_ENDPOINTS = ("/devices/0/light", "/devices/1/light")
# Confirmed by this oven's 2026-10-14 capability capture.
CAPABILITY_ENDPOINTS = ("/capability",)
SUBSCRIPTION_ENDPOINTS = ("/subscriptions",)
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
                identifying = tail in {
                    "name",
                    "friendlyname",
                    "description",
                    "ip",
                    "ipaddress",
                    "host",
                    "di",
                    "pi",
                    "notificationuri",
                    "subscriptionuri",
                    "subscriptionid",
                    "callbackuri",
                    "callbackurl",
                }
                identifying |= tail == "id" and not str(child).isdigit()
                result[key] = REDACTED if identifying else walk(child)
            return result
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, REDACTED)
            item = re.sub(
                r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b", REDACTED, item
            )
            item = re.sub(r"(/subscriptions/)[^/\s?#]+", r"\1" + REDACTED, item)
            return re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", REDACTED, item)
        return item

    return walk(redact_resources(value))


def capability_xml(raw: bytes) -> dict:
    """Expose XML fields to the same redactor as JSON; never resolve document entities."""
    text = raw.decode("utf-8-sig")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
        raise ValueError("XML declarations are not supported.")
    root = ET.fromstring(text)

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    if local_name(root.tag).lower() in {"html", "head", "body", "script"}:
        raise ValueError("HTML is not a capability document.")

    def fields(element):
        children = list(element)
        value = (element.text or "").strip()
        if not children and not element.attrib:
            return value
        result: dict = {}
        if element.attrib:
            result["@attributes"] = {local_name(k): v for k, v in element.attrib.items()}
        if value:
            result["#text"] = value
        for child in children:
            result.setdefault(local_name(child.tag), []).append(fields(child))
        return result

    return {local_name(root.tag): fields(root)}


def read_native(host: str, context, token: str, path: str) -> dict:
    # Fixed GET paths only: never follow links or send a control payload.
    if path not in ALL_ENDPOINTS + LIGHT_ENDPOINTS + CAPABILITY_ENDPOINTS + SUBSCRIPTION_ENDPOINTS:
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
            if path in CAPABILITY_ENDPOINTS and response.status == 200:
                try:
                    return {**result, "body_format": "xml", "body": capability_xml(raw)}
                except (ValueError, ET.ParseError, RecursionError):
                    return {**result, "error": "unparsed_capability_response", "bytes": len(raw)}
            # An HTML error may echo request information; do not export it.
            return {**result, "error": "non_json_response", "bytes": len(raw)}
    except (OSError, http.client.HTTPException) as error:
        return {"error": type(error).__name__}
    finally:
        connection.close()


def capture(
    data: dict,
    context,
    redact_resources,
    label: str | None,
    *,
    all_resources: bool = False,
    light_resource: bool = False,
    capability: bool = False,
    subscriptions: bool = False,
) -> dict:
    if sum((all_resources, light_resource, capability, subscriptions)) > 1:
        raise ValueError("Choose only one capture scope.")
    endpoints = ALL_ENDPOINTS if all_resources else ENDPOINTS
    scope = "all_resources" if all_resources else "baseline"
    if light_resource:
        endpoints = LIGHT_ENDPOINTS
        scope = "light_resource"
    if capability:
        endpoints = CAPABILITY_ENDPOINTS
        scope = "capability"
    if subscriptions:
        endpoints = SUBSCRIPTION_ENDPOINTS
        scope = "subscriptions"
    records = []
    for path in endpoints:
        print(f"Reading {path} ...", file=sys.stderr, flush=True)
        result = read_native(data["host"], context, data["device_token"], path)
        records.append(
            {
                "path": path,
                "captured_at": datetime.now(UTC).isoformat(),
                **scrub(result, data, redact_resources),
            }
        )
    return {
        "format_version": 1,
        "light": label,
        "scope": scope,
        "method": "GET",
        "responses": records,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "label", nargs="?", choices=("off", "on"), help="Observed physical light state"
    )
    parser.add_argument("--config-dir", type=Path, default=Path("/config"))
    parser.add_argument("--entry-id")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--all-resources", action="store_true", help="Also read every remaining advertised resource"
    )
    scope.add_argument(
        "--light-resource", action="store_true", help="Read only the two app-defined light paths"
    )
    scope.add_argument(
        "--capability", action="store_true", help="Read only /capability, accepting JSON or XML"
    )
    scope.add_argument(
        "--subscriptions", action="store_true", help="Read only the advertised /subscriptions list"
    )
    args = parser.parse_args(argv)
    if args.label is None and not (args.capability or args.subscriptions):
        parser.error(
            "A light-state label is required unless --capability or --subscriptions is used."
        )
    prefix = "oven-capability" if args.capability else f"oven-light-{args.label}"
    if args.subscriptions:
        prefix = "oven-subscriptions"
    output = args.config_dir / f"{prefix}-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.json"
    try:
        data = select_entry(args.config_dir, args.entry_id)
        tls = load_support(args.config_dir, "legacy_http_tls.py")
        redactor = load_support(args.config_dir, "registry/redact.py")
        context = tls.client_context(data["leaf_cert_pem"], data["leaf_key_pem"])
        report = capture(
            data,
            context,
            redactor.redact_resources,
            args.label,
            all_resources=args.all_resources,
            light_resource=args.light_resource,
            capability=args.capability,
            subscriptions=args.subscriptions,
        )
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
