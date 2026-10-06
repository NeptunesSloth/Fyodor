"""Wave 28C: abilities activated from a hidden zone name their source on the stack (CR 2026-09-25). Real Oracle text; every scenario
checks the replay and a save and a load.

* 602.2a: "If an activated ability is being activated from a hidden zone, the card that has that ability is revealed (see rule
  701.20a). That ability is created on the stack as an object that's not a card." The opponent reads the ability's source, never the
  rest of the hand.
* 702.29a cycling and channel (discard as a cost), 702.49a ninjutsu (the card stays in the hand until the ability resolves).
"""

from __future__ import annotations

import json

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of, until
from tests.test_rules_wave6e_statics import attack_with
from tests.wave9c_kit import build, check, mana, to_hand

REAL = [
    ("Twinshot Sniper", "{3}{R}", "Artifact Creature — Goblin Archer", "2", "3",
     "Reach\nWhen this creature enters, it deals 2 damage to any target.\nChannel — {1}{R}, Discard this card: It deals 2 damage to any target."),
    ("Lonely Sandbar", "", "Land", None, None, "{T}: Add {U}.\nCycling {U} ({U}, Discard this card: Draw a card.)"),
    ("Ninja of the Deep Hours", "{3}{U}", "Creature — Human Ninja", "2", "2",
     "Ninjutsu {1}{U} ({1}{U}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand "
     "tapped and attacking.)\nWhenever this creature deals combat damage to a player, you may draw a card."),
    ("Tarmogoyf", "{1}{G}", "Creature — Lhurgoyf", "*", "1+*", "Tarmogoyf's power is equal to the number of card types among cards in all graveyards."),
]
EXTRA = [card(n, set_code="t28c", number=f"C{i:02d}", mana_cost=mc, cmc=float(len(mc.replace("{", "").split("}")) - 1) if mc else 0.0,
              type_line=tl, colors=["R"], color_identity=["R"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def stack_ability(s, viewer="p2"):
    (sid,) = s.state.zones["stack"]
    return s.view(viewer)["cards"][sid]["ability"]


def run(s):
    settle(s)
    while s.state.zones.get("stack"):
        act(s, "p1", type="pass_priority")
        act(s, "p2", type="pass_priority")
        settle(s)


def test_channel_names_its_source_on_the_stack(cards):
    s = build(cards, ["Twinshot Sniper", "Tarmogoyf"])
    sniper = to_hand(s, "Twinshot Sniper")
    other = to_hand(s, "Tarmogoyf")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, R=1, C=1)
    idx = next(a["ability"] for a in __import__("app.rules.casting", fromlist=["x"]).activatable(s.state, "p1", s.cards)
               if a["card_id"] == sniper.id)
    act(s, "p1", type="activate_ability", card_id=sniper.id, ability=idx, targets=["p2"])
    assert stack_ability(s)["source_name"] == "Twinshot Sniper"  # 602.2a
    assert other.name not in json.dumps(s.view("p2"), default=str)  # (the rest of the hand stays hidden)
    assert s.state.cards[sniper.id].zone == "p1:graveyard"  # the discard is the cost
    life = s.state.players["p2"].life
    run(s)
    assert s.state.players["p2"].life == life - 2
    check(s)


def test_cycling_names_its_source_on_the_stack(cards):
    s = build(cards, ["Lonely Sandbar", "Tarmogoyf"])
    sandbar = to_hand(s, "Lonely Sandbar")
    to_hand(s, "Tarmogoyf")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, U=1)
    idx = 1  # (Cycling {U})
    act(s, "p1", type="activate_ability", card_id=sandbar.id, ability=idx)
    assert stack_ability(s)["source_name"] == "Lonely Sandbar"
    assert "Tarmogoyf" not in json.dumps(s.view("p2"), default=str)
    hand = len(s.state.zones["p1:hand"])
    run(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_the_hand_is_not_leaked_by_a_hidden_activation(cards):
    """The ability names only the activated card: the spectator and the other player see nothing else of the hand."""
    s = build(cards, ["Lonely Sandbar", "Tarmogoyf"])
    sandbar = to_hand(s, "Lonely Sandbar")
    to_hand(s, "Tarmogoyf")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, U=1)
    idx = 1  # (Cycling {U})
    act(s, "p1", type="activate_ability", card_id=sandbar.id, ability=idx)
    for viewer in ("p2", "__spectator__"):
        assert "Tarmogoyf" not in json.dumps(s.view(viewer), default=str), viewer
    check(s)


def test_ninjutsu_names_its_source_on_the_stack(cards):
    s = build(cards, ["Ninja of the Deep Hours", "Tarmogoyf"])
    ninja = to_hand(s, "Ninja of the Deep Hours")
    to_hand(s, "Tarmogoyf")
    rat = token_of(s, "p1", "Rat", "Token Creature — Rat", "1/1")
    token_of(s, "p2", "Wall", "Token Creature — Wall", "0/4")
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"], hold_priority=True)
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")
    attack_with(s, rat)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    mana(s, U=1, C=1)
    act(s, "p2", type="declare_blockers", blocks=[])
    act(s, "p1", type="activate_ability", card_id=ninja.id, ability=0)
    d = s.state.rules.decision
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[rat.id])
    assert stack_ability(s)["source_name"] == "Ninja of the Deep Hours"  # 602.2a; 702.49b: revealed while the ability is on the stack
    assert "Tarmogoyf" not in json.dumps(s.view("p2"), default=str)
    run(s)
    assert s.state.cards[ninja.id].zone == "p1:battlefield"
    check(s)
