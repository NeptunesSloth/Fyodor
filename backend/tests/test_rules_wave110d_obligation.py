"""Wave 110D: Immortal Obligation, real Oracle text (tests/fixtures/wave110d_cards.json), three players.

* 400.7, 110.2: an opponent's creature card returns under its owner's control with a duty counter.
* 611.2b, 701.15b, 506.3, 509.1: for as long as it has a duty counter it is goaded (by the caster), can't attack the caster or the caster's permanents and can't
  block the caster's creatures; the counter removed, all three end.
"""

from __future__ import annotations

from app.rules import scripts
from tests.game_helpers import act
from tests.test_rules_wave110d_three import three
from tests.wave9c_kit import to_hand
from tests.wave110d_kit import card_db, ch, check, cost, full, grave_new, mana, now, settle  # noqa: F401

NAME = "Immortal Obligation"


def test_full():
    assert full(NAME)


def test_duty_counter_binds_the_returned_creature(cards):
    s = three(cards, [NAME], ["Grizzly Bears"])
    bear = grave_new(s, "Grizzly Bears", "p2")
    c = to_hand(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bear.id])
    settle(s)
    b = now(s, bear)
    assert b.zone == "p2:battlefield" and b.controller == "p2" and b.counters.get("duty") == 1
    x = ch(s, bear)
    rules = scripts.statics(x)
    assert "goaded:p1" in x.imposed and "cant_attack_player_pw:p1" in rules and any(r.startswith("cant_block_sel:") and '"player:p1"' in r for r in rules)
    check(s)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="duty", delta=-1)
    act(s, s.state.rules.priority, type="pass_priority")
    x = ch(s, bear)
    assert "goaded:p1" not in x.imposed and "cant_attack_player_pw:p1" not in scripts.statics(x)
    check(s)
