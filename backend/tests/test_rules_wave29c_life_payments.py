"""Wave 29C: a player may pay all the life they have (CR 119.4: "only if their life total is greater than or equal to the amount of the payment"; the
player then loses the game at the next check, 704.5a). The Phyrexian auto-payer refused to pay 2 life at exactly 2 life (``life_cost >= life``).

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import mana as M
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, life, mana, to_hand

EXTRA = [
    real("Gut Shot", "{R/P}", 1, "Instant", "({R/P} can be paid with either {R} or 2 life.)\nGut Shot deals 1 damage to any target.", None, "R"),
    real("Dismember", "{1}{B/P}{B/P}", 3, "Instant", "({B/P} can be paid with either {B} or 2 life.)\nTarget creature gets -5/-5 until end of turn.", None, "B"),
    real("Toxic Deluge", "{2}{B}", 3, "Sorcery", "As an additional cost to cast this spell, pay X life.\nAll creatures get -X/-X until end of turn.", None, "B"),
    real("K'rrik, Son of Yawgmoth", "{4}{B}{B}", 6, "Legendary Creature — Phyrexian Vampire Noble",
         "Lifelink\nFor each {B} in a cost, you may pay 2 life rather than pay that mana.\nWhenever you cast a black spell, put a +1/+1 counter on K'rrik.", ("3", "3"), "B"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_the_solver_pays_exactly_the_life_it_has():
    mountain = M.Source("m", (("R",),))
    assert M.solve(M.parse_cost("{G/P}"), {}, [mountain], life=2).life == 2  # 119.4: life 2 >= payment 2
    with pytest.raises(M.ManaError):
        M.solve(M.parse_cost("{G/P}"), {}, [mountain], life=1)
    cost = M.parse_cost("{W/P}{U/P}")
    assert M.solve(cost, {}, [], life=4).life == 4  # (both symbols by life: all of it)
    assert M.solve(cost, {"W": 1}, [], life=2).life == 2
    with pytest.raises(M.ManaError):
        M.solve(cost, {}, [], life=3)  # (4 life for two symbols, 3 isn't enough)
    with pytest.raises(M.ManaError):
        M.solve(M.parse_cost("{G/P}"), {}, [], life=0)  # (119.4: only 0 life can be paid with 0 life)


@pytest.mark.parametrize("manual", [False, True])
def test_gut_shot_is_paid_with_the_last_two_life(cards, manual):
    s = build(cards, ["Gut Shot"])
    shot = to_hand(s, "Gut Shot")
    act(s, "p1", type="set_life", player="p1", value=2)
    extra = {"sources": []} if manual else {}  # (MANUAL PAY with no sources: the pool and life)
    act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"], **extra)
    assert life(s, "p1") == 0  # 119.4: paid in full; 704.5a: they lose at the next check
    assert s.state.rules.lost.get("p1") is not None or s.state.players["p1"].life <= 0
    check(s)


def test_gut_shot_is_not_castable_at_one_life(cards):
    s = build(cards, ["Gut Shot"])
    shot = to_hand(s, "Gut Shot")
    act(s, "p1", type="set_life", player="p1", value=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=shot.id, targets=["p2"])
    assert life(s, "p1") == 1
    check(s)


def test_dismember_pays_life_for_one_symbol_and_mana_for_the_other(cards):
    s = build(cards, ["Dismember"])
    spell = to_hand(s, "Dismember")
    from tests.test_rules_conditionals import creature

    victim = creature(s, "p2", "Bob Bear")
    act(s, "p1", type="set_life", player="p1", value=2)
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    assert life(s, "p1") == 0 and s.state.players["p1"].mana == {}
    check(s)


def test_life_paid_by_phyrexian_mana_and_by_an_additional_cost_adds_up(cards):
    # 119.4 is checked for each payment in turn, so together they can't be more than the life total: Toxic Deluge's "pay X life" and
    # K'rrik's 2 life for its {B}. 4 life: X = 3 and the {B} by life is 5 in all; the cast is refused, not carried out into -1 life.
    s = build(cards, ["Toxic Deluge", "K'rrik, Son of Yawgmoth"])
    from tests.wave9c_kit import put

    put(s, "K'rrik, Son of Yawgmoth")
    deluge = to_hand(s, "Toxic Deluge")
    act(s, "p1", type="set_life", player="p1", value=4)
    mana(s, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=deluge.id, x_value=3)
    assert life(s, "p1") == 4 and s.state.players["p1"].mana == {"C": 2}
    act(s, "p1", type="cast_spell", card_id=deluge.id, x_value=2)  # 2 + 2 = 4 life: all of it
    assert life(s, "p1") == 0
    check(s)
