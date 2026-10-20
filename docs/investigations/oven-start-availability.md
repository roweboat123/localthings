# NV51K7770S Start availability

The Lower cavity has no cooking modes while the divider is removed. Keeping
Start Cooking registered allows it to work again after reinsertion without
reloading Home Assistant; [divider recovery](oven-divider-recovery.md) provides
that behavior.

This additional change marks Start Cooking unavailable whenever its cavity
reports no remotely startable modes. On `LCD_OV_WALL_16K`, removing the divider
therefore makes Lower Start unavailable, and reinserting it restores the same
entity on the next update. Upper retains its own availability.

The condition checks live cooking modes, rather than the divider sensor itself.
A reachable oven with no startable modes also gets an unavailable Start button.
Smart Control permission is checked when pressed, and invalid requests are
still rejected by command validation. Other buttons and oven models keep their
existing availability behavior.

## Implementation and verification

`ButtonDesc.available_fn` supplies an optional condition that the button platform
checks after coordinator availability. Only the measured oven's Start Cooking
descriptor uses it.

`tests/test_oven_start_availability.py` covers both divider startup states,
repeated removal and reinsertion, stable unique IDs, separate cavity states,
offline behavior, unchanged Stop availability, other models and Smart Control
validation. The divider-recovery tests also cover command rejection while the
lower cavity is absent.

The owner verified divider removal, reinsertion and Lower Start recovery on
14 October 2026 in the combined implementation. Those observations remain in
the [original investigation](https://github.com/roweboat123/localthings/blob/b9c485da9606f2dab5c8b1a4f35a6325582e56f8/docs/investigations/legacy-oven-controls.md).
The separate extraction is covered by simulated transport tests.
