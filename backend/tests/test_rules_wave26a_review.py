"""Review of wave 26A (static_other). Real Oracle text, replay and a save/load round trip.

* 611.2c: "Creatures target player controls can't block this turn" / "attack this turn if able" (Ember Gale, Incite War, Instigator) modify
  the rules, not characteristics: the player is fixed as the spell resolves, the creatures are not — one that comes under that player's
  control later this turn is affected too.
* 701.23a: "Search target opponent's library …" (Bribery): the searcher isn't searching "their library", so Opposition Agent ("while they're
  searching their libraries") and Ashiok, Dream Render ("can't cause their controller to search their library") don't apply.
* Galadriel's Dismissal kicked: each creature the target player controls phases out (702.26), the unkicked target isn't chosen.
* Sarkhan, the Dragonspeaker's emblem: "At the beginning of your draw step, draw two additional cards" is a triggered ability (603.2) that
  draws after the turn's draw (504.1–504.2); "At the beginning of your end step, discard your hand."
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from tests.fixtures.cards import card, fixture_cards
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.test_rules_attachments import ch
from app.game.errors import ActionError
from tests.test_rules_combat import attack, block
from tests.test_rules_conditionals import to_turn
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip
from tests.test_rules_wave13a_emblems import emblems, get_emblem
from tests.test_rules_wave26a_static_other import EXTRA

SARKHAN = 'You get an emblem with "At the beginning of your draw step, draw two additional cards" and "At the beginning of your end step, discard your hand."'  # noqa: E501
REVIEW = [
    card('Ember Gale', set_code='tst', number='R01', mana_cost='{3}{R}', cmc=4.0, type_line='Sorcery', oracle_text="Creatures target player controls can't block this turn. Ember Gale deals 1 damage to each white and/or blue creature that player controls.", colors=['R'], color_identity=['R'], keywords=[], layout='normal'),  # noqa: E501
    card('Incite War', set_code='tst', number='R02', mana_cost='{2}{R}', cmc=3.0, type_line='Instant', oracle_text='Choose one —\n• Creatures target player controls attack this turn if able.\n• Creatures you control gain first strike until end of turn.\nEntwine {2} (Choose both if you pay the entwine cost.)', colors=['R'], color_identity=['R'], keywords=['Entwine'], layout='normal'),  # noqa: E501
    card('Instigator', set_code='tst', number='R03', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Human Spellshaper', power='1', toughness='1', oracle_text='{1}{B}{B}, {T}, Discard a card: Creatures target player controls attack this turn if able.', colors=['B'], color_identity=['B'], keywords=[], layout='normal'),  # noqa: E501
    card("Galadriel's Dismissal", set_code='tst', number='R04', mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text="Kicker {2}{W} (You may pay an additional {2}{W} as you cast this spell.)\nTarget creature phases out. If this spell was kicked, each creature target player controls phases out instead. (Treat phased-out creatures and anything attached to them as though they don't exist until their controller's next turn.)", colors=['W'], color_identity=['W'], keywords=['Kicker'], layout='normal'),  # noqa: E501
    card('Opposition Agent', set_code='tst', number='R05', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Human Rogue', power='3', toughness='2', oracle_text="Flash\nYou control your opponents while they're searching their libraries.\nWhile an opponent is searching their library, they exile each card they find. You may play those cards for as long as they remain exiled, and you may spend mana as though it were mana of any color to cast them.", colors=['B'], color_identity=['B'], keywords=['Flash'], layout='normal'),  # noqa: E501
    card('Ashiok, Dream Render', set_code='tst', number='R06', mana_cost='{1}{U/B}{U/B}', cmc=3.0, type_line='Legendary Planeswalker — Ashiok', loyalty='5', oracle_text="Spells and abilities your opponents control can't cause their controller to search their library.\n−1: Target player mills four cards. Then exile each opponent's graveyard.", colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Mill'], layout='normal'),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA + REVIEW, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _bear(s, pid="p2"):
    """A creature that comes under ``pid``'s control after the spell resolved."""
    return put(s, "Test Bear", "battlefield", pid=pid)


def test_ember_gale_a_creature_arriving_later_cant_block_either(cards):
    s = build(cards, p1=("Ember Gale", "Test Knight"), p2=("Test Bear",))
    mana(s, R=4)
    put(s, "Ember Gale", "hand")
    act(s, "p1", type="cast_spell", card_id=find(s, "Ember Gale").id, targets=["p2"])
    answer(s)
    bear, knight = _bear(s), put(s, "Test Knight", "battlefield")
    assert "cant_block" in ch(s, bear).imposed and "cant_block" not in ch(s, knight).imposed
    act(s, "p1", type="create_token", player="p1", token={"name": "Sneak", "type_line": "Token Creature — Test", "power": "2",
                                                         "toughness": "2", "text": "Haste"})
    sneak = next(c for c in s.state.cards.values() if c.name == "Sneak")
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    attack(s, (sneak, "p2"))
    with pytest.raises(ActionError):  # 611.2c: the set of creatures isn't locked in
        block(s, "p2", (bear, sneak))
    roundtrip(s)


def test_incite_war_and_instigator_reach_creatures_that_arrive_later(cards):
    s = build(cards, p1=("Incite War", "Instigator", "Test Knight", "Test Glass"), p2=("Test Bear",))
    put(s, "Incite War", "hand")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=find(s, "Incite War").id, modes=[0], targets=["p2"])
    answer(s)
    bear = _bear(s)
    assert "must_attack" in ch(s, bear).imposed
    to_turn(s, 3)  # the effect ended at the cleanup step (514.2)
    assert "must_attack" not in ch(s, bear).imposed
    instigator = put(s, "Instigator", "battlefield")
    put(s, "Test Glass", "hand")
    to_turn(s, 5)
    mana(s, B=3)
    act(s, "p1", type="activate_ability", card_id=instigator.id, ability=0, targets=["p2"])
    answer(s)  # (the discard: the one card in hand, or the first offered)
    knight = put(s, "Test Knight", "battlefield")
    act(s, "p2", type="create_token", player="p2", token={"name": "Late", "type_line": "Token Creature — Test", "power": "1",
                                                         "toughness": "1", "text": ""})
    late = next(c for c in s.state.cards.values() if c.name == "Late")
    assert "must_attack" in ch(s, late).imposed and "must_attack" not in ch(s, knight).imposed
    roundtrip(s)


def test_galadriels_dismissal_kicked_phases_out_each_creature_that_player_controls(cards):
    s = build(cards, p1=("Galadriel's Dismissal", "Test Knight"), p2=("Test Bear",))
    knight, bear = put(s, "Test Knight", "battlefield"), _bear(s)
    put(s, "Galadriel's Dismissal", "hand")
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=find(s, "Galadriel's Dismissal").id, kicker=1, targets=["p2"], target_counts=[0, 1])
    answer(s)
    assert s.state.cards[bear.id].zone == "p2:phased" and s.state.cards[knight.id].zone == "p1:battlefield"
    roundtrip(s)


@pytest.mark.parametrize("watcher", ["Opposition Agent", "Ashiok, Dream Render"])
def test_searching_an_opponents_library_isnt_searching_their_own(cards, watcher):
    s = build(cards, p1=("Bribery",), p2=("Test Bear", watcher))
    w = put(s, watcher, "battlefield", pid="p2")
    if watcher.startswith("Ashiok"):
        act(s, "p2", type="counter", card_ids=[w.id], kind="loyalty", delta=5)
    assert s.state.cards[w.id].zone == "p2:battlefield"
    put(s, "Bribery", "hand")
    mana(s, U=5)
    act(s, "p1", type="cast_spell", card_id=find(s, "Bribery").id, targets=["p2"])
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p1" and d.decider in (None, "p1")  # Bob doesn't control Alice's search (723.2 covers their own library)
    answer(s, pick=find(s, "Test Bear", "p2").id)
    bear = find(s, "Test Bear", "p2")
    assert bear.zone == "p1:battlefield" and bear.controller == "p1"  # not exiled for Bob, not stopped by Ashiok
    assert not any(p.player == "p2" for p in s.state.rules.permissions)
    roundtrip(s)


def test_sarkhans_emblem_draws_two_more_in_the_draw_step_and_discards_at_the_end_step(cards):
    alice, bob = deck(cards, "Krenko, Mob Boss", [(30, "Forest")]), deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    get_emblem(s, SARKHAN)
    assert len(emblems(s, "p1")) == 1
    to_turn(s, 2)  # Bob's turn: Alice's emblem draws nothing for him
    hand = len(s.state.zones["p1:hand"])
    to_turn(s, 3, "main1")
    assert len(s.state.zones["p1:hand"]) == hand + 3  # the turn's draw (504.1), then the trigger's two (504.2)
    to_turn(s, 4, "main1")
    assert s.state.zones["p1:hand"] == [] and len(s.state.zones["p2:hand"]) > 0  # Alice's end step only
    roundtrip(s)
