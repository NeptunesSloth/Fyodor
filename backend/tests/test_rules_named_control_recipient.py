"""CR 608.2c, 509.3g: preserve named control recipients across events."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/named_control_recipient_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='ncr', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Coveted Jewel', 'Drooling Ogre', 'Fractured Loyalty', 'Crag Saurian', 'Discerning Financier', 'Goblin Festival'])
def test_named_control_recipient_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('caster', ['p1', 'p2'])
def test_ogre_goes_to_the_artifact_caster(cards, caster):
    from tests.test_rules_review_combat import stops
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ['Drooling Ogre', 'Sol Ring'], bob=((1, 'Sol Ring'), (10, 'Island')))
    ogre = put(s, 'Drooling Ogre', 'battlefield')
    ring = put(s, 'Sol Ring', 'hand', caster)
    stops(s)
    if caster == 'p2':
        to_phase(s, 'main1', turn=2)
    act(s, caster, type='add_mana', player=caster, mana={'C': 1})
    act(s, caster, type='cast_spell', card_id=ring.id)
    assert s.state.cards[ogre.id].controller == 'p1'
    roundtrip(s)
    settle(s)
    assert s.state.cards[ogre.id].controller == caster
    assert s.state.cards[ring.id].zone == f'{caster}:battlefield'
    roundtrip(s)


def jewel_combat(cards, blockers=False):
    from tests.test_rules_review_combat import stops
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ['Grizzly Bears', 'Llanowar Elves'], bob=((1, 'Coveted Jewel'), (1, 'Grizzly Bears'), (10, 'Island')))
    jewel = put(s, 'Coveted Jewel', 'battlefield', 'p2')
    act(s, 'p2', type='tap', card_ids=[jewel.id], tapped=True)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    guard = put(s, 'Grizzly Bears', 'battlefield', 'p2') if blockers else None
    stops(s)
    to_phase(s, 'declare_attackers', turn=3)
    # Bob's intervening untap step untaps the Jewel; tap it again to verify the rider.
    act(s, 'p2', type='tap', card_ids=[jewel.id], tapped=True)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in [bear, elf]])
    for _ in range(40):
        if s.state.rules.decision is not None or s.state.zones.get('stack'):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    return s, jewel, bear, elf, guard


@pytest.mark.parametrize('blocked', [0, 1])
def test_jewel_triggers_once_for_the_unblocked_batch_and_untaps(cards, blocked):
    s, jewel, bear, elf, guard = jewel_combat(cards, blockers=bool(blocked))
    if guard is not None:
        d = s.state.rules.decision
        assert d is not None and d.kind == 'declare_blockers'
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': guard.id, 'attacker_id': bear.id}])
    assert len(s.state.zones.get('stack', [])) == 1
    hand = len(s.state.zones.get('p1:hand', []))
    roundtrip(s)
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == hand + 3
    assert s.state.cards[jewel.id].controller == 'p1'
    assert not s.state.cards[jewel.id].tapped
    roundtrip(s)


def test_jewel_source_leaving_still_draws_but_does_not_steal_a_new_object(cards):
    s, jewel, bear, elf, guard = jewel_combat(cards)
    assert len(s.state.zones.get('stack', [])) == 1
    hand = len(s.state.zones.get('p1:hand', []))
    act(s, 'p2', type='move', card_ids=[jewel.id], to={'player': 'p2', 'zone': 'hand'})
    act(s, 'p2', type='move', card_ids=[jewel.id], to={'player': 'p2', 'zone': 'battlefield'})
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == hand + 3
    assert s.state.cards[jewel.id].controller == 'p2'
    roundtrip(s)


def test_jewel_remembers_the_attacking_player_after_attacker_control_changes(cards):
    s, jewel, bear, elf, guard = jewel_combat(cards)
    hand = len(s.state.zones.get('p1:hand', []))
    act(s, 'p1', type='set_controller', card_ids=[bear.id, elf.id], player='p2')
    roundtrip(s)
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == hand + 3
    assert s.state.cards[jewel.id].controller == 'p1'
    roundtrip(s)


def test_unbound_control_recipient_is_not_automated():
    # A trigger with no identified player cannot invent one for "that player".
    c = card('Unbound recipient', set_code='ncr', number='bad', type_line='Creature',
             power='1', toughness='1', oracle_text='Whenever this creature attacks, that player gains control of this creature.')
    assert coverage.of_card_data(c).level != 'FULL'


def test_three_player_combat_keeps_each_jewels_unblocked_event_separate(cards):
    from tests.test_rules_wave30m_durations import three, to_phase

    s = three(cards, ['Grizzly Bears', 'Llanowar Elves'], ['Coveted Jewel'], ['Coveted Jewel'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    jewels = [put(s, 'Coveted Jewel', 'battlefield', pid) for pid in ['p2', 'p3']]
    for pid in ['p1', 'p2', 'p3']:
        act(s, pid, type='set_prefs', response='on')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}, {'card_id': elf.id, 'target': 'p3'}])
    for _ in range(40):
        d = s.state.rules.decision
        if s.state.zones.get('stack') or (d is not None and d.kind == 'order'):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    hand = len(s.state.zones.get('p1:hand', []))
    roundtrip(s)
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == hand + 6
    assert all(s.state.cards[c.id].controller == 'p1' for c in jewels)
    assert all(not s.state.cards[c.id].tapped for c in jewels)
    roundtrip(s)


def test_saurian_transfers_to_the_damage_sources_controller(cards):
    from tests.test_rules_review_combat import stops
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ['Crag Saurian'], bob=((1, 'Lightning Bolt'), (10, 'Island')))
    saurian = put(s, 'Crag Saurian', 'battlefield')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    stops(s)
    to_phase(s, 'main1', turn=2)
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[saurian.id])
    roundtrip(s)
    settle(s)
    assert s.state.cards[saurian.id].damage == 3
    assert s.state.cards[saurian.id].controller == 'p2'
    roundtrip(s)


@pytest.mark.parametrize('aura_leaves', [True, False])
def test_loyalty_transfers_to_the_targeting_spell_caster(cards, aura_leaves):
    from tests.test_rules_review_combat import stops
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, ['Fractured Loyalty', 'Grizzly Bears'], bob=((1, 'Giant Growth'), (10, 'Island')))
    bear = put(s, 'Grizzly Bears', 'battlefield')
    aura = put(s, 'Fractured Loyalty', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[bear.id])
    settle(s)
    growth = put(s, 'Giant Growth', 'hand', 'p2')
    stops(s)
    to_phase(s, 'main1', turn=2)
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1})
    act(s, 'p2', type='cast_spell', card_id=growth.id, targets=[bear.id])
    assert s.state.cards[bear.id].controller == 'p1'
    assert len(s.state.zones['stack']) == 2
    if aura_leaves:
        act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'graveyard'})
    roundtrip(s)
    settle(s)
    assert s.state.cards[bear.id].controller == 'p2'
    roundtrip(s)


def test_financier_chooses_another_player_on_resolution_and_draws_for_its_controller(cards):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave30m_durations import three

    s = three(cards, ['Discerning Financier'])
    source = put(s, 'Discerning Financier', 'battlefield')
    act(s, 'p1', type='create_token', player='p1', token={'name': 'Treasure', 'type_line': 'Token Artifact — Treasure'})
    treasure = next(c for c in s.state.cards.values() if c.name == 'Treasure')
    hand = len(s.state.zones.get('p1:hand', []))
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[treasure.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'p2', 'p3'}
    roundtrip(s)
    pick(s, ['p3'])
    settle(s)
    assert s.state.cards[treasure.id].controller == 'p3'
    assert len(s.state.zones.get('p1:hand', [])) == hand + 1
    roundtrip(s)


@pytest.mark.parametrize('won', [True, False])
def test_festival_chooses_a_recipient_only_after_losing_the_flip(cards, monkeypatch, won):
    from tests.test_rules_designations import pick
    from tests.test_rules_wave7r_promotions import flips
    from tests.test_rules_wave30m_durations import three

    flips(monkeypatch, won)
    s = three(cards, ['Goblin Festival'])
    festival = put(s, 'Goblin Festival', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=festival.id, ability=0, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 39
    d = s.state.rules.decision
    if won:
        assert d is None
    else:
        assert d is not None and {o.id for o in d.options} == {'p2', 'p3'}
        roundtrip(s)
        pick(s, ['p3'])
        settle(s)
    assert s.state.cards[festival.id].controller == ('p1' if won else 'p3')
    roundtrip(s)
