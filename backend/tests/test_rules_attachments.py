"""Auras and Equipment: CR 303.4 (Auras), 301.5 (Equipment), 702.5 (enchant), 702.6 (equip),
701.3 (attach), 608.2b (illegal targets), 704.5m-n (state-based actions), 502.3 (untap step)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.combat import attack_problem
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import pass_until_stack_empty


def build(cards, *names):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def named(s, name):
    return next(c for c in s.state.cards.values() if c.name == name)


def to_hand(s, name):
    card = named(s, name)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "hand"})
    return card


def token(s, pid, name, pt="2/2", text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": p,
                                                         "toughness": t, "text": text})
    return named(s, name)


def ch(s, card):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id])


def mana(s, **m):
    act(s, "p1", type="add_mana", player="p1", mana=m)


def test_aura_targets_as_cast_and_enters_attached(cards):
    s = build(cards, "Holy Strength")
    bear = token(s, "p1", "Bear")
    aura = to_hand(s, "Holy Strength")
    mana(s, W=1)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bear.id])
    assert s.state.rules.aura_targets[aura.id].id == bear.id  # 303.4a: it targets as it's cast
    pass_until_stack_empty(s)
    assert s.state.cards[aura.id].zone == "p1:battlefield" and s.state.cards[aura.id].attached_to == bear.id
    assert ch(s, bear).pt == (3, 4)  # "Enchanted creature gets +1/+2."


def test_aura_asks_for_a_target(cards):
    s = build(cards, "Holy Strength")
    bear = token(s, "p1", "Bear")
    aura = to_hand(s, "Holy Strength")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id)
    d = s.state.rules.decision
    assert d.resume["step"] == "cast_target" and bear.id in {o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bear.id])
    pass_until_stack_empty(s)
    assert s.state.cards[aura.id].attached_to == bear.id


def test_aura_with_an_illegal_target_goes_to_the_graveyard(cards):
    """608.2b / 303.4g: the target left before resolution: the Aura spell doesn't resolve."""
    s = build(cards, "Holy Strength")
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    bear = token(s, "p1", "Bear")
    goat = token(s, "p1", "Goat")
    aura = to_hand(s, "Holy Strength")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bear.id])
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})  # (a token: it's gone)
    pass_until_stack_empty(s)
    assert s.state.cards[aura.id].zone == "p1:graveyard" and s.state.cards[aura.id].attached_to is None
    assert ch(s, goat).pt == (2, 2)


def test_aura_obeys_hexproof(cards):
    s = build(cards, "Holy Strength")
    hidden = token(s, "p2", "Hidden", text="Hexproof")
    aura = to_hand(s, "Holy Strength")
    mana(s, W=1)
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p1", type="cast_spell", card_id=aura.id, targets=[hidden.id])


def test_pacifism_stops_attacks_and_blocks(cards):
    s = build(cards, "Pacifism")
    ogre = token(s, "p1", "Ogre", "3/3")
    aura = to_hand(s, "Pacifism")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[ogre.id])
    pass_until_stack_empty(s)
    c = ch(s, ogre)
    assert "cant_attack_or_block" in c.imposed
    assert "can't attack" in (attack_problem(s.state, s.state.cards[ogre.id], c) or "")
    act(s, "p1", type="move", card_ids=[aura.id], to={"zone": "graveyard"})  # the Aura is gone: it can again
    assert not ch(s, ogre).imposed


def test_aura_falls_off_when_its_creature_leaves(cards):
    s = build(cards, "Holy Strength")
    bear = token(s, "p1", "Bear")
    aura = to_hand(s, "Holy Strength")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bear.id])
    pass_until_stack_empty(s)
    act(s, "p1", type="set_damage", card_ids=[bear.id], value=5)
    act(s, "p1", type="pass_priority")  # state-based actions: the Bear dies, then the Aura (704.5m)
    assert s.state.cards[aura.id].zone == "p1:graveyard"


def test_doesnt_untap_during_the_untap_step(cards):
    s = build(cards, "Test Frozen Aura")
    ogre = token(s, "p2", "Ogre", "3/3")
    act(s, "p2", type="tap", card_ids=[ogre.id], tapped=True)
    aura = to_hand(s, "Test Frozen Aura")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[ogre.id])
    pass_until_stack_empty(s)
    assert s.state.cards[aura.id].attached_to == ogre.id
    act(s, "p1", type="pass_priority", until="next_turn")
    for _ in range(12):
        if s.state.turn.active_player == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.active_player == "p2"
    assert s.state.cards[ogre.id].tapped  # 502.3: it stayed tapped


def test_equip_attaches_at_sorcery_speed(cards):
    s = build(cards, "Bonesplitter")
    bear = token(s, "p1", "Bear")
    goat = token(s, "p1", "Goat")
    other = token(s, "p2", "Theirs")
    splitter = named(s, "Bonesplitter")
    act(s, "p1", type="move", card_ids=[splitter.id], to={"zone": "battlefield"})
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=splitter.id, ability=1, targets=[other.id])  # not yours
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=splitter.id, ability=1, targets=[bear.id])
    pass_until_stack_empty(s)
    assert s.state.cards[splitter.id].attached_to == bear.id and ch(s, bear).pt == (4, 2)
    act(s, "p1", type="activate_ability", card_id=splitter.id, ability=1, targets=[goat.id])  # move it
    pass_until_stack_empty(s)
    assert s.state.cards[splitter.id].attached_to == goat.id
    assert ch(s, bear).pt == (2, 2) and ch(s, goat).pt == (4, 2)


def test_equip_only_as_a_sorcery(cards):
    s = build(cards, "Bonesplitter")
    bear = token(s, "p1", "Bear")
    splitter = named(s, "Bonesplitter")
    act(s, "p1", type="move", card_ids=[splitter.id], to={"zone": "battlefield"})
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    holy = named(s, "Forest")
    act(s, "p1", type="move", card_ids=[holy.id], to={"zone": "battlefield"})
    mana(s, C=1)
    act(s, "p1", type="phase", to="begin_combat")  # not a main phase
    with pytest.raises(ActionError, match="main phase"):
        act(s, "p1", type="activate_ability", card_id=splitter.id, ability=1, targets=[bear.id])


def test_equipment_stays_when_its_creature_dies(cards):
    s = build(cards, "Behemoth Sledge")
    bear = token(s, "p1", "Bear")
    sledge = named(s, "Behemoth Sledge")
    act(s, "p1", type="move", card_ids=[sledge.id], to={"zone": "battlefield"})
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=sledge.id, ability=1, targets=[bear.id])
    pass_until_stack_empty(s)
    c = ch(s, bear)
    assert c.pt == (4, 4) and {"trample", "lifelink"} <= c.keywords
    act(s, "p1", type="set_damage", card_ids=[bear.id], value=9)
    act(s, "p1", type="pass_priority")
    assert s.state.cards[sledge.id].zone == "p1:battlefield" and s.state.cards[sledge.id].attached_to is None  # 704.5n


def test_coverage_of_auras_and_equipment(cards):
    from app.rules.characteristics import printed_from_data

    for name in ("Holy Strength", "Pacifism", "Bonesplitter", "Behemoth Sledge", "Test Frozen Aura"):
        data = cards.get(cards.resolve(name)["id"])
        assert coverage.of_characteristics(printed_from_data(data)).level == "FULL", name
    assert zone  # (helpers import)
