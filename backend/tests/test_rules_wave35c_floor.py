"""Wave 35C: the life floor (CR 120.3a, 614.1a, 611.2a, 114.4, 616.1), real Oracle text (tests/fixtures/wave35c_cards.json). Every scenario checks the replay
and a save and a load.

* "Damage that would reduce your life total to less than 1 reduces it to 1 instead." (Fortune Thief, Ali from Cairo, Sustaining Spirit; with "If you control a
  creature": Worship, Serra the Benevolent's emblem; "Until end of turn": Angel's Grace, Angel of Grace). The Gatherer rulings: the damage dealt stays what it was,
  only the life it makes the player lose changes; "lose life" and paying life bypass it; nothing applies to a player already below 1 life.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, until
from tests.wave9c_kit import build, check, life, mana, put, reloaded, to_hand
from tests.wave35c_kit import alive, bolt, cards, cast_from_hand  # noqa: F401

FULL = ["Worship", "Fortune Thief", "Angel's Grace", "Serra the Benevolent", "Angel of Grace"]


@pytest.mark.parametrize("name", FULL)
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_fortune_thief_leaves_one_life_but_the_damage_is_still_dealt(cards):
    """120.3a: a Bolt for 3 at 3 life makes Alice lose 2 (she keeps 1); she was dealt damage all the same."""
    s = build(cards, ["Fortune Thief", "Lightning Bolt", "Lightning Bolt"], [])
    put(s, "Fortune Thief")
    act(s, "p1", type="set_life", value=3)
    bolt(s, "p1")
    assert life(s) == 1 and alive(s) and s.state.rules.damaged["p1"] == s.state.turn.number
    s = reloaded(s)
    bolt(s, "p1")  # at 1 life the whole 3 would take her below 1: still 1
    assert life(s) == 1 and alive(s)
    check(s)


def test_the_floor_is_only_for_damage(cards):
    """Losing life is not damage (the rulings): Sign in Blood takes Alice from 2 to 0 and she loses the game; Fortune Thief does nothing for it."""
    s = build(cards, ["Fortune Thief", "Sign in Blood"], [])
    put(s, "Fortune Thief")
    act(s, "p1", type="set_life", value=2)
    mana(s, "p1", B=2)
    cast_from_hand(s, "Sign in Blood", targets=["p1"])
    assert life(s) == 0 and not alive(s)
    check(s)


def test_damage_that_does_not_reach_zero_is_dealt_in_full(cards):
    """No replacement: a Bolt for 3 at 4 life is 1 life, as usual (the effect applies only to damage that would take her below 1)."""
    s = build(cards, ["Fortune Thief", "Lightning Bolt"], [])
    put(s, "Fortune Thief")
    act(s, "p1", type="set_life", value=4)
    bolt(s, "p1")
    assert life(s) == 1
    check(s)


def test_worship_needs_a_creature_when_the_damage_would_be_dealt(cards):
    """614.1a: "If you control a creature" is judged as the damage would be dealt: Alice with a Grizzly Bears keeps 1 life; without one she is dead."""
    s = build(cards, ["Worship", "Grizzly Bears", "Lightning Bolt", "Lightning Bolt"], [])
    put(s, "Worship")
    act(s, "p1", type="set_life", value=2)
    bears = put(s, "Grizzly Bears")
    bolt(s, "p1")
    assert life(s) == 1 and alive(s)
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    bolt(s, "p1")
    assert life(s) <= 0 and not alive(s)
    check(s)


def test_angels_grace_lasts_the_turn_and_is_gone_the_next(cards):
    """611.2a: "Until end of turn, damage that would reduce your life total to less than 1 reduces it to 1 instead." (and "You can't lose the game this turn")."""
    s = build(cards, ["Angel's Grace", "Lightning Bolt", "Lightning Bolt"], [])
    act(s, "p1", type="set_life", value=2)
    mana(s, "p1", W=2)
    cast_from_hand(s, "Angel's Grace")
    bolt(s, "p1")
    assert life(s) == 1 and alive(s)
    assert any(r.get("kind") == "replace" for r in s.state.rules.replacements)  # the record waits for the turn to end
    s = reloaded(s)
    bolt(s, "p1")
    assert life(s) == 1 and alive(s)
    check(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert not any(r.get("kind") == "replace" and r.get("turn") == s.state.turn.number for r in s.state.rules.replacements)  # (611.2a: a record is for its turn)


def test_angel_of_grace_covers_the_turn_it_enters(cards):
    s = build(cards, ["Angel of Grace", "Lightning Bolt"], [])
    act(s, "p1", type="set_life", value=3)
    mana(s, "p1", W=5)
    cast_from_hand(s, "Angel of Grace")
    bolt(s, "p1")
    assert life(s) == 1 and alive(s)
    check(s)


def test_serras_emblem_floors_life_while_you_control_a_creature(cards):
    """114.4: the emblem's replacement works from the command zone; "If you control a creature" is judged as the damage would be dealt."""
    s = build(cards, ["Serra the Benevolent", "Grizzly Bears", "Lightning Bolt", "Lightning Bolt"], [])
    serra = put(s, "Serra the Benevolent")
    act(s, "p1", type="counter", card_ids=[serra.id], kind="loyalty", delta=6)  # (moved by hand, it has none: 6 for the -6 ability)
    s.state.rules.controlled_since[serra.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=serra.id, ability=2)
    settle(s)
    assert any(c.token is not None and c.token.type_line == "Emblem" for c in s.state.cards.values() if c.owner == "p1")
    act(s, "p1", type="set_life", value=3)
    bears = put(s, "Grizzly Bears")
    bolt(s, "p1")
    assert life(s) == 1 and alive(s)
    s = reloaded(s)
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    bolt(s, "p1")
    assert life(s) <= 0 and not alive(s)
    check(s)
