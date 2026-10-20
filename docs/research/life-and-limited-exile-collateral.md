# Collateral exile-permission validation

The permission grammar added for Nashi also promotes two unrelated cards. Both use their canonical Oracle wording and metadata in `tests/fixtures/life_and_limited_exile_cards.json`, with real casting/combat-independent damage, saved replay and normal priority.

**Inside Information** is a sorcery costing {X}{B}{B}. It exiles the top X cards of target opponent's library and permits playing all those cards for the rest of the turn. It has no surveil instruction and no one-card limit. Each spell requires life equal to its mana value instead of its mana cost; a land costs no life. Gameplay verifies casting the actual spell, all three exiled cards being usable, opponent ownership and final zones, public exile identities, X=0, rejecting one's own library as a target, and end-of-turn expiry while unused cards remain exiled.

**Unlucky Witness** triggers when it dies, exiles two cards from its controller's library, and allows one shared land-or-spell play until that player's next end step. It does not give a free spell or life alternative. Tests kill it with actual Shock damage, check the pending trigger's original source object after the creature is in the graveyard, then verify both land-first and mana-paid-spell-first consumption of the same group.

Expiry is tested at the beginning of the current turn's own end step, after a death during an already-running own end step, and across intervening opponents' end steps. An actual Sphinx of the Second Sun adds a beginning phase after the postcombat main phase; Witness dies during that additional upkeep and its permission expires at the subsequently restored end step. No hypothetical direct extra-end-step card is invented for this test.

All eleven collateral tests pass without further engine changes. This confirms that the two additional inventory promotions are supported by actual gameplay, not merely by matching a grammar expression.
