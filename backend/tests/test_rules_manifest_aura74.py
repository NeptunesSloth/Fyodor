"""Paid Forms use actual manifest receipts, preserve source identity, and grant working combat abilities."""
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
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

NAMES = ['Cloudform', 'Lightform', 'Rageform']
DATA = json.loads((Path(__file__).parent / 'fixtures/manifest_aura74_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards, blocker=None):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    if blocker:
        put(s, blocker, 'battlefield')
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    top(s, 'Grizzly Bears')
    return s


def top(s, name):
    c = put(s, name, 'hand')
    act(s, 'p1', type='move', card_ids=[c.id], to={'player':'p1', 'zone':'library'}, index=0)
    return c


def cast(s, name, pool, targets=(), pid='p1', pending=False):
    source = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    wait_priority(s, pid)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[])
    if pending:
        for _ in range(10):
            if source.zone != 'stack':
                break
            assert s.state.rules.decision is None
            act(s, s.state.rules.priority, type='pass_priority')
        assert source.zone.endswith(':battlefield')
    else:
        settle(s)
    return source


def form(s, name, **kw):
    return cast(s, name, {'C': 2, 'U': 2, 'W': 2, 'R': 2}, **kw)


def bodies(s):
    return [c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.face_down_kind=='manifest']


@pytest.mark.parametrize('name', NAMES)
def test_canonical_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,keywords', [('Cloudform', {'flying','hexproof'}), ('Lightform', {'flying','lifelink'}),
                                         ('Rageform', {'double strike'})])
def test_paid_manifest_attaches_native_body_with_printed_keywords(cards, name, keywords):
    s = game(cards)
    source = form(s, name)
    body, = bodies(s)
    assert chars(s, body).pt == (2,2) and keywords <= chars(s, body).keywords
    assert chars(s, source).types == {'Enchantment'} and chars(s, source).subtypes == {'Aura'}
    assert source.attached_to == body.id and body.face_down
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_actual_paid_turn_face_up_retains_attachment_and_granted_abilities(cards, name):
    s = game(cards)
    source = form(s, name)
    body, = bodies(s)
    oid = s.state.rules.object_id(body.id)
    mana(s, C=1, G=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='turn_face_up', card_id=body.id, sources=[])
    settle(s)
    body = s.state.cards[body.id]
    assert not body.face_down and s.state.rules.object_id(body.id) == oid
    assert source.attached_to == body.id and chars(s, body).pt == (2,2)
    assert ('double strike' if name=='Rageform' else 'flying') in chars(s, body).keywords
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_prevented_manifest_does_not_attach_a_different_object(cards, name):
    s = game(cards, "Grafdigger's Cage")
    before = list(s.state.zones['p1:library'])
    source = form(s, name)
    assert not bodies(s) and s.state.zones['p1:library'] == before
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_native_artifact_type_is_preserved_when_becoming_aura(cards, name):
    s = game(cards, 'Encroaching Mycosynth')
    source = form(s, name)
    assert chars(s, source).types == {'Artifact','Enchantment'}
    body, = bodies(s)
    assert source.attached_to == body.id
    roundtrip(s)


def test_original_pending_form_still_manifests_after_paid_destruction(cards):
    s = game(cards)
    source = form(s, 'Cloudform', pending=True)
    cast(s, 'Disenchant', {'C':1,'W':1}, [source.id], pid='p2')
    body, = bodies(s)
    assert source.zone == 'p1:graveyard' and body.face_down
    assert all(c.attached_to != body.id for c in s.state.cards.values())
    roundtrip(s)
