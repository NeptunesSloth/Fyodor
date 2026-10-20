# Regenerations Restored: collateral validation

The exact canonical Oracle text has vanishing 12 and a single trigger for one or more time counters removed. That trigger scries once and gains one life, then conditionally exiles its own original object if it has no time counters. Successful exile creates a separate reflexive triggered ability granting an extra turn.

Current native parsing represents those operations distinctly: a counter-removal event, native scry/life gain, a current counter-count condition, native exile with a success binding, and a success-gated reflexive extra-turn trigger. No card-specific runtime code was added.

Removing the last time counters also triggers vanishing's sacrifice ability. Both trigger orders are tested explicitly. Resolving vanishing first sacrifices the enchantment; the other trigger still scries/gains, but cannot exile the departed object and grants no extra turn. Resolving the card's own trigger first exiles it and puts the reflexive trigger on the stack. The separate trigger can be countered by a real Stifle after exile; otherwise the scheduled extra turn is actually taken by the original controller. The eventual vanishing trigger cannot sacrifice a new object in exile.

Canonical gameplay/save/replay cases cover actual casting with twelve entry counters, removal of several counters by Timecrafting triggering once, both final-counter orders, real Stifle, ordinary upkeep vanishing, and unrelated counter kinds. A separate table-counter mutation while the real trigger is on the stack verifies that restoring a time counter prevents its conditional exile and the extra turn; this test intentionally does not claim Timecrafting can add a counter to a permanent with none, which its Oracle target restriction forbids.

Validation: eight canonical gameplay/save/replay cases passed; Ruff passed. Log: `/tmp/fyodor-regenerations-final.log`.
