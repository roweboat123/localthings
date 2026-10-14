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
validation error subsequently appeared as "Bake needs a temperature" on
the live UI, confirming its friendly mode name.

The owner requested an empty Cook time box instead of an idle zero, which
can turn an intended 5 into 50 while typing. For the measured board, the
number entity now presents an unset idle zero as an empty value. Explicitly
entered zero and running values stay visible. This changes only the entity
display; raw timer data, sensor values and command payloads are unchanged.
Tests cover both divided cavities and the whole oven. After the `c4ecc7b`
installation instructions, the owner confirmed that the Cook time box works
as intended. The owner did not specify separate per-cavity checks for this
presentation change.

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

## Low-temperature reporting

On October 13, both cavities showed Unknown while their live resources
reported Ready / NoOperation, current 175°F and desired 0. The owner said
the oven was still warm at that point, then returned after cooling and
confirmed that it was fully cold. The subsequent upper-cavity reads were:

| Condition | Operation / oven state | Current | Desired |
| --- | --- | --- | --- |
| Fully cooled, idle | Ready / Ready | 175°F | 0 |
| Requested immediate read after panel start of UpperConvectionBake | Run / Preheat | 175°F | 325°F |

The legacy decoder passes the current temperature through unchanged. The
existing sensor filter suppresses values at or below 175°F when desired is
unset, but lets the reported value through during a cook. That filter
predates these changes and accounts for the idle Unknown display.

The cold idle value is not an actual room-temperature measurement. Its
appearance during initial preheat also supports a 175°F reporting floor
in this interface. No independent thermometer reading or exact interval
from Start was supplied, so this does not establish the physical sensor's
lower limit or rule out other diagnostic data. Earlier cooking captures
returned varying values above 175°F. The lower cavity has not separately
been read after confirmed full cooling. No temperature behavior is changed.

## Repeated mode selection and Smart Control investigation

Later on October 13, the owner reported one HA start changing the physical
display from Smart Control to Bake and prompting for Smart Control without
the dial being touched. Both that attempt and a normal repeat heated. The
write-override option was off. Subsequent captures with remote control false
followed the owner manually moving the dial to Off; they do not establish
that HA disabled Smart Control. A fresh true baseline and the successful
21:16 LowerBake start (350°F, five minutes) were followed by Run / Preheat
with remote control still true. The owner confirmed normal panel behavior.
The original unexpected transition has not been reproduced or explained.

The owner clarified that pressing HA's Start cooking caused the oven to
enter Bake and physically heat while its display requested Smart Control
activation. The illuminated selection moved to Bake with the physical dial
untouched. This was not merely an indicator change. It happened once and
could not be reproduced in subsequent attempts. This remains a potential
safety issue; there is no contemporaneous authorization capture establishing
when the oven's internal flag changed.

Code review found that normal Start checked cached remote-control status
before acquiring the session lock, then sent settings and Run three seconds
apart without another authorization read. The generic command retry could
also replay the whole sequence after a lost response. Neither finding
establishes the cause of the reported event.

The updated legacy sequence reads the target cavity's own configuration
immediately before settings and again after the three-second wait, before
Run. Each read must explicitly report Smart Control enabled. Off, missing,
malformed or failed responses prevent the next write; cached state and the
write-override option cannot waive these checks. Both checks and writes
remain inside the caller's session lock and share the original timeout
budget. Cooking starts on all transports are no longer automatically
replayed after a transport exception; the error tells the user to check the
appliance before trying again. Stop and ordinary-command retry behavior are
unchanged. Debug logging identifies the authorization phase and each write's
HTTP response without adding new settings to the command.

Software tests cover the safeguards' rejection and timeout paths. On
October 14, after installing `7867769` and restarting, the owner performed
one supervised LowerBake start at 350 F for five minutes. The log records:

| Local time | Stage | Result |
|---|---|---|
| 09:05:23.290 | Fresh Smart Control check before settings | True |
| 09:05:23.408 | Settings response | HTTP 204 |
| 09:05:26.479 | Fresh Smart Control check before Run | True |
| 09:05:26.546 | Run response | HTTP 204 |
| 09:06:35.622 | Stop on the lower operational resource | 2.04 |

The owner confirmed normal heating with the dial remaining on Smart
Control, then normal Stop. The submitted raw reading was explicitly taken
after Stop: both states Ready, NoOperation, time and setpoint zero, and
remoteControlEnabled true. This verifies a successful lower-cavity start
with the added intervening read; it is not an active-cook raw capture or a
new confirmation for Upper or the whole oven. No start replay or refusal
appears in this sequence.

The owner also reports that either a remote or panel Stop requires Smart
Control to be reactivated from the oven display; the dial remaining on
Smart Control alone does not establish readiness for another remote start.
The exact relationship between that display activation and the post-stop
true flag was not captured. Do not infer that the flag alone establishes
the oven's complete authorization state or automatically reactivate it.

Three seconds remains a tested delay, not a measured minimum. A read and
write are not atomic at the appliance, and these checks cannot guarantee
its firmware honors permission or explain the original incident. Further
heating tests are not requested; the investigation now moves to read-only
discovery for the light and reservoir.

The later log and screenshot expose a separate settings bug:

- At 21:20:11, Start used LowerBake at 350°F with duration omitted. The
  settings write succeeded, but Run was refused with `4.00 Control fail,
  <Operation.state=Run>`. This does not establish why the oven refused it.
- At 21:20:32, five minutes was held; at 21:20:33, LowerBake was selected
  again. The old code cleared temperature and duration on every mode
  selection, including the same mode. Start then raised "Bake needs a
  temperature" twice, matching the screenshot despite its visible 350°F
  and five-minute fields.
- The entity overlay could also retain a previous cook's raw setpoint or
  duration when the pending recipe had neither a held value nor a default.
  Start did not use those raw values. This display mismatch is reproduced
  in tests; no simultaneous raw snapshot establishes which values supplied
  the screenshot's fields.

Reselecting the same held mode now revalidates and preserves its settings.
A different mode still restores its defaults. Once a mode is selected,
unset setpoint and time fields no longer fall back to unused raw values;
the measured board displays them as empty. Raw diagnostics and outgoing
start semantics are unchanged. Regression tests cover both cavities,
including a refused untimed attempt followed by a same-mode timed retry.
The update still needs an owner check on the appliance.

The logs also show accepted five-minute LowerConvectionBake (300°F) and
UpperSteamBake (350°F) start sequences. Those entries alone do not confirm
physical heating or panel behavior. The omitted-duration refusal remains
open; this patch does not substitute zero or relax the Smart Control gate.
Light and reservoir controls were deferred until the guarded start sequence
could be reviewed. Their read-only discovery follows the October 14 check.

## Light and reservoir discovery

On October 14 the owner operated the physical buttons while the oven was
idle and the dial was Off. The reservoir is inside the oven: opening the
main oven door is necessary to access it. Fresh `/device/0` reads at 11:41
and 11:42 local time confirmed the following upper-cavity option values,
with the main door remaining open throughout the open/close comparison:

| Option | Reservoir closed | Reservoir open |
|---|---|---|
| `waterTankInSwitch` | On | Off |
| `waterTankOutSwitch` | Off | On |
| `waterInlet` | Close | Close |

The two switches establish position feedback independently of the main
door. They do not identify a writable reservoir command. Motion and
missing or contradictory switch combinations have not been captured.

With the door and reservoir closed, fresh upper-cavity reads with the
interior light off and on were identical. A lower-cavity read also exposed
no lamp field. Diagnostics taken after those direct reads contained no lamp
option, wrapper or field in the retained raw resource bodies for either
cavity, and no unmapped resource wrappers. This establishes absence from
the captured status data, not that remote light control is impossible.
Neither light nor reservoir write commands have been identified or tested;
no new entities were added from these observations.

The initial diagnostic comparisons exposed a freshness limitation:
`LegacyHttpTransport.read()` does not update `last_bodies` for individual
resource reads, while `_read_seed()` replaces it after a full-device read.
Consequently, the mapped door state was Open while the transport snapshot
still said Close; the reservoir switches were also stale until a direct
read. Downloading diagnostics alone does not force a refresh. Future raw
comparisons should first read the intended `/device/<index>` and then
download diagnostics. The diagnostics also omit most aggregate-level
scalars through `_resource_bodies()`. No diagnostics behavior changed here.

## Entering settings in any order

The owner then captured "Choose a cooking mode first" while preparing
settings with No operation selected. The earlier fix allowed time-first
entry but still rejected a temperature before a mode. Pending temperature
and time can now both be entered before selecting the first mode, provided
one available mode accepts the combination. No mode is implicitly selected
on this board and preparation sends no appliance commands. The first mode
selection revalidates both values and retains them. Temperature rounding
waits for the selected mode's own step; unrelated recipe defaults are not
copied from a candidate mode. Start still requires a complete valid plan
and the existing remote-control gate.

Regression tests cover all six entry orders on Upper, Lower and the whole
oven, retention across unchanged polls, unchanged raw readings and zero
appliance writes during preparation. Further tests cover rejection of an
incompatible first mode without losing the pending values, mode-specific
rounding and incompatible pre-mode combinations.

A second screenshot shows a blank Setpoint and `number/set_value: expected
float at 'value'`. This is a separate native Home Assistant input problem.
The [number row][number-row] forwards its changed input string to the
service, while the [number service schema][number-schema] requires a float
before calling the integration. An empty-string submission therefore fails
before LocalThings receives it. The native field should not submit a blank
edit as a numeric setting. This integration patch does not change that
frontend behavior, replace the native controls or weaken the global schema;
the empty-field issue remains open. The exact on-device frontend version
has not been captured; the reviewed sources match the development Core
2026.9.4 environment and its frontend dependency.

## Remaining hardware checks

Normal Start and Stop are confirmed on both divided cavities, and the owner
reports Smart Control working with the divider removed. Further checks
cover the native Cook time unit setting, countdown start and timer
completion, Smart Control off/door-reset behavior through
the normal controls, the unexplained panel transition, the refused untimed
start, the repeated-mode fix and running adjustments.
The basic Start/Stop confirmation does not establish every recipe or
simultaneous-cavity setting combination.

[manual]: https://images.thdstatic.com/catalog/pdfImages/99/9900cc56-8433-4e1b-ba18-4271b575791d.pdf
[number-row]: https://github.com/home-assistant/frontend/blob/20260826.7/src/panels/lovelace/entity-rows/hui-number-entity-row.ts
[number-schema]: https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/components/number/__init__.py
