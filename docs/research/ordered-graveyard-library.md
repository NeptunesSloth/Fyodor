# Ordering targeted graveyard cards in a library

Current Oracle data for Bow of Nylea and Misinformation was checked on 2026-10-19.
Misinformation's official rulings:
https://api.scryfall.com/cards/90a79cd5-d951-4ad7-a6a1-0cade4d0c189/rulings

The rulings say that the cards are targeted, the opponent is not, and the caster
does not have to show that opponent their order. This is an explicit choice in
the instruction (608.2d), overriding the default owner ordering in CR 401.4.
"An opponent's graveyard" restricts the targets to one graveyard even in multiplayer.

The intended grammar is deliberately limited to targeted cards from your graveyard
to your library, or from one opponent's graveyard to that player's library, with
an explicit "in any order" suffix. Existing to_library handling validates targets
again and offers a private order choice. Its default owner chooser is preserved;
the new descriptor explicitly requests the effect controller as chooser.

Bow additionally needs grouped targets in an activated modal ability. That is a
separate extension of the existing target-group announcement and saved-intent flow.
