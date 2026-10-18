# Fyodor wave 30 — shared agent brief (read fully before starting)

Fyodor: Commander-only deterministic MTG rules engine. Repo `NeptunesSloth/Fyodor`. Base for wave 30: branch
`claude/vibrant-hamilton-e00gs8` (main + review-30 random-bottom fix). You work in your OWN git worktree.

## Non-negotiable policies
- Read `.claude/skills/fyodor-game-development/SKILL.md` and `.claude/skills/mtg-rules-research/SKILL.md` first.
- Rules questions: the stored Comprehensive Rules (2026-09-25) are authoritative. Look rules up:
  `cd backend && PYTHONPATH=$PWD /home/user/Fyodor/backend/.venv/bin/python -m tools.rules_research.search "<term or 702.85>"`.
  Never answer rules from memory; cite rule numbers in code comments. Official rulings (Gatherer / Scryfall rulings API) when needed.
- Wrong automation is worse than manual. Refuse rather than guess. Never fake FULL. Unsettled rulings ⇒ keep manual.
- No LLM judge at runtime, card text never executed; scripts are declarative.
- Hidden information never leaks (views, log lines, prompts, option labels, leaks by omission).
- Every new behavior: scenario test with REAL Oracle text + `replay_matches` + save/load round trip (`tests/wave9c_kit.py`:
  `build`, `check`, `reloaded`). New rules-state fields need defaults so old saves load.
- Reuse existing machinery (grep before writing). Mark code blocks `# -- <area> (wave 30X) --`; tests in
  `backend/tests/test_rules_wave30<x>_<area>.py`. Match the surrounding code style (dense comments citing CR).
- Do NOT edit `docs/CURRENT_STATE.md`.

## Environment (shared venv is an editable install of the MAIN checkout — you MUST override the path)
- Run everything from your worktree's `backend/` with `PYTHONPATH=$PWD` and the shared interpreter:
  `cd <worktree>/backend && PYTHONPATH=$PWD /home/user/Fyodor/backend/.venv/bin/python -m pytest -p no:cacheprovider tests/<file>.py`
  Verify once: `PYTHONPATH=$PWD /home/user/Fyodor/backend/.venv/bin/python -c "import app; print(app.__file__)"` must print YOUR worktree path.
- Card DB (real Oracle text for coverage tools and for fixtures): `/home/user/Fyodor/data/cards.sqlite`
  (pass `--db /home/user/Fyodor/data/cards.sqlite` to tools). Tests build their own fixture DB from `tests/fixtures`.
- Helpers (run from your worktree backend with PYTHONPATH=$PWD; they read ../data/cards.sqlite — create a symlink
  `ln -s /home/user/Fyodor/data/cards.sqlite <worktree>/data/cards.sqlite` first):
  - `/tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/tools/cardq.py "<oracle regex>" [--level FULL|PARTIAL] [--defs] [--limit N] [--grep-def SUBSTR]`
  - `/tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/tools/fixture_of.py "Card Name" ...` → JSON fixture entries with real Oracle text
    (see `tests/test_rules_review30_random_bottom.py` for how a test loads them).
- 4 CPUs are shared by 4–5 agents: run TARGETED tests (`-n 1` or no xdist). Do NOT run the full suite; the lead does.
- Lint/type on your changed files: `/home/user/Fyodor/backend/.venv/bin/ruff check app tests && PYTHONPATH=$PWD /home/user/Fyodor/backend/.venv/bin/mypy app tools`.

## Coverage delta (required if your change can affect classification)
`cd <worktree>/backend && PYTHONPATH=$PWD /home/user/Fyodor/backend/.venv/bin/python /tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/tools/levels.py --out /tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/levels_<track>.json`
then diff against the base dump `/tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/base/levels.json`:
`/home/user/Fyodor/backend/.venv/bin/python /tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/tools/levels_diff.py <base> <new>`.
Inspect EVERY card whose level changed (gained AND lost). Report gained FULL, lost FULL, commanders gained.

## Work contract
1. Inspect existing architecture. 2. Research the rules (cite). 3. Identify the exact missing primitive.
4. Failing tests first where practical. 5. Smallest reusable fix. 6. Targeted tests. 7. Coverage delta if relevant.
8. Commit (message ends with the two lines below) and push: `git push -u origin HEAD:<your branch name>` (retry 4x with backoff on network errors).
9. Final message (≤ 40 lines): branch, SHA, what changed, CR refs, tests added/run, coverage delta, cards kept manual,
   risks for the reviewer, anything uncertain.

Commit message trailer (exactly):
```
Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RxoLossQRU8DjpTEzMUC2E
```
Keep your context small: grep narrowly, read only the functions you need, don't dump big files. Finish before your context grows large;
if you run long, commit WIP, push, and report what remains.

## Ponytail ULTRA (user directive, overrides any urge to build)
- YAGNI extremist. Deletion before addition. Smallest diff that is CORRECT. No new modules/abstractions/config unless an existing one can't hold it.
- Reuse what's already in the codebase (grep first). Fix root causes once in the shared function, not per caller.
- If a requested item isn't needed (already works, rare, or risky for little value): say so in one line, pin current behavior with ONE test, move on.
- Still never lazy about understanding the flow, rules correctness, hidden info, or tests: one real-Oracle test + replay/save-load per behavior.
- Report terse: what changed, what was skipped and when to add it.

## Round 3 notes (lead)
- The shared base dump is STALE. Make your OWN base dump at your starting HEAD (levels.py --out .../levels_<track>_base.json) before changing code, and diff against it.
- Start from `git fetch origin claude/vibrant-hamilton-e00gs8 && git reset --hard origin/claude/vibrant-hamilton-e00gs8` (head 36fb38ec or later: waves 30A–30O merged, FULL 25,107).
- Gap data: /tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/ck7/inventory.json (fresh) and analysis/classified.jsonl (older capability labels: re-check each card's current level with cardq.py before working on it).

## Round 4 = wave 31 (lead) — supersedes the Round 3 notes
- Start: `git fetch origin claude/vibrant-hamilton-e00gs8 && git reset --hard origin/claude/vibrant-hamilton-e00gs8` (head 2b78c7f3: waves 30A–30U + reviews merged, FULL 25,218, commanders 2,255).
- Base dump at that code: /tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/final/levels.json (you may still make your own at your start).
- Fresh gap data: /tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/final/inventory.json
  (cards[] with level, commander, missing[{text, family, refusal}]). Query helper: `python3 .../scratchpad/q31b.py "<regex>" [N]`
  lists non-FULL cards with a missing line matching the regex (first column = number of blocking lines; 1 = this line alone blocks FULL).
- Branch: push to `claude/vibrant-hamilton-e00gs8-w31<x>`. Tests: `backend/tests/test_rules_wave31<x>_<area>.py`. Code blocks `# -- <area> (wave 31X) --`.
- Prefer families where ONE reusable grammar/engine piece unlocks many sole-line cards. Measure, don't guess: before coding, group your
  candidate lines by the exact reason they fail (`scripts.define` / the parser's refusal) and pick the top reusable reasons.
- Each track is independent; avoid editing the same functions as other tracks where you can (A: if-you-do binding; B: per-player
  choices; C: permanent copy grammar; D: spell copy grammar + end-of-combat delayed triggers). Shared files (scripts.py, language.py,
  effects.py) are fine: keep your blocks small and self-contained so merges are trivial.

## Round 5 = wave 32 (lead) — supersedes Round 4
- Start: `git fetch origin claude/vibrant-hamilton-e00gs8 && git reset --hard origin/claude/vibrant-hamilton-e00gs8` (head d3587737: waves 30–31 merged, FULL 25,306, commanders 2,272).
- Base dump at that code: /tmp/claude-0/-home-user-Fyodor/1ff99252-0807-5b3d-b3c8-4051817b6125/scratchpad/w31/levels.json. Fresh gap data: .../scratchpad/w31/inventory.json.
  `python3 .../scratchpad/q31b.py "<regex>" [N]` now reads the fresh inventory.
- Branch `claude/vibrant-hamilton-e00gs8-w32<x>`; tests `backend/tests/test_rules_wave32<x>_<area>.py`; blocks `# -- <area> (wave 32X) --`.
- Same method as Round 4: group candidate lines by exact failure, take the top reusable reasons, refuse the rest.

## Round 6 = wave 33 (lead) — agents launched while wave 32 finishes
- Start: `git fetch origin claude/vibrant-hamilton-e00gs8 && git reset --hard origin/claude/vibrant-hamilton-e00gs8` (head 5abab197 or later: wave 32C/32D merged).
  Make your OWN base levels dump at your start HEAD (levels.py --out .../levels_<track>_base.json) and diff against it.
- Gap data: .../scratchpad/w31/inventory.json (slightly stale: re-check each card's level with cardq.py).
- Branch `claude/vibrant-hamilton-e00gs8-w33<x>`; tests `backend/tests/test_rules_wave33<x>_<area>.py`; blocks `# -- <area> (wave 33X) --`.
- Before your final push, merge `origin/claude/vibrant-hamilton-e00gs8` into your branch (other tracks land meanwhile), rerun your tests.

## Style (from wave 43 on)
Caveman ultra for all chat and reports to the lead: drop articles, filler and hedging; fragments OK; one fact once; no arrows; no invented abbreviations; keep code, names, CR numbers and error strings exact; never drop not/never/no/only. Commits, PR text, code comments and test docstrings stay normal English.
Code style: ponytail ultra. YAGNI first; reuse existing machinery before writing; deletion over addition; shortest correct diff; no new abstractions, config or scaffolding; mark a deliberate known-ceiling shortcut with a `ponytail:` comment. Never simplify away correctness, hidden-information safety, validation or the required scenario tests.
