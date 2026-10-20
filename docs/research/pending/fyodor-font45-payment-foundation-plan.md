# Font of Agonies: authoritative life-payment foundation (review draft)

No production changes for Font. Existing Tablet and next-five45 manifests are immutable evidence.

## Canonical contract and authority

Canonical/all official rulings: `/tmp/fyodor-life45-root-{canonical,rulings}.json`, Font entries read completely. First ability is a TRIGGER, creates no permission to pay. Only an action using PAY life qualifies; choosing life LOSS or damage does not. Second ability is already parsed natively: `{1}{B}, Remove four blood counters: Destroy target creature`; whole-card proof still required.

Native CR source: `/workspace/Fyodor/data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt` (118.3b,118.10–13,119.4/8,601.2g–h,603.10). 118.11 permits modified payment actions without undoing paid-cost status, so nominal paid cost and actual life-loss amount need distinct receipts. Mana-ability activations occur in601.2g before the final601.2h total cost. Resolution costs in118.12 are separate chosen costs; root's Killing Wave needs one occurrence per chosen creature cost even when several payments and sacrifices commit simultaneously.

## Existing blockers

* `casting._pay` combines Phyrexian mana life with life costs of auto mana sources into one `life`; PaymentRecord.life includes upstream source costs. Neither aggregate is an authoritative payment-occurrence record.
* Direct fixed, X, half-life, morph, alternative/additional, optional-resolution, entry/shock, combat-attack and draw-toll drivers call generic `replace.lose_life`; that same function also serves ordinary loss and cannot infer intent.
* Ordinary pay triggers are not603.10 exceptions: POST-event objects/abilities/controller determine whether they trigger. Existing _fire_generic explicitly excludes a departed watcher at its hi batch for non-lookback events, so its simultaneous departure boundary already agrees. A frozen post-payment cohort is still proposed to preserve payment-time controller/abilities across delayed collection, instead of inferring those from the final board.
* Native replacement choices must not emit payment before the actual loss/payment finishes or emit twice after resume/cold. Failed/cancelled/declined payments emit none.
* Opening-hand native module supports reveal/exile/begin-on-battlefield, but no actual supported life-payment producer was found there. Initial life settings, Providence-style setting, mulligans and Chancellor loss are not payments. No speculative pregame event inference.

## Proposed typed contract (unimported prototype first)

`LifePaymentOccurrence`: stable operation+ordinal identity, payer, nominal amount, exact cost-source ObjectRef if one exists, and native cause/selected-cost-component identity. It is created from the ACTUAL original selected cost descriptor at its payment site, never `life_loss`, PaymentRecord.life, totals, display text or source-name guesses. Keep separate instances even with equal payer/amount or simultaneous batch.

`LifePaymentReceipt`: the occurrence plus frozen post-event triggered watcher snapshots (exact sourceOID, controller, actual derived ability text/index). An empty cohort is known empty. The event `life_paid` and nullable typed field on Event/TriggerEvent carry the receipt and the established actual payment amount. Preserve requested/nominal cost separately from performed life-loss results; which quantity Font reads under a loss multiplier is still an explicit semantic research gate, not decided by this prototype. Font only matches payer relative to its frozen controller. The resolving Font trigger uses the original source incarnation and the semantically established frozen paid amount; later life/control changes cannot rewrite it. An already queued pay trigger lacking authoritative receipt must use explicit manual resolution, not infer generic loss history.

Identity should reuse a frozen native life-operation ID plus ordinal; allocate once before possible616 pause, retain through the saved request, and commit once. Pure preview only changes its cloned plan. No read-time observer/initialization.

Commit APIs need TWO shapes:
1. Ordered individual payment: validate payable original component, perform its replacement-aware life action, then freeze post-event watcher cohort and emit exactly one committed payment receipt before later cost components/activations execute.
2. Simultaneous payment group supplied by a caller such as root Killing Wave: keep all distinct occurrences through one native planning union, finish all physical simultaneous life/sacrifice changes, THEN freeze the group's post-event watcher cohort and emit each separate occurrence in that same semantic group. Do not collapse per-payer totals into one occurrence.

Example: Confluence pay1 in601.2g, then sacrifice Font to Claws of Gix in601.2h: Font saw the earlier payment (trigger later does nothing after original Font departed). Animated Font sacrificed simultaneously with Killing Wave payments: departed Font sees none; surviving Fonts see each selected payment occurrence.

Exact trusted-action versus direct native emit integration remains to be reviewed with concrete prototype. Existing `emit` assigns next batch, so do not accidentally shift an earlier payment into a later physical group's meaning. A small server-only commit receipt step is preferable if needed for replay, event batch and cost-order fidelity; it must not alter life twice.

## Explicit producer audit matrix

PAY sites requiring authoritative typed occurrences:
- casting `_pay`: separate each original source activation cost from final Phyrexian cost, preserving sourceOID/ability index and original selected symbols.
- casting2534: nonmana morph life.
- casting3795/3799 and4953/4957: direct fixed and X additional/alternative life costs.
- casting5851: activated cost's fixed life.
- casting6179/6312: produced/manual mana source direct life costs.
- cost_payment1015: native dynamic half/commander-colors life components.
- optional_payment700: accepted resolution cost, distinct per original chosen cost, never decline.
- engine1107/1337 and replacements791: actual accepted entry/shock payment, per entering object and exact incarnation.
- combat516: preserve original attack-tax/payment components; `attack_life` aggregate is insufficient to identify separate chosen costs.
- drawn_toll99: explicit pay alternative.

NON-PAY drivers must stay unchanged: effects.lose_life, radiation, ordinary each_may loss, damage/lifelink, life-set/exchange, and manual table life edits. SOURCE_DAMAGE cost parts are damage, not payment of life. `RulesMana.life` in old recorded steps is legacy aggregate, not retroactively recoverable payment knowledge.

No changes to generic cost ordering/solver are authorized yet. The prototype must expose where current source/component ordering is insufficient, then propose the smallest native continuation preserving601.2g/h and selectable nonrandom cost order where Font observability differs. Do not admit Font on a subset of payment drivers.

## Unresolved semantics to settle before producer diff

* Successful cost versus performed payment:118.11 does not imply a PAY-LIFE event if the payment action itself is replaced (currently-PARTIAL Ashiok can exile instead). Preserve both requested cost and performed outcome rather than marking every successful cost as paid life. Also establish whether Font reads nominal amount or modified performed amount when an ordinary life-loss multiplier changes the payment action.

* Multiple life-paid Phyrexian symbols in the FINAL cost: separate2-life occurrences or a single final4-life occurrence? Source activations and separate118.12/Wave costs are unambiguously separate and must remain so.
* Paying0 life:119.4b permits it, but official Font rulings do not specify whether there is a pay trigger. Do not copy119.9's gain0 rule onto pay without justification.

These are research gates, not implicit timestamp/aggregate shortcuts.

## Native proof gates

Actual Font+Mana Confluence vs City of Brass/painland; direct Wall of Blood/Greed life cost; Gitaxian Probe and multiplePhyrexian; auto combined source+final payment; Blood Crypt through play and native reanimation entry; Zombie Cutthroat morph; Bolas's Citadel/alternative cost; accepted/declined resolution payment; attack tax; zero/half life; payer/opponent/control changes and source exactOID; prevention/prohibition/cancellation; payment modified by actual loss replacement with nominal counter amount; Font sacrifice before/after or simultaneous with payment; sourcewipe; counter-doubling/prohibition; actual four-counter remove/destroy legal/illegal target; pending616 no premature event; undo/history/privacy and genuine fresh-process snapshots.

Related native families: life-loss replacements/prohibitions, mana source provenance and nested input, special/morph payments, optional payment, entry choice continuations, casting/activation payments, combat taxes and root Wave group kernel once supplied. Production wiring and admission wait for explicit parent review of the shared producer diff and all complete gates.
