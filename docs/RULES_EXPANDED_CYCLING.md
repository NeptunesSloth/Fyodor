# Cycling costs, searches, and cost changes

Street Wraith and Edge of Autumn use the ordinary activated-ability cost pipeline to pay
life or sacrifice a land and discard the cycling card (CR 702.29a, 602.2b). Nothing is paid
when the cost cannot be paid or cycling is prohibited. Exactly one cycling event is emitted,
and countering the ability does not refund its cost. Gavi's first-cycling alternative can
replace non-mana costs with {0}, and cycling with either cost consumes the turn's first cycle.

Sojourner's Companion's artifact landcycling searches for a card that has both card types.
The same typed-selector path handles ordinary typecycling. Non-mana cycling fees and
compound typecycling are recognized as Oracle keyword lines and available in the hand menu.

Fluctuator changes only cycling costs, including typecycling. It reduces generic mana,
keeps colored requirements, and combines with increases before payment. Suppression Field
is now supported too: non-mana activated abilities, including loyalty abilities, pay its
additional mana cost; mana abilities do not. Loyalty costs are paid only once the whole
activation can be paid. Its old refusal assertion was replaced by gameplay coverage.

Edge of Autumn's spell also reads the generic “you control N or fewer” condition when it
resolves. Its search is performed only when that condition holds.

Validation: 27 focused cases and 316 selected regressions pass (overlap), with replay and
save/load. Cases include both payment outcomes, Gavi, cycling restrictions, replacement
cost choices, cycle triggers, countered abilities, life-payment prohibitions, typed searches,
colored requirements, cost increases, and loyalty/mana abilities. All 84 frontend unit
tests and TypeScript/build passed; Ruff and mypy passed. Real Oracle fixtures are stored
in `backend/tests/fixtures/expanded_cycling_cards.json`.
