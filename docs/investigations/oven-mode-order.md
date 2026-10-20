# NV51K7770S cooking-mode order

Cooking modes are listed alphabetically by their translated labels, making
them easier to find as the available choices change with the divider.
This applies to the exact `LCD_OV_WALL_16K` board's Oven, Upper and Lower
selectors. Other models and selectors retain their existing order.

The order uses Home Assistant's configured language when the integration loads.
Reload the integration after changing that language. A browser profile using a
different language may show translated labels in a different alphabetical order.
Sorting is case-insensitive; it does not implement language-specific collation
rules for accented letters. Missing translations fall back to English, and
unknown modes keep their existing readable labels.

Only the displayed order changes. The mode values, current selection, entity
IDs, device-reported lists and command routing stay intact. Idle remains in the
list under its normal label, with its existing selection validation. Sorting
does not send commands or add or remove choices.

`SelectDesc.sort_options` defaults to false. The oven registry enables it only
for this board's cooking-mode descriptor. The select platform loads translations
through Home Assistant and sorts a copy of the displayed options, keeping the
original value mapping for writes.

Software checks cover all ten languages, both cavities, changing option lists,
the static fallback, unknown values, untranslated labels and unaffected appliance
fixtures. They verify that each choice still maps to its original command value.
This change does not require new appliance protocol behavior or new translations.

During the combined review, compose the model-specific descriptor with item 12's
mode exclusions and item 11a's Sound gate. Check the resolved translation key
with item 4's Healthy Cook labels and item 13's cavity labels.
