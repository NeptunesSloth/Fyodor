# Conditional extra combat phases

Oracle cards: **Overpowering Attack** and **All-Out Assault**.

- CR 500.8: an added phase goes immediately after the specified phase; several added phases retain their specified sequence. An added combat followed by an added main phase precedes the phase that would naturally follow.
- CR 603.4: All-Out Assault's “if it's your main phase” is an intervening condition. It must hold when the enters ability would trigger and when it resolves. The delayed attack ability is part of that conditional ability.
- CR 603.7a–b: “When you next attack this turn” creates a delayed triggered ability during resolution. It triggers once, on a later declaration of attackers by the creating ability's controller, and expires that turn. Merely putting a creature onto the battlefield attacking is not declaring attackers (CR 508.4).
- CR 603.7d–e: the delayed ability keeps its creating controller and source identity. Removing All-Out Assault after creating it does not cancel the delayed untap.
- Overpowering Attack untaps only creatures currently controlled by its controller that were declared as attackers this turn. That instruction happens even outside that player's main phase; only the added phases are conditional.

The existing combat queue, attacked-this-turn object history, `you_attack` event, and one-use delayed watch cover the behavior. The bounded grammar changes must preserve the printed condition and both added phases, support controller-qualified attack-history selectors, and create the delayed untap with a live selector rather than capturing the current creatures.

Official Overpowering Attack ruling (2024-07-05): once an Assassin or commander deals combat damage to a player, freerunning remains available for the rest of that turn even if that source leaves. Existing freerunning implementation remains in use.

- https://api.scryfall.com/cards/e4ad338e-88ee-4919-aec4-320071a7cfb5/rulings
- https://api.scryfall.com/cards/b74876d8-f6a6-4b47-b960-b01a331bab01/rulings (no card-specific rulings)
