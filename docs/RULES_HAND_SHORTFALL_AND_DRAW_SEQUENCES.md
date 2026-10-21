# Hand shortfalls and replacement draw sequences

Rules source: Comprehensive Rules effective 2026-09-25, stored locally under
`data/rules/comprehensive_rules/2026-09-25/`.

## Rules question and authority

When are draw shortfalls measured, what counts as a discard, and how should a draw
sequence resume when a draw doubler produces multiple replacement instruction sequences?

- CR 402.3: hand sizes are public; no card identities are needed to compare them.
- CR 608.2h: determine the effect's required information once when it is applied.
- CR 121.2c: the active player completes their draws before the next player in turn order.
- CR 121.6b and 614.11a: complete a draw replacement before resuming the draw sequence.
- CR 614.5: a replacement cannot repeatedly apply to the same event or its modified events.
- CR 616.1e–g: choose the applicable replacement order and reconsider the modified events.
- CR 701.9: count the cards actually discarded, including a discard whose destination changes.

## Real Oracle examples and engine changes

`hand_shortfall.parse` recognizes complete shortfall instructions without card-name exceptions:

- Balance of Power draws the positive difference between target opponent's hand and yours,
  measured at resolution. A zero difference creates no draw events.
- Tales of the Ancestors captures every live player's hand size and shortfall before any
  draws. The existing draw runner receives a per-player count dictionary. Draw replacements
  affecting an earlier player cannot inflate a later player's shortfall.
- Skull Raid records its discard instruction using the existing `this_way` binding and draws
  the positive shortfall from actual discards. It does not infer discards from graveyard size.

The replacement tests exposed an existing bug: after a draw doubler generated multiple
replacement bodies, `do_draws` ran the first body and discarded its siblings. The draw planner
now stops after the first body or dredge, retaining unprocessed draw events and their applied
replacement IDs. The `draw_pending` continuation processes them against the updated game
state, then resumes the remaining original draws. This also rechecks hand-dependent effects
such as Blood Scrivener after earlier draws change the hand.

The continuation uses existing serialized resolution data. No new GameState model fields or
runtime card-text execution were introduced; old saves retain their existing continuations.

## Scenarios and fallback

Real Oracle fixtures exercise positive/equal/negative hand differences, empty hands, three-player
pods, a draw doubler changing the earlier player's resulting hand size, resolution-time hand
changes, foretell, private discard choices, and Obstinate Baloth replacing a discard destination.
Alhammarret's Archive plus Underrealm Lich verifies that every replacement body runs; Archive
plus Blood Scrivener verifies both replacement orders and fresh conditions on pending draws.
Replay and save/load checks include paused replacement instructions.

Unknown comparisons, mismatched discard/shortfall counts, and other shortfall instructions
remain unsupported. This batch does not complete all remaining partial cards.

23 focused scenarios and 286 selected regression tests passed (overlapping sets). Ruff and
mypy (347 source files) passed. The catalog comparison found exactly the three named
promotions and no lost FULL support: 27,625 FULL / 4,443 PARTIAL. See `CURRENT_STATE.md`.
