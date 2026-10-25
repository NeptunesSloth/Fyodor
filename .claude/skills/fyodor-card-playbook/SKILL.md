---
name: fyodor-card-playbook
description: Compact, token-lean recipe for promoting PARTIAL Commander cards to FULL in Fyodor (find the gap, hook an exact wording, test it, commit). Use for any card-automation batch or agent wave, after fyodor-game-development.
---

# Fyodor card playbook

Policies live in `fyodor-game-development` (refuse rather than guess, real Oracle text, cite CR rule numbers, no hidden-info leaks).
This file is the how-to. Cost is context size × turns: keep both small.

## Loop (one session ≈ 10 cards)

1. `card.py --next <bucket.json> 15` (or `tools.gap_rank --family <f>`) and pick cards that share one wording.
2. `card.py "Name"` prints the Oracle text and missing lines. Copy the Oracle text exactly.
3. Find who reads the nearest wording: `grep -n "<distinctive phrase>" app/rules/*.py | head -20`, then `sed -n A,Bp` ≤60 lines.
4. Implement, write the test, then run ruff, pytest and `card.py` in one chained command. Commit. Next group.
5. After about 10 promotions, commit and write a 10-line handoff (done / next / gotchas), then stop.

## Where wordings are read

- Spell or effect bodies: `scripts.parse_effects` (scripts.py ~2662) tries the wave modules in turn (`multi100n.parse`, `zones100g`,
  `otherchooser100p`, …), then `_parse_effects` and the grammar in `language.py`.
- Whole abilities (triggers, statics, activated): `scripts.define` (~5887) tries `<module>.definition(ability, ch)` hooks (~5970).
- Conditions: `conditions.parse`. Amounts: `values.py`. Object sets: `selectors.py`. Events: `events.py`/`triggers.py`.
  Statics: `statics.py`/`layers.py`. Replacements: `replace.py`/`replacements.py`. Costs: `costs.py`/`cost_payment.py`/`alt_costs.py`.
- Grep the wave modules before writing anything: `multi100n`, `this_way`, `unless_pays`, `instead100k`, `ifyoudo100b`,
  `aslongas100k`, `turnstate100h`, `counters100j`, `zones100g`, `xdamage100e`, `attached100f`, `retarget100o`.

## Cheapest hook: rewrite an exact wording (pattern: `multi100n.py`)

- Map the whole exact Oracle sentence to effects built from `scripts.parse_effects(<native wording>)` (deep-copied), or to
  `scripts.define(replace(ability, text=<native wording>), ch)` for a whole ability. Exact match only: never a loose regex.
- Hook in your own module: one marked line block in `parse_effects` / `define`: `# -- <area> (wave NX) --`.
- Need a new primitive? Write `def prim(plan, ctx, e) -> bool` in your module, export `PRIMITIVES = {"name_nx": prim}` (plus `RESUME`
  for decisions), and register it at the **end** of `effects.py`: `from app.rules import mod as _mod  # noqa: E402` then
  `PRIMITIVES.update(_mod.PRIMITIVES)`. Name keys with a wave suffix. A missing registration means a KeyError at resolution.

## Test recipe (copy `tests/test_rules_wave100n_multi.py`)

```python
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
# copy answer(), cast(s, name, targets), to_graveyard(), gy() and the card_db fixture from test_rules_wave100n_multi.py:103-140
EXTRA = [real("Name", "{1}{R}", 2, "Instant", "<exact Oracle text>", None, "R")]   # pt=("3","2") for creatures
NAMES = [c["name"] for c in EXTRA]
@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name): assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
def test_behavior(cards):
    s = build(cards, ["Name"]); mana(s, R=1, C=1); cast(s, "Name", ["p2"]); answer(s)   # answer(): resolve all decisions
    assert life(s, "p2") == 37; check(s)            # check() = replay_matches + save/load round trip
```

Test the behavior on both sides of any condition (parametrize), plus the refusal edge when it matters.

## Never

- Widen a regex so that untested wordings start to parse. Edit `coverage.py` to pass a card. Hide text as reminder text.
- Read whole big modules (scripts.py is 12k lines, effects.py 7k) or cat bucket, cov or docs/research files. Use grep -n plus a range.
- Run the full suite in an agent (the lead does it). Use `pytest -q -x --tb=line -p no:cacheprovider <file> 2>&1 | tail -15`.
- Re-research a refused card. Write one line in `docs/research/wave<N>-refused.md` and move on.
