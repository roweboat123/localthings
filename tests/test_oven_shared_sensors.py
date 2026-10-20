"""Shared sensors on the measured NV51K7770S cavity pair."""

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from custom_components.localthings.binary_sensor import LocalThingsBinarySensor
from custom_components.localthings.const import DOMAIN
from custom_components.localthings.entity import _is_included
from custom_components.localthings.registry.adapter import flatten
from custom_components.localthings.registry.by_type import oven, resolve
from custom_components.localthings.registry.capabilities import oven as oven_caps
from custom_components.localthings.registry.subdevices import MAIN
from tests.test_legacy_http_lower_cavity import (
    LOWER,
    PREFIX,
    _discovered,
    _fake_https,  # noqa: F401 -- installs the fake legacy transport
    _FakeConnection,
    _lower,
    _requests,
    _routes,
)
from tests.test_subdevice_discovery import _coordinator


@pytest.mark.parametrize("divided", [False, True])
async def test_reservoir_is_shared_and_tracks_position_independently_of_door(
    hass: HomeAssistant, divided
):
    coordinator = await _discovered(hass, _routes(divided=divided))
    reservoirs = [
        b
        for b in coordinator.bound
        if b.desc.key == "reservoir_open" and _is_included(b, coordinator)
    ]
    assert {b.subdevice for b in reservoirs} == {MAIN, _lower(coordinator)}
    entities = [LocalThingsBinarySensor(coordinator, b) for b in reservoirs]
    assert len({e.unique_id for e in entities}) == 2
    assert all(e.device_class == "opening" for e in entities)
    assert flatten(coordinator.bound, coordinator.entity_resources())["reservoir_open"] is False

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "oven_lcd_ov_wall_16k_reservoir.json").read_text()
    )
    _FakeConnection.log.clear()
    for sample in fixture["samples"]:
        rep = {**coordinator.resource("/mode/vs/0"), PREFIX + "options": sample["options"]}
        coordinator._observe.apply("/mode/vs/0", rep, source="poll")
        coordinator._observe.apply(
            "/doors/vs/0",
            {PREFIX + "items": [{PREFIX + "id": "0", PREFIX + "openState": sample["door"]}]},
            source="poll",
        )
        coordinator.async_set_updated_data(
            flatten(coordinator.bound, coordinator.entity_resources())
        )
        assert all(e.is_on is (sample["position"] == "open") for e in entities)
        assert coordinator.data["door_open"] is True
        assert coordinator.data["subdevice1_reservoir_open"] is coordinator.data["reservoir_open"]
        assert PREFIX + "options" not in coordinator.resource("/mode/vs/1")
        assert (
            PREFIX + "options"
            not in coordinator.device_resources(_lower(coordinator))["/mode/vs/0"]
        )

    for options in (
        [],
        None,
        ["waterTankInSwitch_On"],
        ["waterTankInSwitch_On", "waterTankOutSwitch_On"],
    ):
        coordinator._observe.apply("/mode/vs/0", {PREFIX + "options": options}, source="poll")
        coordinator.async_set_updated_data(
            flatten(coordinator.bound, coordinator.entity_resources())
        )
        assert all(e.is_on is None for e in entities)
    assert not _requests()


@pytest.mark.parametrize("divided", [False, True])
async def test_divider_is_shared_without_changing_raw_resources(hass: HomeAssistant, divided):
    coordinator = await _discovered(hass, _routes(divided=divided))
    assert resolve(coordinator.device_resources(_lower(coordinator))) is oven.REGISTRY
    dividers = [
        b for b in coordinator.bound if b.desc.key == "divider" and _is_included(b, coordinator)
    ]
    assert {b.subdevice for b in dividers} == {MAIN, _lower(coordinator)}
    entities = [LocalThingsBinarySensor(coordinator, b) for b in dividers]
    assert len({e.unique_id for e in entities}) == 2
    raw_upper = dict(coordinator.resource("/information/vs/0"))
    _FakeConnection.log.clear()
    for value, expected in [("On", True), ("Off", False), ("Unknown", None), (None, None)]:
        coordinator._observe.apply("/connected/vs/1", {PREFIX + "connected": value}, source="poll")
        coordinator.async_set_updated_data(
            flatten(coordinator.bound, coordinator.entity_resources())
        )
        assert all(e.is_on is expected for e in entities)
        assert coordinator.resource("/information/vs/0") == raw_upper
        assert coordinator.device_resources(MAIN)["/information/vs/0"] == raw_upper
    assert not _requests()


@pytest.mark.parametrize("divided", [False, True])
async def test_shared_sensors_are_included_on_offline_reload(hass, divided):
    online = await _discovered(hass, _routes(divided=divided))
    snapshot = deepcopy(online.last_resources)
    offline = _coordinator(hass)
    offline._snapshot_store.async_load = AsyncMock(
        return_value={
            "resources": snapshot,
            "subdevice_candidates": [asdict(s) for s in online.subdevices],
        }
    )
    assert await offline.async_rehydrate()
    offline.last_update_success = False
    keys = {"divider", "reservoir_open", "door_open"}
    entities = [
        LocalThingsBinarySensor(offline, b)
        for b in offline.bound
        if b.desc.key in keys and _is_included(b, offline)
    ]
    online_ids = {
        LocalThingsBinarySensor(online, b).unique_id
        for b in online.bound
        if b.desc.key in keys and _is_included(b, online)
    }
    assert len(entities) == 6
    assert {e.unique_id for e in entities} == online_ids
    assert all(not e.available for e in entities)
    assert offline.discovery_resources == online.last_resources == snapshot
    assert offline.last_resources == {}


@pytest.mark.parametrize(
    "href,rep",
    [
        ("/information/vs/0", {PREFIX + "modelNum": "LCD_OV_WALL_20K|1|2"}),
        ("/information/vs/1", {PREFIX + "description": "OTHER"}),
        ("/information/vs/1", {PREFIX + "modelNum": "LCD_OV_WALL_20K|1|2"}),
        ("/information/vs/1", {PREFIX + "modelNum": None}),
    ],
)
async def test_shared_divider_and_reservoir_require_the_measured_pair(
    hass: HomeAssistant, href, rep
):
    coordinator = await _discovered(hass)
    coordinator._observe.apply(href, rep, source="poll")
    state = flatten(coordinator.bound, coordinator.entity_resources())
    assert "divider" not in state
    assert "subdevice1_reservoir_open" not in state
    assert coordinator.entity_resources()["/doors/vs/1"] == {PREFIX + "items": []}


@pytest.mark.parametrize(
    "options,expected",
    [
        (["waterTankInSwitch_Off", "waterTankOutSwitch_On"], True),
        (["waterTankInSwitch_Off"], None),
        (["waterTankInSwitch_On", "waterTankOutSwitch_On"], None),
    ],
)
async def test_a_lower_reservoir_reading_is_not_replaced(hass: HomeAssistant, options, expected):
    coordinator = await _discovered(hass)
    coordinator._observe.apply("/mode/vs/1", {PREFIX + "options": options}, source="poll")
    state = flatten(coordinator.bound, coordinator.entity_resources())
    assert state["reservoir_open"] is False
    assert state.get("subdevice1_reservoir_open") is expected
    assert coordinator.entity_resources()["/mode/vs/1"] == coordinator.resource("/mode/vs/1")


@pytest.mark.parametrize("divided", [False, True])
async def test_lower_door_tracks_shared_door_without_changing_raw_resources(
    hass: HomeAssistant, divided
):
    coordinator = await _discovered(hass, _routes(divided=divided))
    lower = _lower(coordinator)
    for connected in ("Off", "On", "Off"):
        coordinator._observe.apply(
            "/connected/vs/1", {PREFIX + "connected": connected}, source="poll"
        )
        for open_state, expected in [("Close", False), ("Open", True), ("Close", False)]:
            rep = {PREFIX + "items": [{PREFIX + "id": "0", PREFIX + "openState": open_state}]}
            coordinator._observe.apply("/doors/vs/0", rep, source="poll")
            state = flatten(coordinator.bound, coordinator.entity_resources())
            assert state["door_open"] is expected
            assert state["subdevice1_door_open"] is expected
            assert coordinator.canonical_resources(lower)["/doors/vs/0"] == rep
            assert coordinator.device_resources(lower)["/doors/vs/0"] == {PREFIX + "items": []}
            assert coordinator.resource("/doors/vs/1") == {PREFIX + "items": []}

    coordinator._observe.apply("/doors/vs/0", {PREFIX + "items": []}, source="poll")
    state = flatten(coordinator.bound, coordinator.entity_resources())
    assert state["subdevice1_door_open"] is None


@pytest.mark.parametrize(
    "href,rep",
    [
        ("/information/vs/0", {PREFIX + "modelNum": "LCD_OV_WALL_OTHER|1|2"}),
        ("/information/vs/1", {PREFIX + "description": "LCD_OV_WALL_16K"}),
        ("/doors/vs/0", {PREFIX + "items": [{PREFIX + "id": "0"}]}),
        (
            "/doors/vs/0",
            {PREFIX + "items": [{PREFIX + "id": "0", PREFIX + "openState": "Unknown"}]},
        ),
    ],
)
async def test_shared_door_requires_the_measured_model_and_a_known_state(
    hass: HomeAssistant, href, rep
):
    coordinator = await _discovered(hass)
    coordinator._observe.apply(href, rep, source="poll")
    assert coordinator.entity_resources()["/doors/vs/1"] == {PREFIX + "items": []}


@pytest.mark.parametrize("divided", [False, True])
async def test_shared_door_preserves_a_lower_cavitys_own_reading(hass: HomeAssistant, divided):
    coordinator = await _discovered(hass, _routes(divided=divided))
    own_door = {PREFIX + "items": [{PREFIX + "id": "0", PREFIX + "openState": "Open"}]}
    coordinator._observe.apply("/doors/vs/1", own_door, source="poll")
    state = flatten(coordinator.bound, coordinator.entity_resources())
    assert state["door_open"] is False
    assert state["subdevice1_door_open"] is True
    assert coordinator.entity_resources()["/doors/vs/1"] == own_door


async def test_entity_view_does_not_change_raw_reads_or_upper_connectivity(hass):
    coordinator = await _discovered(hass, _routes(divided=False))
    coordinator._observe.apply("/connected/vs/0", {PREFIX + "connected": "On"}, source="poll")
    before = deepcopy(coordinator.last_resources)
    view = coordinator.entity_resources()
    assert view["/information/vs/0"]["_localthings_divider"] is False
    assert view["/information/vs/1"]["_localthings_reservoir"] is False
    assert coordinator.last_resources == before
    for cavity in (MAIN, _lower(coordinator)):
        raw = coordinator.device_resources(cavity)
        assert all(not k.startswith("_localthings_") for rep in raw.values() for k in rep)
        for href in ("/mode/vs/0", "/connected/vs/0", "/information/vs/0"):
            actual = cavity.to_actual(href)
            assert coordinator.entity_rep(actual) == before.get(actual, {})
    assert view["/connected/vs/0"] == before["/connected/vs/0"]


async def test_native_lower_reservoir_has_one_entity_at_setup(hass):
    lower = deepcopy(LOWER)
    lower["Mode"]["options"] = ["waterTankInSwitch_Off", "waterTankOutSwitch_On"]
    coordinator = await _discovered(hass, _routes(lower=lower))
    bound = [
        b
        for b in coordinator.bound
        if b.subdevice == _lower(coordinator)
        and b.desc.key == "reservoir_open"
        and _is_included(b, coordinator)
    ]
    assert len(bound) == 1
    assert bound[0].href == "/mode/vs/1"
    state = flatten(coordinator.bound, coordinator.entity_resources())
    assert state["subdevice1_reservoir_open"] is True
    assert state["reservoir_open"] is False


@pytest.mark.parametrize("options", ["invalid", 1, {"waterTankInSwitch_On": True}])
async def test_malformed_lower_options_are_not_replaced_by_upper_readings(hass, options):
    coordinator = await _discovered(hass)
    resources = deepcopy(coordinator.last_resources)
    resources["/mode/vs/1"][PREFIX + "options"] = options
    before = deepcopy(resources)
    view = oven_caps.shared_sensor_view(resources)
    assert "_localthings_reservoir" not in view["/information/vs/1"]
    assert view["/mode/vs/1"] == before["/mode/vs/1"]
    assert resources == before


@pytest.mark.parametrize("model", [None, "LCD_OV_WALL", "LCD_OV_WALL_16K_OTHER", "LCD_OV_WALL_20K"])
def test_other_boards_keep_their_existing_sensors_and_divider_labels(model):
    info = {PREFIX + "modelNum": model, PREFIX + "description": "OTHER_DIV"}
    resources = {"/information/vs/0": info}
    assert oven_caps.shared_sensor_view(resources) is resources
    dividers = [
        e
        for e in oven_caps.OVEN_CONNECTED.entities
        if e.key == "divider" and e.exists_fn is not None and e.exists_fn({}, resources)
    ]
    assert len(dividers) == 1
    assert dividers[0].translation_key is None


@pytest.mark.parametrize(
    "language,name,inserted,removed,reservoir",
    [
        ("cs", "Přepážka", "Vložená", "Vyjmutá", "Nádržka"),
        ("de", "Trennwand", "Eingesetzt", "Entfernt", "Wassertank"),
        ("en", "Divider", "Inserted", "Removed", "Reservoir"),
        ("es", "Divisor", "Insertado", "Retirado", "Depósito de agua"),
        ("fr", "Séparateur", "Inséré", "Retiré", "Réservoir"),
        ("it", "Divisorio", "Inserito", "Rimosso", "Serbatoio"),
        ("ko", "칸막이", "삽입됨", "제거됨", "물통"),
        ("nl", "Scheidingswand", "Geplaatst", "Verwijderd", "Waterreservoir"),
        ("pl", "Przegroda", "Włożona", "Wyjęta", "Zbiornik wody"),
        ("sk", "Priečka", "Vložená", "Vybratá", "Nádržka"),
    ],
)
async def test_shared_sensor_translations_load_in_every_language(
    hass, enable_custom_integrations, language, name, inserted, removed, reservoir
):
    coordinator = await _discovered(hass)
    entities = [
        LocalThingsBinarySensor(coordinator, b)
        for b in coordinator.bound
        if b.desc.key in {"divider", "reservoir_open"} and _is_included(b, coordinator)
    ]
    assert len(entities) == len({e.unique_id for e in entities}) == 4
    for entity in entities:
        expected_key = (
            "divider_lcd_wall_16k" if entity._bound.desc.key == "divider" else "reservoir_open"
        )
        assert entity.translation_key == expected_key
    strings = await async_get_translations(hass, language, "entity", {DOMAIN})
    prefix = f"component.{DOMAIN}.entity.binary_sensor."
    assert strings[prefix + "divider_lcd_wall_16k.name"] == name
    assert strings[prefix + "divider_lcd_wall_16k.state.on"] == inserted
    assert strings[prefix + "divider_lcd_wall_16k.state.off"] == removed
    assert strings[prefix + "reservoir_open.name"] == reservoir
