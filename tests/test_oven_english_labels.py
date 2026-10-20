"""English oven labels preserve other languages, identities and command values."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.localthings.const import CONF_DEVICE_KEY, DOMAIN
from custom_components.localthings.coordinator import LocalThingsCoordinator
from custom_components.localthings.entity import LocalThingsEntity
from custom_components.localthings.registry.adapter import flatten
from custom_components.localthings.registry.oven_labels import oven_label_key
from custom_components.localthings.select import LocalThingsSelect
from custom_components.localthings.sensor import (
    LocalThingsConnectionModeSensor,
    LocalThingsLastResponseSensor,
)
from tests.test_legacy_http_lower_cavity import (
    PREFIX,
    _discovered,
    _fake_https,  # noqa: F401 -- fake legacy transport
    _requests,
    _routes,
)
from tests.test_subdevice_discovery import _coordinator, _discover
from tests.test_translations import _languages
from tests.test_translations import _load as _catalog


async def _load(hass, monkeypatch, coordinator):
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
    if coordinator.rehydrated:
        coordinator._publish_data()
    else:
        coordinator.async_set_updated_data(
            flatten(coordinator.bound, coordinator.entity_resources())
        )
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


@pytest.mark.parametrize("language", _languages())
@pytest.mark.parametrize("divided", [False, True])
async def test_upgrade_preserves_ids_custom_names_and_other_languages(
    hass, monkeypatch, enable_custom_integrations, language, divided
):
    hass.config.language = language
    coordinator = await _discovered(hass, _routes(divided=divided))
    with monkeypatch.context() as previous:
        previous.setattr("custom_components.localthings.sensor.oven_label_key", lambda key, r: key)
        previous.setattr("custom_components.localthings.entity.oven_label_key", lambda key, r: key)
        await _load(hass, previous, coordinator)
        rows = _rows(hass, coordinator)
        entities, devices = er.async_get(hass), dr.async_get(hass)
        custom = rows["number", "cook_time"]
        entities.async_update_entity(
            custom.entity_id, new_entity_id="number.my_cook_time", name="My cooking timer"
        )
        disabled = rows["sensor", "alarm_code"]
        entities.async_update_entity(disabled.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
        old_devices = {}
        for device_id in {row.device_id for row in rows.values()}:
            assert device_id is not None
            old_devices[device_id] = devices.async_update_device(device_id, name_by_user="My Oven")
        old_rows = _rows(hass, coordinator)
        await hass.config_entries.async_unload(coordinator._entry.entry_id)
    await _load(hass, monkeypatch, coordinator)

    rows = _rows(hass, coordinator)
    assert rows.keys() == old_rows.keys()
    catalog = _catalog(language)["entity"]
    for (platform, key), row in rows.items():
        old = old_rows[platform, key]
        assert (row.entity_id, row.unique_id, row.device_id, row.name, row.disabled_by) == (
            old.entity_id,
            old.unique_id,
            old.device_id,
            old.name,
            old.disabled_by,
        )
        if row.translation_key.startswith("oven_title_"):
            assert row.translation_key == "oven_title_" + old.translation_key
            assert row.original_name == catalog[platform][row.translation_key]["name"]
            if language != "en":
                assert row.original_name == old.original_name
        else:
            assert row.original_name == old.original_name
    assert hass.states.get("number.my_cook_time").name.endswith("My cooking timer")
    assert rows["select", "oven_mode"].original_name == (
        "Cooking Mode" if language == "en" else catalog["select"]["oven_mode"]["name"]
    )
    for device_id, old in old_devices.items():
        current = devices.async_get(device_id)
        assert current is not None and old is not None
        assert (current.name, current.name_by_user, current.identifiers) == (
            old.name,
            old.name_by_user,
            old.identifiers,
        )
    assert not any(method == "PUT" for method, _ in _requests())
    await hass.config_entries.async_unload(coordinator._entry.entry_id)


async def test_offline_startup_uses_the_saved_model(hass, monkeypatch, enable_custom_integrations):
    online = await _discovered(hass)
    await online._async_save_snapshot(online.last_resources, online.subdevices)
    restored = LocalThingsCoordinator(hass, online._entry)
    restored.async_set_update_error(UpdateFailed("device offline"))
    assert await restored.async_rehydrate()
    await _load(hass, monkeypatch, restored)
    rows = _rows(hass, restored)
    for identity, name in [
        (("select", "oven_mode"), "Cooking Mode"),
        (("sensor", "connection_mode"), "Connection Mode"),
        (("sensor", "last_response"), "Last Response"),
    ]:
        assert rows[identity].original_name == name
    assert hass.states.get(rows["select", "oven_mode"].entity_id).state == "unavailable"
    await hass.config_entries.async_unload(restored._entry.entry_id)


@pytest.mark.parametrize("divided", [False, True])
async def test_mode_values_current_selection_and_cavity_writes_are_unchanged(
    hass, monkeypatch, divided
):
    coordinator = await _discovered(hass, _routes(divided=divided))
    send = AsyncMock()
    monkeypatch.setattr(coordinator, "async_send_command", send)
    for bound in coordinator.bound:
        if bound.desc.key != "oven_mode":
            continue
        entity = LocalThingsSelect(coordinator, bound)
        original = LocalThingsSelect(
            coordinator, replace(bound, desc=replace(bound.desc, translation_key="oven_mode"))
        )
        coordinator.async_set_updated_data(
            flatten(coordinator.bound, coordinator.entity_resources())
        )
        assert entity.options == original.options
        assert entity.current_option == original.current_option
        for raw in entity._raw_options():
            if raw == "NoOperation":
                continue
            await entity.async_select_option(entity._display_option(raw))
            send.assert_awaited_once_with(bound, raw)
            send.reset_mock()


@pytest.mark.parametrize(
    "fixture",
    [
        "oven_nv75n_dual_cook",
        "oven_tp2x_ks_walloven",
        "microwave_nw9300md",
        "range_tp1x_da_ks_range_0101x",
        "airconditioner_fac_bora_2in1",
    ],
)
async def test_other_appliances_use_their_existing_catalogs(hass, fixture):
    coordinator = _coordinator(hass)
    await _discover(coordinator, fixture)
    for bound in coordinator.bound:
        key = LocalThingsEntity(coordinator, bound).translation_key
        assert key is None or not key.startswith("oven_title_")
    assert LocalThingsConnectionModeSensor(coordinator).translation_key == "connection_mode"
    assert LocalThingsLastResponseSensor(coordinator).translation_key == "last_response"


@pytest.mark.parametrize(
    "model",
    [None, 16, "LCD_OV_WALL", "LCD_OV_WALL_16K_DIV", "LCD_OV_WALL_16K_OTHER", "LCD_OV_WALL_20K"],
)
def test_similar_board_names_do_not_opt_in(model):
    assert oven_label_key("oven_mode", {"/information/vs/0": {PREFIX + "modelNum": model}}) == (
        "oven_mode"
    )


def test_catalogs_preserve_original_wording_and_mode_codes():
    for language in _languages():
        for platform, entries in _catalog(language)["entity"].items():
            for key, entry in entries.items():
                if not key.startswith("oven_title_"):
                    continue
                original = entries[key.removeprefix("oven_title_")]
                if language != "en":
                    assert entry == original
                    continue
                assert entry["name"].lower() == original["name"].lower()
                if platform == "select" and key == "oven_title_oven_mode":
                    assert entry["state"].keys() == original["state"].keys()
                    for code, label in entry["state"].items():
                        assert label.lower() == original["state"][code].lower()
                else:
                    assert entry.get("state") == original.get("state")
    english = _catalog("en")["entity"]
    assert english["button"]["oven_title_start_cooking"]["name"] == "Start Cooking"
    assert english["number"]["oven_title_cook_time"]["name"] == "Cook Time"
    assert english["switch"]["oven_title_energy_saving"]["name"] == "Energy Saving"
    assert english["select"]["oven_title_ai_energy_level"]["name"] == "AI Energy Mode Level"
    modes = english["select"]["oven_title_oven_mode"]["state"]
    assert modes["convection_bake"] == "Convection Bake"
    assert modes["keep_warm"] == "Keep Warm"
    assert modes["bread_proof"] == "Bread Proof"


async def test_labels_preserve_capability_identity_for_upgrade_cleanup(hass):
    from custom_components.localthings.registry.capabilities import oven

    coordinator = await _discovered(hass)
    modes = [bound for bound in coordinator.bound if bound.desc.key == "oven_mode"]
    assert modes
    for bound in modes:
        assert bound.capability is oven.OVEN_MODE
        assert LocalThingsEntity(coordinator, bound).translation_key == "oven_title_oven_mode"
