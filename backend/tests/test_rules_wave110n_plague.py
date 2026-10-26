"""Wave 110N: Necrotic Plague (603.10a it looks back; the dead creature's controller chooses among the creatures their opponents control, 303.4f)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

PLAGUE = "Necrotic Plague"
EXTRA = [real(PLAGUE, "{2}{B}", 3, "Enchantment — Aura",
              "Enchant creature\nEnchanted creature has \"At the beginning of your upkeep, sacrifice this creature.\"\nWhen enchanted creature dies, its controller chooses target creature one of "
              "their opponents controls. Return this card from its owner's graveyard to the battlefield attached to that creature.", None, "B")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([PLAGUE])


def test_the_dead_creatures_controller_picks_one_of_their_opponents_creatures(cards):
    s = build(cards, [PLAGUE, "Murder", "Llanowar Elves"], ["Grizzly Bears", "Grizzly Bears"])
    plague = put(s, PLAGUE)
    victim = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"]
    bears, other = victim[0], victim[1]
    for c in (bears, other):
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    elves = put(s, "Llanowar Elves")
    act(s, "p1", type="attach", card_ids=[plague.id], to=bears.id)
    mana(s, "p1", B=3)
    cast(s, "Murder", [bears.id], pay=False)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d.player == "p2" and {o.card_id for o in d.options} == {elves.id}  # Bob picks among Alice's creatures only, not his other Bears
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[elves.id])
    answer(s)
    c = s.state.cards[plague.id]
    assert c.zone == "p1:battlefield" and c.attached_to == elves.id
    check(s)
