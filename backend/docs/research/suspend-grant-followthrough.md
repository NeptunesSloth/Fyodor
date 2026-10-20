# Exact-object suspend grants

Nine canonical cards share native exile-object bindings, optional payments, counter placement, and suspend capability: Taigam, Master Opportunist; Jhoira of the Ghitu; The Eleventh Doctor; The Parting of the Ways; Sinister Concierge; The Wedding of River Song; Ecstatic Beauty; Rory Williams; and Curse of the Cabal.

Each exile instruction binds the new object under a standard `ref:` namespace. Jhoira reads the activation's actual paid exile references. Sinister Concierge reads the death event's new graveyard object and preserves it across its optional choice. Moving either object away and returning the same physical card does not restore eligibility. The existing native counter pipeline performs placements, with mana values captured together before that placement.

Wedding performs the complete draw-two and optional exile sequence for each player, in order. Both players' exiled cards gain suspend after both sequences. A zero-mana-value card gains the capability with no counters and does not automatically get cast. Ecstatic Beauty only adds counters to cards that already have suspend. Rory's original cast-origin receipt prevents its suspend cast from triggering the non-exile cast ability again.

Curse's upkeep ability explicitly operates from exile and requires the original object still to be suspended at resolution. The generic step scanner accepts only definitions explicitly marked for that zone; ordinary permanent upkeep triggers remain inactive in exile.

Taigam uses the native spell-copy instruction without permission to choose new targets. It can copy the original spell's last known information after that original is countered, while the following exile only finds the original object still on the stack. A copied permanent spell resolves as one token regardless of token-creation doublers.

Wizards rulings dated 2025-04-04 for Taigam confirm the countered-original and copy-property cases; 2023-10-13 Wedding rulings confirm zero-counter grants and simultaneous time-travel changes. These rulings were retrieved from Scryfall's public rulings endpoint during implementation. The Face of Boe remains outside this family: its resolving cast uses the suspend alternative cost and requires a separate native paid-cast alternative.
