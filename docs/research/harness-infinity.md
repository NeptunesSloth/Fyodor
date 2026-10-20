# Harness and Infinity

Research source: stored Comprehensive Rules 2026-09-25, `data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt`, and the repository's actual Oracle database, checked 2026-10-19.

CR 701.64a: “Harness [this permanent]” means “If this permanent isn't harnessed, it becomes harnessed.”

CR 701.64b: Harnessed is a designation with no intrinsic rules meaning. Only permanents can have it; it lasts until the permanent leaves the battlefield. It is neither an ability nor part of copiable values.

CR 702.186a/b: `∞ — [Ability]` is a static ability meaning “As long as this permanent is harnessed, it has [ability].” This is a conditional ability grant, not an intervening-if condition appended to the underlying trigger. It is not linked to a particular activation under CR 607. A harnessed object that changes copiable values can use a different Infinity ability without becoming harnessed again. Copying a harnessed object does not copy its designation.

## Implementation scope

Use the existing public `CardInstance.choices` designation mechanism, already used for Solved: `Harnessed: Yes`. `game.ops` clears choices on zone changes. Control changes, phasing and changing copiable values retain the object and its choices. The layer table cache already keys the choices, so no schema or layer-cache additions are necessary.

A generic typed `harness` instruction resolves the source's exact object identity, checks it is still a permanent, and adds the designation only if absent. Costs still apply to a redundant activation. If the source left before resolution, or exiled itself as its own animated creature cost, it cannot become harnessed.

Recognize `∞ — [Ability]` in `statics.parse` and use the existing conditional self quoted-grant route with a checked granted ability. Add the `harnessed` designation condition to `static_conditions`; read the source's public choice only while it is on the battlefield. Existing layer-6 processing then controls ability loss and restoration, while generic trigger code supplies current-controller timing, target choices and normal resolution/LKI behavior. Do not flatten Infinity into an always-present triggered ability or suppress it solely when resolving.

Small hook scope: new harness module plus scripts/effects registrations; `statics.parse` wrapper recognition; `static_conditions` designation recognition/evaluation. Existing native mana, tap, exile-cost, reanimation and blink instructions are reused. No card-name runtime checks.

The Soul Stone's `{6}{B}, {T}, Exile a creature you control` cost and The Mind Stone's `{5}{W}, {T}` cost already parse fully. Both underlying Infinity trigger texts parse as supported granted abilities. The only current black-border Infinity keyword cards in the stored database are these two Stones. Infinity as an artifact subtype and infinity-valued mana on silver-border cards are separate concepts.

## Canonical fixture and gameplay validation plan

`backend/tests/fixtures/harness_infinity_cards.json` contains the two actual Stones and canonical supporting Oracle cards, including complete mana values, colors, color identities and keyword metadata.

Validate initially inactive triggers; native harness costs and choices including cancellation and insufficient mana; repeated harness activation; activated-ability counters and source departure; Mind Stone's optional zero target, other/nonland restrictions, stolen permanent returning to its owner, and normal ETB triggers; Soul Stone's exact graveyard target restrictions, Grafdigger's Cage and normal ETB behavior. Save/load and replay at costs, target selection and resolution.

Prove the static grant model through removal/restoration of abilities, phased status, control changes, copied versus retained designation, and Mirage Mirror changing between the two Stones after being harnessed. A triggered Infinity ability already on the stack survives later loss of the static source ability; an object without that static ability at the trigger event does not trigger. Harnessing after the relevant beginning-of-step event does not create a missed trigger.

Research and fixtures were prepared during the parent checkpoint freeze; implementation followed its release. Actual gameplay verifies the native costs and conditional grants, including mirrored copiable values, retained versus copied designation, control changes, phasing, source departure, ability loss/restoration, countered activations and trigger timing. Containment Priest's separate existing unsupported replacement was identified during edge research and is not claimed by this family.
