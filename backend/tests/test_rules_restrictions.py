"""Activation restrictions (CR 602.5, 307.5) and trigger limits (app/rules/restrictions.py): "Activate
only as a sorcery / once each turn / no more than twice each turn / once / during your turn / during
your upkeep / during combat / before attackers are declared / if …", and "This ability triggers only
once each turn." Counts live in RulesState.ability_uses: they survive a reload and reset with the turn."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.rules import restrictions, scripts
from tests.game_helpers import act, turn_on, zone
from tests.test_rules_combat import attack, creature, table
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches, run_until
from tests.test_rules_scripts import ch
from tests.test_rules_trigger_context import resolve_all


# -- parsing -------------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "expected"), [
    ("{T}: Draw a card. Activate only as a sorcery.", [{"kind": "sorcery"}]),
    ("{1}: Foo. Activate only as an instant.", [{"kind": "instant"}]),
    ("{1}: Foo. Activate only once each turn.", [{"kind": "per_turn", "n": 1}]),
    ("{1}: Foo. Activate no more than twice each turn.", [{"kind": "per_turn", "n": 2}]),
    ("{1}: Foo. Activate only once.", [{"kind": "per_game", "n": 1}]),
    ("{1}: Foo. Activate only during your turn.", [{"kind": "your_turn"}]),
    ("{1}: Foo. Activate only during an opponent's turn.", [{"kind": "opponents_turn"}]),
    ("{1}: Foo. Activate only during your upkeep.", [{"kind": "step", "phases": ["upkeep"], "whose": "you"}]),
    ("{1}: Foo. Activate only during any upkeep step.", [{"kind": "step", "phases": ["upkeep"], "whose": None}]),
    ("{1}: Foo. Activate only during combat.",
     [{"kind": "step", "phases": ["begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat"], "whose": None}]),
    ("{1}: Foo. Activate only during the declare blockers step.", [{"kind": "step", "phases": ["declare_blockers"], "whose": None}]),
    ("{1}: Foo. Activate only during your turn, before attackers are declared.",
     [{"kind": "step", "phases": ["untap", "upkeep", "draw", "main1", "begin_combat"], "whose": "you"}]),
    ("{1}: Foo. Activate only as a sorcery and only once each turn.", [{"kind": "sorcery"}, {"kind": "per_turn", "n": 1}]),
    ("{1}: Foo. Activate only during your turn and only once each turn.", [{"kind": "your_turn"}, {"kind": "per_turn", "n": 1}]),
    ("{1}: Foo. Activate only if you control a Swamp.",
     [{"kind": "if", "cond": {"value": {"count": 'sel:{"controller":"you","subtypes":["Swamp"]}'}, "op": ">=", "n": 1},
       "text": "you control a Swamp"}]),
    ("{1}: Foo. Activate only if there are seven or more cards in your graveyard.",
     [{"kind": "if", "cond": {"value": {"count": 'sel:{"card":true,"zone_owner":"you","zones":["graveyard"]}'}, "op": ">=", "n": 7},
       "text": "there are seven or more cards in your graveyard"}]),
    ("{1}: Foo.", []),
])
def test_parse(text, expected):
    assert restrictions.parse(text) == expected


@pytest.mark.parametrize("text", [
    # (card types among graveyard cards, "a creature died this turn": read since conditional clauses, wave 1B —
    # test_rules_conditionals.py)
    # ("you've cast an instant or sorcery spell this turn": read since wave 4D — test_rules_wave4d_this_turn.py)
    "{1}: Foo. Activate only as a sorcery and only if you've cast a spell with flying this turn.",
    "{1}: Foo. Activate only if this creature is attacking.",
    "{1}: Foo. Activate only if you control the most creatures.",
])
def test_unread_restrictions_are_refused(text):
    assert restrictions.parse(text) is None
    assert scripts.definitions(ch("Foo", "Creature", text.replace("Foo", "draw a card"))) == {}


def test_definitions_carry_the_restriction_and_the_limit():
    greta = ch("Greta, Sweettooth Scourge", "Creature", "{1}, Sacrifice a Food: Draw a card. Activate only as a sorcery.")
    assert scripts.definitions(greta)[0]["restriction"] == [{"kind": "sorcery"}]
    bloom = ch("Bloombrute", "Creature", "Whenever you gain life, draw a card. This ability triggers only once each turn.")
    assert scripts.definitions(bloom)[0]["limit"] == "once_each_turn"
    # 603.2h "Do this only once each turn.": the action is recorded as it's taken (effects.record_action)
    ondu = ch("Ondu", "Creature", "Whenever an enchantment you control enters, you may draw a card. Do this only once each turn.")
    assert scripts.definitions(ondu)[0]["limit"] == "do_once"


# -- scenarios -----------------------------------------------------------------------------------
def main_phase(s):
    """Automation on in Alice's precombat main phase (what's on the table isn't summoning sick)."""
    turn_on(s)
    act(s, "p1", type="pass_priority")
    assert s.state.turn.phase == "main1" and s.state.rules.priority == "p1"


def hinted(s, card, ability=0):
    return {"card_id": card.id, "ability": ability} in s.view("p1")["rules"]["hints"]["activatable"]


def reload(s, cards):
    return GameSession(s.history.rebuild(), cards=cards)


def test_only_as_a_sorcery(cards):
    s = table(cards)
    scholar = creature(s, "p1", "Scholar", "1/1", "{T}: Draw a card. Activate only as a sorcery.")
    other = creature(s, "p1", "Other", "1/1", "{T}: Draw a card.")
    raider = creature(s, "p1", "Raider", "2/2")
    main_phase(s)
    act(s, "p1", type="set_stops", own=["main1", "declare_attackers", "main2"], others=["main1"])
    assert hinted(s, scholar)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=other.id, ability=0)  # something on the stack
    assert s.state.zones["stack"] and s.state.rules.priority == "p1" and not hinted(s, scholar)
    with pytest.raises(ActionError, match="as a sorcery"):
        act(s, "p1", type="activate_ability", card_id=scholar.id, ability=0)
    act(s, "p1", type="set_prefs", hold_priority=False)
    pass_until_stack_empty(s)
    assert hinted(s, scholar)
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (raider, "p2"))
    assert s.state.turn.phase == "declare_attackers" and s.state.rules.priority == "p1" and not hinted(s, scholar)
    with pytest.raises(ActionError, match="as a sorcery"):
        act(s, "p1", type="activate_ability", card_id=scholar.id, ability=0)
    run_until(s, lambda s: s.state.turn.phase == "main2")
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="activate_ability", card_id=scholar.id, ability=0)
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.priority == "p1")
    act(s, "p1", type="tap", card_ids=[scholar.id], tapped=False)
    with pytest.raises(ActionError, match="as a sorcery"):
        act(s, "p1", type="activate_ability", card_id=scholar.id, ability=0)
    replay_matches(s)


def test_once_each_turn_survives_a_reload_and_resets_next_turn(cards):
    s = table(cards)
    brute = creature(s, "p1", "Brute", "2/2", "{1}: This creature gets +1/+1 until end of turn. Activate only once each turn.")
    main_phase(s)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=brute.id, ability=0)
    pass_until_stack_empty(s)
    s = reload(s, cards)  # (a reconnect / reload: the count is in the saved rules state)
    assert s.state.rules.ability_uses == {f"{brute.id}.0:0:t1": 1, f"{brute.id}.0:0:game": 1}
    assert not hinted(s, brute)
    with pytest.raises(ActionError, match="once each turn"):
        act(s, "p1", type="activate_ability", card_id=brute.id, ability=0)
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    s = reload(s, cards)
    mana(s, C=1)
    assert hinted(s, brute)
    act(s, "p1", type="activate_ability", card_id=brute.id, ability=0)
    pass_until_stack_empty(s)
    assert s.state.rules.ability_uses == {f"{brute.id}.0:0:t3": 1, f"{brute.id}.0:0:game": 2}
    with pytest.raises(ActionError, match="once each turn"):
        act(s, "p1", type="activate_ability", card_id=brute.id, ability=0)
    replay_matches(s)


def test_a_new_object_has_its_own_count(cards):
    """602.5b, 400.7: the limit belongs to the object; the same card back from another zone is new."""
    s = table(cards)
    brute = creature(s, "p1", "Brute", "2/2", "{1}: This creature gets +1/+1 until end of turn. Activate only once each turn.")
    main_phase(s)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=brute.id, ability=0)
    oid = s.state.rules.object_id(brute.id)
    assert restrictions.uses(s.state.rules, oid, 0, 1) == 1 and restrictions.uses(s.state.rules, oid, 0, 2) == 0
    assert restrictions.uses(s.state.rules, oid + "x", 0, 1) == 0  # (another object: its own count)


def test_no_more_than_twice_each_turn_and_only_once(cards):
    s = table(cards)
    imp = creature(s, "p1", "Imp", "1/1", "{1}: This creature gets +1/+0 until end of turn. Activate no more than twice each turn.")
    once = creature(s, "p1", "Detective", "1/1", "{1}: Draw a card. Activate only once.")
    main_phase(s)
    mana(s, C=4)
    for _ in range(2):
        act(s, "p1", type="activate_ability", card_id=imp.id, ability=0)
    with pytest.raises(ActionError, match="only twice each turn"):
        act(s, "p1", type="activate_ability", card_id=imp.id, ability=0)
    act(s, "p1", type="activate_ability", card_id=once.id, ability=0)
    pass_until_stack_empty(s)
    with pytest.raises(ActionError, match="only be activated once"):
        act(s, "p1", type="activate_ability", card_id=once.id, ability=0)
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    s = reload(s, cards)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=imp.id, ability=0)  # a new turn: twice again
    with pytest.raises(ActionError, match="only be activated once"):  # for the game
        act(s, "p1", type="activate_ability", card_id=once.id, ability=0)
    assert not hinted(s, once)
    replay_matches(s)


def test_only_during_your_turn_and_your_upkeep(cards):
    s = table(cards)
    waterbender = creature(s, "p1", "Bender", "1/1", "{1}: This creature gets +1/+1 until end of turn. Activate only during your turn.")
    dragon = creature(s, "p1", "Dragon", "1/1", "{1}: Draw a card. Activate only during your upkeep.")
    main_phase(s)
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=waterbender.id, ability=0)
    pass_until_stack_empty(s)
    with pytest.raises(ActionError, match="during your upkeep"):
        act(s, "p1", type="activate_ability", card_id=dragon.id, ability=0)
    act(s, "p1", type="set_stops", own=["upkeep", "main1"], others=["main1"])
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.priority == "p1")
    mana(s, C=2)
    with pytest.raises(ActionError, match="during your turn"):  # Bob's turn
        act(s, "p1", type="activate_ability", card_id=waterbender.id, ability=0)
    with pytest.raises(ActionError, match="during your upkeep"):
        act(s, "p1", type="activate_ability", card_id=dragon.id, ability=0)
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "upkeep" and s.state.rules.priority == "p1")
    mana(s, C=1)
    assert hinted(s, dragon)
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="activate_ability", card_id=dragon.id, ability=0)
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    replay_matches(s)


def test_before_attackers_are_declared_and_during_combat(cards):
    s = table(cards)
    physician = creature(s, "p1", "Physician", "1/1", "{T}: Draw a card. Activate only during your turn, before attackers are declared.")
    blade = creature(s, "p1", "Blade", "2/2", "{1}: This creature gets +1/+0 until end of turn. Activate only during combat.")
    raider = creature(s, "p1", "Raider", "2/2")
    main_phase(s)
    act(s, "p1", type="set_stops", own=["main1", "declare_attackers", "main2"])
    mana(s, C=2)
    with pytest.raises(ActionError, match="during combat"):
        act(s, "p1", type="activate_ability", card_id=blade.id, ability=0)
    assert hinted(s, physician)
    act(s, "p1", type="pass_priority")  # → combat: declare attackers
    attack(s, (raider, "p2"))
    assert s.state.turn.phase == "declare_attackers"
    with pytest.raises(ActionError, match="before attackers are declared"):
        act(s, "p1", type="activate_ability", card_id=physician.id, ability=0)
    mana(s, C=1)  # (the pool emptied with the main phase, 500.5)
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=0)
    pass_until_stack_empty(s)
    replay_matches(s)


def test_only_if_a_condition_holds(cards):
    s = table(cards)
    certarch = creature(s, "p1", "Certarch", "1/1", "{T}: Draw a card. Activate only if you control a Forest.")
    main_phase(s)
    assert not hinted(s, certarch)
    with pytest.raises(ActionError, match="only be activated if you control a Forest"):
        act(s, "p1", type="activate_ability", card_id=certarch.id, ability=0)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    assert hinted(s, certarch)
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="activate_ability", card_id=certarch.id, ability=0)
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    replay_matches(s)


def test_triggers_only_once_each_turn(cards):
    s = table(cards)
    brute = creature(s, "p1", "Bloombrute", "3/3", "Whenever you gain life, draw a card. This ability triggers only once each turn.")
    priests = [creature(s, "p1", f"Priest {i}", "1/1", "{T}: You gain 1 life.") for i in range(2)]
    main_phase(s)
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="activate_ability", card_id=priests[0].id, ability=0)
    resolve_all(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    s = reload(s, cards)
    act(s, "p1", type="activate_ability", card_id=priests[1].id, ability=0)
    resolve_all(s)
    assert s.state.players["p1"].life == 42 and len(zone(s.state, "p1", "hand")) == hand + 1  # no second draw
    assert s.state.rules.ability_uses[f"{brute.id}.0:0:t1"] == 1
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="activate_ability", card_id=priests[0].id, ability=0)
    resolve_all(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1  # a new turn: it triggers again
    replay_matches(s)
