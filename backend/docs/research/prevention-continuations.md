# Immediate prevention effects

Native damage commits once, then runs its immediate prevention bodies through the ordinary effect runner. A typed saved queue owns any paused body, remaining riders and the original damage caller's terminal. Synchronous completion returns to the caller without firing that terminal. Resumed completion invokes it once. Effects preserve joined instructions and result bindings; combat preserves its postdamage triggers; mana payment preserves the remaining mana riders and original payment stage.

Replacement planning produces pure prevention receipts. Only committed damage publishes `damage_prevented` events; a later redirect split cannot duplicate an earlier receipt. Actual prevention counts exclude unpreventable damage. Original source and recipient identities are retained separately from the new damage source of an additional effect.

Protection and shield counters are native damage-prevention candidates, so affected players choose their order with multipliers and other replacements. Targeting and blocking protection rules retain their existing paths. A shield counter's additional removal still occurs when damage cannot be prevented, and commits once for the simultaneous batch immediately after damage, before state-based actions. Pure previews and discarded plans consume no counters.

An opt-in external optional replacement separates the affected player's replacement-order choice from the printed controller's subsequent acceptance. Existing optional replacement defaults are unchanged.

These foundations alone do not admit new card wording. Cross-recipient finite budgets, delegated announcement targets and state-trigger loops remain separate review gates. The bound prevention reflexive outcomes below use the normal pending-trigger path. New card hooks require canonical full-effect and cold-resume proofs.

## Bound outcome adapters (batch 40)

The exact Oracle adapters in `prevention_outcomes.py` now distinguish immediate additional effects from genuine pending triggers. Comeuppance, Hallow, Brace for Impact, Channel Harm and finite Archon/Acolyte riders run before the original instruction resumes. Their original targets are frozen on resolution; later damage still uses native protection and exact object identity. Hallow includes the permanent-spell transition alias. Additional damage reads the original spell's stack LKI, rather than the original incoming damage source.

Phyrexian Vindicator and New Way Forward enqueue reflexive triggers; Samite Ministration and Judgment of Alexander enqueue the delayed triggers installed by their prevention records. Targets for Vindicator are chosen through the ordinary trigger stack path. Selfless Squire listens to committed positive prevention events from every prevention effect and coalesces the simultaneous batch. The generic trigger amount eligibility explicitly recognizes these positive receipt facts.

Acolyte's Reward, Vengeful Archon, Scars of the Veteran and Sacred Boon opt into finite prevention over the existing single-recipient allocation frontier. The pool persists across occurrences, supports arbitrary integer splits between sources, and is consumed only by actual prevention. Scars and Sacred Boon accumulate actual prevented amounts into an exact-object next-end-step delayed counter instruction. Scars' printed white-card exile alternative cost uses the existing native casting path.

Fifteen whole-card candidates are admitted: Comeuppance, Phyrexian Vindicator, Selfless Squire, New Way Forward, Judgment of Alexander, Hallow, Acolyte's Reward, Channel Harm, Vengeful Archon, Brace for Impact, Scars of the Veteran, Samite Ministration, Shadowbane, Sacred Boon and Blood of the Martyr. Coverage is paired with native positive scenarios, saved decisions, identity negatives and trigger/choice proofs; the suite also explicitly asserts that the independently unproved cards remain PARTIAL.

## Remaining separate foundations

Cover of Winter, Harm's Way, Shining Shoal, Divine Deflection and Refraction Trap remain gated on a cross-recipient shared-pool frontier. The current allocation profiler is keyed by candidate **and recipient**, and deliberately rejects a pool observed at more than one recipient. Its provisional per-packet allocation cannot serve as a cross-recipient frontier: later candidate capacities already depend on the provisional allocation.

For example, take two four-damage packets and pools A=3 and B=3. The first affected player orders A before B; the second orders B before A. Valid interior vectors include A=(1,2), B=(2,1), leaving one damage at each recipient. The capacity of B's first row depends on A's first row, while A's second row depends on B's second row. A global pool order or a greedy first-packet allocation removes valid affected-player choices. Representing this requires saved local candidate frontiers and cyclic capacity constraints, rather than extending the existing post-simulation profile validator. The single-recipient guard stays in force; no cross-recipient hook is admitted by this batch.

Nova Pentacle and Immortal Coil are admitted independently in batch 41 below; the five cross-recipient shared-pool cards remain PARTIAL.

## Nova delegated announcement (batch 41)

Nova Pentacle now opts into `delegated_target_announcements.py`. The original activator selects an opponent before costs; that opponent privately selects the actual creature target, using the original ability controller's targeting legality. The creature need not belong to the choosing opponent. No payment or tap occurs before these choices. The saved frame binds the original activator, source OID, ability index/text and original intent. Both announcement pauses resume through eagerly registered typed handlers.

Only the original activator can cancel. A departed or changed source, vanished target, newly illegal activation, or unaffordable automatic payment returns a cancellation-only decision to that activator. Delegating a target grants no mana-payment authority. Once selected, the ordinary typed activation payment frame retains the exact target reference, including when that creature is sacrificed for mana; the activating Nova remains reserved for its tap cost. At resolution only the damage-source choice remains, through native source shields. Afterward hexproof does not recheck targeting, and a new incarnation is not the original destination.

The cross-recipient budget proof modules remain isolated; see `cross-recipient-prevention-frontier.md`. Nova's announcement admission does not release those cards.


## Immortal Coil state loss and mandatory loop (batch 41)

`immortal_coil_outcomes.py` admits the exact prevention sentence and state-trigger sentence. The prevention rider chooses actual graveyard cards through native replacement-aware exile, capped by available cards while preserving the full prevented damage amount. The printed tap/exile-two activated draw ability uses ordinary native costs; its graveyard exiles finish before opponents receive priority.

The genuine 603.8 trigger is keyed by original source OID and ability index. It waits on the normal stack, retriggers after being countered if still empty, and has no intervening-if clause: a later graveyard card or source departure does not cancel an already-triggered loss. Its isolated primitive otherwise delegates the ordinary native loss implementation unchanged.

A mandatory draw is proved only when that exact pure state-trigger loss actually resolves after the ordinary response round: the original controller remains live and cannot lose; the same source OID/controller and exact current ability remain; the graveyard is still empty; no optional/manual body exists; and no other pending or stack instance of the same state key remains. The last guard prevents a copied trigger above an intervening Murder above the original from declaring a premature draw. The blocked pure loss necessarily recreates the identical mandatory state trigger before the game can progress. This uses native `draw_reason` with CR 104.4b and 732.4, without an iteration cap or changes to generic loss/state handling. CR 732.5 does not force players to cast an outside action to escape.

Native tests cover ordinary loss, blocked draw, counter/retrigger, real response breaks by removing Platinum Angel or adding a graveyard card, ability removal by a flashed Song of the Dryads, changed controller/source identity, copied-trigger ordering, prevent-all with sufficient/insufficient graveyard cards, unpreventable damage, the exact activation cost/draw, and genuinely fresh-process resumes at all three pauses. The production suite also checks whole-card FULL coverage.
