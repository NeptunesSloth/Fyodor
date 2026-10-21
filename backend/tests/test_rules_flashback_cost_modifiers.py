"""CR 601.2f, 702.34a: flashback cost modifiers."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/flashback_cost_modifier_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Catalyst Stone'


def test_catalyst_stone_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, name='Firebolt', stone_owners=('p1',), caster='p1', modifier=None):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table

    deck = [NAME, 'Firebolt', 'Deep Analysis', 'Lava Dart', 'Ancient Grudge', 'Mountain',
            'Sol Ring', 'Sphere of Resistance', 'Lightning Bolt', 'Snapcaster Mage']
    s = table(cards, deck, deck)
    stones = [put(s, NAME, 'battlefield', pid=pid) for pid in stone_owners]
    if modifier:
        put(s, modifier, 'battlefield')
    spell = put(s, name, 'graveyard', pid=caster)
    return s, spell, stones


@pytest.mark.parametrize('caster,stones,generic', [('p1', ('p1',), 2), ('p2', ('p1',), 6),
                                                 ('p1', ('p1', 'p2'), 4)])
def test_controller_reduction_and_opponent_increase_are_paid_for_flashback(cards, caster, stones, generic):
    from app.rules.casting import spell_cost
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, spell, _ = setup(cards, stone_owners=stones, caster=caster)
    assert spell_cost(s.state, spell, chars(s, spell), info=s.cards, player=caster).generic == generic
    if caster != 'p1':
        from tests.test_rules_wave30m_durations import to_phase

        to_phase(s, 'main1', turn=2)
    wait_priority(s, caster)
    mana(s, pid=caster, C=generic, R=1)
    act(s, caster, type='cast_spell', card_id=spell.id, targets=['p3'])
    settle(s)
    assert s.state.cards[spell.id].zone == f'{caster}:exile'
    assert s.state.players['p3'].life == 38
    assert not any(s.state.players[caster].mana.values())
    roundtrip(s)


def test_normal_hand_cost_is_not_a_flashback_cost(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards)
    act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.players['p3'].life == 38
    roundtrip(s)


@pytest.mark.parametrize('owner,generic', [('p1', 0), ('p2', 3)])
def test_colored_mana_and_nonmana_life_cost_remain_required(cards, owner, generic):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards, name='Deep Analysis', stone_owners=(owner,))
    mana(s, C=generic, U=1)
    life = s.state.players['p1'].life
    hand = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1'])
    settle(s)
    assert s.state.players['p1'].life == life-3
    assert len(s.state.zones['p1:hand']) == hand+2
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


@pytest.mark.parametrize('owner,generic', [('p1', 0), ('p2', 2)])
def test_nonmana_flashback_cost_still_sacrifices_mountain_and_can_be_taxed(cards, owner, generic):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell, _ = setup(cards, name='Lava Dart', stone_owners=(owner,))
    mountain = put(s, 'Mountain', 'battlefield')
    if generic:
        mana(s, C=generic)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    settle(s)
    assert s.state.cards[mountain.id].zone == 'p1:graveyard'
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert s.state.players['p3'].life == 39
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


@pytest.mark.parametrize('modifier,name,payment', [('Sphere of Resistance', 'Firebolt', {'C': 3, 'R': 1}),
                                                  ('Sphere of Resistance', 'Deep Analysis', {'U': 1})])
def test_other_taxes_and_final_cost_floor_apply_in_order(cards, modifier, name, payment):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards, name=name, modifier=modifier)
    mana(s, **payment)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


@pytest.mark.parametrize('owner,generic', [('p1', 0), ('p2', 2)])
def test_granted_flashback_cost_uses_the_same_modifiers(cards, owner, generic):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, spell, _ = setup(cards, name='Lightning Bolt', stone_owners=(owner,))
    mage = put(s, 'Snapcaster Mage', 'hand')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=mage.id)
    settle(s)
    wait_priority(s, 'p1')
    roundtrip(s)
    mana(s, C=generic, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert s.state.players['p3'].life == 37
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)


def test_generic_reduction_cannot_pay_the_colored_requirement(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip

    s, spell, _ = setup(cards)
    mana(s, C=3)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].mana['C'] == 3
    roundtrip(s)


def test_modifier_ends_when_stone_leaves_battlefield(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, spell, stones = setup(cards)
    act(s, 'p1', type='move', card_ids=[stones[0].id], to={'player': 'p1', 'zone': 'graveyard'})
    mana(s, C=4, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p3'])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert not any(s.state.players['p1'].mana.values())
    roundtrip(s)
