"""Wave 22B: choosing a card name (CR 201.4, 709.4a) and the prohibitions that read it (601.3, 602.5). Real Oracle text; every scenario
checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, put, to_hand, zone_of

EXTRA = [
    real("Meddling Mage", "{W}{U}", 2, "Creature — Human Wizard", "As this creature enters, choose a nonland card name.\nSpells with the chosen name can't be cast.", ("2", "2"), "WU"),
    real("Pithing Needle", "{1}", 1, "Artifact", "As this artifact enters, choose a card name.\nActivated abilities of sources with the chosen name can't be activated unless they're mana abilities."),
    real("Phyrexian Revoker", "{2}", 2, "Artifact Creature — Phyrexian Horror", "As this creature enters, choose a nonland card name.\nActivated abilities of sources with the chosen name can't be activated.", ("2", "1")),
    real("Nevermore", "{1}{W}{W}", 3, "Enchantment", "As this enchantment enters, choose a nonland card name.\nSpells with the chosen name can't be cast.", None, "W"),
    real("Voidstone Gargoyle", "{3}{W}{W}", 5, "Creature — Gargoyle", "Flying\nAs this creature enters, choose a nonland card name.\nSpells with the chosen name can't be cast.\nActivated abilities of sources with the chosen name can't be activated.", ("3", "3"), "W"),
    real("Probe Bolt", "{R}", 1, "Instant", "Probe Bolt deals 1 damage to any target.", None, "R"),
    real("Probe Charm", "{G}", 1, "Instant", "You gain 1 life.", None, "G"),
    real("Probe Pinger", "{1}", 1, "Artifact", "{T}: Probe Pinger deals 1 damage to any target.\n{T}: Add {C}."),
    real("Probe Land", "", 0, "Land", "{T}: Add {R}."),
]
NAMES = ["Meddling Mage", "Pithing Needle", "Phyrexian Revoker", "Nevermore", "Voidstone Gargoyle"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def name_it(s, text, *, who="p1"):
    d = s.state.rules.decision
    assert d is not None and d.options[0].id == "__name__" and d.player == who
    act(s, who, type="choose", decision_id=d.id, name=text)


def cast_naming(s, name, text, pid="p1"):
    """Cast ``name`` (paid with mana added by hand), let it resolve, and name ``text``."""
    c = card_named(s, name, pid)
    act(s, pid, type="add_mana", player=pid, mana={"W": 3, "U": 1, "G": 3})
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    if s.state.rules.decision is not None:
        name_it(s, text, who=pid)
    return c


def test_meddling_mage_stops_that_name_for_everyone(cards):
    s = build(cards, ["Meddling Mage", "Probe Bolt", "Probe Charm"], ["Probe Bolt"])
    cast_naming(s, "Meddling Mage", "Probe Bolt")
    mage = card_named(s, "Meddling Mage")
    assert zone_of(s, "Meddling Mage") == "p1:battlefield"
    assert s.state.cards[mage.id].choices["Chosen card name"] == "Probe Bolt"
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1, "G": 1})
    bolt = to_hand(s, "Probe Bolt")
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Charm").id)  # another name: fine
    theirs = to_hand(s, "Probe Bolt", "p2")  # 601.3: Bob can't cast it either (his own priority isn't needed to ask)
    from app.rules import cast_limits, characteristics as chars

    assert "can't cast" in cast_limits.cast_problem(s.state, "p2", theirs, chars.of(theirs, s.cards), s.cards)
    check(s)


def test_a_name_must_be_a_real_card_and_fit_the_question(cards):
    s = build(cards, ["Meddling Mage"], [])
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1, "U": 1})
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Meddling Mage").id)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.options[0].group == "nonland card name"
    for bad in ("", "Not A Real Card", "Forest", "Fire // Ice", "Delver of Secrets // Insectile Aberration"):
        with pytest.raises(ActionError):
            act(s, "p1", type="choose", decision_id=d.id, name=bad)
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["__name__"])
    assert s.state.rules.decision is not None
    name_it(s, "ice")  # 201.4b: one half of a split card; the name is stored as the half's own
    assert s.state.cards[card_named(s, "Meddling Mage").id].choices["Chosen card name"] == "Ice"
    check(s)


def test_a_split_half_name_stops_that_half_only_on_the_stack(cards):
    s = build(cards, ["Meddling Mage", "Fire // Ice"], ["Fire // Ice"])
    cast_naming(s, "Meddling Mage", "Ice")
    fire_ice = to_hand(s, "Fire // Ice")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 2, "U": 2})
    with pytest.raises(ActionError, match="can't cast"):
        act(s, "p1", type="cast_spell", card_id=fire_ice.id, face=1, targets=["p2"])  # 709.4a: Ice is one of its names
    act(s, "p1", type="cast_spell", card_id=fire_ice.id, face=0, targets=["p2"])  # 709.3a: cast as Fire, it has only that name
    check(s)


def test_pithing_needle_stops_non_mana_abilities_only(cards):
    s = build(cards, ["Pithing Needle", "Probe Pinger"], [])
    pinger = put(s, "Probe Pinger")
    cast_naming(s, "Pithing Needle", "Probe Pinger")
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=pinger.id, ability=0, targets=["p2"])
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=1)  # 605.1a: its mana ability still works
    assert s.state.cards[pinger.id].tapped
    check(s)


def test_phyrexian_revoker_stops_mana_abilities_too(cards):
    s = build(cards, ["Phyrexian Revoker", "Probe Pinger"], [])
    pinger = put(s, "Probe Pinger")
    cast_naming(s, "Phyrexian Revoker", "Probe Pinger")
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=pinger.id, ability=1)
    check(s)


def test_the_choice_leaves_with_the_permanent(cards):
    s = build(cards, ["Nevermore", "Probe Bolt"], [])
    cast_naming(s, "Nevermore", "Probe Bolt")
    nm = card_named(s, "Nevermore")
    act(s, "p1", type="move", card_ids=[nm.id], to={"zone": "hand"})
    bolt = to_hand(s, "Probe Bolt")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # 400.7: the old object's choice is gone
    check(s)
