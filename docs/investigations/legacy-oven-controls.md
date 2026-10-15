# NV51K7770S control follow-up

These changes use LocalThings' existing entities and legacy HTTPS transport.
Hardware evidence is from one NV51K7770SG/AA with `LCD_OV_WALL_16K`, the
`LCD_OV_WALL_16K_DIV` lower record, software `20201110.0138` and firmware
`17071200,17041300`. Other NV51K7770S variants have not been independently tested.

## Cooking controls

The measured start sequence loads settings without `Operation.state`, waits
three seconds, then sends Run to the same cavity. The existing Start button
performs the sequence; users do not need separate setup and start actions.
See [the protocol measurements](oven-cycle-start.md#legacy-https-flex-duo-settings-then-run).

The current sequence requires a fresh, explicit Smart Control enabled reading
from the target cavity immediately before each write. Off, missing, malformed
or failed readings prevent the next write; cached permission and the generic
write-override option cannot waive these transport checks. The coordinator
lock covers the sequence and every request shares the original timeout budget.
A settings refusal prevents Run. Cooking starts on all transports are never
automatically replayed after a transport exception: the user is told to check
the appliance before retrying. Stop and ordinary-command retries are unchanged.

**The cause of one unexpected Smart Control transition remains unresolved.**
The owner reported actual heating after pressing HA Start while the oven display
requested Smart Control activation, with the physical dial untouched. There
is no simultaneous authorization capture and the event was not reproduced.
The fresh checks and no-replay behavior address weaknesses found in code review;
they are not evidence that the reported incident's cause has been fixed.

Before those safeguards, normal Start/Stop worked on both divided cavities,
and the owner confirmed mode visibility with the divider removed. The owner
later clarified that whole-oven cooking itself still needed confirmation at that stage.
After installing the safeguards, one supervised lower-cavity test on October 14
confirmed normal heating and Stop, with the dial remaining on Smart Control:

| Local time | Stage | Result |
| --- | --- | --- |
| 09:05:23.290 | Fresh permission before settings | True |
| 09:05:23.408 | Settings | HTTP 204 |
| 09:05:26.479 | Fresh permission before Run | True |
| 09:05:26.546 | Run | HTTP 204 |
| 09:06:35.622 | Stop | 2.04 |

The supplied raw reading was after Stop: Ready, NoOperation, zero setpoint and
times, and remote control true. It is not an active-cook reading.
The owner reports having to reactivate Smart Control on the display after Stop;
the relationship between that requirement and the reported true flag is unknown.
The integration does not reactivate Smart Control. A permission read and write
are not atomic at the appliance, and three seconds is a tested delay, not a
measured minimum. No additional heating tests are required for this write-up.

Later on October 14 the owner visually confirmed whole-oven Start and Stop
from HA, using Upper with the divider removed, Bake, 350 F and five minutes.
The accompanying diagnostic reports Bake, desired 350 F, both time fields
00:05:00, Smart Control true and lower divider Off. Both operation and cavity
states are Ready: this records the settings, not an active-cook sample or a
request/response trace. Whole-oven Start/Stop evidence is the owner's observation.

At 22:24 America/Chicago on October 14, the owner confirmed divided Upper
Convection Bake starting through Smart Control in d72b8da, with Lower Bake
started concurrently. Each cavity stopped using its own Stop button. This
confirms the revised Upper start sequence and independent stopping for that
simultaneous combination; it does not verify all paired modes or timer completion.

## Settings and presentation

Setpoint and cooking-duration controls use native numeric boxes. On the measured
board an unset idle timer is blank; explicit zero and running values remain visible.
Other oven families retain their total Cook time number and native duration-unit
conversion, including one-minute precision when displaying decimal hours. The
coordinator holds one duration and the appliance receives HH:MM:SS.

The LCD_OV_WALL legacy wall-oven family exposes **Cook Time Hours** and **Cook Time Minutes**
as two native number controls per cavity. They replace one component of the
same duration: 1 h plus 30 min means 90 minutes, not two independent timers.
Hours are limited to whole numbers from 0 to 9 and minutes from 0 to 59 in
both entity bounds and command validation. Live modeSpecs can further restrict
the combined duration. Each edit preserves the other
component, and idle edits remain held until Start. Invalid components and an
unreadable current duration are rejected without guessing a replacement.

The pair replaces the original **Cook Time** total-duration entity for that family.
Setup removes its old number registry entry only where both replacements exist,
including a renamed entry, and only within the owning config entry. Automations
using that old entity need the paired controls or the existing start_cooking
action's duration parameter. Other oven families keep their original control.

The pair uses fixed units, not HA duration-unit conversion. On the measured board,
both are blank for an unset idle timer and show zero once explicitly set. HA
determines their row layout; no custom frontend is added. Only the NV51K7770S has hardware evidence
so far. Tests cover sibling family identifiers without claiming additional
hardware captures. The owner confirmed both controls appear in Home Assistant
and later reported normal operation after installing the final build. Individual
timer boundaries and the complete entry-order matrix remain software-tested;
no separate hardware captures of those checks were supplied.

Pending temperature and time may be entered before choosing a mode if at least
one available mode accepts the combination. The first mode selection revalidates
and retains those values; selecting the same held mode again preserves them.
Changing mode restores its defaults. Preparation does not select a mode or send
commands on the measured board. The entity view clears previous-cook values
that Start would not use, while raw diagnostics remain unchanged. Validation
errors use the same translated mode labels as the Cooking mode selector.

The owner confirmed numeric Setpoint/Cook time, the blank idle timer, lower-cavity
time-first entry and persistence, revised recipe labels, and removal of the old
Power control. All six entry orders and repeated selection are covered in software
for Upper, Lower and whole-oven configurations; those complete combinations are
not separately hardware-confirmed. Clearing a numeric field can still cause HA's
native service schema to reject an empty string before LocalThings receives it.
This change does not add custom cards, frontend code or a typed-character limit.

## Modes and limits

Panel-started captures verified all eight divided Healthy Cook readback mappings:

| Recipe | Upper code | Lower code | Fahrenheit preset |
| --- | --- | --- | --- |
| Baked potato | UpperHealthycook1 | LowerHealthycook1 | 375 |
| Grilled chicken | UpperHealthycook2 | LowerHealthycook2 | 375 |
| Salmon steak | UpperHealthycook3 | LowerHealthycook3 | 375 |
| White fish fillet | UpperHealthycook4 | LowerHealthycook4 | 400 |

The measured board's lower fallback now includes those four recipes. Recipe
labels omit redundant cavity prefixes and are translated in all ten catalogs;
Samsung's command codes stay unchanged. Other models retain their numbered
Healthy Cook labels. Removing the divider correctly
exposes whole-oven modes on Upper and no cooking modes on Lower, as owner-confirmed.

At the owner's request, the same recipe order and Fahrenheit presets are also
used for whole-oven Healthycook1–4: Baked potato, Grilled chicken and Salmon steak
at 375 F, then White fish fillet at 400 F. These mappings are carried over from
the divided-cavity evidence; no separate whole-oven panel capture for these four
recipes has been supplied. Their limits use the manual's whole-oven range of
175–550 F (80–285 C), rather than the divided range. Tests verify the whole-oven
command codes, held presets and bounds without sending cavity-prefixed codes.

Cooking-mode selectors sort choices by translated label using HA's configured
language when the integration loads. This changes presentation only: raw device
order, command codes and current state are preserved. Other selectors keep their
existing order unless their descriptor explicitly requests sorting.

English labels use Title Case across the oven registry, including controls,
sensors, configuration, diagnostics and all known cooking-mode choices. Shared
catalog entries use the same labels wherever they are reused; the Start Cooking
action and its Cook Time field match the entities. Other languages retain their
normal capitalization. These are display-text changes only: translation keys,
entity identities and raw command values are unchanged.

On this board, the Cooking mode selector omits Drain, Autocook, SelfClean,
PyroFree, Descale, Broil and UpperBroil, and its mode write rejects those choices,
including when the live list is missing and static choices are used. The owner
requested excluding cleaning and Gourmet Cook controls from this submission.
The manual explicitly prohibits remote Self Clean; the other exclusions do
not establish a universal firmware prohibition. The raw advertised modes and
reported states remain available in diagnostics, and other models are unchanged.

During the divided-cavity test in d72b8da, selecting Broil exposed LocalThings'
existing remote-start refusal while the menu still offered that choice. The
specless start policy excludes the Broil family; this was an integration
validation error, not a captured firmware rejection. Broil and UpperBroil are
now hidden on this board to match that restriction. No remote Broil support or
Hi/Lo mapping is inferred, and the start policy is unchanged.

Whole-oven captures advertise Healthycook1 through Healthycook6. Two additional
panel-started recipes are verified:

| Recipe | Whole-oven code | Reported Fahrenheit target | Adjustment |
| --- | --- | --- | --- |
| Dehydrate | Healthycook5 | 150 | 100–225 F (40–105 C), manual p.34 |
| Bread Proof | Healthycook6 | 100 | Fixed; the panel shows no temperature control |

On October 14 the owner started Dehydrate from the panel with the divider
removed and confirmed its 150 F preset. The capture identifies Healthycook5,
desired 150 F, Operation Run and Oven Cooking. Both cook-duration fields are
00:00:00 and Smart Control is false. This verifies the whole-oven recipe code
and preset, not a remote start or the reported current-temperature accuracy.
The subsequent Bread Proof capture reports Healthycook6, desired 100 F,
Operation Run and Oven Cooking, with zero cook-duration fields, Smart Control
false and the divider out. The owner confirms that neither setup nor cooking
shows a temperature. Both captures report current 175 F; it is not evidence of
a measured 100 F cavity temperature.

The model-specific labels are translated in all ten catalogs. Dehydrate uses
its documented range and captured preset. Bread Proof's HA setpoint displays
100 F with both bounds fixed to 100; other requested targets are rejected.
Neither Celsius preset is guessed: Dehydrate requires a chosen temperature,
and Bread Proof's setpoint control is unavailable in Celsius without a live
modeSpec declaring usable bounds. The owner confirmed that the new mode mappings
appear correctly after installing build 81826e4. Remote starts for these two
recipes remain unverified.

The [NV51K7770S manual][manual], pp.24, 29 and 34, supplies a 599-minute maximum;
divided Bake/convection/Healthy Cook limits of 175–480 F (80–250 C); and whole-oven
Bake/convection/Healthy Cook 1–4 limits of 175–550 F (80–285 C).
Steam starts at 230 F (110 C).
These fallbacks are scoped to the measured board; live modeSpecs take precedence.
Celsius recipe presets are not guessed. The paired-cavity restrictions on pp.27–28
are not interpolated, and the appliance can refuse incompatible combinations.
LowerConvectionRoast remains the earlier #572 fallback, but its physical menu
availability is unverified. Broil Hi/Lo remains unverified and is excluded from
remote choices; the carried-over whole-oven Healthycook1–4 mappings still need
their own hardware evidence.
A recorded omitted-duration Run refusal was investigated again on October 15;
see the untimed-start investigation below.

## Untimed starts

On October 15 the owner reported that Lower Bake at 400 F failed at Run with
the cook time left blank, then confirmed that entering one minute allowed it
to start. The preceding diagnostic showed Smart Control true, divider On,
door Close, the probe disconnected and both cavities Ready. At 14:21
America/Chicago, the owner also confirmed that explicitly entering zero hours
and zero minutes fails. Both omitted and explicit-zero durations therefore
fail for this Lower Bake case; one minute succeeds.

Samsung's Oven plug-in v1.1040.8.0 converts blank hour/minute fields to zero,
formats them as `HH:MM:00`, and includes `Operation.operationTime` in the
settings request. This is visible in `OvenMainControlActivity.sendDataToOvenInReadyState`
and `DBOvenMainControlActivity.sendDataToOven`, through the operation builder
in `com.samsung.oven.shp.control.a`. The inspected APK's SHA-256 is
`6325172bcb173b43549cf07bcc71cdcace797c0c410c753c79cd2fa702135e52`.

The explicit-zero candidate was removed after the failed hardware check and
was never published. The app's serialization is not proof that this oven's
firmware accepts untimed starts through the same path. No alternative untimed
command is verified, and no arbitrary duration or timed-start-then-clear
sequence is substituted for the user's request.

### Experimental operation endpoint

The same APK's `com.samsung.oven.shp.control.a` has a helper that can dispatch
Run through `DeviceProviderJs.putDeviceOperationById`. `DeviceCommunicatorJs` builds
`/devices/{id}/operation`; `UtilForJson.obj2Json` enables root wrapping and
`OperationJs` declares the JSON root name `Operation`. The resulting request is
`PUT /devices/{id}/operation` with `{"Operation":{"state":"Run"}}`.
LocalThings' verified timed sequence instead sends the Device-wrapped Run
command to `/devices/{id}`. This endpoint difference is evidence for a test,
not proof that the appliance accepts an untimed cook.

The isolated `investigate/oven-untimed-start` build at `aaf15aa` sent explicit
zero in the settings step and used the app's operation endpoint for Run only
on untimed LCD_OV_WALL_16K starts. It retained fresh Smart Control checks before
both writes, the session lock, three-second settling time and at-most-once
dispatch. It did not retry using the aggregate endpoint after a refusal or a
lost response.
Positive-duration starts, Stop and other board families keep their existing
routes. At 14:54 America/Chicago on October 15, the owner reported the same
error with this build. Changing only the Run endpoint therefore did not resolve
the untimed Lower Bake failure. The experimental runtime and test changes were
removed; its commit remains available as evidence. The submitted #637 and #640
branches were not changed by this experiment.

The tested cases are omitted duration and explicit zero through the aggregate
endpoint, then explicit zero through the operation endpoint. All failed; a
one-minute duration succeeded. No working untimed remote start is established.
These observations suggest a firmware restriction or an unobserved protocol
requirement, but do not distinguish between them or prove a limitation for
other cavities, modes or oven models.

Samsung's NV51K7770S manual p.37 describes remote Start but does not state a
positive-duration requirement. Samsung's NE63*871 range manual p.46 explicitly
requires a cooking time for remote control; that different model's restriction
does not establish the wall oven's behavior.

### Untimed local Bake capture

At 15:36 America/Chicago on October 15, the owner supplied diagnostics after
the request to start an untimed Bake at the oven panel. The lower cavity's raw
body and translated resources both report `LowerBake`, `Operation.state=Run`,
`Oven.state=Preheat`, and `00:00:00` for both `operationTime` and `remainingTime`.
Its setpoint is 350 F; current temperature is 244 F in the cached raw body and
245 F in the translated resource. The upper cavity is Ready/NoOperation, the
divider is On and the probe is disconnected.

Both cavities report Smart Control false in this local-start capture. The
earlier failed remote-start diagnostic reported it true; the local capture's
permission state does not explain the earlier remote refusals. The target also
differs from the 400 F remote test, so this is not a controlled comparison of
start methods at otherwise identical settings.

The appliance reports an active untimed cook using zero durations, with no
additional untimed flag in the captured resources. This confirms the read-side
representation, not an accepted remote-start payload. In particular, the
reported `Oven.state=Preheat` is not evidence that it is writable. No new
command or runtime change follows from this capture. The private source
diagnostic's SHA-256 is
`42ebfc363a728937d7db4049e5ebb35abdf61a557ab705c6fa23adfe6381612b`.

### App caller follow-up

A further static trace of this APK found that both direct oven-activity callers
of `a(OperationModeEnum)` are `sendCommand(DeviderEnum)` methods passing Pause.
The helper's Run branch is therefore not evidence of a reachable fresh-start
flow in this app. The earlier endpoint experiment tested a real serializer and
helper, but describing it as Samsung's verified Start path overstated the
evidence. The settings-send handlers accept blank time fields as zero; no
positive-duration guard was found in the inspected handlers. These observations
do not establish what the current SmartThings plug-in sends to this model.

The next discriminating observation would be an untimed start attempt in
Samsung's own app on this oven. Success would establish another remote path to
investigate; refusal would support a restriction in Samsung's remote path,
without proving no alternative exists. Repeating the same LocalThings zero-time
writes would add no new evidence. No additional experimental write is proposed
from this static trace.

### Running cook-time edits

At 15:59 on October 15 the owner reported the same untimed-start problem for
the upper cavity and whole-oven configuration. Separately, an attempt to change
a running Lower Bake from two minutes to zero produced
`4.00 the format of request json is wrong` at `/operational/state/vs/1`.
At 16:07 the owner reported that increasing the running cook's time also
failed. The latter report does not include a separate error capture. The
zero-edit refusal therefore does not establish that clearing a valid running
timer is forbidden; positive edits also need investigation.

The existing `_cook_time_write` sends both `operationTime` and `remainingTime`.
Samsung's plug-in's `com.samsung.oven.shp.control.a.b(String)` duration helper
instead creates an Operation containing only `operationTime`. The new isolated
candidate omits `remainingTime` from LCD_OV_WALL_16K cook-time edits, retaining
the existing aggregate endpoint and envelope so only the field set changes.
Other board families keep their existing writes. The start sequence and its
Smart Control checks are unchanged, and no start-then-clear automation is added.

Regression coverage checks upper, lower and whole-oven routing, preservation
of the other hours/minutes component, zero and positive values, unchanged
remaining-time telemetry, and propagation of appliance refusals. Hardware
acceptance of the one-field edit is pending. The first hardware check is a
positive increase from two to three minutes; zero clearing should only be
retested after a normal edit is verified.

## Status and verification

- **Power:** the LCD_OV_WALL family's ineffective switch becomes read-only status,
  consistent with this owner's observations and #572. Setup removes only an old
  switch whose exact identity/config entry now has a discovered Power sensor.
  Power On does not establish heating.
- **Door:** on the measured board with its matching lower record, the entity
  view shares the upper door reading when the lower items list is empty. This
  was hardware-confirmed with the divider inserted. During testing of 69eb069,
  the owner reported Lower becoming Unknown after removing the divider. The
  sharing code incorrectly required the divider to be inserted; that condition
  is now removed. Tests cover open/close updates across repeated divider changes
  and startup in either position. An existing lower reading is preserved, and
  raw reads and diagnostics remain unchanged. The owner confirmed the corrected
  Door displays on both devices after installing d72b8da. The follow-up divider-out capture confirms Upper Close and an
  empty Lower door list; replaying it with the correction gives Closed on both.
- **Idle readings with the divider removed:** the October 14 follow-up capture
  still reports Power On, remote control enabled, Ready and NoOperation for
  both cavities. Lower exposes only NoOperation as a supported mode, so its
  Start Cooking button is unavailable. Both temperatures report current 175 F
  with desired 0; the existing idle-floor filter hides that sentinel, and zero
  means no setpoint. Remaining and operation times are both 00:00:00, so there
  is no Estimated Finish; paired cook-time controls are blank unless a duration
  has been held. Main reservoir tokens are In On / Out Off, and replay produces
  Closed for both Reservoir sensors. This snapshot explains those unset values,
  but it does not include HA's entity states or held choices; any other Unknown
  displays need their names or a screenshot before attributing a cause.
- **Reservoir:** the owner confirmed Closed = In On / Out Off, and Open = In Off /
  Out On, while the main door stayed open. The read-only opening sensor belongs
  to the cavity reporting both switch tokens; missing or contradictory readings
  are Unknown. On LCD_OV_WALL_16K with its matching lower record, the entity view
  also shows this shared reservoir on Lower. Any lower tank-switch tokens take
  precedence over the shared reading. After installing d72b8da, the owner
  confirmed that both device-page Reservoir sensors follow physical opening
  and closing.
  Other existing fixtures with both tokens also bind the sensor, but their position mapping has
  not been independently hardware-tested. No reservoir actuator is added.
- **Divider:** on that same measured board pair, both device pages display the
  divider state from the lower record, including when it is removed. The Upper
  copy uses a separate entity-view value, preserving Upper's connectivity flag.
  Both copies display Inserted for on and Removed for off, with equivalent state
  labels in all ten catalogs. The underlying on/off states remain unchanged for
  automations; unknown source readings remain Unknown.
  Both new copies are read-only, preserve existing entity identities and leave
  raw diagnostics, polling and control routing unchanged. The owner confirmed
  both Inserted/Removed displays in d72b8da.
- **Discovery with the divider removed:** the `OV` board token identifies the
  oven even when Lower offers only NoOperation. Previously its `WALL` description
  could fall through to the washer-prefix match during startup. Regression tests
  now verify both shared sensor copies from divider-in and divider-out startup.
- **Lower controls after reinserting the divider:** after installing 244fb00
  with the divider removed, the owner reported an unavailable Start Cooking
  button and obsolete Start, Pause and Delay Start controls. A regression test
  reproduces the missing button: Lower's startup list contains only NoOperation,
  so its Start Cooking entity was not registered and later mode updates could
  not restore it. LCD_OV_WALL now retains the entity across divider changes,
  making it unavailable while no modes are startable and available when they
  return. Existing mode and Smart Control checks still validate every start.
  Setup removes the three obsolete laundry controls left by the earlier type
  misidentification, scoped to the identified Lower cavity's exact IDs and
  config entry; current capabilities, other devices and user names on valid
  entities are preserved. Tests cover startup with the divider in or out,
  repeated transitions without reload, Lower command routing and the English
  Start Cooking label. In d72b8da, the owner confirmed that Lower Start Cooking
  becomes available after reinserting the divider without restarting HA.
- **Write verification:** items match by ID and requested fields, allowing extra
  returned fields and equivalent finite numeric setpoints. IDs and units remain
  exact; ambiguous, missing or mismatched items fail. Individual and batch writes
  share the comparison, including merged options. A stale Run after Stop still
  fails verification until Ready is observed.

Cold idle readings remained at 175 F with desired 0. The existing display filter
therefore showed Unknown; that value is not a measured room temperature. This
change does not alter temperature filtering or claim to fix a physical sensor.

## Configuration switches

The October 14 diagnostic and divided-cavity fixture report `EnergySaving_On`
but no `Sound_*` token in the upper record; the lower has no options array.
Sound was bound whenever the options array existed,
making an absent option appear as an Off switch. It now uses the same
token-presence gate as the other oven option switches. Devices reporting Sound
keep their control. Setup removes the old LCD_OV_WALL Sound registry entry only
when that cavity reports an options list without Sound; unknown resources and
other config entries are preserved.

The owner's panel photos confirm a separate Volume slider spanning 0–15.
On October 14, diagnostics were supplied after setting it to 0 and again to 15,
following instructions to reload the integration. Each download contained both
cavities. The complete main resources, lower resources and raw legacy transport
bodies were identical at both settings; only HA's internal Observe mode-change
timestamp differed. No named Sound/Volume field or indirectly changing value was
found. This rules out a volume reading in those captured responses, not every
possible firmware command or unqueried endpoint. No functional volume slider can
be added from this evidence, and no guessed volume write is introduced.

Energy saving already has that presence gate. Its command sends one
`EnergySaving_On` or `EnergySaving_Off` token to the selected cavity's Mode
resource through the existing legacy transport. On October 14 the owner confirmed
that the existing HA toggle works, in response to an idle HA-Off/panel-readback
check. This is owner-confirmed hardware behavior; no request/response log was
supplied and the Smart Control state at the time of the write was not established.
The existing switch is retained without a command change.

The panel identifies this setting as **12 hour energy saving**: automatic
shutoff after 12 hours of baking or 3 hours of broiling. This is separate from
the maximum 9:59 Cook Time countdown documented on [manual][manual] p.24;
baking can also be started with Cook Time unset. The shutoff setting does not
establish support for a longer countdown.

The coordinator initially displays writes optimistically. An explicit immediate
readback check is currently conditional on Remote Control being off; otherwise
the normal refresh/settle path applies. A brief switch movement or HTTP success
alone is therefore insufficient evidence. The Sound write confirmed in
[the earlier investigation](oven-cycle-start.md#what-is-measured) was on a
different TP2X board and does not prove legacy wall-oven support.

The oven registry reuses the shared `diagnosisStart: Start` command. On October
14, the owner's first logged attempt at 17:59:27 was blocked by LocalThings'
Remote Control guard before transmission. After enabling Smart Connect, the
18:34:49 attempt logged `PUT /diagnosis/vs/0` with success code `0x44`. The legacy
transport sends this as a `Diagnosis` object inside `Device` to `/devices/0`;
the success acknowledgement alone does not confirm execution. The immediate
refresh was suppressed by the coordinator's settling guard, and the supplied
log contains no subsequent diagnosis result. At approximately 18:36 the owner's
HA screenshot showed `Ready`, and the owner reported no oven-screen response.
These are the log/UI's local times. No diagnostic run or result is verified.

The inspected Samsung Oven plug-in APK (v1.1040.8.0) includes generic
`getDeviceDiagnosisById` and `putDeviceDiagnosisById` helpers targeting
`/devices/{id}/diagnosis`, and a `DiagnosisJs` model containing `diagnosisStart`.
The inspected DEX contains no oven-specific caller of those helpers or verified
start/result sequence. That narrower endpoint differs from LocalThings'
aggregate write, but a shared app helper does not establish which write this
oven implements. No alternative diagnosis write was attempted. The Start
diagnosis button is withdrawn specifically for `LCD_OV_WALL_16K`, whose tested
command provides no verified function or useful feedback. This is a conservative
UI decision, not proof that the firmware cannot run diagnostics. Diagnosis status
and Alarm code remain read-only sensors; `Ready` is not evidence of a completed
or passed diagnostic. Other oven boards retain their existing diagnosis button.
Setup removes the withdrawn button's registry row by exact unique ID and config
entry, including renamed rows, so upgrades do not leave an unavailable control.
Automations or dashboards referencing that button need to be updated.

## Lamp investigation closed for this submission

All 21 native resource responses were identical with the lamp on and off.
The app-defined `/devices/0/light` and `/devices/1/light` reads returned HTTP 405
with `Not supported resource`. The inspected Samsung apps supplied no verified
oven-specific lamp command. The exact-model service manual shows a lamp relay,
but a relay on the board does not establish a network API.

An October 14 `/devices` subscription recovered complete door Open/Close events
on `/devices/0/doors`, with no lamp fields or notifications during manual Lamp
changes. The callback needed a bounded body read after a header-parser defect.
The temporary subscription was removed and its absence confirmed. This establishes
local notification delivery, not lamp support or production push-update support.
The standalone capture scripts are research tools, excluded from this submission.

No lamp entity or guessed write is added. Native LocalThings lamp support is an
optional future feature if new protocol evidence emerges; external sensors and
actuators are outside the owner's requested scope. Detailed research is retained
on the [investigation branch][research].

## Kitchen timer investigation

The owner supplied an idle capture and another with the separate kitchen timer
running on October 14. The raw upper and lower bodies expose no countdown,
timer-active flag or additional resource; cooking operationTime and remainingTime
stay 00:00:00. The only device-body change was remoteControlEnabled becoming
false. This provides no timer sensor or control through the examined local
interface, without proving that no undiscovered endpoint exists. Cook duration
must not be presented as the independent kitchen timer.

## Final build acceptance

On October 14 the owner installed build
`a23a0109152ef2754c715b5e3a2199b3a2bcf9c3`, reported that everything seemed to
work normally, and approved preparing the changes for submission. The supplied
HA screenshot confirms that Start diagnosis is gone while Alarm code,
Connection mode and Diagnosis status remain. This is general owner acceptance,
not a separate hardware test of every changed feature or cooking combination.

That build passed all 3,202 tests on Python 3.14.8, plus formatting, lint and
type checks. The owner then installed 81826e4, which includes shared Divider and
Reservoir displays, five mode exclusions and the verified Dehydrate/Bread Proof
mappings, and confirmed that the new modes are mapped correctly. That build
passed all 3,222 tests plus formatting, lint and type checks. This confirmation
does not establish remote recipe starts or confirm every other added display.

Build 244fb00 carries the existing recipe mappings into whole-oven
Healthycook1–4 and alphabetizes cooking-mode choices. It passed all 3,228 tests,
plus formatting, lint and type checks. All ten translation
catalogs are checked for matching keys and placeholders; whole-oven recipe
labels reuse the existing localized Upper/Lower labels. The owner installed
244fb00 and confirmed that this presentation looked good, then reported the
Lower control issue after reinserting the divider. The correction above
addresses the reproduced startup failure.

The Lower control correction passed all 3,239 tests, plus formatting, lint
and type checks. The subsequent Divider state labels and divider-out door fix
pass all 3,240 tests and the same checks. No appliance commands were sent during
these software tests.

After installing d72b8da on October 14, the owner confirmed the requested
divider-transition checks: with the divider removed at restart, both Divider
sensors show Removed and both Door sensors follow opening and closing;
reinserting it without another restart changes both labels to Inserted and
restores Lower Start Cooking availability. This confirms the display and
entity-lifecycle fixes, not a new heating or Start/Stop test. The owner then
separately confirmed Reservoir Open/Closed reporting on both device pages.

The owner subsequently confirmed Upper Convection Bake and Lower Bake running
at the same time, each stopping with its respective Stop button. The owner also
confirmed that the obsolete Lower Start, Pause and Delay Start controls are gone.
The planned pre-submission hardware checks are complete; remaining coverage
limits below do not require repeating those checks. The Broil menu correction
was made after this confirmation. At 22:36 America/Chicago on October 14, the
owner reported checking the latest build, 4118021, and approved preparing it
for submission. This is final-build acceptance, not another heating test.
That build passes all 3,240 tests plus formatting, lint and type checks. The focused
lifecycle tests also run independently after explicitly enabling custom
integrations for their translation lookup.

This test build retains the two-device layout. The requested combined-device
presentation will use a separate feature branch and pull request, preserving
this fixes
branch as the fallback. No device-grouping migration is included here.

## Temperature probe follow-up

On October 15, the NV51K7770S owner connected the probe. The 11:34 and 11:43
America/Chicago captures report `meatprobe_connected`, Ready / NoOperation, and
temperature item `id: "1"` with current and desired values of zero in Fahrenheit.
Selecting Bake 350°F and a probe target of 150°F on the panel without starting
does not change those reported values.

The 11:46 running capture reports Bake / Run / Preheat, cavity target 350°F,
and probe item `id: "1"` with desired 150°F. The cached transport body has
current 100°F; the resource snapshot has 107°F. The divider reports Off. This
confirms the current/target mapping and connected token on this model. It does
not establish remote probe target writes, probe-specific remote starts,
measurement accuracy or reporting below 100°F. Connected idle zero handling is
unchanged; both entities remain read-only.

Sensor setup now adds already-discovered optional sensors when their existing
inclusion check first passes during a normal coordinator update. No integration
reload is needed. Once created, probe sensors become unavailable when unplugged
and reuse their existing IDs and custom names on reconnection. The owner
confirmed unplugging at 12:14 and reconnection without a reload at 12:26 on the
separate combined-device build `34de099`. That confirms the shared sensor logic;
the two-device version itself has software coverage, not a separate hardware
installation check.

The display names are Temperature Probe and Temperature Probe Target, with
localized labels in all ten catalogs. Internal keys `food_probe_temp` and
`food_probe_setpoint` and existing HA entity IDs remain unchanged. The tests
cover legacy HTTPS, OCF vendor arrays and OCF fallback resources, initial and
later detection, repeated unplug/reconnect updates, unload cleanup and label
upgrades in all ten languages. The upper and lower devices remain separate.
This update passes all 3,257 tests (57.59 seconds) on Python 3.14.8, plus
formatting, lint and type checks. Its 17 probe regression cases also pass
independently. Translation checks do not constitute native-speaker review.

## Divider-aware labels with separate devices

The upper device's cavity controls and sensors now use Upper labels with the
divider inserted and Oven labels when it reports Removed. For example, Upper
Cooking Mode becomes Oven Cooking Mode, and Upper Start becomes Oven Start.
The labels update during normal polling without a reload. A missing divider
reading keeps Upper rather than asserting whole-oven operation.

This applies to oven/range pairs with one declared Lower cavity and its divider
resource, including modeSpec-derived declarations. Regression fixtures cover the
NV51K7770S legacy pair, NV75N Dual Cook OCF oven, NE9801T Flex Duo range and
NV7B6665IAA Dual Cook. Single-cavity and unrelated appliances retain their labels.
This does not claim hardware validation for every model in those families.

Both HA devices remain separate. Device names, lower-device labels, shared
sensor and probe labels, command routes, entity IDs and custom names remain
unchanged. No grouping migration, duplicate removal or new availability rule is
introduced. All ten catalogs reuse the combined-device labels and retain their
cooking-mode state translations. The new tests cover existing-ID upgrades,
both initial divider states, repeated transitions and unknown divider readings.
This separate-device label update has not yet been hardware-tested.
All 3,284 tests pass (60.22 seconds), with formatting, lint and type checks.
The 44 focused probe/label cases pass independently, including all ten locales.

## Validation limits

Regression coverage includes both cavity paths, held settings, mode labels,
duration conversion, paired hours/minutes in all 24 setting-entry orders,
strict permission checks, timeout/refusal/no-replay paths,
status migration, Sound capability gating, diagnosis-button cleanup, reservoir
states and partial-item verification. Passing tests do not resolve the reported
Smart Control incident. Timer completion, the complete paired-timer entry-order
and boundary matrix, simultaneous combinations beyond Upper Convection Bake
with Lower Bake, all recipe starts and running adjustments remain hardware
coverage gaps.

[manual]: https://images.thdstatic.com/catalog/pdfImages/99/9900cc56-8433-4e1b-ba18-4271b575791d.pdf
[research]: https://github.com/roweboat123/localthings/tree/117eade8c5e0ffea1a22799e42ad4c6f27eb3b08/docs/investigations
