"""Wave 110I session 14.

* Wayta, Trainer Prodigy: "a creature you control being dealt damage" makes the triggers of that damage trigger an additional time (603.2d; the fight's cost drops by {2} when both targets are creatures you control (601.2f).
* Spoils of War: {X}{B}; X is the number of artifact and/or creature cards in the opponent chosen as it is cast (ruling 2008-08-01): the announced X names the opponent.
* Acidic Dagger: delayed triggers on the target (603.7): combat damage to a non-Wall creature destroys it; the Dagger is sacrificed when the target leaves; first combat phase only (ruling 2013-09-20).
* Guardian Archon: "Reveal the player you chose" (the entry secret choice, 614.12a) gives you and a permanent you control protection from that player (702.16k) until end of turn; once only.
"""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave110e_cards import cast as cast_card
from tests.test_rules_wave110e_s11 import _three
from tests.test_rules_wave110e_s12 import SHAMAN
from tests.wave9c_kit import card_named, check, mana, put, to_hand
import tests.test_rules_wave110e_cards as base

ARCHON = real("Guardian Archon", "{4}{W}{W}", 6, "Creature — Archon",
              "Flying\nAs this creature enters, secretly choose an opponent.\nReveal the player you chose: You and target permanent you control each gain protection from the chosen player "
              "until end of turn. Activate only once.", ("5", "5"), "W")
base.EXTRA.append(ARCHON)


def test_archon_full(cards):
    assert coverage.of_card_data(cards.resolve("Guardian Archon")).level == "FULL"


def _table(cards, choose):
    s = _three(cards, ["Guardian Archon", "Test Shaman"])
    shaman = put(s, "Test Shaman")
    mana(s, W=2, C=4)
    cast_card(s, "Guardian Archon")
    for _ in range(3):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and "secretly" in d.prompt:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.startswith(choose))])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s, shaman


def _bolt(s, pid, target):
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=to_hand(s, "Test Bolt", pid).id, targets=[target])


@pytest.mark.parametrize("who", ["p2", "p3"])
def test_archon_protects_you_and_the_target_from_the_chosen_player_only(cards, who):
    """Bob was chosen: afterwards Bob can target neither Alice nor her Shaman; Carol still can. The ability is once only (Activate only once)."""
    s, shaman = _table(cards, "Bob")
    archon = card_named(s, "Guardian Archon")
    assert archon.zone == "p1:battlefield"
    act(s, "p1", type="activate_ability", card_id=archon.id, ability=2, targets=[shaman.id])
    answer(s)
    for pid in ("p2", "p3"):
        act(s, pid, type="set_stops", own=[], others=["main1"], smart_pass=False)
    act(s, "p1", type="pass_priority")
    while s.state.rules.priority != who:
        act(s, s.state.rules.priority, type="pass_priority")
    for target in ("p1", shaman.id):
        if who == "p2":
            with pytest.raises(ActionError, match="(?i)target"):
                _bolt(s, who, target)
        else:
            _bolt(s, who, target)
            answer(s)
            assert s.state.players["p1"].life == 37
            break
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=archon.id, ability=2, targets=[shaman.id])
    check(s)


WAYTA = real("Wayta, Trainer Prodigy", "{R}{G}{W}", 3, "Legendary Creature \u2014 Human Warrior",
             "Haste\n{2}{G}, {T}: Target creature you control fights another target creature. This ability costs {2} less to activate if it targets two creatures you control.\n"
             "If a creature you control being dealt damage causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
             ("1", "5"), "RGW")
SPARKY = real("Test Sparky", "{1}{G}", 2, "Creature \u2014 Beast", "Whenever this creature is dealt damage, you gain 1 life.", ("1", "9"), "G")
base.EXTRA.extend([WAYTA, SPARKY])


def test_wayta_full(cards):
    assert coverage.of_card_data(cards.resolve("Wayta, Trainer Prodigy")).level == "FULL"


def _fight(cards, enemy, paid):
    s = _three(cards, ["Wayta, Trainer Prodigy", "Test Sparky", "Test Bear"], carols=("Test Bear",))
    wayta, sparky = put(s, "Wayta, Trainer Prodigy"), put(s, "Test Sparky")
    other = put(s, "Test Bear") if enemy == "mine" else put(s, "Test Bear", "p3")
    mana(s, G=1, C=paid - 1)
    act(s, "p1", type="activate_ability", card_id=wayta.id, ability=1, targets=[sparky.id, other.id], target_counts=[1, 1])
    answer(s)
    return s, wayta


@pytest.mark.parametrize(("enemy", "paid", "gained"), [("mine", 1, 2), ("theirs", 3, 2)])
def test_wayta_fight_costs_two_less_with_two_of_your_creatures_and_doubles_the_damage_triggers(cards, enemy, paid, gained):
    """{G} suffices for two creatures you control; {2}{G} is needed against Bob's. Sparky is dealt damage once: its trigger happens twice (Wayta)."""
    s, wayta = _fight(cards, enemy, paid)
    assert wayta.tapped and s.state.players["p1"].life == 40 + gained
    check(s)


def test_wayta_fight_against_an_opposing_creature_cannot_be_paid_with_the_discount(cards):
    with pytest.raises(ActionError):
        _fight(cards, "theirs", 1)


SPOILS = real("Spoils of War", "{X}{B}", 1, "Sorcery",
              "X is the number of artifact and/or creature cards in an opponent's graveyard as you cast this spell.\nDistribute X +1/+1 counters among any number of target creatures.", None, "B")
base.EXTRA.append(SPOILS)


def test_spoils_full(cards):
    assert coverage.of_card_data(cards.resolve("Spoils of War")).level == "FULL"


def _spoils(cards, x):
    """Bob's graveyard holds one creature card, Carol's two (Bear, Giant) and a Bolt: X may be 1 or 2, naming the opponent."""
    s = _three(cards, ["Spoils of War", "Test Bear"], carols=("Test Bear", "Test Giant", "Test Bolt"))
    for name, pid in (("Test Giant", "p2"), ("Test Bear", "p3"), ("Test Giant", "p3"), ("Test Bolt", "p3")):
        act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"player": pid, "zone": "graveyard"})
    bear = put(s, "Test Bear")
    mana(s, B=1, C=x)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Spoils of War").id, targets=[bear.id], target_counts=[1], x_value=x)
    answer(s)
    return s, bear


@pytest.mark.parametrize("x", [1, 2])
def test_spoils_counters_equal_the_chosen_opponents_cards(cards, x):
    s, bear = _spoils(cards, x)
    assert s.state.cards[bear.id].counters.get("+1/+1") == x
    check(s)


@pytest.mark.parametrize("x", [0, 3])
def test_spoils_x_must_name_an_opponent(cards, x):
    with pytest.raises(ActionError):
        _spoils(cards, x)


DAGGER = real("Acidic Dagger", "{4}", 4, "Artifact",
              "{4}, {T}: Whenever target creature deals combat damage to a non-Wall creature this turn, destroy that non-Wall creature. When the targeted creature leaves the battlefield this turn, "
              "sacrifice this artifact. Activate only before blockers are declared.", None)
WALL = real("Wall110I", "{2}{W}", 3, "Creature \u2014 Wall", "", ("0", "9"), "W")
FANG = real("Fang110I", "{2}{R}", 3, "Creature \u2014 Wolf", "", ("3", "3"), "R")
GIANT = real("Giant110I", "{2}{G}", 3, "Creature \u2014 Giant", "", ("0", "9"), "G")
BEAR = real("Bear110I", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G")
base.EXTRA.extend([DAGGER, WALL, GIANT, BEAR, FANG])


def test_dagger_full(cards):
    assert coverage.of_card_data(cards.resolve("Acidic Dagger")).level == "FULL"


def _dagger_game(cards, blocker):
    from tests.test_rules_conditionals import until
    from tests.test_rules_wave43d_cast_keywords import connect
    from tests.wave9c_kit import build

    s = build(cards, ["Acidic Dagger", "Bear110I"], ["Wall110I", "Giant110I", "Fang110I"], forests=25, islands=25)
    dagger, bear, foe = put(s, "Acidic Dagger"), put(s, "Bear110I"), put(s, blocker, "p2")
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None and s.state.turn.active_player == "p1")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=dagger.id, ability=0, targets=[bear.id])
    answer(s)
    connect(s, bear, block=(foe, bear))
    return s, dagger, bear, foe


@pytest.mark.parametrize(("blocker", "dies"), [("Giant110I", True), ("Wall110I", False)])
def test_dagger_destroys_only_a_non_wall_creature_dealt_combat_damage_by_the_target(cards, blocker, dies):
    s, dagger, bear, foe = _dagger_game(cards, blocker)
    assert s.state.cards[foe.id].zone.endswith(":graveyard") == dies
    assert s.state.cards[dagger.id].zone == "p1:battlefield"
    check(s)


def test_dagger_is_sacrificed_when_the_target_leaves_the_battlefield(cards):
    """Bob's Fang blocks and kills the targeted Bear: when it leaves, Alice sacrifices the Dagger."""
    s, dagger, bear, foe = _dagger_game(cards, "Fang110I")
    assert s.state.cards[bear.id].zone == "p1:graveyard" and s.state.cards[dagger.id].zone == "p1:graveyard"
    check(s)


def test_dagger_not_after_combat(cards):
    from tests.test_rules_conditionals import until
    from tests.wave9c_kit import build

    s = build(cards, ["Acidic Dagger", "Bear110I"], ["Giant110I"], forests=25, islands=25)
    dagger, bear = put(s, "Acidic Dagger"), put(s, "Bear110I")
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main2" and s.state.rules.decision is None and s.state.turn.active_player == "p1")
    mana(s, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=dagger.id, ability=0, targets=[bear.id])
