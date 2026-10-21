# Mount Doom — choose creatures and destroy the rest

Sources: [Oracle](https://api.scryfall.com/cards/named?exact=Mount+Doom), [official rulings](https://api.scryfall.com/cards/b5bc71a1-2344-4bc6-aa60-658cec19d0d6/rulings), checked 2026-10-19; Comprehensive Rules 2026-09-25, 602.2b (activation follows casting/payment procedure), 608.2d (choices on resolution), 701.8 (destruction), 701.21 (sacrifice).

The official ruling states that no chosen creature is a target, so a creature with shroud can be chosen. The controller may choose zero, one, or two creatures from the entire battlefield. All other creatures are destroyed together using ordinary destruction rules, including indestructible and regeneration. The choice remains optional even when there are only one or two creatures available.

All printed costs already have typed support: pay {5}{B}{R}, tap Mount Doom, sacrifice Mount Doom and a legendary artifact you control. These costs are paid on activation; the subsequent choice occurs on resolution after the land has left. Existing activation restrictions enforce sorcery timing.

The generic `group_choice` grammar now reads `Choose [up to] N <permanent selector>, then destroy the rest.` into an existing `player_chooses` instruction followed by destruction of the selector's complement. The separate complement is necessary because the older per-player `rest` instruction refers only to permanents controlled by its chooser.
