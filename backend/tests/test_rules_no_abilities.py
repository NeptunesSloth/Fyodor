"""CR 113, 613: ability-sensitive subjects read after layer 6."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/no_abilities_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Ruxa, Patient Professor', 'Muraganda Petroglyphs'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, *, ruxa=True):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    names = ['Ruxa, Patient Professor', 'Muraganda Petroglyphs', 'Grizzly Bears', 'Wind Drake', 'Rancor',
             'Paradise Mantle', 'Humility', 'Living Lands', 'Turn to Frog', 'Canopy Claws', 'Giant Growth', 'Raise the Alarm']
    s = table(cards, names, ['Grizzly Bears'])
    put(s, 'Ruxa, Patient Professor' if ruxa else 'Muraganda Petroglyphs', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    return s, bear


@pytest.mark.parametrize('ruxa', [True, False])
def test_vanilla_creature_boost_and_controller_scope(cards, ruxa):
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, bear = setup(cards, ruxa=ruxa)
    opposing = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    assert chars(s, bear).pt == ((3, 3) if ruxa else (4, 4))
    assert chars(s, opposing).pt == ((2, 2) if ruxa else (4, 4))
    roundtrip(s)


@pytest.mark.parametrize('equipment', ['Rancor', 'Paradise Mantle'])
@pytest.mark.parametrize('ruxa', [True, False])
def test_granted_keyword_or_activated_ability_excludes_creature(cards, equipment, ruxa):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, bear = setup(cards, ruxa=ruxa)
    grant = put(s, equipment, 'battlefield')
    act(s, 'p1', type='attach', card_ids=[grant.id], to=bear.id)
    assert chars(s, bear).pt == ((4, 2) if equipment == 'Rancor' else (2, 2))
    act(s, 'p1', type='move', card_ids=[grant.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert chars(s, bear).pt == ((3, 3) if ruxa else (4, 4))
    roundtrip(s)


@pytest.mark.parametrize('ruxa', [True, False])
def test_keyword_counter_is_ability_but_plus_counter_is_not(cards, ruxa):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, bear = setup(cards, ruxa=ruxa)
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='+1/+1', value=1)
    assert chars(s, bear).pt == ((4, 4) if ruxa else (5, 5))
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='flying', value=1)
    assert chars(s, bear).pt == (3, 3)
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='flying', value=0)
    assert chars(s, bear).pt == ((4, 4) if ruxa else (5, 5))
    roundtrip(s)


def test_humility_removes_creature_anthem_but_enchantment_anthem_survives(cards):
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, bear = setup(cards)
    put(s, 'Muraganda Petroglyphs', 'battlefield')
    put(s, 'Humility', 'battlefield')
    assert chars(s, bear).pt == (3, 3)
    roundtrip(s)


def test_only_printed_keyword_removed_creature_becomes_abilityless(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, _ = setup(cards)
    drake = put(s, 'Wind Drake', 'battlefield')
    spell = put(s, 'Canopy Claws', 'hand')
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[drake.id])
    settle(s)
    assert not chars(s, drake).keywords
    assert chars(s, drake).pt == (3, 3)
    roundtrip(s)

@pytest.mark.parametrize('text', ['', '(This creature has no abilities.)'])
def test_no_text_and_reminder_only_tokens_are_abilityless(cards, text):
    from tests.test_rules_attachments import token
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, _ = setup(cards)
    creature = token(s, 'p1', 'Vanilla', '1/1', text)
    assert chars(s, creature).pt == (2, 2)
    roundtrip(s)


@pytest.mark.parametrize('counter_after', [True, False])
def test_keyword_counter_timestamp_against_later_ability_loss(cards, counter_after):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, bear = setup(cards)
    if not counter_after:
        act(s, 'p1', type='set_counter', card_id=bear.id, kind='flying', value=1)
    spell = put(s, 'Turn to Frog', 'hand')
    mana(s, U=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    if counter_after:
        act(s, 'p1', type='set_counter', card_id=bear.id, kind='flying', value=1)
    assert ('flying' in chars(s, bear).keywords) is counter_after
    assert chars(s, bear).pt == ((1, 1) if counter_after else (2, 2))
    roundtrip(s)

@pytest.mark.parametrize('text', [
    'Creatures with no abilities have flying.',
    'Creatures with no abilities get +1/+1 and have flying.',
    'Creatures with abilities lose all abilities.',
    'Creatures with no abilities have "{T}: Add {G}.".',
])
def test_ability_sensitive_layer_six_effects_remain_refused(text):
    from app.rules import statics
    assert statics.parse(text) is None


def test_ability_sensitive_base_setting_selects_after_granted_abilities(cards):
    from tests.game_helpers import act
    from tests.test_rules_attachments import token
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, bear = setup(cards)
    token(s, 'p1', 'Fixed Shape', '1/1', 'Creatures with no abilities have base power and toughness 5/5.')
    assert chars(s, bear).pt == (6, 6)
    mantle = put(s, 'Paradise Mantle', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[mantle.id], to=bear.id)
    assert chars(s, bear).pt == (2, 2)
    roundtrip(s)

@pytest.mark.parametrize('remove', [None, 'Humility', 'Turn to Frog'])
def test_animated_forest_intrinsic_mana_ability_counts_until_removed(cards, remove):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars
    s, _ = setup(cards, ruxa=False)
    forest = put(s, 'Forest', 'battlefield')
    put(s, 'Living Lands', 'battlefield')
    ch = chars(s, forest)
    assert ch.pt == (1, 1)
    assert ch.has_abilities and any(a.intrinsic and a.kind == 'mana' for a in ch.abilities)
    if remove == 'Humility':
        put(s, remove, 'battlefield')
    elif remove:
        spell = put(s, remove, 'hand')
        mana(s, U=2)
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[forest.id])
        settle(s)
    if remove:
        ch = chars(s, forest)
        assert not ch.has_abilities and not ch.abilities
        assert ch.pt == (3, 3)
    roundtrip(s)
