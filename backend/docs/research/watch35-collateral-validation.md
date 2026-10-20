# Paladin of Prahv and Seasinger

Batch35's generic bound outgoing-damage watches promote Paladin of Prahv's
forecast ability, while the current-controller-controls-a-basic-land selector
promotes Seasinger's control activation. Canonical database metadata is preserved
in tests/fixtures/watch35_collateral_cards.json; gameplay proofs live in
tests/test_rules_watch35_collateral.py.

Paladin's printed permanent trigger gains life for combat and noncombat damage.
Forecast functions from hand during its controller's upkeep, reveals as a cost,
and is usable only once each turn (702.57). Its delayed trigger watches the chosen
creature's exact object identity, independent of the forecast card remaining in
hand. Damage amounts come from the native damage event; this is not lifelink.
The saved native watch is tested in a fresh process before the watched creature
actually deals damage, including replay and JSON round trips.

Seasinger's target must have a controller who controls an Island both when the
activation is announced and when it resolves (608.2b). Changing target controller
to a player without an Island invalidates that target. After resolution, losing
that Island does not itself end control; the duration instead ends when Seasinger
untaps or its original activation controller stops controlling Seasinger (611.2b).
The native optional untap choice may keep the control effect across turns. Actual
Act of Aggression changes Seasinger's controller and ends the control effect.
Actual Boomerang returns its controller's only Island, causing Seasinger's state
trigger to sacrifice it; its control effect then ends. The state trigger uses the
ordinary stack and is not an immediate state-based action (603.8).
