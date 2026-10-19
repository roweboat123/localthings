# NV51K7770S shared sensors

Upper and Lower represent one physical oven, but each device page omits some
of its shared sensors. This change shows Divider on Upper, Reservoir on Lower,
and the shared Door reading on both devices.

It follows the separate [Reservoir sensor](oven-reservoir.md) addition and
[divider recovery](oven-divider-recovery.md) fix. The latter is needed for
Lower discovery when Home Assistant starts with the divider removed.

## Shared readings

Sharing requires both records to report board `LCD_OV_WALL_16K`, with Lower's
description exactly `LCD_OV_WALL_16K_DIV`.

| Sensor | Reported by | Display behavior |
| --- | --- | --- |
| Door | Upper `/doors/vs/0`, item `0` | Fill Lower's empty door list from the single Upper reading. A genuine Lower reading takes precedence. |
| Divider | Lower `/connected/vs/1` | Show on both devices: `On` = Inserted, `Off` = Removed. Upper's connectivity flag keeps its own value. |
| Reservoir | Upper `/mode/vs/0`, tank-switch options | Share the existing position reading with Lower. Any native Lower tank-switch token prevents fallback. |

Divider labels use a model-specific translation key in all ten catalogs. The
existing Lower entity retains its unique ID and underlying on/off states.
Reservoir uses the existing sensor's mapping and translated name.

## Implementation

`registry/capabilities/oven.py` provides `shared_sensor_view()`. The coordinator
applies it when building live entity values and when registering entities from
an offline snapshot. `registry/by_type/oven.py` binds the added display copies.

The view copies only the affected representations. Shared scalar values are
attached to information records under private display fields, keeping them
separate from mode options and connectivity. Device reads, diagnostics and
stored snapshots retain the reported data. Copying Upper's full options array
into Lower would risk exposing or writing controls on the wrong cavity.

Existing Door and Lower Divider identities remain stable; the new copies
receive their own IDs. The normal door, mode and connectivity polls supply
updates.

## Evidence and verification

The owner confirmed both device pages followed Door, Divider and Reservoir
changes on 14 October 2026, including startup and door use with the divider
removed. The observations remain in the
[original investigation](https://github.com/roweboat123/localthings/blob/b9c485da9606f2dab5c8b1a4f35a6325582e56f8/docs/investigations/legacy-oven-controls.md).

`tests/test_oven_shared_sensors.py` covers both divider startup states,
changing readings, native Lower precedence, model boundaries, raw-data
preservation, offline registration and all ten translations. It reuses the
Reservoir feature's measured position fixture. The divider-recovery tests also
check command routing with this shared view enabled.
