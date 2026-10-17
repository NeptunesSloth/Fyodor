"""Wave 46C: single-wording gaps of cards played in many decks (CR 2026-09-25), real Oracle text (tests/fixtures/wave46c_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 613.1b, 303.4e: "You control enchanted enchantment." (Steal Enchantment [6463]) - an Aura on a permanent of another type than a creature already took control;
  the enchantment it enchants is the host.
* 506.3, 508.1b: "Exile target creature that's attacking you or a planeswalker you control." (Soul Snare [6643]) - an attacker's target is the player or a planeswalker
  (a battle or another player's planeswalker is no target of it).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave46c_kit import FULL, cast, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def controller(s, c):
    return s.state.cards[c.id].controller


def walker(s, pid="p1", loyalty=5):
    act(s, pid, type="create_token", player=pid, token={"name": "Walker", "type_line": "Token Legendary Planeswalker — Test"})
    w = card_named(s, "Walker", pid)
    act(s, pid, type="counter", card_ids=[w.id], kind="loyalty", delta=loyalty)
    return w


def test_steal_enchantment_takes_control_of_the_enchantment_it_enchants(cards):
    s = build(cards, ["Steal Enchantment"], ["Ghostly Prison"])
    prison = put(s, "Ghostly Prison", "p2")
    to_hand(s, "Steal Enchantment")
    mana(s, U=2, C=2)
    cast(s, "Steal Enchantment", targets=[prison.id])
    assert controller(s, prison) == "p1"  # 613.1b: layer 2
    check(s)


def attack_at(s, attacker, target):
    """Bob's declare attackers step (turn 2), this attacker declared at that target."""
    stops(s)
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": target}])
    act(s, "p2", type="pass_priority")  # (the active player first, then Alice has priority)


def test_soul_snare_exiles_a_creature_attacking_a_planeswalker_you_control(cards):
    s = build(cards, ["Soul Snare"], ["Grizzly Bears"])
    snare = put(s, "Soul Snare")
    bears = put(s, "Grizzly Bears", "p2")
    w = walker(s)
    attack_at(s, bears, w.id)
    mana(s, W=1)
    activate(s, "p1", snare, targets=[bears.id])
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile" and zone_of(s, "Soul Snare") == "p1:graveyard"
    check(s)


def test_soul_snare_exiles_a_creature_attacking_you(cards):
    s = build(cards, ["Soul Snare"], ["Grizzly Bears"])
    snare = put(s, "Soul Snare")
    bears = put(s, "Grizzly Bears", "p2")
    attack_at(s, bears, "p1")
    mana(s, W=1)
    activate(s, "p1", snare, targets=[bears.id])
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile"
    check(s)


def test_soul_snare_cannot_target_a_creature_attacking_the_opponent(cards):
    s = build(cards, ["Soul Snare", "Hill Giant"], [])
    snare, giant = put(s, "Soul Snare"), put(s, "Hill Giant")
    stops(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p2"}])
    mana(s, W=1)
    with pytest.raises(ActionError):
        activate(s, "p1", snare, targets=[giant.id])  # it attacks Bob, not Alice or a planeswalker of hers
    check(s)


def equip_to(s, equipment, creature, pid="p1"):
    index = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[equipment.id]).abilities if "equip" in a.keywords)
    act(s, pid, type="activate_ability", card_id=equipment.id, ability=index, targets=[creature.id])
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")


def attached_to(s, equipment):
    return s.state.cards[equipment.id].attached_to


def test_helitrooper_makes_equip_abilities_that_target_it_cost_less_but_not_others(cards):
    # 601.2c, 601.2f: Loxodon Warhammer's Equip {3} costs {2} less when it targets Helitrooper ("Equip abilities you activate that target this creature")
    s = build(cards, ["Helitrooper", "Hill Giant", "Loxodon Warhammer"], [])
    trooper, giant, hammer = put(s, "Helitrooper"), put(s, "Hill Giant"), put(s, "Loxodon Warhammer")
    mana(s, C=1)
    with pytest.raises(ActionError):
        equip_to(s, hammer, giant)  # the Giant is not the Helitrooper: {3}
    equip_to(s, hammer, trooper)
    assert attached_to(s, hammer) == trooper.id and s.state.players["p1"].mana.get("C", 0) == 0
    check(s)


def test_bladegraft_aspirant_reduces_the_activated_abilities_of_equipment_that_target_it(cards):
    s = build(cards, ["Bladegraft Aspirant", "Loxodon Warhammer"], [])
    aspirant, hammer = put(s, "Bladegraft Aspirant"), put(s, "Loxodon Warhammer")
    mana(s, C=2)
    equip_to(s, hammer, aspirant)  # {3} less {1}
    assert attached_to(s, hammer) == aspirant.id
    check(s)
