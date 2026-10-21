# Counter-payment quantities, source names, and mana activation limits

Rules source: Comprehensive Rules effective 2026-09-25, stored locally.

## Rules question and authority

How is a counter-removal quantity chosen, paid, and used later, and can the counters come
from a source that will also be sacrificed?

- CR 107.1c: “any number” permits positive numbers and zero.
- CR 601.2b, 601.2h, 602.2b: announce a variable activation cost, then pay the complete cost;
  nonrandom costs can be paid in any order, including removing counters before sacrificing.
- CR 118.3: an unpayable cost cannot be paid; “one or more” cannot be paid with zero.
- CR 608.2b and 608.2h: target legality is checked again and the amount paid remains the amount
  paid even when the source leaves or its counters change.
- CR 201.5 and 201.5c: a named self-reference, including a shortened legendary name, identifies
  the actual source.
- CR 605.3a–b and 702.177a: mana abilities obey activation restrictions and resolve without the
  stack; exhaust means “Activate only once.”
- CR 400.7: a source returning as a new object has independent activation-use history.

## Oracle examples and reusable implementation

Ant-Man and Geistflame Reservoir accept any number of counters, including zero. Ooze Flux
and Simic Manipulator require at least one; Flux can divide its payment among creatures,
and Manipulator's target uses the announced amount and must remain legal on resolution.
The amount travels through the existing X/payment machinery, with matched counter-kind
references rewritten to that value. Independent variable costs and unknown references stay manual.

Rasputin's named mana cost is normalized against its actual source name and uses existing
counted mana choices. Unrelated names are not accepted. This normalization also exposed
Loot's exhaust mana ability. Mana abilities now use the existing activation-restriction checker
and usage records; Loot pays green for three mana and each exhaust ability has its own limit.

The Filigree Sylex's ten-counter cost uses the common number vocabulary. Counter payments
may use the Sylex before the sacrifice part is paid. Existing counter selection and ordered
payment handle the removal and sacrifice; no new GameState fields were added.

## Edge cases and validation

30 focused scenarios passed, including all seven real-card coverage checks. Gameplay cases
check replay and save/load, zero payments, overpayment rejection without resource changes,
minimum-one hints, distributed payments, source departure, changing target power, Rasputin's
actual three-player ETB and mana choices, named-source validation, independent-variable
refusal, mismatched-counter refusal, Loot's limits and reset, and Sylex payments with zero,
some, or all counters on the source.

494 selected cost, mana, restriction, ordered-payment, borrowed-ability, and defined-X regression
tests passed (overlaps focused suite). Ruff, mypy (348 files), and whitespace checks passed.
An isolated pre-batch scan reproduced 27,644 FULL / 4,424 PARTIAL; the final catalog is
27,651 FULL / 4,417 PARTIAL, with exactly seven promotions and no lost FULL support.
