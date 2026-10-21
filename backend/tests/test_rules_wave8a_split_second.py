"""Wave 8A: split second (702.61; app/rules/split_second.py, asked by cast_limits on every cast and activation path).

While a spell with split second is on the stack, players can't cast spells or activate abilities that aren't mana
abilities (702.61a); mana abilities stay possible and triggered abilities still trigger (702.61b). Every scenario checks
the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, mana_units
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import creature, on_field, settle, to_hand
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_wave4h_activation_costs import ability

EXTRA = [
    card('Krosan Grip', set_code="tst", number="W00", mana_cost='{2}{G}', cmc=3.0, type_line='Instant', oracle_text="Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)\nDestroy target artifact or enchantment.", colors=['G'], color_identity=['G'], keywords=['Split second']),  # noqa: E501
    card('Sudden Shock', set_code="tst", number="W01", mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text="Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)\nSudden Shock deals 2 damage to any target.", colors=['R'], color_identity=['R'], keywords=['Split second']),  # noqa: E501
    card('Take Possession', set_code="tst", number="W02", mana_cost='{5}{U}{U}', cmc=7.0, type_line='Enchantment — Aura', oracle_text="Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)\nEnchant permanent\nYou control enchanted permanent.", colors=['U'], color_identity=['U'], keywords=['Enchant', 'Split second']),  # noqa: E501
    card('Sulfur Elemental', set_code="tst", number="W03", mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Elemental', oracle_text="Flash\nSplit second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)\nWhite creatures get +1/-1.", power='3', toughness='2', colors=['R'], color_identity=['R'], keywords=['Flash', 'Split second']),  # noqa: E501
    card('Samut, Tyrant of Naktamun', set_code="tst", number="W04", mana_cost='{1}{U}', cmc=2.0, type_line='Legendary Creature — Human Wizard', oracle_text="Instant and sorcery spells you control have split second. (As long as a spell with split second is on the stack, players can't cast spells or activate abilities that aren't mana abilities.)", power='2', toughness='1', colors=['U'], color_identity=['U']),  # noqa: E501
]
FULL = ["Krosan Grip", "Sudden Shock", "Take Possession", "Sulfur Elemental"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_granting_split_second_is_read_now(cards):
    """Wave 28C: a static granting split second to the spells on the stack is read (app/rules/spell_grants.py); see test_rules_wave28c_spell_grants."""
    assert coverage.of_card_data(cards.resolve("Samut, Tyrant of Naktamun")).level == "FULL"


def table(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Krosan Grip"), (1, "Lightning Bolt"), (1, "Sol Ring"), (1, "Sulfur Elemental"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Lightning Bolt"), (1, "Sol Ring"), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")  # (otherwise the engine passes for a player who can't respond: it
    return s  # does so under split second as well - see the last test)


def refused(s, pid, **payload):
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match="split second"):
        act(s, pid, **payload)
    assert s.state.model_dump(mode="json") == before  # nothing changed (601.3, 602.5)


def test_nothing_can_be_cast_or_activated_but_mana_abilities_while_it_is_on_the_stack(cards):
    s = table(cards)
    pingers = {pid: creature(s, pid, f"Pinger {pid}", pt="1/1", text="{1}: You gain 1 life.") for pid in ("p1", "p2")}
    rings = {pid: on_field(s, "Sol Ring", pid=pid) for pid in ("p1", "p2")}
    bolts = {pid: to_hand(s, "Lightning Bolt", pid=pid) for pid in ("p1", "p2")}
    grip = to_hand(s, "Krosan Grip")
    mana(s, G=1, C=2)
    for pid in ("p1", "p2"):
        mana(s, pid, R=1)
    act(s, "p1", type="cast_spell", card_id=grip.id, targets=[rings["p2"].id])
    assert s.state.zones["stack"] and s.state.cards[grip.id].zone == "stack"
    for _ in range(2):  # whoever holds priority (the engine hands it on): both players are stopped the same way
        me = s.state.rules.priority
        other = "p2" if me == "p1" else "p1"
        refused(s, me, type="cast_spell", card_id=bolts[me].id, targets=[other])  # no other spell
        refused(s, me, type="activate_ability", card_id=pingers[me].id, ability=ability(s, pingers[me], "{1}: You gain"))
        before = mana_units.visible_pool(s.state, me).get("C", 0)
        act(s, me, type="activate_ability", card_id=rings[me].id, ability=ability(s, rings[me], "{T}: Add"))  # 702.61b
        assert mana_units.visible_pool(s.state, me).get("C", 0) == before + 2
        roundtrip(s)
        act(s, me, type="pass_priority")
    settle(s)
    assert rings["p2"].id not in s.state.zones["p2:battlefield"]  # the split second spell resolved
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolts["p1"].id, targets=["p2"])  # the stack is clear again: it is allowed
    settle(s)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_a_split_second_creature_spell_stops_the_table_too(cards):
    s = table(cards)
    elemental = to_hand(s, "Sulfur Elemental")
    mana(s, R=4)
    act(s, "p1", type="cast_spell", card_id=elemental.id)
    me = s.state.rules.priority  # (the engine hands priority on: nobody can respond, but the stack is not skipped)
    bolt = to_hand(s, "Lightning Bolt", pid=me)
    mana(s, me, R=1)
    refused(s, me, type="cast_spell", card_id=bolt.id, targets=["p2" if me == "p1" else "p1"])
    settle(s)
    assert s.state.cards[elemental.id].zone == "p1:battlefield"
    roundtrip(s)


def test_the_engine_does_not_wait_for_a_response_nobody_can_make(cards):
    s = table(cards)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="auto")
    grip = to_hand(s, "Krosan Grip")
    target = on_field(s, "Sol Ring", pid="p2")
    to_hand(s, "Lightning Bolt", pid="p2")
    mana(s, G=1, C=2)
    mana(s, "p2", R=1)  # Bob has an instant and the mana for it - but not while a split second spell is on the stack
    act(s, "p1", type="cast_spell", card_id=grip.id, targets=[target.id])
    assert not s.state.zones.get("stack") and target.id not in s.state.zones["p2:battlefield"]
    roundtrip(s)
