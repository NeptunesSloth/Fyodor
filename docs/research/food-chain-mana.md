# Mana from exiling a creature as an activation cost

Food Chain's current Oracle text is saved in the canonical test fixture. Its selected EXILE cost uses the existing cost-choice/payment system; it is not a target, does not use the stack, and is never selected automatically by the mana payer.

The typed mana count `exiled_mv_plus_one` snapshots the selected creature's battlefield mana value before the cost is paid (CR 608.2h, 2026-09-25 rules). In particular, a Phantasmal Image copying Sun Titan yields seven mana, a face-down Sagu Mauler yields one, and a token copy preserves the copied mana cost. Reading the printing after exile would give incorrect answers. The existing paid-color continuation offers five homogeneous colored options after exile; a preselected color uses the same fixed amount.

Existing provenance-bearing mana units enforce the creature-spell spending restriction, including when activated inside an outer spell-payment prompt. Food Chain's official rulings (2011-09-22) expressly allow additional casting costs such as kicker and exclude costs imposed after the spell is initially cast. No new payment state or mana engine is introduced.

Canonical gameplay tests cover each color, rejected colorless, selected cost cancellation, tokens, copied and face-down characteristics, source self-exile under Opalescence, restricted spending, and nested payment. Histories replay and survive save/load, including pending choices.

Selected-cost mana abilities now preserve the pre-cost source object ID and the ability's spending/rider metadata across the paid-color choice. The shared `mana_units.from_context` reads source characteristics from the original object's LKI after departure. This also corrects an animated Ashnod's Altar sacrificing itself: its mana retains the original battlefield source and Artifact Creature traits rather than the new graveyard object. Existing mana-unit APIs and old saved continuations remain compatible.
