# Wave 110G refused / deferred (researched, not promoted)

- Sacred Ground: "caused by a spell or ability" has no cause info on die events (SBA vs effect deaths indistinct); needs cause tracking.
- Psychogenic Probe, Widespread Panic: shuffle event does not tell spell/ability from a manual shuffle.
- Wormfang Drake, Wormfang Crab: old linked-LTB wording differs from "until" duration when the creature leaves before the ETB resolves (610.3); needs linked exile + LTB trigger.
- Tatsumasa, Gurzigost, Rock Jockey, Henry Wu, Spikeshell Harrier, Fugitive of the Judoon, Pure Intentions, Thijarian Witness: each needs a new primitive (return-from-exile on token death; put N gy cards on bottom as unless-cost; cast-this-turn static; exploited-creature power condition; speed reduction; token with ward + two-part exile cost; batch discard watch; "alone" LKI).
- Mindstorm Crown: "had no cards in hand at the beginning of this turn" needs a turn-start hand snapshot (engine.start_next_turn); an intervening-if rewrite rechecks at resolution (wrong with two Crowns).
- Nature's Wrath: "Island or blue permanent" is a subtype-or-color union, no selector form outside targets.
- Blade of the Swarm: "exiled card with warp" has no selector/record. Thought Prison: imprint link + "shares a color or mana value with the exiled card" cast condition missing.
