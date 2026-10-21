"""CR 601.2i, 608.2i: first spell paid with mana from a Treasure."""
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
from tests.test_rules_wave10b_spell_cascade import cascades
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/first_mana_source_spell_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = 'Rain of Riches'


def setup(cards, *, present=True, copies=1):
    s = table(cards, [NAME, NAME, 'Lightning Bolt', 'Grizzly Bears', 'Opt', 'Sol Ring'], ['Counterspell'])
    sources = []
    for c in list(s.state.cards.values()):
        if c.name == NAME and c.owner == 'p1' and len(sources) < copies:
            if present:
                act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
            sources.append(c)
    return s, sources


def treasure(s, *, floating=False):
    before = set(s.state.cards)
    act(s, 'p1', type='create_token', player='p1', token={'name': 'Treasure', 'type_line': 'Token Artifact — Treasure',
        'text': '{T}, Sacrifice this token: Add one mana of any color.'})
    t = next(c for cid, c in s.state.cards.items() if cid not in before)
    if floating:
        act(s, 'p1', type='activate_ability', card_id=t.id, ability=0, mana_choice='R')
    return t


def cast(s, *, use_treasure=True, floating=False):
    wait_priority(s, 'p1')
    b = put(s, 'Lightning Bolt', 'hand')
    if use_treasure:
        treasure(s, floating=floating)
    else:
        mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=b.id, targets=['p3'])
    d = s.state.rules.decision
    if d is not None and d.kind == 'order':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
    return b


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('floating', [False, True])
def test_first_qualifying_spell_after_ordinary_spell_gets_cascade(cards, floating):
    s, _ = setup(cards)
    cast(s, use_treasure=False)
    assert cascades(s) == 0
    settle(s)
    spell = cast(s, floating=floating)
    assert cascades(s) == 1
    assert any('Treasure' in tags for tags in s.state.rules.payments[s.state.rules.object_id(spell.id)].mana_tags)
    roundtrip(s)
    settle(s)
    # Its stack payment has gone; the historical cast still blocks later qualifying spells.
    cast(s)
    assert cascades(s) == 0
    settle(s)
    roundtrip(s)


def test_earlier_qualifying_spell_before_enchantment_entered_counts(cards):
    s, sources = setup(cards, present=False)
    cast(s)
    assert cascades(s) == 0
    settle(s)
    act(s, 'p1', type='move', card_ids=[sources[0].id], to={'player': 'p1', 'zone': 'battlefield'})
    cast(s)
    assert cascades(s) == 0
    settle(s)
    roundtrip(s)


def test_source_reentry_does_not_reset_first_spell(cards):
    s, sources = setup(cards)
    cast(s)
    assert cascades(s) == 1
    settle(s)
    act(s, 'p1', type='move', card_ids=[sources[0].id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[sources[0].id], to={'player': 'p1', 'zone': 'battlefield'})
    cast(s)
    assert cascades(s) == 0
    settle(s)
    roundtrip(s)


def test_two_enchantments_grant_two_instances_to_same_first_spell(cards):
    s, _ = setup(cards, copies=2)
    cast(s)
    assert cascades(s) == 2
    settle(s)
    roundtrip(s)


def test_first_qualifying_spell_each_turn(cards):
    s, _ = setup(cards)
    cast(s)
    assert cascades(s) == 1
    settle(s)
    to_phase(s, 'main1', turn=2)
    cast(s)
    assert cascades(s) == 1
    settle(s)
    roundtrip(s)


def test_enter_trigger_creates_two_real_treasures(cards):
    s, sources = setup(cards, present=False)
    source = sources[0]
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=3, R=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert sum(c.quantity for c in s.state.cards.values() if c.name == 'Treasure' and c.controller == 'p1') == 2
    assert all('Add one mana of any color' in c.token.text for c in s.state.cards.values() if c.name == 'Treasure')
    roundtrip(s)


def test_floating_treasure_mana_does_not_count_until_spent(cards):
    s, _ = setup(cards)
    # Float red Treasure mana, then cast a green creature using Forests instead.
    treasure(s, floating=True)
    bear = put(s, 'Grizzly Bears', 'hand')
    mana(s, G=2)
    act(s, 'p1', type='cast_spell', card_id=bear.id, sources=[])
    assert cascades(s) == 0
    settle(s)
    bolt = put(s, 'Lightning Bolt', 'hand')
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=['p3'])
    assert cascades(s) == 1
    settle(s)
    roundtrip(s)


def test_countered_first_qualifying_spell_still_counts(cards):
    s, _ = setup(cards)
    spell = cast(s)
    wait_priority(s, 'p2')
    counter = put(s, 'Counterspell', 'hand', 'p2')
    mana(s, pid='p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    cast(s)
    assert cascades(s) == 0
    settle(s)
    roundtrip(s)
