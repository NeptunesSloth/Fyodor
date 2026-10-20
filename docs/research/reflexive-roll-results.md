# Single die results in reflexive triggered abilities

Ancient Brass Dragon and Ancient Bronze Dragon roll as the original combat-damage trigger resolves. Their “When you do” instructions are separate reflexive triggered abilities (CR 603.12), put on the stack after resolution with their targets chosen at that time (603.3, 601.2c). Players may respond to and counter either ability independently. Countering the first prevents the roll; countering the reflexive ability does not undo it.

`reflexive_roll.parse` reads a mandatory single-roll instruction followed by an explicit “where X is the result” reflexive body. Both the roll and the inner body use the existing ordinary grammar. It rejects multiple/optional/chosen-result roll shapes, and unrelated event references in the body. The earlier support for ordinary dice instructions remains unchanged.

The reflexive instruction captures the completed roll's final result, after existing modifiers and ignored extra rolls (CR 706), as `TriggerEvent.amount`. It requires an actual completed nonempty roll context. Amount fields use `event_amount`; the existing `x_event` path supplies the same immutable value when targets are announced. This prevents a later response, source departure, controller change, or other roll from recomputing X.

Brass reuses the ordinary any-number graveyard target group with a total mana-value bound and return-under-your-control effect. Bronze reuses the ordinary up-to-two creature group and add-counters effect; counter replacements still apply normally. Zero targets remain legal. Targets are checked again on resolution, independently of the budget check when announced.

Canonical fixtures preserve current Oracle colors, identity, mana value, keywords, and text. Focused tests use actual combat damage and recorded rolls, including save/replay during target announcement and with the reflexive ability on the stack. Cases cover exact/excess budgets, zero and more-than-two targets across players' graveyards, partial illegal targets, source/controller changes, independently countering both abilities, Pixie Guide's ignored lowest roll, and Hardened Scales.

Official Scryfall rulings endpoints for Brass printing `536f7d4d-701b-4358-8a26-da1463a509aa` and Bronze printing `00c29e58-aafc-480c-9ad3-25a9b4bca8b5` were queried; both currently contain no rulings. The implementation follows the Oracle text and the cited Comprehensive Rules.
