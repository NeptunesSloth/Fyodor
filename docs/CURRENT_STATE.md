# Current state — handoff for the next session

Written 2026-09-30 at the end of the session that fixed the review 5 findings (PR #7). Every fact
here was checked against git, CI and local runs at that time. Where something was not verified,
the text says so.

## Current repository state

| | |
|---|---|
| Repository | `NeptunesSloth/Fyodor` |
| `main` | The merge of **PR #7** (review 5 fixes + Claude skills). Before it: `bbde2cc` (merge of PR #6). |
| Open PRs | None expected once PR #7 is merged. Check with the GitHub tools before starting. |
| Branches | `claude/serene-faraday-f8knp9` (PR #7) is merged. `claude/blissful-turing-entypf` (PR #6) is merged. `claude/sharp-curie-nOXLF` is an unrelated old branch (207 behind `main`); ignore it. |
| Agent worktrees | None. The previous session's 34 worktrees lived in its container and are **gone**. |

### Work lost with the previous container

The handoff before this one listed four unmerged agent branches as "keep". They were never pushed,
and they no longer exist anywhere (not on `origin`, not as commits):

| Lost branch | What it was | What happened |
|---|---|---|
| `agent-review5-fixes` (`f188973`) | Review 5 fixes | **Rebuilt from scratch** in PR #7 (below). |
| `agent-modal` (`809b152`) | Modal triggered/activated abilities | Lost. Must be rebuilt. |
| `agent-conditionals` | Conditional / "instead" clauses (partial) | Lost. Must be rebuilt. |
| `agent-copy` | Copy system (partial) | Lost. Must be rebuilt. |

Lesson: push agent branches (or at least the lead's integration branch) before a session can end.

## Last known test status (PR #7 head)

| Check | Status |
|---|---|
| Backend pytest (full) | Passed locally on the final head, and in GitHub CI. |
| ruff (`backend`) / mypy (`app tools`, 142 files) | Passed locally and in CI. |
| Frontend typecheck / vitest / build | Passed in GitHub CI (no frontend files changed). |
| Playwright | Passed in GitHub CI. **Flaky once** on PR #7's first head: `e2e/automation.spec.ts:41` ("Automation FULL … play a land") drew 8 cards without finding an Island, on a commit that only added Markdown. Not reproduced since; root cause unknown. |
| Coverage tool | Run on the final head (numbers below). `data/reports` was **not** regenerated: the only differences from the committed reports come from the newer Scryfall snapshot. |

## Current Commander coverage

Data: Scryfall snapshot 2026-09-30, Comprehensive Rules 2026-09-25. `main` before PR #7 gives the
same numbers on this snapshot as on the 2026-09-28 one.

| | |
|---|---|
| Commander-legal cards | **32,068** |
| FULL | **12,643 (39.4%)** |
| PARTIAL | 19,425 |
| REVIEW | 0 |
| MANUAL | 0 |
| Possible commanders | 3,501 |
| Possible commanders FULL | **677** |
| Oracle text classified (automated, or sorted into a concrete missing capability) | 97.7% (2,622 clauses unclassified) |
| Ability features counted | 113,154 |

To reproduce: build the card database with `scripts/update-cards.sh --images none` (about a
minute; it downloads Scryfall bulk data), then run `python -m tools.commander_coverage` from
`backend/`. Use `--out <dir>` to keep the committed reports untouched.

## What PR #7 added

- **Claude skills** (`.claude/skills/`):
  - `caveman`: upstream output-compression skill, verbatim (commit `2fd153c` of
    JuliusBrussee/caveman).
  - `mtg-rules-research`: how to research rules for this engine (authority order, narrow CR
    lookups, required output template). Use it before implementing rules features.
- **Review 5 fixes** (`backend/tests/test_rules_review5.py`, 15 scenarios):
  - 701.21a: "sacrifice it" only sacrifices a permanent the ability's controller still controls.
    Evoke's "its controller sacrifices it" (702.74a) uses the current controller (`"by":
    "controller"` on the `sacrifice` effect).
  - 800.4a / 610.3: when a player leaves, what the permanents they owned exiled "until ~ leaves the
    battlefield" returns, all at once (610.3d). The leaver's own exiled cards stay (800.4b). A
    per-card MANUAL source is left to the players.
  - 800.4a / 611.2b: "for as long as …" effects end when their source left the game with its owner.
  - 800.4m: "until your next turn" of a player who left ends when that turn would have begun.
  - 800.4a: selector counts ignore every zone of a player who left (`selectors.candidates`).
  - 400.7: linked exile records the exiled rules objects (`<card id>.<n>`); a card that left exile
    and came back isn't returned. Old saves (card ids) still load.
  - Continuous effects remember the table markers they wrote (`ContinuousEffect.markers`; `None`
    for effects from older saves). Ending one removes only its own markers, also for two-part
    clauses ("gets +2/+2 and gains flying until your next turn").
  - A returning Aura (Banishing Light on Pacifism) asks what it enchants (303.4f) instead of
    crashing.
  - When the active player leaves, the turn's cleanup (514.2) happens before the next turn starts
    (`engine.end_turn_early`).
  - "Exile target … card from a graveyard until ~ leaves the battlefield" is no longer automated:
    610.3 would return it to the graveyard, and the linked return only knows the battlefield.
- An independent reviewer (read-only) attacked the first version; its blocking finding (evoke) and
  valid should-fix findings are fixed above, with its repro tests ported.

## What is already built (unchanged from before PR #7)

- **Architecture.** The server is authoritative (FastAPI in `backend/`). Clients send intents.
  Each intent is compiled on a `Plan`, a scratch copy of the state: an `ActionError` aborts the
  whole intent. `plan.do` records steps, so replay is deterministic (`history.rebuild()`
  reproduces the state). `RulesState` holds decisions whose `resume` payloads let a pause survive.
  The React/TS frontend in `frontend/` renders only what the server sends each viewer.
- **Automation OFF / ASSISTED / FULL**, per-card overrides, presets. **Response modes** OFF / AUTO /
  ON, stops, the stack helper. **Mana and payment**: AUTO / ASK / MANUAL, source protection; the
  player taps their own lands.
- **Object identity, last-known information, event batches**: `card.n` gives a new object on every
  zone change (400.7); LKI snapshots; a controller change keeps the same object.
- **Resolution and trigger context**: `ObjectRef`, `TriggerEvent` (`game/rules_state.py`),
  `app/rules/context.py` (`ref:<name>` bindings for objects, players, amounts and payment results),
  optional payment / "if you do" (`optional_payment.py`). Built in PR #6; do not rebuild.
- **Selectors, values, effect grammar, triggers** (including delayed triggers, "one or more"
  batching, combat variants, once-each-turn), **conditions**, **multiple targets**, **costs**
  (kicker, optional payments), **cast permissions and cost modifiers**, **statics and layers**
  (613 fixpoint, timestamps, animation in layers 4–7b), **replacement effects stage 1**,
  **activation restrictions**, **attachments**, planeswalker basics.
- **Commander tooling**: legality from card data; `tools/commander_coverage.py` writes
  `data/reports/*`. Gap-ranking scripts from earlier sessions are lost; rebuild if needed.
- **Rules research tooling**: stored CR at
  `data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt`;
  `python -m tools.rules_research.search <term | rule number>` from `backend/`.
- **Privacy**: per-viewer views; hidden cards carry no identity metadata; structured decision
  view (a non-chooser sees only `{type: "PLAYER_MAKING_CHOICE", chooser}`).
- **Manual fallback**, deterministic **replay / undo / save** (decisions survive save/load).
- **2D table** shipped. 3D table and plane themes postponed (late-stage work).

## Top remaining rules gaps

From the last gap ranking (at `4b514c5`, before later merges). Treat the numbers as upper bounds
and rerun a ranking before choosing.

| Cluster | PARTIAL cards | Sole blocker (cards) | Status |
|---|---|---|---|
| Modal triggered/activated abilities (603.3c, 700.2) | 270 | 100 | **Open** — the earlier branch was lost |
| Conditional / "instead" clauses | 905 | 418 | **Open** — lost partial work |
| Copy system (707, 707.10) | 487 | 113 | **Open** — lost partial work |
| Mana wording / rituals | 563 | 309 | Open |
| Keyword lines (unsupported keywords, non-mana ward) | 2,288 | 822 | Open |
| Replacement effects stage 2 (doubling, redirection, draw/life replacements, 616.1 ordering) | 1,048 | 606 | Open |
| Temporary quoted grants with a duration | 791 | 403 | Keyword/pump riders done; quoted grants open |
| Player-level restrictions ("can't gain life", "can't lose") | 641 | 356 | Blocking restrictions done |
| Dynamic amounts, multi-target forms, player choices, selectors | — | — | Largely done |
| "OTHER" residue | 2,626 | 998 | Not yet clustered |

The current coverage report's top missing features (`data/reports/commander_rules_coverage.md`,
"Top Commander features to implement next") start with: "choose n …" modes, ±N/±N counters,
"pay {m}", "draw n" riders, ward, and target selectors.

## Known shipped limitations

- **800.4j is simplified**: when the active player leaves, the engine ends their turn at once
  (after its 514.2 cleanup) instead of letting it continue without an active player. That turn's
  remaining steps are skipped, so its "at the beginning of the end step" triggers (including
  delayed ones created that turn) fire at the next end step instead.
- **800.4a, reanimated permanents**: a permanent the leaver put onto the battlefield under their own
  control (not through a control-changing effect) is returned to its owner; the rule exiles it.
- **610.3d for ordinary departures**: when several "until ~ leaves" sources leave at once (a board
  wipe), their exiled cards return one source at a time rather than simultaneously. (A player
  leaving already returns them together.)
- **701.21a in the echo / "sacrifice ~ unless you pay" path** (`effects.py`, unless-pay sacrifice):
  no check that the payer still controls the permanent.
- **No copy system.** Storm and copied spells can't be made or choose new targets; clones stay
  manual.
- **Non-mana ward costs** are unsupported (manual).
- **903.9b without a remembered answer:** the commander briefly lands in the hand or library, then
  its owner is asked. With a remembered "yes" it goes straight to the command zone.
- **`prevent_all` bug:** records created on resolution don't store `source_card`; Gideon uses a
  `prevent_self` workaround.
- **Quoted grants** (`app/rules/granted.py`): "Until end of turn, target creature gets +2/+0 and gains
  "When this creature dies, …"", "creatures you control gain "{T}: …"", "It gains "…"" (no duration: the
  game), "… becomes a … creature with "…". It's still a land.", "for as long as you control ~" /
  "… has a bounty counter on it" / "until your next turn". Only abilities read from the object as it
  is now are granted (triggered, activated, mana, characteristic-defining P/T, "If ~ would die, exile
  it instead"; "can't be blocked" and the like become restrictions on the same objects). Other
  statics granted by an effect (anthems, conditional statics such as Restless Spire's first strike),
  permissions ("you may cast this card from exile"), grants to cards in other zones or to players,
  and a quote that names its granter (Hellish Rebuke) stay manual. "You don't lose this mana" is manual.
- **Simultaneous entries** are processed one after another; 613.7m (APNAP order of simultaneous
  entries) isn't tracked.
- **"Before attackers are declared"** is modelled conservatively.
- `begin_resolution`'s "may" memory key uses `effects[0]["do"]`: two do-once triggers from
  same-named cards share a remembered answer.
- **Battles** aren't attackable; damage to a battle removes defense counters.
- **Fixture caveat:** the Karador/Kess test fixtures use simplified wording.
- `coverage.REFUSED` still lists "fight" and "choose_targets" (harmless).

## Rules and architecture decisions to preserve

- **Commander-only** card automation scope; coverage is measured over Commander-legal cards.
- The stored **current Comprehensive Rules are authoritative.** Never rely on remembered rules
  (use the `mtg-rules-research` skill).
- **No LLM as a runtime rules judge.** Card text is never executed; scripts are declarative data.
- **Unsupported behavior falls back to manual.** Wrong automation is worse than manual: refuse
  rather than guess. A card is **FULL** only with complete, tested behavior.
- The **rules engine is authoritative**; the renderer is not. Manual moves stay available.
- **Hidden information must never leak.**
- Work reusable gaps ranked by data. **Do not chase cards one by one.**
- An independent rules review comes before merging risky subsystems.
- 3D polish, plane themes, decorative toys, the command palette and final screenshots are
  **late-stage work**.
- Security: validate WebSocket messages and file imports, no path traversal, no telemetry, no need
  for Internet access during games.

## Next session start instructions

1. Start a **fresh session** from `main`. Check open PRs and `main`'s CI first; if red, fix that.
2. Set up the backend: `cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
   'mypy==2.3.1'`. For coverage, build the card DB (`scripts/update-cards.sh --images none`).
3. Read this file, `docs/ARCHITECTURE.md`, `docs/RULES_COVERAGE.md`, `docs/AUTOMATION_UX.md`.
4. **Next subsystem: modal triggered/activated abilities** (603.3c, 700.2): modes are chosen as the
   ability is put on the stack, "choose one that hasn't been chosen", modes with their own targets.
   Modal *spells* already exist (`1d2298f`, "modal spells (700.2) with a target per mode"). Then:
   conditionals, copy, mana wording, keywords.
5. Workflow: plan → at most 2 implementation agents (Sonnet) with narrow file ownership + 1
   read-only analysis agent → targeted tests → one integration run (ruff, mypy, full pytest,
   coverage) → an independent reviewer (Opus) → fix findings → PR → green CI → merge → update
   this file.
6. **Push every agent branch you intend to keep** before ending a session.

## Usage control

- Fresh session per major PR; no large agent swarms; Sonnet for routine workers, Opus for
  architecture and high-risk review.
- Narrow agent scopes; don't reread the whole repository or the Comprehensive Rules.
- Targeted tests while implementing; full verification only at integration checkpoints. (The full
  backend suite takes a few minutes locally and about 2 minutes in CI.)
