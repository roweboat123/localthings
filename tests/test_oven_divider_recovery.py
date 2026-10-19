"""Legacy oven controls survive divider changes and earlier misidentification."""

from dataclasses import replace

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.localthings import _drop_misidentified_oven_controls
from custom_components.localthings.button import async_setup_entry as setup_buttons
from custom_components.localthings.const import DOMAIN
from custom_components.localthings.registry.adapter import flatten
from custom_components.localthings.registry.by_type import for_device_by_model
from custom_components.localthings.registry.capabilities import cook
from custom_components.localthings.registry.capabilities.operational import OPERATIONAL_STATE
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


@pytest.mark.parametrize("initially_divided", [False, True])
async def test_lower_start_survives_divider_changes_without_reload(
    hass, enable_custom_integrations, initially_divided
):
    coordinator = await _discovered(hass, _routes(divided=initially_divided))
    lower = _lower(coordinator)
    entry = coordinator._entry
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    buttons = []
    await setup_buttons(
        hass, entry, lambda new_entities, update_before_add=False: buttons.extend(new_entities)
    )
    start = next(
        (
            b
            for b in buttons
            if b._bound.subdevice == lower and b._bound.desc.key == "start_cooking"
        ),
        None,
    )
    assert start is not None
    unique_id = start.unique_id
    assert not {"start", "pause", "delay_start_hours"} & {
        b.desc.key for b in coordinator.bound if b.subdevice == lower
    }

    for divided in (False, True, False, True):
        _FakeConnection.routes = _routes(divided=divided)
        for index in (0, 1):
            resources = _seed(coordinator._session, index)
            for href, rep in resources.items():
                coordinator._observe.apply(href, rep, source="poll")
        coordinator.async_set_updated_data(
            flatten(coordinator.bound, coordinator.entity_resources())
        )
        assert start.unique_id == unique_id
        assert start.available is divided
        _FakeConnection.log.clear()
        if not divided:
            with pytest.raises(ServiceValidationError):
                await coordinator.async_start_cooking(
                    lower, mode="LowerBake", temperature=350, duration=300
                )
            assert not any(method == "PUT" for method, *_ in _FakeConnection.log)

    bound = {b.desc.key: b for b in coordinator.bound if b.subdevice == lower}
    for key, value in (
        ("oven_mode", "LowerBake"),
        ("oven_setpoint", 350),
        ("cook_time", 5),
    ):
        await coordinator.async_send_command(bound[key], value)
    await start.async_press()
    writes = [(path, body) for method, path, body, _ in _FakeConnection.log if method == "PUT"]
    assert writes == [
        (
            "/devices/1",
            {
                "Device": {
                    "Mode": {"modes": ["LowerBake"]},
                    "Temperatures": [{"id": "0", "desired": 350, "unit": "Fahrenheit"}],
                    "Operation": {"operationTime": "00:05:00", "state": "Run"},
                }
            },
        ),
    ]
    coordinator.last_update_success = False
    assert not start.available

    _FakeConnection.routes = _routes(divided=False)
    for index in (0, 1):
        for href, rep in _seed(coordinator._session, index).items():
            coordinator._observe.apply(href, rep, source="poll")
    coordinator.async_set_updated_data(flatten(coordinator.bound, coordinator.entity_resources()))
    assert not start.available
    _FakeConnection.log.clear()
    await coordinator.async_start_cooking(MAIN, mode="Bake", temperature=350, duration=300)
    writes = [(path, body) for method, path, body, _ in _FakeConnection.log if method == "PUT"]
    assert len(writes) == 1
    assert writes[0][0] == "/devices/0"
    assert writes[0][1] is not None
    assert writes[0][1]["Device"]["Mode"] == {"modes": ["Bake"]}


@pytest.mark.parametrize("divided", [False, True])
async def test_old_lower_laundry_rows_are_removed_without_losing_oven_entities(hass, divided):
    coordinator = await _discovered(hass, _routes(divided=divided))
    registry = er.async_get(hass)
    prefix = f"{DOMAIN}_{coordinator.device_key}_"
    obsolete = (("button", "start"), ("button", "pause"), ("number", "delay_start_hours"))
    removed, kept = [], []
    for platform, key in obsolete:
        old = registry.async_get_or_create(
            platform, DOMAIN, f"{prefix}subdevice1_{key}", config_entry=coordinator._entry
        )
        removed.append(
            registry.async_update_entity(old.entity_id, new_entity_id=f"{platform}.renamed_{key}")
        )
        kept.extend(
            registry.async_get_or_create(
                platform, DOMAIN, unique_id, config_entry=coordinator._entry
            )
            for unique_id in (f"{prefix}{key}", f"{prefix}subdevice2_{key}", f"unrelated_{key}")
        )
        kept.append(
            registry.async_get_or_create(
                "sensor", DOMAIN, f"{prefix}subdevice1_{key}", config_entry=coordinator._entry
            )
        )
    for platform, key in (
        ("button", "start_cooking"),
        ("button", "stop"),
        ("number", "cook_time"),
    ):
        kept.append(
            registry.async_get_or_create(
                platform, DOMAIN, f"{prefix}subdevice1_{key}", config_entry=coordinator._entry
            )
        )

    for _ in range(2):
        _drop_misidentified_oven_controls(hass, coordinator._entry, coordinator)
        assert all(registry.async_get(row.entity_id) is None for row in removed)
        assert all(registry.async_get(row.entity_id) == row for row in kept)


@pytest.mark.parametrize(
    "case", ["unknown_model", "other_model", "similar_model", "other_entry", "currently_supported"]
)
async def test_laundry_cleanup_requires_confirmed_obsolete_lower_oven_controls(hass, case):
    coordinator = await _discovered(hass)
    if case in ("unknown_model", "other_model", "similar_model"):
        coordinator._observe.apply(
            "/information/vs/1",
            {
                PREFIX + "modelNum": {
                    "unknown_model": "",
                    "other_model": "DA_WM_TP1",
                    "similar_model": "LCD_OV_WALL_17K",
                }[case]
            },
            source="poll",
        )
    elif case == "currently_supported":
        # A future capability reusing a key must not lose a live registry row.
        start = next(
            b
            for b in coordinator.bound
            if b.subdevice == _lower(coordinator) and b.desc.key == "start_cooking"
        )
        coordinator.bound.extend(
            replace(start, capability=OPERATIONAL_STATE, desc=desc)
            for desc in OPERATIONAL_STATE.entities
            if desc.key in ("start", "pause", "delay_start_hours")
        )
    entry = coordinator._entry
    if case == "other_entry":
        entry = MockConfigEntry(domain=DOMAIN)
        entry.add_to_hass(hass)
    registry = er.async_get(hass)
    rows = [
        registry.async_get_or_create(
            PLATFORM_OF[type(desc)],
            DOMAIN,
            f"{DOMAIN}_{coordinator.device_key}_subdevice1_{desc.key}",
            config_entry=entry,
        )
        for desc in OPERATIONAL_STATE.entities
        if desc.key in ("start", "pause", "delay_start_hours")
    ]
    _drop_misidentified_oven_controls(hass, coordinator._entry, coordinator)
    assert all(registry.async_get(row.entity_id) == row for row in rows)


@pytest.mark.parametrize("spec", [[], [{"mode": "LowerBake", "control": "Setting"}], "malformed"])
async def test_wall_button_keeps_existing_mode_spec_rules(hass, spec):
    coordinator = await _discovered(hass, _routes(divided=False))
    resources = coordinator.canonical_resources(_lower(coordinator))
    resources = {**resources, cook.MODE_HREF: {**resources[cook.MODE_HREF], cook.MODE_SPEC: spec}}
    assert cook.can_start({}, resources) is (spec == [])


@pytest.mark.parametrize(
    "model",
    [None, 123, "LCD_OV_WALL", "LCD_OV_WALL_17K", "LCD_OV_WALL_16K_OTHER", "TP2X_KS_WALLOVEN"],
)
def test_no_start_button_is_added_to_other_boards_with_no_cooking_modes(model):
    resources = {
        "/information/vs/0": {PREFIX + "modelNum": model},
        cook.MODE_HREF: {PREFIX + "supportedModes": ["NoOperation"]},
    }
    assert not cook.can_start({}, resources)


@pytest.mark.parametrize("description", ["LCD_OV_WALL_16K", "LCD_OV_WALL_16K_DIV"])
@pytest.mark.parametrize("model", ["LCD_OV_WALL_16K|1|2", ""])
def test_oven_type_does_not_depend_on_available_cooking_modes(model, description):
    registry = for_device_by_model(model, description)
    assert registry is not None
    assert registry.name == "oven"


@pytest.mark.parametrize("model", ["DISCOVERY", "OVERTURE", "BOARD|OV|1"])
def test_ov_type_token_does_not_match_substrings_or_capability_data(model):
    assert for_device_by_model(model, "") is None
