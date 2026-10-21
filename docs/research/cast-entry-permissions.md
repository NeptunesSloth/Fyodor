# Casting permissions with entry and additional-cost riders

Intrepid Paleontologist, Hundred-Battle Veteran, Worldheart Phoenix,
Osteomancer Adept, and Risen Executioner reuse the native permission and
casting payment pipelines.

The selected permission carries its entry descriptor to the original spell's
exact object identity. CR400.7h links the consequent to the card actually cast
through the permission. A spell copy does not inherit that descriptor merely
because alternative-cost decisions are copied under CR707.10. Canonical
Double Major tests cover both self graveyard permissions.

Intrepid uses the existing linked exile ledger, now recognizing the explicit
“cards you own” link wording. Ownership and Dinosaur creature filtering apply
before offering the permission. Its finality rider survives casting separately
from whether the source remains available for future casts.

Osteomancer stores a backward-compatible additional nonmana cost on its native
turn-limited Permission. Forage uses existing atomic Food/three-graveyard-card
choices and excludes the spell being cast. A fresh Python process resumes the
saved forage choice without test registration.

Risen's permission counts other creature cards, adds generic mana before native
cost reductions, and retains the prepared total through mana payment. The
Ashnod's Altar test puts a new creature into the graveyard during payment and
proves that this does not increase the already locked total. Hand casts and
other permissions do not receive this permission's surcharge.

Canonical tests cover ordinary hand casts, graveyard casts, copied spells,
Solemnity, wrong ownership/type, mandatory forage, both forage branches,
resolved permission source departure, replay, JSON and cold recovery.

Validation: 25 focused canonical cases and 141 related native permission/
linked-exile/optional-cost cases pass across the completed runs (166 distinct
cases). Scoped Ruff and diff checks pass.
