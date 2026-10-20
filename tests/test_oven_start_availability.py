"""Optional Start availability follows this oven's live cavity modes."""

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.localthings.button import LocalThingsButton
from custom_components.localthings.button import async_setup_entry as setup_buttons
from custom_components.localthings.const import DOMAIN
from custom_components.localthings.registry.adapter import flatten
from custom_components.localthings.registry.capabilities.oven import START_COOKING_BUTTON
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
async def test_start_availability_follows_its_cavity_without_recreating_entities(
    hass, enable_custom_integrations, initially_divided
):
    coordinator = await _discovered(hass, _routes(divided=initially_divided))
    entry = coordinator._entry
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    buttons = []
    await setup_buttons(
        hass, entry, lambda new_entities, update_before_add=False: buttons.extend(new_entities)
    )
    starts = {b._bound.subdevice: b for b in buttons if b._bound.desc.key == "start_cooking"}
    lower = _lower(coordinator)
    identities = {cavity: b.unique_id for cavity, b in starts.items()}
    assert starts[lower].available is initially_divided
    assert starts[MAIN].available

    for divided in (False, True, False, True):
        _FakeConnection.routes = _routes(divided=divided)
        for index in (0, 1):
            for href, rep in _seed(coordinator._session, index).items():
                coordinator._observe.apply(href, rep, source="poll")
        coordinator.async_set_updated_data(
            flatten(coordinator.bound, coordinator.entity_resources())
        )
        assert starts[lower].available is divided
        assert starts[MAIN].available
        assert {cavity: b.unique_id for cavity, b in starts.items()} == identities

    coordinator.last_update_success = False
    assert all(not b.available for b in starts.values())


@pytest.mark.parametrize(
    "model",
    [None, 123, "LCD_OV_WALL", "LCD_OV_WALL_17K", "LCD_OV_WALL_16K_OTHER", "TP2X_KS_WALLOVEN"],
)
def test_other_models_keep_their_start_availability(model):
    gate = START_COOKING_BUTTON.available_fn
    assert gate is not None
    assert gate(
        {},
        {
            "/information/vs/0": {PREFIX + "modelNum": model},
            "/mode/vs/0": {PREFIX + "supportedModes": ["NoOperation"]},
        },
    )


@pytest.mark.parametrize("divided", [False, True])
async def test_stop_does_not_inherit_start_availability(hass, divided):
    coordinator = await _discovered(hass, _routes(divided=divided))
    lower = _lower(coordinator)
    bound = next(b for b in coordinator.bound if b.subdevice == lower and b.desc.key == "stop")
    stop = LocalThingsButton(coordinator, bound)
    assert stop.available
    coordinator.last_update_success = False
    assert not stop.available


async def test_available_start_still_requires_smart_control(hass):
    coordinator = await _discovered(hass)
    lower = _lower(coordinator)
    coordinator._observe.apply(
        "/remotectrl/vs/1", {PREFIX + "remoteControlEnabled": "false"}, source="poll"
    )
    bound = next(
        b for b in coordinator.bound if b.subdevice == lower and b.desc.key == "start_cooking"
    )
    start = LocalThingsButton(coordinator, bound)
    assert start.available
    _FakeConnection.log.clear()

    with pytest.raises(ServiceValidationError) as error:
        await start.async_press()

    assert error.value.translation_key == "remote_control_disabled"
    assert not any(method == "PUT" for method, *_ in _FakeConnection.log)
