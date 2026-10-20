# Defending-player effects and attackers with no attack target

The twelve canonical cards in tests/fixtures/defender_relative36_cards.json use
one defending player's graveyard, hand count, optional payment/draw, or spell
restriction. The native attack event identifies the creature involved; an Aura's
controller and that attacking creature's controller may differ. Selecting targets
binds the appropriate player when the ability is put on the stack (603.3d).
Resolution-only instructions instead use that exact attacker's current association
or last known information (508.5, 608.2h).

Rules text source: Magic Comprehensive Rules effective September 25, 2026,
locally researched in /tmp/fyodor-gift-cr.txt. CR 506.4 removes an attacked
planeswalker/battle from combat when it leaves, phases, changes controller or
protector, or loses its required card type. Crucially, 506.4c keeps its attacking
creatures attacking, but attacking no player or permanent. Such a creature may be
blocked and can deal combat damage to its blockers; it deals no damage to a player
or permanent it is no longer attacking. Rule 508.5's last-defender fallback applies
when the creature itself is no longer attacking, not when it still attacks no
object.

CardInstance.is_attacking is the shared status check. A targetless designation
retains the former defending player solely for blocker declarations. Separate
last-association information records loss of the defender even if the creature
subsequently leaves combat. This distinguishes these two orders: removing the
creature first preserves its old defending player; removing its attack target
first leaves no defending player for its pending effect, even if the creature is
removed later. Snapshots preserve both facts and exact object identity. New object,
new attack declaration, and end-of-combat reset paths discard the appropriate
information. Legacy saves default to their previous ordinary attack behavior.

The designation is changed through recorded native actions or deterministic
handlers for zone/control/phasing changes. Battle protector/type changes emit an
opt-in attack action, preserving replay and fresh-process restoration. Generic
attackers, attack selectors, conditions, static rules, blocked/unblocked status,
regeneration, banding, and combat damage recognize the same status. No attack
requirement solver or cost/payment engine changes are involved.

Graveyard targets use the native defending-player selector binding. Unquenchable
Fury reads the defender's current public hand size. Animus of Night's Reach reads
that defender's current creature-card graveyard count. Optional payments use the
native persistent payment continuation; optional draws use its native named
chooser. Xantid Swarm creates a player-specific turn limit only after its trigger
resolves.

Chorale of the Void's official ruling expressly permits the entering creature to
attack ANY legal player, planeswalker, or battle, independently of the enchanted
creature's attack recipient. It enters attacking rather than being declared as an
attacker; native entering-attacker choices and restrictions remain in force.
Rakshasa Debaser's official rulings identify an attacked planeswalker's controller
as its defending player and confirm its returned creature cannot attack that
combat. Xantid Swarm's ruling allows the defending player to cast spells before the
trigger resolves and limits the restriction to that one player.

Drana, the Last Bloodchief remains outside this bounded promotion: its returned
creature must have the additional Vampire type as it enters (611.2e), rather than
receiving an ignored metadata field or a later-only type effect.
