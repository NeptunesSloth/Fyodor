# Activated copies based on actual costs

Canonical scope: Ashnod the Uncaring; Verrak, Warped Sengir; Pit Automaton;
Dynaheir, Invoker Adept; Magus Lucea Kane. Oracle fixtures preserve printed
costs, colors, types and keywords. Official WotC rulings were checked through
Scryfall; in particular Pit/Dynaheir's updated nonmana exclusions and Magus's
shared next-spell-or-activation condition are applied.

Native activated abilities already carry payment records keyed by their own
stack object, separate from the permanent that produced them. The activation
trigger freezes actual mana, direct life, sacrificed-cost objects and whether
the original activation cost contains {X}. Trigger resolution reads those
facts even if the original ability has been countered. Copies spend no mana
and pay no life, and do not generate a fresh activation event.

Auxiliary life paid to mana sources is tracked on the payment receipt separately
from life paid for the final activation. Existing total-life accounting remains
unchanged. Greed paid with Mana Confluence pays 1 upstream plus 2 directly;
Verrak may ask for precisely 2 more, yielding life 35 and two Greed draws.
Life paid solely to make input mana does not qualify. Direct sacrifices likewise
come from the activation cost record, never mana sources sacrificed upstream.

Pit and Dynaheir create native once watches, with conditions respectively on
exhaust and at least four actual mana. Printed costs, reductions, life payments
and nonmana contributions are not substituted for actual mana. Magus creates
one native cast-or-activation watch as its mana ability resolves, without using
the stack. The first matching event consumes the shared watch. Spending its
particular CC is not required; {X} must occur in the actual mana/activation cost,
including X=0. Numeric X defined elsewhere is insufficient. Copies use native
LKI, retargeting, modes, X and payment-decision preservation.

Dynaheir's existing activation-as-haste static now recognizes the printed
'other' exclusion. It permits tapping other new creatures without granting
haste for attacking. All source/control, save, cleanup and once semantics use
the native static/watch machinery.

Validation: all 33 canonical cases pass across focused runs, including a fresh
Python process resuming a paused special-payment callback and checking replay
equality. The initial combined mechanics run passed 160 cases (five final
canonical cases plus155 existing payment/copy/watch/mana/counter regressions).
Late native CPS/cycling checks also uncovered and corrected two stale plain-pool
assertions in the existing cast-limits suite; mana now retains producer units.
Both corrected tests and the concurrently repaired Rite of Flame cases pass.
No inventory or individual mypy was run by this agent.

Cycling/transmute use their existing saved terminal callback to record actual
payment at the individual ability OID. Original cycling cost-X is captured
before alternatives, reductions and paid-X substitution; X survives the
ability stack entry. Actual Shark Typhoon X-cycling creates one Shark from the
original cycle event and draws twice from copied cycling. Decree of Justice
has X in its card mana cost, but fixed cycling, and correctly does not consume
Magus's watch. Dynaheir's tap legality check now reads plan.info where the
activation preflight intentionally omits generic cost checking; intrinsic
summoning sickness and its other-only exclusion remain enforced.
