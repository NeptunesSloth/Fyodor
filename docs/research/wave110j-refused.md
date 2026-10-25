# Wave 110J refused

- Cannibalize: which creature is exiled is chosen on resolution among the legal targets; a fixed target order would guess the ruling for one illegal target.
- Arcum's Sleigh: "defending player controls a snow land" has no defending player outside an attack trigger in multiplayer (506.2); no ruling found.
- Ray of Frost: conditional "loses all abilities" static; layers (attached_types.wipe_key) read lose_all without its condition.
- Gaea's Liege: attacking/not attacking P/T from two Forest counts (no conditional CDA support); Crown of Convergence: color-sharing with top card.
- Corruption of Towashi: no "enters transformed" event.
- Jester's Mask: already "too large" in wave100-refused (hidden hand/library swap with a searching opponent library); not re-researched.
- Magnetic Web: forced-attack requirement for all magnet-counter creatures, set after attackers are declared; no foundation.
- Rasputin Dreamweaver: "started the turn untapped" has no turn-start snapshot and the untap-step ruling is unconfirmed; plus a counter cap.
- Livio, Oathsworn Sentinel: exiled-with-counter cards returned later (aegis); no exile-counter foundation.
- Simic Guildmage: Aura reattach to another permanent (303.4) not supported.
- Manor Gargoyle: "indestructible as long as it has defender" reads the source's own layer-6 keywords while deriving them (613.8 dependency), needs a keyword-aware static condition.
- Rumbling Ruin: selector compare has no "number of +1/+1 counters on creatures you control" right side, and the number must be fixed at resolution.
- Corruption of Towashi: no "enters transformed" event in the engine.
- Ray of Frost: promoted in s3 (line above is stale). The Oracle reads "As long as enchanted creature is red, it loses all abilities" with no colour change, so there is no self-reference; the colour is read in layer 5 before layer 6 (613.1e-f, 611.3a).
- Arcum's Sleigh: "defending player" outside combat events is undefined in multiplayer (no ruling found).
- Bone Shaman: "creatures dealt damage by this creature this turn can't be regenerated" needs a damage-linked regeneration shield.
- Jester's Mask: searching another player's library for a count tied to a hand move; no foundation.
- Simic Guildmage, Livio, Merseine, Rasputin, Crown of Convergence, Wiitigo: each needs a new foundation (see handoff_j).
