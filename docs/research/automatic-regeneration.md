# Automatic regeneration

Mossbridge Troll and both Holy Nimbus creatures regenerate immediately when their destruction would occur (CR 614.8), rather than allocating a shield for a later destruction. The existing regeneration action now supports this distinction without consuming an unrelated shield.

A typed, JSON-safe destruction preparation snapshots competing automatic regeneration, finite shield, shield-counter and umbra-armor replacements before any destruction mutation. Affected controllers select in APNAP order; effect and lethal-damage SBA decisions resume independently after save/load, including in a fresh process. Selections belong to the current destruction event and exact source incarnation, and are cleared after the batch. Existing nonautomatic regeneration paths retain their behavior.

Destruction that forbids regeneration excludes both regeneration alternatives but still permits armor/counters. Indestructibility prevents destruction before this preparation; zero toughness and sacrifice are not destruction. Simultaneously doomed armor remains applicable from the prepared snapshot, and already moved armor is not moved twice.

Canonical tests cover real Oracle coverage, repeated destruction, finite shields, shield counters, armor, indestructibility, zero toughness, Wrath of God, lethal-damage combat removal, simultaneous Planar Cleansing, native Nimbus suppression, APNAP choice ordering, deterministic replay, and cold effect/SBA continuations. Opponent-only activation and Troll signed-power tapping are independently tested by the Nimbus/Troll activation suite.
