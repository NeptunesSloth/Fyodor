"""Ninjutsu reductions change only generic mana, retaining the return cost (602.2b)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import casting, coverage, ninjutsu
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_conditionals import settle, token_of, until
from tests.test_rules_wave6c_tokens_pumps import build, mana, pt, put, to_hand
from tests.test_rules_wave6e_statics import attack_with
from tests.test_rules_wave15e_keywords import check, next_own_turn


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/silver_fur_master_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Silver-Fur Master')).level == 'FULL'


@pytest.mark.parametrize('masters', [0, 1, 2])
def test_actual_ninjutsu_payment_and_unblocked_return_cost(cards, masters):
    s = build(cards, 'Ninja of the Deep Hours', *(['Silver-Fur Master'] * masters))
    ninja = to_hand(s, 'Ninja of the Deep Hours')
    for c in list(s.state.cards.values()):
        if c.owner == 'p1' and c.name == 'Silver-Fur Master':
            act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
    attacker = token_of(s, 'p1', 'Rat', 'Token Creature — Rat', '1/1')
    token_of(s, 'p2', 'Wall', 'Token Creature — Wall', '0/4')
    act(s, 'p1', type='set_prefs', stops_my_turn=['main1', 'declare_blockers', 'main2'])
    next_own_turn(s)
    attack_with(s, attacker)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_blockers')
    mana(s, U=1, C=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=ninja.id, ability=0)
    act(s, 'p2', type='declare_blockers', blocks=[])
    act(s, 'p1', type='activate_ability', card_id=ninja.id, ability=0)
    d = s.state.rules.decision
    if d:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[attacker.id])
    settle(s)
    assert mana_pool(s, 'p1').get('C', 0) == (1 if masters else 0)
    now = s.state.cards[ninja.id]
    assert now.zone == 'p1:battlefield' and now.tapped and now.attacking.id == 'p2'
    assert attacker.id not in s.state.zones['p1:battlefield']
    assert pt(s, now) == (2 + masters, 2 + masters)
    check(s)


def test_color_symbols_ordinary_abilities_and_other_controller_unchanged(cards):
    s = build(cards, 'Silver-Fur Master', 'Azure Mage', 'Ninja of the Deep Hours')
    master = put(s, 'Silver-Fur Master')
    ninja = to_hand(s, 'Ninja of the Deep Hours')
    mage = put(s, 'Azure Mage')
    plan = Plan(s.state, 'p1', s.cards, None)
    ch = plan.ch(master)
    synthetic = ninjutsu.ability(ch, 0, '{U}{B}')
    assert casting.ability_cost(ch, synthetic, state=s.state, card=master, info=plan.info).mana == '{U}{B}'
    ch = plan.ch(mage)
    ab = next(a for a in ch.abilities if a.kind == 'activated')
    assert casting.ability_cost(ch, ab, state=s.state, card=mage, info=plan.info).mana == '{3}{U}'
    act(s, 'p1', type='move', card_ids=[master.id], to={'player': 'p2', 'zone': 'battlefield'})
    # Moving to another battlefield does not itself change control; use the game action.
    act(s, 'p1', type='set_controller', card_ids=[master.id], player='p2')
    plan = Plan(s.state, 'p1', s.cards, None)
    ch = plan.ch(ninja)
    ab = ninjutsu.ability(ch, 0, '{1}{U}')
    assert casting.ability_cost(ch, ab, state=s.state, card=ninja, info=plan.info).mana == '{1}{U}'
    check(s)


def test_ability_removal_stops_reduction_and_does_not_remove_hand_ninjutsu(cards):
    s = build(cards, 'Silver-Fur Master', 'Ninja of the Deep Hours', 'Dress Down')
    master = put(s, 'Silver-Fur Master')
    ninja = to_hand(s, 'Ninja of the Deep Hours')
    dress = to_hand(s, 'Dress Down')
    plan = Plan(s.state, 'p1', s.cards, None)
    ch = plan.ch(ninja)
    ab = ninjutsu.ability(ch, 0, '{1}{U}')
    assert casting.ability_cost(ch, ab, state=s.state, card=ninja, info=plan.info).mana == '{U}'
    mana(s, U=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=dress.id, targets=[])
    settle(s)
    plan = Plan(s.state, 'p1', s.cards, None)
    ch = plan.ch(ninja)
    assert ninjutsu.cost_of(ch, 0) == '{1}{U}'
    assert casting.ability_cost(ch, ab, state=s.state, card=ninja, info=plan.info).mana == '{1}{U}'
    assert not plan.ch(s.state.cards[master.id]).abilities
    check(s)
