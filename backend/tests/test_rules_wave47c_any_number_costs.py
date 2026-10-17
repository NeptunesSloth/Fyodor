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
from tests.test_rules_wave30h_linked_exile import settle
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
