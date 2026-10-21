# Relative selectors and announced X costs

This extends the energy batch with reusable rules support. It does not complete the remaining Commander catalog.

Authority: Comprehensive Rules effective 2026-09-25, stored under `data/rules/comprehensive_rules/2026-09-25/`.

## One union of objects

CR 613.1f and 613.4c apply a keyword or power/toughness modifier once to each matching object. A relative selector such as “creatures you control that are Zombies and/or tokens” is a union. A Zombie token belongs to that union once. This supports On Wings of Gold, Glistening Deluge, and Take to the Streets. The parser also recognizes “an additional” before a power/toughness modification, supporting Fistful of Force. Unknown traits remain unsupported, and existing creature/Vehicle unions remain valid.

CR 115.1 and 115.2b distinguish spells from abilities. A list of spell types followed by an ability kind uses the existing stack-selector union. Spider-Sense accepts instant spells, sorcery spells, and triggered abilities, while rejecting creature spells and activated abilities.

## X announced during activation

CR 107.3a and 602.2b require announcing X in an activation cost before choosing targets and paying costs. This includes paying X energy, removing X counters, and tapping X artifacts. Coverage now recognizes these supported cost components, using the engine's existing announcement and payment implementation. HELIOS One, Chthonian Nightmare, Hourglass of the Lost, and Resonance Technician have real-card scenarios. X chosen during resolution cannot determine an earlier announced target.

## Energy cost determined during resolution

CR 107.14, 118.3, 118.12, and 608.2c require calculating the complete payment at the payment instruction, after preceding energy gains. Confiscation Coup and Jolted Awake reuse the existing concrete energy-cost/payment implementation. Declining or lacking sufficient energy leaves the dependent effect undone, without partial payment. Jolted Awake supports choosing zero targets; an announced target that becomes illegal causes the spell not to resolve (608.2b).

## Validation

Real Oracle text is retained in the new test fixtures. Scenarios cover controller changes, union deduplication, extra bonuses, clash wins and ties, zero X, source sacrifice/exile, unaffordable costs, invalid targets, optional payment decisions, replay, and serialized state round trips.

The real-card review suites now locate the installed database through application settings rather than a machine-specific path. The named-token copy regression selects the actual creature ID and asserts the result instead of conditionally skipping.

Whole-pool comparison: FULL 27,572 → 27,590; PARTIAL 4,496 → 4,478 of 32,068. No previously FULL card lost that classification. Real-card scenarios cover all eighteen promotions. This does not establish correct automation of every possible interaction.

Final validation: 612 affected tests passed with no skips on the integrated checkout; Ruff and mypy (345 source files) passed. The earlier energy checkpoint passed 15,921 tests with 56 skips. The full checkpoint preceded the relative-selector/X/stack-union additions; those additions were validated by the final affected suites.
