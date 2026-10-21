# Cumulative mana-value exile

Actual Oracle text and complete characteristics come from `data/cards.sqlite` (`printings`, English entries), including Dream Harvest's hybrid mana cost and both faces of Valki.

Tasha's Hideous Laughter and Dream Harvest share an exile-until operation whose accumulator starts at zero for each opponent. Land cards and X outside the stack contribute zero; split cards contribute their combined mana value, and modal double-faced cards contribute their front face's mana value (CR 202.3, 202.3d–e; 712). Empty libraries finish without attempting to draw. An earlier card exiled by a different effect never contributes to this instruction's total.

The leaf performs the existing native exile-top operation in APNAP player order, recording the new original exile objects after every move (CR 400.7j). It measures actual face-up exiled characteristics, stops at the first threshold reached or the end of the library, and does not select targets. Tasha grants no subsequent casting permission.

Dream delegates to the existing exact-object `grant_play` primitive with a free alternative cost, cast-only permission, and end-of-turn duration. This is a lasting permission subject to ordinary casting timing, rather than an instruction to cast during resolution. Mandatory additional costs still apply, and X is zero when the free alternative cost is used (CR 118.9, 107.3b, 601.2). Owners remain unchanged; the spell's controller may cast either legal spell face. A land card does not become playable. Original-object permissions expire at cleanup and do not follow a card out of exile and back (CR 400.7, 514.2).

Improvisation Capstone has a related threshold scan, but its distinct paradigm mechanic is outside this implementation and remains honestly unclaimed.

Validation: `tests/test_rules_exile_mv_threshold.py` contains 16 canonical gameplay and coverage cases, including public exile, per-player totals, exact stopping points, split/MDFC/X values, empty and all-land libraries, libraries with over 100 zero-value cards, cross-owner free casting, ordinary timing and additional costs, source departure, stale object identity, cleanup expiry, and actual cold-process saved-state continuation. Every gameplay scenario checks replay/save equality.
