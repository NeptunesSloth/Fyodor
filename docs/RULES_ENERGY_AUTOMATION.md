# Energy replacement and payment history

This first local batch implements a reusable part of the remaining card automation. Subsequent additions and the current catalog totals are documented in [RULES_WORDING_AUTOMATION.md](RULES_WORDING_AUTOMATION.md). All Commander card rules are not yet automated.

## Rules question and authority

How should energy-specific replacement effects compose with generic counter replacements, and how does a later ability count energy paid or lost?

Comprehensive Rules effective 2026-09-25:

- 107.14: each {E} represents one energy counter; paying it removes one counter.
- 614.5: each replacement gets one opportunity to modify an event.
- 616.1: the affected player chooses which applicable replacement to apply first.
- 608.2i: effects can refer to events that happened earlier in the game.

## Oracle examples

The unabridged local Oracle text is captured in `backend/tests/fixtures/energy_replacements_cards.json`.

- Izzet Generatorium increases its controller's energy receipts by one and restricts its draw activation to turns when that player has paid or lost at least four energy.
- Aether Refinery doubles its controller's energy receipts, then offers its activation's payment and creates the correctly sized token when paid.
- Territorial Aetherkite gets energy, then creates a separate damage trigger if its optional payment is made (603.12).
- Localized Destruction protects only the controller's creatures with matching power; its destruction happens even when payment is declined.
- Wrath of the Skies compares mana values with energy actually paid, independently of the spell's cast X.
- Die Young's reduction and Aether Spike's controller payment scale with energy actually paid, including zero.
- Winding Constrictor increases generic player-counter receipts, so it can compose with the energy-specific doubler.

## Engine implementation

The existing `player_counters` replacement event now accepts energy-specific filters and multiplication. All ordering, one-application limits and decisions use the existing replacement planner. Other counter kinds and other players remain unaffected.

`TurnLog.energy_lost` records negative energy-counter events, including cost payments. It defaults to an empty mapping when loading old state. Conditions and numeric expressions can read the total paid or lost this turn; gains do not cancel earlier removals. The existing turn-log lifecycle resets the count each turn.

## Scenarios and remaining boundaries

Regression scenarios cover real Oracle text, the controller and opponent cases, poison isolation, both orders of doubling plus addition, generic-counter composition, activation thresholds, actual energy costs, turn boundaries, old-state defaults, replay, and serialized state round trips.

Only the exact supported replacement wordings are recognized. Unknown replacement operations stay unsupported. Resolution-time energy comparisons are bound within their own paragraph or mode and cannot restrict targets announced before payment. Aether Spike reuses its already-announced spell target. Ambiguous creature antecedents stay unsupported. The broader sticker/Attraction, banding, copy-casting, text-changing and other missing capabilities remain separate work.

Whole-pool measurement on the same local catalog: FULL 27,572 → 27,579; PARTIAL 4,496 → 4,489, of 32,068 Commander-legal cards. The coverage tool classifies supported behavior; the scenario tests validate this batch's semantics. This is not evidence of automation for every card or every interaction.
