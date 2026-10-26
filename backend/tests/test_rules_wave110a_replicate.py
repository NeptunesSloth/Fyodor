"""Wave 110A: granted replicate (702.56a) - "Each Sliver spell you cast has replicate. The replicate cost is equal to its mana cost." (Hatchery Sliver, Ian Chesterton)."""

# ruff: noqa: F403, F405
from __future__ import annotations

from app.game.errors import ActionError
from tests.wave110a_kit import *

NAMES = ["Hatchery Sliver", "Ian Chesterton", "Zinnia, Valley's Voice"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test(NAMES)


def _count(s, name, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield")


def _cast_kicked(s, name, times):
    c = to_hand(s, name)
    fund(s, (s.cards.resolve(name).get("mana_cost") or "") * (times + 1))
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=times)
    answer(s)


def test_hatchery_sliver_gives_slivers_replicate(cards):
    s = build(cards, ["Hatchery Sliver", "Muscle Sliver"])
    put(s, "Hatchery Sliver")
    _cast_kicked(s, "Muscle Sliver", 2)
    assert _count(s, "Muscle Sliver") == 3  # 702.56a: the spell and one copy per replicate cost paid (copies of permanent spells become tokens)
    check(s)


def test_replicate_only_for_the_chosen_kind_of_spell(cards):
    s = build(cards, ["Hatchery Sliver", "Grizzly Bears"])
    put(s, "Hatchery Sliver")
    with pytest.raises(ActionError):
        _cast_kicked(s, "Grizzly Bears", 1)


def test_ian_chesterton_gives_sagas_replicate(cards):
    s = build(cards, ["Ian Chesterton", "Welcome to Sweettooth"])
    put(s, "Ian Chesterton")
    _cast_kicked(s, "Welcome to Sweettooth", 1)
    next_turn(s)
    assert _count(s, "Welcome to Sweettooth") == 2
    check(s)


def _pt(s, c):
    from app.rules import sba
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(c)
    return sba.power(c, ch), sba.toughness(c, ch)


def test_zinnia_offspring_unpaid_makes_no_token(cards):
    s = build(cards, ["Zinnia, Valley's Voice", "Grizzly Bears"])
    put(s, "Zinnia, Valley's Voice")
    c = to_hand(s, "Grizzly Bears")
    fund(s, "{1}{G}")
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    assert len([x for x in s.state.cards.values() if x.name == "Grizzly Bears" and x.zone == "p1:battlefield"]) == 1
    check(s)


def test_zinnia_gives_creature_spells_offspring(cards):
    s = build(cards, ["Zinnia, Valley's Voice", "Grizzly Bears", "Lightning Bolt"])
    put(s, "Zinnia, Valley's Voice")  # 702.175a: "Creature spells you cast gain offspring {2} as you cast them."
    c = to_hand(s, "Grizzly Bears")
    fund(s, "{1}{G}{2}")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    answer(s)
    toks = [x for x in s.state.cards.values() if x.name == "Grizzly Bears" and x.zone == "p1:battlefield"]
    assert len(toks) == 2 and sorted(_pt(s, x) for x in toks) == [(1, 1), (2, 2)]
    check(s)


def test_zinnia_offspring_not_for_noncreature(cards):
    s = build(cards, ["Zinnia, Valley's Voice", "Lightning Bolt"])
    put(s, "Zinnia, Valley's Voice")
    c = to_hand(s, "Lightning Bolt")
    fund(s, "{R}{2}")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"], kicker=1)
