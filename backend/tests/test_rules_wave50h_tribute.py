"""Wave 50H: tribute N (CR 702.104, 2026-09-25), real Oracle text (tests/fixtures/wave50h_cards.json, from data/cards.sqlite). Every scenario checks the replay and a
save and a load.

* 702.104a: "As this creature enters, choose an opponent. That player may put an additional N +1/+1 counters on it as it enters." The controller chooses the opponent
  only when there is more than one; the chosen opponent decides, as a question of their own, before the creature enters (it enters with the counters).
* 702.104b: "if tribute wasn't paid" is true unless that opponent had the creature enter with the counters (Snake of the Golden Grove, Fanatic of Xenagos).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import until_asked
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, life, mana, pt, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50h_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50h", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build3(cards, *mine):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (9, "Forest")]), deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def cast_snake(s):
    snake = to_hand(s, "Snake of the Golden Grove")
    mana(s, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=snake.id)
    return snake


def keywords(s, name):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name).id]).keywords


@pytest.mark.parametrize("name", ["Snake of the Golden Grove", "Fanatic of Xenagos"])
def test_tribute_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_opponent_is_asked_and_declining_leaves_the_trigger(cards):
    s = build(cards, ["Snake of the Golden Grove"])
    mine = life(s)
    cast_snake(s)
    d = until_asked(s)
    assert d.player == "p2" and "tribute" in d.prompt and [o.id for o in d.options] == ["pay", "no"]  # the chosen opponent decides, not the controller
    assert zone_of(s, "Snake of the Golden Grove") != "p1:battlefield"  # 702.104a: before it enters
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["no"])
    settle(s)
    assert pt(s, "Snake of the Golden Grove") == (4, 4) and life(s) == mine + 4  # "if tribute wasn't paid, you gain 4 life"
    check(s)


def test_paying_tribute_puts_the_counters_on_it_as_it_enters_and_no_trigger(cards):
    s = build(cards, ["Snake of the Golden Grove"])
    mine = life(s)
    cast_snake(s)
    d = until_asked(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert pt(s, "Snake of the Golden Grove") == (7, 7) and life(s) == mine  # three +1/+1 counters; 702.104b: tribute was paid
    check(s)
    assert pt(reloaded(s), "Snake of the Golden Grove") == (7, 7)


def test_unpaid_tribute_trigger_gives_haste_and_a_bonus_until_end_of_turn(cards):
    s = build(cards, ["Fanatic of Xenagos"])
    fan = to_hand(s, "Fanatic of Xenagos")
    mana(s, R=1, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=fan.id)
    d = until_asked(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["no"])
    settle(s)
    assert "haste" in keywords(s, "Fanatic of Xenagos") and pt(s, "Fanatic of Xenagos") == (4, 4)
    check(s)


def test_with_several_opponents_the_controller_chooses_who_decides(cards):
    s = build3(cards, "Snake of the Golden Grove")
    mine = life(s)
    cast_snake(s)
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"} and "choose an opponent" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p3" and [o.id for o in d.options] == ["pay", "no"]  # Carol, not Bob, decides
    act(s, "p3", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert pt(s, "Snake of the Golden Grove") == (7, 7) and life(s) == mine
    check(s)


def test_a_single_opponent_is_not_asked_to_be_chosen(cards):
    s = build(cards, ["Snake of the Golden Grove"])
    cast_snake(s)
    d = until_asked(s)
    assert "choose an opponent" not in d.prompt  # 2 players: the only opponent is the chosen one


def test_a_creature_put_onto_the_battlefield_by_an_effect_asks_the_opponent_again(cards):
    s = build(cards, ["Snake of the Golden Grove", "Cloudshift"])
    mine = life(s)
    cast_snake(s)
    act(s, "p2", type="choose", decision_id=until_asked(s).id, option_ids=["no"])
    settle(s)
    assert life(s) == mine + 4
    shift = to_hand(s, "Cloudshift")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=shift.id, targets=[card_named(s, "Snake of the Golden Grove").id])
    d = until_asked(s)
    assert d.player == "p2" and "tribute" in d.prompt  # a new object (400.7): tribute again, decided by the opponent
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert pt(s, "Snake of the Golden Grove") == (7, 7) and life(s) == mine + 4  # paid this time: no second trigger
    check(s)
