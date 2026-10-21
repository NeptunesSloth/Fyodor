# Named combat history and player loss

Gollum, Obsessed Stalker uses every creature with that literal damage-time name, regardless of its controller or incarnation. The official June 16, 2023 rulings explicitly say that this is not limited to the particular Gollum whose end-step ability resolves. Native committed combat damage therefore carries the source's creature names into a persistent public player receipt. Prevented damage, noncombat damage and a creature whose name changed before damage do not add that receipt. The accumulated value is independent of the two-turn log and of any current Gollum. The end-step ability uses gross actual life gained this turn, rather than net life change.

Fresh games initialize complete named combat history. Legacy saves without that history retain an explicit unknown state; they never manufacture a negative result from current permanents or the short event log. An affected Gollum ability records a manual-resolution notice rather than silently claiming complete history.

Blood Tyrant's upkeep instruction uses actual committed life-loss receipts from the native replacement choke point. The receipt is bound before either a synchronous continuation or the saved replacement-order continuation advances. A prohibited loss contributes zero; changed losses contribute their actual final amounts. Counter addition remains a distinct native instruction with its own replacement handling.

CR 603.10f specifically requires player-loses-the-game abilities to look back. The three native departure paths (state-based loss, effect loss and concession) capture the same pre-loss battlefield cohort before any simultaneously losing player is marked as gone. Each actual loss emits one native event. Its collector restores that exact source/controller cohort and refuses stack triggers controlled by departed players (800.4d). A surviving controller may retain a trigger from a source owned by the departing player. A source's subsequent blink or control change does not replace the trigger's original source object.

Blood Tyrant's February 1, 2009 rulings explicitly include concession and every actual means of losing the game. Concession remains permitted despite effects that prevent losing (104.3a). The final player's immediate victory continues to end the game normally.

Canonical Oracle and official rulings were read from `/tmp/fyodor-life-history40-canonical.json` and `/tmp/fyodor-life-history40-rulings.json`; the current pinned comprehensive rules are `https://media.wizards.com/2026/downloads/MagicCompRules%2020260925.txt`.
