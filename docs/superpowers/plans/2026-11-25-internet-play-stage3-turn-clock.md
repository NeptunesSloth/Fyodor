# Internet Play Stage 3 (Turn Clock) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An optional, server-owned turn clock for LAN/internet tables: a bank per player, an uncharged buffer per decision, and at zero either the safest legal default or just "0:00". It never concedes or eliminates anyone.

**Architecture:** A pure model (`app/game/turn_clock.py`) works out who the engine is waiting on and charges them with server monotonic time. A pure rules module (`app/game/clock_defaults.py`) picks the safest legal answer for each kind of wait, and cites the Comprehensive Rules for each. A per-room asyncio task (`app/multiplayer/turn_clock_driver.py`, modelled on `bots.py`) wakes at the next deadline and acts under the room's existing `room.lock`. The whole clock (settings and banks) lives on `GameSession`, beside `table_snapshots`, and is saved in the save's `extras`. It is never part of `GameState`, so it is outside history, replay and undo.

**Tech Stack:** Python 3.12, FastAPI, pydantic, pytest (`backend/`); TypeScript, React, Vite, Vitest (`frontend/`). No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-21-internet-play-design.md`: "Stage 3: Turn clock", the Anti-goals ("A clock that makes a player lose the game by timing out") and "Review gate (every stage)". Rules references come from `data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt`.

**Stage 2 dependency: none.** The clock changes only the game, session, hub, game routes and the table UI. It never touches the launcher, `netguard.py`, the tunnel or host identity. Branch `internet-play-stage3` from `master` after Stage 2 has merged. If Stage 2 has not merged yet, branch from `internet-play-stage1`; the only overlap is merge conflicts in `api/games.py` and `multiplayer/hub.py`.

## Global Constraints

- The clock is "Off by default, so pod nights are unchanged". Defaults: "bank per player (default 25 minutes)" = 1500 s; "buffer per decision (default 30 seconds, not charged)"; at zero "**Act for the player** (default) or **Only show it**"; disconnect "grace period (default 2 minutes, host can extend)" = 120 s.
- "Only the player the server is waiting on (priority or a pending decision)" is charged. Nobody is charged "while the server resolves, during another player's choices, while automation is paused, or while a player is disconnected within a grace period".
- At zero the server "never concedes or eliminates". "The log says the clock acted." "The host can add time or turn the clock off at any moment." After zero, "each later decision still gets its full buffer".
- "The server owns the clock and uses its own monotonic time. Client timestamps are ignored." Clients draw the countdown from the remaining time and the server's send time. Lag allowance is the buffer; there is "no per-move lag model".
- "Other players see whose clock is running and each bank, never what the decision is." The clock adds no new waiting.
- Clock data has defaults ("old saves load with the clock off"), survives save/load, and is "excluded from undo so undoing does not refund time".
- "Sandbox, practice and solo tables: the clock is not offered." In this codebase "solo" means the hot-seat `local` room.
- "A timeout and a player action can never both apply": the driver uses the existing `room.lock`. There is no second lock or queue.
- Project policy (`.claude/skills/fyodor-game-development/SKILL.md`): the server is authoritative; hidden information never leaks, including by omission; every behaviour has a scenario test with real Oracle text, `replay_matches` and a save/load round trip.
- Every default answer cites its rule number in a code comment. Rules come from the file above, never from memory.
- Payloads have strict schemas (`extra="forbid"`, bounded numbers). There is no new `except Exception`, bare `except` or silent fallback, and host checks fail closed.
- Before every commit, from `backend/`: `.venv/Scripts/ruff check . && .venv/Scripts/mypy app tools`. Each task's own test files pass before its last commit. The full suite (`.venv/Scripts/python -m pytest -n 8 -q`) passes at Tasks 3, 5 and 8. Any frontend change: `npm run typecheck && npm test` in `frontend/`.
- UI work follows `.claude/skills/fyodor-ui-design/SKILL.md`: text as well as colour, `tabular-nums`, reduced motion respected, no burning rope.

## Review Focus

1. **A phone sleeps mid-decision and its socket drops for 90 seconds.** Within the grace period nothing is charged, and on return the same decision has the buffer and bank it had. (Task 3)
2. **A player's computer clock is minutes wrong, or a background tab's timers were throttled.** The countdown still matches the server and never shows less than 0:00 or more than the bank. (Task 7)
3. **Fyodor restarts mid-game.** The banks come back, the downtime is not charged, and the clock starts again without anyone acting. (Task 5)
4. **A player clicks illegal actions, or another player acts, while the player's buffer runs.** The buffer is not refilled; only a new decision gets a new buffer. (Task 1)
5. **Every default is refused** (a manual resolution, or an engine refusal Fyodor did not foresee). The result is one log notice and nothing applied: no loop and no concede. The host can still add time or turn the clock off. (Task 3)

---

## Resolved ambiguities (the executor follows these; the owner may overrule)

- **"Clock fields live in game state."** The clock's settings and banks live on `GameSession.clock`, not in `GameState`/`GameSettings`. They are saved under the save's `extras["clock"]` (as `table_snapshots` already are) and in the room's crash-recovery metadata. A `GameState` field that changes without a recorded action would break `replay_matches`, and undo would refund it. Settings changed through the recorded `configure` action could be undone by players. The executor does neither.
- **The clock runs only while rules automation is on** (Assisted or Full) and not paused. With automation off the server waits on nobody. The lobby offers the clock at any automation level and says this in its hint.
- **Rules confirmations at Assisted** (`sba_confirm`, `combat_damage`, `trigger_confirm`) are answered "yes": 704.3, 510.2 and 603.3 say these happen. Any other `confirm` is a "may" and is declined.
- **A decision part-way through casting** (`rules_state.cancelable(d)`, for example choosing targets) is cancelled. Under 601.2 and 733.1 the cast is reversed, which is safer than the clock choosing targets for the player.
- **`manual_resolution` and `reconcile` are left to the table.** These are facts about what was done by hand, not choices. Policy: "wrong automation is worse than manual". The player is still charged, and at zero the log says the clock cannot answer.
- **Nobody is charged while no seated human is connected.** This stops a table left running, or restored after a restart, from being played forward by the clock.
- **Bank size changes never refill banks.** A bank is filled once, the first time the clock runs for that player in the game. After that only **Add time** changes it, so turning the clock off and on refunds nothing. Buffer, at-zero mode and grace changes apply at once.
- **A late click.** A player action sent from a view older than the clock's action for that player is refused ("seen revision" guard, Task 6). This is how "a timeout and a player action can never both apply" holds across network latency, not only inside the lock.
- **Saves and restarts.** A decision that was waiting when the game was saved, or when Fyodor restarted, starts again with a full buffer on load. The banks are kept.

## File map

| File | Responsibility |
|---|---|
| `backend/app/game/turn_clock.py` (new) | `ClockSettings`, `TurnClock` (accounting, presence, public view, dump/load), `waiting_on`, save-extras helpers |
| `backend/app/game/clock_defaults.py` (new) | The safest legal default for each wait, with rule numbers |
| `backend/app/multiplayer/turn_clock_driver.py` (new) | The per-room timer task, `poke`/`hold`/`tick`, view fields, late-action guard |
| `backend/app/api/turn_clock.py` (new) | `POST /games/{id}/clock`: the host's settings, add time, extend grace |
| `backend/app/game/session.py` | `GameSession.clock` |
| `backend/app/multiplayer/hub.py` | Calls into the driver from `perform`, `broadcast`, `after_change`, `connect`, `disconnect`, `close`, `_meta`, `meta`, `restore` |
| `backend/app/multiplayer/lobby.py` | `LobbySettings.clock` |
| `backend/app/api/games.py`, `api/night.py`, `services.py`, `main.py` | Lobby settings and start, rematch and lobby carry-over, saves, recovery, `seen_revision`, router |
| `frontend/src/game/turnClock.ts` (new) | Countdown arithmetic and formatting |
| `frontend/src/game/TurnClockChip.tsx` (new), `game/SeatPlate.tsx`, `game/HostTools.tsx`, `pages/TurnClockSetting.tsx` (new), `pages/LobbyScreen.tsx` | The countdown on each seat plate, host controls, lobby setting |
| `frontend/src/types/game.ts`, `state/gameStore.ts`, `services/gameSocket.ts`, `services/games.ts` | Types, skew tracking, `seen_revision`, `setClock` |

---

### Task 1: Who is waited on, and charging them

**Files:**
- Create: `backend/app/game/turn_clock.py`, `backend/tests/test_turn_clock.py`

**Interfaces:**
- Produces:
  - `AtZero = Literal["act", "show"]`
  - `class ClockSettings(BaseModel)` (`extra="forbid"`): `on: bool = False`, `bank_seconds: int = Field(1500, ge=60, le=7200)`, `buffer_seconds: int = Field(30, ge=5, le=300)`, `at_zero: AtZero = "act"`, `grace_seconds: int = Field(120, ge=30, le=1800)`.
  - `MAX_BANK = 14400.0` and `MAX_GRACE_EXTRA = 3600.0`.
  - `waiting_on(state: GameState) -> dict[str, str]` maps each charged human seat to its wait key, in seat order. The result is `{}` when `state.rules is None`, `automation == "off"`, `rules.paused`, or there is a winner or `draw_reason`. It skips `autoseat.non_human`, `left`, `conceded` and `lost` seats. In pregame, every seat that is `deciding` or `bottoming` is charged, with key `f"m:{status}:{mulligans}"`. Otherwise `decider_of(state, decision)` is charged with key `f"d:{decision.id}"`. Otherwise `controller_of(state, rules.priority)` is charged with key `f"p:{turn.number}:{turn.phase}:{len(stack)}:{stack[-1] if stack else ''}:{len(rules.passed)}"`. This key stays the same when other players act or a refused action arrives, and changes when the player gets a new priority (117.3b-d).
  - `class TurnClock(BaseModel)`: `settings: ClockSettings`, `banks: dict[str, float]` (each 0..`MAX_BANK`, at most 12 entries). In-memory private state: the running waits (key, last settle time, buffer left), `held`, `away_since`, `grace_extra`, `gave_up` keys, and `acted_through: dict[str, int]`. Methods (all take `now: float`, monotonic seconds):
    - `sync(waiting: dict[str, str], connected: set[str], now: float) -> None` settles and then sets the waits. A wait whose key is unchanged keeps its buffer. A new key gets `buffer_seconds`. A player missing from `banks` gets `bank_seconds` here. If `connected` is empty, nobody is charged. When `settings.on` is false, waits are cleared and nothing is charged.
    - Settling charges each running wait for the time since its last settle: the buffer first, then the bank (never below 0). A wait is not charged while `held`, while the clock is off, or while its player was exempt at the last settle. Exempt means away for less than `grace_seconds + grace_extra`. The clock never over-charges.
    - `hold(now) -> None` settles and stops all charging until the next `sync`: the server is resolving.
    - `due(now) -> list[str]` lists players whose buffer and bank are both 0, when `at_zero == "act"`, who are not exempt, and whose key is not in `gave_up`.
    - `next_event(now) -> float | None` is the earliest of each charged wait's zero time (act mode only, skipping `gave_up` keys) and each exempt player's grace end. A time already past never comes back once its key has been given up, so the task cannot spin.
    - `due`, `bank`, `public` and `next_event` only read: they work from the last settle plus `now` and never change state. Only `sync`, `hold`, `add_time`, `extend_grace`, `give_up` and `mark_acted` change state. Each `sync` drops `gave_up` keys that are no longer current.
    - `bank(pid, now) -> float`; `add_time(pid, seconds, now) -> float` (capped at `MAX_BANK`, returns the new bank); `extend_grace(pid, seconds) -> None` (total capped at `MAX_GRACE_EXTRA`, reset on reconnect); `give_up(pid) -> None`; `mark_acted(pid, revision) -> None`; `acted_revision(pid) -> int | None`.
    - `public(now: float, sent_at: float) -> dict[str, Any]` returns `{"settings": {...}, "sent_at": sent_at, "players": {pid: {"bank": float, "buffer": float | None, "running": bool, "away": bool}}}`. Numbers are rounded to 0.1. `players` is present only when on. It never contains a wait key, decision id or kind.
    - `dump(now) -> dict[str, Any]` is `{"settings", "banks"}` settled to `now`. `TurnClock.load(data: object) -> TurnClock | None` returns `None` and logs a warning on `ValidationError`. Callers add the notice (Task 5).

- [ ] **Step 1: Write the failing tests.** Charging tests use a bare `TurnClock` and explicit `now`. `waiting_on` tests use `tests.test_rules_effects.build(cards)` and set fields on its state.

```python
def on(**kw): return TurnClock(settings=ClockSettings(on=True, **kw))

def test_buffer_first_then_bank():
    c = on(); c.sync({"p1": "k"}, {"p1"}, 0.0); c.sync({"p1": "k"}, {"p1"}, 40.0)
    assert c.bank("p1", 40.0) == 1490.0 and "p2" not in c.banks          # nobody else was waited on

def test_same_key_keeps_its_buffer_new_key_refills():          # Review Focus 4
    c = on(); c.sync({"p1": "k"}, {"p1"}, 0.0); c.hold(20.0); c.sync({"p1": "k"}, {"p1"}, 25.0)
    assert c.public(25.0, 0)["players"]["p1"]["buffer"] == 10.0
    c.sync({"p1": "k2"}, {"p1"}, 26.0); assert c.public(26.0, 0)["players"]["p1"]["buffer"] == 30.0

def test_held_and_exempt_are_not_charged():
    c = on(); c.sync({"p1": "k"}, {"p1"}, 0.0); c.hold(1.0); c.sync({"p1": "k"}, {"p1"}, 500.0)
    assert c.bank("p1", 500.0) == 1500.0
    c.sync({"p1": "k"}, {"p2"}, 500.0); c.sync({"p1": "k"}, {"p2"}, 600.0)    # p1 away 100 s < 120 s grace
    assert c.bank("p1", 600.0) == 1500.0
    assert c.next_event(600.0) == 620.0                                       # the driver wakes at the grace end
    c.sync({"p1": "k"}, {"p2"}, 620.0); c.sync({"p1": "k"}, {"p2"}, 700.0)
    assert c.bank("p1", 700.0) < 1500.0                                       # past grace: charged

def test_nobody_connected_charges_nobody():
    c = on(); c.sync({"p1": "k"}, set(), 0.0); c.sync({"p1": "k"}, set(), 9999.0)
    assert c.bank("p1", 9999.0) == 1500.0 and c.due(9999.0) == []

def test_zero_then_each_decision_gets_its_buffer():
    c = on(); c.banks["p1"] = 0.0; c.sync({"p1": "k"}, {"p1"}, 0.0)
    assert c.due(29.9) == [] and c.due(30.0) == ["p1"] and c.next_event(0.0) == 30.0
    c.sync({"p1": "k2"}, {"p1"}, 31.0); assert c.due(31.0) == [] and c.bank("p1", 31.0) == 0.0

def test_show_only_never_due_and_floor_is_zero():
    c = on(at_zero="show"); c.banks["p1"] = 5.0; c.sync({"p1": "k"}, {"p1"}, 0.0)
    assert c.due(1e6) == [] and c.bank("p1", 1e6) == 0.0

def test_add_time_and_grace_are_capped():
    c = on(); assert c.add_time("p1", 99999, 0.0) == MAX_BANK
    c.sync({"p1": "k"}, set(), 0.0); c.extend_grace("p1", 99999)          # away from t=0
    assert c.next_event(0.0) == 120 + MAX_GRACE_EXTRA                      # its grace end (act mode, bank untouched)

def test_dump_load_round_trip_and_bad_data():
    c = on(); c.banks = {"p1": 12.5}; assert TurnClock.load(c.dump(0.0)).banks == {"p1": 12.5}
    assert TurnClock.load({"settings": {"on": True}, "banks": {"p1": -3}}) is None
    assert TurnClock.load({"settings": {"on": True, "evil": 1}, "banks": {}}) is None

def test_public_block_never_names_the_decision():
    c = on(); c.sync({"p1": "d:secret-id"}, {"p1"}, 0.0)
    block = c.public(0.0, 1.0); assert "secret-id" not in json.dumps(block)
    assert set(block["players"]["p1"]) == {"bank", "buffer", "running", "away"}

def test_waiting_on(cards):
    s = build(cards)                                     # Alice holds priority in main 1
    assert list(waiting_on(s.state)) == ["p1"]
    s.state.rules.paused = True; assert waiting_on(s.state) == {}
    s.state.rules.paused = False; s.state.rules.conceded.append("p1"); assert "p1" not in waiting_on(s.state)
    # a decision with decider p2 (723.5) charges p2; a target dummy seat is never charged; automation off charges nobody
```

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_turn_clock.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `turn_clock.py`. Base `waiting_on` on `bot.pending` (`app/game/bot.py:111`), extended to every human seat.
- [ ] **Step 4: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit** `Turn clock: who the engine waits on, and charging them on monotonic time`.

### Task 2: The safest legal default for each wait

**Files:**
- Create: `backend/app/game/clock_defaults.py`, `backend/tests/test_turn_clock_defaults.py`

**Interfaces:**
- Consumes: `waiting_on` (Task 1); `app.game.dummy.answers` (reused, not copied); `app.game.rules_state.cancelable`.
- Produces: `answers(state: GameState, pid: str, info: CardInfo | None) -> list[dict[str, Any]]`: the payloads to try in order (the first one the engine accepts wins). `[]` means "leave it to the table". Also `RULES_CONFIRMS = frozenset({"sba_confirm", "combat_damage", "trigger_confirm"})` and `TABLE_ONLY = frozenset({"manual_resolution", "reconcile"})`.
- The order, with the comment each line carries:
  - pregame `deciding`: `mulligan_keep` (103.5: keeping is the declaration not to mulligan; 103.5b: Serum Powder is optional and not used). Pregame `bottoming`: `mulligan_bottom` with the first `to_bottom` cards of the hand in hand order (103.5: the player must put that many cards on the bottom).
  - priority: `pass_priority` with no `until` (117.3d).
  - decision kind in `TABLE_ONLY`: `[]`.
  - `cancelable(d)`: `choose ["cancel"]` first (601.2, 733.1: the announcement is reversed), then the rest as fallbacks.
  - `declare_attackers`: the empty declaration (508.1a "if any"). Then, for 508.1d, each `d.display["must_attack"]` creature at its first listed place.
  - `declare_blockers`: the empty declaration (509.1a). Then, for 509.1c, the block tries from `dummy.answers(d, state=state, info=info, blocks="all")` without its trailing empty one.
  - `confirm`: `["yes"]` when `d.resume["step"]` is in `RULES_CONFIRMS` (704.3, 510.2, 603.3: the rules say it happens). Otherwise `["no"]` when offered (603.5, 608.2d: a "may" is declined).
  - `min_choices <= 0`: `choose []` (an optional "up to" choice is declined).
  - Then `dummy.answers(d, state=state, info=info)` as fallbacks (608.2d / 700.2: the first legal options; `order` in the order offered; `divide` evenly, 601.2d; typed names).
  - Duplicates are removed (order kept), and the list is capped at `dummy.MAX_TRIES + 2`.

- [ ] **Step 1: Write the failing scenario tests.** Each test applies `answers(...)` with the helper below, then calls `replay_matches(s)` and `roundtrip(s)` (`tests/test_rules_designations.py:215`). Cards come from `fixture_cards()` plus `tests/fixtures/attack_destinations34_cards.json` (Juggernaut: "This creature attacks each combat if able.…"; Bident of Thassa: "Whenever a creature you control deals combat damage to a player, you may draw a card.…"). Add one fixture, copied verbatim from `data/cards.sqlite`: **Razorgrass Screen** `{1}` Artifact Creature — Wall 2/1, "Defender (This creature can't attack.)\nThis creature blocks each combat if able." Use the cards fixture pattern from `tests/test_rules_attack_destinations34.py:28`.

```python
def first_accepted(s, pid):
    for p in answers(s.state, pid, s.cards):
        try: act(s, pid, **p); return p
        except (ActionError, ValidationError): continue
    return None

def test_priority_is_passed(cards):                    # 117.3d
def test_a_may_trigger_is_declined(cards):             # 603.5: Bident's draw → answers[0] chooses ["no"]; hand size unchanged
def test_a_cast_being_announced_is_taken_back(cards):  # 601.2c/733.1: Murder at its target → ["cancel"]; Murder back in hand, stack empty
def test_no_attack_unless_a_creature_must(cards):      # 508.1a/d: bear only → nobody attacks; with Juggernaut → Juggernaut attacks
def test_no_block_unless_a_creature_must(cards):       # 509.1a/c: Razorgrass Screen untapped → the empty block is refused, Screen blocks
def test_mulligans_keep_then_bottom_the_first_cards(cards):  # 103.5: COMMANDER_LONDON, 3 takes + keep → mulligan_bottom hand[:2]
def test_assisted_rules_confirmations_are_applied(cards):    # 510.2: "Combat damage: Bear → Bob 3" → ["yes"], Bob at 37
def test_manual_resolution_is_left_to_the_table(cards):      # answers == [] (the Sol Ring manual-mode setup, test_rules_automation.py:118)
```

Assertions are in the comments. Each test also asserts that nobody is in `rules.conceded`, `rules.lost` or `left` afterwards. Before pinning the Bident assertion, check that its "you may draw a card" arrives as the yes/no `confirm` (`rules/effects.py:450`). If it arrives as a `min_choices == 0` choice instead, the expected default is `choose []`: change the test's expectation, not the code.

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_turn_clock_defaults.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `clock_defaults.answers`.
- [ ] **Step 4: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit** `Turn clock: the safest legal default for each wait, from the Comprehensive Rules`.

### Task 3: The timer task, hub wiring and the clock in every view

**Files:**
- Create: `backend/app/multiplayer/turn_clock_driver.py`, `backend/tests/test_turn_clock_driver.py`
- Modify: `backend/app/game/session.py` (add `self.clock: TurnClock | None = None` in `__init__`), `backend/app/multiplayer/hub.py`

**Interfaces:**
- Consumes: Task 1 and Task 2.
- Produces (driver module):
  - `now: Callable[[], float] = time.monotonic` and `wall: Callable[[], float] = time.time`. Tests patch both.
  - `offered(room: Room) -> bool`: `room.mode == "lan"`, `room.practice is None`, `room.started`, and `state.format == "commander"`.
  - `clock_of(room: Room) -> TurnClock | None`: the session's clock, when offered.
  - `poke(hub: GameHub, room: Room) -> None` calls `clock.sync(waiting_on(state), connected, now())`. `connected` is the seats with `connections > 0` that are not `bot`. While a final board is shown (`room.night.final_board()`), nothing is charged. In a running loop, `poke` also (re)arms the room's one task: it sets the task's wake `asyncio.Event`, never a second task. Outside a loop it only syncs, like `bots.poke`.
  - `hold(room: Room) -> None`.
  - `async tick(hub: GameHub, room: Room) -> list[str]` runs under `room.lock`. It returns early if the room was closed or replaced. It syncs, then repeats while `clock.due(now())` is non-empty, at most `len(seat_order) * 2` times. For each due player it tries `clock_defaults.answers` through `await hub.perform(room, pid, payload)`, catching only `ActionError` and `ValidationError`. On success: `clock.mark_acted(pid, room.revision)`, `session.notice(ACTED.format(name=...))`, `hub.after_change(room)`, then re-sync. If every answer fails (or there are none): `clock.give_up(pid)` and `session.notice(CANT.format(name=...))`, once per wait key. After releasing the lock, it calls `await hub.broadcast(room)` if anything changed. It returns the players it acted for.
  - The task loop: clear the wake event, then wait until `clock.next_event(now())` or the wake event (`hub.perform` inside `tick` calls `poke`, so the event is cleared first), then `tick`. It exits when the room is closed, the clock is off, or there is no next event. There is no broad `except` (gate point 8). `AutomationError` subclasses `ActionError` (`app/game/errors.py`), so the narrow catch covers rules-engine failures. Any other error ends the task, and a done-callback logs `task.exception()` at error level. The next `poke` (every broadcast) starts a fresh task. Name this in the audit as the clock's only failure path.
  - `view_fields(room: Room) -> dict[str, Any]`: `{}` when not offered. `{"clock": {"settings": ClockSettings().model_dump()}}` when offered with no clock. Otherwise `{"clock": clock.public(now(), wall())}`.
  - `forget(room_id: str) -> None`.
  - Copy: `ACTED = "{name} ran out of time: Fyodor acted for them."` and `CANT = "{name} ran out of time, but Fyodor can't make this choice for them. The table decides it; the host can add time or turn the clock off."` Neither names the choice: the action's own log entry already follows visibility rules.
- Hub changes:
  - `perform`: call `turn_clock_driver.hold(room)` first, and `turn_clock_driver.poke(self, room)` in the outermost `finally` of both branches, so a refused action resumes the same wait.
  - `broadcast`: `poke` right after `await self.settled(room)`, so views carry the current clock.
  - `after_change`, `connect` and `disconnect`: `poke`. `close`: `turn_clock_driver.forget(game_id)`.
  - `_meta`: `**turn_clock_driver.view_fields(room)` beside `bots.view_fields`. The block is the same for every viewer, spectators included.

- [ ] **Step 1: Write the failing tests.** These are hub-level async tests in the style of `tests/test_interim_views.py`: `GameHub()`, `create_room(session, mode="lan")`, fake `Connection`s with inboxes, `asyncio.run`. The session comes from `tests.test_rules_effects.build(cards)` with `session.clock = TurnClock(settings=ClockSettings(on=True))`. Patch `turn_clock_driver.now` to a list-backed fake.

```python
def test_only_the_waited_player_is_charged(...):          # p1 priority, t += 100 → p1 1430, p2 1500
def test_at_zero_the_clock_passes_and_says_so(...):       # p1 bank 0, t += 30 → tick == ["p1"]; last action pass_priority by p1;
                                                          # every inbox's log has "Alice ran out of time: Fyodor acted for them."; replay_matches
def test_only_show_it_does_nothing(...):                  # at_zero="show": tick == [], history unchanged, bank 0
def test_nobody_is_charged_while_an_action_resolves(...): # monkeypatch GameSession.prepare to advance the fake clock 100 s; banks unchanged
def test_phone_sleeps_within_grace(...):                  # Review Focus 1: disconnect p1, t += 90, reconnect → bank and buffer unchanged
def test_after_grace_the_absent_player_is_acted_for(...): # p1 gone, t += 120 + 30 + bank → tick acts for p1
def test_simultaneous_mulligans_each_charged(...):        # pregame, both deciding: both banks fall; both at 0 → both keep
def test_never_concedes_or_eliminates(...):               # banks 0, 40 ticks across turns: nobody conceded/lost/left, no concede in history
def test_refused_everything_says_so_once(...):            # Review Focus 5: manual_resolution at 0 → one CANT notice over 3 ticks, nothing applied,
                                                          # and clock.next_event(now) is None afterwards (no wake-up at a past time)
def test_an_engine_failure_ends_only_the_task(...):       # answers' perform raises RuntimeError → logged, table unchanged, the next poke re-arms
def test_every_viewer_sees_the_same_clock(...):           # p1 in a hidden library search vs p1 at priority: p2's and the spectator's
                                                          # game.clock blocks have the same keys and values, and no decision id appears in them
def test_the_task_fires_without_anyone_acting(...):       # inside asyncio.run: poke with now past the deadline → history grows within 2 s
def test_not_offered_on_hot_seat_or_practice_or_sandbox(...):  # view_fields == {}, tick == []
```

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_turn_clock_driver.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the driver and the hub calls.
- [ ] **Step 4: Run these tests, then the full backend suite.** Expected: all pass. This catches any change in view shape or hub timing.
- [ ] **Step 5: Commit** `Turn clock: the room's timer acts at zero under the room lock; every view shows the clock`.

### Task 4: Settings in the lobby and at the table (host only)

**Files:**
- Create: `backend/app/api/turn_clock.py`, `backend/tests/test_turn_clock_settings.py`
- Modify: `backend/app/multiplayer/lobby.py` (`LobbySettings.clock: ClockSettings = Field(default_factory=ClockSettings)`; the `_sandbox_starts_manual` validator also sets `clock.on = False`), `backend/app/api/games.py` (`LobbySettingsIn.clock: ClockSettings | None = None`, with no Ready reset; in `start_game`, when `lobby.clock.on and lobby.format == "commander"`, `session.clock = TurnClock(settings=lobby.clock)`), `backend/app/main.py` (register the router)

**Interfaces:**
- Consumes: `turn_clock_driver.offered`, `clock_of`, `poke`; `authorize` and `room.is_host`. This is the one host check; nothing new.
- Produces: `POST /api/games/{game_id}/clock`. Body `ClockIn` (`extra="forbid"`): `op: Literal["settings", "add_time", "grace"]`, `settings: ClockSettings | None`, `player: str | None = Field(None, pattern=r"^p\d{1,2}$")`, `seconds: int | None = Field(None, ge=1, le=3600)`. It returns `{"view": <the caller's view>}`.
  - 403 `"Only the host can change the turn clock"` unless `room.mode == "lan" and room.is_host(x_seat_token)`.
  - 409 `"The turn clock is for LAN tables"` (hot-seat, practice); 409 `"A Sandbox table has no turn clock"`.
  - 422 when `settings` is missing for `settings`, or `player`/`seconds` is missing for the other ops. 422 `"No such player"` for a seat that is not a human player in the game.
  - Under `room.lock`: `settings` creates the clock if absent, or replaces its settings (banks untouched). `add_time` calls `clock.add_time`; `grace` calls `clock.extend_grace`. Each logs a notice: `"The host turned the turn clock on."` / `"…off."` / `"The host changed the turn clock settings."` / `"The host added {m:ss} to {name}'s clock."` / `"The host gave {name} {m:ss} more to reconnect."` Then `poke` and broadcast. Nothing is recorded in history.

- [ ] **Step 1: Write the failing tests** (TestClient; `create_lobby` and `h` from `tests/test_lobby.py`). A lobby with `automation="full"` and `clock={"on": true}` starts with `game.clock.players` holding 1500 for each human seat and no entry for a LAN bot. A Sandbox lobby reads `clock.on == False`. `clock={"bank_seconds": 10}` is 422, and so is an unknown field. Host `add_time` p2 300 gives a bank of 1800 and the notice in the log. Bob (a seat) gets 403, a spectator 403, a hot-seat table 409, a sandbox LAN table 409. `seconds: 0` and `seconds: 4000` are 422. `player: "p9"` is 422. `settings` with `on: false` removes `players` from the block, and nothing is charged after it. After `grace` for p2, p2's grace end moves by that amount.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_turn_clock_settings.py tests/test_lobby.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit** `Turn clock: lobby setting and the host's table controls`.

### Task 5: Saves, restarts, undo, rematch

**Files:**
- Create: `backend/tests/test_turn_clock_saves.py`
- Modify: `backend/app/game/turn_clock.py` (save helpers), `backend/app/services.py` (`autosave`, `recover_rooms`), `backend/app/api/games.py` (`save_game`, `load_save`), `backend/app/multiplayer/hub.py` (`meta`, `restore`), `backend/app/api/night.py` (`rematch`, `to_lobby`)

**Interfaces:**
- Produces:
  - `turn_clock.save_extras(session: GameSession, now: float) -> dict[str, Any]` returns `{"clock": session.clock.dump(now)}`, or `{}` when there is no clock.
  - `turn_clock.load_extras(session: GameSession, extras: dict[str, Any]) -> None` sets `session.clock` from `extras.get("clock")`. When the data is present but `TurnClock.load` returns `None`, it adds the notice `"The turn clock in this save couldn't be read, so it is off."`.
  - The three save writers pass `extras={"table_snapshots": …, **turn_clock.save_extras(session, turn_clock_driver.now())}`. The two loaders call `load_extras` after reading snapshots. `package.py` already carries `extras` unchanged (`storage/package.py:195`). The `RestoreState` and history-restore routes replace only `session.state`, so the clock is untouched (no change needed).
  - `hub.meta(room)` adds `"clock"` (the dump, or `None`). `hub.restore` loads it over the checkpoint's clock when present. On recovery every seat starts disconnected, so nobody is charged until a player reconnects (Task 1's "nobody connected" rule).
  - `rematch`: `session.clock = TurnClock(settings=old.clock.settings)` (fresh banks). `to_lobby`: when the old session had a clock, `room.lobby` takes its `settings`, as it already does for `card_permissions`.

- [ ] **Step 1: Write the failing tests:**
  - A save then a load keeps the settings, and each bank to within 0.5 s.
  - A save written without `extras["clock"]` loads with `session.clock is None`.
  - A damaged `extras["clock"]` loads with no clock and the notice.
  - Review Focus 3: crash recovery in the pattern of `tests/test_recovery.py` (`crash`, a new `TestClient`). The bank after recovery equals the bank at the crash even after the fake clock moves 1000 s. After a seat reconnects, the timer acts at zero with no player action.
  - Undo after the clock acted: the bank is not refunded, and `replay_matches` still holds.
  - A rematch has full banks and the same settings. Back in the lobby, `settings.clock` equals the game's settings.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_turn_clock_saves.py tests/test_recovery.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run these tests, then the full backend suite.** Expected: all pass.
- [ ] **Step 5: Commit** `Turn clock: saved with the game, restored after a restart, never refunded by undo`.

### Task 6: A timeout and a player action never both apply

**Files:**
- Create: `backend/tests/test_turn_clock_race.py`
- Modify: `backend/app/multiplayer/turn_clock_driver.py`, `backend/app/api/games.py` (`ActionIn`, `WsAction`, `post_action`, `_handle_ws_message`), `frontend/src/services/gameSocket.ts`, `frontend/src/services/gameSocket.test.ts`

**Interfaces:**
- Produces:
  - `seen_revision: int | None = Field(default=None, ge=0, le=2**31 - 1)` on `ActionIn` and `WsAction`.
  - `turn_clock_driver.late(room: Room, actor: str, seen_revision: int | None, action_type: str | None) -> str | None` returns `"The clock already acted for you. Look at the table and try again."` when all of these hold: the clock acted for `actor` at revision `R`; `seen_revision is not None and seen_revision <= R`; and `action_type` is in `INTENT_TYPES - {"concede", "set_prefs", "set_stops", "set_card_automation"}`. A concession always goes through (104.3a). Otherwise it returns `None`. Both routes call it under `room.lock`, after the `client_action_id` lookup and before `perform`. A refusal is remembered like any `ActionError` (409 / `REJECTED`), so a retry with the same id gets the same answer.
  - Frontend: `requestAction` stores `seen_revision: this.revision` in the queued message when it is queued. A resend after a reconnect keeps it. `services/games.ts` `tableAction` (the REST path for pages that are not at the table) has no view revision and stays unguarded by design. Say so in its doc comment.

- [ ] **Step 1: Write the failing tests:**
  - A player's pass is being worked out (patch `GameSession.prepare` to sleep 0.2 s) while `tick` runs past the deadline, both under `asyncio.gather`. History has exactly one `pass_priority` by p1 for that wait, and the clock did not act.
  - The clock acted, then p1's pass arrives with the old `seen_revision`: 409, history unchanged. The same pass with the broadcast's revision is accepted.
  - The same id, retried after a refusal, gets the same refusal. A concede with an old `seen_revision` is accepted. An action with no `seen_revision` is accepted as before.
  - The same flow over the socket (`connect_game` from `tests/conftest.py`): `REJECTED`, with the message.
  - Vitest: a queued action carries the revision it was requested at, and keeps it across a reconnect.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_turn_clock_race.py tests/test_action_ids.py -q` and `npm test -- gameSocket`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit** `Turn clock: a late click after the clock acted is refused; the room lock orders the rest`.

### Task 7: The countdown, the lobby setting and the host controls

**Files:**
- Create: `frontend/src/game/turnClock.ts`, `frontend/src/game/turnClock.test.ts`, `frontend/src/game/TurnClockChip.tsx`, `frontend/src/pages/TurnClockSetting.tsx`
- Modify: `frontend/src/types/game.ts` (`game.clock?`, `LobbySettings.clock?`), `frontend/src/state/gameStore.ts` (`clockSkew: number | null`, updated on every applied view or delta whose `game.clock.sent_at` is set), `frontend/src/game/SeatPlate.tsx` (render the chip in both plate variants), `frontend/src/game/HostTools.tsx`, `frontend/src/pages/LobbyScreen.tsx` (beside `PlanechaseSetting`; hidden for Sandbox), `frontend/src/services/games.ts` (`setClock(gameId: string, body: ClockBody): Promise<{ view: GameView }>`), `docs/UI_REFERENCE_STUDY.md`

**Interfaces:**
- Consumes: the view block from Task 3 and the route from Task 4.
- Produces:
  - `noteSkew(prev: number | null, sentAt: number, receivedAtMs: number): number` returns `min(prev, receivedAtMs / 1000 - sentAt)` (the least-delayed message wins).
  - `remainingNow(e: ClockEntry, sentAt: number, skew: number, nowMs: number): { buffer: number; bank: number }`. Elapsed is `max(0, nowMs / 1000 - skew - sentAt)`, and only while `running && !away`. It is taken from the buffer first, then the bank; both are clamped to at least 0 and at most the values sent.
  - `formatClock(seconds: number): string` gives `"25:00"`, `"0:07"`, or `"1:02:03"` above an hour.
  - `TurnClockChip({ player })` shows the bank as `m:ss` in `tabular-nums`. While running it also shows the buffer before the bank (`0:24 · 12:31`) and the word "running" for assistive technology. Away shows "Paused — reconnecting". There is no colour-only state, no flashing and no rope. It re-renders once a second only while some clock runs. `aria-label` example: `"Alice's clock: 12:31 left, running"`.
  - Host tools, "Turn clock" section: On/Off; At zero ("Act for the player" / "Only show it"); grace per decision (seconds); reconnect grace (minutes); per player **+1:00**, **+5:00**, and, when that player is away, **Give 2 more minutes to reconnect**.
  - Lobby `TurnClockSetting` hints. On: "Each player has a bank of time for the whole game. Each decision first gets a short grace that isn't charged. At zero, Fyodor makes the safest choice for them (pass, decline, no attack); it never concedes for anyone. Runs while rules automation is on." Only show it: "At zero the clock just reads 0:00; nothing happens." Off: "Off: no clock."

- [ ] **Step 1: Write the failing Vitest cases** in `turnClock.test.ts`:
  - Review Focus 2: a client clock 600 s ahead gives the same remaining time as a correct one.
  - A message whose `sentAt` looks like the future gives elapsed 0.
  - The buffer is spent before the bank, and the bank never goes below 0.
  - Not running, or away, means frozen.
  - `formatClock(1500) === "25:00"`, `formatClock(7) === "0:07"`, `formatClock(3723) === "1:02:03"`.
- [ ] **Step 2: Run** `npm test -- turnClock`. Expected: FAIL.
- [ ] **Step 3: Implement** `turnClock.ts`, the store skew, the types and `setClock`.
- [ ] **Step 4: Build the UI** with `frontend-design` per `fyodor-ui-design`: the chip on both plate variants, the host section and the lobby setting. Run the app, then screenshot a four-seat LAN table with one clock running, one away and one at 0:00, at 1920×1080, 2560×1440 and a laptop size. Run `impeccable critique` on the chip and fix its concrete findings.
- [ ] **Step 5: Update `docs/UI_REFERENCE_STUDY.md`:**
  - M4 "Avoid: Turn clocks. A private pod doesn't need them." becomes "Avoid: a turn clock by default. Fyodor's is optional and off unless the host turns it on (internet-play Stage 3)."
  - G3's Borrow/Avoid becomes: an optional server-owned clock (bank + uncharged buffer) whose zero either takes the safest legal default or only shows 0:00; still no burning rope, no flashing, no pressure by default, since the accessibility point (AC2) stands.
- [ ] **Step 6: Run** `npm run typecheck && npm test` in `frontend/`. Expected: PASS.
- [ ] **Step 7: Commit** `Turn clock: countdown on each seat plate, lobby setting, host controls`.

### Task 8: Stage gate

**Files:**
- Create: `docs/superpowers/specs/2026-11-25-stage3-audit.md`
- Modify: `docs/LAN_PLAY.md` (a "Turn clock" section: what it does, who is charged, the two at-zero modes, the grace period, that it never concedes, that it runs only with rules automation on), `docs/CURRENT_STATE.md` (one batch entry)

- [ ] **Step 1:** From `backend/`, run `.venv/Scripts/ruff check . && .venv/Scripts/mypy app tools && .venv/Scripts/python -m pytest -n 8 -q`. From `frontend/`, run `npm run typecheck && npm test`. Paste the summaries into the audit file.
- [ ] **Step 2:** Run `bandit -r app -q`, `pip-audit` and `npm audit` (dev tools only, as in Stage 1). List every finding as "fixed in <commit>" or "accepted because …".
- [ ] **Step 3:** Walk the spec's 13-point Review gate, one line each, with the test or commit that meets it or "not applicable" and why. Points 1 and 13: the clock route uses `authorize` and `room.is_host` only, and the race uses `room.lock` only. Point 2: `test_every_viewer_sees_the_same_clock`. Point 6: `ClockIn`, `ClockSettings`, `seen_revision`. Point 8: no new broad `except`. Point 10: `test_turn_clock_race.py`. Point 9: no new dependency.
- [ ] **Step 4:** Manual check on two devices with automation at Full, the clock on, bank 2 minutes and buffer 10 s:
  - The countdown matches on both screens.
  - At zero the clock passes, and the log says so.
  - A phone that sleeps within the grace period loses nothing.
  - **+1:00** shows on both screens.
  - **Only show it** reads 0:00 and nothing happens.
  - Turning the clock off removes it.

  Record what was seen.
- [ ] **Step 5:** Run the `security-review` skill on the branch, and dispatch one fresh reviewer with the spec, this plan and the diff. Fix or answer every finding.
- [ ] **Step 6: Commit** the docs and audit file. Do not merge to `master` until the owner has read the audit file.
