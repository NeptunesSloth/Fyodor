"""Wave 20E: control change. Real Oracle text; every scenario checks the replay and a save and a load.

* 613.1b / 608.2c: "Gain control of all artifacts and creatures target opponent controls." (Tezzeret, Master of Metal; Ashiok, Sculptor of
  Fears: "… all creatures target opponent controls.") - the permanents that player controls as the ability resolves, for good.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, cast, check, mana, put, to_hand

EXTRA = [
    real('Probe Heist', '{1}', 1, 'Sorcery', 'Gain control of all artifacts and creatures target opponent controls.', None),
    real('Probe Soldier', '{1}{W}', 2, 'Creature — Human Soldier', '', ("1", "1"), 'W'),
    real('Probe Rock', '{3}', 3, 'Artifact', '', None),
    real('Probe Land', '', 0, 'Land', '', None),
    card("Plains", set_code="cmm", number="1005", type_line="Basic Land — Plains", oracle_text="({T}: Add {W}.)", color_identity=["W"]),
    real('Dominating Vampire', '{2}{R}{R}', 4, 'Creature — Vampire', 'When this creature enters, gain control of target creature with mana value less than or equal to the number of Vampires you control until end of turn. Untap that creature. It gains haste until end of turn.', ("3", "3"), 'R'),
    real('Kenku Artificer', '{2}{U}', 3, 'Creature — Bird Artificer', 'Homunculus Servant — When this creature enters, put three +1/+1 counters on up to one target noncreature artifact. That artifact becomes a 0/0 Homunculus artifact creature with flying.', ("2", "2"), 'U'),
    real('Lay Down Arms', '{W}', 1, 'Sorcery', 'Exile target creature with mana value less than or equal to the number of Plains you control. Its controller gains 3 life.', None, 'W'),
    real('Probe Thrull', '{B}', 1, 'Creature — Thrull', '', ("1", "1"), 'B'),
    real('Probe Giant', '{5}', 5, 'Creature — Giant', '', ("5", "5")),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Probe Heist"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_all_artifacts_and_creatures_the_opponent_controls(cards):
    s = build(cards, ["Probe Heist"], ["Probe Soldier", "Probe Rock", "Probe Land"])
    soldier, rock = put(s, "Probe Soldier", "p2"), put(s, "Probe Rock", "p2")
    land = card_named(s, "Forest")  # (Alice's own: not touched)
    heist = to_hand(s, "Probe Heist")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1})
    act(s, "p1", type="cast_spell", card_id=heist.id, targets=["p2"])
    for _ in range(10):
        if not s.state.rules.stack:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[soldier.id].controller == "p1" and s.state.cards[rock.id].controller == "p1"
    assert s.state.cards[soldier.id].owner == "p2" and land.owner == "p1"
    check(s)


def test_a_target_with_mana_value_up_to_the_number_of_vampires_you_control(cards):
    """608.2c / 115.1: one Vampire (itself) is controlled, so only a creature with mana value 1 or less is a legal target."""
    s = build(cards, ["Dominating Vampire"], ["Probe Thrull", "Probe Giant"])
    thrull, giant = put(s, "Probe Thrull", "p2"), put(s, "Probe Giant", "p2")
    to_hand(s, "Dominating Vampire")
    mana(s, "p1", R=2, C=2)
    cast(s, "Dominating Vampire")  # (the Thrull is the only legal target: chosen as the trigger goes on the stack, 603.3d)
    assert s.state.cards[thrull.id].controller == "p1" and s.state.cards[giant.id].controller == "p2"
    check(s)


def test_that_artifact_is_the_noncreature_artifact_that_was_targeted(cards):
    """"That artifact becomes a 0/0 Homunculus artifact creature with flying" after the three counters (611.2c: it stays so)."""
    from app.rules.plan import Plan

    s = build(cards, ["Kenku Artificer", "Probe Rock"], [])
    rock = put(s, "Probe Rock")
    to_hand(s, "Kenku Artificer")
    mana(s, "p1", U=1, C=2)
    cast(s, "Kenku Artificer")
    card = s.state.cards[rock.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(card)
    assert card.counters.get("+1/+1") == 3 and "Creature" in ch.types and "Homunculus" in ch.subtypes and "flying" in ch.keywords
    assert ch.pt == (3, 3)
    check(s)


@pytest.mark.parametrize("plains,gone", [(1, False), (2, True)])
def test_exile_a_creature_with_mana_value_up_to_the_plains_you_control(cards, plains, gone):
    s = build(cards, ["Lay Down Arms", "Plains", "Plains"], ["Probe Soldier"], forests=0, islands=0)
    soldier = put(s, "Probe Soldier", "p2")
    for c in [c for c in s.state.cards.values() if c.name == "Plains" and c.owner == "p1"][:plains]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    to_hand(s, "Lay Down Arms")
    mana(s, "p1", W=1)
    arms = card_named(s, "Lay Down Arms")
    if gone:
        act(s, "p1", type="cast_spell", card_id=arms.id, targets=[soldier.id])
        for _ in range(5):
            if not s.state.rules.stack:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert s.state.cards[soldier.id].zone == "p2:exile"
    else:
        with pytest.raises(ActionError):  # (mana value 2 is more than the one Plains)
            act(s, "p1", type="cast_spell", card_id=arms.id, targets=[soldier.id])
    check(s)
