# NV51K7770S Start Diagnosis

Start Diagnosis offered no verified diagnostic run or useful feedback on this
oven. Withdraw that button while retaining Diagnosis Status and Alarm Code.

## Hardware observation

On 14 October 2026, an attempt with Smart Connect enabled received success code
`0x44` for the diagnosis command. The owner saw no response on the oven, and a
later Home Assistant screenshot still showed Ready. An acknowledgement confirms
receipt of the request; it does not establish that a diagnostic ran or passed.

LocalThings sends `Diagnosis: {diagnosisStart: Start}` through the aggregate
`/devices/0` write. Samsung's app contains generic helpers for a separate
`/devices/{id}/diagnosis` endpoint, but the investigation found no verified
oven-specific start/result sequence. No alternate diagnosis command was tested.
The [original configuration investigation](https://github.com/roweboat123/localthings/blob/b9c485da9606f2dab5c8b1a4f35a6325582e56f8/docs/investigations/legacy-oven-controls.md#configuration-switches)
records the request and follow-up observations.

This is a decision to remove an unverified control. It does not establish that
the oven firmware cannot perform diagnostics. Diagnosis Status continues to show
what the appliance reports; Ready must not be interpreted as a completed test.

## Implementation and scope

`registry/capabilities/oven.py` specializes the shared `dishwasher.DIAGNOSIS`
capability, changing only the button's existence predicate. The button is hidden
when the first `modelNum` component is exactly `LCD_OV_WALL_16K`.
`registry/by_type/oven.py` registers that specialization. The status descriptor
and polling tier are reused unchanged; other oven boards retain their button.
Microwaves and dishwashers keep their existing capabilities.

Setup removes the old button by integration, button platform, full unique ID
and owning config entry. Renamed and disabled buttons are included. Status
sensors and unrelated entities remain. Removal is logged; dashboard or automation
references to that button need deleting.

Sound and Energy Saving are unchanged by this branch. It introduces no new
labels or translation changes.

## Validation

`tests/test_oven_diagnosis_control.py` checks the exact model boundary, retained
status, per-cavity cleanup, offline restoration and unaffected microwave and
dishwasher controls. The existing golden entity lists are unchanged.
