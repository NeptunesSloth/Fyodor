# Bound subsets and resolution-time choosers

Coin of Fate, Trial of Agony, Incriminate, Wake to Slaughter, Barrin's Spite,
Retribution, O-Kagachi Made Manifest, Neyam Shai Murad, Fortunate Few,
Monomania, Goblin War Cry, Eunuchs' Intrigues, and Teferi, Temporal Pilgrim
compose native choices, movement, sacrifice, counters, restrictions, and delayed effects.

A bound pool records object identities before a choice. The selected object and its
complement are bound before either moves; a singular “the other” requires one actual
selection. A sole surviving legal target is compulsory, and Wake returns that sole card
to hand. Coin binds the actual two-card exile cost receipt, rather than looking up card
names or using the original cost intent. Library placement, ownership, and the returned
permanent's new object identity remain native.

The native target-group relation enforces “controlled by the same player” at announcement,
copy retargeting, and resolution. The resolution-time chooser can be any existing player
reference, including defending player or the damaged player; absent players do not fall
back to the ability controller. Fortunate Few explicitly evaluates each chooser's
“don't control” filter from that player's perspective and destroys the global unchosen
nonland pool after all choices.

CR 608.2d bars impossible sacrifice selections. If one target cannot be sacrificed, choose
the other legal option. If neither can be selected, no singular complement is identified;
Barrin's Spite does not bounce both and Retribution does not counter both. A replacement
that changes the selected sacrifice's destination still allows the instruction on the
previously bound other creature. Official card rulings also require the sole remaining
legal target to be chosen for Trial, Barrin's Spite, Retribution, and Wake.

Tests use canonical Oracle fixtures, actual activated and loyalty costs, genuine combat
and Saga triggers, printed flashback, spell copying, controller changes, illegal targets,
sacrifice restrictions and replacements, and private discard choices. Saved native choice
contexts resume in fresh Python processes, including a counter replacement-order pause
and Wake's later new-object exile.
