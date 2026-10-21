# Kogla and Yidaro

The cost parser already supported discarding this card from hand. The missing instruction was returning that discarded incarnation from the graveyard to the library and drawing a card.

CR 400.7 allows an ability to find the public object its cost moved. `PaymentRecord.discarded_objects` records the actual post-discard object IDs. A native source reference checks the source card, its current graveyard, and that exact ID. Leaving the graveyard and returning creates an ineligible new object. Existing ability-copy payment aliases preserve these references for copies (707.10).

The bounded activation parser recognizes the explicit self-shuffle from the graveyard only with a self-discard cost. It emits native return-to-library and shuffle instructions. The library is shuffled even if the card has left the graveyard, as required by CR 701.24c. The subsequent draw also happens unless the ability is countered, including being countered for having no remaining legal chosen targets.

Canonical fixtures and gameplay tests cover zero or one chosen target, artifacts and enchantments, exact discarded identity, graveyard replacements, a real Scavenging Ooze response, Stifle, Rings of Brighthearth, payments, replay, and JSON save/load.
