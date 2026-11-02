"""The pod's Silverquill, the Disputant deck (tests/fixtures/soak_decks/silverquill_draf.txt): its plan, with real Oracle text.

Silverquill gives each instant and sorcery spell Alice casts casualty 1 (702.153a): as she casts it she may sacrifice a creature with power 1
or greater, and then a cast trigger copies the spell, with new targets if she likes (707.10: the copy keeps the modes, X, the overload and the
spree costs chosen for the original). The sacrifice feeds the deck's death payoffs (Grave Pact, Bastion of Remembrance), Twinning Staff adds a
copy to each copy (one more each time), and Sedgemoor Witch makes a Pest for the cast and one for each copy (magecraft).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.view import hints, rules_view
from tests.fixtures.cards import card as fixture_card
from tests.game_helpers import act
from tests.pod_c_kit import card, field, hold, mana, put, settle, table, to_hand
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

SILVERQUILL = "Silverquill, the Disputant"
EXTRA = [
    real('Silverquill, the Disputant', '{2}{W}{B}', 4, 'Legendary Creature — Elder Dragon',
         'Flying, vigilance\nEach instant and sorcery spell you cast has casualty 1. (As you cast that spell, you may sacrifice a creature with '
         'power 1 or greater. When you do, copy the spell and you may choose new targets for the copy.)', ('4', '4'), 'BW'),
    real('Troubling Tribbles', '{2}{W}', 3, 'Creature — Tribble',
         "This creature can't block.\nAt the beginning of your upkeep, create a token that's a copy of this creature.", ('0', '1'), 'W'),
    real('Twinning Staff', '{3}', 3, 'Artifact',
         'If you would copy a spell one or more times, instead copy it that many times plus an additional time. You may choose new targets for '
         'the additional copy.\n{7}, {T}: Copy target instant or sorcery spell you control. You may choose new targets for the copy.'),
    real('Sedgemoor Witch', '{2}{B}', 3, 'Creature — Human Warlock',
         'Menace\nWard—Pay 3 life. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless '
         'that player pays 3 life.)\nMagecraft — Whenever you cast or copy an instant or sorcery spell, create a 1/1 black and green Pest '
         'creature token with "When this token dies, you gain 1 life."', ('3', '2'), 'B'),
    real('Grave Pact', '{1}{B}{B}{B}', 4, 'Enchantment',
         'Whenever a creature you control dies, each other player sacrifices a creature of their choice.', None, 'B'),
    real('Bastion of Remembrance', '{2}{B}', 3, 'Enchantment',
         'When this enchantment enters, create a 1/1 white Human Soldier creature token.\nWhenever a creature you control dies, each opponent '
         'loses 1 life and you gain 1 life.', None, 'B'),
    real('Duty Beyond Death', '{1}{W}', 2, 'Instant',
         'As an additional cost to cast this spell, sacrifice a creature.\nCreatures you control gain indestructible until end of turn. Put a '
         '+1/+1 counter on each creature you control. (Damage and effects that say "destroy" don\'t destroy those creatures.)', None, 'W'),
    real('Exsanguinate', '{X}{B}{B}', 2, 'Sorcery', 'Each opponent loses X life. You gain life equal to the life lost this way.', None, 'B'),
    real('Will of the Mardu', '{2}{W}', 3, 'Instant',
         'Choose one. If you control a commander as you cast this spell, you may choose both instead.\n• Create a number of 1/1 red Warrior '
         'creature tokens equal to the number of creatures target player controls.\n• Will of the Mardu deals damage to target creature equal '
         'to the number of creatures you control.', None, 'W'),
    real('Damn', '{B}{B}', 2, 'Sorcery',
         'Destroy target creature. A creature destroyed this way can\'t be regenerated.\nOverload {2}{W}{W} (You may cast this spell for its '
         'overload cost. If you do, change "target" in its text to "each.")', None, 'BW'),
    real('Temporal Extortion', '{B}{B}{B}{B}', 4, 'Sorcery',
         'When you cast this spell, any player may pay half their life, rounded up. If a player does, counter Temporal Extortion.\nTake an '
         'extra turn after this one.', None, 'B'),
    real('Crypt Ghast', '{3}{B}', 4, 'Creature — Spirit',
         'Extort (Whenever you cast a spell, you may pay {W/B}. If you do, each opponent loses 1 life and you gain that much life.)\nWhenever '
         'you tap a Swamp for mana, add an additional {B}.', ('2', '2'), 'B'),
    real('Mondrak, Glory Dominus', '{2}{W}{W}', 4, 'Legendary Creature — Phyrexian Horror',
         'If one or more tokens would be created under your control, twice that many of those tokens are created instead.\n{1}{W/P}{W/P}, '
         'Sacrifice two other artifacts and/or creatures: Put an indestructible counter on Mondrak. ({W/P} can be paid with either {W} or 2 '
         'life.)', ('4', '4'), 'W'),
    fixture_card('Revival // Revenge', number="pod-revival", layout="split", mana_cost="{W/B}{W/B} // {4}{W}{B}", cmc=8.0,
                 type_line="Sorcery // Sorcery", colors=["B", "W"], color_identity=["B", "W"],
                 card_faces=[
                     {"object": "card_face", "name": "Revival", "mana_cost": "{W/B}{W/B}", "type_line": "Sorcery",
                      "oracle_text": "Return target creature card with mana value 3 or less from your graveyard to the battlefield."},
                     {"object": "card_face", "name": "Revenge", "mana_cost": "{4}{W}{B}", "type_line": "Sorcery",
                      "oracle_text": "Double your life total. Target opponent loses half their life, rounded up."}]),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def silverquill(cards, *mine, theirs=()):
    s = table(cards, mine, theirs, commander=SILVERQUILL, lands=("Swamp", 10))
    put(s, SILVERQUILL)
    return s


def casualty(s, name: str, **kw):
    """Cast ``name`` from the hand paying its casualty cost (the hint's "Cast and sacrifice a creature with power 1 or greater")."""
    spell = to_hand(s, name)
    act(s, "p1", type="cast_spell", card_id=spell.id, optional_costs=[f"{spell.id}:casualty"], **kw)
    return spell


def test_casualty_is_offered_for_instants_and_sorceries_with_a_creature_of_power_one(cards):
    """702.153a: a creature with power 0 (Troubling Tribbles) can't pay it; a creature spell has no casualty."""
    s = silverquill(cards, "Swords to Plowshares", "Troubling Tribbles", "Grizzly Bears", theirs=["Albino Troll"])
    swords, bears = to_hand(s, "Swords to Plowshares"), to_hand(s, "Grizzly Bears")
    mana(s, W=1, G=2)
    offered = lambda: hints(s.state, "p1", s.cards).get("optional_costs", {})  # noqa: E731
    assert offered()[swords.id] == [{"id": f"{swords.id}:casualty", "label": "Casualty 1: sacrifice a creature with power 1 or greater"}]
    assert bears.id not in offered()
    act(s, "p1", type="move", card_ids=[card(s, SILVERQUILL).id], to={"zone": "command"})
    put(s, "Troubling Tribbles")
    assert swords.id not in offered()  # (Tribbles has power 0: nothing can pay it)
    check(s)


def test_casualty_copies_swords_to_plowshares_onto_a_new_target(cards):
    """Alice picks the creature to sacrifice (power 1 or greater: not Tribbles), then the copy's new target: both of Bob's creatures go."""
    s = silverquill(cards, "Swords to Plowshares", "Troubling Tribbles", "Raise the Alarm", theirs=["Grizzly Bears", "Albino Troll"])
    bears = put(s, "Grizzly Bears", "p2")
    put(s, "Albino Troll", "p2")
    put(s, "Troubling Tribbles")
    mana(s, W=3, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Raise the Alarm").id)
    settle(s)
    casualty(s, "Swords to Plowshares", targets=[bears.id])
    d = s.state.rules.decision
    assert d.prompt.startswith("Swords to Plowshares: choose 1 to sacrifice") and sorted(o.label for o in d.options) == [
        "Silverquill, the Disputant", "Soldier", "Soldier"]
    asked = settle(s, "Soldier", "Albino Troll")
    assert any(p.startswith("Copy of Swords to Plowshares: keep its target") for p in asked)
    assert field(s, "p2") == {} and s.state.players["p2"].life == 40 + 2 + 3
    assert field(s)["Soldier"] == 1 and field(s)["Troubling Tribbles"] == 1
    check(s)


def test_twinning_staff_adds_a_copy_and_the_witch_and_grave_pact_see_it_all(cards):
    """The casualty copy is two copies with Twinning Staff (three Raise the Alarms: six Soldiers); Sedgemoor Witch makes a Pest for the cast
    and one for each copy; the sacrificed Grizzly Bears makes Bob sacrifice a creature (Grave Pact) and drains him (Bastion)."""
    s = silverquill(cards, "Twinning Staff", "Sedgemoor Witch", "Raise the Alarm", "Grizzly Bears", "Grave Pact", "Bastion of Remembrance",
                    theirs=["Albino Troll"])
    for name in ("Twinning Staff", "Sedgemoor Witch", "Grave Pact", "Bastion of Remembrance", "Grizzly Bears"):
        put(s, name)
    settle(s)
    put(s, "Albino Troll", "p2")
    mana(s, W=2)
    casualty(s, "Raise the Alarm")
    settle(s, "Grizzly Bears")
    assert field(s)["Soldier"] == 2 * 3 and field(s)["Pest"] == 3 and field(s)["Grizzly Bears"] == 0
    assert field(s, "p2") == {} and s.state.players["p2"].life == 39 and s.state.players["p1"].life == 41
    check(s)


def test_duty_beyond_death_sacrifices_twice_and_counts_twice(cards):
    """The additional cost and the casualty cost are two sacrifices of two creatures; the copy puts a second counter on Silverquill."""
    s = silverquill(cards, "Duty Beyond Death", "Grizzly Bears", "Albino Troll")
    put(s, "Grizzly Bears"), put(s, "Albino Troll")
    mana(s, W=2)
    casualty(s, "Duty Beyond Death")
    settle(s, "Grizzly Bears", "Albino Troll")
    assert field(s) == {SILVERQUILL: 1} and s.state.cards[card(s, SILVERQUILL).id].counters == {"+1/+1": 2}
    check(s)


def test_exsanguinate_copy_keeps_x(cards):
    """707.10: the copy has the X of the original (3): Bob loses 6, Alice gains 6."""
    s = silverquill(cards, "Exsanguinate", "Grizzly Bears")
    put(s, "Grizzly Bears")
    mana(s, B=5)
    casualty(s, "Exsanguinate", x_value=3)
    settle(s, "Grizzly Bears")
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (46, 34)
    check(s)


def test_will_of_the_mardu_copy_keeps_both_modes_and_takes_a_new_creature(cards):
    """With a commander on the battlefield both modes are chosen (700.2); the copy keeps them (707.10) and its damage goes to another of Bob's
    creatures."""
    s = silverquill(cards, "Will of the Mardu", "Grizzly Bears", theirs=["Albino Troll", "Llanowar Elves", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    troll, elves = put(s, "Albino Troll", "p2"), put(s, "Llanowar Elves", "p2")
    put(s, "Grizzly Bears", "p2")
    mana(s, W=3)
    casualty(s, "Will of the Mardu", modes=[0, 1], targets=["p2", troll.id])
    settle(s, "Grizzly Bears", "Keep Bob", "Llanowar Elves")
    assert s.state.cards[elves.id].zone == "p2:graveyard"
    assert field(s)["Warrior"] == 3 + 2  # (the copy resolves first: Bob had three creatures, then two)
    check(s)


def test_damn_overloaded_copy_is_overloaded_too(cards):
    """707.10: the copy of an overloaded Damn destroys each creature as well (Silverquill too)."""
    s = silverquill(cards, "Damn", "Grizzly Bears", theirs=["Albino Troll"])
    put(s, "Grizzly Bears"), put(s, "Albino Troll", "p2")
    damn = to_hand(s, "Damn")
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=damn.id, alt_cost=f"{damn.id}:1", optional_costs=[f"{damn.id}:casualty"])
    settle(s, "Grizzly Bears", "Command zone")
    assert field(s) == {} and field(s, "p2") == {}
    check(s)


def test_revenge_is_cast_when_revival_has_no_target(cards):
    """709.3a: the hint lists Revival // Revenge as castable for its second half; a cast that names no half was always read as Revival and
    refused ("Revival has no legal target"), so Revenge could never be cast from the hand. With casualty, Alice's life doubles twice and Bob's
    halves twice."""
    s = silverquill(cards, "Revival // Revenge", "Grizzly Bears")
    put(s, "Grizzly Bears")
    split = to_hand(s, "Revival // Revenge")
    mana(s, W=3, B=3)
    offered = hints(s.state, "p1", s.cards)
    assert split.id in offered["castable"]
    assert [o["face"] for o in offered["optional_costs"][split.id]] == [1]  # (the casualty cost for Revenge only: Revival has no target)
    act(s, "p1", type="cast_spell", card_id=split.id, optional_costs=[f"{split.id}:casualty"])
    settle(s, "Grizzly Bears")
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (160, 10)
    check(s)


def test_split_card_offers_casualty_for_each_half_it_can_cast(cards):
    """With a creature card for Revival in the graveyard, both halves can be cast: each half's casualty is offered with its half, and the
    named half is the one cast. The sacrificed Albino Troll is in the graveyard by the time the copy is made, so the copy returns it (707.10c)."""
    s = silverquill(cards, "Revival // Revenge", "Grizzly Bears", "Albino Troll")
    put(s, "Albino Troll")
    act(s, "p1", type="move", card_ids=[card(s, "Grizzly Bears").id], to={"zone": "graveyard"})
    split = to_hand(s, "Revival // Revenge")
    mana(s, W=3, B=3)
    assert [o["face"] for o in hints(s.state, "p1", s.cards)["optional_costs"][split.id]] == [0, 1]
    act(s, "p1", type="cast_spell", card_id=split.id, face=0, optional_costs=[f"{split.id}:casualty"])
    asked = settle(s, "Albino Troll", "Albino Troll")
    assert any(p.startswith("Copy of Revival: keep its target") for p in asked)
    assert field(s)["Grizzly Bears"] == 1 and field(s)["Albino Troll"] == 1 and s.state.players["p1"].life == 40
    check(s)


def test_temporal_extortion_copy_takes_a_turn_and_the_order_prompt_says_which_trigger_is_which(cards):
    """The casualty copy and the "any player may pay" trigger share a source: the order prompt read "Temporal Extortion: Storm" and
    "Temporal Extortion: Each_may". The copy isn't cast (707.10): no second "may pay" trigger and no second extort (Crypt Ghast). Nobody pays:
    two extra turns."""
    s = silverquill(cards, "Temporal Extortion", "Grizzly Bears", "Crypt Ghast")
    put(s, "Grizzly Bears"), put(s, "Crypt Ghast")
    mana(s, B=5)
    casualty(s, "Temporal Extortion")
    settle(s, "Grizzly Bears", stop_at="Order your triggered abilities")
    d = s.state.rules.decision
    assert sorted(o.label for o in d.options) == ["Crypt Ghast", "Temporal Extortion: Any player may pay half their life rounded up",
                                                  "Temporal Extortion: Copy it"]
    asked = settle(s, "Don't pay", "Don't pay", "Don't pay")
    assert sum(p.startswith("Crypt Ghast") for p in asked) == 1 and sum(p.startswith("Temporal Extortion: pay half") for p in asked) == 2
    assert len(s.state.rules.extra_turns) == 2 and s.state.players["p2"].life == 40
    check(s)


def test_mondraks_sacrifice_two_tells_the_table_it_takes_both(cards):
    """Soak seed 5102: "Sacrifice two other artifacts and/or creatures" is chosen as none (cancel) or exactly two (601.2h); the decision said
    0 to 2, so the table let a player confirm one, and the server refused it ("Choose 2"). It now carries the exact count for the client.
    Mondrak doubles the Soldier tokens."""
    s = silverquill(cards, "Mondrak, Glory Dominus", "Raise the Alarm", "Grizzly Bears")
    mondrak = put(s, "Mondrak, Glory Dominus")
    put(s, "Grizzly Bears")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Raise the Alarm").id)
    settle(s)
    assert field(s)["Soldier"] == 4
    mana(s, W=3)
    act(s, "p1", type="activate_ability", card_id=mondrak.id, ability=1)
    d = s.state.rules.decision
    assert (d.min_choices, d.max_choices, d.display) == (0, 2, {"exactly": 2})
    view = rules_view(s.state, "p1", s.cards)["decision"]
    assert view["display"] == {"exactly": 2} and "display" not in (rules_view(s.state, "p2", s.cards)["decision"] or {})
    soldiers = [o.id for o in d.options if o.label == "Soldier"]
    with pytest.raises(ActionError, match="Choose 2"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=soldiers[:1])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=soldiers[:2])
    settle(s, "{W}", "{W}")
    assert s.state.cards[mondrak.id].counters.get("indestructible") == 1 and field(s)["Soldier"] == 2
    check(s)


def test_casualty_is_offered_only_when_the_spell_has_a_target(cards):
    """Soak (seed 5201): with an empty stack the table offered "Cast Reprieve and sacrifice …", and the server refused it (601.2c: a
    required target can't be chosen, 601.5). The optional-cost hint makes the same target check as the plain cast."""
    s = silverquill(cards, "Counterspell", "Raise the Alarm", "Grizzly Bears")
    put(s, "Grizzly Bears")
    counter = to_hand(s, "Counterspell")
    hold(s)
    mana(s, U=2)
    offered = lambda: hints(s.state, "p1", s.cards).get("optional_costs", {})  # noqa: E731
    assert counter.id not in hints(s.state, "p1", s.cards)["castable"]
    assert counter.id not in offered()  # (nothing to counter)
    act(s, "p1", type="clear_mana", player="p1")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Raise the Alarm").id)
    mana(s, U=2)
    assert s.state.rules.decision is None and [s.state.cards[i].name for i in s.state.zones["stack"]] == ["Raise the Alarm"]
    assert counter.id in offered()  # (Raise the Alarm is on the stack)
    check(s)


def test_twinning_staff_asks_which_copy_goes_first_only_when_the_spell_has_targets(cards):
    """Twinning Staff's additional copy differs from the others only in that its targets may be changed (614.1a, 707.10c). For Raise the Alarm
    (no targets) the table asked "Put the next copy on the stack: original or additional copy?", a question with no meaning: it isn't asked.
    For Swords to Plowshares it is, in words that say which copy is which."""
    s = silverquill(cards, "Twinning Staff", "Raise the Alarm", "Swords to Plowshares", "Grizzly Bears", "Llanowar Elves",
                    theirs=["Albino Troll", "Grizzly Bears"])
    put(s, "Twinning Staff"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    mana(s, W=2)
    casualty(s, "Raise the Alarm")
    asked = settle(s, "Grizzly Bears")
    assert not any("copy" in p.lower() for p in asked), asked
    assert field(s)["Soldier"] == 2 * 3
    troll, bears = put(s, "Albino Troll", "p2"), put(s, "Grizzly Bears", "p2")
    mana(s, W=1)
    casualty(s, "Swords to Plowshares", targets=[troll.id])
    settle(s, "Llanowar Elves", stop_at="Swords to Plowshares: which copy")
    d = s.state.rules.decision
    assert d.prompt == "Swords to Plowshares: which copy goes on the stack next? (the last one there resolves first)"
    assert [o.label for o in d.options] == ["A copy (may choose new targets)", "Twinning Staff's additional copy (may choose new targets)"]
    settle(s, "Twinning Staff's additional copy", f"Keep {troll.name}", bears.name)
    assert field(s, "p2") == {}
    check(s)
