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
CAPTURE_SECONDS = 150
REQUESTED_DURATION = 180
MAX_BODY = 2 * 1024 * 1024
MAX_EVENTS = 100
MAX_TOTAL_BODY = 8 * 1024 * 1024


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

    def log_message(self, format, *args):
        pass

    def log_error(self, format, *args):
        self.server.request_failures += 1

    def do_POST(self):
        server = self.server
        if self.path != "/notifications":
            self.reply(404)
            return
        error = None
        if self.headers.get("Transfer-Encoding"):
            error = "unsupported_transfer_encoding"
        lengths = self.headers.get_all("Content-Length", [])
        length = int(lengths[0]) if len(lengths) == 1 and lengths[0].isdigit() else -1
        if not 0 < length <= MAX_BODY:
            error = "invalid_content_length"
        if error:
            server.record({"error": error})
            self.reply(400)
            return
        raw = self.rfile.read(length)
        if len(raw) != length:
            server.record({"error": "incomplete_body", "bytes": len(raw)})
            self.reply(400)
            return
        server.total_bytes += length
        if server.total_bytes > MAX_TOTAL_BODY:
            server.dropped += 1
            self.reply(200)
            return
        try:
            server.record({"body": json.loads(raw)})
        except (ValueError, UnicodeDecodeError, RecursionError):
            server.record({"error": "non_json_notification", "bytes": length})
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
    print("Listening. Follow each prompt; press Enter AFTER the action.", flush=True)
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
    report: dict = {"format_version": 1, "scope": "notifications", "requests": [], "markers": []}
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
