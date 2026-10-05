"""Wave 22D: resolution memory and linked objects (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 608.2h / 107.3c: "where X is 2 plus the sacrificed creature's mana value" - a spell's additional-cost sacrifice is read as the creature last existed.
* 607.2a / 608.2h: "the exiled card's owner creates an X/X token, where X is the mana value of the exiled card" - the linked ability's card.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import pt

EXTRA = [
    real("Eldritch Evolution", "{1}{G}{G}", 3, "Sorcery",
         "As an additional cost to cast this spell, sacrifice a creature.\nSearch your library for a creature card with mana value X or less, where X is 2 plus the sacrificed creature's mana value. Put that card onto the battlefield, then shuffle. Exile Eldritch Evolution.",
         None, "G"),
    real("Probe Four", "{3}{G}", 4, "Creature — Beast", "", ("4", "4"), "G"),
    real("Probe Five", "{4}{G}", 5, "Creature — Beast", "", ("5", "5"), "G"),
    real("Probe Two", "{1}{G}", 2, "Creature — Beast", "", ("2", "2"), "G"),
    real("Skyclave Apparition", "{1}{W}{W}", 3, "Creature — Kor Wizard",
         "When this creature enters, exile up to one target nonland, nontoken permanent you don't control with mana value 4 or less.\nWhen this creature leaves the battlefield, the exiled card's owner creates an X/X blue Illusion creature token, where X is the mana value of the exiled card.",
         ("2", "2"), "W"),
    real("Probe Rock", "{3}", 3, "Artifact", "", None),
    real("Probe Flicker", "{1}{W}", 2, "Instant", "Exile target creature you control, then return it to the battlefield under its owner's control.", None, "W"),
]
NAMES = ["Eldritch Evolution", "Skyclave Apparition"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def zone(s, name, pid="p1"):
    return s.state.cards[find(s, name, pid).id].zone


def tokens(s, name, pid):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


def test_eldritch_evolution_finds_up_to_two_more_than_the_sacrificed_creature(cards):
    s = build(cards, p1=("Eldritch Evolution", "Probe Two", "Probe Four", "Probe Five"))
    put(s, "Probe Two", "battlefield")
    spell = put(s, "Eldritch Evolution", "hand")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    assert zone(s, "Probe Two") == "p1:graveyard"  # sacrificed as a cost
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    names = {s.state.cards[o.id].name for o in d.options}
    assert "Probe Four" in names and "Probe Five" not in names  # mana value 2 + 2 = 4 or less
    answer(s, pick=find(s, "Probe Four").id)
    assert zone(s, "Probe Four") == "p1:battlefield" and zone(s, "Eldritch Evolution") == "p1:exile"
    roundtrip(s)


def _skyclave(cards):
    s = build(cards, p1=("Skyclave Apparition", "Probe Flicker"), p2=("Probe Rock", "Ambush Viper"))
    rock = put(s, "Probe Rock", "battlefield", pid="p2")
    put(s, "Ambush Viper", "battlefield", pid="p2")
    sky = put(s, "Skyclave Apparition", "hand")
    mana(s, W=3)
    act(s, "p1", type="cast_spell", card_id=sky.id)
    pass_until_stack_empty(s)
    answer(s, pick=rock.id)
    assert s.state.cards[rock.id].zone == "p2:exile"
    return s, sky, rock


def test_skyclave_apparition_gives_its_owner_a_token_the_size_of_the_exiled_card(cards):
    s, sky, rock = _skyclave(cards)
    roundtrip(s)
    act(s, "p1", type="set_damage", card_ids=[sky.id], value=2)  # it dies (state-based action)
    act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert len(tokens(s, "Illusion", "p2")) == 1  # the exiled card's owner (Bob), not Alice
    assert pt(s, "Illusion", "p2") == (3, 3)  # the mana value of the exiled card
    assert s.state.cards[rock.id].zone == "p2:exile"  # the exile is permanent
    assert not tokens(s, "Illusion", "p1")
    roundtrip(s)


def test_skyclave_apparition_blinked_leaves_a_token_and_the_card_stays_exiled(cards):
    s, sky, rock = _skyclave(cards)
    mana(s, W=1, C=1)
    flicker = put(s, "Probe Flicker", "hand")
    act(s, "p1", type="cast_spell", card_id=flicker.id, targets=[sky.id])
    answer(s)  # the leaves trigger (token), then the new Apparition's enters trigger (another exile)
    assert len(tokens(s, "Illusion", "p2")) == 1
    assert s.state.cards[rock.id].zone == "p2:exile"  # never returns: the old object's link ended with it (400.7)
    roundtrip(s)
