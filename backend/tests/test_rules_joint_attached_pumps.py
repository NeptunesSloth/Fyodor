"""CR 613.4c, 702.103: a source and its enchanted creature each get independent pumps."""
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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/joint_attached_pumps_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAMES = ['Nighthowler', 'Eidolon of Countless Battles']


def setup(cards, name, *, bestow=True):
    s = table(cards, [name, 'Grizzly Bears', 'Rancor', 'Pacifism', 'Humility'],
              ['Murder', 'Grizzly Bears', 'Colossal Dreadmaw'], ['Colossal Dreadmaw'])
    put(s, 'Grizzly Bears', 'graveyard', 'p2')
    put(s, 'Colossal Dreadmaw', 'graveyard', 'p3')
    host = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, name, 'hand')
    mana(s, C=2 if bestow else 1, **({'B': 2} if name == 'Nighthowler' else {'W': 2}))
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[host.id] if bestow else [],
        **({'alt_cost': f'{source.id}:0'} if bestow else {}))
    return s, source, host


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES)
def test_bestowed_source_only_buffs_attached_creature_and_becomes_creature_after_host_dies(cards, name):
    s, source, host = setup(cards, name)
    settle(s)
    assert 'Aura' in chars(s, source).subtypes and not chars(s, source).is_creature
    assert chars(s, host).pt == (4, 4)
    wait_priority(s, 'p2')
    kill = put(s, 'Murder', 'hand', 'p2')
    mana(s, pid='p2', C=1, B=2)
    act(s, 'p2', type='cast_spell', card_id=kill.id, targets=[host.id])
    settle(s)
    assert s.state.cards[host.id].zone == 'p1:graveyard'
    assert chars(s, source).is_creature and 'Aura' not in chars(s, source).subtypes
    assert chars(s, source).pt == ((3, 3) if name == 'Nighthowler' else (1, 1))
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_illegal_bestow_target_resolves_as_creature_with_its_own_pump(cards, name):
    s, source, host = setup(cards, name)
    wait_priority(s, 'p2')
    kill = put(s, 'Murder', 'hand', 'p2')
    mana(s, pid='p2', C=1, B=2)
    act(s, 'p2', type='cast_spell', card_id=kill.id, targets=[host.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].attached_to is None
    assert chars(s, source).is_creature
    assert chars(s, source).pt == ((3, 3) if name == 'Nighthowler' else (1, 1))
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_normal_creature_uses_only_its_self_siblings(cards, name):
    s, source, host = setup(cards, name, bestow=False)
    assert chars(s, source).pt == (0, 0)  # the buff is not a CDA; it does not function on the stack
    settle(s)
    assert chars(s, source).pt == (2, 2)
    assert chars(s, host).pt == (2, 2)
    assert s.state.cards[source.id].attached_to is None
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_phasing_out_aura_removes_both_siblings_then_restores_host_pump(cards, name):
    s, source, host = setup(cards, name)
    settle(s)
    assert chars(s, host).pt == (4, 4)
    act(s, 'p1', type='phase_shift', card_ids=[source.id], out=True)
    assert chars(s, host).pt == (2, 2)
    act(s, 'p1', type='phase_shift', card_ids=[source.id], out=False)
    assert chars(s, host).pt == (4, 4)
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_losing_creature_source_abilities_removes_all_sibling_pumps(cards, name):
    s, source, _ = setup(cards, name, bestow=False)
    settle(s)
    put(s, 'Humility', 'battlefield')
    assert chars(s, source).pt == (1, 1)
    assert not chars(s, source).abilities
    roundtrip(s)


def test_eidolon_counts_its_current_controller_creatures_and_auras_not_owner_or_host_controller(cards):
    s, source, host = setup(cards, 'Eidolon of Countless Battles')
    settle(s)
    # Two creatures belong to the new controller; the Aura remains attached to Alice's Bear.
    bear = next(c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p2')
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'battlefield'})
    put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    assert s.state.cards[source.id].owner == 'p1'
    assert s.state.cards[host.id].controller == 'p1'
    assert chars(s, host).pt == (5, 5)
    roundtrip(s)


def test_transient_aura_creature_is_counted_in_each_additive_set(cards):
    # An Aura creature cannot remain attached after SBAs (303.4d). Derive the legitimate
    # transient state during a resolution, before the engine performs those checks.
    from app.rules import layers
    from app.rules.plan import Plan

    s, source, host = setup(cards, 'Eidolon of Countless Battles', bestow=False)
    settle(s)
    aura = put(s, 'Rancor', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[aura.id], to=host.id)
    assert chars(s, source).pt == (3, 3)  # two creatures plus one Aura
    probe = Plan(s.state, 'p1', s.cards, None)
    layers.add_effect(probe, affected=[probe.oid(aura)], layer='4', source=None, controller='p1',
                      add_types=['Creature'], duration='end_of_turn', label='Transient Aura creature')
    assert probe.ch(probe.state.cards[aura.id]).is_creature
    assert 'Aura' in probe.ch(probe.state.cards[aura.id]).subtypes
    assert probe.ch(probe.state.cards[source.id]).pt == (4, 4)  # three creatures PLUS one Aura
    assert chars(s, source).pt == (3, 3)  # the read-only probe did not alter the game
    roundtrip(s)
