"""Wave 110D: Kitesail Larcenist, real Oracle text (tests/fixtures/wave110d_cards.json).

* 115.1, 603.3d: one "up to one other target" group per player (artifacts and creatures, never the Larcenist itself).
* 205.1a, 613.1d-f: the chosen permanents become Treasure artifacts (no longer creatures) with only the quoted mana ability; 611.2b: only for as
  long as the Larcenist remains on the battlefield.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, mana, to_hand
from tests.wave110d_kit import ability, card_db, ch, check, cost, full, now, put_new, settle, to_phase  # noqa: F401

NAME = "Kitesail Larcenist"
ABILITY = "{T}, Sacrifice this artifact: Add one mana of any color"


def _scene(cards):
    s = build(cards, [NAME, "Sol Grail", "Grizzly Bears"], ["Grizzly Bears"])
    grail = put_new(s, "Sol Grail")
    theirs = put_new(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)
    return s, grail, theirs


def _enter(s, picks):
    """Cast the Larcenist and answer every target decision with the first of ``picks`` it offers."""
    c = to_hand(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        ids = [o.id for o in d.options]
        chosen = [p for p in picks if p in ids] or []
        act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)


def test_larcenist_is_full():
    assert full(NAME)


def test_two_chosen_become_treasures_until_it_leaves(cards):
    s, grail, theirs = _scene(cards)
    mine = put_new(s, "Grizzly Bears")
    _enter(s, [mine.id, theirs.id])
    for c in (mine, theirs):
        x = ch(s, c)
        assert x.types == {"Artifact"} and x.subtypes == {"Treasure"} and [a.text.rstrip(".") for a in x.abilities] == [ABILITY]
    assert "Treasure" not in ch(s, grail).subtypes  # not chosen: untouched
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=ability(s, mine, "{T}, Sacrifice"), sources=[])  # a working mana ability
    settle(s)
    assert now(s, mine).zone == "p1:graveyard"
    lark = next(c for c in s.state.cards.values() if c.name == NAME)
    assert "Creature" in ch(s, lark).types  # "other": never itself
    act(s, "p1", type="move", card_ids=[lark.id], to={"zone": "hand"})  # 611.2b: it left the battlefield
    act(s, "p1", type="pass_priority")  # (a manual move skips the state check; priority passing runs it)
    assert "Creature" in ch(s, theirs).types and ch(s, theirs).power == "2"
    check(s)


def test_up_to_one_each_may_choose_nothing(cards):
    s, grail, theirs = _scene(cards)
    _enter(s, [])
    assert "Creature" in ch(s, theirs).types
    check(s)
