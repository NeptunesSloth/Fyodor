"""Wave 23B: delayed triggers and payloads (CR 603.7), researched against the stored Comprehensive Rules.

* The Pacts (603.7a, 118.12a): "At the beginning of your next upkeep, pay {X}. If you don't, you lose the game." is a paragraph of
  the instant (the delayed trigger is created as the spell resolves) read as "you lose the game unless you pay {X}": the payer is the
  delayed trigger's controller, deciding as it resolves; PAY only while the whole cost is payable (118.3).
Every scenario checks that the recorded history replays to the same table (also with a prompt pending) and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_costs_components import choose, decision
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_suspend import until
from tests.test_rules_wave9b_exile_permission import build, put, roundtrip

EXTRA = [
    card('Pact of the Titan', set_code='tst', number='D01', mana_cost='{0}', cmc=0.0, type_line='Instant', oracle_text="Create a 4/4 red Giant creature token.\nAt the beginning of your next upkeep, pay {4}{R}. If you don't, you lose the game.", colors=['R'], color_identity=['R']),  # noqa: E501
    card('Pact of Negation', set_code='tst', number='D02', mana_cost='{0}', cmc=0.0, type_line='Instant', oracle_text="Counter target spell.\nAt the beginning of your next upkeep, pay {3}{U}{U}. If you don't, you lose the game.", colors=['U'], color_identity=['U']),  # noqa: E501
    card("Summoner's Pact", set_code='tst', number='D03', mana_cost='{0}', cmc=0.0, type_line='Instant', oracle_text="Search your library for a green creature card, reveal it, put it into your hand, then shuffle.\nAt the beginning of your next upkeep, pay {2}{G}{G}. If you don't, you lose the game.", colors=['G'], color_identity=['G']),  # noqa: E501
    card('Slaughter Pact', set_code='tst', number='D04', mana_cost='{0}', cmc=0.0, type_line='Instant', oracle_text="Destroy target nonblack creature.\nAt the beginning of your next upkeep, pay {2}{B}. If you don't, you lose the game.", colors=['B'], color_identity=['B']),  # noqa: E501
    card('Intervention Pact', set_code='tst', number='D05', mana_cost='{0}', cmc=0.0, type_line='Instant', oracle_text="The next time a source of your choice would deal damage to you this turn, prevent that damage. You gain life equal to the damage prevented this way.\nAt the beginning of your next upkeep, pay {1}{W}{W}. If you don't, you lose the game.", colors=['W'], color_identity=['W']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def rules(s):
    return s.state.rules


def parsed(text):
    found = scripts.parse_effects(text)
    return found[0] if found else None


def to_upkeep(s, pid):
    """On to the beginning of ``pid``'s next upkeep, stopping at a decision."""
    until(s, lambda s: decision(s) is not None or (s.state.turn.phase == "upkeep" and s.state.turn.active_player == pid), limit=80)


# -- the Pacts ----------------------------------------------------------------------------------
PACT = "At the beginning of your next upkeep, pay {4}{R}. If you don't, you lose the game."


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_the_pacts_are_automated(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_pact_wording():
    effects = parsed(PACT)
    assert [e["do"] for e in effects] == ["delayed", "deferred:optional_payment", "deferred:only_if", "deferred:lose_game"]
    assert effects[0]["when"] == {"kind": "step", "step": "upkeep", "whose": "you"} and effects[0]["n"] == 3
    assert effects[1]["who"] == "you" and effects[1]["cost"] == "{4}{R}"
    assert parsed("At the beginning of your next upkeep, pay {4}{R}. If you don't, you lose 5 life.") is None  # (not read)


def cast_pact(cards):
    s = build(cards, p1=("Pact of the Titan",))
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    pact = put(s, "Pact of the Titan", "hand")
    act(s, "p1", type="cast_spell", card_id=pact.id)
    pass_until_stack_empty(s)
    return s


def test_pact_pay_and_survive(cards):
    s = cast_pact(cards)
    (t,) = rules(s).delayed
    assert t.controller == "p1" and t.when["whose"] == "you"
    roundtrip(s)  # (saved and loaded with the delayed trigger waiting)
    to_upkeep(s, "p1")
    assert len(s.state.zones["stack"]) == 1  # (the delayed trigger, 603.7)
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1, "C": 4})
    pass_until_stack_empty(s)
    d = decision(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]
    assert "options" not in s.view("p2")["rules"]["decision"]  # (the payer's decision)
    roundtrip(s)  # (also with the prompt pending)
    choose(s, ["pay"])
    assert "p1" not in rules(s).lost and not rules(s).delayed
    roundtrip(s)


def test_pact_decline_loses_the_game(cards):
    s = cast_pact(cards)
    to_upkeep(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1, "C": 4})
    pass_until_stack_empty(s)
    choose(s, ["decline"])
    assert "p1" in rules(s).lost
    roundtrip(s)


def test_pact_unpayable_loses_without_a_choice(cards):
    s = cast_pact(cards)
    to_upkeep(s, "p1")
    pass_until_stack_empty(s)  # (118.3: PAY isn't offered without the mana, so there is nothing to decide)
    assert "p1" in rules(s).lost
    roundtrip(s)


def test_pact_waits_for_its_controllers_upkeep(cards):
    s = cast_pact(cards)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "upkeep", limit=80)
    pass_until_stack_empty(s)
    assert decision(s) is None and "p1" not in rules(s).lost and len(rules(s).delayed) == 1


# -- payloads: a token / a draw / a sacrifice at a later step (603.7) ---------------------------------------------------
PAYLOADS = [
    card('Barbed Sextant', set_code='tst', number='D10', mana_cost='{1}', cmc=1.0, type_line='Artifact', oracle_text="{1}, {T}, Sacrifice this artifact: Add one mana of any color. Draw a card at the beginning of the next turn's upkeep."),  # noqa: E501
    card('Celestial Sword', set_code='tst', number='D11', mana_cost='{6}', cmc=6.0, type_line='Artifact', oracle_text='{3}, {T}: Target creature you control gets +3/+3 until end of turn. Its controller sacrifices it at the beginning of the next end step.'),  # noqa: E501
    card('Transluminant', set_code='tst', number='D12', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Dryad Shaman', oracle_text='{W}, Sacrifice this creature: Create a 1/1 white Spirit creature token with flying at the beginning of the next end step.', power='2', toughness='2', colors=['G'], color_identity=['G', 'W']),  # noqa: E501
    card('Test Ox', set_code='tst', number='D13', mana_cost='{2}', cmc=2.0, type_line='Creature — Ox', oracle_text='', power='3', toughness='3'),  # noqa: E501
]
EXTRA += PAYLOADS


@pytest.mark.parametrize("name", [c["name"] for c in PAYLOADS if c["name"] != "Test Ox"])
def test_payload_cards_are_automated(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_barbed_sextant_adds_mana_and_draws_at_the_next_upkeep(cards):
    s = build(cards, p1=("Barbed Sextant",))
    sextant = put(s, "Barbed Sextant", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=sextant.id, ability=0)  # a mana ability: no stack (605.3b)
    act(s, "p1", type="choose", decision_id=rules(s).decision.id, option_ids=["3"])  # {R}
    from tests.game_helpers import mana_pool

    assert mana_pool(s) == {"R": 1}  # ({1} paid with the {C}; known-source mana retains provenance)
    assert s.state.cards[sextant.id].zone.endswith(":graveyard")
    (t,) = rules(s).delayed
    assert t.when == {"kind": "step", "step": "upkeep", "whose": "next_turn"} and t.controller == "p1"
    roundtrip(s)  # (saved and loaded with the delayed trigger waiting)
    hand = len(s.state.zones.get("p1:hand", []))
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "upkeep")
    assert len(s.state.zones["stack"]) == 1  # (the delayed trigger, at the beginning of the next turn's upkeep)
    pass_until_stack_empty(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1 and not rules(s).delayed  # (the next turn's upkeep: the opponent's)
    roundtrip(s)


def test_transluminant_makes_the_token_at_the_end_step(cards):
    s = build(cards, p1=("Transluminant",))
    t = put(s, "Transluminant", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0)
    pass_until_stack_empty(s)
    assert s.state.cards[t.id].zone.endswith(":graveyard")
    assert not [c for c in s.state.cards.values() if c.is_token and c.name == "Spirit"]  # (not yet: 603.7a)
    (d,) = rules(s).delayed
    assert d.when == {"kind": "step", "step": "end", "whose": "next"}
    roundtrip(s)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    until(s, lambda s: any(c.is_token and c.name == "Spirit" for c in s.state.cards.values()))
    spirit = next(c for c in s.state.cards.values() if c.is_token and c.name == "Spirit")
    assert spirit.zone == "p1:battlefield" and s.state.turn.phase == "end"
    roundtrip(s)


def test_celestial_sword_pump_then_the_controller_sacrifices_it(cards):
    s = build(cards, p1=("Celestial Sword", "Test Ox"))
    sword = put(s, "Celestial Sword", "battlefield")
    ox = put(s, "Test Ox", "battlefield")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    act(s, "p1", type="activate_ability", card_id=sword.id, ability=0, targets=[ox.id])
    pass_until_stack_empty(s)
    assert s.state.cards[ox.id].zone == "p1:battlefield" and len(rules(s).delayed) == 1
    roundtrip(s)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    until(s, lambda s: s.state.cards[ox.id].zone.endswith(":graveyard") or s.state.turn.number > 1)
    assert s.state.cards[ox.id].zone == "p1:graveyard" and s.state.turn.number == 1 and s.state.turn.phase == "end"  # (601.2: this turn's end step)
    roundtrip(s)
