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


@pytest.mark.parametrize("scope", ["baseline", "all_resources", "light_resource"])
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
    )

    endpoints = {
        "baseline": capture.ENDPOINTS,
        "all_resources": capture.ALL_ENDPOINTS,
        "light_resource": ("/devices/0/light", "/devices/1/light"),
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


def test_conflicting_capture_scopes_do_not_send_requests(monkeypatch):
    connect = Mock()
    monkeypatch.setattr(capture.http.client, "HTTPSConnection", connect)
    with pytest.raises(ValueError):
        capture.capture(
            DATA, object(), redact_resources, "off", all_resources=True, light_resource=True
        )
    with pytest.raises(SystemExit) as error:
        capture.main(["off", "--all-resources", "--light-resource"])
    assert error.value.code == 2
    connect.assert_not_called()


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
