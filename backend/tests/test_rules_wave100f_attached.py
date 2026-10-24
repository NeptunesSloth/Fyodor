"""Wave 100F: attached objects and control, real Oracle text (tests/fixtures/wave100f_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load (tests/wave9c_kit.check).

* 603.7, 603.7c, 603.10d: "When you lose control of the creature, tap it." (Ray of Command, Magus of the Unseen) / "When you lose control of that
  Equipment, unattach it." (Ogre Geargrabber) — a delayed trigger on the object taken; it triggers when the "until end of turn" effect ends in
  cleanup (514.2, 514.3a), when another player gains control of it, or when it leaves the battlefield (the official rulings).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty
from tests.wave9c_kit import build, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100f_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w100f", number=f"F{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
CARDS = ["Ray of Command", "Magus of the Unseen", "Ogre Geargrabber", "Temporary Insanity"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", CARDS)
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def settle(s, limit=60):
    """Resolve everything on the stack, taking the first option of every decision."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def next_turn(s, limit=300, until=None):
    """Pass priority (no attackers, no blockers) into the next turn (or until ``until(s)`` holds)."""
    turn = s.state.turn.number
    for _ in range(limit):
        if until is not None and until(s):
            return
        if until is None and s.state.turn.number > turn and not s.state.zones.get("stack") and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached the next turn")


def to_phase(s, phase, turn=None, limit=300):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached — or passed: a step nobody gets priority in is
    gone through within one action."""
    from app.game.state import PHASES

    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if turn is not None and (s.state.turn.number, PHASES.index(s.state.turn.phase)) > (turn, PHASES.index(phase)) \
                and not s.state.zones.get("stack") and (d is None or d.kind in ("declare_attackers", "declare_blockers")):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} (at {s.state.turn.phase})")


def tapped(s, c):
    return s.state.cards[c.id].tapped


def taps(s, c):
    """The turns in which the rules engine tapped ``c`` (its "tapped" events)."""
    return [(e.turn, e.step_phase) for e in s.state.rules.events if e.kind == "tapped" and e.card == c.id and not e.manual]


# -- losing control (603.7, 603.10d) -------------------------------------------------------------------------------------------------------------------
def test_ray_of_command_taps_the_creature_as_it_goes_back_at_cleanup(cards):
    s = build(cards, ["Ray of Command"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="tap", card_ids=[bear.id], tapped=True)
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ray of Command").id, targets=[bear.id])
    settle(s)
    now = s.state.cards[bear.id]
    assert now.controller == "p1" and not now.tapped  # untapped and taken until end of turn
    assert any(t.when.get("event") == "lose_control" for t in s.state.rules.delayed)
    next_turn(s)
    back = s.state.cards[bear.id]
    assert back.controller == "p2"
    assert taps(s, bear) == [(1, "cleanup")]  # 514.2: the effect ends in Alice's cleanup, she loses control, it is tapped there (514.3a); Bob untaps it in his untap step
    assert not any(t.when.get("event") == "lose_control" for t in s.state.rules.delayed)  # 603.7b: once
    check(s)


def test_ray_of_command_triggers_when_another_player_gains_control(cards):
    """The ruling: it taps when you lose control for any reason; here Alice's own Wrong Turn gives the creature to Bob for good before cleanup."""
    s = build(cards, ["Ray of Command", "Wrong Turn"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ray of Command").id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].controller == "p1" and not tapped(s, bear)
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Wrong Turn").id, targets=["p2", bear.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[bear.id].controller == "p2" and tapped(s, bear)  # Alice lost control: the delayed trigger tapped it
    assert not any(t.when.get("event") == "lose_control" for t in s.state.rules.delayed)
    act(s, "p2", type="tap", card_ids=[bear.id], tapped=False)
    next_turn(s)  # Ray's effect ends in cleanup: Bob keeps it (Wrong Turn is later, 613.7), nothing triggers again
    assert s.state.cards[bear.id].controller == "p2" and not tapped(s, bear)
    check(s)


def test_the_creature_leaving_is_losing_control(cards):
    s = build(cards, ["Ray of Command"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ray of Command").id, targets=[bear.id])
    settle(s)
    act(s, "p1", type="set_damage", card_ids=[bear.id], value=9)
    act(s, "p1", type="pass_priority")  # 704.5g: it dies under Alice's control
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    assert not any(t.when.get("event") == "lose_control" for t in s.state.rules.delayed)
    settle(s)
    assert s.state.cards[bear.id].zone == "p2:graveyard" and not tapped(s, bear)  # (the new object isn't tapped: 400.7)
    check(s)


def test_magus_of_the_unseen_taps_the_artifact_it_gives_back(cards):
    """An artifact taken with haste (the ruling: whether or not it's a creature), given back at cleanup and tapped."""
    s = build(cards, ["Magus of the Unseen"], ["Sol Ring"])
    magus = put(s, "Magus of the Unseen")
    ring = put(s, "Sol Ring", "p2")
    to_phase(s, "main1", turn=3)  # (Alice's next turn: the Magus can {T})
    act(s, "p2", type="tap", card_ids=[ring.id], tapped=True)
    mana(s, U=1, C=1)
    act(s, "p1", type="activate_ability", card_id=magus.id, ability=0, targets=[ring.id])
    pass_until_stack_empty(s)
    assert s.state.cards[ring.id].controller == "p1" and not tapped(s, ring)
    next_turn(s)
    assert s.state.cards[ring.id].controller == "p2" and taps(s, ring)[-1:] == [(3, "cleanup")]
    check(s)


def test_ogre_geargrabber_takes_attaches_and_unattaches_the_equipment(cards):
    s = build(cards, ["Ogre Geargrabber"], ["Bonesplitter", "Grizzly Bears"])
    ogre = put(s, "Ogre Geargrabber")
    bear = put(s, "Grizzly Bears", "p2")
    splitter = put(s, "Bonesplitter", "p2")
    act(s, "p2", type="attach", card_ids=[splitter.id], to=bear.id)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p2"}])
    settle(s)  # (its one target: Bob's Bonesplitter)
    now = s.state.cards[splitter.id]
    assert now.controller == "p1" and now.attached_to == ogre.id  # 701.3a: moved from Bob's Bear onto the Ogre
    next_turn(s)
    back = s.state.cards[splitter.id]
    assert back.controller == "p2" and back.attached_to is None and back.zone == "p2:battlefield"  # 701.3d: unattached as Alice lost control
    check(s)


# -- "target creature with power less than the number of cards in your graveyard" (Temporary Insanity; 115.1, 608.2b) ----------------------------------------
def test_temporary_insanity_needs_more_cards_in_the_graveyard_than_the_power(cards):
    s = build(cards, ["Temporary Insanity", "Grizzly Bears", "Llanowar Elves"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")  # power 3
    spell = to_hand(s, "Temporary Insanity")
    for name in ("Grizzly Bears", "Llanowar Elves"):
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == name and c.owner == "p1")], to={"zone": "graveyard"})
    mana(s, R=1, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[giant.id])  # 2 cards: power 3 isn't less than 2
    forest = next(c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest], to={"zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")],
        to={"zone": "graveyard"})
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[giant.id])  # 4 cards now
    settle(s)
    assert s.state.cards[giant.id].controller == "p1"
    check(s)
