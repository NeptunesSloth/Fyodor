"""Wave 110H session 8: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip).

* Squall, Gunblade Duelist: an attack on an opponent by a creature whose power or toughness equals the chosen number deals Squall's power to the defending player (603.4).
* Heart of Kiran: one loyalty counter from a planeswalker you control may pay the crew cost instead of tapping creatures (702.122a, 122.1); no creature is tapped.
* Darigaaz Reincarnated: dying is replaced by exile with three egg counters (614.1a, 122.1); at each of its owner's upkeeps one comes off (603.4), and with none left it returns (400.7).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110h_s5 import answer
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
from tests.wave110j_kit import ability, ch, now, to_phase

EXTRA = [
    real("Darigaaz Reincarnated", "{4}{B}{R}{G}", 7, "Legendary Creature — Dragon",
         "Flying, trample, haste\nIf Darigaaz would die, instead exile it with three egg counters on it.\nAt the beginning of your upkeep, if this card is exiled with an egg "
         "counter on it, remove an egg counter from it. Then if this card has no egg counters on it, return it to the battlefield.", ("7", "7"), "BRG"),
    real("Heart of Kiran", "{2}", 2, "Legendary Artifact \u2014 Vehicle",
         "Flying, vigilance\nCrew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)\n"
         "You may remove a loyalty counter from a planeswalker you control rather than pay Heart of Kiran's crew cost.", ("4", "4"), ""),
    real("Hill Giant", "{3}{R}", 4, "Creature \u2014 Giant", "", ("3", "3"), "R"),
    real("Squall, Gunblade Duelist", "{R}{W}{B}", 3, "Legendary Creature \u2014 Human Mercenary",
         "First strike\nAs Squall enters, choose a number.\nWhenever one or more creatures attack one of your opponents, if any of those creatures have power or toughness "
         "equal to the chosen number, Squall deals damage equal to its power to defending player.", ("3", "2"), "RWB"),
    real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B"),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_darigaaz_exiles_with_egg_counters_and_returns_on_the_third_upkeep(cards):
    """Destroyed: exiled with three egg counters (not dead); the owner's upkeeps (not the opponent's) remove one each; the third return puts it on the battlefield."""
    s = build(cards, ["Darigaaz Reincarnated", "Murder"])
    dari = put(s, "Darigaaz Reincarnated")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[dari.id])
    answer(s)
    assert now(s, dari).zone == "p1:exile" and now(s, dari).counters == {"egg": 3}
    to_phase(s, "main1", turn=3)
    assert now(s, dari).zone == "p1:exile" and now(s, dari).counters == {"egg": 2}  # (turn 2 was p2's upkeep: no tick)
    to_phase(s, "main1", turn=5)
    assert now(s, dari).zone == "p1:exile" and now(s, dari).counters == {"egg": 1}
    to_phase(s, "main1", turn=7)
    assert now(s, dari).zone == "p1:battlefield" and not now(s, dari).counters
    check(s)


def _crew_setup(cards, *, walker=True, giant=False):
    names = ["Heart of Kiran", "Test Walker Card", "Hill Giant"]
    s = build(cards, names)
    hk = put(s, "Heart of Kiran")
    pw = put(s, "Test Walker Card") if walker else None
    if pw is not None:
        act(s, "p1", type="counter", card_ids=[pw.id], kind="loyalty", delta=4)
    if giant:
        put(s, "Hill Giant")
    to_phase(s, "main1", 1)
    return s, hk, pw


def test_heart_of_kiran_crews_by_removing_a_loyalty_counter(cards):
    """No creature needed and none tapped; the walker loses exactly one counter; the Vehicle is a creature afterwards."""
    s, hk, pw = _crew_setup(cards, giant=True)
    before = s.state.cards[pw.id].counters.get("loyalty", 0)
    assert before >= 1
    act(s, "p1", type="activate_ability", card_id=hk.id, ability=ability(s, hk, "Crew"), crew=[pw.id])
    answer(s)
    assert s.state.cards[pw.id].counters.get("loyalty", 0) == before - 1
    assert "Creature" in ch(s, hk).types and not card_named(s, "Hill Giant").tapped
    check(s)


def test_heart_of_kiran_still_crews_with_creatures_and_refuses_a_mix(cards):
    from app.game.errors import ActionError

    s, hk, pw = _crew_setup(cards, giant=True)
    giant = card_named(s, "Hill Giant")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=hk.id, ability=ability(s, hk, "Crew"), crew=[pw.id, giant.id])
    act(s, "p1", type="activate_ability", card_id=hk.id, ability=ability(s, hk, "Crew"), crew=[giant.id])
    answer(s)
    assert s.state.cards[giant.id].tapped and "Creature" in ch(s, hk).types
    check(s)


def test_heart_of_kiran_needs_a_planeswalker_with_a_counter_when_no_creature_can_crew(cards):
    from app.game.errors import ActionError

    s, hk, pw = _crew_setup(cards, walker=False)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=hk.id, ability=ability(s, hk, "Crew"), crew=[hk.id])


@pytest.mark.parametrize(("chosen", "hit"), [("3", True), ("2", True), ("4", False), ("0", False)])
def test_squall_hits_when_an_attacker_has_the_chosen_power_or_toughness(cards, chosen, hit):
    """Squall (3/2) attacks alone: chosen 3 matches its power, 2 its toughness; the trigger deals its power (3) on top of the 3 combat damage."""
    from tests.test_rules_wave100f_attached import to_phase as to_step

    s = build(cards, ["Squall, Gunblade Duelist"])
    squall = to_hand(s, "Squall, Gunblade Duelist")
    mana(s, R=1, W=1, B=1)
    act(s, "p1", type="cast_spell", card_id=squall.id)
    answer(s, chosen)
    to_step(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": squall.id, "target": "p2"}])
    assert life(s, "p2") == (34 if hit else 37)
    check(s)
