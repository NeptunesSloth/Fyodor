"""Native crew/saddle readers and original source identities."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import pick, put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

DATA = json.loads((Path(__file__).parent / 'fixtures/crew_saddle_readers81_cards.json').read_text())
CANDIDATES = ['Subterranean Schooner', 'Ghost Ark', "Archmage's Newt"]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='read81', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup81(cards, name):
    names = list(dict.fromkeys([c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Forest', 'Island', 'Sol Ring']))
    s = table(cards, names, ['Grizzly Bears', 'Forest', 'Lightning Bolt'], [])
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    return s, source, bear


def crew81(s, source, bear, saddle=False):
    index = next(a.index for a in chars(s, source).abilities if a.text.lower().startswith('saddle' if saddle else 'crew'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[bear.id])
    settle(s)


@pytest.mark.parametrize('name', CANDIDATES)
def test_whole81(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('change', ['none', 'destroy', 'blink'])
def test_schooner_original_vehicle_source_preserves_targeted_explore(cards, change):
    s, source, bear = setup81(cards, 'Subterranean Schooner')
    spell = put(s, 'Cloudshift' if change == 'blink' else 'Disenchant', 'hand')
    crew81(s, source, bear)
    forest = next(c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1')
    act(s, 'p1', type='move', card_ids=[forest.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    d = s.state.rules.decision
    assert d is not None and bear.id in {o.id for o in d.options}
    pick(s, [bear.id])
    assert s.state.zones.get('stack')
    if change != 'none':
        mana(s, W=1, C=1)
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    assert s.state.cards[forest.id].zone == 'p1:hand'
    assert not bear.counters.get('+1/+1')


def test_ghost_locks_only_existing_artifact_creatures_then_actual_unearth(cards):
    s, source, bear = setup81(cards, 'Ghost Ark')
    ornithopter = put(s, 'Ornithopter', 'graveyard')
    land = put(s, 'Sol Ring', 'graveyard')
    creature = put(s, 'Llanowar Elves', 'graveyard')
    crew81(s, source, bear)
    assert any(a.text.lower().startswith('unearth') for a in chars(s, ornithopter).abilities), {'source': [(a.kind,a.text) for a in chars(s, source).abilities], 'target': [a.text for a in chars(s, ornithopter).abilities], 'effects': [(e.layer,e.affected,e.add_abilities,e.ability_zone) for e in s.state.rules.effects]}
    assert not any(a.text.lower().startswith('unearth') for a in chars(s, land).abilities)
    assert not any(a.text.lower().startswith('unearth') for a in chars(s, creature).abilities)
    late = put(s, 'Memnite', 'graveyard')
    assert not any(a.text.lower().startswith('unearth') for a in chars(s, late).abilities)
    spell = put(s, 'Disenchant', 'hand')
    mana(s, W=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    index = next(a.index for a in chars(s, ornithopter).abilities if a.text.lower().startswith('unearth'))
    mana(s, C=3)
    act(s, 'p1', type='activate_ability', card_id=ornithopter.id, ability=index)
    settle(s)
    assert s.state.cards[ornithopter.id].zone == 'p1:battlefield'
    assert 'haste' in chars(s, ornithopter).keywords
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[ornithopter.id])
    settle(s)
    assert s.state.cards[ornithopter.id].zone == 'p1:exile'


def newt_grant81(cards, name, saddled, blink=False):
    from tests.test_rules_unblocked_riders32 import unblocked
    s, source, bear = setup81(cards, "Archmage's Newt")
    target = put(s, name, 'graveyard')
    if saddled:
        elf = put(s, 'Llanowar Elves', 'battlefield')
        index = next(a.index for a in chars(s, source).abilities if a.text.lower().startswith('saddle'))
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[bear.id, elf.id])
        settle(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    unblocked(s, source)
    for _ in range(16):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None and target.id in {o.id for o in d.options}
    pick(s, [target.id])
    if blink:
        spell = put(s, 'Cloudshift', 'hand')
        mana(s, W=1)
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    to_phase(s, 'main2', turn=4)
    return s, source, target


@pytest.mark.parametrize('saddled', [True, False])
@pytest.mark.parametrize('blink', [True, False])
def test_newt_current_or_last_known_saddle_determines_flashback_cost(cards, saddled, blink):
    from app.rules import graveyard_grants
    s, source, target = newt_grant81(cards, 'Lightning Bolt', saddled, blink)
    assert graveyard_grants.flashback_cost(s.state, s.state.cards[target.id], chars(s, target), s.cards) == ('{0}' if saddled else '{R}')
    before = s.state.players['p2'].life
    if not saddled:
        mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=target.id, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == before - 3
    assert s.state.cards[target.id].zone == 'p1:exile'


@pytest.mark.parametrize('name', CANDIDATES)
def test_true_cold_native_grant_or_pending_explore81(cards, tmp_path, name):
    import subprocess
    import sys

    import app
    if name == "Archmage's Newt":
        s, source, target = newt_grant81(cards, 'Lightning Bolt', True, True)
    else:
        s, source, bear = setup81(cards, name)
        if name == 'Ghost Ark':
            target = put(s, 'Ornithopter', 'graveyard')
            crew81(s, source, bear)
        else:
            crew81(s, source, bear)
            target = next(c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1')
            act(s, 'p1', type='move', card_ids=[target.id], to={'player':'p1','zone':'library'}, position='top')
            act(s, 'p1', type='set_prefs', hold_priority=True)
            to_phase(s, 'declare_attackers', turn=4)
            attack(s, (source, 'p2'))
            pick(s, [bear.id])
            assert s.state.zones.get('stack')
    saved = tmp_path / 'reader81.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_bandmate_references import mana
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
name,target=sys.argv[3:]
if name=='Subterranean Schooner':
 settle(s);assert s.state.cards[target].zone=='p1:hand'
elif name=='Ghost Ark':
 index=next(a.index for a in chars(s,s.state.cards[target]).abilities if a.text.lower().startswith('unearth'))
 mana(s,C=3);act(s,'p1',type='activate_ability',card_id=target,ability=index);settle(s)
 assert s.state.cards[target].zone=='p1:battlefield'
 assert 'haste' in chars(s,s.state.cards[target]).keywords
else:
 before=s.state.players['p2'].life
 act(s,'p1',type='cast_spell',card_id=target,targets=['p2']);settle(s)
 assert s.state.players['p2'].life==before-3
 assert s.state.cards[target].zone=='p1:exile'
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, target.id],
        capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('saddled', [False, True])
def test_newt_card_without_mana_cost_requires_zero_cost_branch(cards, saddled):
    from app.game.errors import ActionError
    s, source, target = newt_grant81(cards, 'Ancestral Vision', saddled)
    before = len(s.state.zones.get('p1:hand', []))
    if not saddled:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=target.id, targets=['p1'])
        assert s.state.cards[target.id].zone == 'p1:graveyard'
        return
    act(s, 'p1', type='cast_spell', card_id=target.id, targets=['p1'])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:exile'
    assert len(s.state.zones.get('p1:hand', [])) == before + 3


def test_ghost_grant_expires_and_does_not_follow_new_graveyard_object(cards):
    s, source, bear = setup81(cards, 'Ghost Ark')
    target = put(s, 'Ornithopter', 'graveyard')
    other = put(s, 'Memnite', 'graveyard')
    crew81(s, source, bear)
    assert any(a.text.lower().startswith('unearth') for a in chars(s, target).abilities)
    act(s, 'p1', type='move', card_ids=[target.id], to={'player':'p1','zone':'hand'})
    act(s, 'p1', type='move', card_ids=[target.id], to={'player':'p1','zone':'graveyard'})
    assert not any(a.text.lower().startswith('unearth') for a in chars(s, target).abilities)
    assert any(a.text.lower().startswith('unearth') for a in chars(s, other).abilities)
    to_phase(s, 'main1', turn=5)
    assert not any(a.text.lower().startswith('unearth') for a in chars(s, other).abilities)


@pytest.mark.parametrize('saddled', [False, True])
def test_newt_variable_mana_cost_is_payable_only_for_mana_cost_branch(cards, saddled):
    s, source, target = newt_grant81(cards, 'Volcanic Geyser', saddled)
    before = s.state.players['p2'].life
    mana(s, R=2, C=3)
    if saddled:
        from app.game.errors import ActionError
        saved = s.state.model_dump_json()
        with pytest.raises(ActionError, match='X is 0'):
            act(s, 'p1', type='cast_spell', card_id=target.id, x_value=3, targets=['p2'])
        assert s.state.model_dump_json() == saved
        act(s, 'p1', type='cast_spell', card_id=target.id, targets=['p2'])
    else:
        act(s, 'p1', type='cast_spell', card_id=target.id, x_value=3, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == before - (0 if saddled else 3)
    assert s.state.cards[target.id].zone == 'p1:exile'


@pytest.mark.parametrize('name', CANDIDATES)
def test_actual_printed_card_cast81(cards, name):
    names = list(dict.fromkeys([c['name'] for c in DATA] + ['Forest']))
    s = table(cards, names, ['Forest'], [])
    source = put(s, name, 'hand')
    start(s)
    mana(s, U=2, C=4)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert chars(s, source).name == name
