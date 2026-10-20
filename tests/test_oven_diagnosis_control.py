"""Withdraw the measured oven's unverified diagnosis button, keeping status."""

from copy import deepcopy

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.localthings import _drop_unverified_oven_diagnosis_buttons
from custom_components.localthings.const import DOMAIN
from custom_components.localthings.coordinator import LocalThingsCoordinator
from custom_components.localthings.entity import _is_included
from custom_components.localthings.registry.adapter import _key, flatten
from custom_components.localthings.registry.by_type import oven as oven_registry
from custom_components.localthings.registry.capabilities import dishwasher, oven
from custom_components.localthings.registry.discovery import discover
from custom_components.localthings.registry.entities import ButtonDesc
from custom_components.localthings.registry.subdevices import MAIN
from tests.test_legacy_http_lower_cavity import (
    LOWER,
    PREFIX,
    _discovered,
    _fake_https,  # noqa: F401 -- fake legacy transport
    _requests,
    _routes,
)


def _buttons(coordinator):
    return [b for b in coordinator.bound if b.desc.key == "diagnosis_start"]


@pytest.mark.parametrize("divided", [False, True])
async def test_start_is_absent_but_status_and_energy_saving_remain(hass, divided):
    coordinator = await _discovered(hass, _routes(divided=divided))
    included = [b for b in coordinator.bound if _is_included(b, coordinator)]
    assert not any(b.desc.key == "diagnosis_start" for b in included)
    status = next(b for b in included if b.desc.key == "diagnosis_status")
    assert status.desc is next(
        d for d in dishwasher.DIAGNOSIS.entities if d.key == "diagnosis_status"
    )
    state = flatten(coordinator.bound, coordinator.last_resources)
    assert state["diagnosis_status"] == "ready"
    assert state["energy_saving"] is True
    assert "alarm_code" in state
    assert any(b.desc.key == "sound" for b in included)
    assert not any(method == "PUT" for method, _ in _requests())


@pytest.mark.parametrize(
    "model", [None, 16, "LCD_OV_WALL", "LCD_OV_WALL_16K_OTHER", "LCD_OV_WALL_20K"]
)
async def test_other_boards_keep_the_diagnosis_command(hass, model):
    coordinator = await _discovered(hass)
    resources = deepcopy(coordinator.canonical_resources(MAIN))
    resources["/information/vs/0"][PREFIX + "modelNum"] = model
    bound = discover(resources, oven_registry.REGISTRY.capabilities)
    start = next(b for b in bound if b.desc.key == "diagnosis_start")
    assert isinstance(start.desc, ButtonDesc)
    assert start.desc.exists_fn is not None
    assert start.desc.exists_fn(resources[start.href], resources)
    original = next(d for d in dishwasher.DIAGNOSIS.entities if d.key == "diagnosis_start")
    assert isinstance(original, ButtonDesc)
    assert start.desc.write_fn is original.write_fn


@pytest.mark.parametrize("disabled", [False, True])
async def test_cleanup_is_exact_per_cavity_and_idempotent(hass, disabled, caplog):
    lower = deepcopy(LOWER)
    lower["Diagnosis"] = {"diagnosisStart": "Ready"}
    coordinator = await _discovered(hass, _routes(lower=lower))
    buttons = _buttons(coordinator)
    assert len(buttons) == 2
    registry = er.async_get(hass)
    removed = []
    keep = []
    for i, bound in enumerate(buttons):
        uid = f"{DOMAIN}_{coordinator.device_key}_{_key(bound)}"
        old = registry.async_get_or_create(
            "button",
            DOMAIN,
            uid,
            config_entry=coordinator._entry,
            disabled_by=er.RegistryEntryDisabler.USER if disabled else None,
        )
        old = registry.async_update_entity(old.entity_id, new_entity_id=f"button.renamed_check_{i}")
        removed.append(old)
        keep.extend(
            registry.async_get_or_create(platform, domain, key, config_entry=coordinator._entry)
            for platform, domain, key in (
                ("button", DOMAIN, uid + "_other"),
                ("button", "other_integration", uid),
                ("sensor", DOMAIN, uid),
                ("sensor", DOMAIN, uid.replace("diagnosis_start", "diagnosis_status")),
            )
        )
    with caplog.at_level("INFO", logger="custom_components.localthings"):
        _drop_unverified_oven_diagnosis_buttons(hass, coordinator._entry, coordinator)
        _drop_unverified_oven_diagnosis_buttons(hass, coordinator._entry, coordinator)
    assert all(registry.async_get(e.entity_id) is None for e in removed)
    assert all(registry.async_get(e.entity_id) for e in keep)
    for old in removed:
        assert caplog.text.count(f"Removing {old.entity_id}:") == 1


@pytest.mark.parametrize("guard", ["other_entry", "other_model", "missing_diagnosis"])
async def test_cleanup_preserves_unmatched_entries(hass, guard):
    coordinator = await _discovered(hass)
    entry = coordinator._entry
    if guard == "other_entry":
        entry = MockConfigEntry(domain=DOMAIN)
        entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "button", DOMAIN, f"{DOMAIN}_{coordinator.device_key}_diagnosis_start", config_entry=entry
    )
    if guard != "other_entry":
        resources = deepcopy(coordinator.last_resources)
        if guard == "other_model":
            resources["/information/vs/0"][PREFIX + "modelNum"] = "LCD_OV_WALL_20K"
        else:
            del resources["/diagnosis/vs/0"]
        coordinator._run_discovery(resources, from_snapshot=True)
        coordinator._rehydrate_resources = resources
    _drop_unverified_oven_diagnosis_buttons(hass, coordinator._entry, coordinator)
    assert registry.async_get(old.entity_id) is not None


async def test_offline_snapshot_keeps_status_and_cleans_the_withdrawn_button(hass):
    online = await _discovered(hass)
    await online._async_save_snapshot(online.last_resources, online.subdevices)
    restored = LocalThingsCoordinator(hass, online._entry)
    assert await restored.async_rehydrate()
    assert restored.last_resources == {}
    assert not any(_is_included(b, restored) for b in _buttons(restored))
    assert any(
        b.desc.key == "diagnosis_status" and _is_included(b, restored) for b in restored.bound
    )
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "button",
        DOMAIN,
        f"{DOMAIN}_{restored.device_key}_diagnosis_start",
        config_entry=online._entry,
    )
    _drop_unverified_oven_diagnosis_buttons(hass, online._entry, restored)
    assert registry.async_get(old.entity_id) is None


@pytest.mark.parametrize("name", ["microwave_nw9300md", "dishwasher"])
async def test_shared_appliances_keep_their_diagnosis_buttons(hass, name):
    from tests.test_subdevice_discovery import _coordinator, _discover

    coordinator = _coordinator(hass)
    await _discover(coordinator, name)
    buttons = [b for b in _buttons(coordinator) if _is_included(b, coordinator)]
    assert buttons
    registry = er.async_get(hass)
    entries = [
        registry.async_get_or_create(
            "button",
            DOMAIN,
            f"{DOMAIN}_{coordinator.device_key}_{_key(b)}",
            config_entry=coordinator._entry,
        )
        for b in buttons
    ]
    _drop_unverified_oven_diagnosis_buttons(hass, coordinator._entry, coordinator)
    assert all(registry.async_get(e.entity_id) for e in entries)
    assert all(isinstance(b.desc, ButtonDesc) and b.desc.write_fn is not None for b in buttons)
    assert all(b.desc.exists_fn is None or b.capability is oven.OVEN_DIAGNOSIS for b in buttons)
