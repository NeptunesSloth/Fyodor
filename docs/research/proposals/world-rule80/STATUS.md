# World duration foundation — held, not installed

No production rule, coverage promotion, or completed native gate is claimed here. Reserved owner: text71. Entry76's In the Eye of Chaos remains held until this global rule is proven.

## Authority

Pinned CR: data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt.

- 704.5k: if two or more permanents are World, all except the unique permanent that has been World for the shortest time go to their owners' graveyards. A tie for the shortest time sends **all Worlds**, including older ones, to the graveyard.
- 205.4b / 205.4f: World is an independent supertype; changing a card type must not erase it.
- 613.7m: simultaneous entry may assign different APNAP timestamps. These are not different World durations.
- 702.26b/d/f: phased objects are excluded from the rule; simple phasing retains identity/history; continuous effects can expire while phased out.

## Native defect evidence already supplied by entry76

/tmp/counter79-chaos-held-native-tests.py.proposed:
`test_chaos_world_rule_replaces_old_world_and_noninstant_does_not_trigger_tax`.
Both Worlds enter through actual p1 casts. Concordant Crossroads fails to remove In the Eye of Chaos. Last failure: /tmp/counter79-wizard-chaos10.log. No fabricated timestamps or source-receipt mutation.

Canonical sources: /tmp/counter79-upkeep-tax-canonical-rulings.json and /tmp/counter79-support-canonical.json.

## Proposed persisted authority

Use typed exact-object World-interval receipts and an independently incremented monotonic acquisition epoch, not OID order or ordinary timestamps. Each receipt needs physical-card identity, exact current object ID, interval start epoch (nullable for unknown legacy history), observation bound for unknown legacy history, actual native cause/event batch, and provenance. All genuine acquisitions in one atomic event share one epoch.

Before a native mutation, observe the complete current World set. After that mutation, remove intervals for genuine loss/zone departure and issue one epoch to the actual newly-World group. A same-object uninterrupted World interval survives another copy effect that remains World; gaining a new effect is not by itself a new World interval. Losing and regaining World starts a new interval.

Unknown legacy history is never assigned an invented ordinal. An unknown interval observed before a later proven native acquisition is provably older than that acquisition. Other uncertain comparisons require explicit manual table recovery before any simultaneous SBA is applied. The rule cannot silently pick a survivor or use the current controller to fabricate historical events.

## Exact mutation surface discovered

- Plan.do: native action handler + track commits the true zone-change batch and exact new OIDs. One Move with multiple card IDs is the entry group, despite per-object after-entry work and APNAP timestamps. Observe after track and before any derivation that might apply SBAs. Skip rules_sync to avoid replacing new metadata with an already materialized payload.
- layers.add_effect: appends genuine layer1/layer4 changes without Plan.do. A native multi-object become-copy currently creates one effect containing the whole affected group, so those gains must tie.
- layers.end_of_turn: direct removal of end-of-turn/end-of-combat effects, followed by delayed.end_of_next_turn. All simultaneous cleanup expirations need one outer acquisition group.
- delayed._end: direct expiry removal (next-turn/source lifetimes). Marker-removal Plan.do calls must not split this event into multiple World epochs.
- delayed._drop: modifies a per-object while-counter effect without Plan.do before removing markers; gains/losses need observation even if no marker exists.
- combat.end_combat: direct end-of-combat effect removal. One group.
- copying._drop_entering: replaces provisional entering-copy recipes. Off-battlefield provisional objects must not receive a World-permanent duration.
- layers.control_sync/prune: bookkeeping-only stale-effect removal must not reset an uninterrupted interval. `prune` currently omits phased OIDs, but no caller was found; do not call this a reproduced native phase bug.
- Manual table mutations between engine intents cannot be assumed native. Newly observed uncertain history needs explicit legacy/manual treatment.

An observer nesting depth on Plan can group nested marker actions inside a true atomic event. It must not group an entire resolving spell or whole engine intent: two sequential entry instructions are different intervals even if no player got priority between them. Native receipt bookkeeping must not trigger recursive derivation or alter unrelated source layers.

## Required admission gates

1. Actual Eye then Crossroads casts: old World goes to its owner's graveyard; different controllers/owners also work.
2. Actual simultaneous entry of two newer Worlds while an older World exists: **all three** die. Check shared event batch rather than relying on card ordering.
3. Entering copies, native multi-object become-copy, acquiring World after entry, and an already-World object receiving another World copy effect.
4. Actual loss/regain of World from copy expiry, including two simultaneous expired copy effects with distinct pre-existing effect timestamps.
5. Simple phase-out/in retains a World interval and excludes phased objects from SBA; actual expiry while phased does not leave a stale interval. Distinguish printed/copied/derived World; verify pinned rules before asserting the expiry boundary.
6. Native zone departure/return creates a new interval even if a physical card ID is reused.
7. True fresh-process restoration preserves native batch receipts, phase state, and relative ordering.
8. Legacy ambiguous histories hold explicitly before other simultaneous SBA; old unknown observed before a later native new World can be ranked without inventing an exact old timestamp.
9. World puts cards into graveyards: indestructible/regeneration do not prevent it; normal destination replacements still apply.
10. Existing exact source/copy/layers/SBA/death/replacement tests, scoped types/Ruff, native whole/negative gates, and performance against unrelated battlefield actions.

Isolated read-only baseline: /tmp/world-rule80-stage/backend, initial 830 app files, baseline-hashes.json. This stage predates subsequent root integrations; future patches must be rebased narrowly against live, never copied wholesale.

## Isolated prototype progress

An uninstalled draft now lives in /tmp/world-rule80-stage/backend. It adds WorldInterval80/world_epoch80/world_intervals80, app/rules/world_durations80.py, native Plan.do observation, atomic add/expiry hooks in layers/delayed/combat, and World deaths in sba.find. It is **not an integration candidate yet**.

Bounded actual native4 passed: Eye then Crossroads casts; Open the Vaults simultaneous two-owner World entry ties and removes older Eye too (actual shared event batch checked); Copy Enchantment actual entering-copy acquisition; unknown legacy single older World safely ranked older than later native entry. /tmp/world-rule80-native4.log.

First source check: scoped7 mypy passed; Ruff imports repaired in stage. Copy/phase/unknown-negative development gates remain active. The first uninterrupted-copy test expected a chooser when only one legal source existed; native engine correctly auto-selected it. This was a test assumption and is being corrected, not a World source repair.

Canonical support was read locally through CardRepository from /workspace/Fyodor/data/cards.sqlite; canonical-support.json preserves the normalized sources. A direct Scryfall request failed with HTTP400 and supplies no authority.

## Recovery and owned-only artifact

The prior `current-live-review.patch` was found to be a whole-stage diff that removed newer sibling integrations. It is archived as `superseded-unsafe-full-stage.patch` and MUST NOT be applied. The replacement `owned-world-only.patch` contains exactly eight World-owned files; its only removed lines are the old sba import/blank line. It preserves every current linked-exile, Dash, flashback-X, counter-payment and parser/permission change. `git apply --check` passed against current root source.

The new isolated `/tmp/world81-rebased/backend` starts from the current857-module source and adds only this World delta. Its configured Ruff8 passes. Rebased native14 plus core54 and types8 are running. The previous final68 log emitted68 passing dots before KeyboardInterrupt; it is not counted as a completed gate. The first recovery run against the older baseline was withdrawn after13 passing cases once the current-root rebase was authorized; it is also not an admission gate.

No-World 50-permanent/60-native-tap-action benchmark warm medians: baseline2.6259185s; cached candidate2.6330386s (~0.27% difference, within observed sample variation). Only potential World carriers are cached using exact copiable/object signatures; effective World membership is still derived after each native mutation.

## Final current-root gate closed

The immutable current-root-based World stage passes68 tests:14 World native/negative cases and54 engine/history/object/privacy cases, including two genuine fresh-process phasing/copy continuations. Scoped types8 and configured Ruff8 pass. Final evidence is `final-rebased68.log`, `final-rebased-types8.log`, `final-rebased-ruff8.log` and `manifest.json`. The exact owned eight-file source patch and base/candidate hashes are authoritative; no live integration, World card definition, coverage promotion or target increment is claimed. Root requested this foundation remain for the next snapshot.
