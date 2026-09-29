"""Keyword actions (CR 701) carried out by app/rules/keyword_actions.py: the wording each one is
called by (app/rules/scripts.py) and the table after it resolves — amass (701.47), connive
(701.50), monstrosity (701.37), bolster (701.39), support (701.41). Every scenario also checks
that replaying the recorded history reproduces the table exactly."""

from __future__ import annotations

import json

import pytest

from app.rules import scripts
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, named, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches

OTHER_CREATURE = 'sel:{"other":true,"types":["Creature"]}'


# -- parsing ------------------------------------------------------------------------------
@pytest.mark.parametrize(("text", "effects", "target"), [
    ("Amass Orcs 2.", [{"do": "amass", "sub": "Orc", "n": 2}], None),
    ("Amass Zombies 1.", [{"do": "amass", "sub": "Zombie", "n": 1}], None),
    ("Amass Elves X.", [{"do": "amass", "sub": "Elf", "n": {"x": 1}}], None),
    ("Monstrosity 3.", [{"do": "monstrosity", "n": 3}], None),
    ("Bolster 2.", [{"do": "bolster", "n": 2}], None),
    ("Target creature you control connives.", [{"do": "connive", "who": "target", "n": 1}], "creature_you_control"),
    ("Target creature connives 2.", [{"do": "connive", "who": "target", "n": 2}], "creature"),
    ("Support 2.", [{"do": "add_counters", "who": "target:0", "kind": "+1/+1", "n": 1}],
     [{"what": OTHER_CREATURE, "min": 0, "max": 2}]),
])
def test_parse_keyword_actions(text, effects, target):
    assert scripts.parse_effects(text) == (effects, target, False)


def test_connive_pronouns_name_the_source():
    d = scripts.definitions(_ch("Toluz", "Creature — Human", "When Toluz enters, it connives."))
    assert d[0]["effects"] == [{"do": "connive", "who": "self", "n": 1}]
    d = scripts.definitions(_ch("Tiger Shark", "Creature — Shark", "Whenever Tiger Shark attacks, he connives."))
    assert d[0]["effects"] == [{"do": "connive", "who": "self", "n": 1}]
    d = scripts.definitions(_ch("Cyclops", "Creature — Cyclops", "{5}{R}: Monstrosity 3."))
    assert d[0] == {"kind": "activated", "cost": "{5}{R}", "effects": [{"do": "monstrosity", "n": 3}], "target": None}


@pytest.mark.parametrize("text", [
    "Amass Foo 2.",  # not a creature type
    "Amass Orcs X, where X is that spell's mana value.",  # (the rider isn't understood here)
    "Goad target creature.",  # 701.15: combat requirements the engine doesn't model
    "Earthbend 2.",  # 701.66: its delayed return trigger isn't modeled
    "Incubate 3.",  # 701.53: the Incubator can't transform
])
def test_unsupported_keyword_actions_stay_manual(text):
    assert scripts.parse_effects(text) is None


def _ch(name, type_line, text):
    from app.rules import oracle
    from app.rules.characteristics import Characteristics, parse_type_line

    sup, types, sub = parse_type_line(type_line)
    return Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, oracle_text=text,
                           abilities=tuple(oracle.parse_abilities(text)))


# -- scenarios ----------------------------------------------------------------------------
def activate(s, card, pid="p1", **kw):
    act(s, pid, type="add_mana", player=pid, mana={"C": 1})
    act(s, pid, type="activate_ability", card_id=card.id, ability=0, **kw)
    pass_until_stack_empty(s)


def decision(s):
    return s.state.rules.decision


def armies(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == pid
            and "Army" in (c.token.type_line if c.token else "")]


def test_amass_creates_an_army_then_grows_it(cards):
    s = build(cards)
    src = token(s, "p1", "Warlord", text="{1}: Amass Orcs 2.")
    activate(s, src)
    (army,) = armies(s)  # 701.47a: no Army → a 0/0 black Orc Army token, then the counters
    assert army.token.type_line == "Token Creature — Orc Army" and army.token.colors == ["B"]
    assert (army.token.power, army.token.toughness) == ("0", "0") and army.counters == {"+1/+1": 2}
    activate(s, src)
    assert len(armies(s)) == 1 and armies(s)[0].counters == {"+1/+1": 4}  # an Army exists: no new token
    replay_matches(s)


def test_amass_with_several_armies_is_the_controllers_choice(cards):
    s = build(cards)
    src = token(s, "p1", "Warlord", text="{1}: Amass Orcs 1.")
    activate(s, src)
    activate(s, src)
    # a second Army by hand (another amass source would find the first): now there's a choice
    act(s, "p1", type="create_token", player="p1", token={"name": "Zombie Army", "type_line": "Token Creature — Zombie Army",
                                                          "power": "0", "toughness": "0", "colors": ["B"]})
    act(s, "p1", type="counter", card_ids=[named(s, "Zombie Army").id], kind="+1/+1", delta=1)
    activate(s, src)
    d = decision(s)
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {a.id for a in armies(s)}
    assert "options" not in s.view("p2")["rules"]["decision"]  # Bob only sees that Alice is choosing
    zombie = named(s, "Zombie Army")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[zombie.id])
    assert s.state.cards[zombie.id].counters == {"+1/+1": 2} and named(s, "Orc Army").counters == {"+1/+1": 2}
    assert len(armies(s)) == 2
    replay_matches(s)


def test_monstrosity_happens_once(cards):
    s = build(cards)
    cyclops = token(s, "p1", "Cyclops", "3/3", text="{1}: Monstrosity 3.")
    activate(s, cyclops)
    assert s.state.cards[cyclops.id].counters == {"+1/+1": 3}
    assert s.state.rules.object_id(cyclops.id) in s.state.rules.monstrous
    activate(s, cyclops)  # 701.37a: it is monstrous already: nothing
    assert s.state.cards[cyclops.id].counters == {"+1/+1": 3}
    assert "already monstrous" in json.dumps(s.view("p2")["log"])
    replay_matches(s)


def test_bolster_picks_the_least_toughness(cards):
    s = build(cards)
    token(s, "p1", "Big", "4/4")
    small = token(s, "p1", "Small", "1/1")
    token(s, "p2", "Theirs", "0/1")  # (an opponent's creature doesn't count)
    src = token(s, "p1", "Captain", "2/2", text="{1}: Bolster 2.")
    activate(s, src)
    assert s.state.cards[small.id].counters == {"+1/+1": 2}
    assert decision(s) is None and named(s, "Big").counters == {} and named(s, "Theirs").counters == {}
    replay_matches(s)


def test_bolster_tie_is_the_controllers_private_choice(cards):
    s = build(cards)
    a = token(s, "p1", "A", "2/2")
    b = token(s, "p1", "B", "3/2")
    src = token(s, "p1", "Captain", "5/5", text="{1}: Bolster 1.")
    activate(s, src)
    d = decision(s)
    assert d is not None and d.player == "p1" and d.kind == "choose_cards" and {o.id for o in d.options} == {a.id, b.id}
    assert "options" not in s.view("p2")["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[b.id])
    assert s.state.cards[b.id].counters == {"+1/+1": 1} and s.state.cards[a.id].counters == {}
    replay_matches(s)


def test_support_puts_counters_on_up_to_n_other_creatures(cards):
    s = build(cards)
    a = token(s, "p1", "A")
    b = token(s, "p2", "B")
    src = token(s, "p1", "Auxiliary", text="{1}: Support 2.")
    activate(s, src, targets=[a.id, b.id], target_counts=[2])
    assert s.state.cards[a.id].counters == {"+1/+1": 1} and s.state.cards[b.id].counters == {"+1/+1": 1}
    assert s.state.cards[src.id].counters == {}  # 701.41a: "other" target creatures
    activate(s, src, targets=[], target_counts=[0])  # "up to": none is fine
    assert s.state.cards[a.id].counters == {"+1/+1": 1}
    replay_matches(s)


def test_connive_draws_then_discards_privately_and_counts_nonland(cards):
    s = build(cards, "Sol Ring", "Lightning Bolt")
    act(s, "p1", type="draw", count=3)  # (hands start empty at this table): Sol Ring, Lightning Bolt, a Forest
    hand_before = list(zone(s.state, "p1", "hand"))
    src = token(s, "p1", "Conniver", text="{1}: This creature connives.")
    activate(s, src)
    hand = zone(s.state, "p1", "hand")
    assert len(hand) == len(hand_before) + 1  # 701.50a: draw a card, then …
    d = decision(s)
    assert d is not None and d.player == "p1" and d.min_choices == d.max_choices == 1
    assert {o.id for o in d.options} == set(hand)
    bob = json.dumps(s.view("p2"))
    for cid in hand:  # nobody else learns what's in the hand
        assert cid not in bob and s.state.cards[cid].name not in bob
    nonland = next(c for c in hand if not s.cards.resolve(s.state.cards[c].name)["type_line"].startswith("Basic Land"))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[nonland])
    assert s.state.cards[nonland].zone == "p1:graveyard" and s.state.cards[src.id].counters == {"+1/+1": 1}
    activate(s, src)
    d = decision(s)
    forest = next(o.id for o in d.options if s.state.cards[o.id].name == "Forest")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[forest])
    assert s.state.cards[src.id].counters == {"+1/+1": 1}  # a land: no counter
    replay_matches(s)


def test_target_creature_connives_by_its_controller(cards):
    s = build(cards)
    act(s, "p2", type="draw", player="p2", count=2)
    theirs = token(s, "p2", "Theirs")
    src = token(s, "p1", "Lookout", text="{1}: Target creature connives.")
    bob_hand = len(zone(s.state, "p2", "hand"))
    activate(s, src, targets=[theirs.id])
    d = decision(s)
    assert len(zone(s.state, "p2", "hand")) == bob_hand + 1  # 701.50a: the permanent's controller draws
    assert d is not None and d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    replay_matches(s)
