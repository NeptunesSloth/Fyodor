"""Canonical collateral validation of three global Way loyalty grants."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Way of the Deathbringer', 'Way of the Warlord', 'Way of the Wildspeaker']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/way_loyalty_collateral_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()







def granted(s, walker, text):
    return next(a.index for a in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[walker.id]).abilities
                if a.kind == 'loyalty' and text in a.text)


def setup(cards, name):
    s = table(cards, [*NAMES, 'Grizzly Bears', 'Disenchant', "Hero's Downfall", 'Sarkhan the Masterless', 'Counterspell'], ['Grizzly Bears'])
    source = put(s, name, 'hand')
    mana(s, C=4, B=1, R=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    walkers = [c for c in s.state.cards.values() if c.name == 'Jace' and c.is_token and c.zone == 'p1:battlefield']
    assert len(walkers) == 1
    walker = walkers[0]
    assert walker.counters['loyalty'] == (7 if name == NAMES[2] else 5)
    assert source.attached_to is None
    roundtrip(s)
    return s, source, walker


@pytest.mark.parametrize('name', NAMES)
def test_exact_canonical_way_cards_are_full_and_only_grant_controlled_planeswalkers(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
    s, source, walker = setup(cards, name)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    assert not any(a.kind == 'loyalty' for a in Plan(s.state, 'p1', s.cards, None).ch(bear).abilities)
    assert len([a for a in Plan(s.state, 'p1', s.cards, None).ch(walker).abilities if a.kind == 'loyalty']) == 3
    act(s, 'p1', type='set_controller', card_ids=[walker.id], player='p2')
    assert len([a for a in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[walker.id]).abilities if a.kind == 'loyalty']) == 2
    roundtrip(s)


@pytest.mark.parametrize('sacrifice', [False, True])
def test_deathbringer_optional_sacrifice_native_payment_and_beast(cards, sacrifice):
    s, source, walker = setup(cards, NAMES[0])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    index = granted(s, walker, 'You may sacrifice')
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=index)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'pay', 'decline'}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if sacrifice else 'decline'])
    settle(s)
    if sacrifice and (pick := s.state.rules.decision) is not None:
        assert bear.id in {o.id for o in pick.options}
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=pick.id, option_ids=[bear.id])
        settle(s)
    assert s.state.cards[walker.id].counters['loyalty'] == 3
    beasts = [c for c in s.state.cards.values() if c.name == 'Beast' and c.zone == 'p1:battlefield']
    assert len(beasts) == int(sacrifice)
    if sacrifice:
        assert s.state.cards[bear.id].zone == 'p1:graveyard'
        assert Plan(s.state, 'p1', s.cards, None).ch(beasts[0]).pt == (4, 4)
        assert 'trample' in Plan(s.state, 'p1', s.cards, None).ch(beasts[0]).keywords
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=walker.id, ability=index)
    assert s.state.model_dump(mode='json') == before
    printed = granted(s, walker, 'Surveil')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=walker.id, ability=printed)
    roundtrip(s)


@pytest.mark.parametrize('creature_target', [False, True])
def test_warlord_optional_permanent_and_required_player_damage(cards, creature_target):
    s, source, walker = setup(cards, NAMES[1])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    index = granted(s, walker, 'deals 2 damage')
    targets = [bear.id, 'p2'] if creature_target else ['p2']
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=index,
        targets=targets, target_counts=[int(creature_target), 1])
    settle(s)
    assert s.state.players['p2'].life == 38
    assert s.state.cards[walker.id].counters['loyalty'] == 1
    assert s.state.cards[bear.id].zone == ('p2:graveyard' if creature_target else 'p2:battlefield')
    roundtrip(s)


def test_wildspeaker_native_beast_creation(cards):
    s, source, walker = setup(cards, NAMES[2])
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=granted(s, walker, 'Create a 4/4'))
    settle(s)
    beasts = [c for c in s.state.cards.values() if c.name == 'Beast' and c.zone == 'p1:battlefield']
    assert len(beasts) == 1
    assert 'trample' in Plan(s.state, 'p1', s.cards, None).ch(beasts[0]).keywords
    assert s.state.cards[walker.id].counters['loyalty'] == 3
    roundtrip(s)


def test_granted_loyalty_requires_own_main_phase_and_empty_stack(cards):
    s, source, walker = setup(cards, NAMES[0])
    index = granted(s, walker, 'You may sacrifice')
    instant = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=instant.id, targets=[source.id])
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=walker.id, ability=index)
    assert s.state.model_dump(mode='json') == before
    # Counter the source-removing spell, preserving the Way for a separate
    # turn-restriction check without changing the board by hand.
    counter = put(s, 'Counterspell', 'hand')
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[instant.id])
    settle(s)
    to_phase(s, 'main1', turn=2)
    settle(s)
    for _ in range(3):
        if s.state.rules.priority == 'p1':
            break
        act(s, s.state.rules.priority or s.state.turn.active_player, type='pass_priority')
    assert s.state.rules.priority == 'p1' and s.state.turn.active_player == 'p2'
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=walker.id, ability=index)
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_source_leaving_does_not_remove_ability_already_on_stack(cards):
    s, source, walker = setup(cards, NAMES[2])
    index = granted(s, walker, 'Create a 4/4')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=index)
    instant = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=instant.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert any(c.name == 'Beast' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    assert len([a for a in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[walker.id]).abilities if a.kind == 'loyalty']) == 2
    roundtrip(s)


def test_warlord_damage_uses_departed_host_last_known_information(cards):
    s, source, walker = setup(cards, NAMES[1])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='activate_ability', card_id=walker.id, ability=granted(s, walker, 'deals 2 damage'),
        targets=[bear.id, 'p2'], target_counts=[1, 1])
    instant = put(s, "Hero's Downfall", 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=instant.id, targets=[walker.id])
    settle(s)
    assert walker.id not in s.state.cards
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_type_changing_out_of_planeswalker_removes_way_grant_and_zero_loyalty_does_not_kill_creature(cards):
    s, source, walker = setup(cards, NAMES[2])
    sarkhan = put(s, 'Sarkhan the Masterless', 'hand')
    mana(s, C=3, R=2)
    act(s, 'p1', type='cast_spell', card_id=sarkhan.id)
    settle(s)
    index = granted(s, sarkhan, 'each planeswalker you control becomes')
    act(s, 'p1', type='activate_ability', card_id=sarkhan.id, ability=index)
    settle(s)
    ch = Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[walker.id])
    assert 'Creature' in ch.types and 'Planeswalker' not in ch.types
    assert not any('Create a 4/4 green Beast' in a.text for a in ch.abilities)
    act(s, 'p1', type='set_counter', card_id=walker.id, kind='loyalty', value=0)
    act(s, s.state.rules.priority or s.state.turn.active_player, type='pass_priority')
    assert s.state.cards[walker.id].zone == 'p1:battlefield'
    assert Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[walker.id]).pt == (4, 4)
    roundtrip(s)
