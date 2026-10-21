# Text-defined activation costs

Rules source: Comprehensive Rules effective 2026-09-25, stored locally.

## Rules question and authority

Who determines X when an activated ability defines it, including when a copied imprint
trigger exiles several cards?

- CR 107.3a and 107.3c: the player announces X only when the text does not define it.
  A text-defined X is determined by that definition; its value can change on the stack.
- CR 601.2b, 601.2f–h and 602.2b: determine the activation's value, calculate and lock
  its cost, then pay it. Cost reductions apply after substituting the determined X.
- CR 607.2a and 607.3: linked abilities refer to the cards their paired ability exiled.
  If multiple answers determine one variable, sum them. Creating copies of “the”
  exiled card creates one for each linked card.
- CR 400.7: a card that leaves exile is no longer the linked exiled object.

## Oracle examples and engine implications

`defined_activation_x` recognizes cost-only X defined by the mana value of the linked
exiled card or by a named kind of counter on the source. The effect grammar strips that
recognized definition and retains its declaration as metadata. The casting engine determines
X before activation costs and rejects conflicting client values. Availability hints use the
real determined cost and do not request a chosen X. Original `{X}` symbols are retained
for mana-spending restrictions; reductions apply after substitution.

- Prototype Portal and Soul Foundry use the linked card's mana value. Copied imprint
  triggers sum mana values and produce a copy of each linked card.
- Elite Arcanist pays the linked instant's mana value, then offers casting a copy normally
  through the existing copy/cast mechanism.
- Voodoo Doll pays X twice, where X is its pin counter count. Its damage instruction
  separately reads the current pin counter count at resolution.

Cost locking retains the determined activation value during payment continuations. No
GameState fields were added. Definitions that also use bare X within their effect remain
unsupported by this helper: those need a resolution-time value, not a frozen activation value.
Choosing an opponent or one of several candidate cards to determine X is also outside this
helper's scope.

## Scenarios and validation

19 focused scenarios passed, with replay and save/load checks. They cover zero/nonzero
mana values, incorrect client X, summed multiple imprint values, cards leaving exile before
or after activation, the source leaving, Elite Arcanist casting Lightning Bolt, cost reduction
by Zirda, spending Rosheen Meanderer's X-restricted mana, current counters versus paid cost,
and Voodoo Doll's upkeep/end-step abilities.

377 selected activation, cost, linked-copy, and mana-provenance regression tests passed
(overlaps the focused set). Ruff and mypy (348 source files) passed. The catalog comparison
found exactly the four named promotions and no lost FULL support: 27,629 FULL / 4,439 PARTIAL.
See `CURRENT_STATE.md`.
