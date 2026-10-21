# Filtering on either base power or base toughness

Authority: Comprehensive Rules effective 2026-09-25, CR 208.4b and 613.4 (base
power/toughness after setting effects, before modifying effects or counters),
107.1c (any number), 701.21a (sacrifice), 608.2c/h (ordered resolution and information),
and 702.114 (devoid).

Sword of the Squeak counts a creature once when either base stat is exactly 1.
Angelic Aberration allows sacrificing creatures with either base stat 1 or less,
then makes one Eldrazi Angel per creature sacrificed. Counters, anthems, and temporary
pumps do not change base stats; effects such as Lignify that set them do.

A selector suffix records the either-stat comparison and reads the existing derived
base values. The explicit sacrifice-count sequence reader now also supports a token
creation continuation, using existing reference counts and token creation primitives.
No new state fields.

14 focused scenarios and 213 selected regression tests pass (overlap), with replay
and save/load gameplay checks. Cases cover exact versus upper-bound comparisons,
0/1 and 0/2 creatures, counting 1/1 once, controller filtering, counters/anthems/pumps,
dynamic count changes, equip and optional Rat-entry attachment, zero/one/multiple
sacrifices, replaced destinations, token keywords/base stats, devoid, Lignify, and
no eligible creatures. Ruff, mypy (349 files), and whitespace checks pass.

The catalog promotes exactly Sword of the Squeak and Angelic Aberration, with no
lost FULL support: 27,672 FULL / 4,396 PARTIAL of 32,068 Commander-legal cards.
