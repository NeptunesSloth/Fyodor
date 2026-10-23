# Selected keyword costs65 — root review candidate

Exact two cards: Warbringer and Nahiri, Storm of Stone. Actual selected Dash receives generic reduction after native increases; colored costs remain payable. Nahiri composes native first strike during its controller’s turn with native equip-only pricing, retaining native loyalty target restrictions.

CR702.109a does not restrict Dash to hand. The narrow native Dash zone repair retains the existing casting-permission check and refuses selected required alternatives (flashback, foretell, escape, alt mana or life), plus explicitly refuses an alternative already selected. Native commander first cast and actual Bolt/removal/recast prove tax order; native Muldrotha grave permission works, no-permission grave cast and Underworld Breach escape substitution reject atomically. Incompatible own-hand flags evoke/face-down/awaken/alt-cost reject atomically.

Native22 distinct tests are closed: final22 run passed21 with only a cold fixture error (Equipment static index mistaken for activated equip); the corrected Nahiri cold rerun passed. Warbringer cold also independently passed in the cold2 run. Both use fresh subprocess loading saved native state/DB and actual cost/action, not warm replay. Related45 passed; scoped mypy4 and configured Ruff4+native test passed. Earlier fixture-index failures and stopped obsolete18 run are preserved honestly. No app change was needed to fix the cold fixture.

Root must install the owned-only four-file patch and run production checks/frozen admission before counting promotions. This stage does not alter cost_payment or shared counter-order work.
