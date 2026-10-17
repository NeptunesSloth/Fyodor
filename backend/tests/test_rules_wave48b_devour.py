"""Wave 48B: devour (702.82) and what a permanent devoured (702.82b), real Oracle text (tests/fixtures/wave48b_cards.json). Every scenario checks the replay and a save and a load.

* 702.82a: "As this object enters, you may sacrifice any number of creatures. This permanent enters with N +1/+1 counters on it for each creature sacrificed this way."
* 702.82b: "It devoured" means "sacrificed as a result of its devour ability as it entered the battlefield": "twice the number of Goblins it devoured" (Voracious Dragon, each
  checked as it last existed, 2009-02-01 ruling) and "has flying and trample if it devoured a creature" (Hellkite Hatchling).
* Thromok the Insatiable: "Devour X, where X is the number of creatures devoured this way": X counters for each, so n creatures make n times n (2012-06-01 ruling).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave48b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w48b", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Voracious Dragon", "Hellkite Hatchling", "Thromok the Insatiable", "Mycoloth"])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def devour_cast(s, name, picks, targets=None, **m):
    """Cast ``name`` from the hand and answer devour's questions with ``picks`` (card ids, in order, then "done") and any target question with ``targets``."""
    c = to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id)
    picks, targets = list(picks), list(targets or [])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            if "done" in ids:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[picks.pop(0) if picks else "done"])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[targets.pop(0)] if targets else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return s.state.cards[c.id]
    raise AssertionError("the stack never emptied")


def plus_counters(s, name):
    return s.state.cards[card_named(s, name).id].counters.get("+1/+1", 0)


def keywords(s, name):
    return set(Plan(s.state, "p1", s.cards, None).ch(card_named(s, name)).keywords)


def devour_table(cards, devourer, crew, extra=()):
    s = build(cards, [devourer, *crew, *extra])
    return s, [put(s, n) for n in crew]


def test_voracious_dragon_deals_twice_the_number_of_goblins_it_devoured(cards):
    """Ruling 2009-02-01: "The number of Goblins it devoured" means the Goblins sacrificed as a result of its devour ability as it entered; each is checked as it last existed.
    The Dragon can devour any type of creature, not just Goblins (devour 1: a counter for each)."""
    s, crew = devour_table(cards, "Voracious Dragon", ("Goblin Piker", "Goblin Chieftain", "Hill Giant"))
    devour_cast(s, "Voracious Dragon", [x.id for x in crew], targets=["p2"], R=2, C=3)
    assert plus_counters(s, "Voracious Dragon") == 3 and all(zone_of(s, x.name) == "p1:graveyard" for x in crew)
    assert life(s, "p2") == 40 - 4  # (two Goblins: Goblin Piker and Goblin Chieftain; the Giant is not one)
    check(s)


def test_voracious_dragon_devouring_no_goblin_deals_no_damage(cards):
    s, crew = devour_table(cards, "Voracious Dragon", ("Hill Giant", "Gray Ogre"))
    devour_cast(s, "Voracious Dragon", [crew[0].id], targets=["p2"], R=2, C=3)
    assert plus_counters(s, "Voracious Dragon") == 1 and life(s, "p2") == 40 and zone_of(s, "Gray Ogre") == "p1:battlefield"
    check(s)


def test_voracious_dragon_with_nothing_devoured_deals_no_damage(cards):
    s, crew = devour_table(cards, "Voracious Dragon", ("Goblin Piker",))
    devour_cast(s, "Voracious Dragon", [], targets=["p2"], R=2, C=3)
    assert plus_counters(s, "Voracious Dragon") == 0 and life(s, "p2") == 40 and zone_of(s, "Goblin Piker") == "p1:battlefield"
    check(s)


def test_voracious_dragon_with_a_counter_doubler_gets_twice_the_counters_but_the_damage_counts_the_goblins(cards):
    """Doubling Season (ruling 2024-11-08: "affects permanents that enter with counters"): four +1/+1 counters for two creatures devoured; the damage still counts Goblins."""
    s, crew = devour_table(cards, "Voracious Dragon", ("Goblin Piker", "Hill Giant"), ("Doubling Season",))
    put(s, "Doubling Season")
    devour_cast(s, "Voracious Dragon", [x.id for x in crew], targets=["p2"], R=2, C=3)
    assert plus_counters(s, "Voracious Dragon") == 4 and life(s, "p2") == 40 - 2
    check(s)


def test_hellkite_hatchling_has_flying_and_trample_if_it_devoured_a_creature(cards):
    s, crew = devour_table(cards, "Hellkite Hatchling", ("Hill Giant", "Gray Ogre"))
    devour_cast(s, "Hellkite Hatchling", [crew[0].id], R=1, G=1, C=2)
    assert {"flying", "trample"} <= keywords(s, "Hellkite Hatchling") and plus_counters(s, "Hellkite Hatchling") == 1
    check(s)


def test_hellkite_hatchling_that_devoured_nothing_has_neither(cards):
    s, crew = devour_table(cards, "Hellkite Hatchling", ("Hill Giant",))
    devour_cast(s, "Hellkite Hatchling", [], R=1, G=1, C=2)
    assert not ({"flying", "trample"} & keywords(s, "Hellkite Hatchling"))
    check(s)


def test_hellkite_hatchling_keeps_flying_without_its_counters_but_a_new_object_devoured_nothing(cards):
    """Ruling 2009-02-01: "It retains those abilities even if its +1/+1 counters are somehow removed." Back from the hand it is a new object (400.7) that devoured nothing."""
    s, crew = devour_table(cards, "Hellkite Hatchling", ("Hill Giant",))
    devour_cast(s, "Hellkite Hatchling", [crew[0].id], R=1, G=1, C=2)
    hatch = card_named(s, "Hellkite Hatchling")
    act(s, "p1", type="counter", card_ids=[hatch.id], kind="+1/+1", delta=-1)
    assert "flying" in keywords(s, "Hellkite Hatchling")
    act(s, "p1", type="move", card_ids=[hatch.id], to={"zone": "hand"})
    devour_cast(s, "Hellkite Hatchling", [], R=1, G=1, C=2)
    assert "flying" not in keywords(s, "Hellkite Hatchling")
    check(s)


def test_thromok_enters_with_that_many_counters_for_each_creature_devoured(cards):
    """Ruling 2012-06-01: "if Thromok devours one creature, it will enter with one +1/+1 counter on it. If it devours two creatures, it will enter with two +1/+1 counters
    for each of them, for a total of four. Devouring three creatures will produce nine +1/+1 counters.\""""
    s, crew = devour_table(cards, "Thromok the Insatiable", ("Hill Giant", "Gray Ogre", "Goblin Piker"))
    devour_cast(s, "Thromok the Insatiable", [x.id for x in crew], R=1, G=1, C=3)
    assert plus_counters(s, "Thromok the Insatiable") == 9 and all(zone_of(s, x.name) == "p1:graveyard" for x in crew)
    check(s)


def test_thromok_with_two_devoured_and_a_counter_doubler_enters_with_eight(cards):
    s, crew = devour_table(cards, "Thromok the Insatiable", ("Hill Giant", "Gray Ogre"), ("Doubling Season",))
    put(s, "Doubling Season")
    devour_cast(s, "Thromok the Insatiable", [x.id for x in crew], R=1, G=1, C=3)
    assert plus_counters(s, "Thromok the Insatiable") == 8
    check(s)


def test_thromok_that_devoured_one_is_a_one_one(cards):
    s, crew = devour_table(cards, "Thromok the Insatiable", ("Hill Giant",))
    devour_cast(s, "Thromok the Insatiable", [crew[0].id], R=1, G=1, C=3)
    assert plus_counters(s, "Thromok the Insatiable") == 1 and zone_of(s, "Thromok the Insatiable") == "p1:battlefield"
    check(s)


def test_thromok_that_devoured_none_is_a_zero_zero_and_dies(cards):
    s, crew = devour_table(cards, "Thromok the Insatiable", ("Hill Giant",))
    devour_cast(s, "Thromok the Insatiable", [], R=1, G=1, C=3)
    assert zone_of(s, "Thromok the Insatiable") == "p1:graveyard" and zone_of(s, "Hill Giant") == "p1:battlefield"
    check(s)
