"""CR 122.6: a privately selected creature enters with conditional additional counters."""
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
from tests.test_rules_abundance import set_library
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = "Animist's Awakening"


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/animist_awakening_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards, mastery=('Lightning Bolt', 'Divination'), x=3, names=None, permanent=None, mastery_pid='p1'):
    s = table(cards, [NAME, 'Forest', 'Island', 'Lightning Bolt', 'Lightning Bolt', 'Divination', 'Divination', 'Divination',
                      'Dryad Arbor', 'Containment Priest', 'Lotus Field', 'Amulet of Vigor', 'Swamp'],
              ['Lightning Bolt', 'Divination'])
    spell = put(s, NAME, 'hand')
    old = put(s, 'Swamp', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[old.id], tapped=True)
    if permanent:
        put(s, permanent, 'battlefield')
    top = set_library(s, names or ['Forest', 'Lightning Bolt', 'Island', 'Divination'])
    for c in list(s.state.cards.values()):
        if c.zone == 'p1:graveyard':
            act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'hand'})
    used = set(top)
    for name in mastery:
        c = next(c for c in s.state.cards.values() if c.owner == mastery_pid and c.name == name and c.id not in used)
        used.add(c.id)
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': mastery_pid, 'zone': 'graveyard'})
    mana(s, C=x, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x)
    settle(s)
    return s, spell, old, top


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('mastery,untapped', [((), False), (('Divination',), False),
                                             (('Divination', 'Divination'), True),
                                             (('Lightning Bolt', 'Divination'), True)])
def test_spell_mastery_counts_total_cards_excludes_resolving_spell_and_old_lands(cards, mastery, untapped):
    s, spell, old, top = setup(cards, mastery=mastery)
    assert s.state.cards[top[0]].zone == s.state.cards[top[2]].zone == 'p1:battlefield'
    assert s.state.cards[top[0]].tapped != untapped and s.state.cards[top[2]].tapped != untapped
    assert s.state.cards[old.id].tapped
    assert s.state.zones['p1:library'] == [top[3], top[1]]
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_opponents_graveyard_does_not_enable_mastery(cards):
    s, spell, old, top = setup(cards, mastery_pid='p2')
    assert s.state.cards[top[0]].tapped and s.state.cards[top[2]].tapped
    roundtrip(s)


@pytest.mark.parametrize('x,names', [(0, ['Forest', 'Island']), (7, ['Forest', 'Island']),
                                    (2, ['Lightning Bolt', 'Divination'])])
def test_zero_fewer_than_x_and_no_land_boundaries(cards, x, names):
    s, spell, old, top = setup(cards, mastery=(), x=x, names=names)
    if x == 0:
        assert s.state.zones['p1:library'] == top
    elif x == 7:
        assert all(s.state.cards[c].zone == 'p1:battlefield' for c in top)
    else:
        assert set(s.state.zones['p1:library']) == set(top)
    assert s.state.cards[old.id].tapped
    roundtrip(s)


def test_priest_redirected_land_creature_not_untapped_or_counted_as_entered(cards):
    s, spell, old, top = setup(cards, permanent='Containment Priest', names=['Dryad Arbor', 'Forest', 'Island'])
    assert s.state.cards[top[0]].zone == 'p1:exile'
    assert s.state.cards[top[1]].zone == s.state.cards[top[2]].zone == 'p1:battlefield'
    assert not s.state.cards[top[1]].tapped and not s.state.cards[top[2]].tapped
    assert s.state.cards[old.id].tapped
    roundtrip(s)


def test_lotus_field_enters_untapped_by_mastery_before_its_sacrifice_trigger(cards):
    s, spell, old, top = setup(cards, names=['Lotus Field', 'Forest', 'Island'])
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert not s.state.cards[top[0]].tapped
    d = s.state.rules.decision
    assert d is not None and d.kind == 'choose_cards'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[old.id, top[1]])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:battlefield' and not s.state.cards[top[0]].tapped
    roundtrip(s)


def test_native_as_entry_sacrifice_pause_preserves_binding_and_mastery(cards):
    s = table(cards, [NAME, 'Lake of the Dead', 'Swamp', 'Lightning Bolt', 'Divination'], [])
    spell = put(s, NAME, 'hand')
    swamp = put(s, 'Swamp', 'battlefield')
    top = set_library(s, ['Lake of the Dead'])
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[swamp.id])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:battlefield' and not s.state.cards[top[0]].tapped
    assert s.state.cards[swamp.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_amulet_entry_triggers_still_untap_new_lands_without_spell_mastery(cards):
    s, spell, old, top = setup(cards, mastery=(), permanent='Amulet of Vigor')
    assert not s.state.cards[top[0]].tapped and not s.state.cards[top[2]].tapped
    assert s.state.cards[old.id].tapped
    roundtrip(s)
