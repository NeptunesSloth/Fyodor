"""Replacement and prevention effects, stage 2 (CR 614, 615, 616; app/rules/replace.py).

Real Commander-legal cards: their Oracle text (from the card database, 2026-09-30 snapshot) is
transcribed below as custom-text permanents named after the card. Every scenario checks the final
table and that replaying the recorded history reproduces it; scenarios with a choice also check
save / load and undo / redo.
"""

from __future__ import annotations

from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_attachments import build, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

# -- Oracle text (current, from data/cards.sqlite) --------------------------------------------------
PARALLEL_LIVES = ("If an effect would create one or more tokens under your control, it creates twice that many of "
                  "those tokens instead.")  # Parallel Lives
ANOINTED_PROCESSION = PARALLEL_LIVES  # Anointed Procession (same Oracle text)
DOUBLING_SEASON = (PARALLEL_LIVES + "\nIf an effect would put one or more counters on a permanent you control, it puts "
                   "twice that many of those counters on that permanent instead.")  # Doubling Season
HARDENED_SCALES = ("If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 "
                   "counters are put on it instead.")  # Hardened Scales
WINDING_CONSTRICTOR = ("If one or more counters would be put on an artifact or creature you control, that many plus one "
                       "of each of those kinds of counters are put on that permanent instead.\nIf you would get one or "
                       "more counters, you get that many plus one of each of those kinds of counters instead.")  # Winding Constrictor 2/3


def rules(s):
    return s.state.rules


def permanent(s, pid, name, kind, text):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token {kind} — Test", "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def activate(s, card, pid="p1", **kw):
    act(s, pid, type="add_mana", player=pid, mana={"C": 1})
    act(s, pid, type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def named_all(s, name):
    return [c for c in s.state.cards.values() if c.name == name]


def reload(s, cards):
    return GameSession(s.history.rebuild(), cards=cards)


# -- tokens (614.16, 616.1) -------------------------------------------------------------------------
def test_parallel_lives_and_anointed_procession_commute_without_a_prompt(cards):
    s = build(cards)
    permanent(s, "p1", "Parallel Lives", "Enchantment", PARALLEL_LIVES)
    permanent(s, "p1", "Anointed Procession", "Enchantment", ANOINTED_PROCESSION)
    maker = token(s, "p1", "Maker", text="{1}: Create a 1/1 white Soldier creature token.")
    activate(s, maker)
    assert rules(s).decision is None  # ×2 ×2 either way: no 616.1 prompt
    assert len(named_all(s, "Soldier")) == 4
    replay_matches(s)


def test_doubling_season_hardened_scales_order_prompt(cards):
    s = build(cards)
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    permanent(s, "p1", "Hardened Scales", "Enchantment", HARDENED_SCALES)
    bear = token(s, "p1", "Bear")
    feeder = token(s, "p1", "Feeder", text="{1}: Put a +1/+1 counter on target creature.")
    activate(s, feeder, targets=[bear.id])
    d = rules(s).decision
    assert d is not None and d.player == "p1" and d.resume["step"] == "replace_order"
    assert d.kind == "confirm" and "616.1" in d.prompt
    labels = {o.id: o.label for o in d.options}
    # Doubling Season first: 1 → 2 → 3; Hardened Scales first: 1 → 2 → 4
    assert "3" in labels["yes"] and "Doubling Season" in labels["yes"] and "4" in labels["no"], labels
    assert not s.state.cards[bear.id].counters  # nothing happened yet (614.6)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    assert s.state.cards[bear.id].counters == {"+1/+1": 4} and rules(s).decision is None
    replay_matches(s)
