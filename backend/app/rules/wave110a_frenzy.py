"""Wave 110A: Berserker's Frenzy - "Roll two d20 and ignore the lower roll." with its two result rows (706.2 results table, 706.6 an ignored roll never happened).

* "Roll two d20 and ignore the lower roll": the roll step with ``keep_highest`` (dice.py, as the Monarch roll-off): both dice are rolled together, only the
  higher counts (a tie is one number).
* "Choose any number of creatures. They block this turn if able.": the caster chooses on resolution, from any creatures on the battlefield (608.2d, not targets),
  and those creatures must block (509.1c, the must-block requirement ``restrict`` already imposes).
* "You choose which creatures block this turn and how those creatures block." is read by ``declare_chooser110a`` (wave110a_choosers)."""

from __future__ import annotations

from typing import Any

BODY = ("Roll two d20 and ignore the lower roll. 1—14 | Choose any number of creatures. They block this turn if able. "
        "15—20 | You choose which creatures block this turn and how those creatures block.")


def build() -> tuple[list[dict[str, Any]], Any, bool]:
    from app.rules import scripts, selectors

    gates = scripts.parse_effects("Roll a d20. 1—14 | Draw a card. 15—20 | Draw two cards.")
    chooser = scripts.parse_effects("You choose which creatures block this turn and how those creatures block.")
    assert gates is not None and chooser is not None
    roll, low, _, high, _ = gates[0]
    sel = selectors.parse("creature")
    assert sel is not None
    pick = {"do": "player_chooses", "who": "you", "sel": sel.key(), "n": 250, "label": "creatures", "any": True, "upto": True, "as": "frenzy110a"}
    return [{**roll, "count": 2, "keep_highest": True}, {**low, "skip": 2}, pick, {"do": "restrict", "who": "ref:frenzy110a", "rules": ["must_block"]},
            {**high, "skip": 1}, *chooser[0]], None, False


BUILDERS = {BODY: build}
