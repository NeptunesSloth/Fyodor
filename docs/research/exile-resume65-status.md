# Resumed exile batch: production validation

Fourteen new whole-card candidates relative to checkpoint49 have adapter-free production proofs: Yorion, Sky Nomad; Nahiri's Resolve; Sudden Disappearance; Roll-Roll-Roll-Roll; Obzedat, Ghost Council; Legion's Initiative; Astral Drift; Morningtide's Light; Kaya, Ghost Assassin; Silver Surfer, Cosmic Voyager; Research // Development; Coax from the Blind Eternities; Magus of the Abyss; Cephalid Constable. These are pending the central catalog diff, not a new global total.

The ten blink cards pass 69 native cases, including actual source/target object-incarnation changes and fresh-process saves. Research // Development passes 13 native cases, including actual paid split-half casting, required empty-set shuffle under Commander 903.11, three sequential opponent-choice rounds, and native multiplayer departure recovery. Related delayed/companion/exile packet suites pass 126 cases. Eight leaf modules pass mypy and owned Ruff. Production tests contain no leaf registration adapters or cold subprocess bootstraps; the Surfer staged skip guard was removed.

Coax passes 6 focused cases including a fresh-process saved resolution choice, plus 17 existing outside-game/Karn regressions. The existing Karn exile-choice foundation accepts the literal Eldrazi alternative and retains the Commander prohibition against ordinary outside-game imports. Both creature Eldrazi and Kindred Eldrazi are eligible; foreign-owned, face-down and devoid non-Eldrazi cards are excluded. One source type check and owned Ruff pass. The new choice label has a backward-compatible default for old saved receipts.

Primary evidence: `/tmp/exile-resume65-admitted-manifest.json`, `/tmp/exile-resume65-admitted-expected.json`, `/tmp/exile-resume50-production-collected.log`, `/tmp/exile-resume50-blink-production.log`, `/tmp/exile-resume50-research-production-native.log`, `/tmp/exile-resume50-related.log`, `/tmp/exile-resume50-types.log`, `/tmp/exile-resume65-coax-production.log`, `/tmp/exile-resume65-coax-types.log`, `/tmp/exile-resume65-all-ruff.log`.

Magus of the Abyss passes 17 native whole/cold cases plus 19 existing player-relative cases in production. Its refreshed isolated copy/relative suite passes 52 cases; the unchanged 101-copy stress case is explicitly excluded and is not claimed passing. Two source modules pass mypy and owned Ruff passes. The chooser metadata changes only the decision player; legal target authority and stack controller remain the source controller. The Abyss remains held for the World rule; the proposed producer explicitly rejects World sources. No World automation completion is claimed. Cephalid Constable passes ten adapter-free native whole/cold cases and 25 existing where-X target-bound regressions in production. Its exact producer reuses existing event-amount target bounds and player-relative bindings, with no new targeting or damage kernel. One source module passes mypy and owned Ruff passes. Source departure, noncombat/prevented damage negatives, changed target controller/incarnation, actual 1/4 combat damage, foreign ownership and fresh-process target selection are covered. Fear of Burning Alive and Chandra's Incinerator remain isolated research candidates.

## Native fight/exile follow-on: four additional cards

Mawloc, Unnatural Aggression, Faunsbane Troll, and Burn from Within are now production verified, independently of the original fourteen-card manifest. Their exact producer delegates casting, targets, combat/fight damage, Ravenous, Aura sacrifice, and conditional damage receipts to existing native definitions, then binds the printed exile replacement to its named original object. Burn's existing actual-damage creature condition encloses both indestructible removal and the exile replacement. Named targets are filtered on admission, so a permanent that later stops being a creature retains its original-object replacement.

Proof: 17 native whole-card/negative/cold cases passed in `/tmp/exile-resume65-fight4-production.log`; 46 related replacement, regeneration, and fight cases passed in `/tmp/exile-resume65-fight4-related.log`; scoped source mypy and Ruff passed. An expanded import-following mypy run reported an unrelated conditional_counters argument, subsequently corrected by its owner. Tests include real Ravenous X=5/draw, optional-zero targets, paid Role sacrifice, source departure before fight, own fighter becoming illegal, zero/prevented Burn damage, same-turn Cloudshift successor exclusion, animated Factory becoming a noncreature land before destruction, and a fresh-process unresolved fight.

New-only manifest: `/tmp/exile-resume65-fight4-admitted-manifest.json`. Fiery Annihilation remains outside this manifest while its dependent Equipment target foundation undergoes native copying, attachment, legality, and cold continuation tests.

## Chandra's Incinerator

Production native12 whole/negative/cold proofs passed. The exact damage-recipient binding is opt-in metadata; the new cost history key counts actual noncombat damage to all opposing players, including departed opponents, without changing previous history meanings. Parent's frozen799 source mypy/Ruff and the exact39 catalog audit passed. The parent explicitly accepted those scoped proofs for admission while the already-running broader129 history/source regressions continue in the background; that run is **RUNNING, not PASS**, in `/tmp/exile-resume65-incinerator-related.log` (PID685845).

New-only manifest: `/tmp/exile-resume65-incinerator-admitted-manifest.json`. Fear of Burning Alive remains held: a real Bolt resolution produces an incorrect delirium trigger when the fourth graveyard type arrives after the damage event.

## Fiery Annihilation dependent targets

Fiery Annihilation now has a separate production admission after the dependent object foundation closed. Its later Equipment target binds to the earlier creature's original object identity, follows changed targets on a spell copy, and becomes ineffective when that earlier creature target is illegal. Metadata is used only by the exact producer. The earlier four-card manifest is unchanged.

Nine native whole/negative/cold proofs passed in `/tmp/exile-resume65-dependent-fiery-production.log`; 128 related player-relative, attachment/block-event, and target-copy cases passed in `/tmp/exile-resume65-dependent-related.log`; all three new leaves passed strict mypy and Ruff. Proof includes actual Magnetic Theft changing attachment, Blossoming Defense invalidating only the creature while Equipment remains attached, Cloudshift plus reattachment to the successor incarnation, actual Reverberate changing creature and Equipment targets together, and fresh-process continuation of that copy choice.

New-only manifest: `/tmp/exile-resume65-fiery-admitted-manifest.json`.

## Torch the Tower

The exact printed main/rider pair now delegates to native bargain payment, kicked gates, damage outcome receipts, scry continuation, and turn-long exile replacement. Nine unified production cases passed in `/tmp/exile-resume65-torch-production.log`, including an actually cast planeswalker with native starting loyalty, paid-bargain Reverberate copy, genuine fresh-process continuation during scry before lethal state-based actions, full prevention, later destruction, and blink successor exclusion. Six focused bargain/copy and damage replacement regressions passed; strict leaf types and Ruff passed. Damage outcome receipts track actual recipients after damage replacement, not the original spell target.

New-only manifest: `/tmp/exile-resume65-torch-admitted-manifest.json`.

The retained Incinerator broader history/source regression run subsequently completed **all129 cases PASS, exit0**, in `/tmp/exile-resume65-incinerator-related.log`. The existing new-only Incinerator manifest now records that completed result; the earlier running status remains above as the admission-time record.

## Kumano static replacement pair

Kumano's Blessing and Kumano Faces Kakkazan // Etching of Kumano are production verified. Their exact static replacement metadata reads actual current-turn damage facts by original recipient/source object. The controller of a damage source is frozen from its emitted damage event's actor, preserving the controller when damage happened instead of using later control state.

Sixteen unified native/cold cases passed in `/tmp/exile-resume65-static2-production.log`; three focused Aegar/exile regressions passed in `/tmp/exile-resume65-static-related3.log`; strict leaf mypy and Ruff passed. Native proofs include every Saga chapter and both faces, next-creature-only counter, actual haste attack, Flash on another player's turn, damage before the Aura entered, Aura departure, controlled versus opposing sources, simultaneous lethal damage including Etching itself, full prevention, original source/recipient blink successors (with actual Regrowth/recast), a focused native damage-event timing unit, and fresh-process damage-history continuation.

New-only manifest: `/tmp/exile-resume65-static2-admitted-manifest.json`. Runesword and Whippoorwill remain outside the admitted damage/exile group.


## Copy66: Chandra, Pyromaster and Mysterious Stranger

Both cards are production FULL after concrete source/ruling review. Native original-object and successful exile packets compose existing card-copy and immediate free-cast continuations. Chandra has all three loyalty abilities, a relative optional creature group, and 0–3 copies from only this ultimate’s packet. Stranger announces one required target for each qualifying graveyard and copies one native random successful exile only if at least two moved.

Production 37 whole/negative/cold tests and focused five regressions passed. Mypy passed three affected sources; Ruff passed owned leaf, shared scoped sources, and tests. Proof manifest: `/tmp/exile-resume66-admitted-manifest.json`. This is later than checkpoint53; no adapter or classifier-only admission. Cumulative owned closed cards:25.
