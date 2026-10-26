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
