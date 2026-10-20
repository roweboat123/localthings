"""NV51K7770S labels follow the divider without replacing devices or entities."""

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.localthings.const import CONF_DEVICE_KEY, DOMAIN
from custom_components.localthings.coordinator import LocalThingsCoordinator
from custom_components.localthings.entity import LocalThingsEntity
from custom_components.localthings.oven_labels import CAVITY_KEYS, main_cavity_divider
from custom_components.localthings.registry.adapter import flatten
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


async def _set_divider(hass, coordinator, state):
    coordinator._observe.apply("/connected/vs/1", {PREFIX + "connected": state}, source="poll")
    coordinator._publish_data()
    await hass.async_block_till_done()


@pytest.mark.parametrize("language", _languages())
@pytest.mark.parametrize("initially_divided", [False, True])
async def test_upgrade_and_live_labels_preserve_identity_and_user_names(
    hass, monkeypatch, language, initially_divided
):
    hass.config.language = language
    coordinator = await _discovered(hass, _routes(divided=initially_divided))
    with monkeypatch.context() as previous:
        previous.setattr(
            "custom_components.localthings.entity.main_cavity_divider", lambda resources: None
        )
        await _load(hass, previous, coordinator)
    old_rows = _rows(hass, coordinator)
    device_ids = {row.device_id for row in old_rows.values()}
    assert len(device_ids) == 2
    devices, entities = dr.async_get(hass), er.async_get(hass)
    for index, device_id in enumerate(sorted(device_ids)):
        devices.async_update_device(device_id, name_by_user=f"My Oven {index}")
    old_devices = {device_id: devices.async_get(device_id) for device_id in device_ids}
    custom = old_rows["number", "oven_setpoint"]
    custom = entities.async_update_entity(
        custom.entity_id, new_entity_id="number.my_oven_target", name="My Setpoint"
    )
    old_rows["number", "oven_setpoint"] = custom
    await hass.config_entries.async_unload(coordinator._entry.entry_id)
    await _load(hass, monkeypatch, coordinator)
    reload_requested = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", reload_requested)
    catalog = _catalog(language)

    for state in ("On" if initially_divided else "Off", "Off", "On", None, "Unexpected"):
        await _set_divider(hass, coordinator, state)
        rows = _rows(hass, coordinator)
        assert rows.keys() == old_rows.keys()
        label = "oven" if state == "Off" else "upper"
        for (domain, key), row in rows.items():
            old = old_rows[domain, key]
            assert (row.entity_id, row.unique_id, row.device_id) == (
                old.entity_id,
                old.unique_id,
                old.device_id,
            )
            if key in CAVITY_KEYS:
                expected = catalog["entity"][domain]["oven_cavity_" + old.translation_key]
                name = expected["name"].format(
                    cavity=catalog["selector"]["instance_name"]["options"][f"oven_cavity_{label}"]
                )
                assert row.original_name == name
                assert row.translation_key == "oven_cavity_" + old.translation_key
                assert hass.states.get(row.entity_id).name.endswith(
                    "My Setpoint" if row.entity_id == custom.entity_id else name
                )
            else:
                assert row.original_name == old.original_name
                assert row.translation_key == old.translation_key
        current = entities.async_get(custom.entity_id)
        assert current is not None
        assert current.name == "My Setpoint"
        for device_id, old in old_devices.items():
            current = devices.async_get(device_id)
            assert current is not None and old is not None
            assert (current.identifiers, current.name, current.name_by_user) == (
                old.identifiers,
                old.name,
                old.name_by_user,
            )
    reload_requested.assert_not_called()
    assert not any(method == "PUT" for method, _ in _requests())
    await hass.config_entries.async_unload(coordinator._entry.entry_id)


@pytest.mark.parametrize("divided", [False, True])
async def test_offline_snapshot_uses_saved_label_and_updates_on_reconnect(
    hass, monkeypatch, divided
):
    online = await _discovered(hass, _routes(divided=divided))
    await online._async_save_snapshot(online.last_resources, online.subdevices)
    restored = LocalThingsCoordinator(hass, online._entry)
    restored.async_set_update_error(UpdateFailed("device offline"))
    assert await restored.async_rehydrate()
    assert restored.last_resources == {}
    await _load(hass, monkeypatch, restored)
    rows = _rows(hass, restored)
    target = rows["number", "oven_setpoint"]
    assert target.original_name == ("Upper" if divided else "Oven") + " Setpoint"
    assert hass.states.get(target.entity_id).state == "unavailable"
    restored._rehydrate_resources = None
    for href, rep in online.last_resources.items():
        restored._observe.apply(href, rep, source="poll")
    restored.last_update_success = True
    await _set_divider(hass, restored, "Off" if divided else "On")
    updated = _rows(hass, restored)["number", "oven_setpoint"]
    assert updated.entity_id == target.entity_id
    assert updated.original_name == ("Oven" if divided else "Upper") + " Setpoint"
    await hass.config_entries.async_unload(restored._entry.entry_id)


@pytest.mark.parametrize(
    "model",
    [None, 16, "LCD_OV_WALL", "LCD_OV_WALL_16K_DIV", "LCD_OV_WALL_16K_OTHER", "LCD_OV_WALL_20K"],
)
def test_model_match_is_exact(model):
    assert main_cavity_divider({"/information/vs/0": {PREFIX + "modelNum": model}}) is None


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
async def test_other_devices_keep_original_entity_labels(hass, fixture):
    coordinator = _coordinator(hass)
    await _discover(coordinator, fixture)
    for bound in coordinator.bound:
        entity = LocalThingsEntity(coordinator, bound)
        assert entity._oven_divider_href is None
        assert "cavity" not in entity.translation_placeholders


@pytest.mark.parametrize("device_type", ["microwave", "range", None])
async def test_model_token_cannot_enable_labels_in_another_registry(hass, device_type):
    coordinator = await _discovered(hass)
    coordinator.device_type_name = device_type
    for bound in coordinator.bound:
        entity = LocalThingsEntity(coordinator, bound)
        assert entity._oven_divider_href is None


def test_all_languages_keep_existing_names_and_state_mappings():
    for language in _languages():
        catalog = _catalog(language)
        for entries in catalog["entity"].values():
            for key, value in entries.items():
                if not key.startswith("oven_cavity_"):
                    continue
                original = entries[key.removeprefix("oven_cavity_")]
                assert value["name"].endswith(original["name"])
                assert value.get("state") == original.get("state")
                assert value["name"].count("{cavity}") == 1
