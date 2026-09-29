# Implementation Plan

Fyodor is an offline-first digital tabletop for Magic: The Gathering. It is a
**sandbox**: the software handles the table (zones, cards, counters, life, the
stack, turn tracking, history). The players decide whether actions are legal,
the same way they would at a physical table.

This document is the working plan. Each milestone ends with a commit, passing
tests, and an updated status table.

## Starting point (inspection, 2026-09-28)

- The repository was empty apart from a blank `README.md`.
- Environment: Python 3.11, Node 22, SQLite 3.45 with FTS5.
- Scryfall `/bulk-data` now serves gzipped **JSONL** (`jsonl_download_uri`),
  so the importer can stream line by line without holding a 500 MB JSON array
  in memory. The importer also accepts the older `download_uri` JSON-array
  format and local files.

## Status

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Foundation: repo layout, FastAPI, React/TS/Vite, SQLite, health, dev scripts, tests | ✅ done |
| 2 | Card database: Scryfall importer, search, detail API, image cache, placeholders, card browser | ✅ done |
| 3 | Deck system: parser, persistence, commander designation, library/editor UI, warnings | ✅ done |
| 4 | Playable tabletop: games, zones, shuffle/draw, drag and drop, zoom, tap, life | ✅ done |
| 5 | Advanced tabletop: counters, tokens, copies, notes, face-down, DFCs, search, mill, reveal, dice, stack, phases, combat | ✅ done |
| 6 | Commander: tax, damage matrix, poison, monarch, initiative, custom resources | ✅ done |
| 7 | History: event model, undo/redo, log, save/load, autosave | ✅ done |
| 8 | LAN multiplayer: WebSocket sync, seats, reconnect, spectators, hidden-info filtering | ✅ done |
| 9 | Pod hardening: explicit visibility model, protocol leak tests, LAN lobby (bring your own deck), mulligan policies (London / Commander London / Boston slot / Custom), response helper, Playwright + CI | ✅ done |
| 10 | Pod P0: presence + reconnect grace, revisions + resync, host tools, owner/controller, face-down kinds, multi-commander, save migrations v3/v4 | ✅ done |
| 11 | Pod tracker: results, corrections, Pod Stats, deck stats, backup | ✅ done |
| 12 | Table tools (P1/P2): effects, damage, arrows, mana pool, mass actions, filters, choices, cast metadata, exile groups, cleanup, sleeves/playmats, asset manager, tabletop HUD | ✅ done |
| 13 | P3: snapshots + history timeline, profiles/sound/keys/accessibility/perf presets, custom actions (declarative macros), solo tools, portable packages, diagnostics, launcher + first-run, lobby deck checks, full pod regression E2E | ✅ done |
| 14 | 3D table client (three.js) and tabletop toys (dice objects, bags incl. hidden draw bag) | planned — see `3D_DIRECTION.md` |

The history model (M7) and hidden-information views (M8) shape the engine
itself, so they are built into the engine from Milestone 4. Retrofitting
either one later would mean rewriting the engine.

## Milestones in detail

### M1 — Foundation
- `backend/` FastAPI app factory, settings from env/`.env`, structured logging,
  `/api/health`.
- `frontend/` Vite + React + TypeScript (strict), dev proxy to the backend.
- SQLite helpers with numbered schema migrations.
- `scripts/dev.sh` runs both servers; `scripts/test.sh` runs every test suite.
- pytest and vitest suites.

### M2 — Card database
- `python -m tools.update_cards` (run in `backend/`) downloads bulk metadata,
  streams it into `data/cards.sqlite`, and can then download images. It
  reports progress, resumes interrupted downloads, and skips images it already
  has.
- Search uses FTS5 over name, type line, and oracle text, with filters.
- Each oracle card has a default printing, chosen by a scoring function.
- Images are stored as `data/images/cards/<id[0:2]>/<id>-<size>.jpg` and
  served only through a validated-UUID route. When an image is missing, the UI
  renders a text card instead.
- Offline card-browser page.

### M3 — Deck system
- A tolerant text parser covering Moxfield, Archidekt, MTGGoldfish, and plain
  lists (see `docs/DECK_FORMAT.md`).
- Card resolution against the local database, with an exact set and
  collector-number match first, then set-only, then the default printing.
- Decks are stored in `data/app.sqlite` and support CRUD, duplication, and a
  commander flag.
- Validation warnings only: unresolved cards, deck size, commander count,
  color identity. No legality enforcement.

### M4 — Playable tabletop
- Game engine built on an action/event model (see `docs/ARCHITECTURE.md`).
- Per-player zones; free positioning on the battlefield.
- Drag and drop between zones, tap/untap, zoom, life.

### M5 — Advanced tabletop
- Everything in the M5 list above, implemented as engine actions with tests.

### M6 — Commander
- Per-player resource panel with commander damage recorded by source
  commander, and warnings at 21 commander damage and 10 poison.

### M7 — History
- Undo and redo by replaying deterministic events from checkpoints.
- Log entries rendered per viewer, so hidden card names are not leaked.
- Save and load in a versioned JSON format stored in SQLite, plus autosave.

### M8 — LAN multiplayer
- WebSocket hub with player seats and reconnect tokens.
- A sanitized view built for each connection; spectators get the public view.
- Tests confirm that no private card identity reaches a viewer who isn't
  allowed to see it.

## Delivery notes

- **Tests**: 241 backend tests (pytest), 28 frontend unit tests (vitest) and 16 browser
  end-to-end tests (Playwright, production build, fixture card data, no Internet). CI runs all
  three on every push; `E2E=1 scripts/test.sh` runs them locally.
- **Manual smoke test**: `docs/SMOKE_TEST.md` covers the 25-step acceptance list.
- **Measured performance** (headless Chromium, 300 cards on the table): the server
  applies an action and builds a view in about 8 ms. A phase change round-trips and
  re-renders in about 50 ms. Dragging holds a 16.7 ms median frame time.
- **Real data**: importing Scryfall `default_cards` (115k printings) takes about 17 s
  and produces a ~260 MB database. Search queries take about 40 ms.

## Design decisions worth knowing (not gaps)

- **One shared, linear undo history.** It's the table's history, not a player's: undo takes back
  the latest action whoever did it, and everyone sees it in the log. The host can also restore
  any earlier point from *Snapshots & history*. Per-player undo would let two people rewrite
  the same board in conflicting ways.
- **Full sanitized view per change**, with an increasing revision and resync on gaps. On a
  home LAN this is ~150 KB for a 300-card table and renders in ~50 ms. Delta sync only matters
  for WAN play, which the pod doesn't need.

## Next

- 3D table client (three.js) on top of the same server-authoritative state
  (`3D_DIRECTION.md`), then tabletop toys (physical dice, dice tray, token bags, and a hidden
  draw bag that uses the same per-viewer privacy as libraries).

## Deliberately out of scope

Fyodor is a physical-feeling table for one trusted pod, not Arena and not a judge. It does not
include:

- **Rules help:** a rules engine, automatic trigger / "missed trigger" / upkeep reminders,
  enforced priority, replacement effects, or enforced legality. Deck checks are advisory, with
  *Play anyway*.
- **Online and competitive features:** tournament enforcement, matchmaking, accounts, cloud
  saves, rankings / ELO / medals, achievements.
- **Other formats and audiences:** sealed, draft, spectator/caster tooling.
- **Ecosystem and oversight:** a mod marketplace, anti-cheat, telemetry or analytics.

The `rules/` and `assistant/` packages hold interfaces only; see
`docs/ARCHITECTURE.md#extension-points`.

## Decisions and defaults (documented so nobody has to ask)

| Decision | Choice | Why |
|---|---|---|
| Card DB vs app DB | Two SQLite files: `cards.sqlite` (rebuildable) and `app.sqlite` (user data) | Card updates can rebuild or replace the card DB without touching decks or saves. |
| ORM | None; stdlib `sqlite3` with a thin repository layer | Few tables and fast bulk import; no extra dependency. |
| Bulk dataset | `default_cards` (all English printings), selectable | Deck lines like `(CMM) 123` need printings. |
| Undo strategy | Event log + periodic snapshots + deterministic replay | Randomness (shuffle, dice) is resolved into the event, so replay is exact and undo restores the previous library order. |
| Undo scope | Global, linear (the last action at the table) | Matches "take that back" at a real table; per-player undo interacts badly with shared state. |
| Transport | REST for library data, WebSocket for game actions (REST fallback for actions too) | Simple tests and simple clients. |
| State sync | Full sanitized view per update; client reconciles to keep object identity | Correct first; deltas can be added later without protocol breakage (versioned messages). |
| Library order | Index 0 is the **top** | |
| Coordinates | Battlefield positions are in virtual units (1000×600 per player area) and scaled by the client | Independent of screen size. |
| Drag and drop | A small custom pointer-events system rather than a library | Needs free positioning and zone drops at once, with smooth transforms. |
| Frontend state | zustand store with selectors, normalized by id | Keeps rerenders to the components that changed. |
| Instance ids | Random, and **re-keyed when a library is shuffled** | Stops opponents tracking a known card through a shuffle. |
| Local vs LAN | A game created from the UI is "local" (hot-seat; any client may pick any seat). LAN games require seat tokens. | Hot-seat playtesting stays one click away. |
