"""Wave 26D: counter wordings over existing machinery. Real Oracle text, replay and save/load for each.

* 614.1c / 614.12: "enters with N counters for each <group you control>" counts a battlefield group only when the entering
  permanent can't belong to it (it isn't on the battlefield while the count is read; the count here happens after the move).
* 702.51a, 601.2h: "each creature that convoked it" reads the spell's payment record (the creatures tapped for convoke).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests import test_rules_cost_contributions as cb
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches

EXTRA = [
    card('Ancient Imperiosaur', set_code='tst', number='W01', mana_cost='{5}{G}{G}', cmc=7.0, type_line='Creature — Dinosaur', oracle_text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nTrample, ward {2}\nThis creature enters with two +1/+1 counters on it for each creature that convoked it.", power='6', toughness='6', colors=['G'], color_identity=['G'], keywords=['Trample', 'Ward', 'Convoke'], layout='normal'),  # noqa: E501
    card('Venerated Loxodon', set_code='tst', number='W02', mana_cost='{4}{W}', cmc=5.0, type_line='Creature — Elephant Cleric', oracle_text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nWhen this creature enters, put a +1/+1 counter on each creature that convoked it.", power='4', toughness='4', colors=['W'], color_identity=['W'], keywords=['Convoke'], layout='normal'),  # noqa: E501
    card('Michelangelo, On the Scene', set_code='tst', number='W03', mana_cost='{4}{G}{G}', cmc=6.0, type_line='Legendary Creature — Mutant Ninja Turtle', oracle_text="Trample (This creature can deal excess combat damage to the player it's attacking.)\nMichelangelo enters with a +1/+1 counter on him for each land you control.\nWhen Michelangelo dies, return this card to your hand.", power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Trample'], layout='normal'),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    return GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)


def roundtrip(s):
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def counters(s, cid):
    return dict(s.state.cards[cid].counters)


def find(s, name):
    return next(c for c in s.state.cards.values() if c.name == name)


@pytest.mark.parametrize("name", FULL)
def test_supported(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def convoke_cast(cards, spell, creatures):
    s, card, made, _, _ = cb.build(cards, spell, creatures=creatures)
    cb.cast(s, card)
    for c in made:
        cb.commit(s, c, "convoke")
    return s, card, made


def settle(s):
    for _ in range(30):
        if s.state.rules.decision is not None:
            d = s.state.rules.decision
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id] if d.options else [])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def test_convoke_counters_for_each_creature(cards):
    # 702.51a, 614.1c: enters with two +1/+1 counters for each creature that convoked it (read from the payment record)
    s, card, made = convoke_cast(cards, "Ancient Imperiosaur", [[], [], []])
    d = s.state.rules.decision
    act(s, "p1", type="add_mana", player="p1", mana={"G": 4})
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert s.state.cards[card.id].zone == "p1:battlefield"
    assert counters(s, card.id) == {"+1/+1": 6}
    roundtrip(s)


def test_convoke_counters_on_each_convoker(cards):
    # "When this creature enters, put a +1/+1 counter on each creature that convoked it": only those creatures
    s, card, made = convoke_cast(cards, "Venerated Loxodon", [["W"], [], ["G"]])
    d = s.state.rules.decision
    act(s, "p1", type="create_token", player="p1", token={"name": "Bystander", "type_line": "Token Creature — Test", "power": "1", "toughness": "1"})
    act(s, "p1", type="add_mana", player="p1", mana={"W": 2})
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert s.state.cards[card.id].zone == "p1:battlefield"
    assert all(counters(s, c) == {"+1/+1": 1} for c in made)
    assert counters(s, card.id) == {} and counters(s, find(s, "Bystander").id) == {}
    roundtrip(s)


def test_enters_with_counters_per_land(cards):
    # "Michelangelo enters with a +1/+1 counter on him for each land you control": a creature isn't in that group (614.12)
    s = cb.build(cards, "Michelangelo, On the Scene")[0]
    mich = find(s, "Michelangelo, On the Scene")
    lands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p1:library"][:3]
    act(s, "p1", type="move", card_ids=lands, to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[mich.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana={"G": 6})
    act(s, "p1", type="cast_spell", card_id=mich.id)
    settle(s)
    assert s.state.cards[mich.id].zone == "p1:battlefield"
    assert counters(s, mich.id) == {"+1/+1": 3}
    roundtrip(s)
