# Wandering Archaic / Explore the Vastlands

Implementation and verification notes. The canonical card now parses both faces fully; focused gameplay tests cover the branches below.

Canonical Oracle fixture: `backend/tests/fixtures/wandering_archaic_cards.json`. Scryfall printing `f3a98e14-1a13-4d0a-b227-9ba830ce3344`; official rulings fetched from its `/rulings` API endpoint into `/tmp/fyodor-wandering-archaic-rulings.json`.

## Front: optional payment followed by optional copy

The opponent must decide whether to pay two before the Archaic controller decides whether to copy. The copy resolves before the original spell. This is not a target of the triggered ability: the trigger references the exact spell object in its cast event.

Existing `optional_payment`, succeeded bindings, `only_if`, `copy_spell(event_spell)`, and `copy_new_targets` cover runtime behavior. The bounded grammar now lowers the payer's optional payment followed by a different player's optional copy and its new-target sentence. It offers payment before copying and keeps retargeting optional. Existing source-object references and copy last-known information handle the original spell leaving the stack.

## Back: staged APNAP library choices

Official ruling: “While resolving Explore the Vastlands, first the active player reveals the cards they are going to put into their hand. Then each other player in turn order does the same, knowing choices made before they choose.” Revealing either category is optional, and everyone gains three regardless of revealing cards.

Existing `look_top` deliberately has no combined `looked` context when several libraries are named. `scripts` refuses multi-player `pick_looked(by_owner)`. Simply iterating whole look/pick/rest bodies is incorrect: cards must be revealed in APNAP order before the subsequent hand/bottom instruction.

Implemented primitive: a per-player private library selection with a saved APNAP queue, per-player looked-card and selected-card maps, and two phases. During selection each player privately sees their top five and chooses zero to two different cards with at most one of each category (land; instant-or-sorcery), immediately revealing chosen cards to everyone. Later choosers can see earlier reveals. Only once all choices finish, move each player's chosen cards to that player's hand and the remainder to the bottom in a random order, then continue the ordinary gain-life effect. Skip departed players; limit short libraries; never expose unmatched private cards or hidden random order.

Reuse `looking.kinds_of` / `distinct_kinds` for category matching, ordinary reveal/move actions, and `bottom_at_random` for hidden remainder ordering. A combined instant/sorcery card fills one category, not two. One card cannot satisfy both categories as two chosen cards.

## Verification

Eighteen focused tests pass, including:

Front: pay prevents copying; decline and copy; decline copying; insufficient mana offers decline; mana abilities during payment; optional new targets; original spell leaves stack; changed controller and source leaves battlefield; replay/save during both decisions.

Back: all players privately look; APNAP changes when caster is not active player; earlier reveals visible to later chooser; hand/bottom moves deferred until everyone reveals; choose zero, land only, instant only, sorcery only, both; reject two lands or two instant/sorcery cards; reject another library's card; empty/short libraries; all players gain three; private remainder/random order; replay/save at each decision; putting cards into hand uses move actions, not draw actions.

The selected payment/copy regression suite passed 195 of 197 cases; its only failures were two older assertions expecting produced mana solely in the scalar pool after the shared mana-provenance update. The parent agent owns those assertions/display checks. No engine change was made for those failures.

## Spree alternative audit

Spree already has shared keyword parsing, modal costs, copy handling, and castability hints. In the fourth central inventory 19 of 22 Spree cards were FULL. The remaining three were Great Train Heist (combat-phase conditional and delayed damage/Treasure rider), One Last Job (attached Aura/Equipment reanimation), and Getaway Glamer (conditional greatest-power destruction). Implementing Spree infrastructure again would not address those effect gaps.
