"""Wave 110A: granted replicate (702.56a) - "Each Sliver spell you cast has replicate. The replicate cost is equal to its mana cost." (Hatchery Sliver, Ian Chesterton)."""

# ruff: noqa: F403, F405
from __future__ import annotations

from app.game.errors import ActionError
from tests.wave110a_kit import *

NAMES = ["Hatchery Sliver", "Ian Chesterton"]


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
