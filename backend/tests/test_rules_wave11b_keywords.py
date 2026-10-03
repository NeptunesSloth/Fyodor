"""Wave 11B: keywords carried out as their Comprehensive Rules definition (CR 2026-09-25).

* Living weapon (702.92a) and For Mirrodin! (702.163a): an enters trigger making a token and attaching to it.
* Annihilator N (702.86a) and afflict N (702.130a): attack / becomes-blocked triggers (each instance separately).
* Ravenous (702.156a): enters with X +1/+1 counters, and draws if X is 5 or more (X is 0 when not cast, 107.3m).
* Outlast [cost] (702.107a): "[Cost], {T}: Put a +1/+1 counter on this creature. Activate only as a sorcery."

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of, until
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import build, mana, pt, put, reloaded, to_hand, tokens
from tests.test_rules_wave6e_statics import attack_with

EXTRA = [
    card('Merciless Eternal', set_code='tst', number='W00', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Zombie Cleric', oracle_text='Afflict 2 (Whenever this creature becomes blocked, defending player loses 2 life.)\n{2}{B}, Discard a card: This creature gets +2/+2 until end of turn.', power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=['Afflict']),  # noqa: E501
    card('Flayer Husk', set_code='tst', number='W01', mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment', oracle_text='Living weapon (When this Equipment enters, create a 0/0 black Phyrexian Germ creature token, then attach this to it.)\nEquipped creature gets +1/+1.\nEquip {2}', power=None, toughness=None, colors=[], color_identity=[], keywords=['Equip', 'Living weapon']),  # noqa: E501
    card('Abzan Falconer', set_code='tst', number='W02', mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Human Soldier', oracle_text='Outlast {W} ({W}, {T}: Put a +1/+1 counter on this creature. Outlast only as a sorcery.)\nEach creature you control with a +1/+1 counter on it has flying.', power='2', toughness='3', colors=['W'], color_identity=['W'], keywords=['Outlast']),  # noqa: E501
    card('Jacked Rabbit', set_code='tst', number='W03', mana_cost='{X}{1}{W}', cmc=2.0, type_line='Creature — Rabbit Warrior', oracle_text="Ravenous (This creature enters with X +1/+1 counters on it. If X is 5 or more, draw a card when it enters.)\nWhenever this creature attacks, create a number of 1/1 white Rabbit creature tokens equal to this creature's power.", power='1', toughness='2', colors=['W'], color_identity=['W'], keywords=['Ravenous']),  # noqa: E501
    card('Pathrazer of Ulamog', set_code='tst', number='W04', mana_cost='{11}', cmc=11.0, type_line='Creature — Eldrazi', oracle_text="Annihilator 3 (Whenever this creature attacks, defending player sacrifices three permanents of their choice.)\nThis creature can't be blocked except by three or more creatures.", power='9', toughness='9', colors=[], color_identity=[], keywords=['Annihilator']),  # noqa: E501
    card('Exocrine', set_code='tst', number='W05', mana_cost='{X}{2}{R}', cmc=3.0, type_line='Creature — Tyranid', oracle_text='Ravenous (This creature enters with X +1/+1 counters on it. If X is 5 or more, draw a card when it enters.)\nBio-plasmic Barrage — When this creature enters, it deals X damage to each player and each other creature.', power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=['Ravenous', 'Bio-plasmic Barrage']),  # noqa: E501
    card("Goldwarden's Helm", set_code='tst', number='W06', mana_cost='{2}{W}', cmc=3.0, type_line='Artifact — Equipment', oracle_text='For Mirrodin! (When this Equipment enters, create a 2/2 red Rebel creature token, then attach this to it.)\nEquipped creature gets +0/+1.\nEquip {1}{W} ({1}{W}: Attach to target creature you control. Equip only as a sorcery.)', power=None, toughness=None, colors=['W'], color_identity=['W'], keywords=['For Mirrodin!', 'Equip']),  # noqa: E501
]
FULL = [c["name"] if isinstance(c, dict) else c.name for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def cast_card(s, name, **kw):
    c = to_hand(s, name)
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    settle(s)
    return c


def test_living_weapon_makes_an_equipped_germ(cards):
    s = build(cards, "Flayer Husk")
    mana(s, C=1)
    husk = cast_card(s, "Flayer Husk")
    (germ,) = tokens(s)
    assert germ.name == "Phyrexian Germ" and s.state.cards[husk.id].attached_to == germ.id
    assert pt(s, germ) == (1, 1)  # a 0/0 with Flayer Husk's +1/+1
    check(s)


def test_for_mirrodin_makes_an_equipped_rebel(cards):
    s = build(cards, "Goldwarden's Helm")
    mana(s, W=1, C=2)
    helm = cast_card(s, "Goldwarden's Helm")
    (rebel,) = tokens(s)
    assert rebel.name == "Rebel" and s.state.cards[helm.id].attached_to == rebel.id
    assert pt(s, rebel) == (2, 3)  # 2/2 and the Helm's +0/+1
    check(s)


@pytest.mark.parametrize(("x", "draws"), [(5, 1), (2, 0)])
def test_ravenous_counters_and_draw(cards, x, draws):
    s = build(cards, "Jacked Rabbit")
    hand = len(s.state.zones["p1:hand"])
    mana(s, W=1, C=1 + x)
    rabbit = cast_card(s, "Jacked Rabbit", x_value=x)
    assert s.state.cards[rabbit.id].counters.get("+1/+1", 0) == x  # 702.156a
    assert len(s.state.zones["p1:hand"]) == hand + draws  # the card is gone from hand, X >= 5 draws one
    check(s)


def test_ravenous_not_cast_enters_with_no_counters(cards):
    s = build(cards, "Jacked Rabbit")
    rabbit = put(s, "Jacked Rabbit")
    assert s.state.cards[rabbit.id].counters.get("+1/+1", 0) == 0  # 107.3m: X is 0
    check(s)


def next_own_turn(s):
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")


def test_outlast_is_a_sorcery_speed_tap_ability(cards):
    s = build(cards, "Abzan Falconer")
    falconer = put(s, "Abzan Falconer")
    mana(s, W=1)
    with pytest.raises(Exception, match="summoning sickness"):
        act(s, "p1", type="activate_ability", card_id=falconer.id, ability=0)
    next_own_turn(s)
    mana(s, W=1)
    act(s, "p1", type="activate_ability", card_id=falconer.id, ability=0)
    settle(s)
    c = s.state.cards[falconer.id]
    assert c.counters.get("+1/+1") == 1 and c.tapped  # {W}, {T}: a +1/+1 counter
    check(s)


def test_annihilator_defender_sacrifices_n_permanents(cards):
    s = build(cards, "Pathrazer of Ulamog")
    for i in range(5):
        token_of(s, "p2", f"Rock{i}", "Token Artifact — Rock", "0/0")
    pathrazer = put(s, "Pathrazer of Ulamog")
    next_own_turn(s)
    before = len(s.state.zones["p2:battlefield"])
    attack_with(s, pathrazer)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p2")
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])
    settle(s)
    assert len(s.state.zones["p2:battlefield"]) == before - 3  # annihilator 3
    check(s)


def test_afflict_triggers_once_when_blocked(cards):
    s = build(cards, "Merciless Eternal")
    eternal = put(s, "Merciless Eternal")
    b1 = token_of(s, "p2", "Wall A", "Token Creature — Wall", "0/4")
    b2 = token_of(s, "p2", "Wall B", "Token Creature — Wall", "0/4")
    next_own_turn(s)
    attack_with(s, eternal)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    life = s.state.players["p2"].life
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b1.id, "attacker_id": eternal.id},
                                                 {"blocker_id": b2.id, "attacker_id": eternal.id}])
    settle(s)
    assert s.state.players["p2"].life == life - 2  # afflict 2, once
    check(s)
