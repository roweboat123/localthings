"""The native capture exports unknown state fields without appliance writes."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from custom_components.localthings.registry.redact import redact_resources
from docs.investigations import legacy_oven_capture as capture

DATA = {
    "transport": "legacy_http",
    "legacy_family": "LCD_OV_WALL_16K",
    "host": "192.0.2.8",
    "device_token": "private-device-token",
    "leaf_cert_pem": "private-certificate",
    "leaf_key_pem": "private-key",
    "serial": "PRIVATE-SERIAL",
}


@pytest.mark.parametrize("scope", ["baseline", "all_resources", "light_resource", "capability"])
def test_capture_preserves_native_scalars_and_uses_only_known_gets(monkeypatch, capsys, scope):
    connections = []

    def connect(host, port, **kwargs):
        assert host == DATA["host"]
        assert port == 8888
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps(
            {"Device": {"id": "PRIVATE-SERIAL", "name": "Private name", "lamp": True}}
        ).encode()
        connections.append(connection)
        return connection

    monkeypatch.setattr(capture.http.client, "HTTPSConnection", connect)
    report = capture.capture(
        DATA,
        object(),
        redact_resources,
        "on",
        all_resources=scope == "all_resources",
        light_resource=scope == "light_resource",
        capability=scope == "capability",
    )

    endpoints = {
        "baseline": capture.ENDPOINTS,
        "all_resources": capture.ALL_ENDPOINTS,
        "light_resource": ("/devices/0/light", "/devices/1/light"),
        "capability": ("/capability",),
    }[scope]
    assert report["scope"] == scope
    assert len(connections) == len(endpoints)
    for path, connection, record in zip(endpoints, connections, report["responses"], strict=True):
        connection.request.assert_called_once_with(
            "GET", path, headers={"Authorization": "Bearer private-device-token", "Accept": "*/*"}
        )
        connection.close.assert_called_once()
        assert record["body"]["Device"]["lamp"] is True
        assert record["body"]["Device"]["name"] == capture.REDACTED
        assert record["body"]["Device"]["id"] == capture.REDACTED
    assert "private-device-token" not in json.dumps(report) + capsys.readouterr().err


def test_light_probe_retains_missing_resource_response(monkeypatch):
    connection = Mock()
    connection.getresponse.return_value.status = 404
    connection.getresponse.return_value.read.return_value = b'{"error": "Not Found"}'
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", Mock(return_value=connection))
    report = capture.capture(DATA, object(), redact_resources, "off", light_resource=True)
    assert [record["http_status"] for record in report["responses"]] == [404, 404]
    assert all(record["body"] == {"error": "Not Found"} for record in report["responses"])


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("all_resources", "light_resource"),
        ("all_resources", "capability"),
        ("light_resource", "capability"),
    ],
)
def test_conflicting_capture_scopes_do_not_send_requests(monkeypatch, first, second):
    connect = Mock()
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", connect)
    with pytest.raises(ValueError):
        capture.capture(DATA, object(), redact_resources, "off", **{first: True, second: True})
    with pytest.raises(SystemExit) as error:
        capture.main(["off", "--" + first.replace("_", "-"), "--" + second.replace("_", "-")])
    assert error.value.code == 2
    connect.assert_not_called()


def test_capability_xml_keeps_services_but_removes_identity(monkeypatch):
    connection = Mock()
    response = connection.getresponse.return_value
    response.status = 200
    response.read.return_value = b"""<?xml version="1.0"?>
    <root xmlns="urn:example:device">
      <device>
        <friendlyName>Private kitchen name</friendlyName>
        <serialNumber>new-private-serial</serialNumber>
        <UDN>uuid:12345678-1234-1234-1234-123456789abc</UDN>
        <URLBase>https://192.0.2.8:8888/</URLBase>
        <metadata token="new-private-token"/>
        <serviceList>
          <service><serviceType>ExampleStatus</serviceType><eventSubURL>/events</eventSubURL></service>
          <service><serviceType>ExampleLight</serviceType><state>Off</state></service>
        </serviceList>
      </device>
    </root>"""
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", Mock(return_value=connection))
    report = capture.capture(DATA, object(), redact_resources, None, capability=True)
    record = report["responses"][0]
    assert record["body_format"] == "xml"
    encoded = json.dumps(report)
    for value in ("Private kitchen", "new-private", "192.0.2.8", "12345678-"):
        assert value not in encoded
    services = record["body"]["root"]["device"][0]["serviceList"][0]["service"]
    assert services[0]["eventSubURL"] == ["/events"]
    assert services[1]["state"] == ["Off"]
    assert report["light"] is None
    connection.request.assert_called_once_with(
        "GET",
        "/capability",
        headers={"Authorization": "Bearer private-device-token", "Accept": "*/*"},
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"<html>private-device-token</html>",
        b"<root><invalid>private-device-token",
        b'<!DOCTYPE root [<!ENTITY secret "private-device-token">]><root>&secret;</root>',
    ],
)
def test_capability_does_not_export_unparsed_or_entity_document(monkeypatch, raw):
    connection = Mock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = raw
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", Mock(return_value=connection))
    result = capture.read_native(DATA["host"], object(), DATA["device_token"], "/capability")
    assert result["error"] == "unparsed_capability_response"
    assert "body" not in result
    assert "private-device-token" not in json.dumps(result)


def test_capability_keeps_error_and_does_not_follow_redirect(monkeypatch):
    connection = Mock()
    response = connection.getresponse.return_value
    response.status = 302
    response.read.return_value = b'{"errorDescription": "Not supported resource"}'
    response.getheader.return_value = "https://example.com/"
    connect = Mock(return_value=connection)
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", connect)
    report = capture.capture(DATA, object(), redact_resources, None, capability=True)
    assert report["responses"][0]["http_status"] == 302
    assert report["responses"][0]["body"]["errorDescription"] == "Not supported resource"
    connect.assert_called_once()
    connection.request.assert_called_once()


def test_cli_capability_saves_report_without_light_label(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(capture, "select_entry", Mock(return_value=DATA))
    tls = Mock()
    redactor = Mock(redact_resources=redact_resources)
    monkeypatch.setattr(capture, "load_support", Mock(side_effect=[tls, redactor]))
    monkeypatch.setattr(
        capture,
        "read_native",
        Mock(
            return_value={
                "http_status": 405,
                "body": {"errorDescription": "Not supported resource"},
            }
        ),
    )
    assert capture.main(["--capability", "--config-dir", str(tmp_path)]) == 1
    reports = list(tmp_path.glob("oven-capability-*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report["scope"] == "capability"
    assert report["light"] is None
    assert reports[0].stat().st_mode & 0o777 == 0o600
    assert "Saved:" in capsys.readouterr().err


def test_cli_still_requires_label_for_existing_scopes(monkeypatch):
    select = Mock()
    monkeypatch.setattr(capture, "select_entry", select)
    with pytest.raises(SystemExit) as error:
        capture.main([])
    assert error.value.code == 2
    select.assert_not_called()


@pytest.mark.parametrize(
    "path", ["/devices/0/lamp", "https://example.com/", "/devices/0/operation/start"]
)
def test_capture_will_not_probe_unlisted_endpoints(monkeypatch, path):
    connect = Mock()
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", connect)
    with pytest.raises(ValueError):
        capture.read_native(DATA["host"], object(), DATA["device_token"], path)
    connect.assert_not_called()


def test_capture_scrubs_identifiers_and_credentials_without_dropping_state():
    raw = {
        "name": "Owner's oven",
        "description": "LCD_OV_WALL_16K_PRIVATE-SERIAL",
        "oddField": "private-device-token private-key 192.0.2.8 PRIVATE-SERIAL owner@example.com",
        "authToken": "newly-returned-token",
        "nested": [{"serialNum": "serial-from-response", "id": "0", "light": "Off"}],
        "options": ["waterTankInSwitch_On", "waterTankOutSwitch_Off"],
    }
    result = capture.scrub(raw, DATA, redact_resources)
    text = json.dumps(result)
    for private in (
        "Owner",
        "PRIVATE-SERIAL",
        "private-",
        "192.0.2.8",
        "owner@",
        "newly-returned",
        "serial-from-response",
    ):
        assert private not in text
    assert result["nested"][0]["id"] == "0"
    assert result["nested"][0]["light"] == "Off"
    assert result["options"] == raw["options"]


@pytest.mark.parametrize(
    "response_body", [b"<html>private-device-token</html>", b"x" * (capture.MAX_RESPONSE_BYTES + 1)]
)
def test_non_json_or_oversize_body_is_not_exported(monkeypatch, response_body):
    connection = Mock()
    connection.getresponse.return_value.status = 500
    connection.getresponse.return_value.read.return_value = response_body
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", Mock(return_value=connection))
    result = capture.read_native(DATA["host"], object(), DATA["device_token"], "/devices")
    assert "body" not in result
    assert "private-device-token" not in json.dumps(result)
    connection.close.assert_called_once()


def test_connection_errors_do_not_echo_credentials(monkeypatch):
    connection = Mock()
    connection.request.side_effect = OSError("private-device-token")
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", Mock(return_value=connection))
    assert capture.read_native(DATA["host"], object(), DATA["device_token"], "/devices") == {
        "error": "OSError"
    }
    connection.close.assert_called_once()


@pytest.mark.parametrize("duplicate", [False, True])
def test_capture_selects_only_the_intended_oven_entry(tmp_path: Path, duplicate):
    storage = tmp_path / ".storage"
    storage.mkdir()
    entries = [
        {"domain": "localthings", "entry_id": "oven", "data": DATA},
        {
            "domain": "localthings",
            "entry_id": "cooktop",
            "data": {**DATA, "legacy_family": "TP6X_CT_16K"},
        },
        {"domain": "other", "entry_id": "other", "data": DATA},
    ]
    if duplicate:
        entries.append({"domain": "localthings", "entry_id": "second_oven", "data": DATA})
    (storage / "core.config_entries").write_text(json.dumps({"data": {"entries": entries}}))
    assert capture.select_entry(tmp_path, "oven") == DATA
    if duplicate:
        with pytest.raises(ValueError):
            capture.select_entry(tmp_path)
    else:
        assert capture.select_entry(tmp_path) == DATA


def test_capture_loads_support_without_importing_home_assistant():
    root = Path(__file__).resolve().parents[1]
    assert callable(capture.load_support(root, "legacy_http_tls.py").client_context)
    assert callable(capture.load_support(root, "registry/redact.py").redact_resources)
