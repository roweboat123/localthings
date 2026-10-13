# NV51K7770S control follow-up

The October 13, 2026 hardware check confirmed numeric Cook time and the
lower shared-door display. Setpoint still appeared as a slider, and the
obsolete Power switch remained unavailable in Controls. Normal Start/Stop
through the revised entities has not yet been verified.

## Power and Setpoint

Power is a read-only binary sensor. Setup removes the corresponding old
switch registry entry only when discovery includes that Power sensor, using
the exact unique ID and config entry. Other controls remain registered.

Both discovered Setpoint entities expose `mode: box` in the development
environment. The owner subsequently captured `mode: slider` from the live
lower entity. Reading the installed `oven.py` showed both Setpoint
descriptors missing the `mode="box"` line, although revision `6870fa9`
contains it. This establishes a source-installation mismatch; a screenshot
or browser refresh cannot establish that the corrected code was loaded.
Install the complete integration from an immutable tested revision and
check the installed files before restarting and inspecting live attributes.
The previously recorded installed revision is therefore unverified.

## Verified Healthy Cook mappings

On October 13 the owner started each recipe at the panel and captured its
mode and Fahrenheit setpoint through `read_resource`. Every capture reported
Run / Cooking, with Smart Control off. These establish readback mappings,
not successful remote starts of these recipes.

| Recipe | Upper mode | Lower mode | Preset |
| --- | --- | --- | --- |
| Baked potato | UpperHealthycook1 | LowerHealthycook1 | 375°F |
| Grilled chicken | UpperHealthycook2 | LowerHealthycook2 | 375°F |
| Salmon steak | UpperHealthycook3 | LowerHealthycook3 | 375°F |
| White fish fillet | UpperHealthycook4 | LowerHealthycook4 | 400°F |

The lower shim previously supplied only Bake, convection bake and convection
roast, then retained whichever recipe was running. Its apparently changing
supportedModes was not a complete raw firmware recipe list. The measured
LCD_OV_WALL_16K fallback now includes all four lower recipe codes. Removing
the divider still suppresses independent lower operation.

The recipe translations and defaults are scoped to the measured board.
Other boards keep numbered Healthy Cook labels. Whole-oven Healthycook1–6
and Gourmet Cook have not been mapped by these divided-cavity captures.
The existing LowerConvectionRoast fallback remains from the panel report
in #572; its physical availability still needs verification, since it is
absent from the manual's lower menu.

## Limits

Samsung's NV51K7770S user manual ([PDF][manual], pp.24, 29 and 34) gives:

- Cook time: 1 minute through 9 hours 59 minutes; zero cancels the timer.
- Divided Bake/convection and the four Healthy Cook recipes: 175–480°F
  (80–250°C). Steam starts at 230°F (110°C).
- Whole-oven Bake/convection: 175–550°F (80–285°C); whole-oven steam starts
  at 230°F (110°C).

These limits now apply to the measured board's fallback, idle selections
and running numeric controls. Device-reported modeSpecs take precedence.
Fahrenheit Healthy Cook defaults come from the captures; Celsius presets
are not guessed. Other boards retain their existing limits.

The paired-cavity restrictions on pp.27–28 are additional constraints and
are not inferred by interpolating the manual's sample rows. The appliance
may reject a combination while both cavities run. Broil's Hi/Lo codes,
whole-oven numbered recipe meanings and fixed-temperature programs still
need their own evidence before extending their controls.

## Cook time display

Cook time uses the standard Home Assistant numeric box and duration unit
setting. Minutes remain the default. The entity converts its value, bounds,
step and writes together when a user chooses hours in entity settings;
changing units does not send a command or change a held duration. The
coordinator continues to store whole minutes and the oven receives HH:MM:SS.
Tests cover 4, 10, 90 and 599 minutes and a 1.5-hour entry.

This avoids Home Assistant 2026.9's native duration-number conversion
rounding integer-minute states to whole hours while leaving the step at 1.
The standard frontend controls unit spacing, field width and typed character
count. This patch does not inject a frontend, add whitespace to a unit, or
claim an inline unit picker or a hard three-character typing limit. The
599-minute maximum bounds valid minute values to three integer digits;
hour fractions can need more characters to retain one-minute precision.

## Remaining hardware checks

After the combined installation, verify the Setpoint box, recipe names in
both mode lists, native Cook time unit setting, idle value persistence,
normal Start/Stop and Smart Control behavior. Check a short timed cook and
when its countdown begins. Divider-out, untimed starts and running changes
remain distinct tests; the panel captures and development checks do not
establish physical command acceptance.

[manual]: https://images.thdstatic.com/catalog/pdfImages/99/9900cc56-8433-4e1b-ba18-4271b575791d.pdf
