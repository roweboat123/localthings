# NV51K7770S reservoir and shared sensors

The two cavity devices represent one oven with a shared door, divider and water
reservoir. This change adds a Reservoir sensor to both devices, shows Divider
on Upper, and fills Lower's empty Door reading from Upper. Each device page
then shows these physical states without needing to consult the other cavity.

This feature follows [divider recovery](oven-divider-recovery.md), which fixes
Lower discovery when Home Assistant starts with the divider removed.

## Reported resources

Sharing requires both records to report board `LCD_OV_WALL_16K`, with Lower's
description exactly `LCD_OV_WALL_16K_DIV`.

| Sensor | Reported by | Display behavior |
| --- | --- | --- |
| Door | Upper `/doors/vs/0`, item `0` | Fill Lower's empty door list from the single Upper reading. A genuine Lower reading takes precedence. |
| Divider | Lower `/connected/vs/1` | Show on both devices: `On` = Inserted, `Off` = Removed. Upper's connectivity flag keeps its own value. |
| Reservoir | Upper `/mode/vs/0`, tank-switch options | Show on both devices. Any Lower tank-switch token prevents fallback to Upper. |

The reservoir measures position, not water level. The owner opened and closed
it while the oven door stayed open, confirming these independent readings:

| `waterTankInSwitch` | `waterTankOutSwitch` | Reservoir |
| --- | --- | --- |
| `On` | `Off` | Closed |
| `Off` | `On` | Open |

Missing, contradictory or unrecognized pairs report Unknown.

The reservoir entity and its position mapping are limited to this board.
Divider state labels use a model-specific translation key in all ten catalogs;
the existing Lower entity retains its unique ID and underlying on/off states.

## Implementation

`registry/capabilities/oven.py` contains the mappings and `shared_sensor_view()`.
The coordinator applies that function when building live entity values and
when registering entities from an offline snapshot.

The view copies only the affected representations. Shared scalar values are
attached to the information records under private display fields, keeping them
separate from mode options and connectivity. Device reads, diagnostics and
stored snapshots retain the reported data. In particular, copying Upper's full
options array into Lower would risk exposing or writing controls on the wrong
cavity.

`registry/by_type/oven.py` binds the added display sensors. Existing Door and
Lower Divider identities remain stable; the new copies receive their own IDs.
The normal door, mode and connectivity polls supply updates.

## Evidence and verification

The owner confirmed both device pages followed Door, Divider and Reservoir
changes on 14 October 2026, including startup and door use with the divider
removed. The observations remain in the
[original investigation](https://github.com/roweboat123/localthings/blob/b9c485da9606f2dab5c8b1a4f35a6325582e56f8/docs/investigations/legacy-oven-controls.md).

`tests/fixtures/oven_lcd_ov_wall_16k_reservoir.json` preserves the two measured
reservoir positions. `tests/test_oven_shared_sensors.py` covers both divider
startup states, changing readings, conflicting or missing values, native Lower
readings, model boundaries, raw-data preservation, offline registration and
all ten translations. The divider-recovery tests also check command routing
with this shared view enabled.
