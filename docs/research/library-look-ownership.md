# Private inspection of another player's library

Implemented canonical Oracle family: Dimir Charm, Tahngarth's Glare, Ransack, Wand of Denial, Psychic Surgery. Fixtures include full actual DB metadata.

CR 401.2 keeps the library face down; CR 401.4 permits a player instructed to order multiple cards to choose their order without revealing it. CR 701.20e distinguishes looking from revealing. The existing look_top action grants inspection to its actor, while player identifies the library owner. This implementation keeps those roles separate, including Tahngarth's Glare's second inspection by the targeted opponent. Private library-order prompts retain the native convention that the first choice for the bottom ends at the very bottom.

Native looked_owner remains the destination owner. Opt-in exact_look captures object identities, and pending selection/order ignores cards that moved or became different objects. Native selection, private order, continuation, move replacement and history/reload mechanisms are reused. Ransack independently orders selected bottom cards and remaining top cards. Dimir Charm keeps its chosen card on top and moves only the rest to that library owner's graveyard.

Wand of Denial checks the actual looked-at card is a nonland, then uses native optional payment of two life (CR 118.3, 118.12). Its original controller pays even if the Wand is destroyed before resolution, and the resulting graveyard move follows native replacement effects. No payment is offered for a land or insufficient life.

Psychic Surgery uses an actual library_shuffled event emitted after a library shuffle finishes, even for an empty library (CR 701.24). The affected player, rather than the action's actor, determines whether an opponent shuffled. Generic nonlibrary shuffles do not emit it. Manual tabletop actions remain excluded from native triggers, consistently with the existing event engine. Canonical Feldon's Cane exercises actual automatic shuffle triggering; declining the optional look exposes no cards, and accepting it leads to native optional exile and private top ordering.

Gameplay tests save/load and replay at each decision. Additional integration inspects REST and initial WebSocket state frames for opponents and spectators while a Ransack decision is pending; neither receives real hidden card IDs. Targeted related regressions cover native library distribution, optional payments and protocol privacy.
