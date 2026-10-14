"""Capture legacy oven notifications using one temporary subscription."""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import ipaddress
import json
import os
import re
import select
import signal
import socket
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CALLBACK_PORT = 8889
CAPTURE_SECONDS = 360
REQUESTED_DURATION = 420
MAX_BODY = 2 * 1024 * 1024
MAX_EVENTS = 100
MAX_TOTAL_BODY = 8 * 1024 * 1024
MAX_FRAMING_LINE = 8192
MAX_TRAILER_BYTES = 16384
UNFRAMED_PROBE_SECONDS = 1.5


def body_metadata(headers) -> dict:
    """Export framing facts, never arbitrary header values or trailer contents."""
    lengths = headers.get_all("Content-Length", [])
    values = [part.strip() for value in lengths for part in value.split(",")]
    valid = bool(values) and all(re.fullmatch(r"[0-9]{1,10}", part) for part in values)
    numbers = {int(part) for part in values} if valid else set()
    valid = valid and len(numbers) == 1
    transfers = headers.get_all("Transfer-Encoding", [])
    codings = [part.strip().lower() for value in transfers for part in value.split(",")]
    payload = headers.get_payload()
    return {
        "header_fields": len(headers),
        "header_parse_defects": sorted({type(defect).__name__ for defect in headers.defects}),
        "header_payload_bytes": len(payload.encode("iso-8859-1", errors="replace"))
        if isinstance(payload, str)
        else 0,
        "content_length_fields": len(lengths),
        "content_length_valid": valid,
        "declared_length": next(iter(numbers)) if valid else None,
        "transfer_encoding": "chunked"
        if codings == ["chunked"]
        else "other"
        if transfers
        else "none",
        "expect_continue": headers.get("Expect", "").strip().lower() == "100-continue",
        "content_type_is_json": headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        == "application/json",
    }


def read_callback_body(stream, metadata) -> bytes:
    """Decode bounded HTTP framing; requests without either length field are empty."""

    def exact(size):
        value = stream.read(size)
        if len(value) != size:
            raise ValueError("incomplete_body")
        return value

    def line():
        value = stream.readline(MAX_FRAMING_LINE + 1)
        if len(value) > MAX_FRAMING_LINE or not value.endswith(b"\r\n"):
            raise ValueError("invalid_framing_line")
        return value

    transfer = metadata["transfer_encoding"]
    if transfer != "none":
        if transfer != "chunked":
            raise ValueError("unsupported_transfer_encoding")
        if metadata["content_length_fields"]:
            raise ValueError("ambiguous_body_framing")
        body = bytearray()
        for _ in range(8192):
            token = line()[:-2].split(b";", 1)[0]
            if not re.fullmatch(rb"[0-9a-fA-F]{1,16}", token):
                raise ValueError("invalid_chunk_size")
            size = int(token, 16)
            if len(body) + size > MAX_BODY:
                raise ValueError("body_too_large")
            if size == 0:
                trailer_bytes = 0
                while True:
                    trailer = line()
                    trailer_bytes += len(trailer)
                    if trailer_bytes > MAX_TRAILER_BYTES:
                        raise ValueError("trailers_too_large")
                    if trailer == b"\r\n":
                        return bytes(body)
            body.extend(exact(size))
            if exact(2) != b"\r\n":
                raise ValueError("invalid_chunk_terminator")
        raise ValueError("too_many_chunks")
    if not metadata["content_length_fields"]:
        return b""
    if not metadata["content_length_valid"]:
        raise ValueError("invalid_content_length")
    length = metadata["declared_length"]
    if length > MAX_BODY:
        raise ValueError("body_too_large")
    return exact(length)


def probe_unframed_body(stream, connection) -> tuple[bytes, str]:
    """Check for nonstandard body bytes without waiting indefinitely for an HTTP boundary."""
    deadline = time.monotonic() + UNFRAMED_PROBE_SECONDS
    previous_timeout = connection.gettimeout()
    body = bytearray()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return bytes(body), "time_limit"
            connection.settimeout(remaining)
            try:
                # read1 includes bytes buffered while parsing headers; recv would miss them.
                piece = stream.read1(min(65536, MAX_BODY + 1 - len(body)))
            except TimeoutError:
                return bytes(body), "time_limit"
            except OSError:
                return bytes(body), "read_error"
            if not piece:
                return bytes(body), "peer_closed"
            body.extend(piece)
            if len(body) > MAX_BODY:
                return bytes(body), "size_limit"
            try:
                parsed = json.loads(body)
            except (ValueError, UnicodeDecodeError, RecursionError):
                continue
            if isinstance(parsed, (dict, list)):
                return bytes(body), "complete_json"
    finally:
        connection.settimeout(previous_timeout)


def body_prefix_kind(raw: bytes) -> str:
    """Describe an unparsed body's shape without exposing any of its text."""
    prefix = raw.lstrip()[:1]
    if prefix in (b"{", b"["):
        return "json_container"
    if prefix == b"<":
        return "markup"
    return "other" if prefix else "empty_or_whitespace"


def load_capture():
    path = Path(__file__).with_name("legacy_oven_capture.py")
    spec = importlib.util.spec_from_file_location("legacy_oven_capture", path)
    if spec is None or spec.loader is None:
        raise ImportError("The read-only capture helper must be beside this script.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stamp() -> str:
    return datetime.now(UTC).isoformat()


def subscription_path(row) -> str | None:
    if not isinstance(row, dict):
        return None
    identifier = row.get("id")
    path = row.get("href")
    if path is None and isinstance(identifier, (str, int)):
        path = f"/subscriptions/{identifier}"
    if (
        isinstance(path, str)
        and re.fullmatch(r"/subscriptions/[A-Za-z0-9_.-]{1,128}", path)
        and path.rsplit("/", 1)[-1] not in {".", ".."}
    ):
        return path
    return None


def subscription_rows(response) -> list | None:
    body = response.get("body")
    rows = body.get("Subscriptions") if isinstance(body, dict) else None
    return rows if response.get("http_status") == 200 and isinstance(rows, list) else None


def exchange(data, context, method, *, body=None, owned_path=None) -> dict:
    # The only write targets are the subscription collection and our returned ID.
    path = "/subscriptions"
    if method == "DELETE":
        if owned_path is None or subscription_path({"href": owned_path}) != owned_path:
            raise ValueError("A validated owned subscription path is required.")
        path = owned_path
    elif method not in {"GET", "POST"}:
        raise ValueError("Only subscription GET, POST and owned DELETE are supported.")
    connection = http.client.HTTPSConnection(data["host"], 8888, context=context, timeout=8)
    try:
        headers = {"Authorization": f"Bearer {data['device_token']}", "Accept": "application/json"}
        payload = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode()
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read(MAX_BODY + 1)
        result = {"http_status": response.status}
        if len(raw) > MAX_BODY:
            return {**result, "error": "response_too_large"}
        if not raw:
            return {**result, "body": None}
        try:
            return {**result, "body": json.loads(raw)}
        except (ValueError, UnicodeDecodeError, RecursionError):
            return {**result, "error": "non_json_response", "bytes": len(raw)}
    except (OSError, http.client.HTTPException) as error:
        return {"error": type(error).__name__}
    finally:
        connection.close()


class NotificationHandler(BaseHTTPRequestHandler):
    """Keep the body, never headers or unparsed text that could carry credentials."""

    server: NotificationListener
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def log_error(self, format, *args):
        self.server.request_failures += 1

    def do_POST(self):
        server = self.server
        if self.path != "/notifications":
            self.reply(404)
            return
        metadata = body_metadata(self.headers)
        unframed = not metadata["content_length_fields"] and metadata["transfer_encoding"] == "none"
        record = {
            "received_at": stamp(),
            "framing": metadata,
            "body_read": {"mode": "unframed_probe" if unframed else "http_framing"},
        }
        try:
            if unframed:
                raw, ending = probe_unframed_body(self.rfile, self.connection)
                record["body_read"]["termination"] = ending
            else:
                raw = read_callback_body(self.rfile, metadata)
        except (ValueError, OSError) as error:
            detail = str(error) if isinstance(error, ValueError) else type(error).__name__
            server.record({**record, "error": detail})
            self.reply(400)
            return
        length = len(raw)
        server.total_bytes += length
        if length > MAX_BODY:
            server.record({**record, "error": "body_too_large", "bytes": length})
            self.reply(413)
            return
        if server.total_bytes > MAX_TOTAL_BODY:
            server.dropped += 1
            self.reply(200)
            return
        try:
            server.record({**record, "body": json.loads(raw) if raw else None, "bytes": length})
        except (ValueError, UnicodeDecodeError, RecursionError):
            server.record(
                {
                    **record,
                    "error": "non_json_notification",
                    "bytes": length,
                    "body_prefix_kind": body_prefix_kind(raw),
                }
            )
        self.reply(200)

    def reply(self, code):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True


class NotificationListener(HTTPServer):
    allow_reuse_address = True

    def __init__(self, address, peer, context, scrub):
        self.peer = peer
        self.context = context
        self.scrub = scrub
        self.events = []
        self.tls_failures = 0
        self.request_failures = 0
        self.connections = 0
        self.dropped = 0
        self.total_bytes = 0
        self.stop_event = threading.Event()
        self.thread = None
        super().__init__(address, NotificationHandler)
        self.timeout = 0.25

    def get_request(self):
        raw, address = self.socket.accept()
        if address[0] != self.peer:
            raw.close()
            raise OSError("Unexpected callback peer")
        self.connections += 1
        raw.settimeout(3)
        try:
            return self.context.wrap_socket(raw, server_side=True), address
        except OSError:
            self.tls_failures += 1
            raw.close()
            raise

    def handle_error(self, request, client_address):
        self.request_failures += 1

    def record(self, event):
        if len(self.events) >= MAX_EVENTS:
            self.dropped += 1
            return
        self.events.append({"received_at": stamp(), **self.scrub(event)})

    def start(self):
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while not self.stop_event.is_set():
            self.handle_request()

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=4)
        self.server_close()


def local_address_for(host: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((host, 9))
        address = probe.getsockname()[0]
    parsed = ipaddress.ip_address(address)
    if parsed.is_loopback or parsed.is_unspecified:
        raise ValueError("No LAN callback address is available.")
    return address


def guide(report, cancelled, deadline):
    print(
        "Listening. You have up to six minutes for all four steps.\n"
        "Follow each prompt; press Enter AFTER the action.",
        flush=True,
    )
    for label, action in (
        ("lamp_on_door_closed", "Press Lamp to turn the light ON, keeping the door closed."),
        ("lamp_off_door_closed", "Press Lamp to turn the light OFF, keeping the door closed."),
        ("door_open", "Open the oven door and leave it open."),
        ("door_closed", "Close the oven door."),
    ):
        if cancelled.wait(5) or time.monotonic() >= deadline:
            report["observation_status"] = "cancelled_or_timed_out"
            return
        print(action + " Then press Enter here.", flush=True)
        while not cancelled.is_set() and time.monotonic() < deadline:
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            if ready:
                if not sys.stdin.readline():
                    cancelled.set()
                    return
                report["markers"].append({"action": label, "confirmed_at": stamp()})
                break
        else:
            report["observation_status"] = "cancelled_or_timed_out"
            return
    cancelled.wait(min(10, max(0, deadline - time.monotonic())))
    report["observation_status"] = "completed"


def run_capture(
    data, tls, scrub, cancelled, *, observe=guide, listener_factory=NotificationListener
):
    report: dict = {
        "format_version": 1,
        "scope": "notifications",
        "capture_limit_seconds": CAPTURE_SECONDS,
        "requests": [],
        "markers": [],
    }
    context = tls.client_context(data["leaf_cert_pem"], data["leaf_key_pem"])
    peer = socket.gethostbyname(data["host"])
    address = local_address_for(peer)
    callback = f"https://{address}:{CALLBACK_PORT}/notifications"
    identity = str(uuid.uuid4())
    body = {
        "Subscription": {
            "uuid": identity,
            "notificationURI": callback,
            "resourceURIs": ["/devices"],
            "duration": REQUESTED_DURATION,
        }
    }
    owned = set()
    attempted = False
    listener = None

    def request(method, *, owned_path=None, payload=None):
        result = exchange(data, context, method, body=payload, owned_path=owned_path)
        report["requests"].append(
            scrub(
                {"method": method, "path": owned_path or "/subscriptions", "at": stamp(), **result}
            )
        )
        return result

    def find_owned(rows):
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if row.get("uuid") == identity and row.get("notificationURI") == callback:
                path = subscription_path(row)
                if path:
                    owned.add(path)

    try:
        before = request("GET")
        rows = subscription_rows(before)
        if rows is None or rows:
            report["error"] = "subscription_list_unavailable_or_not_empty"
            return report
        listener = listener_factory(
            (address, CALLBACK_PORT),
            peer,
            tls.server_context(data["leaf_cert_pem"], data["leaf_key_pem"]),
            scrub,
        )
        listener.start()
        if cancelled.is_set():
            report["observation_status"] = "cancelled"
            return report
        report["registration_request"] = scrub(body)
        attempted = True
        created = request("POST", payload=body)
        if 200 <= created.get("http_status", 0) < 300:
            result_body = created.get("body")
            row = result_body.get("Subscription") if isinstance(result_body, dict) else None
            path = subscription_path(row)
            if (
                path
                and isinstance(row, dict)
                and row.get("uuid", identity) == identity
                and row.get("notificationURI", callback) == callback
            ):
                owned.add(path)
        current = subscription_rows(request("GET"))
        find_owned(current)
        if not owned or not 200 <= created.get("http_status", 0) < 300:
            report["error"] = "registration_not_confirmed"
            return report
        report["markers"].append(
            {"action": "baseline_lamp_off_door_closed", "confirmed_at": stamp()}
        )
        observe(report, cancelled, time.monotonic() + CAPTURE_SECONDS)
    except KeyboardInterrupt:
        report["observation_status"] = "cancelled"
    except (OSError, ValueError, http.client.HTTPException) as error:
        report["error"] = type(error).__name__
        if isinstance(error, OSError):
            report["errno"] = error.errno
    finally:
        if attempted:
            # Reconcile even a timed-out POST: it may have created our registration.
            find_owned(subscription_rows(request("GET")))
            for path in sorted(owned):
                request("DELETE", owned_path=path)
            remaining = subscription_rows(request("GET"))
            if remaining is None or (remaining and not owned):
                report["cleanup"] = "unverified"
            elif any(
                subscription_path(row) in owned
                or (
                    isinstance(row, dict)
                    and row.get("uuid") == identity
                    and row.get("notificationURI") == callback
                )
                for row in remaining
            ):
                report["cleanup"] = "registration_still_present"
            else:
                report["cleanup"] = "confirmed_absent"
        if listener is not None:
            listener.stop()
            report["notifications"] = listener.events
            report["listener"] = {
                "connections": listener.connections,
                "tls_failures": listener.tls_failures,
                "request_failures": listener.request_failures,
                "dropped": listener.dropped,
            }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path("/config"))
    parser.add_argument("--entry-id")
    args = parser.parse_args(argv)
    cancelled = threading.Event()
    previous = {}
    try:
        capture = load_capture()
        data = capture.select_entry(args.config_dir, args.entry_id)
        tls = capture.load_support(args.config_dir, "legacy_http_tls.py")
        redactor = capture.load_support(args.config_dir, "registry/redact.py")
        input("With the oven idle and cool, door CLOSED and light OFF, press Enter to begin. ")
        output = args.config_dir / f"oven-events-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.json"
        handle = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            for name in ("SIGINT", "SIGTERM", "SIGHUP"):
                signum = getattr(signal, name, None)
                if signum is not None:
                    previous[signum] = signal.signal(signum, lambda *_: cancelled.set())
            report = run_capture(
                data,
                tls,
                lambda value: capture.scrub(value, data, redactor.redact_resources),
                cancelled,
            )
            json.dump(report, stream, indent=2)
            stream.write("\n")
        print(f"Saved: {output}", flush=True)
        print(json.dumps(report, indent=2))
        return 1 if "error" in report or report.get("cleanup") != "confirmed_absent" else 0
    except (OSError, ValueError, KeyError, ImportError, EOFError) as error:
        print(f"Capture could not complete ({type(error).__name__}).", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 1
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
