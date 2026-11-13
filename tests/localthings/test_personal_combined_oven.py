"""One physical Flex Duo device keeps independent cavity commands and identities."""

from collections import Counter
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.localthings.const import CONF_DEVICE_KEY, DOMAIN
from custom_components.localthings.entity import _is_included
from custom_components.localthings.oven_device import (
    CAVITY_KEYS,
    async_combine_oven_devices,
)
from custom_components.localthings.registry.adapter import _key, flatten
from custom_components.localthings.registry.entities import PLATFORM_OF
from custom_components.localthings.registry.subdevices import MAIN
from tests.test_legacy_http_lower_cavity import (
    PREFIX,
    _discovered,
    _fake_https,  # noqa: F401
    _FakeConnection,
    _lower,
    _routes,
    _seed,
)
from tests.test_subdevice_discovery import _coordinator, _discover


async def _load(hass, monkeypatch, coordinator, *, offline=False):
    await hass.async_block_till_done()
    entry = coordinator._entry
    hass.config_entries.async_update_entry(
        entry, version=4, data={**entry.data, CONF_DEVICE_KEY: coordinator.device_key}
    )
    monkeypatch.setattr(
        "custom_components.localthings.LocalThingsCoordinator", lambda *args: coordinator
    )
    monkeypatch.setattr(coordinator, "async_load_mode_specs", AsyncMock())
    monkeypatch.setattr(coordinator, "async_config_entry_first_refresh", AsyncMock())
    monkeypatch.setattr(coordinator, "async_close", AsyncMock())
    coordinator.async_set_updated_data(flatten(coordinator.bound, coordinator.entity_resources()))
    if offline:
        coordinator.last_update_success = False
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _rows(hass, coordinator):
    prefix = f"{DOMAIN}_{coordinator.device_key}_"
    return {
        (row.domain, row.unique_id.removeprefix(prefix)): row
        for row in er.async_entries_for_config_entry(
            er.async_get(hass), coordinator._entry.entry_id
        )
    }


def _seed_split_registry(hass, coordinator):
    devices, entities = dr.async_get(hass), er.async_get(hass)
    with patch("custom_components.localthings.coordinator.combined_lower", return_value=None):
        upper = devices.async_get_or_create(
            config_entry_id=coordinator._entry.entry_id, **coordinator.device_info_for(MAIN)
        )
        lower = devices.async_get_or_create(
            config_entry_id=coordinator._entry.entry_id,
            **coordinator.device_info_for(_lower(coordinator)),
        )
        for bound in coordinator.bound:
            if not _is_included(bound, coordinator):
                continue
            entities.async_get_or_create(
                PLATFORM_OF[type(bound.desc)],
                DOMAIN,
                f"{DOMAIN}_{coordinator.device_key}_{_key(bound)}",
                config_entry=coordinator._entry,
                device_id=upper.id if bound.subdevice == MAIN else lower.id,
            )
    return upper, lower, _rows(hass, coordinator)


@pytest.mark.parametrize("initially_divided", [False, True])
async def test_upgrade_groups_entities_preserves_ids_and_changes_cavity_labels(
    hass, monkeypatch, initially_divided
):
    coordinator = await _discovered(hass, _routes(divided=initially_divided))
    upper, lower, old_rows = _seed_split_registry(hass, coordinator)
    entities = er.async_get(hass)
    old_start = old_rows["button", "subdevice1_start_cooking"]
    entities.async_update_entity(
        old_start.entity_id, new_entity_id="button.my_lower_start", name="My Lower Start"
    )
    old_status = old_rows["sensor", "subdevice1_oven_state"]
    entities.async_update_entity(old_status.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    dr.async_get(hass).async_update_device(upper.id, name_by_user="My Flex Duo")
    old_rows = _rows(hass, coordinator)
    await _load(hass, monkeypatch, coordinator)

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), coordinator._entry.entry_id)
    assert [d.id for d in devices] == [upper.id]
    assert devices[0].name_by_user == "My Flex Duo"
    assert entities.async_get(old_status.entity_id).disabled_by == er.RegistryEntryDisabler.USER
    assert dr.async_get(hass).async_get(lower.id) is None
    rows = _rows(hass, coordinator)
    removed = {
        ("binary_sensor", "divider"),
        ("binary_sensor", "subdevice1_door_open"),
        ("binary_sensor", "subdevice1_reservoir_open"),
        ("binary_sensor", "subdevice1_power_switch"),
        ("binary_sensor", "subdevice1_remote_control"),
    }
    expected = (old_rows.keys() - removed) | {
        ("sensor", "connection_mode"),
        ("sensor", "last_response"),
    }
    assert rows.keys() == expected, {
        "extra": rows.keys() - expected,
        "missing": expected - rows.keys(),
    }
    assert all(row.device_id == upper.id for row in rows.values())
    assert rows["button", "subdevice1_start_cooking"].entity_id == "button.my_lower_start"
    assert rows["button", "subdevice1_start_cooking"].name == "My Lower Start"
    for key, row in rows.items():
        if key in old_rows:
            assert row.entity_id == old_rows[key].entity_id
            assert row.unique_id == old_rows[key].unique_id

    counts = Counter(key.removeprefix("subdevice1_") for _, key in rows)
    for key in ("door_open", "divider", "reservoir_open", "power_switch", "remote_control"):
        assert counts[key] == 1
    for key in (
        "start_cooking",
        "stop",
        "oven_mode",
        "oven_setpoint",
        "cook_time_hours",
        "cook_time_minutes",
    ):
        assert counts[key] == 2
    assert ("binary_sensor", "subdevice1_divider") in rows
    assert ("binary_sensor", "divider") not in rows

    main_time = rows["number", "cook_time_minutes"].entity_id
    lower_time = rows["number", "subdevice1_cook_time_minutes"].entity_id
    for divided in (False, True, False, True):
        _FakeConnection.routes = _routes(divided=divided)
        for index in (0, 1):
            for href, rep in _seed(coordinator._session, index).items():
                coordinator._observe.apply(href, rep, source="poll")
        coordinator.async_set_updated_data(
            flatten(coordinator.bound, coordinator.entity_resources())
        )
        await hass.async_block_till_done()
        expected = "Upper" if divided else "Oven"
        state = hass.states.get(main_time)
        assert state is not None and expected + " Cook Time Minutes" in state.name
        assert entities.async_get(main_time).original_name == expected + " Cook Time Minutes"
        assert (hass.states.get(lower_time).state == "unavailable") is not divided
        assert entities.async_get("button.my_lower_start").name == "My Lower Start"
    assert _rows(hass, coordinator).keys() == rows.keys()
    await hass.config_entries.async_unload(coordinator._entry.entry_id)


async def test_old_layout_can_restore_device_and_entity_ids(hass, monkeypatch):
    coordinator = await _discovered(hass)
    upper, lower, old_rows = _seed_split_registry(hass, coordinator)
    devices = dr.async_get(hass)
    devices.async_update_device(lower.id, name_by_user="My Lower Oven")
    await _load(hass, monkeypatch, coordinator)
    assert devices.async_get(lower.id) is None
    await hass.config_entries.async_unload(coordinator._entry.entry_id)
    with patch("custom_components.localthings.coordinator.combined_lower", return_value=None):
        await _load(hass, monkeypatch, coordinator)
        rows = _rows(hass, coordinator)
        restored = devices.async_get(lower.id)
        assert restored is not None and restored.name_by_user == "My Lower Oven"
        for key, old in old_rows.items():
            assert rows[key].entity_id == old.entity_id
            assert rows[key].device_id == old.device_id
        assert {
            d.id for d in dr.async_entries_for_config_entry(devices, coordinator._entry.entry_id)
        } == {upper.id, lower.id}
        await hass.config_entries.async_unload(coordinator._entry.entry_id)


async def test_combined_start_action_selects_lower_and_upper_without_crossing_settings(
    hass, monkeypatch
):
    coordinator = await _discovered(hass)
    hass.config.units = US_CUSTOMARY_SYSTEM
    await _load(hass, monkeypatch, coordinator)
    device = dr.async_entries_for_config_entry(dr.async_get(hass), coordinator._entry.entry_id)[0]
    for cavity, mode, path, temperature, duration in (
        ("lower", "LowerBake", "/devices/1", 350, "00:07:00"),
        ("upper", "UpperConvectionBake", "/devices/0", 375, "00:05:00"),
    ):
        _FakeConnection.log.clear()
        await hass.services.async_call(
            DOMAIN,
            "start_cooking",
            {
                "device_id": device.id,
                "cavity": cavity,
                "mode": mode,
                "temperature": temperature,
                "duration": duration,
            },
            blocking=True,
        )
        writes = [(href, body) for method, href, body, _ in _FakeConnection.log if method == "PUT"]
        assert writes == [
            (
                path,
                {
                    "Device": {
                        "Mode": {"modes": [mode]},
                        "Temperatures": [{"id": "0", "desired": temperature, "unit": "Fahrenheit"}],
                        "Operation": {"operationTime": duration},
                    }
                },
            ),
            (path, {"Device": {"Operation": {"state": "Run"}}}),
        ]
    coordinator._observe.apply("/connected/vs/1", {PREFIX + "connected": "Off"}, source="poll")
    _FakeConnection.log.clear()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "start_cooking", {"device_id": device.id, "cavity": "lower"}, blocking=True
        )
    assert not any(method == "PUT" for method, *_ in _FakeConnection.log)
    await hass.config_entries.async_unload(coordinator._entry.entry_id)


async def test_unidentified_sibling_keeps_separate_devices(hass):
    coordinator = await _discovered(hass)
    coordinator._observe.apply(
        "/information/vs/1", {PREFIX + "description": "OTHER"}, source="poll"
    )
    assert coordinator.combined_oven_lower is None
    assert (
        coordinator.device_info_for(_lower(coordinator))["identifiers"]
        != coordinator.device_info["identifiers"]
    )


async def test_only_the_owning_entry_is_migrated(hass):
    coordinator = await _discovered(hass)
    other = MockConfigEntry(domain=DOMAIN)
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    foreign = registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{DOMAIN}_{coordinator.device_key}_subdevice1_remote_control",
        config_entry=other,
    )
    async_combine_oven_devices(hass, coordinator._entry, coordinator)
    assert registry.async_get(foreign.entity_id) == foreign


@pytest.mark.parametrize("language", ["cs", "de", "en", "es", "fr", "it", "ko", "nl", "pl", "sk"])
async def test_cavity_names_and_mode_states_are_translated(hass, monkeypatch, language):
    import json
    from pathlib import Path

    catalog = json.loads(
        (
            Path(__file__).parents[2]
            / "custom_components"
            / "localthings"
            / "translations"
            / f"{language}.json"
        ).read_text()
    )
    hass.config.language = language
    coordinator = await _discovered(hass)
    await _load(hass, monkeypatch, coordinator)
    rows = _rows(hass, coordinator)
    for (domain, key), row in rows.items():
        base = key.removeprefix("subdevice1_")
        if base not in CAVITY_KEYS:
            continue
        expected = catalog["entity"][domain][row.translation_key]
        label = "lower" if key.startswith("subdevice1_") else "upper"
        name = expected["name"].format(
            cavity=catalog["selector"]["instance_name"]["options"][f"oven_cavity_{label}"]
        )
        assert row.original_name == name
        if base == "oven_mode":
            assert expected["state"] == catalog["entity"]["select"]["oven_title_oven_mode"]["state"]
        if base == "start_cooking":
            assert catalog["entity"]["button"]["start"]["name"] in row.original_name
    await hass.config_entries.async_unload(coordinator._entry.entry_id)


async def _ocf_coordinator(hass, fixture):
    coordinator = _coordinator(hass)
    if fixture == "oven_lcd_r18":
        from tests.test_dual_cook_lower_zone import LOWER, _resources

        resources = _resources()
        coordinator.subdevices = [LOWER]
        coordinator._run_discovery(resources)
        for href, rep in resources.items():
            coordinator._observe.apply(href, rep, source="poll")
    else:
        await _discover(coordinator, fixture)
    return coordinator


async def test_offline_snapshot_still_registers_one_device_and_one_set_of_shared_sensors(
    hass, monkeypatch
):
    coordinator = await _discovered(hass, _routes(divided=False))
    coordinator._rehydrate_resources = coordinator.last_resources
    coordinator._cache.links.clear()
    coordinator._canonical_cache.clear()
    await _load(hass, monkeypatch, coordinator, offline=True)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), coordinator._entry.entry_id)
    assert len(devices) == 1
    rows = _rows(hass, coordinator)
    for key in ("door_open", "divider", "reservoir_open", "remote_control", "power_switch"):
        assert sum(k.removeprefix("subdevice1_") == key for _, k in rows) == 1
    assert ("button", "subdevice1_start_cooking") in rows
    for (domain, key), row in rows.items():
        if key == "connection_mode" or row.disabled_by is not None:
            continue
        assert hass.states.get(row.entity_id).state == "unavailable", (domain, key)
    await hass.config_entries.async_unload(coordinator._entry.entry_id)


async def test_disabled_lower_device_remains_separate_and_disabled(hass, monkeypatch):
    coordinator = await _discovered(hass)
    upper, lower, old_rows = _seed_split_registry(hass, coordinator)
    devices = dr.async_get(hass)
    devices.async_update_device(lower.id, disabled_by=dr.DeviceEntryDisabler.USER)
    assert coordinator.combined_oven_lower is None
    await _load(hass, monkeypatch, coordinator)
    registered = devices.async_get(lower.id)
    assert registered is not None and registered.disabled_by == dr.DeviceEntryDisabler.USER
    rows = _rows(hass, coordinator)
    for key, old in old_rows.items():
        assert rows[key].entity_id == old.entity_id
        assert rows[key].device_id == old.device_id
    assert coordinator.device_info_for(MAIN)["identifiers"] == upper.identifiers
    await hass.config_entries.async_unload(coordinator._entry.entry_id)


@pytest.mark.parametrize(
    "fixture",
    [
        "oven_lcd_r18",
        "oven_nv75n_dual_cook",
        "microwave_nw9300md",
        "oven_tp2x_ks_walloven",
        "refrigerator",
        "cooktop",
    ],
)
async def test_other_appliances_keep_upstream_device_layout(hass, fixture):
    coordinator = await _ocf_coordinator(hass, fixture)
    assert coordinator.combined_oven_lower is None


async def test_diagnosis_status_is_kept_but_start_is_hidden(hass, monkeypatch):
    coordinator = await _discovered(hass)
    await _load(hass, monkeypatch, coordinator)
    rows = _rows(hass, coordinator)
    assert ("sensor", "diagnosis_status") in rows
    assert ("sensor", "alarm_code") in rows
    assert not any(key.endswith("diagnosis_start") for _, key in rows)
    await hass.config_entries.async_unload(coordinator._entry.entry_id)
