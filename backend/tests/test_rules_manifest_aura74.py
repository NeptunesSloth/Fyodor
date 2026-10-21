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


def cast(s, name, pool, targets=(), pid='p1', pending=False, **kwargs):
    wait_priority(s, pid)
    source = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    wait_priority(s, pid)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[], **kwargs)
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
    assert not bodies(s)
    assert s.state.zones['p1:library'] == [cid for cid in before if cid != source.id]
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


@pytest.mark.parametrize('name', NAMES)
def test_native_combat_executes_flying_lifelink_or_double_strike(cards, name):
    s = game(cards)
    form(s, name)
    body, = bodies(s)
    to_phase(s, 'declare_attackers', turn=7)
    before = {pid: s.state.players[pid].life for pid in ['p1','p2']}
    attack(s, (body,'p2'))
    to_phase(s, 'end_combat', turn=7)
    settle(s)
    assert s.state.players['p2'].life == before['p2'] - (4 if name=='Rageform' else 2)
    assert s.state.players['p1'].life == before['p1'] + (2 if name=='Lightform' else 0)
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_empty_library_leaves_unattached_aura_to_native_sba(cards, name):
    s = game(cards)
    source = put(s, name, 'hand')
    library = list(s.state.zones['p1:library'])
    act(s, 'p1', type='move', card_ids=library, to={'player':'p1','zone':'exile'})
    form(s, name)
    assert not bodies(s) and source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_pending_paid_form_resolves_with_native_manifest_receipt(cards, tmp_path, name):
    import subprocess
    import sys

    import app

    s = game(cards)
    source = form(s, name, pending=True)
    assert not bodies(s) and 'Aura' not in chars(s, source).subtypes
    saved = tmp_path / 'form.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.test_rules_wave6c_tokens_pumps import chars
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
settle(s)
body,=[c for c in s.state.cards.values() if c.zone=='p1:battlefield' and c.face_down_kind=='manifest']
aura=s.state.cards[sys.argv[3]]
assert aura.attached_to==body.id and chars(s,body).pt==(2,2)
assert ('double strike' if sys.argv[4]=='Rageform' else 'flying') in chars(s,body).keywords
assert 'Aura' in chars(s,aura).subtypes
roundtrip(s)
'''
    p = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, name],
                       capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert p.returncode == 0, p.stdout + p.stderr


def test_paid_blink_successor_keeps_its_own_attachment_not_old_trigger_output(cards):
    assert coverage.of_card_data(cards.resolve('Flicker of Fate')).level == 'FULL'
    s = game(cards)
    top(s, 'Llanowar Elves')
    top(s, 'Grizzly Bears')
    source = form(s, 'Cloudform', pending=True)
    original = s.state.rules.object_id(source.id)
    cast(s, 'Flicker of Fate', {'C':1,'W':1}, [source.id], pid='p2')
    current = s.state.cards[source.id]
    assert s.state.rules.object_id(source.id) != original
    created = bodies(s)
    assert len(created) == 2
    first = next(c for c in created if c.name == 'Grizzly Bears')
    second = next(c for c in created if c.name == 'Llanowar Elves')
    assert current.attached_to == first.id and current.attached_to != second.id
    assert 'flying' in chars(s, first).keywords and 'flying' not in chars(s, second).keywords
    roundtrip(s)


def test_cloudform_hexproof_rejects_enemy_spell_but_allows_own_native_spell(cards):
    from app.game.errors import ActionError

    s = game(cards)
    source = form(s, 'Cloudform')
    body, = bodies(s)
    enemy = put(s, 'Lightning Bolt', 'hand', 'p2')
    mana(s, pid='p2', R=1)
    wait_priority(s, 'p2')
    with pytest.raises(ActionError):
        act(s, 'p2', type='cast_spell', card_id=enemy.id, targets=[body.id], sources=[])
    assert body.damage == 0 and body.zone == 'p1:battlefield'
    cast(s, 'Lightning Bolt', {'R':1}, [body.id])
    assert not bodies(s) and source.zone == 'p1:graveyard'
    roundtrip(s)


def test_countered_native_trigger_leaves_original_non_aura_enchantment(cards):
    s = game(cards)
    source = form(s, 'Lightform', pending=True)
    original = next(sid for sid, entry in s.state.rules.stack.items() if entry.source_card == source.id)
    cast(s, 'Stifle', {'U':1}, [original], pid='p2')
    assert source.zone == 'p1:battlefield' and 'Aura' not in chars(s, source).subtypes
    assert source.attached_to is None and not bodies(s)
    roundtrip(s)


def test_native_copy_to_shrine_then_old_trigger_replaces_enchantment_subtype_set(cards):
    assert coverage.of_card_data(cards.resolve('True Polymorph')).level == 'FULL'
    s = game(cards, 'Encroaching Mycosynth')
    put(s, 'Encroaching Mycosynth', 'battlefield', 'p2')
    shrine = put(s, 'Sanctum of All', 'battlefield', 'p2')
    source = form(s, 'Rageform', pending=True)
    oid = s.state.rules.object_id(source.id)
    cast(s, 'True Polymorph', {'C':4,'U':2}, [source.id, shrine.id], target_counts=[1,1])
    current = s.state.cards[source.id]
    assert s.state.rules.object_id(source.id) == oid
    assert chars(s, current).name == 'Sanctum of All'
    assert chars(s, current).types == {'Artifact','Enchantment'}
    assert chars(s, current).subtypes == {'Aura'}
    body, = bodies(s)
    assert current.attached_to == body.id
    roundtrip(s)
