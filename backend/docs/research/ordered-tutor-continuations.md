# Ordered tutor continuations

The canonical fixtures in `tests/fixtures/ordered_tutor_continuation_cards.json` cover Cartographer's Hawk, Yavimaya Dryad, Myr Incubator, Thawing Glaciers, Elfhame Sanctuary, Distant Memories, Hithlain Rope, Fervent Mastery, Omenpath Journey, Doomsday, Sift Through Sands, Grim Reminder, Prishe's Wanderings, and Disorienting Choice.

`ordered_tutor_continuations` composes native search requests, exact object bindings, entry queues, triggered abilities, delayed returns, and multiplayer choices. It does not implement a separate search engine. Producers and consumers use standard `ref:` bindings so script compilation can namespace them together.

Doomsday and Grim Reminder capture native search results without moving the found cards prematurely. Doomsday then exiles the rest of both zones and privately orders its chosen cards. Grim Reminder reveals the chosen card, compares its names with public as-cast name snapshots, and shuffles afterward. Unknown legacy snapshots use the shared public cast-name restoration decision rather than inferring a historical name from the card's current characteristics.

Opposition Agent's official rulings state that a search covering the library and other zones gives its controller the choices in all those zones, and exiles all found cards. Subsequent instructions referring to the found cards cannot see the diverted cards. The shared search and named-search corrections therefore apply the replacement across the complete search, exclude diverted cards from linked/result bindings, and preserve native Agent play permissions. A genuine graveyard-only search or a prohibited library search does not acquire this replacement.

Cartographer's Hawk checks the relative land count when combat damage triggers its ability. Its Oracle text has no intervening-if condition; later changes do not cancel the search. Returning the exact source is still required. A blinked source is a new object and cannot pay that return instruction. Thawing Glaciers likewise schedules its cleanup return for the exact activated object.

Elfhame Sanctuary uses a turn-scoped draw-step skip. Its official ruling says that multiple searches do not skip draw steps on later turns. Declining a later upkeep search therefore permits that turn's ordinary draw.

Fervent Mastery reads the selected alternative-cost decision from the exact payment record. CR 707.10 copies that decision onto a spell copy even though the copy was not cast. This differs from Grim Reminder and Sift Through Sands, whose conditions require actual cast history.

Grim Reminder's independently supported graveyard-only activated ability is excluded from the spell's resolving instruction list. Unsupported activated text remains unsupported; the regression suite includes that boundary.

The gameplay suite proves successful effects for all fourteen cards, replay and JSON restoration, native cold continuations, multiplayer choices, actual spell copying, exact source identity, search restrictions, Agent permissions and result visibility, and current-turn skip expiration. REST and WebSocket privacy are tested through the application adapters.

The collateral `Roads Go Ever, Ever On` fixture is canonical Oracle data from the local card catalog. Its linked Plains search became supported through the native search/link composition. The collateral scenarios cover all four chapters, zero/one/two found cards, exact linked returns, saved-state continuation, and the final chapter's delayed attack trigger after the Saga has been sacrificed.
