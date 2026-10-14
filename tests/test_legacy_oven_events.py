"""Bounded notification capture owns its subscription and preserves raw events."""

import http.client
import io
import json
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from email.message import Message
from unittest.mock import Mock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from custom_components.localthings import legacy_http_tls
from custom_components.localthings.registry.redact import redact_resources
from docs.investigations import legacy_oven_capture as capture
from docs.investigations import legacy_oven_events as events

DATA = {
    "host": "192.0.2.8",
    "device_token": "private-device-token",
    "leaf_cert_pem": "private-certificate",
    "leaf_key_pem": "private-key",
}


def scrub(value):
    return capture.scrub(value, DATA, redact_resources)


class FakeListener:
    def __init__(self, *args):
        self.events = []
        self.connections = self.tls_failures = self.request_failures = self.dropped = 0
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(events.socket, "gethostbyname", lambda host: host)
    monkeypatch.setattr(events, "local_address_for", lambda host: "192.0.2.10")
    rows = []
    calls = []
    listener = FakeListener()
    options = {"post_timeout": False, "delete_failure": False, "omit_identity": False}

    def exchange(data, context, method, *, body=None, owned_path=None):
        calls.append((method, owned_path or "/subscriptions", body))
        if method == "GET":
            return {"http_status": 200, "body": {"Subscriptions": list(rows)}}
        if method == "POST":
            assert listener.started
            assert body is not None
            row = {**body["Subscription"], "id": "our-new-id", "href": "/subscriptions/our-new-id"}
            if options["omit_identity"]:
                row = {"href": "https://unrelated.example/subscriptions/foreign-id"}
            rows.append(row)
            if options["post_timeout"]:
                return {"error": "TimeoutError"}
            return {"http_status": 201, "body": {"Subscription": row}}
        assert method == "DELETE"
        if options["delete_failure"]:
            return {"http_status": 500, "body": None}
        rows[:] = [row for row in rows if row.get("href") != owned_path]
        return {"http_status": 204, "body": None}

    monkeypatch.setattr(events, "exchange", exchange)

    def run(observe=lambda *args: None, cancelled=None):
        return events.run_capture(
            DATA,
            Mock(),
            scrub,
            cancelled or threading.Event(),
            observe=observe,
            listener_factory=lambda *args: listener,
        )

    return rows, calls, listener, options, run


def test_only_own_subscription_is_removed_and_callback_identity_is_private(rig):
    rows, calls, listener, _, run = rig
    foreign = {"id": "foreign-id", "href": "/subscriptions/foreign-id", "uuid": "another-client"}

    def observe(report, cancelled, deadline):
        rows.append(foreign)
        report["markers"].append({"action": "lamp_on_door_closed"})

    report = run(observe)
    assert rows == [foreign]
    assert listener.stopped
    assert report["cleanup"] == "confirmed_absent"
    assert [(method, path) for method, path, _ in calls if method != "GET"] == [
        ("POST", "/subscriptions"),
        ("DELETE", "/subscriptions/our-new-id"),
    ]
    payload = next(body for method, _, body in calls if method == "POST")["Subscription"]
    assert payload["resourceURIs"] == ["/devices"]
    assert payload["notificationURI"] == "https://192.0.2.10:8889/notifications"
    encoded = json.dumps(report)
    for private in ("192.0.2.10", "our-new-id", payload["uuid"], "private-device-token"):
        assert private not in encoded


def test_timeout_after_post_still_discovers_and_removes_created_registration(rig):
    rows, calls, listener, options, run = rig
    options["post_timeout"] = True
    observe = Mock()
    report = run(observe)
    observe.assert_not_called()
    assert report["error"] == "registration_not_confirmed"
    assert report["cleanup"] == "confirmed_absent"
    assert not rows
    assert listener.stopped
    assert sum(method == "POST" for method, _, _ in calls) == 1


def test_interrupt_during_observation_still_cleans_up(rig):
    rows, _, listener, _, run = rig

    def interrupt(*args):
        raise KeyboardInterrupt

    report = run(interrupt)
    assert report["observation_status"] == "cancelled"
    assert report["cleanup"] == "confirmed_absent"
    assert not rows
    assert listener.stopped


def test_failed_delete_is_not_reported_as_clean(rig):
    rows, _, _, options, run = rig
    options["delete_failure"] = True
    report = run()
    assert rows
    assert report["cleanup"] == "registration_still_present"


def test_unknown_registration_is_not_deleted_or_reported_as_absent(rig):
    _, calls, _, options, run = rig
    options["omit_identity"] = True
    report = run()
    assert report["cleanup"] == "unverified"
    assert report["error"] == "registration_not_confirmed"
    assert not any(method == "DELETE" for method, _, _ in calls)


def test_existing_subscriptions_stop_before_any_registration(rig):
    rows, calls, listener, _, run = rig
    rows.append({"href": "/subscriptions/existing"})
    report = run()
    assert "error" in report
    assert [method for method, _, _ in calls] == ["GET"]
    assert not listener.started


@pytest.mark.parametrize(
    "path",
    [
        "/subscriptions/..",
        "https://example.com/subscriptions/1",
        "/devices/0/operation",
        "/subscriptions/1?delete=all",
        "/subscriptions/",
    ],
)
def test_unsafe_cleanup_path_cannot_send_a_request(monkeypatch, path):
    connect = Mock()
    monkeypatch.setattr(events.http.client, "HTTPSConnection", connect)
    with pytest.raises(ValueError):
        events.exchange(DATA, object(), "DELETE", owned_path=path)
    connect.assert_not_called()


def test_transport_posts_only_the_subscription_document(monkeypatch):
    connection = Mock()
    connection.getresponse.return_value.status = 201
    connection.getresponse.return_value.read.return_value = b'{"Subscription":{"id":"test"}}'
    monkeypatch.setattr(events.http.client, "HTTPSConnection", Mock(return_value=connection))
    body = {"Subscription": {"resourceURIs": ["/devices"]}}
    result = events.exchange(DATA, object(), "POST", body=body)
    assert result["http_status"] == 201
    args, kwargs = connection.request.call_args
    assert args == ("POST", "/subscriptions")
    assert json.loads(kwargs["body"]) == body
    assert kwargs["headers"]["Authorization"] == "Bearer private-device-token"
    connection.close.assert_called_once()


@pytest.fixture
def tls_material():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "notification-test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .sign(key, hashes.SHA256())
    )
    return (
        cert.public_bytes(serialization.Encoding.PEM).decode(),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    )


@pytest.mark.parametrize("chunked", [False, True])
def test_https_callback_retains_unmapped_event_and_discards_credentials(
    socket_enabled, tls_material, chunked
):
    cert, key = tls_material
    listener = events.NotificationListener(
        ("127.0.0.1", 0), "127.0.0.1", legacy_http_tls.server_context(cert, key), scrub
    )
    listener.start()
    try:
        conn = http.client.HTTPSConnection(
            "127.0.0.1",
            listener.server_port,
            context=legacy_http_tls.client_context(cert, key),
            timeout=3,
        )
        body_bytes = json.dumps(
            {
                "Notification": {
                    "subscriptionURI": "/subscriptions/test-id",
                    "Events": [
                        {"unknownLampField": True, "authToken": "secret-event-token", "id": "0"}
                    ],
                }
            }
        ).encode()
        conn.request(
            "POST",
            "/notifications",
            body=[body_bytes[:10], body_bytes[10:]] if chunked else body_bytes,
            encode_chunked=chunked,
            headers={"Authorization": "Bearer private-header", "Content-Type": "application/json"},
        )
        response = conn.getresponse()
        response.read()
        assert response.status == 200
        conn.close()
    finally:
        listener.stop()
    assert len(listener.events) == 1
    body = listener.events[0]["body"]["Notification"]
    assert body["Events"][0]["unknownLampField"] is True
    assert body["Events"][0]["id"] == "0"
    encoded = json.dumps(listener.events)
    for private in ("test-id", "secret-event-token", "private-header"):
        assert private not in encoded
    assert listener.connections == 1
    assert listener.tls_failures == 0
    assert listener.events[0]["framing"]["transfer_encoding"] == ("chunked" if chunked else "none")
    assert listener.thread is not None
    assert not listener.thread.is_alive()


def test_wrong_peer_is_rejected_before_tls(socket_enabled):
    context = Mock()
    listener = events.NotificationListener(("127.0.0.1", 0), "192.0.2.8", context, scrub)
    try:
        with socket.create_connection(("127.0.0.1", listener.server_port)), pytest.raises(OSError):
            listener.get_request()
        context.wrap_socket.assert_not_called()
    finally:
        listener.server_close()


def test_standalone_helper_dependency_loads_without_home_assistant():
    assert callable(events.load_capture().select_entry)


def framing(headers):
    message = Message()
    for key, value in headers:
        message[key] = value
    return events.body_metadata(message)


@pytest.mark.parametrize(
    ("headers", "wire", "expected"),
    [
        ([], b"", b""),
        ([("Content-Length", "0")], b"", b""),
        ([("Content-Length", " 2 ")], b"{}", b"{}"),
        ([("Content-Length", "2"), ("Content-Length", "2")], b"{}", b"{}"),
        ([("Content-Length", "2, 2")], b"{}", b"{}"),
        (
            [("Transfer-Encoding", "CHUNKED")],
            b"1;private-extension=secret\r\n{\r\n1\r\n}\r\n0\r\n"
            b"Authorization: private-trailer\r\n\r\n",
            b"{}",
        ),
        ([("Transfer-Encoding", "chunked")], b"0\r\n\r\n", b""),
    ],
)
def test_valid_callback_framing_and_empty_messages_are_read(headers, wire, expected):
    assert events.read_callback_body(io.BytesIO(wire), framing(headers)) == expected


@pytest.mark.parametrize(
    ("headers", "wire", "error"),
    [
        ([("Content-Length", "2, 3")], b"{}", "invalid_content_length"),
        ([("Content-Length", "private-invalid-value")], b"", "invalid_content_length"),
        ([("Content-Length", "4")], b"{}", "incomplete_body"),
        ([("Content-Length", str(events.MAX_BODY + 1))], b"", "body_too_large"),
        (
            [("Transfer-Encoding", "private-unsupported-coding")],
            b"",
            "unsupported_transfer_encoding",
        ),
        (
            [("Transfer-Encoding", "chunked"), ("Content-Length", "2")],
            b"",
            "ambiguous_body_framing",
        ),
        ([("Transfer-Encoding", "chunked")], b"private-invalid-size\r\n", "invalid_chunk_size"),
        ([("Transfer-Encoding", "chunked")], b"1\r\n{xx", "invalid_chunk_terminator"),
        ([("Transfer-Encoding", "chunked")], b"2\r\n{", "incomplete_body"),
        ([("Transfer-Encoding", "chunked")], b"0\r\n", "invalid_framing_line"),
        ([("Transfer-Encoding", "chunked")], b"300000\r\n", "body_too_large"),
        (
            [("Transfer-Encoding", "chunked")],
            b"a" * (events.MAX_FRAMING_LINE + 1),
            "invalid_framing_line",
        ),
        (
            [("Transfer-Encoding", "chunked")],
            b"0\r\n" + (b"X: " + b"a" * 8000 + b"\r\n") * 3,
            "trailers_too_large",
        ),
    ],
)
def test_invalid_framing_has_specific_safe_errors(headers, wire, error):
    metadata = framing(headers)
    with pytest.raises(ValueError, match="^" + error + "$"):
        events.read_callback_body(io.BytesIO(wire), metadata)
    assert "private-" not in json.dumps(metadata)


def test_http_expect_continue_completes_before_sender_transmits_body(socket_enabled, tls_material):
    cert, key = tls_material
    listener = events.NotificationListener(
        ("127.0.0.1", 0), "127.0.0.1", legacy_http_tls.server_context(cert, key), scrub
    )
    listener.start()
    try:
        context = legacy_http_tls.client_context(cert, key)
        with (
            socket.create_connection(("127.0.0.1", listener.server_port), timeout=3) as raw,
            context.wrap_socket(raw) as conn,
        ):
            conn.sendall(
                b"POST /notifications HTTP/1.1\r\nHost: localhost\r\n"
                b"Expect: 100-continue\r\nContent-Length: 2\r\n\r\n"
            )
            with conn.makefile("rb") as stream:
                assert stream.readline().startswith(b"HTTP/1.1 100 ")
                assert stream.readline() == b"\r\n"
                conn.sendall(b"{}")
                assert stream.readline().startswith(b"HTTP/1.1 200 ")
    finally:
        listener.stop()
    assert listener.events[0]["body"] == {}
    assert listener.events[0]["framing"]["expect_continue"] is True


@pytest.mark.parametrize(
    ("wire_headers", "pieces", "termination"),
    [
        (b"Host: localhost\r\n", [b'{"unknownLampField":true}'], "complete_json"),
        (
            b"Host: localhost\r\n",
            [b'{"unknownLamp', b'Field":true,"authToken":"private-body-token"}'],
            "complete_json",
        ),
        (b"Host: localhost\r\n", [], "time_limit"),
        (b"Host: localhost\r\n", [b'{"authToken":"private-body-token"'], "time_limit"),
        (b"Host: localhost\r\n", [b"private-unparsed-content"], "time_limit"),
        (
            b"Bad header : private-malformed-value\r\n",
            [b'{"unknownLampField":true}'],
            "complete_json",
        ),
    ],
)
def test_https_unframed_probe_reads_buffered_and_delayed_bytes_without_leaking_raw_text(
    socket_enabled, tls_material, monkeypatch, wire_headers, pieces, termination
):
    monkeypatch.setattr(events, "UNFRAMED_PROBE_SECONDS", 0.25)
    cert, key = tls_material
    listener = events.NotificationListener(
        ("127.0.0.1", 0), "127.0.0.1", legacy_http_tls.server_context(cert, key), scrub
    )
    listener.start()
    try:
        context = legacy_http_tls.client_context(cert, key)
        with (
            socket.create_connection(("127.0.0.1", listener.server_port), timeout=2) as raw,
            context.wrap_socket(raw) as conn,
        ):
            conn.sendall(
                b"POST /notifications HTTP/1.1\r\n"
                + wire_headers
                + b"\r\n"
                + (pieces[0] if pieces else b"")
            )
            for piece in pieces[1:]:
                time.sleep(0.025)
                conn.sendall(piece)
            response = http.client.HTTPResponse(conn)
            response.begin()
            assert response.status == 200
            assert response.read() == b""
    finally:
        listener.stop()
    assert len(listener.events) == 1
    event = listener.events[0]
    assert event["body_read"] == {"mode": "unframed_probe", "termination": termination}
    assert event["bytes"] == sum(map(len, pieces))
    assert event["framing"]["content_length_fields"] == 0
    if termination == "complete_json":
        assert event["body"]["unknownLampField"] is True
    elif not pieces:
        assert event["body"] is None
    else:
        assert event["error"] == "non_json_notification"
        assert event["body_prefix_kind"] == (
            "json_container" if pieces[0].startswith(b"{") else "other"
        )
    if wire_headers.startswith(b"Bad"):
        assert event["framing"]["header_parse_defects"] == ["MissingHeaderBodySeparatorDefect"]
        assert event["framing"]["header_payload_bytes"] > 0
    assert "private-" not in json.dumps(event)
    assert listener.request_failures == 0
    assert listener.thread is not None
    assert not listener.thread.is_alive()


def test_unframed_probe_bounds_slow_trickle_by_total_time(monkeypatch):
    monkeypatch.setattr(
        events, "time", Mock(monotonic=Mock(side_effect=[10, 10, 10.6, 11.2, 11.8]))
    )
    stream = Mock()
    stream.read1.return_value = b"{"
    connection = Mock()
    connection.gettimeout.return_value = 3
    assert events.probe_unframed_body(stream, connection) == (b"{{{", "time_limit")
    assert stream.read1.call_count == 3
    connection.settimeout.assert_called_with(3)


def test_unframed_probe_limits_body_bytes_and_retains_partial_data_on_read_error(monkeypatch):
    monkeypatch.setattr(events, "MAX_BODY", 16)
    connection = Mock()
    assert events.probe_unframed_body(io.BytesIO(b"x" * 50), connection) == (
        b"x" * 17,
        "size_limit",
    )
    stream = Mock()
    stream.read1.side_effect = [b'{"partial":', OSError("private-error-detail")]
    assert events.probe_unframed_body(stream, connection) == (b'{"partial":', "read_error")
    assert events.probe_unframed_body(io.BytesIO(b"partial"), connection) == (
        b"partial",
        "peer_closed",
    )
