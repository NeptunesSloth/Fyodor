# Reanimation entry riders

Canonical Oracle fixtures are in `backend/tests/fixtures/reanimation_entry_cards.json`.

Vigor Mortis's conditional counter changes the return instruction, so the counter
is present as the creature enters (CR 614.1c, 122.6). The native cast-condition
predicate reads actual green mana spent, rather than available mana or colors it
could be spent as. The choice is fixed before entry choices pause the resolver.
A free cast with unspent green receives no counter; a copied spell inherits no
green payment from the original. Counter replacements remain native.

Aberrant Return already uses the native one-to-three target group spanning all
graveyards and one simultaneous return under the caster's control. Its final
sentence now adds the native -1/-1 entry counter. Exact target references permit
partial resolution while excluding a replaced object. A 1/1 returned with the
counter dies to state-based actions normally.

Fifteen focused cases and 71 related paid-mana/entry-counter cases pass across
runs, including actual Reverberate retargeting, a JSON-reloaded Phantasmal Image
entry choice, Doubling Season, Solemnity, Mycosynth Lattice, multiple owners,
target-count validation, replay and save/load. No callback is introduced.
