"""Native targeting source kinds, aggregate watches and copied backup provenance."""
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
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars

NAMES = ['Professor Hojo', 'Leyline of Combustion', 'Mirror-Shield Hoplite']
DATA = json.loads((Path(__file__).parent / 'fixtures/targeting_sources77_cards.json').read_text())


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



@pytest.mark.parametrize('name', NAMES)
def test_canonical_whole_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards, name, pyro=False):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves']
    s = table(cards, names, names, names)
    source = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    if pyro:
        put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s, source, bear, elf


def test_hojo_reduced_first_equip_and_once_draw(cards):
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    dagger = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='activate_ability', card_id=dagger.id, ability=2, targets=[bear.id], sources=[])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=dagger.id, ability=2, targets=[elf.id], sources=[])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    assert dagger.attached_to == elf.id


def test_hojo_spell_target_negative(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    before = len(s.state.zones['p1:hand'])
    cast(s, 'Giant Growth', {'G':1}, [bear.id])
    # The spell is moved into hand from the deck by the helper, then spent.
    assert len(s.state.zones['p1:hand']) == before


def test_leyline_mixed_player_permanent_targets_aggregate_once(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Leyline of Combustion')
    cast(s, 'Electrolyze', {'C':1, 'U':1, 'R':1}, ['p1', bear.id], pid='p2', target_counts=[2], division=[1,1])
    assert s.state.players['p2'].life == 38
    assert s.state.players['p1'].life == 39


def test_hoplite_actual_backup_copies_and_grants_keywords(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Mirror-Shield Hoplite')
    cast(s, 'Boon-Bringer Valkyrie', {'C':3, 'W':2})
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    # Keep the original backup target for the copy.
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'])
    settle(s)
    assert bear.counters.get('+1/+1',0) == 2
    assert {'flying','first strike','lifelink'} <= chars(s, bear).keywords


@pytest.mark.parametrize('same', [True, False])
def test_leyline_one_spell_repeated_or_multiple_permanent_targets_once(cards, same):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Leyline of Combustion')
    cast(s, 'Seeds of Strength', {'G':1, 'W':1}, [bear.id, bear.id if same else elf.id, bear.id], pid='p2', target_counts=[1,1,1])
    assert s.state.players['p2'].life == 38


def test_leyline_own_spell_does_not_trigger(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Leyline of Combustion')
    cast(s, 'Giant Growth', {'G':1}, [bear.id])
    assert s.state.players['p1'].life == 40


def test_hoplite_nonbackup_activated_target_does_not_trigger(cards):
    s, source, bear, elf = setup(cards, 'Mirror-Shield Hoplite')
    dagger = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=dagger.id, ability=2, targets=[bear.id], sources=[])
    settle(s)
    assert s.state.rules.decision is None and not bear.counters


def test_hoplite_countered_original_backup_uses_native_lki_copy(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Mirror-Shield Hoplite')
    cast(s, 'Boon-Bringer Valkyrie', {'C':3, 'W':2})
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    original = next(cid for cid, entry in s.state.rules.stack.items() if entry.name == 'Boon-Bringer Valkyrie')
    cast(s, 'Stifle', {'U':1}, [original])
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'])
    settle(s)
    assert bear.counters.get('+1/+1',0) == 1
    assert {'flying','first strike','lifelink'} <= chars(s, bear).keywords


def test_hoplite_generic_counter_etb_is_not_backup(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Mirror-Shield Hoplite')
    cast(s, 'Bond Beetle', {'G':1})
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert s.state.rules.decision is None
    assert bear.counters.get('+1/+1',0) == 1


def test_copied_backup_retains_keyword_and_triggers_unused_hoplite(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, source, bear, elf = setup(cards, 'Mirror-Shield Hoplite')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Boon-Bringer Valkyrie', {'C':3, 'W':2})
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[other.id])
    original = next(cid for cid, entry in s.state.rules.stack.items() if entry.name == 'Boon-Bringer Valkyrie')
    cast(s, 'Return the Favor', {'C':1, 'R':2}, [original], modes=[0])
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'])
    settle(s)
    assert bear.counters.get('+1/+1',0) == 2
    assert other.counters.get('+1/+1',0) == 1


@pytest.mark.parametrize('mode', ['Leyline', 'Hoplite', 'Hojo'])
def test_genuine_cold_pending_target_event_or_copy_choice(cards, tmp_path, mode):
    import subprocess
    import sys

    import app
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    name = {'Leyline':'Leyline of Combustion', 'Hoplite':'Mirror-Shield Hoplite', 'Hojo':'Professor Hojo'}[mode]
    s, source, bear, elf = setup(cards, name)
    before = len(s.state.zones['p1:hand'])
    if mode == 'Hojo':
        dagger = put(s, 'Silver-Inlaid Dagger', 'battlefield')
        act(s, 'p1', type='activate_ability', card_id=dagger.id, ability=2, targets=[bear.id], sources=[])
        assert s.state.rules.stack
    elif mode == 'Leyline':
        wait_priority(s, 'p2')
        spell = put(s, 'Lightning Bolt', 'hand', 'p2')
        mana(s, pid='p2', R=1)
        act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[bear.id], sources=[])
        assert s.state.rules.stack
    else:
        cast(s, 'Boon-Bringer Valkyrie', {'C':3, 'W':2})
        d = s.state.rules.decision
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
        settle(s)
        assert s.state.rules.decision is not None
    saved = tmp_path/'targeting.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_wave6c_tokens_pumps import chars
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
mode,bear,before=sys.argv[3:]
if mode=='Hoplite':
 d=s.state.rules.decision
 assert d is not None
 act(s,d.player,type='choose',decision_id=d.id,option_ids=['keep'])
settle(s)
if mode=='Leyline':assert s.state.players['p2'].life==38
elif mode=='Hojo':assert len(s.state.zones['p1:hand'])==int(before)+1
else:
 c=s.state.cards[bear]
 assert c.counters.get('+1/+1',0)==2
 assert {'flying','first strike','lifelink'} <= chars(s,c).keywords
assert s.state.rules.decision is None
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), mode, bear.id, str(before)],
                            capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name,pool', [('Leyline of Combustion', {'C':2,'R':2}), ('Mirror-Shield Hoplite', {'R':1,'W':1})])
def test_paid_full_target_watcher_entry(cards, name, pool):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    start(s)
    source = cast(s, name, pool)
    assert source.zone == 'p1:battlefield'


def test_hoplite_actual_vigilance_attack_stays_untapped(cards):
    from tests.test_rules_wave30m_durations import to_phase
    from tests.test_rules_wave30p_combat import attack
    s, source, bear, elf = setup(cards, 'Mirror-Shield Hoplite')
    to_phase(s, 'declare_attackers')
    attack(s, (source, 'p2'))
    settle(s)
    assert source.is_attacking and not source.tapped


def test_leyline_native_opening_hand_entry(cards):
    from tests.test_rules_wave18c_pregame_vote import answer, table3
    s = table3(cards, ['Leyline of Combustion'], [], [])
    for pid in ('p1','p2','p3'):
        act(s, pid, type='mulligan_keep')
    answer(s, 'p1', ['Leyline of Combustion'])
    answer(s, 'p2')
    answer(s, 'p3')
    source = next(c for c in s.state.cards.values() if c.name == 'Leyline of Combustion' and c.owner == 'p1')
    assert source.zone == 'p1:battlefield'


@pytest.mark.parametrize('name', ['Professor Hojo', 'Leyline of Combustion'])
def test_opponent_native_activated_source_kind_targets_creature(cards, name):
    from tests.test_rules_bandmate_references import wait_priority
    s, source, bear, elf = setup(cards, name, pyro=True)
    pyro = next(c for c in s.state.cards.values() if c.name == 'Prodigal Pyromancer' and c.owner == 'p2')
    before = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=pyro.id, ability=0, targets=[bear.id], sources=[])
    settle(s)
    if name == 'Professor Hojo':
        assert len(s.state.zones['p1:hand']) == before + 1
    else:
        assert s.state.players['p2'].life == 38
    assert bear.damage == 1
