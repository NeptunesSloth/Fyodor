# Counter placement as an additional spell cost

Lethal Sting and Scarscale Ritual are production verified: 20 whole-card checks, including two fresh-process restores, plus 123 native cost regressions. The cost source passes mypy and owned tests pass Ruff. Canonical texts and all official source/support rulings were read. Evidence: `/tmp/counter70-cost-production-manifest.json`.

The exact shared printed cost now enters the existing native chosen-creature PUT_COUNTER payment path. Three parser lines reuse the established selector, prohibition checks, transaction validation, replacement processing, actual paying player, event receipts, and post-cost state actions. No payment, event, or casting implementation was replaced.

Checks prove payment before the spell body, atomic rejection without a legal controlled creature or under Solemnity, a 1/1 payer dying before resolution, Doubling Season not multiplying a cost, Counterspell retaining the paid cost, an illegal post-payment spell target using native fizzle, and actual Nest of Scarabs triggers even when the payer dies. Vizier of Remedies reducing the placement to zero still pays the cost and creates no fabricated counter event; Melira forbids the payment even with Vizier present. Both spells resume from paid pending stack objects in fresh processes.
