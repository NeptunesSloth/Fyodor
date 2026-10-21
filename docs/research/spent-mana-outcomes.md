# Actual spent-mana outcomes

The bounded batch36 family uses the actual mana on the original spell's immutable payment record. It does not inspect the spell's mana cost or infer colors from spend-as-though permissions. There is no payment solver change.

The fifteen canonical cards are Batwing Brume, Mythos of Nethroi, Boros Fury-Shield, Torrent of Souls, Devour Intellect, Wumpus Aberration, Moonhold, Dawnglow Infusion, Mythos of Vadrok, Bladecoil Serpent, Invert the Skies, Cankerous Thirst, Flash Conscription, River's Grasp, and Unnerving Assault. The independent fixture includes full mana value, colors, keywords, and Oracle metadata. Canonical gameplay tests are in `backend/tests/test_rules_spent_mana_outcomes.py`.

## Rules and composition

CR601.2c-d chooses targets and any division before payment. A conditional instruction that cares about colors paid does not make its targets illegal. Cankerous Thirst always requires both creature targets (which may be the same), and its two actions are separately optional during resolution. Mythos of Nethroi can target any nonland permanent; its creature test happens on resolution. River's Grasp and Torrent of Souls retain the native optional creature group and required player group.

CR608.2c follows printed instruction order. River's Grasp first returns its creature, so that card may then be chosen from the revealed hand. Torrent returns its creature before pumping creatures controlled by its player target. Devour Intellect replaces its ordinary discard instruction only if a Treasure actually supplied mana that paid the spell. Treasure mana spent to activate a filter is input to that activation; the filter's output that pays the spell has its own provenance.

The shared `spent_mana_outcomes` builder composes existing native prevention, discard/reveal choices, division, targeting, continuous effects, casting limits, and grants. It never prunes targets based on mana paid. The few runtime recipes calculate a scalar or choose a branch, then insert native instructions into the existing saved resolution context.

Dawnglow Infusion computes a single gain-life instruction for X times the number of paid green/white predicates. Both colors therefore produce one life-gain event of 2X, as the official ruling specifies. The test with Ajani's Pridemate distinguishes this from two X-life events. X remains the announced X.

Bladecoil Serpent uses native mana-pair values, rounding down independently for each color. Its red trigger grants trample and haste only if at least one red pair was paid. Casting a spell copy without paying is distinct from copying an existing spell: CR707.10 copies do not pay mana and get no paid-color bonuses. Reanimation likewise has no cast payment. Existing unknown-payment guards do not invent paid colors for legacy/manual records.

Wumpus Aberration has a native cast trigger with an intervening if (CR603.4): a known original casting payment must contain no colorless mana. This remains independently on the stack when the creature spell is countered. Its targeted opponent's private optional hand entry uses native `each_put`, preserving entry replacements and control.

Mythos of Vadrok keeps its original announced damage division. Legal original targets get the attack/block/activation restrictions even if all damage is prevented; illegal targets get neither damage nor restriction. A native duration wrapper ends restrictions at the original caster's next turn (CR500.4). Flash Conscription grants the actual triggered ability to the creature until end of turn. Its controller when it deals combat damage gains life; the spell does not create a detached watcher that would survive ability loss.

Invert the Skies and Unnerving Assault use native layer effects whose affected creatures are fixed on resolution (CR611.2c). Later creatures are not included, and changing control does not recompute that affected set.

## Canonical ruling sources

Official Oracle rulings were retrieved through each Scryfall card's `rulings_uri`; the full response and URLs are preserved in `/tmp/fyodor-spent-outcomes36-rulings.json` during implementation. Relevant public card pages:

- https://scryfall.com/search?q=%21%22Dawnglow+Infusion%22
- https://scryfall.com/search?q=%21%22Cankerous+Thirst%22
- https://scryfall.com/search?q=%21%22Mythos+of+Nethroi%22
- https://scryfall.com/search?q=%21%22Mythos+of+Vadrok%22
- https://scryfall.com/search?q=%21%22Flash+Conscription%22
- https://scryfall.com/search?q=%21%22Wumpus+Aberration%22

## Boundaries

Boreal Outrider, Vazi, Keen Negotiator, and Abby, Merciless Soldier remain outside this implementation. Boreal needs paired actual color-and-Snow metadata, rather than unrelated aggregate color counts and Snow tags. Vazi must observe actual mana-ability activations as well as nonmana activations, with an immutable activation payment snapshot. Abby needs an opponent-controller choice before entering; an ordinary enter trigger changing control is not equivalent.

Validation includes actual positive gameplay for every card, actual spell-copy and spend-as-though cases, legal/illegal target boundaries, a prevented-damage restriction case, filter input/output accounting, native attack and combat damage, and four fresh-process save/replay cases at paid spell, private hand choice, optional action, and independent cast-trigger continuations. All cold cases also compare rebuilt history against state.
