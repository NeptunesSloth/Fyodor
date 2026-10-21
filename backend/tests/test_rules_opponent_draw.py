"""CR 608.2d, 118.9a: a chosen opponent draws without being targeted."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/opponent_draw_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Baleful Mastery'


def test_mastery_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Omniscience', 'Notion Thief', 'Witchbane Orb'], ['Grizzly Bears', 'Counterspell', 'Narset, Parter of Veils'], ['Grizzly Bears'])
    spell = put(s, NAME, 'hand')
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    return s, spell, victim


@pytest.mark.parametrize('opponent', ['p2', 'p3'])
def test_alternative_cost_chooses_opponent_on_resolution_then_exiles(cards, opponent):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle as finish
    from tests.test_rules_designations import roundtrip, settle

    s, spell, victim = setup(cards)
    hands = {p: len(s.state.zones[p+':hand']) for p in ('p2', 'p3')}
    mana(s, C=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=[victim.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    assert {o.id for o in d.options} == {'p2', 'p3'}
    assert s.state.cards[victim.id].zone == 'p2:battlefield'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[opponent])
    finish(s)
    assert s.state.cards[victim.id].zone == 'p2:exile'
    for p, before in hands.items():
        assert len(s.state.zones[p+':hand']) == before+(p == opponent)
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


@pytest.mark.parametrize('free', [False, True])
def test_normal_and_free_casts_do_not_give_an_opponent_a_card(cards, free):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell, victim = setup(cards)
    if free:
        put(s, 'Omniscience', 'battlefield')
    else:
        mana(s, C=3, B=1)
    hands = {p: len(s.state.zones[p+':hand']) for p in ('p2', 'p3')}
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[victim.id], free=free)
    settle(s)
    assert s.state.cards[victim.id].zone == 'p2:exile'
    assert all(len(s.state.zones[p+':hand']) == n for p, n in hands.items())
    roundtrip(s)


def test_illegal_only_target_prevents_the_draw_as_well(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, victim = setup(cards)
    hands = {p: len(s.state.zones[p+':hand']) for p in ('p2', 'p3')}
    mana(s, C=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=[victim.id])
    act(s, 'p2', type='move', card_ids=[victim.id], to={'player': 'p2', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert all(len(s.state.zones[p+':hand']) == n for p, n in hands.items())
    roundtrip(s)


@pytest.mark.parametrize('replacement', [False, True])
def test_chosen_player_is_not_targeted_and_draw_uses_replacements(cards, replacement):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle as finish
    from tests.test_rules_designations import put, roundtrip, settle

    s, spell, victim = setup(cards)
    orb = put(s, 'Witchbane Orb', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[orb.id], player='p2')
    if replacement:
        put(s, 'Notion Thief', 'battlefield')
    before = {p: len(s.state.zones[p+':hand']) for p in ('p1', 'p2', 'p3')}
    mana(s, C=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=[victim.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and 'p2' in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    finish(s)
    assert len(s.state.zones['p1:hand']) == before['p1']-1+replacement
    assert len(s.state.zones['p2:hand']) == before['p2']+(not replacement)
    assert len(s.state.zones['p3:hand']) == before['p3']
    assert s.state.cards[victim.id].zone == 'p2:exile'
    roundtrip(s)


def test_countering_mastery_prevents_both_draw_and_exile(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell, victim = setup(cards)
    counter = put(s, 'Counterspell', 'hand', 'p2')
    before = len(s.state.zones['p3:hand'])
    mana(s, C=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=[victim.id])
    wait_priority(s, 'p2')
    mana(s, 'p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.cards[victim.id].zone == 'p2:battlefield'
    assert len(s.state.zones['p3:hand']) == before
    roundtrip(s)


def test_single_remaining_opponent_draws_without_a_choice(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, victim = setup(cards)
    act(s, 'p3', type='concede')
    before = len(s.state.zones['p2:hand'])
    mana(s, C=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0', targets=[victim.id])
    settle(s)
    assert len(s.state.zones['p2:hand']) == before+1
    assert s.state.cards[victim.id].zone == 'p2:exile'
    assert s.state.rules.decision is None
    roundtrip(s)
