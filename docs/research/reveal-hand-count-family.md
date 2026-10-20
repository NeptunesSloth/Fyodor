# Revealed hand cards size payments and returns

Scent of Brine, Brine Seer, and Rofellos's Gift use canonical Oracle metadata from the local card database, including colors, color identity, mana value, keywords and printed power/toughness.

CR 701.20a/c: revealing shows the selected cards to everyone without moving them. Any number permits zero. Native reveal_hand_cards asks the controller privately even when no cards match, then binds only the cards actually revealed. Unknown hand cards remain hidden. CR 608.2c/h: the later instruction counts this resolution's revealed-card binding, rather than the current hand size, matching colors, or colored mana symbols.

CR 118.12a: the Brine payer may pay the entire dynamically sized generic mana cost; only a failure to pay causes the counter instruction. Revealing zero therefore offers a zero-mana payment. Target legality is checked before resolving the reveal, and an uncounterable spell can still be chosen and its controller can decline payment. Brine Seer's printed mana and tap costs remain ordinary activated-ability costs, subject to summoning sickness.

Gift has no target. Its controller chooses the enchantment cards during resolution, from their own graveyard. The native mandatory return choice returns exactly the lesser of the reveal count and the eligible-card count, with distinct selections. Native replay/save state carries the reveal binding into both the payment and graveyard choices.

The shared unless-payment grammar now reads native this-way quantity expressions before rejecting otherwise unbound pronouns. A small typed reveal/return grammar emits the existing reveal_hand_cards and return_choice effects. No new payment or card movement runtime is introduced.

Metalworker, Sacellum Godspeaker and Rosheen, Roaring Prophet remain a separate scope: their reveal/output abilities must be mana abilities without the stack, including nested mana payment continuations. These three are deliberately excluded from the current implementation.
