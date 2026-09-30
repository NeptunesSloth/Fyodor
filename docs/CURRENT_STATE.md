# Current state — handoff for the next session

Written 2026-09-30 when a stop request ended the session. Every fact here was checked against git
and the logs at that time. Where something was not verified, the text says so.

## Current repository state

| | |
|---|---|
| Repository | `NeptunesSloth/Fyodor` |
| Working branch | `claude/blissful-turing-entypf` |
| Branch HEAD | `5f61da3` (pushed; this handoff adds one docs-only commit on top) |
| `main` | `d07fd05` (merge of PR #5) |
| Branch vs `main` | 85 commits ahead, 0 behind |
| Open PR | **#6** — draft, open — https://github.com/NeptunesSloth/Fyodor/pull/6 |
| PR #6 state | Last known mergeable (clean). Its description is **out of date** (written at the start of the PR). |
| Working tree (main checkout) | Clean. Everything verified is committed and pushed. |
| Scheduled check-in | Routine `trig_01Kvdtg6TfQaHEJ7riBWGw5f` ("Re-check PR #6 CI") re-arms itself each time it fires. Delete it if the PR is no longer being watched. |

### Agent worktrees (`.claude/worktrees/`, excluded via `.git/info/exclude`)

There are 34 worktrees. **Nothing in them is needed except the four marked "keep" below.** The
others are either already merged into the branch or are stale scratch copies. Clean up with
`git worktree remove --force <path>` once you have looked at the keep list.

| Worktree / branch | State | What to do |
|---|---|---|
| `agent-a5b699a9bf410c614` / `agent-modal` @ `809b152` | **Not merged.** Modal triggered/activated abilities. The agent was killed by the usage limit while re-running checks after merging the base. The branch has commits, but they are **unverified**, and there is no report. | **Keep.** Re-verify (ruff, mypy, full suite, coverage audit) before any merge. |
| `agent-a655e71aa60d4e6d1` / `agent-review5-fixes` @ `f188973` | **Not merged.** Fixes for review 5, findings 2–6, 8 and 9 (commit `70ce89a` plus a merge of the base). Killed while running checks: **unverified**, no report. | **Keep.** Re-verify, read the diff, merge if green. |
| `agent-adcd65efa59df1ba2` / `agent-conditionals` @ `2cd5031` | Conditional / "instead" clauses. **Uncommitted, partial** edits in `conditions.py`, `coverage.py`, `effects.py`, `language.py`, `scripts.py`, `tests/test_rules_statics.py`, plus `data/reports`. Never tested. | **Keep** as reference, or discard. Not safe to merge as it is. |
| `agent-a4199f56cc6c6211d` / `agent-copy` @ `2cd5031` | Copy system. **Uncommitted, partial** edits in `rules_state.py`, `coverage.py`, `effects.py`, `layers.py`, `scripts.py`, plus untracked new files `app/rules/copy.py` and `tests/test_rules_copy.py`. Never tested. | **Keep** as reference, or discard. Not safe to merge as it is. |
| `review3`, `review4` | The reviewers' throwaway repro tests (`test_review3_*.py`, `test_review4_*.py`), untracked. | Their findings are fixed and ported. Discard. |
| `agent-triggers` (1 of 2), `agent-pay` (1 of 2), `agent-statics`, `agent-permissions` (1 of 2), `agent-refs` (1 of 2) | Old dirty copies from the first, rate-limited round. Their work was redone and merged. | Discard. |
| All other `agent-*`, `mt-groups`, `costs-kicker` | Merged into the branch. (`agent-library` @ `24b0283` shows as "not merged" only because its last commit is a merge of the base; its content is merged.) | Discard. |

The review 5 repro tests are at `/tmp/claude-0/.../scratchpad/test_review5_findings.py`. That is
scratch space for this session only and will not survive it. The fixes branch above ports them.

## Last known test status

| Check | Status |
|---|---|
| Backend pytest | **Passed at `bc25b55`** (the combat-trigger merge). `5f61da3` only regenerates `data/reports`, so the code is identical. The earlier count was 1483 tests at `3d2a40e`; more tests were added since, and the exact count at `bc25b55` wasn't captured. |
| ruff (`app tools tests`) | **Passed at `bc25b55`.** |
| mypy 2.3.1 (`app tools`, 142 files) | **Passed at `bc25b55`.** |
| Frontend typecheck / vitest / build | **Not run locally during PR #6.** Passed in GitHub CI at `23a870b`. No frontend files changed in PR #6. |
| Playwright | Passed in GitHub CI at `23a870b`. Not run since. |
| GitHub CI | **Fully green at `23a870b`** (backend, frontend, Playwright). At `1e9aaec`, a `check_suite.completed` event arrived with no failure, but individual jobs weren't checked. **Unknown** for every later commit (`e06f2ed` … `5f61da3`). |
| Coverage tool | Regenerated at `bc25b55`; its output is committed in `5f61da3`. |

## Current Commander coverage (at `bc25b55`)

Data: Scryfall snapshot 2026-09-28, Comprehensive Rules 2026-09-25.

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

PR #6 started at 8,855 FULL / 342 commanders (the end of PR #5) and at 32,116 legal cards. The
count dropped by 48 when the legality fix removed Unfinity sticker sheets.

## What is already built

- **Architecture.** The server is authoritative (FastAPI in `backend/`). Clients send intents.
  Each intent is compiled on a `Plan`, a scratch copy of the state: an `ActionError` aborts the
  whole intent. `plan.do` records steps, so replay is deterministic (`history.rebuild()`
  reproduces the state). `RulesState` holds decisions whose `resume` payloads let a pause survive.
  The React/TS frontend in `frontend/` renders only what the server sends each viewer.
- **Automation OFF / ASSISTED / FULL**, per-card overrides, presets.
- **Response modes** OFF / AUTO / ON, stops, the stack helper.
- **Mana and payment.** AUTO / ASK / MANUAL payment and source protection. The player taps their
  own lands; the engine never taps them.
- **Object identity, last-known information, event batches.**
  - `card.n` gives a new object on every zone change (400.7).
  - An LKI snapshot records power, toughness, types-as-token and face-down status.
  - A controller change keeps the same object.
- **Shared context contract (lead-owned):** `ObjectRef` and `TriggerEvent` in
  `game/rules_state.py`, and `app/rules/context.py`. See "Resolution and trigger context" below.
- **Selectors** (`selectors.py`): combat status, defending player per attacker (508.5a),
  type unions, zone-scoped selectors.
- **Values** (`values.py`):
  - counts by domain, distinct-ness, devotion, life, counters, max/sum, twice/half, compound X;
  - characteristic-defining power/toughness in every zone;
  - "+N/+N for each" statics.
- **Effect grammar**: `language.py`, `scripts.py` and friends. One-shot effects, library
  manipulation, player choices (edicts, hand reveal), keyword actions (amass, connive,
  monstrosity, bolster, support), token wording, bite and fight, animation.
- **Triggers** (`triggers.py`, `events.py`):
  - trigger event context and "one or more" batching;
  - leaves-the-battlefield look-back;
  - combat trigger variants;
  - delayed triggers (`delayed.py`, 603.7);
  - "triggers only once each turn" and "do this only once each turn" (603.2h).
- **Conditions** (`conditions.py`): intervening "if", counts, life, hand, "succeeded".
- **Multiple targets**: target groups, divided damage, "other" and "another", abilities on the
  stack as targets.
- **Costs**: non-mana cost components, kicker and multikicker, optional payments
  ("you may pay … if you do", "unless … pays").
- **Cast permissions and cost modifiers** (`permissions.py`, the 601.2f pipeline).
- **Statics** (`statics.py`, `layers.py`):
  - anthems and granted abilities in layer order;
  - the 613.8 fixpoint and 613.7 timestamps;
  - evasion and restriction statics;
  - animation in layers 4–7b.
- **Replacement effects, stage 1** (`replacements.py`):
  - a unified entering path (enters tapped, enters with counters, shock lands, "as ~ enters,
    choose");
  - "would die / from anywhere → exile";
  - unearth and madness;
  - 903.9b for any move to a hand or library;
  - damage prevention with the 615.7 shield choice.
- **Activation restrictions** (`restrictions.py`, 602.5).
- **Attachments**, and the basics of planeswalkers and loyalty abilities.
- **Commander tooling**:
  - Legality comes from the card data.
  - `tools/commander_coverage.py` writes `data/reports/*`.
  - The gap-ranking scripts lived in the session scratchpad and are lost; rebuild them if needed.
- **Rules research tooling**: the stored rules text is
  `data/rules/comprehensive_rules/2026-09-25/comprehensive_rules.txt`.
- **Privacy**:
  - Per-viewer views; hidden cards carry no identity metadata.
  - A structured decision view: a non-chooser sees only `{type: "PLAYER_MAKING_CHOICE", chooser}`.
  - Reveal and look-at-top are modelled server-side.
- **Manual fallback**: anything unsupported stays manual (the physical tabletop).
- **Replay, undo and save** are deterministic. Decisions survive a save/load mid-choice.
- **2D table**: shipped. **3D table and plane themes**: postponed (late-stage work).

## Resolution and trigger context (already built — the "next planned subsystem" is done)

These were planned as the next subsystem. They were **built and merged in PR #6**; do not
rebuild them.

- **`ObjectRef`** (`game/rules_state.py`): `card` + `object_id` + `zone` + optional LKI
  `snapshot`. It names one rules object. After a zone change, it doesn't match the new object
  (400.7). A controller change keeps the match.
- **Resolution context** (`app/rules/context.py`): the resolving ability's `ctx["refs"]` holds
  explicit named bindings — objects (with `was` for information), players, amounts and payment
  results. Effects address them as `ref:<name>`, `ref:<name>.controller` / `.owner`,
  `{"power": "ref:<name>"}` and `{"ref_amount": name}`. The engine never rescans the board.
- **Trigger event context** (`TriggerEvent`): what a trigger triggered on, captured when it
  triggered. It holds the objects (with LKI), the new objects, the players, the source, the amount
  and the count. It is carried PendingTrigger → StackEntry → `ctx["event"]` and addressed as
  `event`, `event.new` and `event_player`.
- **Optional payment / "if you do"** (`optional_payment.py`): a transactional PAY/DECLINE with no
  partial payment. It binds `payment` under an explicit name, and conditions test
  `{"succeeded": name}`. There is no global "last action succeeded".

## Current work that was in progress

Every agent was stopped by usage limits or by the stop request. **No uncommitted work exists in
the main checkout.**

| Item | Goal | State | Safe to discard? |
|---|---|---|---|
| Review 5 fixes (`agent-review5-fixes`, `f188973`) | A delayed "sacrifice it" must check control (701.21a). A leaving player's permanents must leave the game (800.4a, 610.3): exile-until returns, "for as long as you control" ends. "Until your next turn" must end when the leaver's turn would have begun. Counts must ignore departed players' zones. Linked exile should key on object id. Markers should key on effect id. | Committed on its branch; **checks never completed**; not merged. | Keep: these are real bugs, see limitations. |
| Modal triggered/activated abilities (`agent-modal`, `809b152`) | Modes chosen when the ability goes on the stack (603.3c, 700.2), "choose one that hasn't been chosen", modes with their own targets. | Committed on its branch; **unverified**; no report. | Keep; re-verify. |
| Conditional / "instead" clauses (`agent-conditionals`) | "X. If <cond>, Y instead", "if you search your library this way, shuffle", "unless you discard / pay", raid-style conditions. | **Uncommitted partial** edits in the worktree; untested. | Yes, if you'd rather restart. |
| Copy system (`agent-copy`) | Copy target spell (choose new targets, 707.10), token copies (707), a layer-1 copy step, Clone-style "enter as a copy". | **Uncommitted partial** edits plus new `copy.py`; untested. | Yes, if you'd rather restart. |

Items 9 (mana wording / rituals), 10 (remaining keywords + non-mana ward), 11 (residue pass) and
12 (engine-level gaps) were **not started**.

## Top remaining rules gaps

These are from the last gap-ranking run, at `4b514c5`, before the later merges. Treat the numbers
as **upper bounds**: clusters marked "largely done" were worked on afterwards. Rerun the ranking
before choosing.

| # | Cluster | PARTIAL cards | Sole blocker (cards) | Status since |
|---|---|---|---|---|
| 1 | References to objects from earlier in the same effect | (built) | — | Done (context refs) |
| 2 | Trigger-event references | (built) | — | Done |
| 3 | "You may pay / sacrifice … if you do", "unless … pays" | (built) | — | Done; spells' `succeeded` gates were fixed in `830c27a` |
| 4 | More trigger events | (built) | — | Done, plus combat variants |
| 5 | Static anthem / grant grammar | (built) | — | Done; a quoted grant with a duration is still missing |
| 6 | Dynamic amounts | 2,059 | 1,016 | Largely done (+323) |
| 7 | Cost modifiers / cast permissions | (built) | — | Done (open review-2 items fixed) |
| 8 | Remaining multi-target forms | 1,030 | 566 | Largely done (+184); some forms are refused (see `coverage.REFUSED`) |
| 9 | Library manipulation | 540 | 141 | Largely done |
| 10 | Conditional clauses | 905 | 418 | **Open** (partial worktree) |
| 11 | Player choices | 1,184 | 400 | Largely done (edicts, hand reveal, choose a color/type) |
| 12 | Selector gaps | 789 | 377 | Partly done |
| 13 | Combat trigger variants | 398 | 67 (125 commanders) | Done (+53) |
| 14 | Delayed triggers / durations | 827 | 258 | Done (+119) |
| 15 | Conditional statics ("as long as …") | — | — | Partly done (statics conditions); devotion statics are refused |
| 16 | Evasion / player restrictions | 641 | 356 | Blocking restrictions done; player-level ones ("can't gain life", "can't lose") **open** |
| 17 | Temporary non-keyword grants | 791 | 403 | Keyword/pump riders done (+340); quoted grants with a duration **open** |
| 18 | Replacement effects | 1,048 | 606 | Stage 1 done; doubling, redirection, draw/life replacements and 616.1 ordering **open** |
| 19 | Activation restrictions | 868 | 267 | Done (+222) |
| 20 | Keyword actions | 522 | 171 | Partly done; goad, earthbend and incubate refused |
| — | Copy system | 487 | 113 | **Open** (partial worktree) |
| — | Modal triggered/activated | 270 | 100 | **Open** (unverified branch) |
| — | Mana wording / rituals | 563 | 309 | **Open** |
| — | Keyword lines (unsupported keywords) | 2,288 | 822 | **Open** |
| — | Animation | 436 | 228 | Done (+157) |
| — | "OTHER" residue | 2,626 | 998 | Not yet clustered |

## Known shipped limitations (true at `5f61da3`)

- **No copy system.** Storm and copied spells can't be made or choose new targets; clones stay
  manual.
- **Non-mana ward costs** are unsupported (manual).
- **Review 5 bugs, open until `agent-review5-fixes` merges:**
  - A delayed "sacrifice it" whose creature changed control is still sacrificed. With the
    `e06f2ed` context fix the reference now survives, so this is **reachable**. Affects Lowland
    Oaf, Kiki-Jiki-style effects.
  - A leaving player's "exile until ~ leaves" never returns the card, and their "for as long as
    you control" effects never end.
  - "Until your next turn" never ends if its controller leaves.
  - Tarmogoyf-style counts still read a departed player's graveyard.
- **903.9b without a remembered answer:** the commander briefly lands in the hand or library, then
  its owner is asked. The rules say it should be "instead". With a remembered "yes" it goes
  straight to the command zone.
- **"Dies" triggers miss animated permanents and crewed Vehicles.** LKI keeps power and toughness
  but not types. There is a strict xfail test for this.
- **`prevent_all` bug:** records created on resolution don't store `source_card`, so a resolved
  "Prevent all damage that would be dealt to ~ this turn" never matches. Gideon uses a
  `prevent_self` workaround.
- **Gaps in grants:** quoted granted abilities with a duration ("gains '…' until end of turn") and
  "you don't lose this mana" are unsupported (manual).
- **Simultaneous entries** are processed one after another. An "unless you control …" land can see
  a card that entered with it.
- **"Before attackers are declared"** is modelled conservatively: untap through beginning of
  combat of any combat.
- `begin_resolution`'s "may" memory key uses `effects[0]["do"]`. Two do-once triggers from
  same-named cards share a remembered answer.
- **613.7m** (APNAP order of simultaneous entries) isn't tracked. Timestamps use creation order.
- **Battles**: not modelled as attackable. Damage to a battle removes defense counters.
- **Fixture caveat:** the Karador/Kess test fixtures use simplified wording; the real Oracle texts
  are PARTIAL.
- `coverage.REFUSED` still lists "fight" and "choose_targets" (harmless; both primitives now
  exist).

## Rules and architecture decisions to preserve

- **Commander-only** card automation scope; coverage is measured over Commander-legal cards.
- The stored **current Comprehensive Rules are authoritative.** Never rely on remembered rules.
- **No LLM as a runtime rules judge.** Card text is never executed; scripts are declarative data.
- **Unsupported behavior falls back to manual.** Wrong automation is worse than manual: refuse
  rather than guess.
- The **rules engine is authoritative**; the renderer is not. The physical-tabletop freedom
  (manual moves) stays available.
- **Hidden information must never leak.** No identity metadata for hidden cards; no CSS hiding;
  a structured, per-viewer decision view.
- A card is **FULL** only with complete, tested behavior. Audit newly-FULL cards against Oracle
  text.
- Work reusable gaps ranked by data. **Do not chase cards one by one.**
- An independent rules review comes before merging risky subsystems (replacement effects, layers).
- Themed plane tables, 3D polish, decorative toys, the command palette and final screenshots are
  **late-stage work**.
- Security: validate WebSocket messages and file imports, no path traversal, no telemetry, and no
  need for Internet access during games.

## Next session start instructions

1. `git fetch origin` and check out `claude/blissful-turing-entypf`. Confirm HEAD matches this file
   plus the docs commit, and that the tree is clean.
2. Read `docs/CURRENT_STATE.md` (this file), `docs/ARCHITECTURE.md`, `docs/RULES_COVERAGE.md` and
   `docs/AUTOMATION_UX.md`.
3. Check PR #6's CI on the current head. If it's red, fix that first.
4. **First task:** verify and merge `agent-review5-fixes` (`f188973`):
   - read its diff;
   - run `ruff check app tools tests`, `mypy app tools` and the full `pytest`;
   - regenerate coverage;
   - merge and push.

   It fixes reachable wrong-automation bugs.
5. Then close PR #6:
   - update its description with the metrics above;
   - run the frontend typecheck, unit tests, build and Playwright once;
   - wait for green CI;
   - mark it ready and merge;
   - start a fresh branch and PR from `main` for the next subsystem.
6. Continue with the highest-value unfinished rules subsystem, in this order: modal abilities
   (verify `agent-modal`), conditionals, copy, mana wording, then keywords.
7. Use limited subagents:
   - 1 lead;
   - at most 2 implementation agents;
   - 1 read-only analysis agent;
   - an independent reviewer only after a coherent batch.
8. Prefer Sonnet for workers; keep Opus for architecture and high-risk review.
9. Keep agent scopes narrow (named files and regions). Don't rebuild context by rereading the whole
   repository.

## Usage control for the next session

We are reducing Claude Code usage. Optimize for **correct Commander coverage gained per token**.

Do NOT:
- run large agent swarms (this session ran 6–8 at once and hit limits repeatedly);
- use Opus for routine worker tasks;
- keep one session alive across multiple major PRs;
- repeatedly scan the entire repository or the Comprehensive Rules;
- rerun the full suite (~10 minutes) after every small edit.

Do:
- use a fresh session per major PR;
- give workers narrow scopes;
- run targeted tests during implementation;
- do full verification (ruff, mypy, full pytest, coverage regen) only at coherent integration
  checkpoints.
