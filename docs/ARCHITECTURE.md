# Architecture

```
┌──────────────────────── Browser (React + TS) ────────────────────────┐
│ pages/ (cards, decks, lobby, game)                                   │
│ game/ board UI ── state/ zustand store ── services/ REST + WebSocket │
└───────────────▲──────────────────────────────────┬───────────────────┘
                │ sanitized PlayerView (JSON)      │ Action (JSON)
┌───────────────┴──────────────────────────────────▼───────────────────┐
│ FastAPI  api/ (REST routers, /ws)                                    │
│   multiplayer/  GameHub: rooms, seats, connections, broadcast        │
│   game/         pure domain: state, actions, engine, views, history  │
│   cards/        card repository, Scryfall importer, image cache      │
│   decks/        parser, resolver, deck repository                    │
│   storage/      sqlite connections, migrations, save repository      │
│   rules/        (extension point, no-op today)                       │
│   assistant/    (extension point, disabled by default)               │
└───────────────┬──────────────────────────────────────────────────────┘
                │
        data/cards.sqlite   data/app.sqlite   data/images/…
```

Rules of the codebase:

- `game/` never imports FastAPI, SQLite, or the network. It is pure Python and
  deterministic given its inputs, so it can be tested directly.
- `storage/` knows nothing about game rules. It stores opaque JSON snapshots.
- The server is authoritative. Clients send *intents* (actions); the server
  validates them, resolves any randomness, applies them, and sends each client
  **its own** sanitized view.

## Domain model (`backend/app/game/state.py`)

```
GameState
  id, version(int, bumps each applied event), format ("commander" | "constructed" | "sandbox")
  players: {player_id: PlayerState}
  seat_order: [player_id]
  cards: {instance_id: CardInstance}         # normalized — zones hold ids only
  zones: {zone_key: [instance_id]}           # zone_key = "<player_id>:<zone>" or "stack"
  turn: TurnState {number, active_player, phase}
  table: TableState {monarch, initiative, day_night}
  combat: {attacker_id: AttackTarget}, blocks: {blocker_id: attacker_id}
  searches: {viewer_player_id: zone_key}     # zones temporarily shown to one player
  log: [LogEntry]
  rng_counter (for reproducible id generation in tests)

PlayerState
  id, name, color, life, life_history[]
  resources: {"poison": 0, "energy": 0, "experience": 0, "<custom>": n}
  commander_damage: {source_instance_id: n}
  commander_tax: {commander_instance_id: n}
  city_blessing: bool, mulligans: int, deck_id

CardInstance
  id (random, re-keyed on library shuffle)
  card_id (printing id in cards.sqlite, or null for custom tokens)
  owner, controller
  zone (zone_key; denormalized for O(1) lookup)
  x, y (battlefield virtual units), z (stacking order)
  tapped, face_down, face_index, flipped (Kamigawa-flip 180° display)
  counters: {type: n}
  note, is_token, token: TokenDef?, copy_of: CopyRef?
  is_commander
  known_to: set[player_id] | ALL        # who has seen this card while it is hidden
  revealed: bool                        # temporarily shown to all while in a hidden zone
  ability: AbilityObject?               # stack-only temporary objects
```

### Zones

Per player: `library`, `hand`, `battlefield`, `graveyard`, `exile`,
`command`, `sideboard`, `companion`, `foretell`. The `stack` is shared.

| Zone | Default visibility |
|---|---|
| library | nobody (not even the owner), except cards in `known_to`, or during a search by the searcher |
| hand | owner |
| foretell | owner |
| sideboard | owner |
| battlefield, graveyard, exile, command, companion, stack | everyone (face-down cards only for the controller plus `known_to`) |

Control means battlefield placement. A card on `P2:battlefield` is controlled
by P2, and "return to owner" moves it to the owner's battlefield.

### Knowledge tracking

`known_to` models what players have *actually seen*:

- Moving a card from a public zone into a hidden zone marks it known to
  everyone. Everyone watched Sol Ring get bounced to hand, so everyone knows
  that card in hand.
- A face-down card is always known to its controller.
- Looking at the top N adds the looker to `known_to`.
- Shuffling a zone clears `known_to` and `revealed` for every card in it, and
  **re-keys** the instance ids. After a shuffle the view carries no trace of
  which card went where.

## Actions, events and history (`game/actions.py`, `game/engine.py`, `game/history.py`)

```
client intent ──► resolve(state, action, rng) ──► ResolvedAction ──► apply(state, resolved)
                  (fills random/generated                            (pure, deterministic)
                   fields: shuffle order, new ids,
                   dice results)
```

- Every `ResolvedAction` is deterministic. Applying the same list of resolved
  actions to the same base state always produces the same state.
- `History` holds the base state, the list of resolved actions, a cursor, and
  periodic snapshots (every 20 actions).
  - **Undo** moves the cursor back and rebuilds the state from the nearest
    snapshot by replaying up to the cursor.
  - **Redo** moves the cursor forward and applies the next action.
  - A new action after an undo discards the redo tail.
- Randomness lives only in `resolve`. Undoing a shuffle therefore restores the
  previous library order exactly, and redoing it gives the same new order.
- Undo and redo are themselves logged ("Alice undid: drew a card"), but they
  are not history entries.

### Log

`LogEntry {seq, turn, phase, player_id, ts, parts[]}`. `parts` is a template
of text and card references. A card reference records the card identity and
who could see the card at that moment. The view builder renders "a card"
unless the viewer was allowed to see it. The same rule applies to
`card_name` fields anywhere in a view.

## Views (`game/views.py`)

`build_view(state, viewer)` where `viewer` is a player id, `SPECTATOR`, or
`OMNISCIENT` (local hot-seat "open table" mode only).

- Hidden cards become `{id, hidden: true, owner, zone}` with no `card_id`,
  counters, or notes.
- Libraries are sent as `{count, known: [{index, card}]}`. Hidden library
  cards are never sent as objects, and their ids are not included.
- Other players' hands are sent as a list of hidden cards (so the UI can draw
  card backs), except for cards the viewer knows.
- Search sessions expose the whole searched zone to the searcher only.
- Tests in `tests/test_views.py` walk every view and assert that no hidden
  `card_id` or name appears anywhere in the serialized JSON.

## Multiplayer (`multiplayer/`)

- `GameHub` maps game id to `Room {game, history, seats, connections}`.
- A seat is claimed with a room code (plus an optional password). The server
  returns a random **seat token**, and reconnecting with that token reclaims
  the seat.
- Each connection sends `{"type":"action", "action":{...}, "seq":n}`. The
  server checks that the acting player matches the seat (local games allow any
  seat), applies the action, then broadcasts a fresh sanitized view to every
  connection.
- Every inbound message is validated by pydantic discriminated unions. Unknown
  types or invalid payloads get an `error` reply, and the game state is left
  unchanged.
- All mutations to a room are serialized through a per-room `asyncio.Lock`.

## Storage

- `cards.sqlite`: `printings`, `oracle_defaults`, `card_names` (normalized
  names, including faces), `printings_fts` (FTS5), `meta`.
- `app.sqlite`: `decks`, `deck_cards`, `saves`, `schema_version`.
- Save format: `{"format": "fyodor-save", "version": 1, "state": {...},
  "history": {...}}`. `storage/save_format.py` holds migrations keyed by
  version.

## Extension points

- `rules/`: `RulesModule` protocol with `on_action(state, action) ->
  list[Suggestion]`. The engine calls registered modules *after* applying an
  action; they may only return suggestions, such as "state-based action:
  Grizzly Bears has lethal damage". None ship enabled. Future modules
  (triggers, SBA, combat, layers) plug in here and can later be allowed to
  emit actions through the same validated path as players.
- `assistant/`: `RulesAssistant` protocol and `build_context(state, viewer)`,
  which gathers oracle text for visible cards, the stack, and the phase. It
  uses the viewer's sanitized view, so it can never leak hidden info. An
  `OllamaAssistant` stub is configured by `FYODOR_ASSISTANT_URL` and disabled
  by default. It is read-only and holds no reference to the engine.

## Risky decisions and mitigations

| Risk | Mitigation |
|---|---|
| Full-view broadcasts get large with 4 players and hundreds of cards | Views omit card metadata (the client fetches and caches card data by id), and the client reconciles object identity to avoid rerenders. Delta sync can be added behind the protocol `version` field. |
| Replay-based undo cost grows with game length | Snapshots every 20 actions bound the replay to 20 applies. |
| Hidden-info leaks through ids, log text, or counts | Re-keying on shuffle, per-viewer log rendering, and serialized-JSON leak tests. |
| Card database schema drift from Scryfall | The importer stores `raw` faces and parts JSON, and pulls fields defensively with `.get`. |
| Undo in multiplayer can be abused | Undo is logged publicly. A host-only undo setting is planned. |
| Bulk file size | Streaming gzip JSONL import in batches of 2,000 rows inside a single transaction. |
