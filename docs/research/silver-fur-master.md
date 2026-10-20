# Silver-Fur Master: ninjutsu cost reduction

Canonical Oracle data from the imported 2026-10-18 card database includes the creature's ninjutsu, its ability reduction, and its Ninja/Rogue anthem. The reduction is represented as a native activated-ability cost modifier restricted to the structured ninjutsu activation. It uses the existing increases-before-reductions calculation and cannot remove colored mana (CR 602.2b, 601.2f, 118.7a). Ordinary activated abilities and opponents' activations are unaffected. Native source characteristic derivation determines whether the static ability currently exists.

The existing ninjutsu implementation still pays the separate cost of returning an unblocked attacker, and still requires blockers to have been declared (CR 702.49a). Multiple Masters cannot reduce the colored component. Commander ninjutsu uses the same generated activation and therefore the same restriction without a card-name exception.

Gameplay tests cover zero, one, and two Masters; actual mana spent; the return cost and combat timing; the arriving Ninja and anthem; colored costs; unrelated Azure Mage activation costs; source control changes; Dress Down removing the modifier while the hand's ninjutsu survives; replay and save/load verification. Related existing ninjutsu and general activation-cost tests guard the shared cost pipeline.
