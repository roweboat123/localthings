# Brennan's personal LocalThings build

Version: **0.38.0+personal.1**, based on upstream **v0.38.0**
(`bdbf750889a95ebdf147614c01138f42bc9549a3`).

This branch combines the saved personal preferences with the current upstream
fixes. It uses the existing `localthings` integration and configuration entries.
It is a personal build, not an upstream release or a second integration to add.

## Appliances

| Appliance | Owner's model | Behavior in this build |
| --- | --- | --- |
| Oven | NV51K7770S / LCD_OV_WALL_16K | Personal controls, labels and combined device page below. |
| Cooktop | NZ36K7570R / TP6X_CT_16K | Keep v0.38.0 support, including the owner's earlier upstream fixes. |
| Refrigerator | RF23DB9750QLAA / TP1X_REF_21K | Shorter door labels and the door-aware Cabinet Light switch. |

The other owner's RS68N8941SL/EF Family Hub is not part of this build.

## Oven preferences

- One Home Assistant device page, with independently routed upper and lower
  controls and readings. Confirmed copies of shared door, divider, reservoir,
  power and Smart Control readings are collapsed to their original sources.
- Separate Cook Time Hours and Cook Time Minutes inputs, with a combined maximum
  of 9:59 and any narrower limit reported by the selected mode. An unset idle
  timer stays blank; explicitly entering zero remains meaningful.
- Upper labels with the divider inserted or its status unknown; Oven labels
  when removed. Lower stays Lower and its cavity entities become unavailable
  when the divider is removed.
- English Title Case labels and cooking choices sorted by their displayed names.
  Healthy Cook retains the captured names: Baked Potato, Grilled Chicken, Salmon
  Steak, White Fish Fillet, Dehydrate and Bread Proof. The last two are whole-oven
  choices; the raw mode codes and upstream mode restrictions stay intact.
- Hide Start Diagnosis while retaining Diagnosis Status and Alarm Code.
- Keep v0.38.0's quiet repeated Start during a running cook. Cook-time edits use
  the existing write-through behavior; pressing Start does not send another Run.
- Preserve the older personal build's untimed-start sequence described below.
  This does not add Pause or Resume to this oven.

The combined-device and paired-time changes require the reported LCD_OV_WALL_16K
WallOven identity. Unrelated ovens and microwave/oven combinations retain their
upstream layout. A lower device disabled in Home Assistant remains separate and
disabled. A subdevice disabled through LocalThings options stays excluded.

For `localthings.start_cooking`, select `upper` or `lower` in the optional
`cavity` field when targeting the combined device. Omitting the field uses Upper,
which also controls the whole oven with the divider removed. Each selection
keeps that cavity's mode, setpoint, timer and Smart Control checks. Raw resource
actions still use the original resource paths.

### Untimed start

The saved personal implementation starts this oven with a temporary one-minute
timer, confirms Run, clears the timer to zero and confirms that both operation
and remaining time are zero. It checks Smart Control before settings, Run and
timer clearing. Failed or uncertain stages report an error and do not replay
Start. Ordinary timed starts retain upstream's sequence and 0.5-second settling
delay. No permission check is bypassed or remotely re-enabled.

The sequence was carried forward from the earlier personal implementation
[`7c6e8d5`](https://github.com/roweboat123/localthings/commit/7c6e8d5c7c2bad0d21c6f41ec99a279cab1c30e7).
This assembled version still needs confirmation on the owner's appliance.

## Refrigerator preferences

Door entity names omit the redundant word Open; their open/closed state remains
visible. Cabinet Light becomes unavailable while a reported door is open and
returns when the doors close. Brightness and the other settings are unchanged.
The existing shared fridge descriptors carry these preferences; hardware evidence
is limited to the owner's RF23DB9750QLAA.

Welcome-light proximity is not used as a motion signal or an availability gate.
The [recorded investigation](../investigations/refrigerator-rf23db9750.md) explains
why the reported fields could not establish live approach activity.

## Upgrade and installation

1. Make a full Home Assistant backup, and keep a copy of the currently installed
   `custom_components/localthings` folder. Keep that backup until the new build
   has been checked on all three appliances.
2. Extract the personal-build download on your computer. The package contains
   `custom_components/localthings` and these instructions.
3. Replace the existing Home Assistant `custom_components/localthings` folder
   with the package's folder. Use the same Home Assistant configuration directory;
   do not nest it inside the old `localthings` directory. Do not remove the
   integration from Home Assistant or pair the appliances again.
4. Restart Home Assistant. Confirm the loaded integration version is
   `0.38.0+personal.1`, then check the existing appliance pages.
5. Keep automatic updates for LocalThings off in HACS. Installing an upstream
   update over this folder will replace the personal changes. Future personal
   updates need the same integration work against the newer upstream version.

Existing paired timer identities and custom entity names are retained. When
upgrading from the public single-minutes version, that old timer entity is
replaced by the Hours and Minutes entities; automations using the old timer
must be adjusted. Combining a previously split oven retains the upper device
and moves the lower entities while preserving their unique IDs, entity IDs,
custom names and disabled settings. Automations targeting the former lower
**device ID** may still need updating even when entity IDs survive. Confirmed
duplicate shared entities are removed, so check references to those too.

The surviving upper device's user name and area take precedence. A removed
lower device's separate name and area cannot both appear on one device page.
Home Assistant still controls entity order; this build does not add tabs.

To undo the installation, restore the full backup. Simply reinstalling upstream
code does not guarantee reversal of device grouping or automation changes.

## Validation

Automated checks cover paired timer bounds and independent cavity writes,
quiet Start, untimed-start failures and confirmation, custom-name migration,
disabled entities and devices, offline startup, divider changes, unrelated
device layouts and fridge-light recovery. The complete upstream test suite is
also run. On 13 November 2026 UTC, all **4,374 tests passed, with 7 skipped**
on both Python 3.13 / Home Assistant 2026.2.3 and Python 3.14 / Home Assistant
2026.9.4. Formatting, lint and type checks passed. The final test-only adjustment
was also checked on Python 3.14 (34 focused tests).

This is automated verification. No new Home Assistant installation, appliance
operation or physical test was performed for this assembled version. English
is the intended display language; catalog structure and placeholders are
checked in all 14 languages, but some new personal strings use English fallback.

After installation, first check device pages, names and live readings. During
normal supervised use, confirm each cavity's mode, temperature, timer edits and
Stop, then the fridge light with a door open and closed. Untimed start should be
checked separately; do not infer success from an accepted command alone.
