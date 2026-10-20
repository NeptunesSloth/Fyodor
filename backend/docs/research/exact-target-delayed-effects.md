# Exact-target delayed triggers

The canonical fixtures are `tests/fixtures/bound_delayed35_cards.json` and
`tests/fixtures/attack_reveal_fight_cards.json`, sourced from `data/cards.sqlite`.
Rules references are the pinned 2026-09-25 Comprehensive Rules: 603.2c, 603.7b–e,
603.12, 608.2b/h and 701.14/701.21a.

The ten-card shared family is Niko Aris, Long River Lurker, Jaya, Fiery Negotiator,
Arcbond, Glyph of Life, Reincarnation, Time to Feed, Goblin Sappers, Dwarven Sea
Clan and Phantasmal Mount. Their existing supported abilities are retained.

`bound_delayed_effects` composes ordinary native effects with delayed event,
turn-watch and end-combat instructions. It adds no callback or custom payment
continuation. Native delayed creation preserves the original controller and
source, exact ObjectRefs, and context bindings. Fixed-object unions used by
Sappers bind both original objects before the end-combat trigger; dynamic
selector unions retain their previous behavior. Both creatures are destroyed
through one normal replacement-aware instruction.

Damage watches join simultaneous outgoing damage once per source object and
incoming damage once per recipient object, summing the actual damage facts after
prevention. A filtered source condition is checked before joining amounts.
Glyph of Life therefore counts damage by an attacking creature, including
noncombat damage from an attacking Prodigal Pyromancer; Shock does not qualify.
The original spell controller gains life even if an opponent owns the Wall.
Arcbond uses the damaged creature as the noncombat damage source, including its
last known information after lethal damage, and damages the other creatures and
players simultaneously through the native damage pipeline.

603.7c preserves an identified object when its characteristics or controller
change. Once an exact watch OID matches, the former subject's characteristic
selector is not reapplied; event, combat, defender and damage-source conditions
remain. The canonical counterexample uses Niko, Prodigal Pyromancer, Vedalken
Orrery and Song of the Dryads: the same object becomes a noncreature Forest
before its activated damage ability resolves and is still returned to hand.
A blinked replacement is a different object and does not inherit the watch.

Jaya counts the creatures currently attacking when each delayed trigger
resolves. Reincarnation selects a creature card when its delayed trigger
resolves, rather than targeting that graveyard card when the spell is cast.
The original spell controller chooses; the dead creature's owner receives the
returned creature. This distinction is explicitly confirmed by the WotC ruling
of 2009-10-01, which also permits choosing the dead creature's own card. Rest in
Peace prevents the dies event. Phantasmal Mount preserves both reciprocal exact
leave watches; native sacrifice legality protects a creature the delayed
ability's controller no longer controls. Its WotC ruling of 2008-10-01 confirms
that a later toughness increase does not end the effect.

## Hans Eriksson

Hans uses a separate `attack_reveal_fight` leaf. A normal reveal and conditional
native library-to-battlefield move precede a real reflexive trigger. A
noncreature goes to hand; a creature whose entry is prevented stays where the
native replacement leaves it and creates no reflexive fight.

The native attacking-entry chooser has an opt-in flag permitting the captured
defending player and that player's current planeswalkers. Ordinary player-only
consumers are unchanged. The native chooser and existing resume path handle the
choice during resolution, including a saved game restored in a fresh process.

After successful entry, both participants' original OIDs are fixed in a native
fight definition. The native trigger dispatcher receives REFLEXIVE origin and
the actual entry cause. The trigger can be responded to or countered separately
from Hans's attack trigger. An entry-suppression effect can suppress a trigger
caused by a creature entering; a creature card that enters as a noncreature
still creates Hans's reflexive trigger but cannot fight while it remains a
noncreature. A blink does not substitute the new object for either participant.

WotC Hans rulings dated 2020-11-10 explicitly confirm the separate reflexive
response window, the defending-player definition, and that neither participant
deals fight damage if either original object is absent or is no longer a
creature as that trigger resolves.

The owned gameplay tests exercise actual spells, activations, damage and combat,
with replay/JSON equality and fresh-process pending-choice restoration.
