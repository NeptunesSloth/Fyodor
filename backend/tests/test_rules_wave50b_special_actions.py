"""Wave 50B: a player who can take a special action is not auto-passed past the window (CR 2026-09-25), real Oracle text (the fixtures of waves 38D, 50A and
tests/fixtures/wave50b_room_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 116.2b: turning a face-down creature face up, 116.2c: ending an effect (a Licid's), 116.2g: the companion's {3} (main phase, empty stack, once per game), 116.2m:
  unlocking a door of a Room (main phase, empty stack) are special actions. They are not lands, casts or abilities, so ``casting.can_act`` (the player's own first
  main phase with response OFF, "pass whenever possible") and ``casting.has_responses`` (a stack with something on it) did not see them: a player whose only play was
  one of them was passed over. They count now, when the cost can be paid (a Room's and the companion's only at their timing).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.rules import casting, engine
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave38d_companion import EXTRA as COMPANIONS
from tests.test_rules_wave38d_companion import LURRUS, build38
from tests.test_rules_wave50a_licids import EXTRA as LICIDS
from tests.test_rules_wave50a_licids import attach, game
from tests.wave9c_kit import build, card_named, check, mana, reloaded, to_hand

ROOMS = json.loads((Path(__file__).parent / "fixtures" / "wave50b_room_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t50s", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(ROOMS) if c["name"] not in KNOWN]
POOL = "Bottomless Pool // Locker Room"


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *COMPANIONS, *LICIDS, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def bare(s, pid="p1"):
    """Nothing in the hand to play: only a special action can be left."""
    hand = list(s.state.zones[f"{pid}:hand"])
    if hand:
        act(s, pid, type="move", card_ids=hand, to={"zone": "graveyard"})


def stops(s, pid="p1"):
    """Would the engine stop for ``pid`` here, with response OFF (pass whenever possible), or pass for them?"""
    act(s, pid, type="set_prefs", response="off")
    return engine.is_stop(Plan(s.state, pid, s.cards, None), pid)


def test_a_face_down_creature_with_a_payable_morph_cost_is_not_passed_over(cards):
    s = build(cards, ["Gravel Slinger"])  # Morph {1}{W}
    slinger = to_hand(s, "Gravel Slinger")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=slinger.id, face_down=True)
    settle(s)
    assert s.state.cards[slinger.id].face_down
    bare(s)
    assert not stops(s) and not casting.has_responses(s.state, "p1", s.cards)  # {1}{W} isn't there
    mana(s, W=1, C=1)
    assert stops(s) and casting.has_responses(s.state, "p1", s.cards)  # 116.2b: any time they have priority, so a response too
    assert not casting.special_action(s.state, "p2", s.cards)  # the opponent has no face-down creature of their own
    check(s)
    assert stops(reloaded(s))  # a save and a load


def test_a_licid_whose_effect_can_be_ended_is_not_passed_over(cards):
    s, licid, mine, _ = game(cards, "Calming Licid")
    attach(s, licid, mine, W=1)
    bare(s)
    assert not stops(s)
    mana(s, W=1)
    assert stops(s) and casting.has_responses(s.state, "p1", s.cards)  # 116.2c: "You may pay {W} to end this effect."
    act(s, "p1", type="end_effect", card_id=licid.id)
    assert not stops(s)  # nothing left to end
    check(s)


def test_a_room_with_a_locked_door_is_not_passed_over_in_its_controllers_main_phase(cards):
    s = build(cards, [POOL])
    room = to_hand(s, POOL)
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=room.id, face=0)  # Bottomless Pool; Locker Room ({4}{U}) stays locked
    settle(s)
    bare(s)
    assert not stops(s)
    mana(s, U=1, C=4)
    assert stops(s)  # 116.2m
    assert not casting.has_responses(s.state, "p1", s.cards)  # a sorcery-speed special action is no response
    act(s, "p1", type="unlock_door", card_id=room.id, door=2)
    assert not stops(s)  # both doors are unlocked
    check(s)


def test_the_companion_is_not_passed_over_while_its_three_mana_and_its_deck_are_there(cards):
    s = build38(cards)
    bare(s)
    assert not stops(s)
    mana(s, G=3)
    assert stops(s)  # 116.2g
    assert not casting.has_responses(s.state, "p1", s.cards)
    act(s, "p1", type="activate_ability", card_id=card_named(s, LURRUS).id, ability=0)
    bare(s)
    mana(s, G=3)
    assert not stops(s)  # once per game: it is in the hand now, and nothing is left to take
    check(s)
    s = build38(cards, spells=((1, "Solemn Simulacrum"), (9, "Forest")))  # Lurrus needs permanents of mana value 2 or less: the deck breaks the condition
    bare(s)
    mana(s, G=3)
    assert not stops(s)
