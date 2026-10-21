# Cross-recipient prevention card recipes

Status: VERIFIED at batch 43. The native joint bridge and all five exact producer recipes are registered. Adapter-free full-card/cost/cold checks passed 63 cases, final ownership/eligibility checks passed 33, and related native damage/616 checks passed 47. Central inventory confirmed exactly the intended promotions with no losses or unexpected changes (29,378 FULL / 2,690 PARTIAL); types 661 and core 108 passed.

| Card | Budget | Protected recipients | Result |
| --- | --- | --- | --- |
| Cover of Winter | Current age count, separately for each original creature source and fresh simultaneous combat-damage occurrence | You and creatures you control | Prevent allocated damage |
| Harm's Way | Next 2 damage from the chosen original source this turn | You and permanents you control | Redirect allocated damage to the announced target |
| Shining Shoal | Next announced X damage from the chosen original source this turn | You and creatures you control | Redirect allocated damage to the announced target |
| Divine Deflection | Next announced X damage this turn, shared across sources | You and permanents you control | Prevent allocated damage, then deal the actual prevented amount to the announced target |
| Refraction Trap | Next 3 damage from the chosen original source this turn | You and permanents you control | Prevent allocated damage, then deal the actual prevented amount to the announced target |

Targets are announced during casting. Source choices occur on resolution through the native source chooser, and source matches retain the original OID. A physical card's new incarnation is another source. Saved target refs preserve the original target's identity; immediate prevention bodies do not damage a replacement incarnation. Redirected damage retains its original source. Additional damage from Divine Deflection or Refraction Trap uses the prevention spell as its source. CR614.9's existing native destination checks remain intact; no same-recipient or source guard is widened.

Printed costs use production payment machinery. Cover's snow activation requires an actual snow mana receipt. Cumulative upkeep adds the age counter before requiring the full snow cost and sacrifices on decline. Shoal's exact alternate cost exiles a white hand card whose actual mana value equals the announced X, including zero and high values; hints derive feasible X from the hand. Refraction's alternate cost uses the native cast history for an opponent's red instant this turn. Mandatory taxes, additional costs, cancellation and cold payment state are owned by the existing payment continuations.

The native bridge accepts only its reviewed representable operation set and replays every accepted complete allocation through native applicability/application. Unsupported reachable interactions reject atomically. It does not omit candidates or fall back to packet-order spending. The exact card hooks cannot bypass those checks.

Evidence before exact producer admission includes actual simultaneous splits, distinct local Furnace orders, native affected/amount owners, unpreventable damage, changed source and target incarnations, redirected source identity, Cover trample and independent sources, and fresh-process effect/combat/payment continuations. Additional full-card cases check Cover first-strike versus regular occurrences and noncombat exclusion, planeswalker versus creature recipient scopes, Divine Deflection's shared budget across combat sources, and cold native records/body commits.

Official rulings were read in full from the cached Scryfall/Wizards canonical records for all five cards. Relevant current rules are CR614.5, CR614.9, CR615.5, CR615.7, CR616.1 and CR609.7. The exact recipe module is `prevention_frontier_cards.py`; final admission follows production verification.
