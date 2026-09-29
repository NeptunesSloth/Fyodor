# Implementation Plan

Fyodor is an offline-first digital tabletop for Magic: The Gathering for one trusted pod.
The target is:

> **Tabletop Simulator-style 3D interaction + MTG Arena-like rules automation + a manual
> sandbox override + an Archidekt-first pod workflow.**

- **Today (milestones 1–13):** a complete sandbox. The software runs the table (zones, cards,
  counters, life, the stack, turn tracking, history, LAN, saves) and the players decide what
  is legal. This is the **stable foundation**: it is extended, never rewritten, and its
  tests stay green.
- **Next (milestones 14–19):** a rules engine underneath the table that automates normal play
  at roughly Arena's level **for the cards and mechanics we support**. The manual sandbox
  stays available for everything else.
  - The rules engine comes first. The 3D renderer is built only after it, on top of the rules
    intent API (`3D_DIRECTION.md`), and it sends player **intents** rather than mutating
    state.
- **Priority:** cards from our own decks (Archidekt imports and saved decks) are automated
  first.

This document is the working plan. Each milestone ends with a commit, passing tests, updated
docs, and an updated status table.

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
| 14 | **Rules boundary:** intent protocol, `rules/` package, `RulesState`, decisions, override logging, automation setting, coverage metadata (FULL / PARTIAL / MANUAL), pod card inventory from Archidekt/saved decks | ✅ done |
| 15 | **Core rules primitives:** mana costs and payment, casting and the stack, activated abilities, state-based actions, combat, commander rules | next |
| 16 | **Card effects:** effect primitives, targeting, keywords, triggered and activated abilities, continuous effects (layers), common replacement effects, templated Oracle-text recognition | planned |
| 17 | **Pod coverage:** script the pod's cards by frequency until our decks are mostly FULL; per-deck coverage in the deck view and lobby | planned |
| 18 | **Rules-aware client (2D first):** playable highlights, prompts, stops and auto-pass, override affordances | planned |
| 19 | **3D table** (three.js) on the intent API, then **tabletop toys** (dice objects, bags incl. a hidden draw bag) | planned — see `3D_DIRECTION.md` |

The history model (M7) and hidden-information views (M8) shape the engine itself, so they
were built into the engine from Milestone 4. The rules engine follows the same rule: it is
designed around deterministic, recorded history and per-viewer views from day one (see
`ARCHITECTURE.md#rules-layer`), so it slots in underneath without touching either.

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

- **Tests**: 244 backend tests (pytest), 30 frontend unit tests (vitest) and 16 browser
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

## Roadmap: rules engine, then 3D

The order is deliberate. Each step keeps every existing test green, since automation is off
by default and the foundation doesn't change.

### M14 — Rules boundary ✅

**Status: built** (tests in `test_rules_boundary.py`, `test_rules_coverage.py` and
`test_protocol_privacy.py`). What differs from the outline below:

- **Data model location:** `RulesState` and `Decision` live in `app/game/rules_state.py`,
  next to `GameState`, so the table model doesn't import the engine. Behaviour is in
  `app/rules/`.
- **Two server-only steps**, `rules_sync` and `rules_log`, carry the engine's state and log
  lines inside a compiled plan. Clients can't send them.
- **Already working:**
  - priority with Arena-style stops (`set_stops`; your first main phase is always a stop);
  - the turn structure with its turn-based actions (untap, draw with the two-player
    first-turn skip, discard to hand size as a private decision, damage wearing off);
  - `play_land`, resolving the stack with a manual-resolution step, `choose` and `concede`;
  - picking up where a manual step change left off.
- `cast_spell`, `activate_ability`, `declare_attackers` and `declare_blockers` are in the
  protocol but answer "arrives with the next milestone" until M15.
- **Where automation is turned on:** at creation (hot-seat `automation`, lobby setting) or by
  the host mid-game (`configure automation / automation_paused`).
- **Baseline inventory:** from the sample decks, in `docs/RULES_COVERAGE.md`.

1. **Intent protocol.** Add the `play_land`, `cast_spell`, `activate_ability`,
   `declare_attackers`, `declare_blockers`, `pass_priority`, `choose` and `concede` inputs
   to the same validated message path as sandbox actions. With automation off they are
   rejected with a clear message. The existing actions become the "sandbox" set.
2. **`rules/` package skeleton**, with no FastAPI, storage or renderer imports:
   - `engine` (validate → plan → settle);
   - `state` (`RulesState`, `Decision`);
   - `characteristics`;
   - `costs`;
   - `coverage`;
   - `cards/` (script registry);
   - `keywords`.
3. **`GameSettings.automation`** (`off` | `rules`) and `GameState.rules`.
   - `off` is the default and behaves exactly as today.
   - Adding the field requires save format v5, with a migration that fills `rules: null`.
4. **Compile-and-record.** An intent is planned on a scratch copy into primitive table actions
   and recorded as one history entry (the macro mechanism), so undo, replay and saves work
   unchanged.
5. **Decisions protocol:**
   - one pending decision, addressed to one player, with the legal options in that player's
     view only;
   - the answer arrives through `choose`;
   - privacy tests cover prompts.
6. **Manual override.**
   - Sandbox actions stay available with automation on and are logged as overrides.
   - A `manual_resolution` decision covers unsupported effects.
   - The host can pause and resume automation.
7. **Coverage metadata.** Every card gets FULL / PARTIAL / MANUAL plus a list of its manual
   parts, computed from the script registry and keyword support. It is exposed by
   `GET /api/rules/coverage?oracle_ids=…`.
8. **Pod card inventory.**
   - `python -m tools.rules_inventory` reads the saved decks (Archidekt imports and pasted
     lists) and the cards in saved games, and counts unique Oracle ids by how many pod decks
     play them.
   - It outputs a prioritised coverage report (`docs/RULES_COVERAGE.md` plus JSON).
   - The same report is served at `GET /api/rules/inventory` on the host computer.

### M15 — Core rules primitives

**Progress:**

- **Built, M15a: mana and casting**, tested in `test_rules_casting.py`.
  - Cost parsing covers generic, coloured, hybrid, twobrid, Phyrexian and X.
  - Mana abilities with `{T}` / "sacrifice this" costs are understood, including basic land
    types, "any color" and "commander's color identity". Activating one asks which colour
    when there's a choice. Summoning sickness is derived from control marks.
  - An auto-payment solver uses the pool first and keeps flexible sources for last.
  - `cast_spell` handles timing (sorcery speed vs instant/flash), commander tax, X, targets
    shown as arrows, and "can't pay → nothing happens".
  - Priority: the caster passes unless they hold priority, and smart passing skips players
    with no possible response.
  - Mana pools empty between steps. Auras and spell effects fall back to manual resolution.
- **Still to do:** M15b state-based actions and the commander zone choice, M15c combat, and
  M15d non-mana activated and loyalty abilities.

- **Turn and priority:** the turn structure (untap, upkeep, draw, main, combat steps, end,
  cleanup with discard to hand size) and priority passing with Arena-style stops and
  auto-pass.
- **Casting:** the stack with spell and ability objects, and resolution in LIFO order. Also
  mana costs (parse `{2}{G}{G}`, hybrid, phyrexian, X), mana abilities, auto-payment from
  untapped sources with manual payment as an option, and timing (sorcery speed vs instant,
  one land per turn).
- **Permanents:** they enter and leave the battlefield. Summoning sickness is derived from
  "controlled continuously since the start of your most recent turn".
- **State-based actions:** 0 toughness, lethal damage, deathtouch damage, 0 life, 10 poison,
  21 commander damage, the legend rule, planeswalkers with 0 loyalty, tokens outside the
  battlefield, and +1/+1 / −1/−1 counter annihilation.
- **Combat:** attack and block legality (tapped, sick, defender, flying/reach, menace, can't
  block), first and double strike, trample, deathtouch, lifelink, vigilance, and damage
  assignment order.
- **Commander:** the command zone replacement (a choice), commander tax, and commander damage.
- **Tests:** a scenario test for each rule.

### M16 — Card effects

- **Effect primitives:** damage, life, draw, discard, mill, destroy, exile, bounce,
  reanimate, tokens, counters, pump until end of turn, tap/untap, sacrifice, search library
  (reusing the private search view), gain control, copy, and add mana.
- **Targeting:** target filters, legality on cast, and re-checking on resolution (fizzle).
- **Keywords** as reusable static and triggered abilities.
- **Abilities:** triggered abilities (ETB, dies, attacks, upkeep, cast, damage) with APNAP
  ordering decisions; activated abilities with costs (tap, mana, sacrifice, remove counters,
  loyalty).
- **Continuous effects** with durations, applied in layer order: control, text, type, color,
  abilities, P/T sublayers.
- **Common replacement effects:** "enters tapped", "if it would die, exile it instead", and
  prevention.
- **Templated Oracle-text recognition** that proposes scripts for common wordings. Every
  proposed script needs review and a test before a card counts as FULL.

### M17 — Pod coverage

- Script the pod's cards in inventory order until our decks are mostly FULL, with PARTIAL
  cards listing their manual parts.
- Per-deck coverage appears in the deck view and in the lobby deck summary.
- A re-import from Archidekt refreshes the coverage report.

### M18 — Rules-aware client (2D board first)

- Playable highlights and prompts (targets, modes, X, payment, attackers and blockers, trigger
  order), plus the stops and auto-pass settings.
- A clear "manual override" affordance, and pausing automation for the table.
- E2E: a scripted two-player game played entirely through intents, and a game that mixes
  automated and manual play.

### M19 — 3D table, then toys

- The three.js `TableScene` renders the same views and maps gestures to intents (see
  `3D_DIRECTION.md`). The 2D board remains the fallback.
- Then tabletop toys: dice objects, a dice tray, token bags, and a hidden draw bag that uses
  the same per-viewer privacy as libraries.

## Deliberately out of scope

Rules automation is now **in scope** (M14–M18): the engine does Arena-level bookkeeping for the
cards we support, and the players can always take over by hand. Still out of scope:

- **Judge behaviour:** tournament enforcement, penalties, "missed trigger" warnings and nagging
  reminders. Supported triggers are simply automated. Unsupported ones are resolved by hand,
  without reminders.
- **Online and competitive features:** matchmaking, accounts, cloud saves, rankings / ELO /
  medals, achievements.
- **Other formats and audiences:** sealed, draft, spectator/caster tooling.
- **Ecosystem and oversight:** a mod marketplace, anti-cheat, telemetry or analytics.
- **Code execution:** executing user-supplied or downloaded code. Card scripts are
  repository code; user behaviour stays declarative macros.

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
| Rules vs sandbox | Two inputs: rules **intents** compiled by `rules/`, and sandbox **actions** applied directly (logged as overrides when automation is on) | Arena-like play for supported cards without losing the physical table |
| Rules history | An intent is planned on a scratch copy and recorded as primitive actions (one history entry) | Undo and saves keep working; old saves never re-run changed rules code |
| Rules state | Only what the table can't show (priority, stack metadata, decisions, durations); characteristics are derived on demand | Manual overrides can't desync the engine |
| Automation priority | Cards from the pod's own decks first, by how many decks play them | Most value for our actual games |
| Renderer | Holds no rules logic; sends intents and draws views with server-provided hints | 2D and 3D clients share one engine |
