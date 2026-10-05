"""Wave 22D: "until ~ leaves the battlefield" (CR 610.3, 2026-09-25). Real Oracle text; replay and save/load checked.

* 610.3: the object returns to its previous zone - a card chosen from a hand goes back to that hand, not the battlefield; 610.3a-b: if the
  source left before the ability resolved, nothing is exiled.
* 608.2d: "exile any number of non-Angel creatures you control until ~ leaves the battlefield" is chosen as the ability resolves.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    real("Kitesail Freebooter", "{1}{B}", 2, "Creature — Human Pirate",
         "Flying\nWhen this creature enters, target opponent reveals their hand. You choose a noncreature, nonland card from it. Exile that card until this creature leaves the battlefield.",
         ("1", "2"), "B"),
    real("Glorious Protector", "{2}{W}{W}", 4, "Creature — Angel Cleric",
         "Flash\nFlying\nWhen this creature enters, you may exile any number of non-Angel creatures you control until this creature leaves the battlefield.\nForetell {2}{W}",
         ("3", "4"), "W"),
    real("Abdel Adrian, Gorion's Ward", "{4}{W}", 5, "Legendary Creature — Human Warrior",
         "When Abdel Adrian enters, exile any number of other nonland permanents you control until Abdel Adrian leaves the battlefield. Create a 1/1 white Soldier creature token for each permanent exiled this way.\nChoose a Background (You can have a Background as a second commander.)",
         ("4", "4"), "W"),
    real("Probe Rock", "{3}", 3, "Artifact", "", None),
    real("Probe Two", "{1}{G}", 2, "Creature — Beast", "", ("2", "2"), "G"),
]
NAMES = ["Kitesail Freebooter", "Glorious Protector", "Abdel Adrian, Gorion's Ward"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_kitesail_freebooter_takes_a_card_from_the_hand_and_gives_it_back_to_the_hand(cards):
    s = build(cards, p1=("Kitesail Freebooter",), p2=("Probe Rock", "Probe Two"))
    rock, two = put(s, "Probe Rock", "hand", pid="p2"), put(s, "Probe Two", "hand", pid="p2")
    freebooter = put(s, "Kitesail Freebooter", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=freebooter.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])  # the target opponent
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert [o.card_id for o in d.options] == [rock.id]  # a noncreature, nonland card: the creature isn't offered
    answer(s, pick=rock.id)
    assert s.state.cards[rock.id].zone == "p2:exile" and s.state.cards[two.id].zone == "p2:hand"
    assert not s.state.cards[two.id].revealed_to  # the rest of the hand is hidden again (701.20a)
    roundtrip(s)
    act(s, "p1", type="set_damage", card_ids=[freebooter.id], value=2)
    act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[rock.id].zone == "p2:hand"  # 610.3: to its previous zone, its owner's hand
    assert not s.state.cards[rock.id].revealed_to
    roundtrip(s)


def test_glorious_protector_exiles_the_creatures_you_choose_and_returns_them_when_it_leaves(cards):
    s = build(cards, p1=("Glorious Protector", "Probe Two", "Ambush Viper"))
    two, viper = put(s, "Probe Two", "battlefield"), put(s, "Ambush Viper", "battlefield")
    protector = put(s, "Glorious Protector", "hand")
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=protector.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])  # "you may": yes
    d = s.state.rules.decision
    assert d is not None and {o.card_id for o in d.options} == {two.id, viper.id}  # not itself: an Angel
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    pass_until_stack_empty(s)
    assert s.state.cards[two.id].zone == "p1:exile" and s.state.cards[viper.id].zone == "p1:exile"
    roundtrip(s)
    act(s, "p1", type="set_damage", card_ids=[protector.id], value=4)
    act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[two.id].zone == "p1:battlefield" and s.state.cards[viper.id].zone == "p1:battlefield"
    roundtrip(s)


def test_abdel_adrian_makes_a_soldier_for_each_permanent_exiled_this_way(cards):
    s = build(cards, p1=("Abdel Adrian, Gorion's Ward", "Probe Two", "Probe Rock"))
    put(s, "Probe Two", "battlefield")
    put(s, "Probe Rock", "battlefield")
    abdel = put(s, "Abdel Adrian, Gorion's Ward", "hand")
    mana(s, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=abdel.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    pass_until_stack_empty(s)
    soldiers = [c for c in s.state.cards.values() if c.name == "Soldier" and c.zone == "p1:battlefield"]
    assert len(soldiers) == 2  # one for each of the two permanents exiled
    roundtrip(s)
