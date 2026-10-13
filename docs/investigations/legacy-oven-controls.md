# NV51K7770S control follow-up

The October 13, 2026 hardware checks confirmed numeric Cook time and the
lower shared-door display. After the combined update, the owner also
confirmed numeric Setpoint entry and removal of the obsolete Power control.
After the `27242d6` update instructions, the owner confirmed that normal
Start and Stop work for both upper and lower cavities without errors.
The owner subsequently confirmed that removing the divider exposes the
whole-oven modes on Upper and no modes on Lower, and that Smart Control
works with the divider removed.

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
The previously recorded installed revision is therefore unverified. After
the combined update was supplied, the owner confirmed that Setpoint displays
as numeric entry and the Power control is gone. Normal Start and Stop were
subsequently confirmed on both cavities. The exact installed commit was not
independently captured.

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
Each cavity has its own device, so Cooking mode labels omit redundant
Upper/Lower qualifiers. Recipe labels include the category, for example
"Healthy Cook Baked Potato"; Samsung's cavity-specific command codes remain
unchanged.
The owner confirmed that the revised labels display as intended after the
`d819528` update.
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

The owner then reported repeated "Choose a cooking mode first" errors when
entering Cook time before selecting a mode. The errors listed raw Samsung
mode codes. Idle Cook time can now be held before a mode is chosen, if an
available mode accepts it; the first mode selection revalidates and retains
that duration. Later mode changes still restore defaults. Start still
requires a valid mode and Smart Control. Validation errors resolve mode
names through the same catalog as Cooking mode, in Home Assistant's configured
language. Tests reproduce the original failures. The owner then confirmed
that time-first entry causes no errors and five minutes remains after
selecting Bake and waiting about a minute on the lower cavity. A remaining
validation error's translated text has not yet been captured on the live UI.

The owner requested an empty Cook time box instead of an idle zero, which
can turn an intended 5 into 50 while typing. For the measured board, the
number entity now presents an unset idle zero as an empty value. Explicitly
entered zero and running values stay visible. This changes only the entity
display; raw timer data, sensor values and command payloads are unchanged.
Tests cover both divided cavities and the whole oven. Live confirmation of
the empty box remains pending.

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

Normal Start and Stop are confirmed on both divided cavities, and the owner
reports Smart Control working with the divider removed. Further checks
cover the empty idle Cook time box, native Cook time unit setting, countdown
start and timer completion, Smart Control off/door-reset behavior through
the normal controls, untimed starts and running adjustments.
The basic Start/Stop confirmation does not establish every recipe or
simultaneous-cavity setting combination.

[manual]: https://images.thdstatic.com/catalog/pdfImages/99/9900cc56-8433-4e1b-ba18-4271b575791d.pdf
