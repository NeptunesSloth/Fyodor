# Direct hidden-card costs and discard outcomes

Canonical Oracle gameplay coverage: Soul Exchange, Phyrexian Devourer, Disaster Radius,
Nahiri's Wrath, Induce Despair, Stormscale Anarch, Curie, Emergent Intelligence,
Mishra's Command, Recall, Tamiyo Meets the Story Circle, Rites of Initiation,
Last Rites, Mind Roots, Creeping Dread, Captain Howler, Sea Scourge, and Pitchstone Wall.

## Direct payment facts

Optional typed `PaidCardFact` receipts supplement existing sacrifice and mana-source
receipts. They identify the exact result-zone incarnation, its zone, mana value,
colors, card types and subtypes. A reveal keeps its hand incarnation; a discard
reads its actual destination (including a replacement into exile). Native moves
refresh only matching paid objects about to leave, retaining their last expected-zone
characteristics. A later incarnation of the same physical card is never substituted.
Copies preserve the original direct paid-card facts. Missing legacy receipts request
explicit manual resolution; an actual zero-card payment records an empty list.

Original battlefield exile identities remain separate from result-zone facts. Curie
uses the original creature's battlefield copy recipe through native copy LKI, preserving
copy exceptions and excluding ordinary counters and noncopy modifications. Soul Exchange
checks the exiled creature's original Thrull type and places its counter only on the
actual returned battlefield creature. Devourer's library-exile cost now records both
old and result identities, and its power threshold uses the native state-trigger queue.
The threshold is a trigger condition, not a resolution recheck.

## Native resolution composition

The leaf composes native damage, pump, draw, discard, return, counters, copy and delayed
watch instructions. Explicit `as` and `ref:` bindings retain original discard outcomes
through namespacing and saved continuations. Nahiri applies the full summed value to
EACH selected target; damage is never divided. Recall and Mishra count actual discards.
Last Rites preserves the caster as the hand-choice player. Mind Roots offers only the
exact publicly followable land objects, without an invented graveyard restriction.
Creeping Dread discards simultaneously and compares card types separately for each
opponent. Rites chooses only a quantity before native random discard; it does not let
the player choose the cards. Howler's native delayed watch follows the target object
and keeps the original trigger controller. Pitchstone checks the exact discarded card
in its controller's graveyard after an actual optional sacrifice.

Curie's draw instruction reads base power, including native base-setting effects and
CDA values, while excluding counters and additive pumps. Departed source snapshots
retain base power; legacy snapshots without that field require manual resolution.

## Verification

`tests/test_rules_hidden_card_facts.py` and canonical metadata in
`tests/fixtures/hidden_card_facts_cards.json` cover all sixteen positive effects,
replay/JSON roundtrips, actual combat base-power draw, combined ward payment,
random-discard insufficient-payment atomicity, zero-card additional costs, optional
random quantity selection, simultaneous multiplayer discard, private hand choices,
and fresh-process paid-reveal and hand-choice continuations. The legacy receipt
case verifies a saved explicit manual fallback and completion. The final owned run
passed all 40 cases (including sixteen canonical FULL assertions).

Rules: CR 400.7, 608.2h, 701.9, 603.8, 707.2 and 707.10. The official Nahiri's Wrath
rulings specify result-zone mana values, the same total for each target, and preserving
cost choices on copies. Curie's official rulings specify the exiled creature's last
battlefield copiable values. Stormscale Anarch's official ruling forbids learning a
random discarded card before discovering that the mana cost cannot be paid.

## Declined madness follow-up correction

A further canonical Wall test exposed CR 702.35c / 400.7k: when the madness trigger
resolves first and its card is not cast, other instructions referring to the discarded
card can find the public object created by the madness decline. Ordinary exact exile
identity alone was insufficient. `MadnessFollowup` now records that one native transition,
including a pending 616 replacement choice. Only committed moves supply the public
result; private destinations supply none. The Wall uses an opt-in discarded-reference
lookup and its existing own-graveyard check. General target identity remains unchanged.

Four additional cases pass: declined madness returns Basking Rootwalla; accepting the
madness cast does not; Reclaim followed by Thought Scour creates a new graveyard
incarnation that is not returned; a fresh process resumes the saved decline mapping.
The correction changes no parser coverage classifications. Owned gameplay/coverage
cases total 44, with 101 existing activation/X/this-way regressions also passing.
