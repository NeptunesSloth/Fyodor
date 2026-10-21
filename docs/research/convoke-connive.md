# Creatures that convoked a spell connive

Lethal Scheme uses the spell's actual convoke contributions, rather than every tapped creature or every creature offered during payment. Each contribution already records its rules object ID. A copy retains references to objects used to pay the original spell's costs (CR 707.10).

The [official Scryfall rulings](https://api.scryfall.com/cards/3e449c2b-39a5-48c8-b6a5-60e16306e38a/rulings) explicitly state that a creature that has left the battlefield still connives. Its last controller draws and discards, but counters cannot be placed on its new object if the physical card returned (CR 400.7, 701.50b).

When several permanents connive, the first player in APNAP order with remaining connivers chooses one of theirs to connive. Repeat until none remain (CR 701.50c). Their individual draws, private discards, nonland counters, and replacement choices complete before the next conniver starts. A connive replacement such as Leader, Super-Genius applies independently to each creature.

Lethal Scheme's sole target must remain legal for the spell to resolve (CR 608.2b). Destroying one of its own convokers is legal: that old object still connives after being destroyed. Paying entirely with mana produces no convokers and no connive instructions.

Rules reference: `data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt`, CR 701.50a–f, 702.51, 707.10.
