# A departure that was not a sacrifice

Urza's Miter checks whether its triggering artifact was sacrificed, using the specific
object identity and simultaneous event batch. This distinguishes sacrifice (CR 701.21a)
from destruction, lethal damage, and other moves into a graveyard. Both sacrifice costs
and sacrifice effects emit the existing action event before the zone change.

`TriggerEvent.sacrificed` defaults to unknown for compatibility with old saved events.
A single battlefield departure captures a known true/false value. The intervening
condition checks this captured value when triggering and again during resolution
(CR 603.4). It does not inspect the artifact's current incarnation or a later action.
The grammar refuses the condition outside a single departure trigger.

Miter sees its own nonsacrificed death and each artifact dying with it, using last known
information (CR 603.10a). Sacrificing an artifact, returning it, and later destroying it
can produce the latter trigger. A graveyard replacement that exiles an artifact produces
no death trigger.

Gameplay tests cover payment/decline/unavailable mana, opposing artifacts, both kinds of
sacrifice, simultaneous deaths, returned cards, and graveyard replacement effects. They
verify deterministic replay and saved-state reload. Selected trigger, cost, and bandmate
regressions also pass.
