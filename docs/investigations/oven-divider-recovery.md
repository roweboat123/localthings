# NV51K7770S divider recovery

Starting Home Assistant with the divider removed could leave the Lower oven
without Start Cooking, even after reinserting the divider. It could also create
unusable Start, Pause and Delay Start controls.

## Cause and fix

The Lower cavity reports only `NoOperation` while the divider is removed. That
prevents the cooking-mode resource signature from identifying it as an oven.
Its description, `LCD_OV_WALL_16K_DIV`, then reaches the consumer-model fallback,
where `WALL` matches the washer prefix `WA`.

The existing board-token table now recognizes `OV` as an oven type. This keeps
discovery independent of the modes currently available. Token matching already
ignores substrings and the revision/capability data after `|`.

For `LCD_OV_WALL_16K`, Start Cooking stays registered when the divider is absent.
Its availability follows the cavity's live startable modes, so reinsertion
restores it on the next update. The entity keeps its unique ID. Declared
`modeSpec` restrictions and command validation still apply.

During setup, cleanup removes the old Lower `button.start`, `button.pause` and
`number.delay_start_hours` entries. It requires the verified board, the indexed
Lower cavity, and an included Start Cooking replacement. It matches unique IDs
and the owning config entry, and retains any control still supported by current
discovery. Renamed obsolete entries are handled by the same lookup.

## Hardware evidence

On 14 October 2026, the owner confirmed startup with the divider removed,
reinsertion without reloading, recovery of Lower Start Cooking, and removal of
the three phantom controls. Upper Convection Bake and Lower Bake subsequently
ran together and stopped independently.

The original observations are preserved in the
[investigation record](https://github.com/roweboat123/localthings/blob/b9c485da9606f2dab5c8b1a4f35a6325582e56f8/docs/investigations/legacy-oven-controls.md).
The existing fixture `tests/fixtures/oven_lcd_ov_wall_16k_divided_8888.json`
supplies the two cavity records used by the regression tests.

## Code and verification

- `registry/by_type/__init__.py`: the `OV` type-table entry.
- `registry/capabilities/cook.py`: exact-board detection and Start Cooking
  inclusion while the cavity temporarily offers no cooking modes.
- `registry/capabilities/oven.py`: availability based on live cavity modes.
- `registry/entities.py` and `button.py`: an optional button availability
  predicate, evaluated against that button's own cavity resources.
- `__init__.py`: removal of obsolete Lower controls during entry setup.
- `tests/test_oven_divider_recovery.py`: both startup states, repeated divider
  changes, stable identity, no start while removed, correct Lower and Oven
  command routing, and cleanup boundaries.

Use `exists_fn` for whether a button belongs to a device, and `available_fn` for
a temporary condition that blocks its use. Removing the entity at setup cannot
handle a condition that changes later. Availability is a UI indication;
command validation must also reject actions that cannot currently run.
