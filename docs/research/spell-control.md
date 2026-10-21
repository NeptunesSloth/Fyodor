# Spell-control family

Implemented using the existing spell, target-choice, and action representations. Commandeer, Aethersnatch, and Invert Polarity are supported; the exchange cards below remain a separate follow-on scope.

Commandeer and Aethersnatch need control of a stack spell followed by optional new targets. Invert Polarity uses the same operation in its winning-coin branch and an ordinary counter in its losing branch. Commandeer's exile-two-blue-cards alternative cost already parses; no new alternative-cost subsystem is needed.

## State changes

`SetController` accepts battlefield cards and actual spell cards on the stack, preserving zone, object identity, owner, X, choices, payment, and cast history. It sets both CardInstance.controller and an existing spell StackEntry.controller atomically. Do not accept activated/triggered ability placeholders through this spell-control path. Permanent spells often have no StackEntry and resolve using their CardInstance controller; instant/sorcery effects use the stored entry controller. Ownership still determines the final graveyard, exile or hand destination.

The separate typed `gain_control_spell` primitive handles spell control, independently of the permanent-only layer-2 synchronization (which intentionally scans battlefield objects). Gaining control does not cast the spell again, put it on the stack again, or change its position. The existing new-target chooser can handle ordinary spell entries once their controller is updated, and validates new targets for the spell's new controller.

## Aura and mutate targets

Aura/mutate spells often have no StackEntry. Their announced target is `RulesState.aura_targets`. Existing `stack_interaction.choose_new_targets` silently skips these, so simply reusing it would be incomplete.

A transient target-entry adapter uses the physical spell's controller, object id, current Aura enchant selector, and saved Aura target. This adapter is never installed as a real StackEntry: doing so would change permanent-spell resolution into effect-spell resolution. Retargeting updates `aura_targets`, arrows and target events. Bestow's current characteristics already include its Aura overlay.

For a mutating spell, bind the target's required owner to the spell's owner, independently of its new controller. Existing `merged.resolve` tests MUTATE_TARGET using controller, equivalent only before spell-control effects exist. Generic bound-player support in Selector.owner supplies an owner-bound mutate selector both in retargeting and resolution. Player/creature target shields must still use the spell's controller. A successful merge keeps the existing permanent's controller; the stolen mutating spell does not itself enter the battlefield. An illegal mutate target makes the spell resolve as an ordinary creature under its new controller.

## Follow-on exchange cards

Sudden Substitution and Perplexing Chimera can reuse spell control plus permanent control, but exchange must be atomic and happen only when both objects are still legal. Sudden Substitution lets the spell's new controller choose targets, who may differ from the effect controller. Perplexing Chimera's original ability controller chooses. The existing target chooser currently always uses context.controller, so this needs an explicit chooser binding rather than rewriting the whole resolving context's controller.

## Canonical verification matrix

Fixtures: `spell_control_cards.json` preserves Oracle metadata for the family, Aura/mutate cases, X and shields.

Primary cases: steal Lightning Bolt and keep/change targets; owner receives resolved instant in graveyard; new controller's hexproof permissions; targetless artifact/creature enters under new control; Aura target changes and keeps/loses legality under new controller; mutate retargeting stays with original owner and merged host keeps its controller; invalid mutate target enters normally under new controller; X/modes/kicker choices retained; gain control is not a cast event; Commandeer alternative cost selects exactly two blue cards privately and never the casting card; both recorded coin branches for Invert Polarity; missing/illegal original targets; counter the stealing spell; save/replay during target changes and before final resolution.

No changes to casting's shared cost/announcement refactor are required.

## Controller baseline after entry

A stolen permanent spell enters under its new controller, independently of its owner. Layer-2 synchronization now captures the controller before its first automatic control change, keyed by exact object id. When the last control effect ends, that controller is restored rather than the card owner. Phasing retains this baseline; a zone change discards it. Old saves without recorded baselines preserve the historical owner fallback. Actual Act of Treason and Zealous Conscripts exercise temporary control of a stolen creature and a stolen Aura respectively.
