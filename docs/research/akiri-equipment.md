# Akiri, Fearless Voyager

Oracle source: repository canonical card database, fixture
`backend/tests/fixtures/akiri_equipment_cards.json`.

The attack condition normalizes Akiri's word order into the existing aggregate
equipped-creature attack condition. CR 508.1/508.3 and 603.2: this triggers once
per directly attacked player, regardless of creature or Equipment count. An
attack at a planeswalker does not qualify. Removing Equipment after declaration
does not undo a trigger already generated.

The activated ability chooses optionally during resolution (CR 608.2d), without
targeting. Equipment controlled by an opponent can be unattached from your
creature. The saved decision records exact Equipment and host object identities;
the original ability controller makes the choice even if Akiri leaves. Native
detach, tap, and keyword-grant effects finish the instructions before state-based
actions. An already tapped creature still gains indestructible, and shroud does
not prevent choosing Equipment attached to it. The grant ends at end of turn.

A Germ losing Batterskull dies for zero toughness under CR 704.5f despite gaining
indestructible. Its living weapon setup is tested by actually casting Batterskull.
The new resume handler is eagerly registered and tested from a saved game in a
fresh Python process, including replay equality.

Focused tests: `backend/tests/test_rules_akiri_equipment.py`. Shared attachment
and declared-defender regressions also run for this change.
