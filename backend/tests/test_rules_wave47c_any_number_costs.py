"""Wave 47C: cost reductions paid with objects (CR 2026-09-25), real Oracle text (tests/fixtures/wave47c_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 601.2b: "As an additional cost to cast this spell, you may sacrifice any number of creatures." is announced with the other additional costs (the intent's
  ``optional_costs``, or the question of a free cast, 118.9d); the objects chosen are the number announced.
* 601.2f: the total cost is worked out from that choice ("This spell costs {2} less to cast for each creature sacrificed this way"): generic mana only, never
  below {0} (118.7a), then it is locked in. More objects than the reduction needs may be chosen (rulings 2021-04-16, 2022-02-18).
* 601.2h: the objects are sacrificed, exiled or tapped with the rest of the cost, all at once; cards exiled from the hand are public only then (406.3).
* 607.2q: the cards exiled to pay a permanent spell's cost are "exiled with" the permanent it becomes (Gorex).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.view import hints
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import until
from tests.test_rules_wave30h_linked_exile import settle, stack_top
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave9c_kit import reloaded as reloaded_session

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave47c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w47c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
CREW = ("Hill Giant", "Grizzly Bears", "Goblin Piker", "Gray Ogre", "Savannah Lions")


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


FULL = ["Rottenmouth Viper", "Torment of Hailfire", "Torgaar, Famine Incarnate", "Gorex, the Tombshell", "Dargo, the Shipwrecker", "Hierophant Bio-Titan", "Explosive Singularity", "March of Swirling Mist",
        "March of Otherworldly Light", "March of Wretched Sorrow", "March of Reckless Joy", "March of Burgeoning Life",
        "Extus, Oriq Overlord // Awaken the Blood Avatar"]
# (kept manual: Rottenmouth Viper's cost line is read, its blight-counter choices for every opponent are not; Scrap Welder's "mana value X" is the sacrificed artifact's, no X is announced for "less than X")
PARTIAL = ["Scrap Welder"]


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("name", PARTIAL)
def test_the_cards_whose_other_lines_are_not_read_stay_partial(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "PARTIAL", name


def cast_reduced(s, name, chosen, **kw):
    """Cast ``name`` announcing its any-number cost, paid with these cards (none: announced and paid with nothing)."""
    c = card_named(s, name)
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:reduce"], cost_choices=[{"component": 0, "cards": [x.id for x in chosen]}], **kw)
    settle(s)


def to_graveyard(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def torgaar_table(cards, n=3):
    s = build(cards, ["Torgaar, Famine Incarnate", *CREW[:n]])
    crew = [put(s, name) for name in CREW[:n]]
    to_hand(s, "Torgaar, Famine Incarnate")
    return s, crew


# ---- sacrifice: Torgaar, Famine Incarnate ------------------------------------------------------------------------------------------------------
def test_torgaar_with_nothing_sacrificed_costs_the_whole_eight(cards):
    s, crew = torgaar_table(cards)
    mana(s, B=2, C=6)
    cast_reduced(s, "Torgaar, Famine Incarnate", [])
    assert zone_of(s, "Torgaar, Famine Incarnate") == "p1:battlefield" and all(zone_of(s, x.name) == "p1:battlefield" for x in crew)
    assert not any(s.state.players["p1"].mana.values())
    check(s)


def test_torgaar_with_nothing_sacrificed_is_refused_without_the_whole_eight(cards):
    """601.2f: nothing chosen, nothing taken off; 601.2h: the cast fails whole (118.3), the creatures stay."""
    s, crew = torgaar_table(cards)
    mana(s, B=2, C=5)
    with pytest.raises(ActionError):
        cast_reduced(s, "Torgaar, Famine Incarnate", [])
    assert zone_of(s, "Torgaar, Famine Incarnate") == "p1:hand" and all(zone_of(s, x.name) == "p1:battlefield" for x in crew)


def test_torgaar_with_three_sacrificed_costs_two_black(cards):
    s, crew = torgaar_table(cards)
    mana(s, B=2)
    cast_reduced(s, "Torgaar, Famine Incarnate", crew)
    assert zone_of(s, "Torgaar, Famine Incarnate") == "p1:battlefield"
    assert all(zone_of(s, x.name) == "p1:graveyard" for x in crew)
    check(s)


def test_torgaar_with_one_sacrificed_is_refused_without_enough_mana_and_sacrifices_nothing(cards):
    s, crew = torgaar_table(cards)
    mana(s, B=2, C=3)  # ({4}{B}{B} is six mana)
    with pytest.raises(ActionError):
        cast_reduced(s, "Torgaar, Famine Incarnate", crew[:1])
    assert zone_of(s, "Torgaar, Famine Incarnate") == "p1:hand" and zone_of(s, crew[0].name) == "p1:battlefield"
    mana(s, C=1)
    cast_reduced(s, "Torgaar, Famine Incarnate", crew[:1])
    assert zone_of(s, "Torgaar, Famine Incarnate") == "p1:battlefield" and zone_of(s, crew[0].name) == "p1:graveyard"
    check(s)


def test_torgaar_reduction_stops_at_black_black_and_every_creature_chosen_is_still_sacrificed(cards):
    """Ruling 2018-04-27: "can't reduce its cost below {B}{B}. You can sacrifice any number of creatures, even if they won't reduce Torgaar's cost any further.\""""
    s, crew = torgaar_table(cards, 5)
    mana(s, B=2)
    cast_reduced(s, "Torgaar, Famine Incarnate", crew)
    assert zone_of(s, "Torgaar, Famine Incarnate") == "p1:battlefield" and all(zone_of(s, x.name) == "p1:graveyard" for x in crew)
    check(s)


def test_torgaar_asks_which_creatures_privately_and_takes_the_pick_off_the_cost(cards):
    """No ``cost_choices``: the caster is asked (any number, none too); the other player only sees that they are choosing."""
    s, crew = torgaar_table(cards)
    mana(s, B=2, C=2)
    c = card_named(s, "Torgaar, Famine Incarnate")
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:reduce"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.min_choices == 0 and d.max_choices == 3
    assert sorted(o.card_id for o in d.options) == sorted(x.id for x in crew)
    assert s.view("p2")["rules"]["decision"]["kind"] == "waiting"
    s = reloaded_session(s)  # a save and a load in the middle of the question
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[crew[0].id, crew[1].id])
    settle(s)
    assert zone_of(s, "Torgaar, Famine Incarnate") == "p1:battlefield"
    assert [zone_of(s, x.name) for x in crew] == ["p1:graveyard", "p1:graveyard", "p1:battlefield"]
    check(s)


def test_torgaar_without_the_optional_cost_announced_is_the_plain_cast(cards):
    s, crew = torgaar_table(cards)
    mana(s, B=2, C=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Torgaar, Famine Incarnate").id)
    settle(s)
    assert all(zone_of(s, x.name) == "p1:battlefield" for x in crew)
    check(s)


# ---- sacrifice, artifacts and creatures, with history: Dargo, the Shipwrecker ---------------------------------------------------------------
def test_dargo_sacrificing_two_costs_four_less(cards):
    s = build(cards, ["Dargo, the Shipwrecker", "Sol Ring", "Hill Giant"])
    ring, giant = put(s, "Sol Ring"), put(s, "Hill Giant")
    to_hand(s, "Dargo, the Shipwrecker")
    mana(s, R=1, C=2)  # ({6}{R} less 2 + 2)
    cast_reduced(s, "Dargo, the Shipwrecker", [ring, giant])
    assert zone_of(s, "Dargo, the Shipwrecker") == "p1:battlefield" and zone_of(s, "Sol Ring") == "p1:graveyard" and zone_of(s, "Hill Giant") == "p1:graveyard"
    check(s)


def test_dargo_costs_less_for_what_was_sacrificed_earlier_this_turn_even_when_nothing_is_sacrificed_now(cards):
    """Ruling 2020-11-10: "The cost reduction for artifacts and creatures sacrificed earlier in the turn will apply even if you don't sacrifice any as an additional cost.\""""
    s = build(cards, ["Torgaar, Famine Incarnate", "Dargo, the Shipwrecker", "Hill Giant", "Grizzly Bears", "Goblin Piker", "Sol Ring"])
    crew = [put(s, n) for n in ("Hill Giant", "Grizzly Bears", "Goblin Piker")]
    put(s, "Sol Ring")
    to_hand(s, "Torgaar, Famine Incarnate")
    to_hand(s, "Dargo, the Shipwrecker")
    mana(s, B=2)
    cast_reduced(s, "Torgaar, Famine Incarnate", crew)  # (three creatures sacrificed this turn)
    mana(s, R=1)
    c = card_named(s, "Dargo, the Shipwrecker")
    act(s, "p1", type="cast_spell", card_id=c.id)  # ({6}{R} less 6: just {R})
    settle(s)
    assert zone_of(s, "Dargo, the Shipwrecker") == "p1:battlefield" and zone_of(s, "Sol Ring") == "p1:battlefield"
    check(s)


# ---- exile from the graveyard, linked: Gorex, the Tombshell ----------------------------------------------------------------------------------
def test_gorex_exiles_creature_cards_from_the_graveyard_and_is_linked_to_them(cards):
    """Ruling 2021-09-24 and 607.2q: the cards exiled to pay the cost are "exiled with" Gorex; when it dies one of them, chosen at random, goes to its owner's hand."""
    s = build(cards, ["Gorex, the Tombshell", "Murder", "Hill Giant", "Grizzly Bears", "Goblin Piker"])
    dead = [to_graveyard(s, n) for n in ("Hill Giant", "Grizzly Bears", "Goblin Piker")]
    to_hand(s, "Gorex, the Tombshell")
    mana(s, B=2)
    cast_reduced(s, "Gorex, the Tombshell", dead)
    assert zone_of(s, "Gorex, the Tombshell") == "p1:battlefield" and all(zone_of(s, x.name) == "p1:exile" for x in dead)
    to_hand(s, "Murder")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[card_named(s, "Gorex, the Tombshell").id])
    settle(s)
    assert zone_of(s, "Gorex, the Tombshell") == "p1:graveyard"
    assert sorted(zone_of(s, x.name) for x in dead) == ["p1:exile", "p1:exile", "p1:hand"]
    check(s)


def test_gorex_nothing_exiled_is_the_plain_cast_and_nothing_is_linked(cards):
    s = build(cards, ["Gorex, the Tombshell", "Hill Giant"])
    to_graveyard(s, "Hill Giant")
    to_hand(s, "Gorex, the Tombshell")
    mana(s, B=2, C=6)
    cast_reduced(s, "Gorex, the Tombshell", [])
    assert zone_of(s, "Gorex, the Tombshell") == "p1:battlefield" and zone_of(s, "Hill Giant") == "p1:graveyard"
    check(s)


# ---- tap: Explosive Singularity --------------------------------------------------------------------------------------------------------------
def test_explosive_singularity_taps_the_creatures_chosen_and_costs_one_less_for_each(cards):
    s = build(cards, ["Explosive Singularity", "Hill Giant", "Grizzly Bears", "Goblin Piker"])
    crew = [put(s, n) for n in ("Hill Giant", "Grizzly Bears", "Goblin Piker")]
    to_hand(s, "Explosive Singularity")
    mana(s, R=2, C=5)  # ({8}{R}{R} less 3)
    cast_reduced(s, "Explosive Singularity", crew, targets=["p2"])
    assert all(s.state.cards[x.id].tapped for x in crew)
    assert s.state.players["p2"].life == 30
    check(s)


# ---- exile from the hand, hidden until paid: the March cycle ---------------------------------------------------------------------------------
def march_table(cards, theirs=()):
    s = build(cards, ["March of Wretched Sorrow", "Murder", "Dregscape Zombie", "Grizzly Bears"], ["Grizzly Bears", *theirs])
    bears = put(s, "Grizzly Bears", "p2")
    for n in ("March of Wretched Sorrow", "Murder", "Dregscape Zombie", "Grizzly Bears"):
        to_hand(s, n)
    return s, bears


def test_march_exiles_black_cards_from_the_hand_and_costs_two_less_for_each(cards):
    """{X}{B} with X = 2 is {2}{B}; two black cards exiled take {2} each off the generic part, and it can't go below {B} (ruling 2022-02-18)."""
    s, bears = march_table(cards)
    black = [card_named(s, "Murder"), card_named(s, "Dregscape Zombie")]
    mana(s, B=1)
    c = card_named(s, "March of Wretched Sorrow")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2, targets=[bears.id], optional_costs=[f"{c.id}:reduce"],
        cost_choices=[{"component": 0, "cards": [x.id for x in black]}])
    settle(s)
    assert [zone_of(s, "Murder"), zone_of(s, "Dregscape Zombie"), zone_of(s, "Grizzly Bears")] == ["p1:exile", "p1:exile", "p1:hand"]
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and s.state.players["p1"].life == 42
    check(s)


def test_march_asks_about_black_cards_only_and_reveals_nothing_before_it_is_paid(cards):
    """Only the caster is asked, and only black cards are offered; the other player sees neither the question nor the names until the cards are exiled (406.3)."""
    s, bears = march_table(cards)
    mana(s, B=1)
    c = card_named(s, "March of Wretched Sorrow")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2, targets=[bears.id], optional_costs=[f"{c.id}:reduce"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and sorted(o.label for o in d.options) == ["Dregscape Zombie", "Murder"] and d.min_choices == 0
    seen = json.dumps(s.view("p2"))
    assert s.view("p2")["rules"]["decision"]["kind"] == "waiting" and "Murder" not in seen and "Dregscape Zombie" not in seen
    s = reloaded_session(s)  # a save and a load in the middle of the question
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    settle(s)
    assert zone_of(s, "Murder") == "p1:exile" and zone_of(s, "Dregscape Zombie") == "p1:exile"
    assert "Murder" in json.dumps(s.view("p2"))  # (exiled cards are face up, 406.3)
    check(s)


def test_march_is_asked_even_without_black_cards_so_that_the_question_tells_nothing(cards):
    s = build(cards, ["March of Wretched Sorrow", "Grizzly Bears"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "March of Wretched Sorrow")
    to_hand(s, "Grizzly Bears")
    mana(s, B=1, C=2)
    c = card_named(s, "March of Wretched Sorrow")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2, targets=[bears.id], optional_costs=[f"{c.id}:reduce"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.options == [] and d.min_choices == 0
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and zone_of(s, "Grizzly Bears") == "p1:hand"
    check(s)


def test_march_with_one_black_card_exiled_is_refused_without_enough_mana_and_exiles_nothing(cards):
    s, bears = march_table(cards)
    mana(s, B=1)  # ({3}{B} less 2 is {1}{B}: one short)
    c = card_named(s, "March of Wretched Sorrow")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, x_value=3, targets=[bears.id], optional_costs=[f"{c.id}:reduce"],
            cost_choices=[{"component": 0, "cards": [card_named(s, "Murder").id]}])
    assert zone_of(s, "Murder") == "p1:hand" and zone_of(s, "March of Wretched Sorrow") == "p1:hand"


def test_march_of_otherworldly_light_exiles_a_target_with_mana_value_x_or_less_of_any_kind(cards):
    """"Exile target artifact, creature, or enchantment with mana value X or less.": the limit is on each kind (the 2022-02-18 ruling's example), not on enchantments alone."""
    s = build(cards, ["March of Otherworldly Light"], ["Grizzly Bears", "Sol Ring"])
    bears, ring = put(s, "Grizzly Bears", "p2"), put(s, "Sol Ring", "p2")
    to_hand(s, "March of Otherworldly Light")
    mana(s, W=1, C=1)
    c = card_named(s, "March of Otherworldly Light")
    with pytest.raises(ActionError):  # (X = 1: Grizzly Bears has mana value 2)
        act(s, "p1", type="cast_spell", card_id=c.id, x_value=1, targets=[bears.id])
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=1, targets=[ring.id])
    settle(s)
    assert zone_of(s, "Sol Ring", "p2") == "p2:exile" and zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield"
    check(s)


# ---- a cast without paying its mana cost (118.9d), a copy (707.10) ---------------------------------------------------------------------------
def pick(s, *option_ids):
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(option_ids))


def cascade_march(cards):
    """Bloodbraid Elf (paid from the pool) cascades into March of Wretched Sorrow ({X}{B}, mana value 2), with Murder in hand; "cast it?" is answered "yes"."""
    s = build(cards, ["Bloodbraid Elf", "March of Wretched Sorrow", "Murder"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    stack_top(s, ["March of Wretched Sorrow"])
    to_hand(s, "Bloodbraid Elf")
    to_hand(s, "Murder")
    mana(s, R=1, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Bloodbraid Elf").id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") == "suspend_cast":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    pick(s, "yes")
    return s


def test_a_free_cast_of_march_is_offered_the_exile_cost_and_pays_it(cards):
    """118.9d: a spell cast without paying its mana cost still has its additional costs announced (601.2b) and paid (601.2h): the caster is asked, and the hand's
    cards are offered whether or not one is black."""
    s = cascade_march(cards)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and (d.resume or {}).get("step") == "free_optional"
    assert [o.label for o in d.options] == ["This spell costs {2} less for each: exile any number of black cards from your hand"]
    s = reloaded_session(s)  # a save and a load in the middle of the question
    pick(s, d.options[0].id)
    pick(s, card_named(s, "Grizzly Bears", "p2").id)  # (the target comes first, 601.2c)
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options] == ["Murder"]
    pick(s, d.options[0].id)
    settle(s)
    assert zone_of(s, "Murder") == "p1:exile" and zone_of(s, "March of Wretched Sorrow") == "p1:graveyard"
    check(s)


def test_a_free_cast_of_march_declined_exiles_nothing(cards):
    s = cascade_march(cards)
    pick(s)
    pick(s, card_named(s, "Grizzly Bears", "p2").id)
    settle(s)
    assert zone_of(s, "Murder") == "p1:hand" and zone_of(s, "March of Wretched Sorrow") == "p1:graveyard"
    check(s)


def test_a_copy_of_a_march_pays_nothing_and_exiles_nothing(cards):
    """707.10: a copy of a spell is not cast and no cost is paid for it; only the original exiled the cards (Bob copies Alice's March with Reverberate)."""
    s, bears = march_table(cards, ["Reverberate"])
    to_hand(s, "Reverberate", "p2")
    mana(s, B=1)
    mana(s, "p2", R=2)
    c = card_named(s, "March of Wretched Sorrow")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2, targets=[bears.id], optional_costs=[f"{c.id}:reduce"],
        cost_choices=[{"component": 0, "cards": [card_named(s, "Murder").id, card_named(s, "Dregscape Zombie").id]}])
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Reverberate", "p2").id, targets=[c.id])
    settle(s)
    assert sorted(x.name for x in s.state.cards.values() if x.zone == "p1:exile") == ["Dregscape Zombie", "Murder"]
    assert not any(x.zone == "p2:exile" for x in s.state.cards.values())
    assert s.state.players["p2"].life == 42 and s.state.players["p1"].life == 40  # (Bob's copy, X = 2, resolves first and kills the target: the original fizzles, 608.2b)
    check(s)


# ---- the back face of a double-faced card: Extus, Oriq Overlord // Awaken the Blood Avatar -----------------------------------------------------
def test_awaken_the_blood_avatar_sacrificing_three_creatures_costs_six_less(cards):
    """Ruling 2021-04-16: "can't reduce its cost below {B}{R}. However, you can sacrifice any number of creatures"; the line is read for the face that is cast (712.11b)."""
    s = build(cards, ["Extus, Oriq Overlord // Awaken the Blood Avatar", "Hill Giant", "Grizzly Bears", "Goblin Piker"], ["Grizzly Bears"])
    crew = [put(s, n) for n in ("Hill Giant", "Grizzly Bears", "Goblin Piker")]
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Extus, Oriq Overlord // Awaken the Blood Avatar")
    mana(s, B=1, R=1)
    c = card_named(s, "Extus, Oriq Overlord // Awaken the Blood Avatar")
    act(s, "p1", type="cast_spell", card_id=c.id, face=1, optional_costs=[f"{c.id}:reduce"],
        cost_choices=[{"component": 0, "cards": [x.id for x in crew]}])
    settle(s)
    assert all(zone_of(s, x.name) == "p1:graveyard" for x in crew) and zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    assert any(x.is_token and x.controller == "p1" and x.zone == "p1:battlefield" for x in s.state.cards.values())  # (the Avatar)
    check(s)


# ---- counters from among creatures: Hierophant Bio-Titan --------------------------------------------------------------------------------------
def test_hierophant_bio_titan_removes_the_counters_chosen_and_costs_two_less_for_each(cards):
    """{10}{G}{G}: four +1/+1 counters removed (each one a pick, from any of the creatures: 122.1) take {8} off, leaving {2}{G}{G}; the others stay."""
    s = build(cards, ["Hierophant Bio-Titan", "Hill Giant", "Grizzly Bears"])
    giant, bears = put(s, "Hill Giant"), put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[giant.id], kind="+1/+1", delta=3)
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=2)
    to_hand(s, "Hierophant Bio-Titan")
    mana(s, G=2, C=2)
    c = card_named(s, "Hierophant Bio-Titan")
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:reduce"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.min_choices == 0 and d.max_choices == 5 and d.options[0].label == "+1/+1 counter on Hill Giant"
    s = reloaded_session(s)  # a save and a load in the middle of the question
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options[1:5]])
    settle(s)
    assert zone_of(s, "Hierophant Bio-Titan") == "p1:battlefield"
    assert sum(s.state.cards[x.id].counters.get("+1/+1", 0) for x in (giant, bears)) == 1
    check(s)


def test_hierophant_bio_titan_with_no_counters_on_the_table_asks_nothing_and_costs_the_whole_twelve(cards):
    s = build(cards, ["Hierophant Bio-Titan", "Hill Giant"])
    put(s, "Hill Giant")
    to_hand(s, "Hierophant Bio-Titan")
    mana(s, G=2, C=10)
    c = card_named(s, "Hierophant Bio-Titan")
    act(s, "p1", type="cast_spell", card_id=c.id, optional_costs=[f"{c.id}:reduce"])
    settle(s)
    assert zone_of(s, "Hierophant Bio-Titan") == "p1:battlefield"
    check(s)


def test_march_of_swirling_mist_exiles_a_blue_card_and_phases_out_up_to_x_creatures(cards):
    """{X}{U} with X = 2 is {2}{U}; one blue card exiled (the green one stays) makes it {U}; two creatures phase out (702.26), the ruling's mana value on the stack is X + 1."""
    s = build(cards, ["March of Swirling Mist", "Counterspell", "Grizzly Bears"], ["Grizzly Bears", "Hill Giant"])
    bears, giant = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p2")
    for n in ("March of Swirling Mist", "Counterspell", "Grizzly Bears"):
        to_hand(s, n)
    mana(s, U=1)
    c = card_named(s, "March of Swirling Mist")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2, targets=[bears.id, giant.id], target_counts=[2], optional_costs=[f"{c.id}:reduce"],
        cost_choices=[{"component": 0, "cards": [card_named(s, "Counterspell").id]}])
    settle(s)
    assert zone_of(s, "Counterspell") == "p1:exile" and zone_of(s, "Grizzly Bears") == "p1:hand"
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:phased" and zone_of(s, "Hill Giant", "p2") == "p2:phased"
    check(s)


# ---- "You may play up to two of those cards": March of Reckless Joy -------------------------------------------------------------------------
def test_march_of_reckless_joy_exiles_x_cards_and_lets_you_play_two_of_them(cards):
    """{X}{R} with X = 3 is {3}{R}; two red cards exiled from the hand make it {R}. The top three cards are exiled and only two of them may be played (the one
    that is left has no permission once the second is cast); which ones is chosen as they are played (ruling 2022-02-18)."""
    s = build(cards, ["March of Reckless Joy", "Lightning Bolt", "Fiery Temper", "Savannah Lions", "Goblin Piker", "Grizzly Bears"])
    stack_top(s, ["Savannah Lions", "Goblin Piker", "Grizzly Bears"])
    for n in ("March of Reckless Joy", "Lightning Bolt", "Fiery Temper"):
        to_hand(s, n)
    mana(s, R=1)
    c = card_named(s, "March of Reckless Joy")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=3, optional_costs=[f"{c.id}:reduce"],
        cost_choices=[{"component": 0, "cards": [card_named(s, "Lightning Bolt").id, card_named(s, "Fiery Temper").id]}])
    settle(s)
    assert [zone_of(s, n) for n in ("Savannah Lions", "Goblin Piker", "Grizzly Bears")] == ["p1:exile"] * 3
    assert len([p for p in s.state.rules.permissions if p.player == "p1"]) == 3
    s = reloaded_session(s)  # a save and a load with the permissions in place
    mana(s, W=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Savannah Lions").id)
    settle(s)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Goblin Piker").id)
    settle(s)
    assert zone_of(s, "Savannah Lions") == "p1:battlefield" and zone_of(s, "Goblin Piker") == "p1:battlefield"
    assert not [p for p in s.state.rules.permissions if p.player == "p1"]  # (two were played: the third card can't be)
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    assert zone_of(s, "Grizzly Bears") == "p1:exile"
    check(s)


# ---- "mana value less than X": March of Burgeoning Life ---------------------------------------------------------------------------------------
def test_march_of_burgeoning_life_finds_the_same_name_for_a_target_with_mana_value_below_x(cards):
    """Ruling 2022-02-18: the target's mana value must be less than X (equal is not legal); exiling two green cards from the hand makes {3}{G} just {G}; the search puts
    the same-named creature onto the battlefield tapped."""
    s = build(cards, ["March of Burgeoning Life", "Giant Growth", "Llanowar Elves", "Grizzly Bears"], ["Grizzly Bears"])
    foe = put(s, "Grizzly Bears", "p2")
    for n in ("March of Burgeoning Life", "Giant Growth", "Llanowar Elves"):
        to_hand(s, n)
    mana(s, G=1)
    c = card_named(s, "March of Burgeoning Life")
    green = [card_named(s, "Giant Growth").id, card_named(s, "Llanowar Elves").id]
    with pytest.raises(ActionError):  # (X = 2: Grizzly Bears has mana value 2, not less)
        act(s, "p1", type="cast_spell", card_id=c.id, x_value=2, targets=[foe.id], optional_costs=[f"{c.id}:reduce"], cost_choices=[{"component": 0, "cards": green}])
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=3, targets=[foe.id], optional_costs=[f"{c.id}:reduce"], cost_choices=[{"component": 0, "cards": green}])
    settle(s)
    assert zone_of(s, "Giant Growth") == "p1:exile" and zone_of(s, "Llanowar Elves") == "p1:exile"
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and s.state.cards[card_named(s, "Grizzly Bears").id].tapped
    check(s)


# ---- the hint the table menu is made from -----------------------------------------------------------------------------------------------------
def test_the_menu_offers_the_any_number_cost_when_the_most_it_takes_off_makes_the_spell_payable(cards):
    """Eight mana is too much for two floating, so the plain cast isn't offered; with three creatures to sacrifice ({6} off) the cost is payable, and the
    option is listed with the id the cast names. With no creature to sacrifice it isn't."""
    s, crew = torgaar_table(cards)
    mana(s, B=2)
    c = card_named(s, "Torgaar, Famine Incarnate")
    found = hints(s.state, "p1", cards)
    assert c.id not in found["castable"]
    (opt,) = found["optional_costs"][c.id]
    assert opt["id"] == f"{c.id}:reduce" and opt["label"] == "This spell costs {2} less for each: sacrifice any number of creatures"
    for x in crew:
        act(s, "p1", type="move", card_ids=[x.id], to={"zone": "graveyard"})
    assert c.id not in hints(s.state, "p1", cards).get("optional_costs", {})


# ---- a choice for every counter, every opponent in turn order, paid together: Rottenmouth Viper ------------------------------------------------
def viper_table(cards, bob=(), carol=()):
    decks = [deck(cards, "Krenko, Mob Boss", [(1, "Rottenmouth Viper"), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")]),
             deck(cards, "Krenko, Mob Boss", [*((1, n) for n in carol), (20, "Mountain")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def viper_enters(s):
    """Alice casts Rottenmouth Viper (nothing sacrificed); its trigger's first question waits."""
    to_hand(s, "Rottenmouth Viper")
    mana(s, B=1, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Rottenmouth Viper").id)
    for _ in range(10):
        if s.state.rules.decision is not None:
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def answer(s, *ids):
    d = s.state.rules.decision
    assert d is not None, "nothing was asked"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))
    return s.state.rules.decision


def test_viper_asks_each_opponent_in_turn_order_and_acts_on_all_the_choices_together(cards):
    """Ruling 2024-07-26: each opponent in turn order chooses; the sacrifice, the discard and the life loss happen after the last choice. Bob sacrifices his Bears and
    Carol declines: nothing has happened while Carol is asked, and then Bears is gone and only Carol loses 4."""
    s = viper_table(cards, ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Mountain", "p3")  # (a player with nothing to sacrifice or discard isn't asked: they lose the life)
    d = viper_enters(s)
    assert d.player == "p2" and [o.id for o in d.options][:1] == ["pay:0"] and any(o.id == "decline" for o in d.options)
    d = answer(s, "pay:0")  # (the only nonland permanent: no second question)
    assert d is not None and d.player == "p3" and zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield"
    s = reloaded_session(s)  # a save and a load in the middle of the choices
    answer(s, "decline")
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and zone_of(s, "Mountain", "p3") == "p3:hand"
    assert s.state.players["p2"].life == 40 and s.state.players["p3"].life == 36
    assert s.state.cards[card_named(s, "Rottenmouth Viper").id].counters.get("blight") == 1
    check(s)


def test_viper_lets_an_opponent_always_lose_the_life_instead(cards):
    """Ruling 2024-07-26: "An opponent can always choose not to sacrifice a nonland permanent or discard a card (and therefore lose 4 life)\"."""
    s = viper_table(cards, ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Mountain", "p3")
    viper_enters(s)
    answer(s, "decline")
    answer(s, "decline")
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield" and s.state.players["p2"].life == 36 and s.state.players["p3"].life == 36
    check(s)


def test_viper_attacking_with_two_counters_asks_twice_and_never_the_same_object_again(cards):
    """Two blight counters: each opponent chooses twice. Bob has two nonland permanents and sacrifices for both choices: the second can only be the one the first did
    not take (previously chosen can't be chosen again); Carol, with one, can sacrifice for the first and only discard or lose the life for the second."""
    s = viper_table(cards, ["Grizzly Bears", "Hill Giant"], ["Savannah Lions"])
    bears, giant = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p2")
    put(s, "Savannah Lions", "p3")
    viper_enters(s)
    answer(s, "decline")
    answer(s, "decline")  # (turn 1: both lose 4)
    settle(s)
    viper = card_named(s, "Rottenmouth Viper")
    until(s, lambda s: s.state.turn.number == 4 and (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": viper.id, "target": "p2"}])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"
    d = answer(s, "pay:0")  # Bob, first choice: a sacrifice, which one
    assert d is not None and d.player == "p2" and sorted(o.card_id for o in d.options) == sorted([bears.id, giant.id])
    d = answer(s, bears.id)
    assert d is not None and d.player == "p2" and [o.id for o in d.options][:1] == ["pay:0"]  # Bob, second choice
    d = answer(s, "pay:0")  # (only Hill Giant is left to take: no question)
    assert d is not None and d.player == "p3"
    d = answer(s, "pay:0")  # Carol, first choice: her only nonland permanent
    assert d is not None and d.player == "p3" and [o.id for o in d.options] == ["pay:1", "decline"]  # (the second: Savannah Lions is taken already, a discard or the life)
    answer(s, "decline")
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and zone_of(s, "Hill Giant", "p2") == "p2:graveyard"
    assert zone_of(s, "Savannah Lions", "p3") == "p3:graveyard"
    assert s.state.players["p2"].life == 30 and s.state.players["p3"].life == 32  # (Bob: 36 less the Viper's 6 combat damage, nothing to the trigger; Carol: 36 less 4 for her second choice)
    assert s.state.cards[viper.id].counters.get("blight") == 2
    check(s)


def test_viper_does_not_reveal_a_card_chosen_to_be_discarded_until_it_is_discarded(cards):
    """Ruling 2024-07-26: "cards chosen to be discarded this way won't be revealed until they're discarded at the end of the process". While Carol is still being asked,
    Alice and Carol see nothing of Bob's pick; afterwards the card is in his graveyard."""
    s = viper_table(cards, ["Grizzly Bears"])
    to_hand(s, "Grizzly Bears", "p2")
    to_hand(s, "Mountain", "p3")
    d = viper_enters(s)
    assert d.player == "p2" and [o.id for o in d.options] == ["pay:1", "decline"]  # (no nonland permanent: a discard or the life)
    d = answer(s, "pay:1")
    assert d is not None and d.player == "p3"
    for viewer in ("p1", "p3"):
        assert "Grizzly Bears" not in json.dumps(s.view(viewer)), viewer
    answer(s, "decline")
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and "Grizzly Bears" in json.dumps(s.view("p3"))
    assert s.state.players["p2"].life == 40 and s.state.players["p3"].life == 36
    check(s)


# ---- "Repeat the following process X times": Torment of Hailfire ----------------------------------------------------------------------------
def test_torment_of_hailfire_repeats_the_process_and_each_repetition_is_done_before_the_next(cards):
    """Ruling 2017-07-14: each repetition is done separately (the choice, then the sacrifice, the discard or the life loss, then the next choice). X = 2: Bob sacrifices
    his Bears for the first, which is gone when the second is asked, and declines the second."""
    s = build(cards, ["Torment of Hailfire"], ["Grizzly Bears", "Hill Giant"])
    put(s, "Grizzly Bears", "p2")
    giant = put(s, "Hill Giant", "p2")
    to_hand(s, "Torment of Hailfire")
    mana(s, B=2, C=2)
    c = card_named(s, "Torment of Hailfire")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2)
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and [o.id for o in d.options] == ["pay:0", "decline"]
    d = answer(s, "pay:0")
    assert d is not None and sorted(o.card_id for o in d.options) == sorted(x.id for x in s.state.cards.values() if x.zone == "p2:battlefield" and x.name != "Island")
    d = answer(s, giant.id)  # (Hill Giant: the choice of the first repetition)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard" and d is not None and d.player == "p2"  # (done before the second repetition asks)
    assert [o.id for o in d.options][:1] == ["pay:0"]
    s = reloaded_session(s)  # a save and a load between the repetitions
    answer(s, "decline")
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield" and s.state.players["p2"].life == 37
    check(s)


def test_torment_of_hailfire_with_x_zero_does_nothing(cards):
    """Ruling 2017-07-14: "If X is 0, Torment of Hailfire resolves with no effect.\""""
    s = build(cards, ["Torment of Hailfire"], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Torment of Hailfire")
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Torment of Hailfire").id, x_value=0)
    settle(s)
    assert s.state.players["p2"].life == 40 and zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield" and zone_of(s, "Torment of Hailfire") == "p1:graveyard"
    check(s)
