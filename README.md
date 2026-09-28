# Fyodor — offline MTG tabletop

A fast, offline-first digital tabletop for **Magic: The Gathering**, built for Commander, 60-card
constructed and casual sandbox games. It is a table, not a rules engine: you and your
opponents decide what's legal, and Fyodor provides the zones, cards, counters, life totals,
stack, turn tracker, log, undo and saves. Once the card data is downloaded, nothing needs the
Internet.

- **Tabletop**: free card positioning, drag and drop between every zone, tap/untap, counters,
  tokens, copies, face-down cards, transform/MDFC/adventure/split faces, notes, reveal,
  library search / look at top N / mill, the stack, combat markers, dice and coins
- **Commander**: command zone with automatic (adjustable) commander tax, commander damage
  per commander with 21-damage warnings, poison, energy, experience, custom counters,
  monarch, initiative, city's blessing, day/night
- **History**: every action is logged; unlimited-style undo/redo (default 500 steps),
  save/load with full history, autosave
- **Multiplayer**: hot-seat on one computer, or LAN play where the host is authoritative
  and each device only receives what its player is allowed to see
- **Decks**: paste lists from Moxfield, Archidekt, MTGGoldfish, Arena or plain text;
  deck library, editor, printing picker, advisory checks

See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for design details.

## Requirements

- Python 3.11+
- Node.js 20+ (only needed to build/run the frontend)
- ~300 MB disk for card data, plus images (a few hundred MB for your decks' cards,
  ~2.5 GB for one image of every card)

## Setup

```bash
scripts/setup.sh                    # backend venv + npm install
scripts/update-cards.sh             # download Scryfall card data (needs Internet once, ~80 MB)
scripts/update-cards.sh --skip-data --images tokens   # optional: token art (~100 MB)
```

After importing decks you can cache their art with `scripts/update-cards.sh --skip-data --images decks`.
Image downloads resume where they stopped and never download a file twice. Cards without a
cached image are drawn as readable text cards, so the game is fully playable without any
images.

`update-cards.sh` wraps `python -m tools.update_cards` (run from `backend/`). Options:

| Option | Meaning |
|---|---|
| `--bulk default_cards` | Scryfall dataset: `default_cards` (all English printings, default), `oracle_cards`, `all_cards`, `unique_artwork` |
| `--images none\|decks\|tokens\|default\|all` | which images to cache (default `none`) |
| `--size normal` | image size: `small`, `normal`, `large`, `art_crop` |
| `--file PATH` | import a bulk file you already have (no network) |
| `--force` | re-import even if the local data is current |
| `--skip-data` | only download images |

## Running

**Development** (hot reload, two servers):

```bash
scripts/dev.sh      # backend http://127.0.0.1:8000, frontend http://127.0.0.1:5173
```

**Normal use** (one server, built frontend):

```bash
scripts/serve.sh    # builds the frontend, serves everything on http://127.0.0.1:8000
```

### LAN play

```bash
FYODOR_HOST=0.0.0.0 scripts/serve.sh
```

1. On the host, open `http://127.0.0.1:8000` → **Play** → choose *LAN* → **Start game**.
   The top bar shows a room code (the Play page lists the host's LAN addresses).
2. Other devices open `http://HOST-IP:8000` → **Play** → *Join a LAN game* with the code
   (and password, if set). Players get a free seat; extra people can spectate.
3. Reloading or reconnecting reclaims your seat automatically (the seat token is stored in
   the browser).

Hot-seat (local) games and the saves/game management endpoints only accept requests from
the host computer itself.

## Playing

- **Drag** cards anywhere: battlefield, hand, piles, the stack, another player's
  battlefield (gives control). Drag on empty table to box-select.
- **Double-click**: tap/untap (battlefield), play (hand), draw (library), cast (command zone).
- **Right-click** anything for the full action list (counters, copies, face down, attack,
  block, move to library position N, reveal, give control, notes…).
- Click your **library** for draw N, shuffle, search, look at top N, reveal, mill, mulligan.
- Keys: `D` draw · `T`/space tap · `F` turn over · `N` next step · `Shift+N` next turn ·
  `U` untap all · `Delete` to graveyard · `Ctrl+Z` / `Ctrl+Shift+Z` undo/redo · `?` help.
- In hot-seat games use **View** in the top bar to switch seats, or *Open table* to see
  every hand (goldfishing).

## Configuration

Environment variables (or a `.env` file in `backend/`), see [`.env.example`](.env.example):

| Variable | Default | |
|---|---|---|
| `FYODOR_DATA_DIR` | `./data` | card DB, images, decks and saves |
| `FYODOR_HOST` / `FYODOR_PORT` | `127.0.0.1` / `8000` | bind address (used by the scripts) |
| `FYODOR_LOG_LEVEL` | `INFO` | |
| `FYODOR_AUTOSAVE_EVERY` | `10` | autosave after this many actions |
| `FYODOR_HISTORY_LIMIT` | `500` | undo steps kept per game |
| `FYODOR_CORS_ORIGINS` | dev server | comma-separated |
| `FYODOR_ASSISTANT_URL` | unset | Ollama-compatible endpoint for the optional rules assistant |
| `FYODOR_ASSISTANT_MODEL` | `llama3.1` | |

Data layout:

```
data/
  cards.sqlite        # rebuilt by update-cards (safe to delete)
  app.sqlite          # your decks and saved games
  images/cards/<id[:2]>/<scryfall-id>-<face>-<size>.jpg
  images/tokens/…
  downloads/          # cached bulk file
```

## Tests

```bash
scripts/test.sh     # ruff + pytest (backend), tsc + vitest (frontend)
```

The backend suite covers card import and search, deck parsing, every game action,
undo/redo restoring exact state (including library order after shuffles), save/load
across restarts, and hidden-information leaks for every viewer over REST and WebSocket.
A manual smoke test is in [`docs/SMOKE_TEST.md`](docs/SMOKE_TEST.md).

## Project layout

```
backend/
  app/api/          REST + WebSocket routes
  app/cards/        card DB schema, Scryfall importer, search, image cache, downloader
  app/decks/        decklist parser, deck repository, advisory validation
  app/game/         pure game engine: state, actions, resolve, engine, views, history
  app/multiplayer/  rooms, seats, connections
  app/storage/      SQLite helpers, migrations, versioned saves
  app/rules/        extension point for future rules assistance (advisory only)
  app/assistant/    optional local AI rules assistant (disabled by default)
  tools/update_cards.py
  tests/
frontend/src/
  pages/            home, card browser, decks, deck editor, lobby, game
  game/             table UI (battlefield, hand, piles, panels, menus, drag and drop)
  cards/            card rendering (images with text fallback)
  state/            zustand stores (game, card cache), view reconciliation
  services/         REST + WebSocket clients
docs/               plan, architecture, deck format, smoke test, security
scripts/            setup, dev, serve, test, update-cards
```

## Privacy

No telemetry, analytics or tracking. The only network access is the explicit card/image
download in `update-cards` (and the optional assistant endpoint you configure yourself).

Card data and images are provided by [Scryfall](https://scryfall.com). Magic: The Gathering
is © Wizards of the Coast. Fyodor is unofficial Fan Content and not affiliated with them.
