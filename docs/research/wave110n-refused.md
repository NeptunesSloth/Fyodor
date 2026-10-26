# Wave 110N refused cards

One line each: card, why it stays PARTIAL.

- Grip of Amnesia: "unless its controller exiles all cards from their graveyard" with an empty graveyard (is exiling nothing doing the action?) has no settled ruling in the CR.
- Reversal of Fortune: copying a card in an opponent's hand (707.12) needs a hidden-zone copy that the copy machinery (exile/graveyard only) does not model; casting from their hand leaks or breaks hidden information.
- Phylactery Lich: "As this creature enters, put a phylactery counter on an artifact you control" needs a choice made during entry (614.12); a trigger would let the state-trigger sacrifice fire first.
- Fleshwrither: Transfigure ("sacrifice this creature, search for a creature with the same mana value") has no parse for a tutor with a mana value taken from the sacrificed source.
- Torrent Elemental: an activated ability that works from exile (put this card from exile onto the battlefield) has no activated-from-exile path.
- Overburden: "puts a nontoken creature onto the battlefield" (who puts it when another player's effect does) is unsettled.
- Radiant Performer, Agrus Kos: copying an ability or spell once for each other legal target with a different target each needs an ability-copy spread that only exists for spells.
- Medomai's Prophecy: chapter III as a delayed "first time this turn" cast trigger on the chosen name has no confirmed ruling for when it is created.
- Spinneret and Spiderling: "deals 4 or more damage" for damage split among several recipients is unsettled.
- Dark Intimations: a graveyard-functioning cast trigger that adds loyalty to the entering planeswalker has no entry-counter machinery for spells cast from another zone's trigger.
- Animate Artifact: "as long as enchanted artifact isn't a creature" is a layer dependency on type changes (Vehicles crewed, other animations) that the layer engine does not order.
- Merseine: an activated ability whose cost is the enchanted creature's mana cost, activated only by that creature's controller, is not a cost shape the engine has.
- Voltaic Visionary: "when you play a card exiled with this creature" needs the pre-cast exile object linked to both a cast and a land play.
- Zilortha, Strength Incarnate: "lethal damage is determined by power" (a 0-power creature, 120.6 and 704.5g, and combat damage assignment 510.1c) has no settled ruling here.
- Wayta, Trainer Prodigy: "a creature being dealt damage causes a triggered ability to trigger an additional time" is a refused cause in trigger_multipliers (no ruling read); the fight's conditional cost reduction is separate unfinished work.
- The Dominion Bracelet: the granted ability exiles the Equipment (a named other permanent) as a cost and reduces its own cost by the creature's power; neither shape exists.
- Monument to Perfection: "nine or more lands with different names among the basic, Sphere, and Locus lands" and the "loses all abilities, toxic 9" animation have no grammar.
- Megatron, Tyrant // Megatron, Destructive Force: the excess-damage replacement that also converts the permanent is not modelled.
- Monastery Raid: Freerunning (an alternative cost with a combat-damage condition and an X in the alternative cost) is not implemented.
- Coffin Queen: the two-event delayed exile (becomes untapped or you lose control) tied to each activation is not modelled.
- Yavimaya Bloomsage // Channel: "any time you could activate a mana ability, you may pay 1 life" is a mana-ability grant made mid-payment.
- Land Equilibrium: the replacement ("instead puts that land onto the battlefield then sacrifices a land of their choice") differs in timing from a trigger and the engine has no replacement for lands put onto the battlefield by their own controller's play.
- Chorus of the Conclave: an optional additional cost of "any amount of mana" granted to every creature spell has no announcement machinery.
- Ogre Battlecaster: casting a card from the graveyard by paying extra, with an exile-instead rider and a cast trigger on that spell, is not modelled.
- Glyph of Delusion, Acidic Dagger: "the creature that target Wall blocked this turn" and a damage watch tied to an activation are not modelled.
- Guardian Archon: a secret opponent choice that is later revealed needs hidden choices tied to a permanent; none exist.
- Retriever Phoenix: the replacement of "learn" (Lesson/outside the game, 903.11 aside) by a graveyard return is not modelled.
- Tusk and Whiskers, _____ _____ _____ Trespasser, Smuggler Captain: stickers (name stickers, ability stickers) and noted names ("Conspiracy"-style memory across games) are not modelled.
