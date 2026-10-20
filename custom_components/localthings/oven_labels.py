"""Cavity labels for the measured NV51K7770S Flex Duo oven."""

CAVITY_KEYS = frozenset(
    {
        "start_cooking",
        "stop",
        "oven_mode",
        "oven_setpoint",
        "cook_time",
        "machine_state",
        "cycle_active",
        "progress_percentage",
        "operation_time_minutes",
        "finish_time",
        "oven_state",
        "current_temp_c",
    }
)


def main_cavity_divider(resources: dict[str, dict]) -> str | None:
    """This board's upper controls operate the full cavity when slot 1 is absent."""
    model = (resources.get("/information/vs/0") or {}).get("x.com.samsung.da.modelNum")
    if isinstance(model, str) and model.split("|", 1)[0] == "LCD_OV_WALL_16K":
        return "/connected/vs/1"
    return None
