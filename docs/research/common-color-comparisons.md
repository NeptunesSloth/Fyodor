# Current color-set comparisons

The shared native color-comparison layer implements Tsabo's Assassin, Barrin's Unmaking, Heroic Defiance, Jaded Response, and Call to Arms from canonical Oracle data.

A histogram counts one permanent in every color it has, across all applicable players. Colorless permanents contribute no color. The common-color comparison includes every color tied for the maximum; Call to Arms instead requires a unique strict maximum among the chosen player's nontoken permanents. An all-zero histogram has no unique maximum, so Call to Arms cannot grant its bonus in that state and triggers its sacrifice.

The query reads through type and color layers while suppressing later P/T statics with the existing thread-local derivation guard. This prevents Heroic Defiance's condition from recursively asking for its own P/T modification. Current layer-five color changes, including Painter's Servant, count. The Aura itself counts as a white permanent in the global histogram.

Tsabo's Assassin and Barrin's Unmaking permit their ordinary broad creature/permanent target when announced. The color condition is checked at resolution, then ordinary native destroy (with no regeneration) or bounce handles the result. Jaded Response likewise targets any spell and checks its current colors against creatures its controller currently controls only at resolution, as its official ruling specifies. A split card's actual selected spell face matters; a fused spell has the union of both halves' colors.

Call to Arms extends the existing entering-choice mechanism with two normal sequential questions, color then opponent. Both finish before entry, without priority between them. Its public color record and authoritative chosen-player object-ID namespace use the existing native storage, including duplicate player display names. Changing the enchantment's controller does not change the player it chose. A copied or blinked enchantment makes new independent choices.

The native CR603.8 state-trigger infrastructure supplies the sacrifice trigger. The static bonus stops immediately when the strict comparison becomes false. A waiting or stacked instance suppresses duplicate instances. Once triggered, sacrifice is not an intervening-if and does not recheck recovering counts. Countering the trigger while the state remains false lets a fresh trigger arise. A pending trigger from an old incarnation cannot sacrifice the blinked new object.

Canonical fixtures: tests/fixtures/common_color_comparison_cards.json. The 27 focused cases in tests/test_rules_common_color_comparisons.py cover native costs and conditional no-op, tied/multicolor/colorless counts, real regeneration prohibition, global/layer-five statics, resolution color and control changes, real split/fused spells, nontoken filtering, paired entering choices, state-trigger suppression/counter/retrigger, recovered conditions, old/new objects, independent copies, replay/save-load, and cold-process resumption between the entering choices. No new callback registration or persistent schema is introduced.

Research records: /tmp/common-color-next-canonical.json and /tmp/common-color-next-0-rulings.json through /tmp/common-color-next-4-rulings.json. Call to Arms's official rulings explicitly confirm multicolor counting, colorless exclusion, stable chosen player after controller changes, and CR603.8 trigger behavior.

Canonical sources:

- [Tsabo's Assassin](https://scryfall.com/card/inv/128/tsabos-assassin?utm_source=api); [official rulings feed](https://api.scryfall.com/cards/0047302d-4e3d-4327-9bb2-ecd5b00b00e3/rulings).
- [Barrin's Unmaking](https://scryfall.com/card/inv/46/barrins-unmaking?utm_source=api); [official rulings feed](https://api.scryfall.com/cards/4d4cecb0-12b5-4678-b5e7-8cec8fc86cef/rulings).
- [Heroic Defiance](https://scryfall.com/card/pls/6/heroic-defiance?utm_source=api); [official rulings feed](https://api.scryfall.com/cards/0dc1aa36-5d3b-4d25-9d54-937cdabf72a4/rulings).
- [Jaded Response](https://scryfall.com/card/apc/26/jaded-response?utm_source=api); [official rulings feed](https://api.scryfall.com/cards/6a9ab1f0-4e75-4165-85bc-6f838c221d6a/rulings).
- [Call to Arms](https://scryfall.com/card/me3/4/call-to-arms?utm_source=api); [official rulings feed](https://api.scryfall.com/cards/1a772cac-c853-4621-a61f-a9b06f2e2dec/rulings).
