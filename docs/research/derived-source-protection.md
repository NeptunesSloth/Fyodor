# Derived source qualities and selected spell halves

Six cards share the source-quality foundation: Rebbec, Architect of Ascension; Haktos the Unscarred; Lavabrink Venturer; Mirror Golem; Runed Halo; and Tam, Mindful First-Year. Their canonical data lives in tests/fixtures/source_quality_protection_cards.json, with native gameplay/replay/save-load tests in tests/test_rules_source_quality_protection.py.

Rebbec enumerates current mana values among artifacts its controller controls. Haktos uses the complement of its own chosen number, across every mana value; Lavabrink uses odd/even predicates with zero even. Missing own choices grant no protection. Mirror Golem resolves card types through its native exact-object imprint link; copies make independent links and a card that leaves exile stops contributing. Runed Halo uses native card-name matching, including selected split/adventure faces and fused names, to protect the source's current controller. Safe encoded name qualities avoid punctuation being mistaken for activated-ability syntax. Tam reuses live layer-five color expansion for hexproof from each recipient's own colors, restricted to other creatures its controller controls; this does not prevent damage or blocking.

## X and source views

Global/base mana_value excludes announced X. targets.source_of and damage-source views immutably add the actual or last-known spell X times the number of X symbols. Prospective targeting passes the actual announced x_value and selected face/fuse state through single targets, groups and modal slots. Aura/bestow and mutate resolution checks receive the actual stack X. Ordinary activation X never changes the permanent source's mana value.

Paid copies may choose X, while waived-cost copies must use zero. A paid preflight checks representative common X values at the live numeric-protection boundaries and parity classes rather than scanning a fixed0–40 range or accepting different X for different target groups. It respects the native action schema's capacity. The canonical test gives every player shroud, leaves Haktos as the only possible Blaze target, and proves a paid Tale of Tamiyo copy remains offered when zero-X has no legal target but its chosen nonzero X does.

## Finite random entering choices

Haktos's finite random number is sampled before entry by authoritative stack, effect-entry and token-entry runners. Read-only entry previews expose the required random metadata without consuming entropy. Native entering answers retain the sample across replacement/copy continuation; normal set_choice history records it for replay. This is not a die roll and Wyll/Pixie Guide do not modify it. A fresh Python process resumes Clone's entry choice, independently samples3 when the original Haktos chose2, resolves the legend rule, and reproduces the resulting state from recorded history. Entering under Humility makes no choice; ending ability loss does not invent one.

## Shared selected-half base correction

Real Wear testing exposed an existing shared bug: on-stack Plan.ch used the combined split-card base, so Wear cast as MV2 was later rechecked as MV3. stack_interaction's own mana-value predicates had the same error. A narrow immutable stack_faces projection now uses the authoritative StackEntry/StackMemory selected name, retains copy exceptions, and gives the actual half's base characteristics before later layers. Fused spells keep combined characteristics. X remains excluded, preserving every existing add-X contract. The same projection rebuilds exact stack LKI.

Split/adventure face records may omit colors. Such a half now derives missing colors from its own mana cost/color indicator rather than inheriting the aggregate card's colors. Explicit empty/nonempty colors, devoid and color CDAs remain authoritative. Native tests verify Spell Snare counters Wear at MV2, Negate counters Stomp as an instant, copied Wear remains red/MV2, exact departed Wear LKI retains its half, and fused Wear+Tear remains red-white/MV3.

Research Oracle/ruling snapshots: /tmp/derived-source-protection-{0..6}-{oracle,rulings}.json. Lord of the Nazgûl's additional Ring-bearer source-trait/snapshot work is deliberately separate and remains PARTIAL.
