# Remaining keyword grants

Hunter Sliver grants provoke as an individual keyword ability. Its attack trigger remains
optional and can untap and require a defending player's creature to block (CR 702.39).
Cavalry Master likewise grants a distinct flanking ability; the combat engine counts each
printed and granted instance separately (CR 702.25b). The obsolete refusal was removed.

Lymph Sliver grants absorb 1. Each absorb instance is a separate prevention candidate in
the ordinary replacement loop (CR 702.64). It applies to each source/event independently,
interacts with damage doubling in the affected player's chosen order, and respects
unpreventable damage. It works on Slivers controlled by any player and on combat damage.
Losing absorb removes its prevention immediately. Oracle now recognizes parameterized
absorb lines, and coverage requires a nonnegative integer parameter.

Teferi's Curse, Cloak of Invisibility, and Shimmer grant phasing through the ordinary
layer machinery (CR 702.26). Attached Auras phase indirectly with their host. Shimmer's
entry choice includes all 17 land types from CR 205.3i, with a public “Chosen land type”
record. Basic-land-type choices retain their existing records and restriction. Chosen
land-type selectors handle both apostrophe spellings in Urza's. Cloak's Wall restriction
is retained alongside phasing.

Riding the Dilu Horse has no stated duration, so both its +2/+2 and horsemanship last
indefinitely (CR 611.2a). The generic combined pump/grant parser and pump primitive retain
that duration. It remains a resolved effect fixed to the same object; ordinary horsemanship
blocking rules apply (CR 702.31).

Validation is in `tests/test_rules_remaining_keyword_grants.py`, with real Oracle fixtures
and replay/save-load for gameplay. The catalog and selected regression checkpoints are
recorded in CURRENT_STATE.md after verification.

The inventory also promoted Barbed Foliage. Flanking now has a derived instance count
that follows layer-6 timestamps: losing it removes every existing instance, and a later
grant adds only its own instance. Combat tests combine Barbed Foliage, Cavalry Master,
and a later Agility to verify this (29 focused cases total; 155 final regressions passed).
