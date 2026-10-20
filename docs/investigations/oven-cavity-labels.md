# NV51K7770S divider-aware cavity labels

The upper controls also operate the full oven when its divider is removed.
Their labels should show which space they currently control, without requiring
the owner to rename entities after moving the divider.

For the exact `LCD_OV_WALL_16K` board, the upper device's cooking controls and
cavity sensors use these labels:

| Divider report at `/connected/vs/1` | English label |
| --- | --- |
| `On` | Upper |
| `Off` | Oven |
| Missing or unrecognized | Upper |

For example, **Upper Setpoint** becomes **Oven Setpoint** when the divider is
removed. The two Home Assistant devices stay separate. Lower-device labels,
device names and shared controls and diagnostics are unchanged.

## Implementation

`oven_labels.py` identifies this exact board and lists the cavity-specific entity
keys. `entity.py` applies its name placeholders only to those entities on the
main device, under the oven registry. Matching another `LCD_OV_WALL` board, a
range, or a microwave does not activate the labels.

The existing coordinator update refreshes the translated name when the divider
changes. Home Assistant updates the entity's original name; custom names still
take precedence. Unique IDs, existing entity IDs, device assignments and command
routes do not change. No integration reload or appliance command is needed.

An offline startup uses the saved divider report for its label while the entity
remains unavailable. A missing or unrecognized live report uses Upper, so loss
of a reading does not imply the divider has been removed.

All ten language catalogs include the new cavity labels. The new entity entries
reuse each language's existing names and state mappings, preserving other
appliances' labels. Tests check formatting and runtime name updates in every
language; this is not a native-speaker review.

## Evidence and verification

The legacy fixture `oven_lcd_ov_wall_16k_divided_8888.json` records the divider in
and out and the two cavity endpoints. The owner's earlier tests confirmed that
the upper path controls the full oven without the divider; see the
[preserved oven investigation](https://github.com/roweboat123/localthings/blob/b9c485da9606f2dab5c8b1a4f35a6325582e56f8/docs/investigations/legacy-oven-controls.md).

Regression coverage checks upgrades from the original labels, both initial
divider states, subsequent changes, unknown reports, offline restoration and
reconnection. It verifies custom entity and device names, a renamed entity ID,
both device identities, unchanged lower labels and the other appliance fixtures.

This branch is independent of the other prepared features. During the combined
review, add the split hour/minute keys from item 2 and the model-specific Healthy
Cook translation from item 4 to the cavity labels. Item 8 separately fixes lower
control discovery and availability; this naming change does not include that
behavior or the single-device merger.
