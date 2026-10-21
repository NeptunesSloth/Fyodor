# Great Train Heist

Current Oracle and official rulings (2024-04-12):
https://api.scryfall.com/cards/357dd9b2-5d2d-49f6-86f0-f5c4d63474dd/rulings

- The first mode untaps its controller's creatures in any phase. Only when it is that player's combat phase does it add another combat, without an intervening main phase. “Your combat phase” includes an additional combat, not just the first (CR 500.8).
- Spree pays for all chosen modes and resolves those modes in printed order. If the third mode's only target becomes illegal, none of the spell's chosen modes resolves (CR 608.2b).
- The second mode affects only creatures controlled as it resolves; later creatures do not receive its +1/+0 or first strike (CR 611.2c).
- The third mode's opponent is chosen while casting and becomes a fixed recipient of the delayed ability as the spell resolves (CR 603.7a/c). The watch checks creatures controlled when combat damage happens; each creature dealing combat damage to that opponent triggers separately. First strike and regular combat-damage steps are separate events. Noncombat damage and damage to another opponent do not trigger it.
- Copied spells retain modes but may change targets. Each copy must freeze its own opponent. A spell copy that ceases to exist still leaves its delayed ability active (CR 603.7d/e, 704.5e); the watch uses source last-known information with the creating controller retained.

Implementation reuses normal Spree costs, modes, damage facts, delayed watches, and token creation. The new typed recipient reference participates in target renumbering, is converted to player IDs at resolution, and is checked before a watch matches a damage fact. The ordinary turn cleanup removes the watch.
