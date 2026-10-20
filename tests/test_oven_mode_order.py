"""Cooking mode order follows labels without changing selections or writes."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from custom_components.localthings.catalog import translated_state_label
from custom_components.localthings.const import DOMAIN
from custom_components.localthings.registry.adapter import flatten
from custom_components.localthings.registry.capabilities import oven
from custom_components.localthings.registry.entities import SelectDesc
from custom_components.localthings.select import LocalThingsSelect, async_setup_entry
from tests.test_legacy_http_lower_cavity import (
    PREFIX,
    _discovered,
    _fake_https,  # noqa: F401 -- fake legacy transport
    _routes,
)
from tests.test_select_options import _make_select
from tests.test_subdevice_discovery import _coordinator, _discover
from tests.test_translations import _languages
from tests.test_translations import _load as _catalog


@pytest.mark.parametrize("language", _languages())
@pytest.mark.parametrize("divided", [False, True])
async def test_platform_sorts_live_labels_and_preserves_cavity_commands(
    hass, monkeypatch, enable_custom_integrations, language, divided
):
    hass.config.language = language
    coordinator = await _discovered(hass, _routes(divided=divided))
    hass.data[DOMAIN] = {coordinator._entry.entry_id: coordinator}
    entities = []

    def add_entities(new_entities, update_before_add=False):
        entities.extend(new_entities)

    await async_setup_entry(hass, coordinator._entry, add_entities)
    modes = [entity for entity in entities if entity._bound.desc.key == "oven_mode"]
    assert len(modes) == (2 if divided else 1)
    labels = _catalog(language)["entity"]["select"]["oven_mode"]["state"]
    send = AsyncMock()
    monkeypatch.setattr(coordinator, "async_send_command", send)

    for entity in modes:
        assert entity._bound.desc.sort_options
        identity = entity.unique_id
        for raw_modes in (
            ["SteamBake", "Broil", "ConvectionBake", "Bake", "FutureVendorMode"],
            ["KeepWarm", "Bake", "SteamBake"],
            ["NoOperation"],
        ):
            rep = {PREFIX + "supportedModes": raw_modes, PREFIX + "modes": [raw_modes[0]]}
            coordinator._observe.apply(entity._bound.href, rep, source="poll")
            coordinator.async_set_updated_data(
                flatten(coordinator.bound, coordinator.entity_resources())
            )
            before = list(entity._raw_options())
            current = entity.current_option
            options = entity.options
            displayed = [labels.get(value, value) for value in options]
            assert displayed == sorted(displayed, key=str.casefold)
            assert set(options) == {entity._display_option(raw) for raw in before}
            assert entity.current_option == current
            assert current in options
            assert entity.unique_id == identity
            assert entity._raw_options() == before
            send.assert_not_called()
            for raw in before:
                if raw == "NoOperation":
                    continue
                await entity.async_select_option(entity._display_option(raw))
                send.assert_awaited_once_with(entity._bound, raw)
                send.reset_mock()


async def test_french_label_order_differs_from_raw_codes(hass):
    coordinator = await _discovered(hass)
    bound = next(b for b in coordinator.bound if b.desc.key == "oven_mode")
    strings = {
        f"component.{DOMAIN}.entity.select.oven_mode.state.{state}": label
        for state, label in _catalog("fr")["entity"]["select"]["oven_mode"]["state"].items()
    }
    entity = LocalThingsSelect(coordinator, bound, strings)
    coordinator._observe.apply(
        bound.href,
        {PREFIX + "supportedModes": ["Broil", "Bake", "ConvectionBake"]},
        source="poll",
    )
    # Cuisson precedes Gril, although the raw slug broil precedes convection_bake.
    assert entity.options.index("convection_bake") < entity.options.index("broil")


@pytest.mark.parametrize("form", ["static", "field", "callable"])
def test_sorting_is_opt_in_and_never_mutates_options(form):
    raw = ["SteamBake", "NoOperation", "Broil", "Bake"]
    desc = {
        "static": SelectDesc(key="oven_mode", options=tuple(raw)),
        "field": SelectDesc(key="oven_mode", options_field="supported"),
        "callable": SelectDesc(key="oven_mode", options=lambda resources: raw),
    }[form]
    resources = {"/mode/vs/0": {"supported": raw}}
    unchanged = _make_select(desc, "/mode/vs/0", resources)
    ordered = _make_select(replace(desc, sort_options=True), "/mode/vs/0", resources)
    assert unchanged.options == ["steam_bake", "no_operation", "broil", "bake"]
    assert ordered.options == ["bake", "broil", "no_operation", "steam_bake"]
    assert raw == ["SteamBake", "NoOperation", "Broil", "Bake"]


def test_missing_translations_unknown_values_and_equal_labels():
    assert translated_state_label("select", "oven_mode", "no_operation", {}) == "No operation"
    assert translated_state_label("select", "oven_mode", "Future Vendor Mode", {}) == (
        "Future Vendor Mode"
    )
    entity = _make_select(
        SelectDesc(key="oven_mode", options=("Broil", "Bake"), sort_options=True), "/mode", {}
    )
    entity._state_translations = {
        f"component.{DOMAIN}.entity.select.oven_mode.state.broil": "Same",
        f"component.{DOMAIN}.entity.select.oven_mode.state.bake": "same",
    }
    assert entity.options == ["broil", "bake"]


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
async def test_other_appliances_keep_their_option_order(hass, fixture):
    coordinator = _coordinator(hass)
    await _discover(coordinator, fixture)
    selectors = [b for b in coordinator.bound if isinstance(b.desc, SelectDesc)]
    assert selectors
    for bound in selectors:
        assert isinstance(bound.desc, SelectDesc)
        assert not bound.desc.sort_options
        entity = LocalThingsSelect(coordinator, bound)
        assert entity.options == [entity._display_option(raw) for raw in entity._raw_options()]


@pytest.mark.parametrize(
    "model",
    [None, 16, "LCD_OV_WALL", "LCD_OV_WALL_16K_DIV", "LCD_OV_WALL_16K_OTHER", "LCD_OV_WALL_20K"],
)
def test_only_the_exact_board_opts_in(model):
    resources = {"/information/vs/0": {PREFIX + "modelNum": model}}
    assert oven.LCD_WALL_MODE.match_fn is not None
    assert oven.OVEN_MODE_FALLBACK.match_fn is not None
    assert not oven.LCD_WALL_MODE.match_fn({}, resources)
    assert oven.OVEN_MODE_FALLBACK.match_fn({}, resources)


async def test_static_fallback_mode_list_is_sorted(hass):
    coordinator = await _discovered(hass, _routes(divided=False))
    bound = next(b for b in coordinator.bound if b.desc.key == "oven_mode")
    entity = LocalThingsSelect(coordinator, bound)
    coordinator._observe.apply(bound.href, {PREFIX + "supportedModes": None}, source="poll")
    labels = _catalog("en")["entity"]["select"]["oven_mode"]["state"]
    displayed = [labels.get(value, value) for value in entity.options]
    assert set(entity._raw_options()) == set(oven._OVEN_MODES)
    assert displayed == sorted(displayed, key=str.casefold)
