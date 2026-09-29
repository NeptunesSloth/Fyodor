# Architecture

Fyodor is heading for **Tabletop Simulator-style interaction + MTG Arena-like rules
automation + a manual sandbox override + an Archidekt-first pod workflow**.

- Everything in the table layer below (state, actions, history, views, LAN, saves) is built and
  is the stable foundation.
- The **rules layer** goes *underneath* the future 3D table.
  - **Built (M14):** the boundary (intents, compile-and-record, decisions, priority/stops, turn
    structure, land drop, manual fallback, overrides, coverage, pod inventory).
  - **Built (M15):** the core rules: mana and casting, abilities, state-based actions,
    combat.
  - **Planned:** card effects and per-card scripts (M16+).
  - The roadmap is in `IMPLEMENTATION_PLAN.md`.

```
┌──────────────────────────── Browser (React + TS) ──────────────────────────────┐
│ Renderer: 2D board today · three.js TableScene later (3D_DIRECTION.md)         │
│   gestures ──► input/intents: rules INTENT  or  sandbox ACTION                 │
│   overlays, prompts, menus, lobby, stats … ── zustand store ── REST + WS       │
└───────────────▲───────────────────────────────────────────┬────────────────────┘
                │ per-viewer view (+ rules prompt,          │ intent / action (JSON)
                │   legal-intent hints) — sanitized          │
┌───────────────┴───────────────────────────────────────────▼────────────────────┐
│ FastAPI  api/ (REST, /ws) · multiplayer/ (rooms, seats, revisions, presence)   │
│   GameSession.perform(actor, payload)                                          │
│     ├─ rules intent ──► rules/  validate · plan · settle                       │
│     │                     └─ compiles to primitive table actions (recorded)    │
│     └─ sandbox action ─────────────────────────────┐ (manual override)         │
│   game/   table engine: state · resolve · apply · history · views · visibility │
│   cards/ decks/ (Archidekt) · storage/ · assets/ · stats/ · assistant/         │
└───────────────┬────────────────────────────────────────────────────────────────┘
        data/cards.sqlite   data/app.sqlite   data/assets/   data/images/
```

## Rules of the codebase

- `game/` never imports FastAPI, SQLite or the network. It is pure Python and
  deterministic given its inputs.
- `rules/` has the same constraint. It reads card characteristics through an
  injected interface, and it never imports the renderer, FastAPI or storage.
- **The renderer holds no rules logic.** It sends intents or sandbox actions and draws the
  views it receives. Legality, costs, timing and effects are decided on the server only.
- The server is authoritative. It validates every input, resolves all randomness, applies
  it, and sends each client **its own** sanitized view.
- `storage/` knows nothing about game rules. It stores versioned JSON snapshots.

## Domain model (`backend/app/game/state.py`)

```
GameState
  id, name, format ("commander" | "constructed" | "sandbox"), created_at
  seq (actions applied == history position), settings: GameSettings
  players: {player_id: PlayerState}, seat_order: [player_id]
  cards: {instance_id: CardInstance}          # normalized — zones hold ids only
  zones: {zone_key: [instance_id]}            # "<player_id>:<zone>" or "stack"
  turn: TurnState {number, active_player, phase}
  table: TableState {monarch, initiative, day_night, playmat}
  views: [ViewContext]                        # open searches / looks (private)
  hidden_salt                                 # keys the order of hidden placeholders
  pregame (mulligans), response (response helper), arrows, log
  rules: RulesState | None                    # only when automation is on (game/rules_state.py)

PlayerState
  id, name, color, life, life_history, resources (poison, energy, …), mana (pool)
  commander_damage, commander_tax, commander_casts, city_blessing, mulligans
  deck_id, deck_name, sleeve, playmat, left

CardInstance
  id (random, re-keyed on library shuffle), card_id (printing), name, owner, controller, zone
  x, y, rotation, tapped, face_down (+ face_down_kind), face, flipped
  attacking, blocking (combat markers), locked, protected, attached_to, group, quantity
  counters, damage, effects (temporary markers), choices, stack_info, exile_group, note
  is_token (+ token, token_source), copy_of, commander_key, origin, test_object
  revealed_to: [player_id | "*"]              # an active reveal
  ability: AbilityObject?                     # stack-only ability objects
```

### Zones

Per player: `library`, `hand`, `battlefield`, `graveyard`, `exile`, `command`, `sideboard`,
`companion`, `foretell`, `setaside`. The `stack` is shared.

| Zone | Default visibility |
|---|---|
| library | nobody (not even the owner), except an active reveal or the looker/searcher during a look/search |
| hand, sideboard, foretell, setaside (rejected mulligan cards) | owner |
| battlefield, graveyard, exile, command, companion, stack | everyone (face-down cards only for the controller) |

Control means battlefield placement. A card on `P2:battlefield` is controlled by P2.

### Visibility (`game/visibility.py`)

`can_see(state, card, viewer)` is the single source of truth. It is computed from **current
facts only**: the zone, face-down state, controller, an active reveal (`revealed_to`) and open
look/search contexts (`state.views`).

There is deliberately **no memory of past sightings**. A card everyone watched get bounced to
a hand is anonymous to opponents from then on, exactly like a physical table where you'd have to
remember it yourself. Moving or shuffling a card ends any reveal. Shuffling also **re-keys** the
instance ids, so nothing links a card before and after.

## Actions, events and history (`game/actions.py`, `game/engine.py`, `game/history.py`)

```
client intent ──► resolve(state, action, rng) ──► resolved action ──► apply(state, resolved)
                  (fills random/generated                              (pure, deterministic)
                   fields: shuffle order, new ids,
                   dice results, expanded macros)
```

- Every resolved action is deterministic. Applying the same list of resolved actions to the
  same base state always produces the same state.
- `History` holds the base state, the resolved actions, a cursor, and periodic snapshots
  (every 20 actions).
  - **Undo** moves the cursor back and rebuilds the state from the nearest snapshot by
    replaying up to the cursor.
  - **Redo** moves the cursor forward and applies the next action.
  - A new action after an undo discards the redo tail.
- Randomness lives only in `resolve`. Undoing a shuffle restores the previous library order
  exactly, and redoing it gives the same new order.
- **Compound actions.** A macro (`run_macro`) is expanded in `resolve` into ordinary actions,
  resolved one after another on a scratch copy, and recorded as **one** history entry. The
  rules layer uses the same mechanism (below).
- `undo_policy` (everyone / own / host) is checked server-side.

### Log

`LogEntry {seq, turn, phase, actor, ts, parts[]}`. `parts` is a template of text and card
references. A card reference records who could see the card at that moment, and the view
builder renders "a card" for everyone else.

## Views (`game/views.py`)

`build_view(state, viewer)` where `viewer` is a player id, `SPECTATOR`, or `OMNISCIENT` (local
hot-seat "open table" mode only).

- **Libraries** are sent as `{count, known: [[index, id]]}`. Only cards the viewer can see
  right now (a reveal, a look at the top N, a search) are listed. Hidden library cards are
  never sent as objects, and their ids never leave the server.
- **Hands and other owner-only zones:** visible cards keep their ids. Every hidden card becomes
  an opaque placeholder `hidden:<zone>:<n>`. Placeholders are ordered by a keyed BLAKE2b hash
  (per-game secret salt), so the order says nothing about draw order or about a card seen
  earlier. A placeholder carries only `{id, hidden, owner, controller, zone, face_down}`: no
  printing id, Oracle id, name, image, set/collector number, counters, notes or markers.
- **Clients act on placeholders.** The server maps them back for that viewer
  (`resolve_placeholder`), so real ids are never needed.
- **Face-down permanents** are shown to everyone else as a card back plus their
  `face_down_kind`; the identity goes only to the controller.
- **Log lines** name a card only for players who could see it at that moment.
- Protocol tests (`tests/test_protocol_privacy.py`, `tests/test_views.py`) serialize every
  viewer's REST view and WebSocket frames after each step of mixed games. They assert that no
  hidden id, name, printing id or image reference appears anywhere. The Playwright specs check
  the same on real browser traffic.

## Rules layer

**Status:**

- **Built (M14):** intents, compile-and-record, the rules state, decisions, priority and stops,
  the turn structure with its turn-based actions, the land drop, manual resolution, override
  logging, coverage and the pod inventory.
- **Built (M15):** mana abilities and automatic payment, casting, activated and loyalty
  abilities, state-based actions, combat and the commander rules.
  - Code: `mana`, `costs`, `casting`, `sba`, `combat`.
- **Built (M16 foundations):** automation levels OFF / ASSISTED / FULL with per-feature
  options, per-player RESPONSE / stops / temporary overrides / remembered answers, MANA
  AUTO / ASK / MANUAL with source protection, reconciliation after manual play, per-card MANUAL,
  rules object identity, last known information, event batches, damage events, leaving the
  game, failure containment, EXPORT RULES SCENARIO, script Oracle hashes, REPEAT LAST
  VALIDATED SEQUENCE. See `AUTOMATION_UX.md`.
  - Code: `reconcile`, `leave`, `scenario`, `research`, plus the models in `rules_state`.
- **Next (M16):** triggers, effect primitives and selectors, the cost pipeline, permissions
  and restrictions, linked abilities, continuous effects and layers, replacement/prevention,
  copies (`IMPLEMENTATION_PLAN.md#m16--rules-language`).
- **Code:** `app/rules/` (`engine`, `view`, `characteristics`, `oracle`, `coverage`,
  `inventory`, `cards/`, …) plus `app/game/rules_state.py` (data) and
  `app/game/handlers/rules.py` (pure replay).

The goal is Arena-level automation of normal play **for the cards and mechanics we support**,
without losing the sandbox. Players make decisions; the engine does the bookkeeping. Anything
unsupported, or anything the pod wants to do differently, is resolved by hand with the existing
table tools.

### Two kinds of input

| Input | Examples | Handled by |
|---|---|---|
| **Intent** (a game decision) | `play_land(card)`, `cast_spell(card, …)`, `activate_ability(card, ability)`, `declare_attackers([(card, target)])`, `declare_blockers([(blocker, attacker)])`, `pass_priority`, `choose(decision, answer)`, `concede` | `rules/`: validated against the rules, then compiled into primitive table actions |
| **Sandbox action** (physical manipulation) | `move`, `tap`, `counter`, `create_token`, `set_life`, `run_macro`, … (the existing ~100 actions) | `game/` directly. With automation on, it is logged as a **manual override**. |

The renderer maps gestures to inputs in one client module (`input/intents`):

| Gesture | Automation on | Automation off (sandbox) |
|---|---|---|
| Drag a land from hand to the battlefield | `play_land(card)` | `move(card → battlefield)` |
| Drag a spell from hand onto the table or stack | `cast_spell(card)` | `move(card → stack/battlefield)` |
| Drag a creature forward in declare attackers | `declare_attackers([(card, target)])` | `attack` marker |
| Drag a blocker onto an attacker | `declare_blockers([(blocker, attacker)])` | `block` marker |
| Click an ability on a card | `activate_ability(card, ability_id)` | context-menu tools |
| Space / "Pass" | `pass_priority` | `phase` (next step) |
| Hold the override modifier (or menu → *Do it manually*) | the sandbox action, logged as an override | same |

The renderer never decides legality. The server sends hints in the view (which of *your*
cards are playable, which creatures can attack, the pending prompt), so the client can
highlight options like Arena. A rejected intent returns a reason ("Llanowar Elves can't
attack: it came under your control this turn") and offers the manual override.

### Where rules state lives

`GameState.rules: RulesState | None`. It is `None` for tables that never had automation, so
those games, saves and tests behave exactly as before. Turning automation OFF keeps it
**dormant** (still tracked, not shown); turning it back on or resuming from PAUSE runs
`rules/reconcile` before the engine acts again.

- **The table stays the source of truth for physical facts:** zone, tapped, counters, damage,
  attachments, control, life. Rules state holds only what the table can't show:
  - priority holder and passes;
  - stack-object metadata (targets, modes, X, costs paid);
  - the pending decision;
  - turn bookkeeping (lands played, spells cast this turn, attacks declared, when each
    permanent came under its controller's control);
  - registered continuous effects with durations, delayed triggers and the trigger queue.
- **Characteristics are derived, never stored.** Current power/toughness, types, abilities and
  controller are computed on demand from printed data plus continuous effects, in layer order
  (`rules/characteristics`). A manual override (say, moving a card or adding a counter) is
  simply picked up by the next computation; nothing goes out of sync.

### Objects, last known information and events

- **Physical card vs rules object.** A `CardInstance` keeps its id for rendering and history;
  its rules object is `rules.object_id(card)` = `"<card id>.<n>"`, and `n` changes whenever the
  card changes zones (a control change is not a zone change). Per-object bookkeeping
  (once-per-turn, loyalty, stop-after, damage sources) uses object ids, so a flickered
  permanent is a new object with no memory of the old one.
- **Capture → apply → track.** Before every applied step (sandbox action, or each step of an
  intent) `rules_state.capture` snapshots the zones and everything on the battlefield and the
  stack (in memory only). After the step, `track` compares: zone changes get new object ids,
  the old object's snapshot becomes its **last known information** (`rules.lki`, kept for
  two turns), and the step's **events** (zone changes incl. created/ceased objects, counters,
  player counters, taps) are recorded with one shared **batch** number. Handlers add what a
  diff can't see: `rules_damage` emits damage events (source object → recipient), and
  `change_life` emits life loss/gain, so damage and life loss are separate events.
- **Simultaneity.** State-based actions move all dying permanents in one step (one batch);
  combat damage is one step.
- Events are consumed by the next intent (M16's trigger collector); manual events are first
  taken in by the engine (a land put onto the battlefield by hand counts as the land drop).

### Determinism, history and replay

An intent goes through the same pipeline as a macro:

1. **Validate** against the current state: timing, priority, costs, targets and
   restrictions.
2. **Plan** on a scratch copy: pay costs, move to the stack, resolve, run **settle**
   (state-based actions and trigger collection, repeated until stable). The result is a list of
   primitive table actions plus rules-state patches.
3. **Record** that plan in the history entry (`r`). `apply` replays it, and stays pure.

Consequences:

- **Undo** takes back a whole intent (cast + costs + triggers) as one step.
- **Replay never re-runs rules code.** Old saves replay exactly even after card scripts
  change, because only the recorded primitive actions are applied.
- Randomness (random discard, coin-flip cards) is resolved once and recorded, as today.

### Decisions (prompts)

When the engine needs a choice (targets, modes, X, mana payment, attack/block declarations,
damage assignment order, "you may", ordering simultaneous triggers, discarding to hand size,
choosing a replacement effect) it stores a single pending `Decision` addressed to one player.

- **The chooser** gets the prompt in their view, with the legal options.
- **Everyone else** sees only "Alice is choosing targets".
- Options that reference hidden cards are only sent to the chooser.
- The answer comes back as a `choose` intent, validated against the stored options.
- There are no timers.

### Priority and stops

- The engine grants priority and waits for `pass_priority` (optionally `until` a condition).
- `engine.is_stop` decides whether the engine passes *for* a player: forced stops, then HOLD
  AFTER THIS RESOLVES, then PASS UNTIL …, then FULL CONTROL / RESPONSE ON, then RESPONSE AUTO
  (stops + real responses + optional bluff stops) or OFF. Preferences live in
  `rules.prefs[player]` and are changed with `set_prefs`, which is accepted at any time.
- Auto-passes are indistinguishable from passes; nothing reveals why someone passed.
- With automation off, the existing response helper stays as the lightweight fallback.

### Card behaviour and coverage

- **Where behaviour comes from:**
  - keyword abilities (flying, trample, deathtouch, lifelink, …) are implemented once in
    `rules/keywords`;
  - card behaviour lives in `rules/cards/`, keyed by Oracle id and built from a small library
    of effect primitives (deal damage, draw, destroy, exile, return, create token, counters,
    pump until end of turn, search, sacrifice, gain control, …);
  - common templated Oracle text is recognised by a parser that proposes scripts;
  - hand-written scripts always win.
- **Coverage** is computed per card and exposed everywhere cards are shown: card inspector,
  deck view, lobby and the coverage report.

  | Coverage | Meaning |
  |---|---|
  | **FULL** | Everything on the card is automated and covered by a scenario test. Vanilla cards and cards with only supported keywords count as FULL automatically. |
  | **PARTIAL** | Some abilities are automated; the rest are listed as manual steps. |
  | **MANUAL** | The card is a correctly typed object (it can be cast, move, attack), but its text is resolved by hand. |

- **Manual fallback:** when an unsupported ability resolves, or a spell whose effect is
  MANUAL, the engine pauses with a `manual_resolution` decision for its controller. That player
  sees the Oracle text and has the sandbox tools; **Done** hands control back and settle runs
  again.
  - The host can pause automation for the table at any time and resume it later.
- **Security:** card scripts are code in this repository, reviewed and tested like any other
  code. Nothing downloaded or user-authored is executed. User-defined behaviour stays
  declarative macros. Oracle text is parsed as data, never evaluated.

### Tests

- Existing suites run with automation off and stay unchanged.
- Rules tests are scenario tests. Each one builds a board from a compact fixture, performs
  intents and asserts the resulting table and log.
- A card is only FULL when it has a scenario test.
- A replay test checks, for every rules scenario, that re-applying the recorded history
  reproduces the live state exactly.

## Multiplayer (`multiplayer/`)

- `GameHub` maps a game id to a `Room` (game session, seats, connections, revision, presence).
- A seat is claimed with a room code (plus an optional password). The server returns a random
  **seat token**, and reconnecting with that token reclaims the seat. Dropped devices get a
  60 s reconnect grace.
- Each connection sends `{"type":"action", "action":{...}, "seq":n}`. The server checks that
  the acting player matches the seat (hot-seat games allow any seat), applies the action, then
  broadcasts a fresh sanitized view with an increasing **revision** to every connection. Clients
  ignore stale revisions and ask for a resync on a gap.
- Every inbound message is validated by pydantic discriminated unions. Unknown types or invalid
  payloads get an `error` reply, and the game state is left unchanged.
- All mutations to a room are serialized through a per-room `asyncio.Lock`.
- Rules intents (planned) use the same message and the same path.

## Storage

- `cards.sqlite` (rebuildable): `printings`, `oracle_defaults`, `card_names`, `printings_fts`
  (FTS5), `meta`.
- `app.sqlite` (user data): `decks`, `deck_cards`, `saves`, `macros`, `pod_players`,
  `game_results`, `game_result_players`, `assets`, `schema_version`.
  - All reads and writes share one connection guarded by a lock (`storage/db.locked`).
- Save format `fyodor-save` v4, with tested migrations v1→v4 in `storage/save_format.py`. A
  rules-state field will arrive as a new version with a migration that fills `rules: null`.

## Extension points

- `rules/`: today, the `RulesModule` protocol (`after_action → list[Suggestion]`), advisory
  only, with none enabled. It becomes the rules layer described above. The advisory hook stays
  for optional helpers.
- `assistant/`: a read-only helper fed only the asking player's sanitized view
  (`build_context`), disabled by default.

## Risky decisions and mitigations

| Risk | Mitigation |
|---|---|
| Full-view broadcasts get large with 4 players and hundreds of cards | Views omit card metadata (the client caches card data by id), and the client reconciles object identity. Delta sync can be added behind the revision/version fields. |
| Replay-based undo cost grows with game length | Snapshots every 20 actions bound the replay to 20 applies. |
| Hidden-info leaks through ids, log text, counts or rules prompts | Re-keying on shuffle, per-viewer log rendering, prompts addressed to one player, and serialized-JSON leak tests on every view and frame. |
| Rules automation diverges from what the players see or want | The table is the source of truth, characteristics are recomputed on demand, every automated step is logged and undoable, and a manual override is always available. |
| Rules code changes break old saves | History records compiled primitive actions, so replay never re-runs rules code. |
| Card scripts become an attack surface | Scripts are repository code only; user and downloaded content stays declarative data. |
| Card database schema drift from Scryfall | The importer stores raw faces and parts JSON, and pulls fields defensively. |
| Undo in multiplayer can be abused | Undo is logged publicly, and `undo_policy` supports own-actions or host-only. |
