# Counter quantities chosen among permanents

Canonical cards: Slippery Bogbonder, Aetherborn Marauder, Galloping Lizrog, Eventide's Shadow, Sensational Spider-Man, and Garnet, Princess of Alexandria. Each was PARTIAL before this bounded grammar family. Their source Oracle text is stored in `tests/fixtures/counter_group_choice_cards.json`.

CR 608.2d requires the controller to choose which objects supply which quantities. An aggregate total by counter kind cannot implement “from among”: two creatures with the same kind need separate quantity choices. The new queue captures public battlefield objects by exact object identity, offers independent typed nonnegative amounts, and applies any total/per-object limit before accepting an answer. Typed numbers also avoid allocating one decision option per counter. Choosing zero implements the optional instructions without inventing a required removal.

CR 122.5 makes a counter move depend on both the removal and the placement being possible. The queue excludes the destination as a source, checks its exact object identity and counter prohibitions, then removes selected quantities and puts the resulting batch through the existing counter replacement machinery. Counter-doubling and replacement-order prompts remain native. A paused placement continues the saved effect after its removals, rather than repeating them.

Plain removals use their actual quantity to create the subsequent native draw, life-loss, and counter-placement instructions. Thus Solemnity prevents movement/placement but does not prevent plain removal; replacement effects on the later placement or draw remain ordinary native effects. Garnet's selected Sagas each supply at most one lore counter; Spider-Man's three-counter limit is shared across all selected permanents.

The saved queue contains the original descriptor, exact source/destination object references, available rows and already chosen amounts. Fresh-process save/load resumes a second source choice without repeating or losing the first. Changed objects are excluded even when the same physical card returns with new counters. Existing aggregate single-object counter primitives are unchanged.
