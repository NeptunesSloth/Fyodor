# Cyclonus collateral promotion audit

Canonical Oracle and both faces are recorded in tests/fixtures/cyclonus_cards.json. The back-face combat trigger converts Cyclonus first, then creates an additional beginning phase only if that conversion succeeded. The front-face combat trigger instead connives and checks its power after the discard/counter process; becoming the back face does not retroactively generate its combat trigger.

The original extra-beginning primitive only accepted main phases. Actual converted Cyclonus dealt five combat damage and converted correctly, but silently failed to add its beginning phase. The primitive now normalizes the current combat step to the combat phase and uses the existing queue with main2 as its natural successor (CR 500.8). The queue is consumed after end of combat, so untap/upkeep/draw occur after the whole combat phase rather than immediately after damage. Existing queued phases remain in order.

Gameplay tests cover converted casting, living metal on the controller's turn, five combat damage, successful conversion and post-combat untap/upkeep/draw with Phyrexian Arena, connive's land/nonland discard and power thresholds, and failure to convert the original object after it leaves and returns. Paused discard decisions and queued phases round-trip save/load and replay.
