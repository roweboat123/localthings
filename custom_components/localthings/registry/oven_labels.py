"""Model-specific English labels without changing shared appliance translations."""

from dataclasses import replace
from functools import partial

from .capability import Capability

TITLE_CASE_KEYS = frozenset(
    {
        "ai_energy_level",
        "alarm_code",
        "child_lock",
        "cloud_connected",
        "cook_time",
        "cooktop_on_alert",
        "diagnosis_start",
        "diagnosis_status",
        "energy_last_month_kwh",
        "energy_saved_kwh",
        "energy_saving",
        "energy_this_month_kwh",
        "fast_preheat",
        "finish_time",
        "firmware_update",
        "food_probe_setpoint",
        "food_probe_temp",
        "machine_state",
        "natural_steam",
        "operation_time_minutes",
        "oven_mode",
        "oven_state",
        "power_energy_kwh",
        "progress_percentage",
        "selfcheck_error",
        "selfcheck_result",
        "selfcheck_start",
        "selfcheck_status",
        "start_cooking",
        "sync_clock",
        "usage_runtime_hours",
    }
)


def oven_label_key(key: str, resources: dict) -> str:
    model = (resources.get("/information/vs/0") or {}).get("x.com.samsung.da.modelNum")
    if isinstance(model, str) and model.split("|", 1)[0] == "LCD_OV_WALL_16K":
        return f"oven_title_{key}"
    return key


def with_english_labels(capability: Capability) -> Capability:
    """Use separate catalogs only for the verified oven's affected labels."""
    return replace(
        capability,
        entities=tuple(
            replace(desc, translation_key=partial(oven_label_key, key))
            if isinstance(key := desc.translation_key or desc.key, str) and key in TITLE_CASE_KEYS
            else desc
            for desc in capability.entities
        ),
    )
