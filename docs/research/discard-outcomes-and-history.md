# Discard outcomes, exact identities and original draws

Eighteen canonical cards share explicit discard-result or source-cost information:
Ill-Timed Explosion; Mog, Moogle Warrior; Rowdy Crew; Lumengrid Augur; Dream Salvage;
Shadow of the Grave; Aether Rift; Cait, Cage Brawler; Argentum Masticore; Mount Velus
Manticore; Wonderscape Sage; Knollspine Dragon; Forget; Hollow Marauder; Skullknocker
Ogre; Mila, Crafty Companion // Lukka, Wayward Bonder; Fa'adiyah Seer; and Sindbad.
Azra Oddsmaker belongs to the separate nontarget creature-choice family.

## Native composition and immutable values

`discard_outcomes.py` composes existing draw, discard, optional-payment, reflexive-trigger,
life-payment, return, counter and untap primitives. Private APNAP card selection and
simultaneous multiplayer discard remain native. Explicit `as` / `ref:` names preserve the
results through parser namespacing and saved continuations. Scalar damage and target
thresholds are captured before independent reflexive triggers are queued. The original
Argentum trigger has no target; its separate destruction trigger chooses a target only
after the player has discarded. A player can discard to keep Argentum with no legal
destruction target. Manticore counts card types, excluding supertypes and subtypes.

Rowdy Crew intersects two actual cards' card types and adds counters once. Mog checks
whether at least one creature and at least one noncreature were discarded, independently:
multiple qualifying cards do not multiply tokens or counters. Cait must actually discard
a card and may qualify by tying the greatest mana value. Hollow Marauder evaluates each
surviving targeted opponent independently, including an empty-handed opponent.

Knollspine uses native damage history for the chosen opponent and counts damage rather
than net life loss. Dream Salvage counts actual current-turn discards, including costs and
cycling. Forget draws only the number actually discarded. Aether Rift offers native life
payments in turn order and returns only the exact qualifying own-graveyard object.

## Exact public results and returned-land LKI

Optional `TurnFact.discarded_results` retains exact public discard results. Native
replacement-discard facts acquire their actual result without adding a second discard
count. An empty result list identifies a known hidden destination; `None` distinguishes
legacy facts. Shadow follows these exact objects, plus the explicitly allowed declined-
madness transition from CR 702.35c / 400.7k. A madness card that was cast and later died,
or a discarded card that left and returned to the graveyard, is a different incarnation.
It is never recovered by matching only a physical card ID. Ambiguous legacy identity
requests manual resolution instead of guessing.

Optional `PaymentRecord.returned_objects` records the original battlefield identities
returned as direct costs. Wonderscape reads the native LKI characteristics of that land,
including copy and everything-counter effects. A nonbasic land without a nonbasic LAND
TYPE still requires discarding. A land with Cave, Urza's, or another nonbasic land type
does not; basic land types alone do not qualify. Missing legacy receipts request explicit
manual handling. These additions do not change payment ordering or the mana solver.

## Draw and reveal; planeswalker attack qualifier

Seer/Sindbad take a private before-mark of native drawn object IDs, perform the native
draw, and act only on the exact original newly drawn card still in hand. CR 121.6c says
additional actions on a drawn card are not performed when the draw is replaced, including
replacement with another draw. Both native `drawn_replaced` and `drawn_counted` lineages
are excluded for this instruction. Enduring Renewal, Notion Thief, Alhammarret's Archive
and Quantum Riddler each have actual Oracle gameplay proofs. The replacement draw's
cards stay where its own effect put them; the Seer does not discard them. Normal land
and nonland draws are revealed and handled separately from preexisting hand cards.

Mila's front uses a distinct native `your_pw` defender qualifier. The existing attack
fact grouping supplies one event per defending player, so an opponent attacking two
planeswalkers the controller controls triggers once. Attacks only at the player or a
battle do not qualify. The loyalty instruction affects the currently controlled
planeswalkers as it resolves. The back-face discard/draw instruction uses the same
native result bindings and draws two for an actual creature discard.

## Sources and verification

Pinned Comprehensive Rules (2026-09-25): 121.2a, 121.6c, 400.7j–k, 508.3, 603.12,
608.2h, 701.9 and 702.35c. Official card rulings consulted include:

- [Argentum Masticore](https://scryfall.com/card/one/222/argentum-masticore): the second ability
  chooses its target later; discarding remains possible when it has no legal target.
- [Wonderscape Sage](https://scryfall.com/search?q=%21%22Wonderscape+Sage%22): battlefield LKI
  and nonbasic land TYPES, including Copy Land and Omo examples.
- [Shadow of the Grave](https://scryfall.com/card/akh/110/shadow-of-the-grave): cycling,
  discarded costs, declined madness and the cast-madness exclusion.
- [Sindbad](https://scryfall.com/search?q=%21Sindbad) and
  [Fa'adiyah Seer](https://scryfall.com/search?q=%21%22Fa%27adiyah+Seer%22): no additional action
  after a replaced draw, even a replacement which draws another card.

Canonical fixtures and gameplay are in `tests/fixtures/discard_outcomes_cards.json` and
`tests/test_rules_discard_outcomes.py`. They include positive effects for all eighteen,
both Mila faces, random discard traits, three-player choices, current-turn damage and
discard history, empty targets, no legal reflexive target, another player's life payment,
normal and replacement draws, exact madness lineage, and fresh-process continuations.

Verification completed: 58 distinct owned coverage/gameplay/boundary/cold cases, plus
104 existing reflexive, original-draw/reveal and graveyard-history regressions passed.
Four owned cases resume in a fresh Python process.
