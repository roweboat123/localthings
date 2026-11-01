# Personal cooking-mode order (item 14)

Selected for Brennan's personal build on 1 November 2026. No upstream PR is
planned. This is a preference, not a correction to the oven's reported modes.

The Oven, Upper and Lower cooking-mode menus on the `LCD_OV_WALL_16K` board
sort by translated label. Other boards and selectors keep their existing
order. The current mode, option values, entity identities, cavity command
routes and start validation are unchanged. The sorted list still comes from
upstream's mode filtering, including its current-program display exception.

Home Assistant's `select_first`, `select_last`, `select_next` and
`select_previous` actions use the sorted order too. An automation that names
a specific mode continues to select that same mode; one that selects by
position may select a different mode after this customization.

Sorting uses Home Assistant's configured language when the integration loads.
Reload the integration after changing that language or its translations. A
browser using a different profile language can show a nonalphabetical order.
Comparison ignores case but uses Unicode order, not language-specific accent
collation. Missing labels fall back to English, then the readable mode value.

The implementation resolves each entity's current translation key, so the
divider-aware catalog from #723 can be used. When combining #699 and #723,
copy the Healthy Cook states into both mode catalogs as recorded in the
working checklist. Apply the personal recipe names and item 15's Title Case
labels to both catalogs before final validation. Case alone does not change
the order; a renamed recipe can.

This branch is an independent component of the future personal build. It does
not assemble or install the paired hours/minutes controls, personal labels,
recipe names or hidden Start diagnosis control.

Validation on upstream `ed5958724b8e25c295abb35eb34c323a9cd6689d`:
3,570 tests passed on Python 3.13 and 3.14, including 42 sorting cases across
all eleven languages. Formatting, lint and type checks passed on both.
A separate combination with #667 (`63964af`), #699 (`3f4da79`), #721
(`7bc027e`), #722 (`56316b3`) and #723 (`fe0de36`) passed 177 focused tests
on Python 3.14 after their previously recorded merge adjustments. This was
automated verification; no appliance installation or physical test was made.
