"""Hybrid power-up choices retain native cost, purpose, and per-object authority."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table

SOURCES = ['Abomination, Terrifying Titan', 'Brawn, Amadeus Cho', 'She-Hulk, Attorney-at-Law']
DATA = json.loads((Path(__file__).parent / 'fixtures/hybrid_power_up71_cards.json').read_text())
NAMES = [c['name'] for c in DATA] + ['Grizzly Bears']


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


def setup(cards):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    return s


def cast(s, name):
    c = put(s, name, 'hand')
    n = {SOURCES[0]: 3, SOURCES[1]: 1, SOURCES[2]: 2}[name]
    mana(s, C=n, G=1)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=c.id, sources=[])
    settle(s)
    assert c.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    if name == SOURCES[1]:
        assert len(s.state.zones['p1:hand']) == before
    return c


def activate(s, c, pool, branch=None, targets=()):
    wait_priority(s, c.controller)
    if pool:
        mana(s, pid=c.controller, **pool)
    args = {'type': 'activate_ability', 'card_id': c.id, 'ability': 1, 'sources': [], 'targets': list(targets)}
    if c.name == SOURCES[0]:
        args['target_counts'] = [len(targets)]
    if branch is not None:
        args['cost_choices'] = [{'component': 20, 'cards': [f'either:{branch}']}]
    act(s, c.controller, **args)
    return args


def verify_effect(s, c, hand):
    expected = 1 if c.name == SOURCES[0] else hand if c.name == SOURCES[1] else 2
    assert c.counters == {'+1/+1': expected}


@pytest.mark.parametrize('name', SOURCES)
def test_whole_canonicals(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,branch,pool', [
    (SOURCES[0], 0, {'C': 2, 'R': 1}), (SOURCES[0], 1, {'C': 1, 'R': 2}),
    (SOURCES[0], 2, {'C': 2, 'G': 1}), (SOURCES[0], 3, {'C': 1, 'G': 2}),
    (SOURCES[1], 0, {'C': 3}), (SOURCES[1], 1, {'C': 2, 'G': 1}), (SOURCES[1], 2, {'C': 2, 'U': 1}),
    (SOURCES[2], 0, {'C': 4}), (SOURCES[2], 1, {'C': 3, 'G': 1}), (SOURCES[2], 2, {'C': 3, 'W': 1}),
])
def test_each_concrete_hybrid_reduction_branch_is_paid_once(cards, name, branch, pool):
    s = setup(cards)
    c = cast(s, name)
    hand = len(s.state.zones['p1:hand'])
    activate(s, c, pool, branch)
    settle(s)
    verify_effect(s, c, hand)
    assert not s.state.players['p1'].mana
    roundtrip(s)


@pytest.mark.parametrize('branch,spent', [(0, False), (1, True)])
def test_hulk_keeps_free_and_colored_branches_distinct(cards, branch, spent):
    s = setup(cards)
    put(s, 'Hulk, Gamma Goliath', 'battlefield')
    c = cast(s, SOURCES[1])
    hand = len(s.state.zones['p1:hand'])
    activate(s, c, {'G': 1}, branch)
    settle(s)
    verify_effect(s, c, hand)
    assert s.state.players['p1'].mana == ({} if spent else {'G': 1})
    roundtrip(s)


def test_used_power_up_keeps_original_once_per_object_limit(cards):
    s = setup(cards)
    c = cast(s, SOURCES[1])
    activate(s, c, {'C': 3}, 0)
    settle(s)
    mana(s, C=3)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        activate(s, c, {}, 0)
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_wonder_man_grants_exactly_one_additional_activation(cards):
    s = setup(cards)
    put(s, 'Wonder Man, Hollywood Hero', 'battlefield')
    c = cast(s, SOURCES[1])
    hand = len(s.state.zones['p1:hand'])
    for _ in range(2):
        activate(s, c, {'C': 3}, 0)
        settle(s)
    assert c.counters == {'+1/+1': 2 * hand}
    mana(s, C=3)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        activate(s, c, {}, 0)
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_later_turn_uses_full_hybrid_activation_cost(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    c = cast(s, SOURCES[1])
    to_phase(s, 'main1', turn=7)
    mana(s, C=3)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        activate(s, c, {})
    assert s.state.model_dump_json() == before
    hand = len(s.state.zones['p1:hand'])
    activate(s, c, {'C': 1, 'G': 1})
    settle(s)
    verify_effect(s, c, hand)
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_real_power_up_mana_and_activation_trigger_keep_original_purpose(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    jet = put(s, 'Quinjet Technician', 'battlefield')
    to_phase(s, 'main1', turn=7)
    marvel = put(s, 'Marvel Boy, Noh-Varr', 'battlefield')
    c = cast(s, SOURCES[1])
    assert marvel.counters == {'+1/+1': 1}
    hand = len(s.state.zones['p1:hand'])
    mana(s, C=1)
    act(s, 'p1', type='activate_ability', card_id=c.id, ability=1, sources=[jet.id])
    settle(s)
    verify_effect(s, c, hand)
    assert jet.tapped and not s.state.players['p1'].mana
    assert marvel.counters == {'+1/+1': 2}
    roundtrip(s)


def test_blink_resets_once_limit_and_new_entry_discount(cards):
    s = setup(cards)
    c = cast(s, SOURCES[1])
    activate(s, c, {'C': 3}, 0)
    settle(s)
    blink = put(s, 'Flicker of Fate', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[c.id], sources=[])
    settle(s)
    assert not c.counters
    hand = len(s.state.zones['p1:hand'])
    activate(s, c, {'C': 3}, 0)
    settle(s)
    verify_effect(s, c, hand)
    roundtrip(s)


def test_brawn_counts_hand_at_resolution_after_real_response(cards):
    s = setup(cards)
    c = cast(s, SOURCES[1])
    recall = put(s, 'Ancestral Recall', 'hand')
    hand = len(s.state.zones['p1:hand'])
    activate(s, c, {'C': 3}, 0)
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=recall.id, targets=['p1'], sources=[])
    settle(s)
    assert c.counters == {'+1/+1': hand + 2}
    roundtrip(s)


def test_she_hulk_doubles_only_own_creature_counters_after_adding_hers(cards):
    s = setup(cards)
    c = cast(s, SOURCES[2])
    mine = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='counter', card_ids=[mine.id], kind='+1/+1', delta=2)
    act(s, 'p2', type='counter', card_ids=[other.id], kind='+1/+1', delta=3)
    activate(s, c, {'C': 4}, 0)
    settle(s)
    assert c.counters == {'+1/+1': 2} and mine.counters == {'+1/+1': 4} and other.counters == {'+1/+1': 3}
    roundtrip(s)


def test_abomination_adds_counter_then_optionally_fights_native_target(cards):
    s = setup(cards)
    c = cast(s, SOURCES[0])
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate(s, c, {'C': 2, 'R': 1}, 0, [other.id])
    settle(s)
    assert c.counters == {'+1/+1': 1} and c.damage == 2
    assert other.zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name,pool,choice,left', [
    (SOURCES[0], {'C': 1, 'R': 1, 'G': 1}, 'either:2', 0),
    (SOURCES[1], {'C': 2, 'G': 1, 'U': 1}, 'either:1', 1),
    (SOURCES[2], {'C': 3, 'G': 1, 'W': 1}, 'either:2', 1),
])
def test_true_cold_cost_choice_reconstructs_prepared_branch_once(cards, tmp_path, name, pool, choice, left):
    import subprocess
    import sys

    s = setup(cards)
    c = cast(s, name)
    hand = len(s.state.zones['p1:hand'])
    activate(s, c, pool)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'ability_cost'
    assert choice in [o.id for o in d.options]
    saved = tmp_path / 'powerup71.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d and d.resume['step']=='ability_cost'
act(s,'p1',type='choose',decision_id=d.id,option_ids=[sys.argv[4]])
settle(s)
c=s.state.cards[sys.argv[3]]
assert c.counters=={'+1/+1':int(sys.argv[5])}
assert sum(s.state.players['p1'].mana.values())==int(sys.argv[6])
assert s.state.rules.decision is None
GameState.model_validate_json(s.state.model_dump_json())
"""
    expected = 1 if name == SOURCES[0] else hand if name == SOURCES[1] else 2
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), c.id, choice, str(expected), str(left)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cancelling_hybrid_cost_choice_commits_no_payment_or_use(cards):
    s = setup(cards)
    c = cast(s, SOURCES[1])
    hand = len(s.state.zones['p1:hand'])
    activate(s, c, {'C': 2, 'G': 1, 'U': 1})
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'ability_cost'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    assert not c.counters and s.state.players['p1'].mana == {'C': 2, 'G': 1, 'U': 1}
    activate(s, c, {}, 0)
    settle(s)
    verify_effect(s, c, hand)
    assert sum(s.state.players['p1'].mana.values()) == 1
    roundtrip(s)


def test_pending_cost_choice_rejects_source_new_incarnation(cards):
    s = setup(cards)
    c = cast(s, SOURCES[1])
    activate(s, c, {'C': 2, 'G': 1, 'U': 1})
    d = s.state.rules.decision
    assert d and d.resume.get('hybrid_power_up71')
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match='original object'):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['either:0'])
    assert s.state.model_dump_json() == before and not c.counters
    roundtrip(s)


def test_true_cold_pending_cost_choice_rejects_new_source_incarnation(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    c = cast(s, SOURCES[1])
    activate(s, c, {'C': 2, 'G': 1, 'U': 1})
    assert s.state.rules.decision.resume.get('hybrid_power_up71')
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
    saved = tmp_path / 'stale-powerup71.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
before=s.state.model_dump_json()
try:
 act(s,'p1',type='choose',decision_id=d.id,option_ids=['either:0'])
except ActionError as exc:
 assert 'original object' in str(exc)
else:
 raise AssertionError('A new incarnation inherited a stale cost choice')
assert s.state.model_dump_json()==before
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_true_cold_payment_frame_preserves_prepared_flag_and_exact_cost(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    c = cast(s, SOURCES[1])
    land = put(s, 'Forest', 'battlefield')
    hand = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='set_prefs', payment='self')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=c.id, ability=1,
        cost_choices=[{'component': 20, 'cards': ['either:0']}])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'pay_mana' and d.resume['cost'] == '{3}'
    assert d.resume['paid_then']['payload']['ability']['power_up_prepared'] is True
    saved = tmp_path / 'paid-powerup71.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
assert d.resume['paid_then']['payload']['ability']['power_up_prepared'] is True
act(s,'p1',type='activate_ability',card_id=sys.argv[4],ability=0)
assert s.state.rules.decision is None
settle(s)
assert s.state.cards[sys.argv[3]].counters=={'+1/+1':int(sys.argv[5])}
assert s.state.cards[sys.argv[4]].tapped
assert not s.state.players['p1'].mana
GameState.model_validate_json(s.state.model_dump_json())
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), c.id, land.id, str(hand)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', [SOURCES[0], SOURCES[2]])
def test_printed_combat_keywords_after_power_up(cards, name):
    from tests.test_rules_conditional_prevention import attack, damage
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    c = cast(s, name)
    activate(s, c, {'C': 2, 'R': 1} if name == SOURCES[0] else {'C': 4}, 0)
    settle(s)
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2') if name == SOURCES[0] else None
    attack(s, [c], turn=7)
    if blocker is not None:
        to_phase(s, 'declare_blockers')
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': c.id}])
    damage(s)
    if blocker is not None:
        d = s.state.rules.decision
        assert d
        act(s, 'p1', type='choose', decision_id=d.id, amounts=[2, 3])
        settle(s)
        assert blocker.zone == 'p2:graveyard' and s.state.players['p2'].life == 37
    else:
        assert not c.tapped and s.state.players['p2'].life == 35
    roundtrip(s)


@pytest.mark.parametrize('cold', [False, True])
def test_pending_cost_choice_rejects_advanced_turn(cards, tmp_path, cold):
    import subprocess
    import sys

    s = setup(cards)
    c = cast(s, SOURCES[1])
    activate(s, c, {'C': 2, 'G': 1, 'U': 1})
    assert s.state.rules.decision.resume.get('hybrid_power_up71')
    act(s, 'p1', type='next_turn')
    if not cold:
        d = s.state.rules.decision
        before = s.state.model_dump_json()
        with pytest.raises(ActionError, match='no longer applies this turn'):
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=['either:0'])
        assert s.state.model_dump_json() == before and not c.counters
        return
    saved = tmp_path / 'stale-turn-powerup71.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
before=s.state.model_dump_json()
try:
 act(s,'p1',type='choose',decision_id=d.id,option_ids=['either:0'])
except ActionError as exc:
 assert 'no longer applies this turn' in str(exc)
else:
 raise AssertionError('A prior-turn reduction choice was reinterpreted')
assert s.state.model_dump_json()==before
"""
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
