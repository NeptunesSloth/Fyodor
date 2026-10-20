# Clockwork combat history and counter ceilings

Oracle checked against canonical Clockwork Steed, Beast, Avian and Swarm. The combat condition reads declarations in the current combat phase, by exact rules object. A creature removed from combat still attacked; crewing and entering attacking do not declare an attack. Earlier combats in the same turn do not qualify. Attacker history already stores its combat serial; blocker history now stores the equivalent serial with a backward-compatible empty default.

Wizards rulings, retrieved through Scryfall on 2026-10-20:

- [Clockwork Beast rulings](https://api.scryfall.com/cards/1a3bdfda-4269-45be-931d-ecfecbb389a8/rulings), 2007-09-16: “If Clockwork Beast has seven or fewer +1/+0 counters on it when its last ability resolves, it can wind up a maximum of seven such counters on it. If it has seven or more +1/+0 counters on it, the ability will have no effect.” The same ruling permits choosing fewer than X. Counters from other spells and abilities can exceed seven.
- Clockwork Steed, 2008-10-01: the corresponding maximum is four, and choosing fewer than X is allowed.

CR 101.2 gives the ability's prohibition precedence; CR 609.3 performs the possible portion. Counter replacement effects run through the native planner in the affected player's chosen order. The ceiling then limits only the final events for this ability's original object and named counter kind. It does not limit unrelated counters, other recipients, or entry counters. The actual resulting amount is what normal counter events and triggers see.

Recharge numbers are chosen during resolution using the native typed number choice. Saved choices and replacement-order answers retain the original effect descriptor, so resolving a replacement prompt does not ask for the number again. The effect remains restricted to the controller's upkeep. A fresh-process save/load test verifies handler registration and replay without importing test helpers.
