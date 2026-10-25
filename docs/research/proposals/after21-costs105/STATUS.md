# Ion Storm bounded counter-kind payment

Depends on costs104 source base. Two native source changes: CostComponent carries explicit permitted counter kinds; exact activation grammar reads Ion Storm’s +1/+1-or-charge counter removal cost; affordability, choice validation, and final payment enforce permitted kinds, ownership and actual removability through existing counter-token machinery. Other kinds cannot substitute, and counters on an opponent’s permanent cannot pay. No new classifier rules.

Global canonical PR21 PARTIAL now FULL. Native6 includes both permitted kinds, wrong-kind/wrong-controller atomic rejections, insufficient eligible counters, actual damage, and true cold selected-kind continuation. Initial native-first6 had2 pass and4 fixture mistakes: one kind on one permanent is natively auto-selected, so the corrected fixture provides both allowed kinds to require the choice. Runtime unchanged. Final combined gate and mypy2/Ruff3 recorded separately. No whole-suite claim.

Final clean gate: native-final6-related3.log10 PASS (6 owned incl1 true cold +4 related; log filename estimated3 related but actual4). Scoped mypy2 and configured Ruff3 PASS. All initial failures were fixture auto-choice assumptions; runtime unchanged.
