# Original echo payer and current Shah controller

Pinned CR2026-09-25, data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt:

- 702.30a: Echo [cost] means “At the beginning of your upkeep, if this permanent came under your control since the beginning of your last upkeep, sacrifice it unless you pay [cost].”
- 113.8: A triggered ability on the stack is controlled by the player who controlled its source when it triggered.
- 118.12a: “[Do something] unless [a player does something else]” means “[A player may do something else]. If [that player doesn’t], [do something].”
- 701.21a: A player cannot sacrifice a permanent they do not control.

The original echo controller can choose the optional original payment after control changes; inability to sacrifice only prevents the unpaid consequence. The historical came-under-control condition is not undone by a later control change. Goblin’s zero alternative still applies only to permanents currently controlled by the payer. The echo-paid receipt binds the original permanent OID and original payer. Current Shah watches its own paid event and its current controller controls the newly triggered draw ability.

Focused native5 gates cover original pay and decline after Shah moves to p2, original nonmana echo discard paid by p1 after Deepcavern Imp moves to p2, source departure with optional original zero payment and no false departed-source trigger, and genuine cold save retaining p1 as original echo payer while the resulting Shah draw trigger belongs to p2 (p1 and p3 choose/draw). Existing original echo4 related gates re-pass. Controller-change battlefield zone expectations were corrected from p1:battlefield to the native p2:battlefield; actual payment/controller behavior already passed those assertions.
