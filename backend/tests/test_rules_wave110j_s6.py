"""Wave 110J session 6: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 122.1, 115.1: Simic Guildmage moves a +1/+1 counter between two creatures that have the same controller (Bioshift-style "that player").
* 303.4, 701.3b: Simic Guildmage moves an Aura attached to a permanent to another permanent controlled by the controller of its current host;
  an Aura that can't enchant the new permanent stays where it is.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    ability,
    activate,
    card_db,
    cast_on,
    check,
    full,
    mana,
    now,
    put_new,
)

GUILD = "Simic Guildmage"


@pytest.mark.parametrize("name", [GUILD])
def test_the_cards_are_full(name):
    assert full(name)


def _guild(cards, theirs=("Grizzly Bears", "Grizzly Bears")):
    s = build(cards, [GUILD, "Grizzly Bears", "Ray of Frost", "Kudzu", "Forest"], list(theirs))
    return s, put_new(s, GUILD)


def test_guildmage_moves_a_counter_to_a_creature_with_the_same_controller(cards):
    s, g = _guild(cards)
    a, b = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Grizzly Bears", "p2")
    act(s, "p1", type="counter", card_ids=[a.id], kind="+1/+1", delta=2)
    mana(s, G=1, C=1)
    activate(s, g, "{1}{G}", targets=[a.id, b.id], target_counts=[1, 1])
    assert now(s, a).counters == {"+1/+1": 1} and now(s, b).counters == {"+1/+1": 1}
    check(s)


def test_guildmage_counter_refuses_creatures_of_two_players(cards):
    s, g = _guild(cards, theirs=("Grizzly Bears",))
    a, c = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Grizzly Bears", "p1")
    act(s, "p1", type="counter", card_ids=[a.id], kind="+1/+1", delta=1)
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=g.id, ability=ability(s, g, "{1}{G}"), targets=[a.id, c.id], target_counts=[1, 1])


def test_guildmage_moves_an_aura_to_another_permanent_of_its_hosts_controller(cards):
    s, g = _guild(cards)
    a, b = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Grizzly Bears", "p2")
    ray = cast_on(s, "Ray of Frost", a)
    assert ray.attached_to == a.id
    mana(s, U=1, C=1)
    activate(s, g, "{1}{U}", targets=[ray.id, b.id], target_counts=[1, 1])
    assert now(s, ray).attached_to == b.id
    check(s)


@pytest.mark.parametrize("pick", ["same", "mine"])
def test_guildmage_aura_refuses_the_same_host_and_another_controllers_permanent(cards, pick):
    s, g = _guild(cards)
    a = put_new(s, "Grizzly Bears", "p2")
    mine = put_new(s, "Grizzly Bears", "p1")
    ray = cast_on(s, "Ray of Frost", a)
    mana(s, U=1, C=1)
    target = a if pick == "same" else mine
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=g.id, ability=ability(s, g, "{1}{U}"), targets=[ray.id, target.id], target_counts=[1, 1])


def test_guildmage_aura_that_cant_enchant_the_new_permanent_stays_put(cards):
    s, g = _guild(cards)
    land = put_new(s, "Forest", "p1")
    bears = put_new(s, "Grizzly Bears", "p1")
    kudzu = cast_on(s, "Kudzu", land)
    assert kudzu.attached_to == land.id
    mana(s, U=1, C=1)
    activate(s, g, "{1}{U}", targets=[kudzu.id, bears.id], target_counts=[1, 1])
    assert now(s, kudzu).attached_to == land.id  # 303.4i / 701.3b: Kudzu enchants lands only
    check(s)
