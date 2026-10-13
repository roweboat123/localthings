# NV51K7770S control follow-up

The October 13, 2026 hardware check of draft revision `6870fa9` confirmed
numeric Cook time and the lower shared-door display. Setpoint still appeared
as a slider, and the obsolete Power switch remained unavailable in Controls.
Normal Start/Stop through the revised entities has not yet been verified.

## Power and Setpoint

Power is now a read-only binary sensor. Setup removes the corresponding old
switch registry entry only when discovery includes that Power sensor, using
the exact unique ID and config entry. Other controls remain registered.

Both discovered Setpoint entities expose `mode: box` in the development
environment. The installed entity attributes and installed source still need
checking; the screenshot alone does not establish whether the cause is an
old loaded build, a customization or the frontend. Unknown temperature is
not evidence of failed heating while the oven is idle.

## Modes and limits

Samsung's NV51K7770S user manual ([PDF][manual], pages 24, 27–28 and 34)
distinguishes whole-oven operation from divided operation:

| Divider installed | Documented cooking choices |
| --- | --- |
| Upper | Broil, convection bake, convection roast, steam bake, Healthy Cook |
| Lower | Bake, convection bake, Healthy Cook |
| Healthy Cook in either cavity | Baked potato, grilled chicken, salmon steak, white fish fillet |

Dehydrate and bread proof are whole-oven choices. The manual also specifies
a 9-hour-59-minute cook-time maximum and 480°F maxima for divided baking
and the four divided Healthy Cook programs, with further restrictions when
both cavities operate together. The integration's generic 1,439-minute and
550°F bounds should not be treated as verified limits for this configuration.

The captured board list names four `UpperHealthycook` codes but no lower
Healthy Cook codes. The current lower fallback omits Healthy Cook. Capture
the mode reported for each panel-selected recipe before adding codes or
replacing numbered labels; the manual's row order is not a protocol mapping.
The existing `LowerConvectionRoast` fallback came from the panel report in
#572 but is absent from the manual's lower list, so verify it too. Do not
copy whole-oven modes into both divided lists.

[manual]: https://images.thdstatic.com/catalog/pdfImages/99/9900cc56-8433-4e1b-ba18-4271b575791d.pdf
