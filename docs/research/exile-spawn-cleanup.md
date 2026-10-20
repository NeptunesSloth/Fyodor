# Glimpse the Impossible

Canonical Oracle metadata is preserved in `backend/tests/fixtures/glimpse_impossible_cards.json`.
The implementation emits existing effect instructions: exile a bound batch, grant normal paid play until turn end, then create a delayed ability for the next end step of any player.

CR 400.7 makes a card that leaves exile and returns a different object. Both the permission and cleanup use exact object references. CR 603.4 checks whether eligible cards remain exiled when the delayed ability would trigger and again when it resolves. Trigger checks now restore the same captured references as resolution. Binding renaming also handles the reusable `live_ref_count` value.

The cleanup records actual moves into the controller's graveyard before counting Spawn. Rest in Peace and Leyline of the Void therefore produce zero Spawn; replacement of token creation uses the normal native pipeline. The token is a colorless 0/1 Eldrazi Spawn with its printed sacrifice ability, and it can produce mana immediately.

Gameplay tests exercise real casting and land play, reduced and empty libraries, exact references, both condition checks, actual graveyard and token replacements, opponent end steps, creation during an end step, source departure, replay, and JSON save/load. No new persistent callback stage is introduced.
