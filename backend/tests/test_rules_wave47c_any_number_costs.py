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
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
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
