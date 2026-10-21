# Declared direct attack recipients

Firemane Commando official rulings, accessed 2026-10-19:
https://api.scryfall.com/cards/c86269cc-bf4d-44b4-ad4b-8356857c532f/rulings

The final ability examines every creature declared as an attacker. If any
attacked the ability's controller directly, the attacking player does not draw.
Attacking that player's planeswalker or a battle they protect does not attack
the player (CR 508.1, 508.5). Once triggered, subsequent changes to attacking
creatures are irrelevant. This is a resolution condition, not an intervening
if: the ability triggers on qualifying declarations even when a creature
attacked its controller, then the draw instruction checks the recorded event.

The existing aggregate you_attack event already records direct defending
players. TriggerEvent.attacked_players retains that declaration snapshot across
stack resolution, replay and save/load. The predicate reads the trigger's
captured controller, so changing control of Firemane does not change 'you'
(CR 603.3a, 113.8). 'Another player' uses an explicit other-player matcher,
including any teammate, rather than an opponent alias.
