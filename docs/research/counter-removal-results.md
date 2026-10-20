# Counter removal and its actual result

Canonical Oracle fixtures cover Aether Snap, Give // Take, Hex Parasite, Mutated Cultist, and Price of Betrayal. Give // Take's two canonical repository faces are normalized into importer `card_faces`; gameplay covers both Take alone and the genuinely fused spell.

The existing native counter-removal primitive already records the number actually removed. New bounded grammar uses that scalar for Take's draw, Hex Parasite's temporary power, and Mutated Cultist's native next-spell cost grant. Chosen amounts therefore are not substituted for actual removals, and announced X is only an upper bound. Native binding renaming and saved effect continuations remain in use.

The existing single-object per-kind quantity chooser now also accepts live player targets and removes their counters with native resource actions. Player speed is excluded: it is represented as a resource but is not a counter (702.179), as in the existing proliferate implementation. New clauses use typed quantities rather than allocating one option per possible amount; old clauses retain their existing option format. Each paused permanent removal retains its exact object identity, so a new incarnation cannot supply counters to an older ability.

Two generic closed target shapes extend the existing permanent-or-player family: permanent or opponent, and artifact/creature/planeswalker or opponent. Existing target protections and rechecking apply, and neither includes the caster as a player target.

All-removal uses the actual finite counter total rather than the old million-counter sentinel. Native set-counter/resource actions handle large removals when the remaining value fits their normal input bounds; this records the complete removal event without broadening manual UI limits. Native delta chunks handle other partial reductions. A loaded legal large-counter state verifies Aether Snap removes more than two million counters completely.

Aether Snap removes counters from battlefield permanents before exiling tokens; it leaves player counters alone. Give then Take in a fused spell counts the counters actually added by Give, including native Doubling Season replacements. Native Abundance replacement tests preserve the subsequent draws without repeating removal. Hex Parasite tests cover paid Phyrexian life, zero, expiry, borrowed Necrotic Ooze source identity, changed objects, and quantities greater than forty. Mutated Cultist stores the scalar reduction in the existing next-spell grant, which survives its source and expires normally; the first following spell consumes it.

Verification also covers mixed player kinds, speed exclusion, target union legality and hexproof, native Protean Hydra removal triggers, save/replay, and a fresh-process resume in the second kind's quantity choice.
