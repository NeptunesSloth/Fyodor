"""Static P/T and keyword grants from permanents (anthems and lords, layers 6 and 7c)."""

from __future__ import annotations

from app.rules.plan import Plan
from tests.game_helpers import act, turn_on
from tests.test_rules_combat import creature, table


def ch(s, cards, card):
    return Plan(s.state, "p1", cards, None).ch(s.state.cards[card.id])


def goblin(s, pid, name, pt="1/1", text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Goblin",
                                                        "power": p, "toughness": t, "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def test_lord_pumps_other_goblins_you_control(cards):
    s = table(cards)
    lord = goblin(s, "p1", "Lord", "2/2", "Other Goblins you control get +1/+1 and have haste.")
    mine = goblin(s, "p1", "Grunt")
    theirs = goblin(s, "p2", "Raider")
    elf = creature(s, "p1", "Elfy", "1/1")
    turn_on(s)
    assert ch(s, cards, mine).pt == (2, 2) and "haste" in ch(s, cards, mine).keywords
    assert ch(s, cards, lord).pt == (2, 2) and "haste" not in ch(s, cards, lord).keywords  # "Other"
    assert ch(s, cards, theirs).pt == (1, 1)
    assert ch(s, cards, elf).pt == (1, 1)
    act(s, "p1", type="move", card_ids=[lord.id], to={"zone": "graveyard"})
    assert ch(s, cards, mine).pt == (1, 1)


def test_anthem_and_opponents_minus_kills_by_sba(cards):
    s = table(cards)
    creature(s, "p1", "Banner", "0/4", "Creatures you control get +1/+1.\nCreatures your opponents control get -1/-1.")
    bear = creature(s, "p1", "Bear", "2/2")
    weak = creature(s, "p2", "Weakling", "1/1")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # state-based actions run
    assert ch(s, cards, bear).pt == (3, 3)
    assert weak.id not in s.state.cards or not s.state.cards[weak.id].zone.endswith(":battlefield")


def test_sliver_style_all_creatures_of_a_type(cards):
    s = table(cards)
    act(s, "p1", type="create_token", player="p1", token={"name": "Wing", "type_line": "Token Creature — Sliver",
                                                         "power": "1", "toughness": "1", "text": "All Slivers have flying."})
    act(s, "p2", type="create_token", player="p2", token={"name": "Other", "type_line": "Token Creature — Sliver",
                                                         "power": "1", "toughness": "1"})
    turn_on(s)
    other = next(c for c in s.state.cards.values() if c.name == "Other")
    assert "flying" in ch(s, cards, other).keywords  # "All Slivers": everyone's


def test_rules_view_shows_derived_stats(cards):
    from app.rules.view import rules_view

    s = table(cards)
    lord = goblin(s, "p1", "Lord", "2/2", "Other Goblins you control get +1/+1 and have haste.")
    mine = goblin(s, "p1", "Grunt")
    turn_on(s)
    st = rules_view(s.state, "p2", cards)["stats"]
    assert st[mine.id] == {"pt": [2, 2], "base": ["1", "1"], "gained": ["haste"]} and lord.id not in st
