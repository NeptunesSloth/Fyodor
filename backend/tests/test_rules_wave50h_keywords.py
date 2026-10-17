"""Wave 50H: keyword mechanics that blocked several cards each (CR 2026-09-25), real Oracle text (tests/fixtures/wave50h_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 702.182a Job select: "When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this Equipment to it." (Warrior's Sword); the Final
  Fantasy equip costs lead with a flavor word, 207.2d ("Machina — Equip {4}", "Chaosbringer — Equip—Pay 3 life. Activate only once each turn.").
* 613.1f: "Equipped creature gets +1/+1, has "Whenever this creature deals combat damage to a player, draw a card," and is a Rogue in addition to its other types."
  (Thief's Knife): the comma after the quote belongs to the list, not to the granted ability.
* 702.148a Cleave: an alternative cost that removes the words in square brackets from the spell's text (Path of Peril, Alchemist's Retrieval); cast any other way the
  brackets are only punctuation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, mana, pt, put, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50h_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50h", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
BEAR = card("Runeclaw Bear", set_code="w50h", number="P01", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Bear", oracle_text="", power="2", toughness="2",
            colors=["G"], color_identity=["G"])
TITAN = card("Granite Titan", set_code="w50h", number="P02", mana_cost="{4}{R}", cmc=5.0, type_line="Creature — Giant", oracle_text="", power="5", toughness="5",
             colors=["R"], color_identity=["R"])


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, BEAR, TITAN], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def level(cards, name):
    return coverage.of_card_data(cards.resolve(name)).level


def equip(s, gear, target):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[gear.id])
    ab = next(a for a in ch.abilities if "equip" in a.keywords)
    act(s, "p1", type="activate_ability", card_id=gear.id, ability=ab.index, targets=[target.id])
    settle(s)


def heroes(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Hero" and c.zone == "p1:battlefield"]


# -- Job select (702.182a) --------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Warrior's Sword", "Machinist's Arsenal", "Thief's Knife", "Dancer's Chakrams", "Dark Knight's Greatsword"])
def test_job_select_cards_are_full(cards, name):
    assert level(cards, name) == "FULL"


def test_job_select_makes_a_hero_and_attaches_the_equipment_to_it(cards):
    s = build(cards, ["Warrior's Sword"])
    sword = to_hand(s, "Warrior's Sword")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=sword.id)
    settle(s)
    (hero,) = heroes(s)
    assert s.state.cards[sword.id].attached_to == hero.id  # 702.182a: attached as part of the enters trigger
    assert pt(s, "Hero") == (4, 3)  # a 1/1 Hero, +3/+2 from the Warrior's Sword
    check(s)
    assert [c.name for c in heroes(reloaded(s))] == ["Hero"]


def test_a_flavor_word_before_the_equip_cost_is_no_rules_text(cards):
    s = build(cards, ["Machinist's Arsenal", "Runeclaw Bear"])
    arsenal = put(s, "Machinist's Arsenal")
    bear = put(s, "Runeclaw Bear")
    settle(s)
    mana(s, C=4)
    equip(s, arsenal, bear)  # "Machina — Equip {4}": 702.6a
    assert s.state.cards[arsenal.id].attached_to == bear.id
    check(s)


def test_a_flavor_word_before_a_life_payment_equip_cost_keeps_its_restriction(cards):
    s = build(cards, ["Dark Knight's Greatsword", "Runeclaw Bear", "Runeclaw Bear"])
    sword = put(s, "Dark Knight's Greatsword")
    bears = [put(s, "Runeclaw Bear") for _ in range(2)]
    life = s.state.players["p1"].life
    equip(s, sword, bears[0])  # "Chaosbringer — Equip—Pay 3 life. Activate only once each turn."
    assert s.state.cards[sword.id].attached_to == bears[0].id and s.state.players["p1"].life == life - 3
    with pytest.raises(ActionError):
        equip(s, sword, bears[1])
    assert s.state.cards[sword.id].attached_to == bears[0].id and s.state.players["p1"].life == life - 3
    check(s)


def test_thief_knife_grants_the_trigger_and_the_type(cards):
    s = build(cards, ["Thief's Knife"])
    knife = to_hand(s, "Thief's Knife")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=knife.id)
    settle(s)
    (hero,) = heroes(s)
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[hero.id])
    assert "Rogue" in ch.subtypes and pt(s, "Hero") == (2, 2)
    assert any("draw a card" in a.text for a in ch.abilities)  # granted: "Whenever this creature deals combat damage to a player, draw a card."
    check(s)


# -- Two typecycling abilities on one line (702.29e) --------------------------------------------------------------
def test_valley_rannet_is_full(cards):
    assert level(cards, "Valley Rannet") == "FULL"


def start_cycling(s):
    rannet = to_hand(s, "Valley Rannet")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=rannet.id, ability=0)  # "Mountaincycling {2}, forestcycling {2}"
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.label for o in d.options] == ["Mountaincycling {2}", "Forestcycling {2}"]  # announced first (601.2b)
    return rannet, d


def finish_cycling(s):
    d = None
    for _ in range(8):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.kind == "choose_cards"
    return d


@pytest.mark.parametrize("side,found", [("either:0", "Mountain"), ("either:1", "Forest")])
def test_the_ability_chosen_searches_for_its_own_land_type(cards, side, found):
    s = build(cards, ["Valley Rannet", "Mountain"])
    rannet, d = start_cycling(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[side])
    assert zone_of(s, "Valley Rannet") == "p1:graveyard"  # discarded as the cost is paid (702.29a)
    d = finish_cycling(s)
    assert {s.state.cards[o.id].name for o in d.options} == {found}  # only the type of the cycling ability that was activated
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert [c.name for c in s.state.cards.values() if c.zone == "p1:hand"] == [found]
    check(s)


def test_cancelling_the_choice_leaves_the_card_in_hand(cards):
    s = build(cards, ["Valley Rannet", "Mountain"])
    rannet, d = start_cycling(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    assert zone_of(s, "Valley Rannet") == "p1:hand" and s.state.players["p1"].mana == {"C": 2}
    check(s)


# -- Cleave (702.148a) ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Path of Peril", "Alchemist's Retrieval"])
def test_cleave_cards_are_full(cards, name):
    assert level(cards, name) == "FULL"


def board(s):
    return [put(s, "Runeclaw Bear", "p2"), put(s, "Granite Titan", "p2"), put(s, "Runeclaw Bear")]


def test_path_of_peril_without_cleave_destroys_only_cheap_creatures(cards):
    s = build(cards, ["Path of Peril", "Runeclaw Bear"], ["Runeclaw Bear", "Granite Titan"])
    theirs_bear, titan, mine_bear = board(s)
    to_hand(s, "Path of Peril")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Path of Peril").id)
    settle(s)
    assert zone_of(s, "Runeclaw Bear", "p2") == "p2:graveyard" and zone_of(s, "Runeclaw Bear") == "p1:graveyard"  # mana value 2 or less
    assert zone_of(s, "Granite Titan", "p2") == "p2:battlefield"  # mana value 5: "[with mana value 2 or less]" counts
    check(s)


def test_path_of_peril_cleaved_destroys_every_creature(cards):
    s = build(cards, ["Path of Peril", "Runeclaw Bear"], ["Runeclaw Bear", "Granite Titan"])
    board(s)
    path = to_hand(s, "Path of Peril")
    mana(s, W=1, B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=path.id, alt_cost=f"{path.id}:0")  # Cleave {4}{W}{B}
    settle(s)
    assert zone_of(s, "Granite Titan", "p2") == "p2:graveyard" and zone_of(s, "Runeclaw Bear", "p2") == "p2:graveyard"
    assert zone_of(s, "Runeclaw Bear") == "p1:graveyard"
    check(s)


def test_cleave_removes_the_restriction_from_a_target(cards):
    s = build(cards, ["Alchemist's Retrieval"], ["Granite Titan"])
    titan = put(s, "Granite Titan", "p2")
    ret = to_hand(s, "Alchemist's Retrieval")
    mana(s, U=2)
    with pytest.raises(ActionError):  # "[you control]": not cleaved, an opponent's permanent isn't a legal target
        act(s, "p1", type="cast_spell", card_id=ret.id, targets=[titan.id])
    act(s, "p1", type="cast_spell", card_id=ret.id, alt_cost=f"{ret.id}:0", targets=[titan.id])  # Cleave {1}{U}
    settle(s)
    assert zone_of(s, "Granite Titan", "p2") == "p2:hand"
    check(s)
