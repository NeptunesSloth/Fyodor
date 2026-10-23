"""Native permanent offers defer every outcome until all APNAP choices finish."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/nightshade88_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Sol Ring', 'Forest', 'Island']


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


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)



def test_whole(cards):
    assert coverage.of_card_data(cards.resolve('Nightshade Assassin')).level == 'FULL'


def test_actual_count_two(cards):
    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    a = put(s, 'Dark Ritual', 'hand')
    b = put(s, 'Go for the Throat', 'hand')
    source = put(s, 'Nightshade Assassin', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'B': 2})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[], sources=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    assert d.resume['step'] == 'trigger_target'
    choose(s, [target.id])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'nightshade_reveal88'
    assert {o.id for o in d.options} == {a.id, b.id}
    choose(s, [a.id, b.id])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not s.state.rules.revealed_activation_costs
    from app.game.visibility import ALL
    assert ALL not in s.state.cards[a.id].revealed_to
    assert ALL not in s.state.cards[b.id].revealed_to


def cast_assassin(s):
    source = put(s, 'Nightshade Assassin', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'B': 2})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[], sources=[])
    settle(s)
    return source


@pytest.mark.parametrize('count', [0, 1])
def test_zero_or_one_resolution_count(cards, count):
    from app.rules.plan import Plan

    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    a = put(s, 'Dark Ritual', 'hand')
    source = cast_assassin(s)
    choose(s, [target.id])
    choose(s, [a.id] if count else [])
    ch = Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[target.id])
    assert ch.pt == (2-count, 2-count)
    assert 'first strike' in {k.lower() for k in Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[source.id]).keywords}
    roundtrip(s)


def test_reveal_pure_cost_has_no_mana_ability_window(cards):
    from app.game.errors import ActionError

    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    a = put(s, 'Dark Ritual', 'hand')
    ring = put(s, 'Sol Ring', 'battlefield')
    cast_assassin(s)
    choose(s, [target.id])
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=ring.id, ability=0)
    assert s.state.model_dump(mode='json') == before
    choose(s, [a.id])


def test_native_madness_cast_and_resolution_reveal(cards):
    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    assassin = put(s, 'Nightshade Assassin', 'hand')
    a = put(s, 'Dark Ritual', 'hand')
    opt = put(s, 'Opt', 'hand')
    loot = put(s, 'Faithless Looting', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1, 'B': 1})
    act(s, 'p1', type='cast_spell', card_id=loot.id, targets=[], sources=[])
    settle(s)
    choose(s, [assassin.id, opt.id])
    assert s.state.cards[assassin.id].zone == 'p1:exile'
    assert 'Madness' in s.state.rules.decision.prompt
    choose(s, ['yes'])
    assert s.state.cards[assassin.id].zone == 'p1:battlefield'
    choose(s, [target.id])
    choose(s, [a.id])
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    assert s.state.players['p1'].mana == {}


def test_actual_first_strike_combat(cards):
    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    put(s, 'Dark Ritual', 'hand')
    source = cast_assassin(s)
    choose(s, [target.id])
    choose(s, [])
    haste = put(s, 'Expedite', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1})
    act(s, 'p1', type='cast_spell', card_id=haste.id, targets=[source.id], sources=[])
    settle(s)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == 'declare_attackers':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    for _ in range(30):
        if s.state.rules.decision and s.state.rules.decision.kind == 'declare_blockers':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': target.id, 'attacker_id': source.id}])
    for _ in range(30):
        if s.state.turn.phase == 'main2':
            break
        d = s.state.rules.decision
        if d and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].damage == 0
    roundtrip(s)


def test_illegal_target_no_reveal_choice(cards):
    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    put(s, 'Dark Ritual', 'hand')
    source = cast_assassin(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target.id])
    bounce = put(s, 'Unsummon', 'hand', pid='p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    act(s, 'p2', type='cast_spell', card_id=bounce.id, targets=[target.id], sources=[])
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:hand'
    assert s.state.rules.decision is None and not s.state.rules.revealed_activation_costs
    assert s.state.cards[source.id].zone == 'p1:battlefield'


def test_existing_sasaya_hand_reveal_survives_nightshade_resolution(cards):
    from app.game.visibility import ALL

    s = game(cards)
    for pid in ['p1', 'p2', 'p3']:
        act(s, pid, type='set_prefs', hold_priority=True)
    sasaya = put(s, next(c['name'] for c in DATA if c['name'].startswith('Sasaya,')), 'battlefield')
    put(s, 'Vedalken Orrery', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    a = put(s, 'Dark Ritual', 'hand')
    source = put(s, 'Nightshade Assassin', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=sasaya.id, ability=0, targets=[], sources=[])
    assert ALL in s.state.cards[a.id].revealed_to
    old = next(c.id for c in s.state.cards.values() if c.zone == 'stack')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'B': 2})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[], sources=[])
    settle(s)
    choose(s, [target.id])
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[a.id])
    assert s.state.cards[old].zone == 'stack'
    assert ALL in s.state.cards[a.id].revealed_to
    settle(s)
    assert ALL not in s.state.cards[a.id].revealed_to
    assert not s.state.rules.revealed_activation_costs


def test_original_trigger_survives_source_bounce_new_hand_card_counts(cards):
    from app.rules.plan import Plan

    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    source = cast_assassin(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target.id])
    bounce = put(s, 'Unsummon', 'hand', pid='p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    act(s, 'p2', type='cast_spell', card_id=bounce.id, targets=[source.id], sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert {o.id for o in s.state.rules.decision.options} == {source.id}
    choose(s, [source.id])
    assert Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[target.id]).pt == (1, 1)
    assert not s.state.rules.revealed_activation_costs


@pytest.mark.parametrize('chosen_count', [0, 2])
def test_true_cold_private_resolution_choice(cards, tmp_path, chosen_count):
    import os
    import subprocess
    import sys

    import app

    s = game(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    a = put(s, 'Dark Ritual', 'hand')
    b = put(s, 'Go for the Throat', 'hand')
    cast_assassin(s)
    choose(s, [target.id])
    assert s.state.rules.decision.resume['step'] == 'nightshade_reveal88'
    for pid in ['p2', 'p3']:
        assert not any(c.id in json.dumps(s.view(pid)['rules']['decision']) for c in [a, b])
    saved = tmp_path / 'nightshade88.json'
    saved.write_text(s.state.model_dump_json())
    backend = Path(app.__file__).resolve().parents[1]
    code = r'''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.game.visibility import ALL
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
target,first,second,count=sys.argv[3:]
d=s.state.rules.decision
assert d and d.resume['step']=='nightshade_reveal88'
act(s,d.player,type='choose',decision_id=d.id,option_ids=[first,second] if int(count) else [])
settle(s)
if int(count):
 assert s.state.cards[target].zone=='p2:graveyard'
else:
 assert Plan.view(s.state,'p1',s.cards).ch(s.state.cards[target]).pt==(2,2)
assert ALL not in s.state.cards[first].revealed_to and ALL not in s.state.cards[second].revealed_to
assert not s.state.rules.revealed_activation_costs
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id, a.id, b.id, str(chosen_count)],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend) + os.pathsep + os.environ.get('PYTHONPATH', '')},
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
