"""Triggers about another object that then say "it": the word binds to the trigger's event object (603.2, 608.2c), never to the source.

"Whenever a creature you control attacks, it can't be blocked this turn." / "... it dives." / "Whenever another creature you control
enters, it dives." -- the grammar reads "it" in an event trigger as ``who: "event"`` (the attacker / the creature that entered), so the
restriction lands on that creature only, with its own duration: "this turn" ends at cleanup (514.2), dive ends the moment it deals
combat damage while attacking (app/rules/dive.py, 510.2/611.2a). Every scenario checks the replay and a save and a load.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, dive, scripts
from app.rules.characteristics import printed_from_data
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_combat import attack, automate, block, creature, decision, table
from tests.test_rules_conditionals import settle
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, check, mana, pt, to_hand

UNBLOCKABLE = "Whenever a creature you control attacks, it can't be blocked this turn."
DIVES = "Whenever a creature you control attacks, it dives."
ENTERS_DIVES = "Whenever another creature you control enters, it dives."
SHAPES = [
    UNBLOCKABLE, DIVES, ENTERS_DIVES,
    "Whenever another creature you control enters, it can't be blocked this turn.",
    "Whenever another creature enters the battlefield under your control, it gains haste until end of turn.",
    "Whenever a creature you control becomes blocked, it gets +2/+2 until end of turn.",
    "Whenever a creature you control deals combat damage to a player, it explores.",
    # a restriction and a grant on the one creature, either order (two instructions, 608.2c; the second "It" is the first's object)
    "Whenever another creature you control enters, it dives and gains haste until end of turn.",
    "Whenever a creature you control attacks, it can't be blocked this turn and gains flying until end of turn.",
    "Whenever a creature you control attacks, it gets +1/+0 until end of turn and dives.",
    "Whenever a creature you control attacks, it dives and gets +1/+0 until end of turn.",
]
GRANT_THEN_DIVE = "Whenever a creature you control attacks, it gets +1/+0 until end of turn and dives."


def _definition(text):
    data = {"id": f"it-probe-{SHAPES.index(text)}", "oracle_id": None, "name": "It Probe", "type_line": "Creature — Merfolk",
            "mana_cost": "{2}", "oracle_text": text, "power": "2", "toughness": "2", "colors": [], "layout": "normal"}
    return data, scripts.definitions(printed_from_data(data, 0))[0]


@pytest.mark.parametrize("text", SHAPES)
def test_it_reads_as_the_event_object(text):
    data, d = _definition(text)
    assert coverage.of_card_data(data).level == "FULL"
    assert d["kind"] == "triggered"
    whos = [e["who"] for e in d["effects"] if "who" in e]
    assert whos[0] == "event" and all(w == "event" or w.startswith("ref:") for w in whos), d


def _oid(s, card):
    return Plan(s.state, "p1", s.cards, None).oid(s.state.cards[card.id])


def _attack_table(cards, text):
    s = table(cards)
    captain = creature(s, "p1", "Captain", "1/1", text=text)
    raider = creature(s, "p1", "Raider", "2/2")
    guard = creature(s, "p2", "Guard", "2/2")
    automate(s)
    attack(s, (raider, "p2"))
    pass_until_stack_empty(s)  # (the attack trigger resolves; Bob is asked for blockers)
    assert decision(s).kind == "declare_blockers"
    return s, captain, raider, guard


def _restrictions(s):
    return [e for e in s.state.rules.effects if "cant_be_blocked" in (e.imposes or [])]


def test_attack_trigger_makes_the_attacker_unblockable_this_turn(cards):
    s, captain, raider, guard = _attack_table(cards, UNBLOCKABLE)
    (e,) = _restrictions(s)
    assert e.affected == [_oid(s, raider)] and e.duration == "end_of_turn"  # the attacker, not the Captain
    with pytest.raises(ActionError):
        block(s, "p2", (guard, raider))
    block(s, "p2")
    to_phase(s, "main2")
    assert s.state.players["p2"].life == 38
    to_phase(s, "main1", turn=2)
    assert not _restrictions(s)  # 514.2: "this turn" ended at cleanup
    check(s)


def test_attack_trigger_makes_the_attacker_dive_until_it_connects(cards):
    s, captain, raider, guard = _attack_table(cards, DIVES)
    (e,) = _restrictions(s)
    assert e.affected == [_oid(s, raider)] and e.duration == dive.ATTACKING
    with pytest.raises(ActionError):
        block(s, "p2", (guard, raider))
    block(s, "p2")
    to_phase(s, "main2")
    assert s.state.players["p2"].life == 38
    assert not _restrictions(s)  # it dealt combat damage while attacking: the dive ended (510.2, 611.2a)
    assert not [m for m in s.state.cards[raider.id].effects if "blocked" in (m.name or "").lower()]
    check(s)


def test_enters_trigger_it_is_the_creature_that_entered(cards):
    s = build(cards, ["Grizzly Bears"])
    captain = creature(s, "p1", "Captain", "1/1", text=ENTERS_DIVES)
    bears = to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    (e,) = _restrictions(s)
    assert e.affected == [_oid(s, bears)] and e.duration == dive.ATTACKING
    assert _oid(s, captain) not in e.affected
    check(s)


def test_attack_trigger_pump_and_dive_end_apart(cards):
    s, captain, raider, guard = _attack_table(cards, GRANT_THEN_DIVE)
    (e,) = _restrictions(s)
    assert e.affected == [_oid(s, raider)] and e.duration == dive.ATTACKING
    assert pt(s, "Raider") == (3, 2) and pt(s, "Captain") == (1, 1)
    with pytest.raises(ActionError):
        block(s, "p2", (guard, raider))
    block(s, "p2")
    to_phase(s, "main2")
    assert s.state.players["p2"].life == 37
    assert not _restrictions(s)  # the dive ended as it connected ...
    assert pt(s, "Raider") == (3, 2)  # ... the +1/+0 lasts until end of turn (611.2a: each its own duration)
    to_phase(s, "main1", turn=2)
    assert pt(s, "Raider") == (2, 2)
    check(s)


def test_enters_trigger_dive_and_haste_on_the_creature_that_entered(cards):
    s = build(cards, ["Grizzly Bears"])
    captain = creature(s, "p1", "Captain", "1/1", text="Whenever another creature you control enters, it dives and gains haste until end of turn.")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    (e,) = _restrictions(s)
    assert e.affected == [_oid(s, bears)] and e.duration == dive.ATTACKING
    hastes = [x for x in s.state.rules.effects if "haste" in (x.add_keywords or [])]
    assert [x.affected for x in hastes] == [[_oid(s, bears)]] and hastes[0].duration == "end_of_turn"
    assert _oid(s, captain) not in e.affected
    check(s)
