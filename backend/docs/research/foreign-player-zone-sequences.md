# Foreign-player zones: thirteen native sequences

Canonical cards: Quiet Speculation, Knowledge Exploitation, Suffer the Past, Elite Spellbinder, Spoils of Evil, Cruel Calculations, Drafna's Restoration, Grinning Totem, Nightmare Incursion, Agonizing Memories, Guiding Spirit, Haunting Echoes, You Find Some Prisoners. Complete canonical metadata is retained in foreign_player_zone_cards.json; original fetched records/rulings are in /tmp/foreign-player-zones-next-*.

The reusable leaf composes existing native searching, targeting, private-hand selection, library ordering, actual-movement references, casting, life, mana and permissions. A target zone's owner is independent of the searching/choosing controller. Existing foreign search completion now shuffles the library owner rather than accidentally shuffling the searcher.

Suffer's player and graveyard-card target groups retain independent resolution legality. Its actual-exile count produces one loss/gain event each; an illegal player target does not prevent legal cards being exiled or the controller gaining life (official ruling). Drafna uses the same player-relative target-group binding.

Knowledge Exploitation casts from the named opponent's library via the native effect-casting pipeline, then shuffles that opponent regardless of the optional cast. The free-cast source-zone guard accepts an explicitly referenced source-zone owner while existing callers default to the caster.

Elite Spellbinder uses a specific-object owner play permission with a generic cost increase. Stored Permission.generic_extra defaults to zero and forwards existing Grant.generic_extra payment support; native normal timing and MDFC land play remain intact. The grant outlives its source but not the exiled object.

Grinning Totem must find an unqualified card if possible. Its exact-object permission expires when its controller's next upkeep actually begins, including extra upkeeps; a native delayed trigger returns the exact still-unplayed object. Its duration differs from next-turn expiry and survives earlier cleanup/untap. Existing delayed step serial handling preserves additional same-turn upkeep semantics.

Quiet Speculation's flashback filter reads the card's actual ability text, not substring matching or untrusted metadata. Spoils counts artifact/creature union once. Cruel Calculations reads actual library-to-graveyard history even if a card later leaves. Guiding Spirit reads the current top graveyard card, rather than choosing any creature. Haunting uses rules names of actually exiled objects and permits qualified-search failure to find. Prisoners chooses one of actual exiled results and grants only that exact card's timed permission.

Canonical native casts/activations, private choices, independent target legality, actual taxed casting, MDFC land play, next-upkeep expiry/return, replay/JSON roundtrips and three fresh-process resumes are verified in test_rules_foreign_player_zones.py. No casting CPS changes or broad coverage-refusal removal were needed.
