# Linked owner-return wording and heterogeneous targets

Parallax Wave, Parallax Tide, and Parallax Nexus now read their owner-return
sentences through the existing exact linked-card return framework. Battlefield
returns use each card's owner, including when the exiled permanent was stolen.
Gravegouger's “return … to … graveyard” wording uses the existing graveyard
destination instead of requiring the synonym “put … into”.

Parallax Nexus's chosen hand exile already uses the native private hand-choice
primitive. That primitive now preserves an optional `link` flag through both
automatic and saved choice paths and records only cards that reached exile.
Ordinary discard retains its existing default. The original resolving ability
context supplies its source incarnation even if the source changes controllers
or leaves before the hand choice resolves.

Angel of Serenity uses one target group with a maximum of three, whose selector
has two independent branches: other battlefield creatures, or creature cards in
graveyards. “Other” applies only to the battlefield branch. The ordinary target
and linked-exile engines handle partial illegality and subsequent return.

Canonical gameplay verifies all five cards, actual fading costs, multiple owners,
stolen permanents, separate source pools, early source departure, private hand
selection, native control theft, a fresh-process hand-choice continuation, and a
fresh-process Clone entry choice on return. Angel tests include mixed targets,
zero targets, illegal self-target on the battlefield, partial illegality, and an
actual Angel that dies to six Dread of Night effects before trigger targeting:
its own graveyard card remains a legal target. Gravegouger retains the native
single-graveyard restriction.
