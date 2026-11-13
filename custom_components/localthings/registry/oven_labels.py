"""Model-specific English labels without changing shared appliance translations."""

from .capabilities.oven import has_paired_cook_time

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
    if has_paired_cook_time(resources):
        return f"oven_title_{key}"
    return key
