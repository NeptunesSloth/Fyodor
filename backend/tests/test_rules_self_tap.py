"""Players tap their own mana: the engine never taps anyone's lands. Costs are paid from the
mana pool; if it's short, a "tap your mana" prompt opens, mana abilities can be used while it's
open, and the spell goes on as soon as the pool covers the cost."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, zone


def build(cards, lands=2):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Grizzly Bears"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False))
    for prefs in state.rules.prefs.values():
        prefs.payment = "self"  # the table default
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "hand"})
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:lands]
    act(s, "p1", type="move", card_ids=forests, to={"zone": "battlefield"})
    return s, bears, forests


def test_default_is_self_tap():
    from app.game.rules_state import PlayerPrefs

    assert PlayerPrefs().payment == "self"


def test_casting_never_taps_lands_it_asks_you_to_tap(cards):
    s, bears, forests = build(cards)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    d = s.state.rules.decision
    assert d is not None and d.display["kind"] == "tap_mana" and d.display["cost"] == "{1}{G}"
    assert set(d.display["sources"]) == set(forests)
    assert not any(s.state.cards[f].tapped for f in forests)  # nothing tapped for you
    assert s.state.cards[bears.id].zone == "p1:hand"
    with pytest.raises(ActionError, match="Tap your mana first"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    act(s, "p1", type="activate_ability", card_id=forests[0], ability=0)  # you tap a Forest
    assert s.state.rules.decision is not None and s.state.rules.decision.display["pool"] == {"G": 1}
    act(s, "p1", type="activate_ability", card_id=forests[1], ability=0)  # … and the second: it's cast
    assert s.state.cards[bears.id].zone in ("stack", "p1:battlefield")
    assert all(s.state.cards[f].tapped for f in forests)
    assert s.state.players["p1"].mana == {}


def test_cancel_leaves_everything(cards):
    s, bears, forests = build(cards)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    act(s, "p1", type="activate_ability", card_id=forests[0], ability=0)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["cancel"])
    assert s.state.cards[bears.id].zone == "p1:hand" and s.state.players["p1"].mana == {"G": 1}
    assert not s.state.cards[forests[1]].tapped


def test_mana_already_in_the_pool_pays_without_asking(cards):
    s, bears, forests = build(cards)
    for f in forests:
        act(s, "p1", type="activate_ability", card_id=f, ability=0)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert s.state.rules.decision is None or s.state.rules.decision.display is None
    assert s.state.cards[bears.id].zone in ("stack", "p1:battlefield")


def test_extra_lands_stay_untapped(cards):
    s, bears, forests = build(cards, lands=4)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    act(s, "p1", type="activate_ability", card_id=forests[2], ability=0)
    act(s, "p1", type="activate_ability", card_id=forests[3], ability=0)
    assert [s.state.cards[f].tapped for f in forests] == [False, False, True, True]  # exactly the ones you tapped


def test_only_mana_abilities_while_paying(cards):
    s, bears, forests = build(cards)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    with pytest.raises(ActionError):
        act(s, "p1", type="pass_priority")
    assert zone(s.state, "p1", "hand")


def test_echo_is_paid_from_the_mana_you_tap(cards):
    from tests.test_rules_upkeep_costs import until_prompt

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Albino Troll"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    troll = next(c for c in s.state.cards.values() if c.name == "Albino Troll")
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest"][:2]
    act(s, "p1", type="move", card_ids=[troll.id, *forests], to={"zone": "battlefield"})
    s = GameSession(enable(s.state), cards=cards)
    for prefs in s.state.rules.prefs.values():
        prefs.payment = "self"
    d = until_prompt(s)
    with pytest.raises(ActionError, match="Tap your mana first"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    for f in forests:
        act(s, "p1", type="activate_ability", card_id=f, ability=0)  # tapping is allowed during the prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    assert s.state.cards[troll.id].zone == "p1:battlefield" and s.state.players["p1"].mana == {}


def test_convoke_by_tapping_your_creatures(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Stoke the Flames"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False))
    for prefs in state.rules.prefs.values():
        prefs.payment = "self"
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")
    stoke = next(c for c in s.state.cards.values() if c.name == "Stoke the Flames")
    act(s, "p1", type="move", card_ids=[stoke.id], to={"zone": "hand"})
    ids = []
    for i, colors in enumerate([["R"], ["R"], [], ["G"]]):
        act(s, "p1", type="create_token", player="p1", token={"name": f"T{i}", "type_line": "Token Creature — Test",
                                                             "power": "1", "toughness": "1", "colors": colors})
        ids.append(next(c.id for c in s.state.cards.values() if c.name == f"T{i}"))
    act(s, "p1", type="cast_spell", card_id=stoke.id, targets=["p2"])
    d = s.state.rules.decision
    assert set(d.display["convoke"]) == set(ids) and not any(s.state.cards[c].tapped for c in ids)
    for cid in ids:
        act(s, "p1", type="activate_ability", card_id=cid, ability=0, convoke=True)
    assert all(s.state.cards[c].tapped for c in ids)
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == 36
