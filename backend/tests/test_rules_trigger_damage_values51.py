"""Printed non-target cast counters preserve the original spell and independent instructions."""
from __future__ import annotations

import json
import subprocess
import sys
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
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Pain Magnification', 'Tamanoa']
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_damage_values51_cards.json').read_text())


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


def cast(s, name, pool, targets=(), pid='p1', resolve=True):
    wait_priority(s, pid)
    spell = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=spell.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return spell


def setup(cards, name):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Forest', 'Island', 'Sol Ring', 'Goblin']
    s = table(cards, names, names, names)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, name, {'C': 1, 'B': 1, 'R': 1} if name == NAMES[0] else {'R': 1, 'G': 1, 'W': 1})
    assert source.zone == 'p1:battlefield'
    return s, source


@pytest.mark.parametrize('name', NAMES)
def test_complete_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def discard_all(s):
    for _ in range(10):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        assert d.resume['step'] == 'discard' and d.player in ('p2', 'p3')
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    raise AssertionError('discard never settled')


@pytest.mark.parametrize('caster,recipient,triggers', [('p1','p2',True),('p2','p3',True),('p2','p1',False)])
def test_pain_filters_recipient_independent_of_source_controller(cards, caster, recipient, triggers):
    s, _ = setup(cards, 'Pain Magnification')
    put(s, 'Forest', 'hand', recipient)
    put(s, 'Island', 'hand', recipient)
    before = len(s.state.zones[f'{recipient}:hand'])
    cast(s, 'Lightning Bolt', {'R': 1}, [recipient], pid=caster)
    d = s.state.rules.decision
    if triggers:
        assert d is not None and d.player == recipient and d.resume['step'] == 'discard'
    else:
        assert d is None
    discard_all(s)
    # The recipient is not the caster in these cases.
    assert len(s.state.zones[f'{recipient}:hand']) == before - int(triggers)
    roundtrip(s)


def test_pain_does_not_add_separate_damage_events(cards):
    s, _ = setup(cards, 'Pain Magnification')
    cast(s, 'Shock', {'R': 1}, ['p2'])
    cast(s, 'Shock', {'R': 1}, ['p2'])
    assert s.state.players['p2'].life == 36 and s.state.rules.decision is None
    roundtrip(s)


def test_pain_simultaneous_damage_discards_each_opponent_once(cards):
    s, _ = setup(cards, 'Pain Magnification')
    for pid in ('p2','p3'):
        put(s, 'Forest', 'hand', pid)
        put(s, 'Island', 'hand', pid)
    before = {p: len(s.state.zones[f'{p}:hand']) for p in ('p2','p3')}
    cast(s, 'Flame Rift', {'C': 1, 'R': 1})
    discard_all(s)
    assert all(len(s.state.zones[f'{p}:hand']) == before[p]-1 for p in before)
    assert all(p.life == 36 for p in s.state.players.values())
    roundtrip(s)


@pytest.mark.parametrize('target', ['p1','p2','creature'])
def test_tamanoa_noncreature_spell_all_recipients(cards, target):
    s, _ = setup(cards, 'Tamanoa')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Lightning Bolt', {'R': 1}, [bear.id if target == 'creature' else target])
    assert s.state.players['p1'].life == (40 if target == 'p1' else 43)
    if target == 'creature':
        assert bear.zone == 'p2:graveyard'
    roundtrip(s)


def test_tamanoa_counts_each_simultaneous_recipient_amount(cards):
    s, _ = setup(cards, 'Tamanoa')
    cast(s, 'Flame Rift', {'C': 1, 'R': 1})
    assert s.state.players['p1'].life == 48
    assert s.state.players['p2'].life == s.state.players['p3'].life == 36
    roundtrip(s)


def test_tamanoa_ignores_other_controllers_and_creature_sources(cards):
    s, _ = setup(cards, 'Tamanoa')
    cast(s, 'Lightning Bolt', {'R': 1}, ['p3'], pid='p2')
    pyro = put(s, 'Prodigal Pyromancer', 'battlefield')
    # Table setup turn stamp avoids summoning sickness; activation and damage are native.
    to_phase(s, 'main1', turn=7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=pyro.id, ability=0, sources=[], targets=['p2'])
    settle(s)
    assert s.state.players['p1'].life == 40 and s.state.players['p2'].life == 39
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_damage_amount_and_recipient(cards, tmp_path, name):
    from tests.test_rules_counter_event_comparisons50 import resolve_only

    s, source = setup(cards, name)
    put(s, 'Forest', 'hand', 'p2')
    put(s, 'Island', 'hand', 'p2')
    before = len(s.state.zones['p2:hand'])
    spell = cast(s, 'Lightning Bolt', {'R': 1}, ['p2'], resolve=False)
    resolve_only(s, spell)
    assert spell.zone == 'p1:graveyard' and s.state.zones['stack']
    saved = tmp_path / 'damage-values.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
settle(s)
if sys.argv[3]=='Pain Magnification':
 d=s.state.rules.decision
 assert d is not None and d.player=='p2' and d.resume['step']=='discard'
 act(s,'p2',type='choose',decision_id=d.id,option_ids=[d.options[0].id])
 settle(s)
 assert len(s.state.zones['p2:hand'])==int(sys.argv[4])-1
else:
 assert s.state.players['p1'].life==43
assert s.state.players['p2'].life==37
roundtrip(s)
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.name, str(before)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_tamanoa_creature_card_dealing_damage_from_graveyard_is_excluded(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s, source = setup(cards, 'Tamanoa')
    for pid in ('p1','p2'):
        put(s, 'Goblin', 'battlefield', pid)
    gem = put(s, 'Gempalm Incinerator', 'hand')
    mana(s, C=1, R=1)
    act(s, 'p1', type='activate_ability', card_id=gem.id, ability=ability_index(s, gem, 'Cycling'), sources=[])
    for _ in range(10):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = {o.id for o in d.options}
        pick = [source.id] if source.id in ids else ['yes'] if 'yes' in ids else []
        assert pick, (d.kind, d.resume, [(o.id,o.label) for o in d.options])
        act(s, d.player, type='choose', decision_id=d.id, option_ids=pick)
    assert gem.zone == 'p1:graveyard' and source.damage == 2
    assert s.state.players['p1'].life == 40
    roundtrip(s)


def test_pain_one_source_repeated_small_damage_does_not_accumulate(cards):
    s, _ = setup(cards, 'Pain Magnification')
    pyro = put(s, 'Prodigal Pyromancer', 'battlefield')
    to_phase(s, 'main1', turn=7)
    for _ in range(3):
        wait_priority(s, 'p1')
        if pyro.tapped:
            act(s, 'p1', type='tap', card_ids=[pyro.id], tapped=False)
        act(s, 'p1', type='activate_ability', card_id=pyro.id, ability=0, sources=[], targets=['p2'])
        settle(s)
        assert s.state.rules.decision is None
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_tamanoa_lethal_damage_to_itself_still_triggers_before_dying(cards):
    s, source = setup(cards, 'Tamanoa')
    cast(s, 'Lightning Bolt', {'R': 1}, [source.id])
    assert s.state.players['p1'].life == 43 and source.damage == 3
    cast(s, 'Shock', {'R': 1}, [source.id])
    assert source.zone == 'p1:graveyard' and s.state.players['p1'].life == 45
    roundtrip(s)


@pytest.mark.parametrize('matching', [False, True])
def test_tamanoa_spell_controller_not_owner_or_caster(cards, matching):
    s, source = setup(cards, 'Tamanoa')
    if matching:
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    spell = cast(s, 'Lightning Bolt', {'R': 1}, ['p2'], resolve=False)
    act(s, 'p1', type='set_controller', card_ids=[spell.id], player='p3')
    settle(s)
    assert spell.zone == 'p1:graveyard' and s.state.players['p2'].life == 37
    assert s.state.players['p1'].life == 40
    assert s.state.players['p3'].life == (43 if matching else 40)
    roundtrip(s)


def test_pain_two_small_sources_simultaneous_combat_are_not_summed(cards):
    from tests.test_rules_conditional_prevention import attack

    s, _ = setup(cards, 'Pain Magnification')
    bears = [put(s, 'Grizzly Bears', 'battlefield', pid) for pid in ('p1', 'p3')]
    act(s, 'p1', type='set_controller', card_ids=[bears[1].id], player='p1')
    attack(s, bears, turn=7)
    to_phase(s, 'end_combat')
    settle(s)
    assert s.state.players['p2'].life == 36 and s.state.rules.decision is None
    roundtrip(s)
