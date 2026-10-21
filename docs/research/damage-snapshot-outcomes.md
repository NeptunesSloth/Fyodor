# Damage instruction snapshots

The exact printed sequences in `backend/app/rules/damage_snapshot_outcomes.py` use ordinary target selection, typed resolution references, native movement receipts and queued native effects. Every simultaneous damage instruction is one native damage batch, including Incite Rebellion, Grim Contest and multiplied Chainer's Torment tokens. Replacement choices preserve the captured instruction and resume through the existing damage continuation.

Destruction instructions capture last battlefield characteristics and controller before movement. Conditional deaths use actual died receipts; indestructible does not suppress unconditional follow-up damage. Public card sources opt in only for explicitly bound graveyard/exile objects (Selfless Exorcist); default named-source behavior is unchanged.

Gameplay and cold-resume proofs: `test_rules_damage_snapshots38.py` and `test_rules_damage_snapshot_sequences38.py`. Canonical card lists and official rulings were researched against the pinned September 25, 2026 Comprehensive Rules and fetched Wizards rulings. Completion remains provisional until the focused, related and central checks finish.

Verified independent sequence subset: 24 passing gameplay cases, including four fresh-process saves and lethal Command into Platinum Angel, doubled Anthem-modified Chainer tokens, current-exile CDA power, and departed Exorcist recipient. First-family and paused replacement/draw-choice proofs are tracked separately. Related native damage/value/receipt modules:158 passing cases. Existing static-condition regression:91 passing cases after bounded literal-name disjunction repair.

Final root contribution:46 unique focused PASS (22 first-family,24 sequence-family), including six fresh-process saves, two paused native replacement/draw continuations, plus249 related PASS (158 damage/value/receipt and91 static conditions). Feedback support was corrected from PARTIAL Fireball to canonical FULL Blaze; no application change was necessary. Native Incite pending616 proof verifies all five damage facts share one batch and original creature counts remain frozen.
