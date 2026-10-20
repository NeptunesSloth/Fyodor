"""Layer-3 named Aura transformations and their later characteristic changes."""
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
from tests.test_rules_attachments import ch
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import until_asked
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/attached_name_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



WITNESS = 'Witness Protection'
HONEST = 'Honest Work'


def setup(cards):
    return table(cards, [WITNESS, HONEST, 'Ornithopter', 'Cackling Counterpart', "Kenrith's Transformation", 'Lightning Bolt', 'Dress Down'], ['Ornithopter'])


def cast_aura(s, name, target):
    spell = put(s, name, 'hand')
    wait_priority(s, 'p1')
    mana(s, U=1) if name in (WITNESS, HONEST) else mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[target.id])
    settle(s)
    return spell


@pytest.mark.parametrize('name', [WITNESS, HONEST])
def test_named_auras_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_witness_sets_name_color_types_pt_and_removes_abilities_then_reverts(cards):
    s = setup(cards)
    target = put(s, 'Ornithopter', 'battlefield')
    aura = cast_aura(s, WITNESS, target)
    now = ch(s, target)
    assert now.name == 'Legitimate Businessperson' and now.colors == {'G', 'W'}
    assert now.types == {'Creature'} and now.subtypes == {'Citizen'} and now.pt == (1, 1)
    assert not now.abilities and not now.keywords
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'graveyard'})
    now = ch(s, target)
    assert now.name == 'Ornithopter' and now.pt == (0, 2) and 'Artifact' in now.types and 'flying' in now.keywords
    roundtrip(s)


def test_honest_preserves_card_types_color_removes_counters_and_grants_mana(cards):
    from tests.game_helpers import mana_pool

    s = setup(cards)
    target = put(s, 'Ornithopter', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[target.id], kind='+1/+1', delta=3)
    cast_aura(s, HONEST, target)
    now = ch(s, target)
    assert now.name == 'Humble Merchant' and not now.colors and now.types == {'Artifact', 'Creature'}
    assert now.subtypes == {'Citizen'} and now.pt == (1, 1) and not s.state.cards[target.id].counters
    assert s.state.cards[target.id].tapped
    to_phase(s, 'main1', turn=2)
    wait_priority(s, 'p2')
    mana_ability = next(a for a in ch(s, target).abilities if 'Add {C}' in a.text)
    act(s, 'p2', type='activate_ability', card_id=target.id, ability=mana_ability.index)
    assert mana_pool(s, 'p2') == {'C': 1}
    roundtrip(s)


def test_copy_uses_original_name_and_copiable_values_instead_of_named_aura_changes(cards):
    s = setup(cards)
    target = put(s, 'Ornithopter', 'battlefield')
    cast_aura(s, WITNESS, target)
    copy = put(s, 'Cackling Counterpart', 'hand')
    mana(s, C=1, U=2)
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[target.id])
    settle(s)
    token = next(c for c in s.state.cards.values() if c.is_token and c.id != target.id and c.zone.endswith(':battlefield'))
    now = ch(s, token)
    assert now.name == 'Ornithopter' and now.pt == (0, 2) and now.types == {'Artifact', 'Creature'}
    assert now.subtypes == {'Thopter'} and 'flying' in now.keywords and not now.colors
    assert ch(s, target).name == 'Legitimate Businessperson'
    roundtrip(s)



@pytest.mark.parametrize('order', [(WITNESS, HONEST), (HONEST, WITNESS)])
def test_later_name_and_ability_timestamps_then_older_name_returns(cards, order):
    s = setup(cards)
    target = put(s, 'Ornithopter', 'battlefield', 'p2')
    older = cast_aura(s, order[0], target)
    newer = cast_aura(s, order[1], target)
    now = ch(s, target)
    assert now.name == ('Humble Merchant' if order[1] == HONEST else 'Legitimate Businessperson')
    assert any('Add {C}' in a.text for a in now.abilities) == (order[1] == HONEST)
    assert now.colors == {'G', 'W'} and now.types == {'Creature'}
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[newer.id], to={'player': 'p1', 'zone': 'graveyard'})
    now = ch(s, target)
    assert now.name == ('Humble Merchant' if order[0] == HONEST else 'Legitimate Businessperson')
    assert now.colors == (set() if order[0] == HONEST else {'G', 'W'})
    assert any('Add {C}' in a.text for a in now.abilities) == (order[0] == HONEST)
    assert s.state.cards[older.id].attached_to == target.id
    roundtrip(s)


@pytest.mark.parametrize('dress_first', [False, True])
def test_layer_six_host_ability_removal_never_changes_layer_three_name(cards, dress_first):
    s = setup(cards)
    # Dress Down is an enchantment, so the attached Aura itself keeps its static ability.
    target = put(s, 'Ornithopter', 'battlefield', 'p2')
    if dress_first:
        dress = put(s, 'Dress Down', 'battlefield')
    cast_aura(s, HONEST, target)
    if not dress_first:
        dress = put(s, 'Dress Down', 'battlefield')
    now = ch(s, target)
    assert now.name == 'Humble Merchant' and now.pt == (1, 1) and now.subtypes == {'Citizen'}
    assert any('Add {C}' in a.text for a in now.abilities) == dress_first
    act(s, 'p1', type='move', card_ids=[dress.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert any('Add {C}' in a.text for a in ch(s, target).abilities)
    roundtrip(s)



def test_new_names_participate_in_legend_rule_without_removing_legendary(cards):
    s = table(cards, [WITNESS, WITNESS, 'Rograkh, Son of Rohgahh', 'Yoshimaru, Ever Faithful'])
    a = put(s, 'Rograkh, Son of Rohgahh', 'battlefield')
    b = put(s, 'Yoshimaru, Ever Faithful', 'battlefield')
    first = cast_aura(s, WITNESS, a)
    second = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == WITNESS and c.id != first.id)
    act(s, 'p1', type='move', card_ids=[second.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=second.id, targets=[b.id])
    d = until_asked(s)
    assert d.resume['step'] == 'legend_rule' and {o.id for o in d.options} == {a.id, b.id}
    assert ch(s, a).name == ch(s, b).name == 'Legitimate Businessperson'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[a.id])
    settle(s)
    assert s.state.cards[a.id].zone == 'p1:battlefield' and s.state.cards[b.id].zone == 'p1:graveyard'
    assert 'Legendary' in ch(s, a).supertypes
    roundtrip(s)
