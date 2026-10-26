"""Wave 110G session 17."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import activate, next_turn
from tests.test_rules_wave50j_small import EXTRA as EXTRA50J
from tests.test_rules_wave50j_small import counters, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

ADVANCING = ("When this enchantment enters, draw a card.\n"
             "You may pay {0} rather than pay the power-up cost of the first power-up ability you activate during each of your turns.")
JUDGMENT = ("Madness {X}{R} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.)\n"
            "Avacyn's Judgment deals 2 damage divided as you choose among any number of targets. If this spell's madness cost was paid, it deals X damage "
            "divided as you choose among those permanents and/or players instead.")
MACHINATIONS = ("Until end of turn, you may activate loyalty abilities of Jace planeswalkers you control on any player's turn any time you could cast an instant.\n"
                "Empower Jace 8. (Put eight loyalty counters on a Jace token you control. If you don't control one, first create a blue Jace planeswalker token with "
                "\"[\u22121]: Surveil 1\" and \"[\u22123]: Draw a card.\")")
EXTRA = [real("Jace's Machinations", "{2}{U}", 3, "Instant", MACHINATIONS, None, "U"),
         real("Advancing the Spirit", "{2}{W}", 3, "Enchantment", ADVANCING, None, "W"),
         real("Avacyn's Judgment", "{1}{R}", 2, "Sorcery", JUDGMENT, None, "R"),
         real("Discard Probe", "{B}", 1, "Sorcery", "Discard a card.", None, "B")]


@pytest.fixture
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA50J, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    for name in ("Advancing the Spirit", "Avacyn's Judgment", "Jace's Machinations"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_advancing_first_power_up_free_second_pays(cards):
    """118.9, 602.2b: {0} rather than the power-up cost of the first power-up ability activated each of your turns."""
    s = build(cards, mine=["Advancing the Spirit", "Serpent Specialist"])
    put(s, "Advancing the Spirit")
    snake = put(s, "Serpent Specialist")
    next_turn(s)
    activate(s, "p1", snake)  # no mana at all
    settle(s)
    assert counters(s, "Serpent Specialist") == {"+1/+1": 2}
    check(s)


def test_without_it_power_up_costs_mana(cards):
    s = build(cards, mine=["Serpent Specialist"])
    snake = put(s, "Serpent Specialist")
    next_turn(s)
    with pytest.raises(ActionError, match="Not enough mana"):
        activate(s, "p1", snake)


def test_second_power_up_same_turn_pays(cards):
    s = build(cards, mine=["Advancing the Spirit", "Serpent Specialist", "Hulk, Gamma Goliath"])
    put(s, "Advancing the Spirit")
    snake = put(s, "Serpent Specialist")
    hulk = put(s, "Hulk, Gamma Goliath")
    next_turn(s)
    activate(s, "p1", snake)
    settle(s)
    with pytest.raises(ActionError, match="Not enough mana"):
        activate(s, "p1", hulk)
    check(s)


def test_judgment_hard_cast_two_damage_divided(cards):
    """601.2d: 2 damage divided among two targets, 1 each."""
    from tests.test_rules_wave110h_cards import answer
    from tests.wave9c_kit import life

    s = build(cards, ["Avacyn's Judgment"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=1, C=1)
    c = to_hand(s, "Avacyn's Judgment")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2", bears.id], target_counts=[2], division=[1, 1])
    answer(s)
    assert life(s, "p2") == 39 and s.state.cards[bears.id].damage == 1
    check(s)


@pytest.mark.parametrize("x", [3, 5])
def test_judgment_madness_x_damage_divided(cards, x):
    """702.35, 107.3b: cast for its madness cost, X damage divided among players and permanents."""
    from tests.test_rules_wave110h_cards import answer, cast
    from tests.wave9c_kit import life

    s = build(cards, ["Avacyn's Judgment", "Discard Probe"], ["Grizzly Bears"])
    giant = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[giant.id], to={"player": "p2", "zone": "battlefield"})
    to_hand(s, "Avacyn's Judgment")
    mana(s, B=1)
    cast(s, "Discard Probe")
    mana(s, R=1, C=x)
    for pick in (["yes"], [f"x:{x}"]):
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2", giant.id])
    d = s.state.rules.decision
    assert d.kind == "divide"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[], amounts=[x - 1, 1])
    answer(s)
    assert life(s, "p2") == 40 - (x - 1) and s.state.cards[giant.id].damage == 1
    check(s)


def answer(s, limit=40):
    from tests.test_rules_wave110h_cards import answer as _a

    _a(s, limit=limit)


def _jace(s):
    return next(c for c in s.state.cards.values() if c.name == "Jace" and c.token is not None and c.zone.endswith(":battlefield"))


def _machinations(cards):
    s = build(cards, ["Jace's Machinations"], [])
    mana(s, U=1, C=2)
    c = to_hand(s, "Jace's Machinations")
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    return s


def test_machinations_jace_at_instant_speed(cards):
    """606.3 timing lifted until end of turn: the Jace token (8 loyalty) activates in combat."""
    from tests.test_rules_wave34b_activated import activate, stops, to_phase

    s = _machinations(cards)
    jace = _jace(s)
    assert jace.counters["loyalty"] == 8
    stops(s)
    to_phase(s, "begin_combat")
    activate(s, "p1", jace, "Surveil 1")
    answer(s)
    assert s.state.cards[jace.id].counters["loyalty"] == 7
    check(s)


def test_without_machinations_jace_is_sorcery_speed(cards):
    from tests.test_rules_wave34b_activated import activate, stops, to_phase

    s = _machinations(cards)
    jace = _jace(s)
    s.state.rules.once_per_turn.clear()  # the turn mark gone: the token is an ordinary planeswalker
    stops(s)
    to_phase(s, "begin_combat")
    with pytest.raises(ActionError, match="main phase"):
        activate(s, "p1", jace, "Surveil 1")
