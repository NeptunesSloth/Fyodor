# Named continuous Aura transformations

Witness Protection and Honest Work have one continuous effect with parts in several layers (CR 613.1). A terminal “named NAME” changes the enchanted creature's name in layer 3. Its creature/card types change in layer 4, color in layer 5, abilities in layer 6, and base power/toughness in layer 7b. The name change is not a copiable value (707.2).

The attached predicate grammar records `set_name`, protects multi-color descriptions from predicate splitting, and reads a quoted ability following a base-P/T description. Existing type/color, lose-all-abilities, base-P/T and granted-ability handling supplies the remaining parts.

`layers._derive` applies attached name setters in timestamp order before layer 4. The statics table still reads each source's copiable values first: a source that has already lost this text to a copy effect or is absent/face down supplies no name-setting static. Once an effect has started in layer 3, later ability removal does not remove the remaining parts (613.6); named grant statics are retained through the later wipe filter, and `group_layers.first_layer` recognizes their first layer as 3.

Witness Protection makes the host green and white, sets its card type to Creature and subtype to Citizen, removes abilities, and sets 1/1. Honest Work sets the Citizen creature subtype while preserving other card types and color, removes abilities but grants its own mana ability, and sets 1/1. Its existing enters ability taps the host and removes all counters. Supertypes such as Legendary remain; changing names can therefore cause the legend rule.

Later effects removing abilities from the host can remove Honest Work's granted mana ability; earlier ones are followed by its later grant. Neither changes the name-setting layer. Removing an Aura restores the remaining effects or original name. Copying an affected host copies its original/copy-layer name, types, colors, abilities and P/T, without the Aura's modifications.

A source-Aura ability-loss test must respect 303.4d: an Aura that becomes a creature cannot enchant anything and goes to the graveyard as a state-based action. Opalescence also explicitly excludes Auras. The tests use legal attached hosts, their earlier/later ability removal, source departure, and actual copying, rather than inventing a persistent attached creature Aura.

Canonical fixtures retain current Oracle colors, identity, mana values and keywords. Gameplay tests cover both cards' characteristics, source removal and name reversion, Honest Work's actual mana activation and counter removal, Aura timestamps, ability-loss timestamps, copied values, legend-rule interaction, and saved replay.
