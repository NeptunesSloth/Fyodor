# Creature damage and exact-source guards

Bind the Monster preserves the enchanted creature as the damage source, using
its current power and damaging the Aura controller. Cut Propulsion chooses
ordinary or doubled self-damage according to current flying and power, keeping
lifelink and other native damage characteristics. Wisecrack checks whether its
target is attacking and then damages that creature's controller with the spell.

Stalking Yeti checks its exact source incarnation when its entering ability
triggers and again when it resolves. Durkwood Tracker's activated ability checks
its source at resolution. If the source has left, neither damage instruction
happens. These abilities perform two sequential creature-source damage events,
using native source/target bindings and current/last-known power; they are not
compiled to the fight action.

Self-Destruct uses native with_next damage grouping for simultaneous damage
to the other target and the source creature, with distinct target groups.
Its lifelink produces one combined gain event, verified with Ajani's Pridemate.

All six use parser composition and native only_if, tap and damage effects.
Tests use canonical casts and declarations, actual response spells, source
removal, current power, flying, lifelink, multiplayer control and fresh-process
saved target selection, with replay and JSON state checks.
