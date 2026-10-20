# Activated modal target groups

Bow of Nylea's final mode chooses up to four target cards in its controller's graveyard, then puts the remaining legal cards on the bottom of that player's library in any order. This is a target group, rather than one target slot. Its other three modes retain their existing slot or untargeted behavior.

Under CR 602.2b, activating an ability follows the relevant casting steps: choose modes (601.2b), choose targets (601.2c), then determine and pay costs (601.2f–h). Choosing zero targets for an “up to” group is a valid activation that still pays its costs. Cancelling an unfinished announcement pays nothing. Target legality is checked again on resolution (608.2b).

`modal_abilities` now admits plain fixed-size groups for activated and loyalty modes. After mode selection, existing `casting.modal_groups`, `choose_targets`, and `modal_effects` join the chosen groups and renumber the effects. The existing saved activation intent and target-group resume handler carry the choices; the stack entry retains group specifications for resolution. Modes using ordinary single targets continue through the existing slot path.

Activated groups involving X, a total, division, or extra group metadata remain refused. Existing refusals for complex headers remain in place. Triggered groups keep their existing support for event-derived X and totals.

`test_rules_activated_modal_groups.py` covers canonical Bow of Nylea data, all modes, zero/one/four targets, private saved ordering, target legality before payment and on resolution, cancellation, and saved announcement replay. `test_rules_modal_abilities.py` retains an explicit activated X-group refusal case. Related modal, targeting, and cost suites exercise the shared pipeline.
