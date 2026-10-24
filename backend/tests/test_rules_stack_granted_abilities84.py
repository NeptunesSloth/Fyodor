"""Actual stack spells gain native abilities with exact object and duration lifetimes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/stack_granted_abilities84_cards.json').read_text())
LUX, LORD, TYVAR, GALEA = [c['name'] for c in DATA[:4]]
NAMES = [LUX, LORD, TYVAR, GALEA]
BIRGI = 'Birgi, God of Storytelling // Harnfel, Horn of Bounty'
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
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest', 'Silver Myr', 'Skyreach Manta', 'Elvish Mystic',
                          'Jacob Hauken, Inspector // Hauken\'s Insight')




@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical84(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'



def test_actual_lux_grants_sunburst_from_real_spent_colors_to_original_stack_spell84(cards):
    s = setup(cards)
    cast(s, LUX)
    target = put(s, 'Silver Myr', 'hand')
    act(s, 'p1', type='clear_mana')
    mana(s, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    for _ in range(20):
        if not any(e.kind == 'trigger' for e in s.state.rules.stack.values()):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert any(a.text.rstrip('.') == 'Sunburst' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).abilities)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == 2
    assert any(a.text.rstrip('.') == 'Sunburst' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).abilities)
    roundtrip(s)


def resolve_grants(s):
    for _ in range(30):
        if not any(e.kind == 'trigger' for e in s.state.rules.stack.values()):
            return
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('native grant triggers did not resolve')


@pytest.mark.parametrize('damaged', [False, True])
def test_bloodlord_grants_actual_bloodthirst_and_reads_real_opponent_damage84(cards, damaged):
    s = setup(cards)
    cast(s, LORD)
    if damaged:
        cast(s, 'Lightning Bolt', targets=['p2'])
    target = put(s, 'Vampire Nighthawk', 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    resolve_grants(s)
    assert s.state.cards[target.id].zone == 'stack'
    assert any(a.text.rstrip('.').casefold() == 'bloodthirst 3' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).abilities)
    settle(s)
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == (3 if damaged else 0)
    roundtrip(s)


def test_real_tyvar_loyalty_creates_native_emblem_grants_stack_haste_draws_two_and_expires84(cards):
    s = setup(cards)
    cast(s, 'Doubling Season')
    source = cast(s, TYVAR)
    assert s.state.cards[source.id].counters.get('loyalty') == 6
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability(s, source, '−6:'))
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    emblems = [c for c in s.state.cards.values() if c.zone == 'p1:command' and c.token and c.token.type_line == 'Emblem']
    assert len(emblems) == 1
    target = put(s, 'Elvish Mystic', 'hand')
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=target.id)
    resolve_grants(s)
    assert len(s.state.zones['p1:hand']) == before - 1 + 2
    assert 'haste' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).keywords
    settle(s)
    assert 'haste' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).keywords
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': target.id, 'target': 'p2'}])
    settle(s)
    to_phase(s, 'main1', turn=4)
    settle(s)
    assert 'haste' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).keywords
    roundtrip(s)


def top_cast(s, cards, name, source_name=GALEA, **kwargs):
    from app.rules import permissions

    cid = stack_library(s, [name])[0]
    card_now = s.state.cards[cid]
    grants = permissions.grants(s.state, 'p1', card_now, Plan(s.state, 'p1', cards, None).ch(card_now), cards)
    selected = next(g for g in grants if g.label == source_name)
    act(s, 'p1', type='cast_spell', card_id=cid, via=selected.choice_key, **kwargs)
    return cid


def test_galea_actual_selected_top_permission_gives_spell_real_etb_ability_then_attaches84(cards):
    from tests.test_rules_controller_tutors import answer

    s = setup(cards)
    cast(s, GALEA)
    target = put(s, 'Grizzly Bears', 'battlefield')
    gear = top_cast(s, cards, 'Bonesplitter')
    resolve_grants(s)
    assert s.state.cards[gear].zone == 'stack'
    quote = 'When this Equipment enters, attach it to target creature you control.'
    assert any(a.text == quote for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[gear]).abilities)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1' and target.id in {o.id for o in d.options}
    answer(s, [target.id])
    assert s.state.cards[gear].attached_to == target.id
    roundtrip(s)


def test_lux_printed_and_granted_sunburst_each_count_actual_five_colors84(cards):
    s = setup(cards)
    cast(s, LUX)
    target = put(s, 'Skyreach Manta', 'hand')
    act(s, 'p1', type='clear_mana')
    mana(s, W=1, U=1, B=1, R=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    settle(s)
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == 10


@pytest.mark.parametrize('name', ['Sol Ring', 'Grizzly Bears'])
def test_lux_requires_both_artifact_and_creature84(cards, name):
    s = setup(cards)
    cast(s, LUX)
    target = cast(s, name)
    assert not any(a.text.rstrip('.') == 'Sunburst' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).abilities)


def test_galea_competing_selected_forge_authority_does_not_grant_attachment84(cards):
    s = setup(cards)
    cast(s, GALEA)
    cast(s, 'Mystic Forge')
    put(s, 'Grizzly Bears', 'battlefield')
    gear = top_cast(s, cards, 'Bonesplitter', source_name='Mystic Forge')
    settle(s)
    assert s.state.cards[gear].zone == 'p1:battlefield'
    assert s.state.cards[gear].attached_to is None
    assert s.state.rules.decision is None


def test_galea_ordinary_hand_equipment_gets_no_extra_ability84(cards):
    s = setup(cards)
    cast(s, GALEA)
    put(s, 'Grizzly Bears', 'battlefield')
    gear = cast(s, 'Bonesplitter')
    assert s.state.cards[gear.id].attached_to is None
    assert s.state.rules.decision is None


def test_galea_top_aura_retains_ordinary_target_without_equipment_callback84(cards):
    s = setup(cards)
    cast(s, GALEA)
    target = put(s, 'Grizzly Bears', 'battlefield')
    aura = top_cast(s, cards, 'Rancor', targets=[target.id])
    settle(s)
    assert s.state.cards[aura].attached_to == target.id
    assert s.state.rules.decision is None


@pytest.mark.parametrize('mode', ['lux_stack', 'galea_authority'])
def test_genuine_cold_stack_grant_and_selected_permission84(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    s = setup(cards)
    if mode == 'lux_stack':
        cast(s, LUX)
        target = put(s, 'Silver Myr', 'hand').id
        act(s, 'p1', type='clear_mana')
        mana(s, W=1, U=1)
        act(s, 'p1', type='cast_spell', card_id=target)
        resolve_grants(s)
    else:
        cast(s, GALEA)
        target = put(s, 'Grizzly Bears', 'battlefield').id
        stack_library(s, ['Bonesplitter'])
    saved = tmp_path / 'stack84.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from app.rules.plan import Plan
from app.rules import permissions
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
mode,target=sys.argv[3:5]
if mode=='lux_stack':
 assert s.state.cards[target].zone=='stack'
 assert any(a.text.rstrip('.')=='Sunburst' for a in Plan(s.state,'p1',r,None).ch(s.state.cards[target]).abilities)
 settle(s)
 assert s.state.cards[target].counters.get('+1/+1',0)==2
else:
 cid=s.state.zones['p1:library'][0]
 c=s.state.cards[cid]
 grant=next(g for g in permissions.grants(s.state,'p1',c,Plan(s.state,'p1',r,None).ch(c),r) if g.label=='Galea, Kindler of Hope')
 act(s,'p1',type='cast_spell',card_id=cid,via=grant.choice_key)
 settle(s)
 assert s.state.rules.decision
 answer(s,[target])
 assert s.state.cards[cid].attached_to==target
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), mode, target],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr


def test_lux_pending_trigger_survives_source_departure84(cards):
    s = setup(cards)
    source = cast(s, LUX)
    target = put(s, 'Silver Myr', 'hand')
    act(s, 'p1', type='clear_mana')
    mana(s, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    cast(s, 'Disperse', targets=[source.id])
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == 2


def test_galea_resolved_spell_grant_survives_source_departure84(cards):
    from tests.test_rules_controller_tutors import answer

    s = setup(cards)
    source = cast(s, GALEA)
    target = put(s, 'Grizzly Bears', 'battlefield')
    gear = top_cast(s, cards, 'Bonesplitter')
    resolve_grants(s)
    cast(s, 'Disperse', targets=[source.id])
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert s.state.rules.decision
    answer(s, [target.id])
    assert s.state.cards[gear].attached_to == target.id


def test_lux_grant_does_not_follow_bounced_card_into_new_spell_incarnation84(cards):
    s = setup(cards)
    source = cast(s, LUX)
    target = put(s, 'Silver Myr', 'hand')
    act(s, 'p1', type='clear_mana')
    mana(s, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    settle(s)
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == 2
    cast(s, 'Disperse', targets=[target.id])
    put(s, 'Disperse', 'hand')
    cast(s, 'Disperse', targets=[source.id])
    act(s, 'p1', type='clear_mana')
    mana(s, W=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=target.id)
    resolve_grants(s)
    assert not any(a.text.rstrip('.') == 'Sunburst' for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id]).abilities)
    settle(s)
    assert s.state.cards[target.id].counters.get('+1/+1', 0) == 0
