---
name: fyodor-game-development
description: How to change Fyodor's rules engine, game server and card automation correctly. Use before implementing or changing engine behavior, card support (FULL/PARTIAL coverage), game state, actions, saves, LAN/privacy, or when running a rules "wave" with agents. Pairs with mtg-rules-research for every rules question.
---

# Fyodor game development

## Non-negotiable policies

- **Commander only.** Coverage counts Commander-legal cards only.
- **Comprehensive Rules are authoritative** (stored under `data/rules/`). Never answer rules from memory: use
  **`mtg-rules-research`**, cite rule numbers in code comments.
- **No runtime LLM judge; card text is never executed.** Scripts are declarative data.
- **Wrong automation is worse than manual: refuse rather than guess.** A card is FULL only with complete,
  tested behavior on real Oracle text. Unknown wordings must keep parsing to "unsupported". Unsettled rulings
  ⇒ refuse until a ruling or a close official analogy settles it (e.g. Panharmonicon vs "create a token" was refused
  until wave 43A read it from Ancient Greenwarden's "play a land" ruling: see `trigger_multipliers.py`).
- **Server is authoritative; hidden information never leaks** (views, hints, logs, prompts — including leaks by
  omission such as skipping a question only when the hidden answer is "nothing").
- Every new behavior: scenario test with real Oracle text + `replay_matches` + save/load round trip; new state
  fields need defaults so old saves load.

## Where things are (`backend/app/rules/`)

`scripts.py` (templates, `define`, `_parse_effects`), `language.py` (sentence grammar), `effects.py`
(primitives, `PRIMITIVES`/`RESUME`), `hooks.py` (the hooked modules of each step, in order), `conditions.py`, `values.py` (amounts), `selectors.py`, `events.py` +
`triggers.py`, `statics.py` + `layers.py` (613 layers), `replace.py`/`replacements.py` (614–616),
`casting.py`/`costs.py`/`cost_payment.py`/`cost_changes.py`/`alt_costs.py`, `combat.py`, `history.py` (turn
log), `copying.py`, `coverage.py` (FULL/PARTIAL), `rules_state.py` in `app/game/`. Many wave modules
(`this_way.py`, `unless_pays.py`, `chosen.py`, `x_spells.py`, `trigger_multipliers.py`, …) — grep before
writing; reuse existing machinery, don't build parallel systems.

## Setup and checks

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' 'mypy==2.3.1' pytest-xdist
scripts/update-cards.sh --images none          # from repo root: card DB for coverage
.venv/bin/ruff check . && .venv/bin/mypy app tools && .venv/bin/python -m pytest -n 8 -q   # before every push
cd ../frontend && npm ci && npm run typecheck && npm test                                  # if frontend changed
```

`test_rules_statics.py::test_full_board_derive_is_fast` (500 ms) can fail under heavy machine load; rerun it
alone before calling it a regression.

## Finding work

`python -m tools.gap_rank --db ../data/cards.sqlite` ranks unsupported lines by family (sole-blocker counts);
`--family <f> --limit 300` lists cards; `--ngrams <f>` shows shared phrases in catch-all families. Work the
biggest reusable families; never chase single cards. Measure FULL before/after with
`python -m tools.commander_coverage --db ../data/cards.sqlite --out <dir>`.

## Agent waves (what worked)

- One agent per family in its own git worktree; a shared brief file; code changes in small marked blocks
  `# -- <area> (wave NX) --`; tests in `tests/test_rules_waveNx_<area>.py`.
- Worktree agents run with `PYTHONPATH=$PWD` (the venv is an editable install of the main checkout).
- Lead merges each branch as it lands (ruff, mypy, full pytest before every push), keeps both sides on
  registration conflicts, notes risky points for the wave's independent reviewer, which fixes what it finds.
- On usage limits: commit each worktree's work as WIP, push `claude/wip-*`, resume with `SendMessage`.
- Engineering skills: `systematic-debugging` for failures, `test-driven-development` for new behavior,
  `verification-before-completion` before claiming done.
- `docs/CURRENT_STATE.md` is the handoff; update it only at the end of a batch.
