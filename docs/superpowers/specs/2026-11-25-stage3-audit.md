# Stage 3 (turn clock): audit

Branch `internet-play-stage3`, head `2ead807`, built on Stage 2's final head `6b9dd82` (the base for every comparison below).
Plan `docs/superpowers/plans/2026-11-25-internet-play-stage3-turn-clock.md`; spec `docs/superpowers/specs/2026-11-21-internet-play-design.md`
("Stage 3: Turn clock", "Review gate (every stage)"); execution ledger `.superpowers/sdd/2026-11-25-internet-play-stage3-turn-clock/progress.md`.
Every figure below was produced by the command named beside it on 2026-11-25. Commit hashes are the branch's current ones (the
ledger's hashes predate the two rebases onto Stage 2).

| Task | Commits |
|---|---|
| 1 Who is waited on, and charging them | `3b361f3`, `a65f127` |
| 2 The safest legal default | `5ac9393`, `805ca70`, `a67b1a8`, `852c088`, `1108ce4`, `62caa06` |
| 3 Timer task, hub wiring, the clock in every view | `2601e03`, `4e4d1f9` |
| 4 Lobby setting and host controls (server) | `01f63ef` |
| 5 Saves, restarts, undo, rematch | `d8b4191`, `78cb060` |
| 6 A timeout and a click never both apply | `76d0a40` |
| 7 Countdown, lobby setting, host controls (UI) | `2d519db`, `2ead807` |

`git diff --stat 6b9dd82..HEAD` → `39 files changed, 3492 insertions(+), 28 deletions(-)`; `git diff -U0 6b9dd82..HEAD -- backend/app`
adds 934 lines.

## Stage gate (Task 8)

Backend tools ran from `backend/` with Fyodor-main's environment (`..\Fyodor-main\backend\.venv\Scripts\`, `PYTHONPATH` set to this
worktree's `backend`). The base counts came from a temporary `git worktree add --detach C:\Users\littl\AppData\Local\Temp\fyodor-s3-base 6b9dd82`,
run the same way and removed afterwards (`git worktree remove --force`; `git worktree list` no longer shows it).

### Gate results

| Check | Command | Head `2ead807` | Base `6b9dd82` | Verdict |
|---|---|---|---|---|
| ruff | `ruff check . --output-format concise` | `Found 10 errors.` | `Found 10 errors.` | **No new error.** `Compare-Object` of the two outputs → 0 differences (the same ten as Stage 2's audit: I001 ×5, SIM102 ×3, F841, SIM300). |
| mypy | `python -m mypy app tools` | `Found 304 errors in 15 files (checked 1193 source files)` | `Found 303 errors in 15 files (checked 1189 source files)` | **One new message, no new code path.** Messages compared with line numbers removed (`sed -E 's/:[0-9]+: /: /'`, sorted, `diff`): the one extra is `app\api\night.py:246: error: Argument 11 to "LobbySettings" has incompatible type "**dict[str, str]"; expected "ClockSettings" [arg-type]`. Line 246 (`_lobby_from`'s `**({"mulligan_rule": rule} if … else {})`) is not changed by this stage and already raises four such messages at base, one per `LobbySettings` field type; the new `clock` field adds a fifth. Not fixed (it is a pre-existing call, and the fix, an explicit `mulligan_rule=` argument, would also remove the four base messages and move the baseline): a follow-up. The four extra files checked are the four new modules (`turn_clock.py`, `clock_defaults.py`, `turn_clock_driver.py`, `api/turn_clock.py`); none has an error. |
| Full backend suite | `python -m pytest -n 4 -q` (controller) | **FULL SUITE: pending controller run** | | The controller runs it (one run at a time on this machine, ledger Ruling B); its result goes on this line. |
| Frontend typecheck | `npm run typecheck` (`tsc -b --noEmit`) in `frontend/` | exit 0 | | Pass. |
| Frontend tests | `npm test` in `frontend/` | `Test Files 166 passed (166)`, `Tests 1664 passed (1664)` | (Stage 2: 161 / 1633) | Pass. |

### Security tools

**bandit** (`bandit -r app -q -f json`, head and base): head **796 findings (8 High, 27 Medium, 761 Low)**, 203,522 lines; base 794
(8 High, 27 Medium, 759 Low), 202,791 lines. The findings on lines this stage added were found by matching each finding's file and
line against the added lines of `git diff -U0 6b9dd82..HEAD -- backend/app` (934 lines; a throwaway script in the scratchpad):
exactly two.

| Finding | Where | Answer |
|---|---|---|
| B101 assert | `app/api/turn_clock.py:63` (`assert body.settings is not None`) | Accepted because it narrows a type for mypy after the 422 check at `:51-52` refused a missing `settings` in the same request. Under `python -O` it vanishes and the check above still holds; were it ever reached with `None`, the next line raises (500): never a change. |
| B101 assert | `app/api/turn_clock.py:78` (`assert body.player is not None and body.seconds is not None`) | Accepted: the same, after the 422 check at `:54-55`. |

The other 794 findings are on lines from before this stage and were answered in the Stage 1 audit.

**pip-audit** (`pip-audit`, Fyodor-main's environment): `Found 12 known vulnerabilities in 1 package`: six advisories, listed twice,
all in `pip` 25.0.1 (PYSEC-2026-1795 → 25.3, PYSEC-2026-1796 → 26.0, PYSEC-2026-2875 and -2876 → 26.1, PYSEC-2026-196 → 26.1.2,
PYSEC-2026-3721 → 26.2); `fyodor-backend` skipped (not on PyPI). The same as Stage 2. None is on a line this stage added: Stage 3 adds
no dependency (`git diff 6b9dd82..HEAD -- backend/pyproject.toml frontend/package.json frontend/package-lock.json | Measure-Object -Line` → 0).
Accepted because `pip` is the development environment's installer, not part of Fyodor (Stage 1 risk 11, Stage 2 risk 17).

**npm audit** (`npm audit` in `frontend/`): `4 vulnerabilities (2 moderate, 2 high)`: `vite` 8.3.0–8.3.2 (high; GHSA-698v-4r3x-3vcv,
GHSA-r825-w8mm-5pxw, GHSA-587h-7wmj-h5pm, GHSA-9jrq-w75r-8gcw, GHSA-rq7h-c2jc-7f22, GHSA-vfpm-58rq-9qcg), `source-map-js` 1.0.0–1.2.1
(high, GHSA-68fv-2mgg-jv7q), `vitest` / `@vitest/mocker` 5.0.0-beta.1–5.0.2 (moderate, GHSA-qxg6-89mg-rqv8, GHSA-xp26-3454-mjgp).
`npm audit --omit=dev` → `found 0 vulnerabilities`. Identical to Stage 2; none on a line this stage added (no package change). Accepted
because each is a development or build tool, never shipped; the open upgrades of Stage 1 risk 11.

### The 13-point review gate

File and line numbers are as of `2ead807`. Every backend test named is in the full run, which is pending (above).

1. **Met.** The one new route, `POST /api/games/{id}/clock` (`api/turn_clock.py`), decides "host" with `room_host` (`:44`), Stage 2's
   one host gate (`deps.py:79`, `not is_tunnel_request(conn) and room.is_host(token)`), and gets the caller's view with `authorize`
   (`:59`); the player it changes must be a human seat in the game (`:56-58`). The plan names `room.is_host`; since Stage 2 that
   check is reached only through `room_host` (`git grep -n "\.is_host(" -- backend/app/api` → only `deps.py:79`). The clock acts for a
   player through `hub.perform(room, pid, payload)` with the pid the engine waits on, never a client's. The actions' actor still comes
   from the authenticated connection; the new client-supplied field `seen_revision` can only make `late()` refuse *less* (a client
   that lies about it disables a courtesy refusal, never gains an action), and the room lock is what orders a timeout and a click.
   Tests: `test_turn_clock_settings.py::test_only_the_host_changes_the_clock` (a seat 403, a spectator 403),
   `::test_a_seat_that_is_not_a_human_player_is_422`, `::test_hot_seat_and_sandbox_tables_have_no_clock`.
2. **Met.** The clock block is the same for every viewer, spectators included, and never names the decision: `TurnClock.public`
   returns `{settings, sent_at, players: {pid: {bank, buffer, running, away}}}`; `one_instant` makes one broadcast's views carry the same
   block to the byte. It adds no new waiting (it runs only while the engine already waits on a player, which the table already shows).
   The log notices (`ACTED`, `CANT`) name the player, not the choice. The at-zero defaults read only what the waited-on player may see.
   Tests: `test_turn_clock_driver.py::test_every_viewer_sees_the_same_clock` (a hidden library search vs priority: p2's and the
   spectator's `game.clock` blocks have the same keys and values, no decision id), `::test_one_broadcast_one_clock_block`,
   `test_turn_clock.py::test_public_block_never_names_the_decision`.
3. **Met.** No token anywhere in the stage (`git diff 6b9dd82..HEAD | grep -n "^+.*[?&]\(token\|seat_token\)="` → nothing). Three new log
   lines: `clock_defaults.py:247` and `turn_clock_driver.py:215` are constant text (with the traceback); `turn_clock.py:165`
   `log.warning("turn clock not loaded: %s", e)` prints a pydantic `ValidationError` for a damaged save or crash record, which quotes the
   offending input values by `repr` (truncated; control characters escaped). The values come from the host's own save or an imported
   package (`extras["clock"]`), never from a player's request, and hold no token. Accepted.
4. **Not applicable.** The stage makes, stores and compares no token or secret.
5. **Not applicable.** No secret is configured or defaulted; the clock's defaults (off, 1500 s, 30 s, act, 120 s) are not secrets.
6. **Met.** `ClockIn` (`extra="forbid"`; `op` a three-value `Literal`; `player` `^p\d{1,2}$`; `seconds` 1–3600), `ClockSettings`
   (`extra="forbid"`; bank 60–7200, buffer 5–300, grace 30–1800, `at_zero` `Literal["act","show"]`), `TurnClock` (`extra="forbid"`; at
   most 12 banks, each 0–`MAX_BANK` 14400; added time capped at `MAX_BANK`, extra grace at `MAX_GRACE_EXTRA` 3600; negative time refused),
   `seen_revision` on `ActionIn` and `WsAction` (`ge=0, le=2**31-1`, `games.py:274`, `:1851`), `LobbySettings.clock` / `LobbySettingsIn.clock`.
   Tests: `test_turn_clock_settings.py::test_a_lobby_clock_out_of_range_or_with_an_unknown_field_is_422`, `::test_a_bad_request_is_422`
   (`seconds` 0 and 4000), `test_turn_clock.py::test_dump_load_round_trip_and_bad_data`, `::test_top_level_extra_key_and_too_many_banks_are_rejected`,
   `::test_negative_time_is_refused`, `test_turn_clock_race.py::test_seen_revision_is_bounded` (−1 and 2**31 → 422). Open: bank keys are
   not checked against the game's players and their length is unbounded (at most 12; Tasks 1 and 5 minors).
7. **Met.** `git diff 6b9dd82..HEAD -- frontend/src | grep -c "^+.*\(innerHTML\|dangerouslySetInnerHTML\|javascript:\)"` → 0. The notices
   carry the seat name (user text) into the log, rendered as React text like every other log line. New log lines: point 3.
8. **Not met in letter: one new `except Exception`, for the owner to accept or have narrowed.**
   `git diff 6b9dd82..HEAD -- backend/app | grep -n "^+.*\(except\|suppress\)"`:
   - **`except Exception:  # noqa: BLE001` in `clock_defaults._required_blocks` (`clock_defaults.py:246`)** (Task 2, `805ca70`): logs
     `log.exception("The turn clock couldn't work out the required blocks")` and returns `[]`. It does **not** re-raise (unlike Stage 2's
     `manager.py` one); it falls back. Modelled on the target dummy's own block plan (`dummy.py:137`, the same pattern). Consequence: when
     the 509.1c planner fails, the try order is the empty block, then the dummy's one-blocker chumps, then "all" (`clock_defaults.py:89-90`);
     "all" is last and is tried only when the engine refused every earlier declaration; the engine still judges each one, so nothing
     illegal is applied, and a refusal of all of them ends in the `CANT` notice. Not silent (logged with the traceback at error level).
     No ledger entry or review accepted this handler by name; Task 2's report mentions it ("wrapped like the dummy's own block plan").
   - The rest are narrow: `except RuntimeError` around `asyncio.get_running_loop()` (`turn_clock_driver.py:102`, off the loop: synced,
     no timer); `except (ActionError, ValidationError)` in `tick` (`:150`, an answer the engine refused: the next one is tried);
     `contextlib.suppress(TimeoutError)` around the wake-up wait (`:187`, the deadline came); `except ValidationError` in `TurnClock.load`
     (`turn_clock.py:164`: `None`, a warning, and the caller's notice "The turn clock in this save couldn't be read, so it is off.").
   - **The clock's only failure path** (plan Task 3): `tick` catches only `ActionError` (which `AutomationError` is) and `ValidationError`.
     Any other error ends the room's timer task and leaves the table as it was; the done-callback `_ended` (`turn_clock_driver.py:213-215`)
     logs it at error level; the next `poke` (every broadcast) starts a fresh task. Test: `test_turn_clock_driver.py::test_an_engine_failure_ends_only_the_task`.
   - Fail closed: the host check refuses (403) unless `room_host`; the route is a 404 through the tunnel (`netguard.py` excludes `clock`
   from the game subpaths; `test_tunnel_routes.py::test_every_route_is_either_allowed_or_404_on_the_tunnel_port` walks every route). A
   default the clock can't place is left to the table (`[]`), never guessed.
9. **Met.** No new dependency or downloaded binary (command in "Security tools" → 0 lines).
10. **Met, with the RED evidence as the ledger records it.** Each task's report holds its RED/GREEN runs; the weak ones: Task 1's and
    Task 7's RED was only the missing module; Task 6's race, no-revision and concede tests passed before the change (regression pins:
    the room lock already ordered tick and perform; its three new tests were RED); Task 5's undo test is a guard. Negative cases:
    - timeout racing an action: `test_turn_clock_race.py::test_a_pass_being_worked_out_and_the_timeout_apply_once` (exactly one
      `pass_priority` by p1, the clock did not act); a late click: `::test_a_late_pass_is_refused_and_one_from_the_view_that_showed_the_clock_is_accepted`,
      `::test_a_late_pass_over_the_socket_is_rejected_with_the_message`;
    - repeated action id: the same id retried after a refusal gets the same refusal (`::test_a_late_pass_is_refused…`; REST answers it
      `ALREADY_APPLIED` with outcome `REJECTED: …`, the existing contract);
    - wrong seat: `test_turn_clock_settings.py::test_only_the_host_changes_the_clock`, `::test_a_seat_that_is_not_a_human_player_is_422`;
    - oversized: `seconds` 4000, `seen_revision` 2**31, more than 12 banks (point 6);
    - replaced token, foreign Origin, forged `X-Forwarded-For`: not applicable to this stage's new code (no token, and the clock route is
      a 404 on the tunnel port); Stage 1's and 2's tests cover the routes it uses.
11. **Pending (full suite); otherwise met as "no new errors", one mypy note.** ruff 10 = base 10; mypy 304 vs 303 (one more message on
    an unchanged pre-existing line, above); the frontend typecheck and 1664 tests pass; bandit, pip-audit and npm audit are read and
    answered above.
12. **Independent review: pending (controller).** The controller runs the security pass (ledger Ruling D) and one fresh reviewer after
    this commit.
13. **Met.** One host check (`room_host`, point 1), no new token check, no rate limiter. One ordering: `tick` runs under the room's
    existing `room.lock` (`turn_clock_driver.py:131`), as does the clock route (`api/turn_clock.py:60`) and `late()`'s callers
    (`games.py:479`, `:2191`); the stage adds no `Lock`, `Semaphore` or `Queue` (`git diff 6b9dd82..HEAD -- backend/app | grep -n "^+.*\(Lock(\|Semaphore\|Queue(\)"`
    → nothing). One timer task per room (`_drivers`), modelled on `bots.poke`.

### Review Focus (plan)

| # | Focus | Task (commit) | Tests |
|---|---|---|---|
| 1 | A phone sleeps mid-decision for 90 s: nothing charged within the grace; on return the same buffer and bank | 3 (`2601e03`, `4e4d1f9`) | `test_turn_clock_driver.py::test_phone_sleeps_within_grace`, `::test_after_grace_the_absent_player_is_acted_for`, `::test_the_task_wakes_at_the_grace_end_and_syncs`, `::test_a_connect_or_drop_during_an_action_charges_nobody`; `test_turn_clock.py::test_held_and_exempt_are_not_charged` |
| 2 | A client clock minutes wrong, or throttled timers: the countdown matches the server, never below 0:00 or above the bank | 7 (`2d519db`, `2ead807`) | `frontend/src/game/turnClock.test.ts` (a clock 600 s ahead, a future `sentAt`, buffer then bank, frozen when not running or away), `frontend/src/state/clockSkew.test.ts` |
| 3 | Fyodor restarts mid-game: banks come back, downtime not charged, the clock starts again without anyone acting | 5 (`d8b4191`, `78cb060`) | `test_turn_clock_saves.py::test_a_crash_keeps_the_banks_and_charges_nobody_until_a_player_is_back`, `::test_a_host_clock_change_survives_a_crash` |
| 4 | Illegal clicks or another player's action do not refill the buffer; only a new decision does | 1 (`3b361f3`, `a65f127`) | `test_turn_clock.py::test_same_key_keeps_its_buffer_new_key_refills`, `::test_priority_key_follows_real_priority_changes` |
| 5 | Every default refused: one log notice, nothing applied, no loop, no concede; the host can still act | 3 (`2601e03`) | `test_turn_clock_driver.py::test_refused_everything_says_so_once` (and `next_event` is `None` afterwards), `::test_never_concedes_or_eliminates`; `test_turn_clock.py::test_read_methods_do_not_change_state_and_give_up_stops_spinning` |

### Departures from the plan and spec: the rulings, for the owner

Each was made during execution (ledger) and can be overruled.

- **Ruling E: the clock lives on `GameSession.clock`, saved in the save's `extras["clock"]` and the crash record, not in `GameState`.**
  The spec says "clock fields live in game state". A `GameState` field that changes without a recorded action would break
  `replay_matches`, and undo would refund time. The owner chose subagent-driven execution after being told of this. Cost if wrong:
  moving the fields later touches `turn_clock.py` and the save helpers.
- **Task 1: the priority wait key stays as the plan wrote it** (turn number, phase, stack length and top, passed count). A land play
  or a mana ability within one priority window does not refill the buffer (117.3c says the player receives priority again; the key
  doesn't change). Cost: a player who plays a land and taps mana before passing spends one buffer, not several.
- **Task 2: decline only where declining is harmless to the player whose clock ran out.** Where the decline or no-pay branch harms
  them (life loss, damage, sacrifice, discard, losing the game) the clock returns `[]` and the table decides. The spec's "never …
  eliminates" and the anti-goal outrank "decline optional choices" when they conflict. Optional payments are classified by the
  not-paid branch's own effects: harm to the payer → the table; a benefit to someone else only (Smothering Tithe's Treasure) → declined;
  a plain "you may pay … If you do" → declined; anything the module can't place → the table (guard test over every engine
  `optional_payment` definition: 784 cases over 92 definitions, 48 declined, all plain).
- **Task 2: tribute → left to the table** (702.104a: "if tribute wasn't paid" punishes the chooser).
- **Task 2: a commander's zone-change question → "yes"** (903.9a/b: to the command zone), scoped to the player's own commander.
- **Task 2: at Assisted, `combat_damage` confirm stays "yes" even when the damage kills an opponent** (510.2: combat damage is
  mandatory; the clock answers for the attacker; "never eliminates" protects the player whose clock ran out). An `sba_confirm` that
  would make any player lose is left to the table. Also from Task 2's review: the 509.1c fallback plans the fewest required blocks
  instead of the plan's "block with everything able".
- **Ruling A: a late click is refused when `seen_revision < acted_revision`**, where `acted_revision` is the revision of the first view
  that shows the clock's action (`room.revision + 1` at `mark_acted`). The plan wrote `<= R` for a pre-action `R`; its own test ("the
  same pass with the broadcast's revision is accepted") needs `<`.
- The plan's other "Resolved ambiguities", followed as written: the clock runs only with rules automation on (Assisted or Full) and not
  paused; `manual_resolution` and `reconcile` are left to the table (the player is still charged; at zero the log says the clock can't
  answer); nobody is charged while no seated human is connected; bank size changes never refill a bank (only Add time changes it); a
  decision waiting at a save or restart starts again with a full buffer on load, banks kept; a decision part-way through casting is
  cancelled (601.2, 733.1).
- Process rulings (ledger): B (implementers never ran the full suite; the controller does, `-n 4`), C (Task 7's screenshots and critique
  moved to the owner's checklist), D (the two-device check is the owner's; the `security-review` skill is replaced by an equivalent opus
  security pass, as the repository has no remote).

### Manual check on two devices

**NOT DONE — owner's to do** (ledger Rulings C and D). Set-up: a LAN Commander table with rules automation at **Full**, two devices
(say the host computer and a phone) in two seats, the lobby's **Turn clock** on, **Bank** 2 min, **Grace** 10 s, **At zero: Act for the
player**. Each line is an action and what you should see; write what you saw beside it.

- [ ] Start the game. The countdown on the seat plate of the player with priority matches on both screens (within a second), first the
      grace then the bank (`0:10 · 2:00` counting down), and the other plate is still.
- [ ] Let it run out. At zero the clock passes priority for that player, and the log on both screens says *<name> ran out of time:
      Fyodor acted for them.* Nobody concedes or loses.
- [ ] Mid-decision, lock the phone (let it sleep) for under 2 minutes, then wake it. Its plate read *Paused — reconnecting* on the
      other screen meanwhile; on return the bank and grace are what they were: it lost nothing.
- [ ] The host, in **⋯ → Host tools… → Turn clock**, presses **+1:00** for a player: the bank goes up by 1:00 on both screens, and
      the log says *The host added 1:00 to <name>'s clock.*
- [ ] Set **At zero** to **Only show it** and let a clock run out: it reads 0:00 and nothing happens (no pass, no log line).
- [ ] Turn the clock **Off** in Host tools: the countdown disappears from every plate, and the log says *The host turned the turn
      clock off.*
- [ ] Task 7's look (not done by its implementer, Ruling C): screenshots of the countdown chip on **both seat-plate variants** (the
      side layout and the flat one), with one clock running, one away and one at 0:00; of the lobby's **Turn clock** setting (off, on,
      Only show it); and of the **Turn clock** section of Host tools (with a player away, showing **Give 2 more minutes to
      reconnect**), each at **1920×1080**, **2560×1440** and a **laptop size** (e.g. 1366×768). Then an `impeccable` critique of them,
      and fix what fits the tabletop direction (`fyodor-ui-design`).

### Remaining risks

Accepted or deferred during execution (ledger), by task:

1. Task 1: `settings` can be changed in place without `validate_assignment` (only validated models are assigned today); a `sync` with
   the clock off keeps `_away_since` / `_grace_extra`; bank keys are unbounded in length (at most 12); with `rules` `None` the pregame
   is never charged; an extended grace takes effect from the next sync (the route pokes at once).
2. Task 1 ruling: a land play or a mana ability within one priority window does not refill the buffer (above).
3. Task 2: **more choices wait for the table.** Of the "unless … pay" cards the review swept, 6 are declined and about 68 go to the
   table; a timed-out player's game waits for the table there instead of moving on (the safe direction). Not planned:
   `must_be_blocked`, `must_block_all110e`, `declaration_groups`, "must be blocked by two" (they fall back to chump / all blocks, the
   engine judging each). `_unpaid_only_benefits_others` ignores extra keys on a benefit instruction (a "you create a token" whose token
   had a harmful trigger would be declined; none found in real cards or engine definitions).
4. Task 2 (gate point 8): the new `except Exception` in `_required_blocks` (above); when it fires, the fallback order reaches "all"
   blocks after the engine refused every smaller declaration.
5. Task 3: **the +1 revision invariant.** `mark_acted(pid, room.revision + 1)` relies on only `broadcast` bumping the revision and no
   `await` between the action and `mark_acted` (verified on every path today); reading the revision tick's own broadcast sends would be
   sturdier. A view sent outside a broadcast between the clock's action and tick's broadcast shows revision R (errs safe: refuses a
   little more). If `perform` raises between `hold` and its `try` (e.g. building `InterimStream`), the clock stays held until the next
   poke (any broadcast). `tick` waits while an "I have a response" hold is pending (rechecks every 0.5 s).
6. Task 4: 409 (not a LAN table / practice) is answered before 403 (non-host): it reveals only the mode and format, both visible; there
   is no practice-table 409 test; the grace test reads private `_grace_extra`; **+time** or **grace** with no clock silently creates an
   off clock; a lobby PATCH with `clock` replaces the whole `ClockSettings` (the lobby UI always sends the full object, tested).
7. Task 5: a damaged crash-record clock is ignored by `hub.restore` with a logged warning only; the crash test's downtime assertion is
   trivially true (the later act at zero is the real evidence) and polls up to 3 s; an extra reconnect grace is in memory only (not in
   the crash record); bank keys are not checked against the players.
8. Task 6: **the `seen_revision` 0 window.** `gameSocket` sends `seen_revision: 0` before the first snapshot; safe, but it refuses in a
   narrow window (better: send nothing while the revision is 0). Mulligan actions are not in `INTENT_TYPES`, so a late mulligan click
   isn't refused by `late()` (the engine's own refusals cover it: "You've already kept this hand"). The REST `tableAction` path carries
   no view revision and is unguarded by design. The race test sleeps in `prepare`; the `LATE` text is duplicated in the test.
9. Task 7: **the jitter step-back.** When the lowest-delay skew sample ages out of its window, the countdown can step back by the jitter
   difference (under 1 s). **The host field's disabled state:** Host tools' "Grace per decision" `CommitNumber` lost `disabled={busy}`
   (a second change can be sent while one is out; the server applies them in order). The screenshots and critique are not done (owner's
   checklist).
10. mypy: one more message on `night.py:246` (above): a follow-up.
11. Dependency upgrades still open from Stage 1: `pip`; `vite`, `source-map-js`, `vitest`, `@vitest/mocker`.
12. Stage 2's open items are unchanged by this stage (the clock route is not reachable through the invite link).

### Before merging

1. **FULL SUITE: pending controller run.**
2. **Independent review: pending (controller)** (the security pass and a fresh reviewer).
3. **Manual check on two devices** and Task 7's screenshots and critique: NOT DONE — owner's to do (checklist above).
4. The owner rules on gate point 8's `except Exception` in `clock_defaults._required_blocks` (accept, as Stage 2's was, or narrow).
5. Merge order: Stage 1, then Stage 2, then this branch. Do not merge until the owner has read this file.
