# Spell keywords granted by emblems

Ral, Crackling Wit's ultimate draws three cards and creates an emblem granting
storm to its controller's instant and sorcery spells. The emblem operates from
the command zone independently of the planeswalker (CR 114). Each storm ability
triggers independently, including one already printed on the spell (CR 702.40).

The existing cast-keyword parser, controller/filter checks, storm count and spell
copy continuation already implement these rules. The static-source scan now
includes genuine command-zone emblems, restricted to the supported spell-keyword
static definitions. Its cache includes source zone, so moving or creating a
source cannot retain an obsolete battlefield-only scan. Emblem validation accepts
this supported definition.

Canonical gameplay tests cover the actual ultimate and zero-loyalty source
departure; artifact and creature spells count toward storm without gaining it;
printed plus granted storm; two independently created emblems; opponent isolation;
JSON/history replay; and loading a saved emblem in a fresh Python process.
