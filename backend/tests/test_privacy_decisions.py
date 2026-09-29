"""Decision privacy matrix: Alice decides, Bob watches. While Alice's choice concerns a hidden card
(a spell still in her hand as she chooses its targets / modes / division / costs, 601.2a; cards in
her hand or library), nothing identifying that card may appear anywhere in Bob's serialized view
(the same payload REST and WebSocket send), while Alice gets the complete decision. Once the
spell is legally on the stack it is public and Bob sees it."""

from __future__ import annotations

import json

from app.game.session import GameSession
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty


def secrets_of(s, card_ids):
    """What would identify these cards: their ids, printing ids and names."""
    out = []
    for cid in card_ids:
        c = s.state.cards[cid]
        out += [cid, c.name]
        if c.card_id:
            out.append(c.card_id)
    return [x for x in out if x]


def assert_hidden_from_bob(s, card_ids):
    bob = json.dumps(s.view("p2"))
    for secret in secrets_of(s, card_ids):
        assert secret not in bob, secret
    d = s.view("p2")["rules"]["decision"]
    assert d["public"] == {"type": "PLAYER_MAKING_CHOICE", "chooser": "Alice"} and "options" not in d
    assert d["source_id"] is None and "display" not in d


def alice_decision(s):
    d = s.view("p1")["rules"]["decision"]
    assert d["options"] is not None and d["prompt"]  # the chooser gets everything
    return d


def test_target_for_a_spell_still_in_hand(cards):
    s = build(cards, "Lightning Bolt")
    ogre = token(s, "p2", "Ogre", "3/3")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id)
    assert s.state.cards[bolt.id].zone == "p1:hand"
    assert ogre.id in {o["id"] for o in alice_decision(s)["options"]}
    assert_hidden_from_bob(s, [bolt.id])


def test_mode_choice_from_hand(cards):
    s = build(cards, "Test Shatter Charm")
    charm = to_hand(s, "Test Shatter Charm")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=charm.id)
    labels = [o["label"] for o in alice_decision(s)["options"]]
    assert any("Draw a card" in x for x in labels)
    assert_hidden_from_bob(s, [charm.id])
    assert "Destroy target artifact" not in json.dumps(s.view("p2"))  # (mode text from a hidden card)


def test_dividing_damage_for_a_hidden_spell(cards):
    s = build(cards, "Test Barrage")
    ogre = token(s, "p2", "Ogre", "3/3")
    spell = to_hand(s, "Test Barrage")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[ogre.id, "p2"])
    assert alice_decision(s)["kind"] == "divide"
    assert_hidden_from_bob(s, [spell.id])
    assert s.view("p2")["rules"]["decision"]["kind"] == "waiting"


def test_kicked_spell_choosing_targets(cards):
    s = build(cards, "Test Kicked Bolt")
    token(s, "p2", "Ogre", "3/3")
    spell = to_hand(s, "Test Kicked Bolt")
    mana(s, R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1)
    alice_decision(s)
    assert_hidden_from_bob(s, [spell.id])
    assert "Kicker" not in json.dumps(s.view("p2")["rules"])


def test_private_cost_choice_from_hand(cards):
    s = build(cards)
    act(s, "p1", type="draw", player="p1", count=3)
    hand = zone(s.state, "p1", "hand")
    src = token(s, "p1", "Looter", text="{1}, Discard a card: Draw a card.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    assert set(hand) <= {o["id"] for o in alice_decision(s)["options"]}
    assert_hidden_from_bob(s, hand)


def test_library_search(cards):
    s = build(cards)
    src = token(s, "p1", "Tutor", text="{1}: Search your library for a card, put it into your hand, then shuffle.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    options = [o["id"] for o in alice_decision(s)["options"]]
    assert options
    bob = json.dumps(s.view("p2"))
    assert not any(cid in bob for cid in options)
    assert s.view("p2")["rules"]["decision"]["kind"] == "waiting"


def test_look_at_the_top_cards(cards):
    s = build(cards)
    top = zone(s.state, "p1", "library")[:3]
    src = token(s, "p1", "Seer", text="{1}: Look at the top three cards of your library. Put one of them into your hand "
                                      "and the rest into your graveyard.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)
    pass_until_stack_empty(s)
    assert {o["id"] for o in alice_decision(s)["options"]} == set(top)
    bob = json.dumps(s.view("p2"))
    assert not any(cid in bob for cid in top)


def test_reconnecting_while_a_private_decision_is_pending(cards):
    s = build(cards, "Lightning Bolt")
    token(s, "p2", "Ogre", "3/3")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id)
    reloaded = GameSession(s.history.rebuild(), cards=cards)  # (a reconnect / reload sees the saved table)
    bob = json.dumps(reloaded.view("p2"))
    for secret in secrets_of(s, [bolt.id]):
        assert secret not in bob
    assert reloaded.view("p1")["rules"]["decision"]["options"]


def test_the_spell_becomes_public_on_the_stack_not_before(cards):
    s = build(cards, "Lightning Bolt")
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"  # (stop with it on the stack)
    ogre = token(s, "p2", "Ogre", "3/3")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id)
    assert "Lightning Bolt" not in json.dumps(s.view("p2"))  # choosing targets: still hidden
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[ogre.id])
    assert s.state.cards[bolt.id].zone == "stack"
    assert "Lightning Bolt" in json.dumps(s.view("p2"))  # cast: public (601.2a)
    assert named(s, "Lightning Bolt").id in json.dumps(s.view("p2"))
