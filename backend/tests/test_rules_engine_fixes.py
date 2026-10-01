"""Regression tests for engine simplifications replaced by the real rule (batch 3, engine items).

Every card is a real Commander-legal card; its Oracle text (the card database, 2026-09-30 snapshot)
is transcribed below and named in the comment above it. CR 2026-09-25.

- 616.1 / 614.16: token copies go through the pausable token choke point (the creator orders
  non-commuting replacements; the instruction's binding and later steps follow the answer).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_attachments import build, ch, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_replacements2 import (
    DOUBLING_SEASON,
    XORN,
    answer,
    decision,
    named_all,
    permanent,
    reload,
)
from tests.test_rules_suspend import until

# Molten Duplication (sorcery), as the activated ability of a custom permanent (the same effect text)
MOLTEN_DUPLICATION = ("{1}: Create a token that's a copy of target artifact or creature you control, except it's an "
                      "artifact in addition to its other types. It gains haste until end of turn. Sacrifice it at the "
                      "beginning of the next end step.")
TREASURE = "{T}, Sacrifice this token: Add one mana of any color."


def treasure(s, pid="p1"):
    act(s, pid, type="create_token", player=pid, token={"name": "Treasure", "type_line": "Token Artifact — Treasure",
                                                       "text": TREASURE})
    return named_all(s, "Treasure", pid)[-1]


# -- token copies: 616.1 order through the token choke point ------------------------------------------
def test_a_token_copy_asks_the_creator_to_order_xorn_and_doubling_season(cards):
    s = build(cards)
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    token(s, "p1", "Xorn", "3/2", XORN)
    gold = treasure(s)
    dup = permanent(s, "p1", "Molten Duplication", "Enchantment", MOLTEN_DUPLICATION)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=dup.id, ability=0, targets=[gold.id])
    pass_until_stack_empty(s)
    d = decision(s)
    assert d is not None and d.player == "p1" and d.resume["step"] == "replace_order"  # 616.1: the creator's choice
    assert len(named_all(s, "Treasure")) == 1  # nothing is created before the choice (614.6)
    labels = {o.id: o.label for o in d.options}
    assert "3 Treasure" in labels["yes"] and "4 Treasure" in labels["no"]
    paused = reload(s, cards)  # saved and loaded while the choice is open: it goes on the same way
    for game in (paused, s):
        answer(game, "no")  # Xorn first: 1 + 1 = 2, then doubled: 4
        pass_until_stack_empty(game)
    assert len(named_all(paused, "Treasure")) == 5
    copies = [c for c in named_all(s, "Treasure") if c.id != gold.id]
    assert len(copies) == 4 and decision(s) is None
    # the instruction went on with the answer: "It gains haste" bound the four copies, and
    # "Sacrifice it at the beginning of the next end step" waits for them
    assert all("haste" in ch(s, c).keywords for c in copies)
    assert len(s.state.rules.delayed) == 1
    replay_matches(s)
    again = reload(s, cards)
    assert len(named_all(again, "Treasure")) == 5
    until(s, lambda s: not s.state.rules.delayed, limit=60)
    pass_until_stack_empty(s)
    assert [c.id for c in named_all(s, "Treasure")] == [gold.id]  # sacrificed (and gone: 704.5d)
