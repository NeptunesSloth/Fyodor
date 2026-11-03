# Implementation Plan

Fyodor is an offline-first digital tabletop for **Commander** (and only Commander), for one
trusted pod. The target is:

> **Tabletop Simulator-style physical 3D Magic + MTG Arena-level rules automation + Master
> Duel-style response/activation UX + a manual tabletop override + an Archidekt-first pod
> workflow + offline game-night reliability.**
>
> Four people, four Commander decks, one LAN table, and a manual fallback that never
> prevents us from finishing the game.

- **Milestones 1–15 (stable foundation):** the sandbox table, LAN, privacy, saves and history,
  Archidekt, pod stats, macros, assets, profiles, mulligans, plus the rules boundary (M14) and
  the core rules primitives (M15). This is extended, never rewritten, and its tests stay
  green.
- **Milestones 16–20:** the rules language (M16), Commander card knowledge researched from the
  current Comprehensive Rules and the Commander-legal Oracle pool (M17), the digital card game
  UX (M18), the physical 3D client (M19), and game-night hardening (M20).
- **Scope:** Commander only. The engine implements the general Magic rules Commander games need
  (priority, the stack, layers, replacement effects, copies, combat, multiplayer…); card and
  mechanic coverage only counts **Commander-legal** cards. No other formats, no draft/sealed,
  no rankings, no spectator product, no judge penalties.
- **Priority:** our pod decks and commanders first, then reusable mechanics by how many
  Commander-legal cards they unlock, then the rest of the Commander pool.
- **Rules are researched, not remembered:** behaviour is checked against the current official
  Comprehensive Rules (`docs/RULES_RESEARCH.md`), fetched and indexed at development time. The
  finished app never needs the Internet.

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
| 15 | **Core rules primitives:** mana costs and payment, casting and the stack, activated abilities, state-based actions, combat, commander rules | ✅ done |
| 16 | **Rules language:** events and event batches, object identity, LKI, costs, targeting, choices, triggers, continuous effects and layers, replacement/prevention, permissions/restrictions, copies, effect primitives, multiplayer leaving | ✅ built: every Commander-legal card is FULL (32,068 of 32,068; see M16) |
| 17 | **Magic knowledge (Commander-only):** CR research/index/diff tooling, Oracle template library over the Commander-legal pool, mechanic registry, safe generated scripts, Commander + pod coverage | ✅ built: CR research tooling, the Oracle template library and pod coverage (see M17) |
| 18 | **Digital card game UX:** AUTOMATION OFF/ASSISTED/FULL, RESPONSE OFF/AUTO/ON, MANA AUTO/ASK/MANUAL, stops, prompts, stack helper, highlights, auto-yields, reconciliation | ✅ built, engine and client (see M18, `AUTOMATION_UX.md`) |
| 19 | **Physical client:** three.js table, physical cards, camera, hands, playmats, dice/cannon/bags, 2D fallback | ✅ table built (see M19, `3D_DIRECTION.md`), with the table toys: the dice cannon, the Bag of Extras and the hidden draw bag |
| 20 | **Game-night hardening:** crash recovery, durable autosave, idempotent actions, backups, DB recovery, offline test, long sessions, device soak | ✅ built (see M20, `GAME_NIGHT_RECOVERY.md`); still to do: a multi-hour soak on real game-night hardware |

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
- **Built, M15b: state-based actions**, tested in `test_rules_sba.py`. They're checked before
  anyone gets priority and after every intent:
  - players losing to 0 life, 10 poison, 21 commander damage or drawing from an empty
    library, with the last player standing named the winner;
  - creatures dying to 0 toughness, lethal damage or deathtouch damage (indestructible
    respected);
  - planeswalkers with no loyalty (they enter with their printed loyalty);
  - the legend rule, as a decision;
  - tokens ceasing to exist outside the battlefield;
  - +1/+1 and −1/−1 counters cancelling out;
  - the commander's optional move to the command zone from graveyard or exile, asked once
    per arrival.

  Manual edits are picked up the next time the engine acts, so it never fights the players
  mid-edit.
- **Built, M15c: combat**, tested in `test_rules_combat.py`.
  - Attackers are declared as a decision answered by `declare_attackers`. Eligibility covers
    tapped, summoning sickness, haste and defender. Targets are opponents and their
    planeswalkers; vigilance means the attacker doesn't tap.
  - Blockers are declared in turn order, one defending player at a time, answered by
    `declare_blockers`. Flying/reach and menace are enforced.
  - Combat damage is dealt all at once. There's a separate first-strike round (double strike
    deals in both). Trample assigns lethal damage first; deathtouch makes 1 damage lethal;
    lifelink, commander damage and damage to planeswalkers are handled.
  - With no attackers, the blockers and damage steps are skipped. Combat markers are cleared
    at the end of combat.
  - Multiple blockers are assigned damage in declaration order (lethal to each, then the
    rest). Choosing that order interactively is a later refinement.
- **Built, M15d: activated and loyalty abilities**, tested in `test_rules_abilities.py`.
  - Costs are paid automatically when they're `{T}`, mana (with X), "Sacrifice this…",
    "Pay N life" or removing counters from itself. Any other cost is refused with "pay it by
    hand".
  - Loyalty abilities are sorcery speed, once per turn per planeswalker, and check that
    there's enough loyalty. "Activate only as a sorcery" and "only once each turn" are
    respected.
  - The ability goes on the stack and resolves by hand, with its text shown in the prompt,
    until its effect is scripted (M16).
  - Hints list your activatable abilities, and smart passing now uses the real "can I
    activate anything" check.

**M15 is complete.** The next milestone is M16 (card effects), prioritised by the pod
inventory.

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

### M16 — Rules language

Reusable Magic semantics, researched against the current Comprehensive Rules.

**Built (this branch):**

- **Automation levels** OFF / ASSISTED / FULL with per-feature options and presets (CUSTOM
  when any option differs). OFF keeps the rules state dormant; turning automation back on or
  resuming **reconciles** with the table and asks what it can't infer (`AUTOMATION_UX.md`).
- **Rules object identity:** a card changing zones becomes a new rules object
  (`<card id>.<n>`); a control change doesn't. Once-per-turn and loyalty bookkeeping is per
  object. Sandbox moves between battlefields keep damage, counters and tapped state.
- **Last known information:** captured *before* each step for everything on the battlefield
  or the stack; kept for two turns.
- **Events and batches:** zone changes (incl. created and ceased objects), damage, life
  loss/gain, counters, player counters, tap/untap, one batch per applied step. SBA deaths
  are one simultaneous move. Combat damage records source → recipient damage events
  separately from the life loss they cause.
- **Player counters** are generic (poison, energy, experience, rad, tickets, anything).
- **Leaving the game** (concede or loss): owned objects leave, control effects end, their
  stack abilities cease, combat against them ends, monarch/initiative pass on, their seat
  stays as a record.
- **Payment:** AUTO / ASK / MANUAL, PREFER / NORMAL / SAVE sources, exact-source payment,
  CANCEL before anything moves. Split cards and adventures cast as the chosen half.
- **Failure containment:** intents compile on a scratch copy; an unexpected engine error is an
  AUTOMATION ERROR that changes nothing. **EXPORT RULES SCENARIO** turns it into a fixture.
- **Script versioning:** scripts record the Oracle hash they were validated against; changed
  text means PARTIAL + REVIEW NEEDED.
- **REPEAT LAST VALIDATED SEQUENCE** (N times or until a condition), every iteration through
  the engine.

**Built (M16b):** the trigger engine on the event batches (enters / dies / leaves the
battlefield with last known information / upkeep / end step / attacks; 603.3 timing; APNAP
with a private ORDER decision and AUTO ORDER IDENTICAL TRIGGERS; targets when put on the stack;
"may" on resolution with remembered answers; ASSISTED confirmation); target selectors with
hexproof/shroud, checked on cast and on resolution (608.2b); effect primitives (draw, life,
noncombat damage events with lifelink/deathtouch, pump/grant as continuous effects, destroy,
exile, bounce, tap/untap, scry/surveil with private choices and ordering, player counters);
continuous effects with layers 6 and 7a–d, timestamps, locked affected sets, end at cleanup;
"enters tapped" as a replacement; the Oracle template library (`app/rules/scripts.py`) that
turns exact wordings into declarative definitions; flash. Commander FULL coverage went from
921 to 2,434 cards.

**Next, in order:** more templates by the ranked queue (mana-ability wordings, cycling,
protection, regenerate, "can't block", "whenever another …" triggers, intervening-if); token
creation and counters primitives (with doubling/replacement); the cost pipeline (alternative/additional costs,
increases/reductions, Convoke/Delve/Improvise); cast/play permissions (Flashback, Escape,
Foretell, Adventure, cast from exile, …) and restrictions; linked abilities ("exiled with");
continuous effects with the full layer system, timestamps and dependencies; replacement and
prevention with affected-player choice and re-evaluation; copiable values; turn modification
(extra turns/combats); WIN_GAME / LOSE_GAME primitives; an SBA audit generated from the CR.

### M17 — Magic knowledge (Commander-only)

- `tools/rules_research`: fetch the official Comprehensive Rules (TXT), store it versioned
  with metadata and SHA-256, index it into searchable sections, and diff new versions into
  `data/reports/rules_changes.md` with affected engine components.
- A template library over the **Commander-legal** Oracle pool (`legalities.commander ==
  "legal"`): ability segmentation, normalised templates, mapping to tested primitives,
  declarative generated scripts only where every piece is tested, FULL only with scenario
  tests. Banned cards are COMMANDER_BANNED and leave the statistics.
- Commander eligibility (not "legendary = commander") and pairings (Partner, Partner with,
  Friends forever, Background, Doctor's companion, "can be your commander") derived from the
  CR and Oracle text; one tested color-identity implementation for deck checks and rules.
- Reports: `commander_rules_coverage.md/json`, `commander_coverage.md`, the missing-feature
  queue ranked by how many Commander-legal cards each missing mechanic would unlock. The pod
  builds new decks all the time, so the goal is **the whole Commander-legal pool**, not a
  fixed list of decks; there is no pod-deck shortcut.

### M18 — Digital card game UX — built

`AUTOMATION_UX.md`: the HUD (AUTO / RESP / MANA) and its settings panel (segmented levels,
stops grid, overrides), prompts for every decision kind, The Stack panel with Pass / Respond /
Auto-Pass, the Pay panel with suggested sources, targeting on the table, legal-action
highlights, the per-card automation menu and the AUTOMATION ERROR panel.

### UI overhaul — built

A theme-driven design system (framed panels, Cinzel/Inter bundled offline, segmented controls,
switches, action buttons), a launcher with the plane's table live behind the menu, Arena-style
lobby seat cards with commander art and deck automation coverage, and the table themes below.

### M19 — Physical client — table built

The three.js table renders the same per-viewer views and maps gestures to intents
(`3D_DIRECTION.md` §0). Table themes are Magic planes (Dominaria default; Ravnica, Innistrad,
Theros, Zendikar; then Kamigawa, Amonkhet, Ixalan, New Phyrexia, Lorwyn). The 2D table remains
a first-class renderer; different players may use different renderers in one game. The table toys are
built (`3D_DIRECTION.md` "Table toys"): the dice cannon (a volley, or "Who goes first" with ties re-fired), the
Bag of Extras by each seat and the hidden draw bag, every outcome decided and logged on the server. Next: token piles.

### M20 — Game-night hardening — built (`GAME_NIGHT_RECOVERY.md`)

Crash recovery with seat reclaim (room metadata + checkpoint + a journal of every change,
replayed at start), idempotent client actions (`client_action_id` → ACCEPTED / REJECTED /
ALREADY_APPLIED, remembered across restarts) with a client outbox that resends after a
reconnect, connection states with pending actions, graceful shutdown, pre-migration backups,
BACKUP FYODOR / restore, a DB recovery mode, an offline E2E and a long-session test. Still to
do: a multi-hour device soak on real game-night hardware.

### Elimination activity hub — built (`ELIMINATION_HUB.md`, 2026-11-01)

A player eliminated early gets a compact hub instead of only spectating:
- Spectate: the public view only, with a leak test.
- A private Practice Table: a one-seat sandbox with their own deck that never touches the live game.
- Opening hands.
- Deck Lab: a copy of the deck. The host computer opens it in the deck editor; guests save a list in the browser.
- Links to Pod stats and the Card browser.
- A live-game pill with public notices ("X was eliminated", "Final two players remain") and Return to live game.

Dice & toys (a local dice tray, a just-for-fun random player picker and a tally; nothing reaches the live game) are built.
A Game log link opens the table's own log drawer, and Deck Lab compares your deck with the one at the table (`game/DeckChanges.tsx`).

### Spectator side activities — 1-5 built (`SPECTATOR_ACTIVITIES_MILESTONE.md`, 2026-11-02)

For eliminated players and spectators, all outside the live match (none creates a game action or reaches saves):
- Watch + PiP: the practice table shows a compact live summary (life, poison, commander damage, turn, stack, log),
  built from the spectator view.
- A next-game deck queue, proposed (not readied) when the pod returns to the lobby; a spectator can take an open seat.
- A public-only damage sandbox that works out a what-if combat with the engine's own damage step.
- Session-only fake-point predictions, hidden until the game ends.
- Rate-limited reactions, which each player can mute, and a host's table-wide switch.

Not started: Spectator Points cosmetic progression (6).

### Post-game flow — built (`3D_DIRECTION.md` §7a)

After a result there is a winner spotlight, then a vote, which the host can force:
- **Rematch — same decks**: a fresh game with the same seats, decks and settings, and a new result record.
- **Return to lobby**: the pod stays connected, with the previous decks preselected.

When the rules engine ends a game, the result is offered for one-click confirmation. Undoing the deciding action withdraws it.

**View final board:** after a recorded result the table is read-only (actions, undo, restores and deck loads are
refused on the server); the result panel folds into a small bar that reopens the vote.

### Game night / match flow — built (`GAME_NIGHT_FLOW.md`)

Built:
- A persistent pod lobby.
- The pod turn-order rule: d20 rolls for game 1, then the previous winner goes last.
- The pre-game commander intro, with Skip.
- An agreed ending.
- A winner spotlight, which also follows the rules engine's result.
- A rematch vote.
- Elimination notices.

- The host arranges seats in the lobby (arrows or drag); the turn-order setting gains "seats" (seat 1 first), and
  under the pod rule the winner-goes-last order follows the host's seating.
- The game history keeps each game's turn order, how it was set and its d20 rolls.
- Each game's elimination order (who went out, on which turn, and how) and a compact, public-only final-board snapshot, kept
  with the result and shown in the session recap and Pod stats (`GAME_NIGHT_FLOW.md`, "Pod session and game are different objects").

### Tabletop quality-of-life — all 17 aids built (`TABLETOP_QOL_MILESTONE.md`)

Built:
- The private choice drawer and the pending decision indicator.
- Token stacks with a ×N count, split and stack by hand. With rules automation on, the engine works on separate tokens.
- Owner/controller marking.
- X/mode badges.
- Commander damage at a glance: hover a commander, plus a whole-table matrix.
- Attachment lines, shown on hover or selection.
- The combat lane view.
- Focus: C for a card, K for the stack, X for combat, in 3D and 2D.
- Auto-centre: Off, Important or On.
- Nudge, reactions, the countdown, card notes and the session recap.

Undo: the host's undo setting (everyone, own actions only, or host only) is enforced on the server. At a LAN table an
undo the setting refuses can be requested ("Bob asks to undo: cast Sol Ring — Approve / Decline"), and undoing an
action that showed hidden information or a random outcome (a draw, a look, a reveal, a search, a shuffle, a roll)
asks the table under every setting. Hot-seat tables undo directly.

Table permissions: the host's "Who may change a player's cards" setting (everyone, or each player and the host) is
enforced on the server for manual table edits only (`game/table_rights.py`); rules actions, looking, life totals and the
table's procedures are never limited, and hot-seat tables ignore it.

The public choice wheel: a radial picker for public, non-target choices (a color, a type, a player, a number, a coin),
which the server marks; Settings can turn it off.

### Full UI / 3D tabletop redesign — done in rounds (`UI_REDESIGN_BRIEF.md`, `UI_REFERENCE_STUDY.md` §20–31)

The instruction set for the redesign: `frontend-design` drives creation, `impeccable` critiques each
implemented pass, verified in the running app; phases A–E (design system and table shell, core
tabletop, rules UX, 3D/camera, game flow). Built in PR #35's rounds, each recorded in
`UI_REFERENCE_STUDY.md` §20–31: the 2D rework, the Oops-style 3D table, the seat buttons, life hearts,
importer and the game-night scenes.

## Deliberately out of scope

- **Other formats:** Standard, Modern, Pioneer, Legacy, Vintage, Pauper, Brawl, Oathbreaker,
  draft, sealed. Card and mechanic work only targets Commander-legal cards (a host setting may
  allow non-legal cards for house rules; they get no dedicated development).
- **Judge behaviour:** tournament enforcement, penalties, "missed trigger" warnings. Supported
  triggers are automated; unsupported ones are resolved by hand, without reminders.
- **Online and competitive features:** matchmaking, accounts, cloud saves, rankings / ELO.
- **Spectator/caster product work**, telemetry, analytics, a mod marketplace.
- **A runtime AI judge:** research tooling may help developers; live outcomes are decided by
  the deterministic engine only.
- **Code execution** of user-supplied or downloaded code. Card scripts are repository code or
  declarative data; user behaviour stays declarative macros.

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
| Automation priority | Mechanics ranked by how many Commander-legal cards they unlock | The pod keeps building new decks: the whole pool matters |
| Renderer | Holds no rules logic; sends intents and draws views with server-provided hints | 2D and 3D clients share one engine |
