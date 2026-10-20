# Resolution sacrifices followed by counted draws or returns

Authority: Comprehensive Rules effective 2026-09-25, CR 107.1c (any number includes
zero), 701.21a (sacrifice), 608.2c/d/h (instructions, choices on resolution, and
information), 118.11 (replaced payments), 603.2c / 603.10a (simultaneous deaths),
400.7 (new objects), and 702.170 (plot).

Pitiless Carnage, Malevolent Witchkite, and Lich-Knights' Conquest count the
permanents actually sacrificed during resolution. A permanent of several eligible
kinds counts once; a sacrificed token counts even after it ceases to exist. A
replacement sending a sacrificed permanent to exile does not erase that action.
Conquest chooses creature cards after the sacrifices, so a creature just sacrificed
can be returned; it returns as many as possible if there are fewer eligible cards.

The language parser accepts explicit “you control” and mixed artifact/enchantment/
token selectors for any-number sacrifices. A narrow sequence reader joins the
sacrifice and following draw/return through an explicit existing resolution binding.
Existing simultaneous sacrifice, choice, draw, return, and reference-count primitives
perform the effects. No new state fields.

22 focused scenarios and 366 selected regression tests pass (overlap), with gameplay
replay/save-load checks. Cases cover zero/one/multiple sacrifices, filtering, overlapping
kinds, tokens, replacement destinations, return choices after sacrificing, insufficient
graveyard cards, Blood Artist witnessing simultaneous deaths, and plotting Carnage.
Ruff, mypy (349 files), and whitespace checks pass.

The catalog promotes exactly Pitiless Carnage, Malevolent Witchkite, and Lich-Knights'
Conquest, with no lost FULL support: 27,670 FULL / 4,398 PARTIAL of 32,068 Commander-legal
cards. Continue remaining automation work.
