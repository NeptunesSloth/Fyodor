"""Wave 27D: activated abilities that work from the hand or the command zone (CR 2026-09-25). Real Oracle text; every scenario checks
the replay and a save and a load.

* 113.6m: an ability whose effect moves its own object out of a zone works only in that zone: "Put this card from your hand onto the
  battlefield." (Talon Gates of Madara, Urban Retreat) from the hand, "Put Derevi onto the battlefield from the command zone." from there.
* 602.2 / 601.2h: the ability is activated and its costs paid (a mana cost, "Return a tapped creature you control to its owner's hand"),
  then it goes on the stack; the card is put onto the battlefield as the ability resolves (400.7: only if it is still that object there).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.casting import activatable
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

REAL = [
    ("Talon Gates of Madara", "", "Land", None, None,
     "{T}: Add {C}.\n{T}: Add one mana of any color. Activate only if you've cast a spell this turn.\n{4}: Put this card from your hand onto the battlefield."),
    ("Urban Retreat", "", "Land", None, None,
     "{T}: Add {G}.\n{2}, Return a tapped creature you control to its owner's hand: Put this card from your hand onto the battlefield. Activate only as a sorcery."),
    ("Derevi, Empyrial Tactician", "{G}{W}{U}", "Legendary Creature — Bird Shaman", "2", "3",
     "Flying\nWhen Derevi enters or a creature you control deals combat damage to a player, untap target permanent.\n"
     "{1}{G}{W}{U}: Put Derevi onto the battlefield from the command zone."),
]
EXTRA = [card(n, set_code="t27d", number=f"T{i:02d}", mana_cost=mc, cmc=float(len(mc.replace("{", "").split("}")) - 1), type_line=tl,
              colors=["G"], color_identity=["G"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [r[0] for r in REAL])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def listed(s, card_id):
    return [a["ability"] for a in activatable(s.state, "p1", s.cards) if a["card_id"] == card_id]


def run(s):
    settle(s)
    while s.state.zones.get("stack"):
        act(s, "p1", type="pass_priority")
        act(s, "p2", type="pass_priority")
        settle(s)


def test_talon_gates_enter_from_the_hand(cards):
    s = build(cards, ["Talon Gates of Madara"])
    gates = to_hand(s, "Talon Gates of Madara")
    assert listed(s, gates.id) == []  # (no mana)
    mana(s, C=4)
    assert listed(s, gates.id) == [2]
    act(s, "p1", type="activate_ability", card_id=gates.id, ability=2)
    run(s)
    assert zone_of(s, "Talon Gates of Madara") == "p1:battlefield"
    assert s.state.players["p1"].mana == {}
    check(s)


def test_talon_gates_only_from_the_hand(cards):
    s = build(cards, ["Talon Gates of Madara"])
    gates = put(s, "Talon Gates of Madara")
    mana(s, C=4)
    assert 2 not in listed(s, gates.id)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=gates.id, ability=2)
    check(s)


def test_urban_retreat_returns_a_tapped_creature_as_a_cost(cards):
    s = build(cards, ["Urban Retreat", "Llanowar Elves"])
    retreat = to_hand(s, "Urban Retreat")
    bear = put(s, "Llanowar Elves")
    mana(s, C=2)
    assert listed(s, retreat.id) == []  # (no tapped creature to return)
    act(s, "p1", type="tap", card_ids=[bear.id], tapped=True)
    assert listed(s, retreat.id) == [1]
    act(s, "p1", type="activate_ability", card_id=retreat.id, ability=1)
    assert s.state.cards[bear.id].zone == "p1:hand"  # paid as the cost
    run(s)
    assert zone_of(s, "Urban Retreat") == "p1:battlefield"
    check(s)


def test_derevi_from_the_command_zone(cards):
    p1 = deck(cards, "Derevi, Empyrial Tactician", [(10, "Forest")])
    p2 = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=p1), PlayerSetup("Bob", cards=p2)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    derevi = card_named(s, "Derevi, Empyrial Tactician")
    assert derevi.zone == "p1:command"
    assert listed(s, derevi.id) == []
    mana(s, G=1, W=1, U=1, C=1)
    assert listed(s, derevi.id) == [2]
    act(s, "p1", type="activate_ability", card_id=derevi.id, ability=2)
    run(s)
    assert zone_of(s, "Derevi, Empyrial Tactician") == "p1:battlefield"
    check(s)


def test_derevi_not_from_the_hand(cards):
    s = build(cards, ["Derevi, Empyrial Tactician"])
    derevi = to_hand(s, "Derevi, Empyrial Tactician")
    mana(s, G=1, W=1, U=1, C=1)
    assert listed(s, derevi.id) == []
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=derevi.id, ability=2)
