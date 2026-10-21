# Casting and land-play permissions from emblems

Emblems operate from their owner's command zone (CR 114). The existing static
permission scanner now includes genuine emblems for supported permission
definitions. Other static kinds still use their own supported source scans.
Emblem text validation accepts the same permission definitions that this scan
executes; normal controller, zone, type, payment and timing checks remain active.

This completes Wrenn and Realmbreaker's permanent-spell and land permission,
Wrenn and Six's retrace permission, and Jaya Ballard's instant/sorcery permission
with its graveyard-to-exile rider. Tamiyo, Field Researcher's free-hand-casting
emblem also becomes executable; her first loyalty ability is a separate rule.

Twelve canonical gameplay checks include actual ultimate costs and source
departure; paid graveyard casting; normal land limits; foreign graveyard and
nonpermanent exclusion; ordinary timing and mana requirements; a countered
permanent cast again as a new object; actual retrace land discard; Jaya's exile
rider on both successful resolution and Counterspell; Tamiyo's free hand cast
and exclusion of graveyard cards; JSON saves and history replay. These and 151
existing permission/retrace regressions pass together.
