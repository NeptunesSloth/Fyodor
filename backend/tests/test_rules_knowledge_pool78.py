"""Real Ian exile producers and Kaya loyalty/emblem authorities keep their native scopes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/knowledge_pool78_cards.json').read_text())
POOL = 'Knowledge Pool'
DOG = 'Isamaru, Hound of Konda'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'top_library_authorities69_cards.json',
                     'pooled_casting_authorities71_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='lc76', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='lc76', number='a' + str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest', 'Island', 'Plains',
                          'Jacob Hauken, Inspector // Hauken\'s Insight')




def pending_pool_offer(cards):
    s = setup(cards)
    first = stack_library(s, ['Divination', 'Forest', 'Sol Ring'])
    for pid in ['p2', 'p3']:
        stack_library(s, ['Grizzly Bears', 'Forest', 'Sol Ring'], pid=pid)
    source = cast(s, POOL)
    offered = first[0]
    assert s.state.cards[offered].zone == 'p1:exile'
    assert len(s.state.rules.exiled_with[s.state.rules.object_id(source.id)]) == 9
    to_phase(s, 'main1', turn=2)
    settle(s)
    spell = put(s, 'Lightning Bolt', 'hand', pid='p2')
    act(s, 'p2', type='clear_mana')
    mana(s, pid='p2', R=1)
    wait_priority(s, 'p2')
    life = s.state.players['p1'].life
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=['p1'])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    assert offered in {o.id for o in d.options} and spell.id not in {o.id for o in d.options}
    assert s.state.cards[spell.id].zone == 'p2:exile'
    assert s.state.players['p1'].life == life
    return s, source, offered, spell


@pytest.mark.parametrize('choose', [True, False])
def test_real_pool_entry_and_hand_spell_exchange_gives_caster_other_foreign_card78(cards, choose):
    s, source, offered, spell = pending_pool_offer(cards)
    before = len(s.state.zones.get('p2:hand', []))
    answer(s, [offered] if choose else [])
    settle(s)
    assert s.state.cards[offered].zone == ('p1:graveyard' if choose else 'p1:exile')
    assert len(s.state.zones.get('p2:hand', [])) == before + (2 if choose else 0)
    assert not s.state.players['p2'].mana
    assert not s.state.rules.decision
    roundtrip(s)


def prepared_pool(cards):
    s = setup(cards)
    ids = stack_library(s, ['Divination', 'Forest', 'Sol Ring'])
    for pid in ['p2', 'p3']:
        stack_library(s, ['Grizzly Bears', 'Forest', 'Sol Ring'], pid=pid)
    source = cast(s, POOL)
    return s, source, ids[0]


def test_countered_original_spell_creates_no_pool_exchange78(cards):
    s, source, offered = prepared_pool(cards)
    archmage = put(s, 'Glen Elendra Archmage', 'battlefield', pid='p2')
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    mana(s, pid='p2', U=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=archmage.id,
        ability=ability(s, archmage, '{U}, Sacrifice'), targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.cards[offered].zone == 'p1:exile' and not s.state.rules.decision
    assert spell.id not in {oid.rsplit('.', 1)[0] for oid in s.state.rules.exiled_with[s.state.rules.object_id(source.id)]}
    roundtrip(s)


def test_pool_with_only_lands_never_recasts_the_just_exiled_original_spell78(cards):
    s = setup(cards)
    for pid in ['p1', 'p2', 'p3']:
        stack_library(s, ['Forest', 'Island', 'Plains'], pid=pid)
    cast(s, POOL)
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    life = s.state.players['p2'].life
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert s.state.players['p2'].life == life and not s.state.rules.decision
    roundtrip(s)


def test_whole_canonical_pool78(cards):
    assert coverage.of_card_data(cards.resolve(POOL)).level == 'FULL'


def test_two_actual_pool_sources_offer_only_the_first_successful_exiling_pool78(cards):
    s = setup(cards)
    put(s, 'Leyline of Anticipation', 'battlefield', pid='p2')
    for pid in ['p1', 'p2', 'p3']:
        stack_library(s, ['Divination', 'Forest', 'Sol Ring'], pid=pid)
    first = put(s, POOL, 'hand')
    mana(s, C=6)
    act(s, 'p1', type='cast_spell', card_id=first.id)
    second = put(s, POOL, 'hand', pid='p2')
    mana(s, pid='p2', C=6)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=second.id)
    settle(s)
    second_pool = {oid.rsplit('.', 1)[0] for oid in s.state.rules.exiled_with[s.state.rules.object_id(second.id)]}
    first_pool = {oid.rsplit('.', 1)[0] for oid in s.state.rules.exiled_with[s.state.rules.object_id(first.id)]
                  if s.state.rules.object_id(oid.rsplit('.', 1)[0]) == oid}
    to_phase(s, 'main1', turn=3)
    settle(s)
    spell = put(s, 'Lightning Bolt', 'hand', pid='p3')
    mana(s, pid='p3', R=1)
    wait_priority(s, 'p3')
    act(s, 'p3', type='cast_spell', card_id=spell.id, targets=['p1'])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p3'
    assert {o.id for o in d.options} <= second_pool
    assert not {o.id for o in d.options} & first_pool
    answer(s, [])
    settle(s)
    assert not s.state.rules.decision
    first_oid, second_oid = s.state.rules.object_id(first.id), s.state.rules.object_id(second.id)
    assert s.state.rules.object_id(spell.id) in s.state.rules.exiled_with[second_oid]
    assert s.state.rules.object_id(spell.id) not in s.state.rules.exiled_with[first_oid]
    roundtrip(s)


def test_real_snapcaster_graveyard_cast_does_not_trigger_pool78(cards):
    s = setup(cards)
    spell = put(s, 'Lightning Bolt', 'graveyard')
    cast(s, 'Snapcaster Mage')
    d = s.state.rules.decision
    assert d and spell.id in {o.id for o in d.options}
    answer(s, [spell.id])
    ids = stack_library(s, ['Divination', 'Forest', 'Sol Ring'])
    for pid in ['p2', 'p3']:
        stack_library(s, ['Grizzly Bears', 'Forest', 'Sol Ring'], pid=pid)
    source = cast(s, POOL)
    offered = ids[0]
    mana(s, R=1)
    life = s.state.players['p2'].life
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == life - 3
    assert s.state.cards[spell.id].zone == 'p1:exile'  # Native flashback replacement, not linked to Pool.
    assert s.state.rules.object_id(spell.id) not in s.state.rules.exiled_with[s.state.rules.object_id(source.id)]
    assert s.state.cards[offered].zone == 'p1:exile' and not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize('choose', [True, False])
def test_fresh_process_keeps_native_caster_and_other_linked_pool78(cards, tmp_path, choose):
    import os
    import subprocess
    import sys

    s, source, offered, spell = pending_pool_offer(cards)
    saved = tmp_path / 'pool.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
offered,spell,source,choose=sys.argv[3:]
d=s.state.rules.decision
assert d.player=='p2' and offered in {o.id for o in d.options} and spell not in {o.id for o in d.options}
before=len(s.state.zones.get('p2:hand',[]))
answer(s,[offered] if choose=='True' else [])
assert s.state.cards[offered].zone==('p1:graveyard' if choose=='True' else 'p1:exile')
assert len(s.state.zones.get('p2:hand',[]))==before+(2 if choose=='True' else 0)
assert s.state.rules.object_id(spell) in s.state.rules.exiled_with[s.state.rules.object_id(source)]
assert not s.state.rules.decision
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), offered, spell.id, source.id, str(choose)],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_pending_pool_trigger_retains_original_link_after_actual_source_destruction78(cards):
    s, source, offered = prepared_pool(cards)
    seal = put(s, 'Seal of Cleansing', 'battlefield', pid='p2')
    spell = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=seal.id,
        ability=ability(s, seal, 'Sacrifice'), targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    d = s.state.rules.decision
    assert d and d.player == 'p1' and offered in {o.id for o in d.options}
    assert s.state.cards[spell.id].zone == 'p1:exile'
    answer(s, [offered])
    assert s.state.cards[offered].zone == 'p1:graveyard'
    roundtrip(s)
