# References to bandmates

Icatian Skirmishers, Urza's Engine, Camel, and Battering Ram use the shared combat engine.

Skirmishers' triggered first-strike grant and the Engine's activated trample grant select
other creatures currently banded with their source. A source still on the battlefield uses
its current membership. If the source has left its expected zone, its last known snapshot
supplies the bandmates' object identities (CR 608.2h, 113.7a). A creature that left combat or
left and returned is excluded. `ObjectSnapshot.banded_with_ids` defaults empty for older
saved games; it stores object identities, rather than reusable card IDs.

Camel's prevention is a static replacement effect while Camel attacks. It prevents damage
from Desert lands to Camel and its bandmates, including damage from animated Deserts in
combat. It respects unpreventable damage and ends when Camel leaves. The source's last
known Desert subtype still identifies damage from its already-activated ability. The
mirrored official rulings are in `research/bandmate_references_rulings.json`.

Battering Ram's Wall trigger binds the actual opposing blocker and schedules its destruction
at end of combat. An effect that grants indestructible still applies. An isolated subtype
reference in a blocked/blocking trigger uses the same event binding as “that creature.”

The parser accepts source-bound bandmate references. It deliberately declines an unbound
“it” or a pronoun following an unrelated target instruction.

Validation: 32 focused gameplay/coverage scenarios pass, with replay and save/load checks.
They cover ordinary and expanded band blocks, source departure/return/removal from combat,
blinked bandmates, temporary grants, Desert abilities and combat, unpreventable damage,
and delayed Wall destruction with and without indestructible.
