"""Production actual draws, optional players and native random-target triggers."""
import pytest

from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_random_consequences import answer
from tests.test_rules_random_native_outcomes42 import cards as cards
from tests.test_rules_random_native_outcomes42 import setup
from tests.test_rules_source_quality_protection import spell


@pytest.mark.parametrize('accepts', [[], ['p2'], ['p2', 'p3']])
def test_each_actual_draw_creates_independent_native_random_target_trigger(cards, monkeypatch, accepts):
    s = setup(cards)
    before = {p: len(s.state.zones.get(p + ':hand', [])) for p in s.state.players}
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert set(pool) == {'p2', 'p3'}
        return 'p2'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    source = spell(s, 'Explosion of Riches', {'C': 5, 'R': 1})
    for _ in range(12):
        decision = s.state.rules.decision
        if decision is None:
            break
        if decision.kind == 'order':
            act(s, decision.player, type='choose', decision_id=decision.id, option_ids=[o.id for o in decision.options])
        else:
            assert decision.player in {'p2', 'p3'}
            answer(s, ['yes' if decision.player in accepts else 'no'])
        settle(s)
    settle(s)
    assert s.state.rules.decision is None
    assert len(sampled) == 1 + len(accepts)
    assert s.state.players['p2'].life == 40 - 5 * (1 + len(accepts))
    assert s.state.players['p3'].life == 40
    assert len(s.state.zones['p1:hand']) == before['p1'] + 1  # Fixture finds the spell outside hand; the actual draw adds one.
    for p in ['p2', 'p3']:
        assert len(s.state.zones[p + ':hand']) == before[p] + int(p in accepts)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('replacement', ['Notion Thief', 'Spirit of the Labyrinth'])
def test_completed_actual_draws_honor_redirected_or_prevented_native_draws(cards, monkeypatch, replacement):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    to_phase(s, 'main1', turn=4)
    put(s, replacement, 'battlefield', 'p2')
    before = len(s.state.zones['p2:hand'])
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        return 'p3'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    spell(s, 'Explosion of Riches', {'C': 5, 'R': 1})
    for _ in range(12):
        decision = s.state.rules.decision
        if decision is None:
            break
        if decision.kind == 'order':
            act(s, decision.player, type='choose', decision_id=decision.id, option_ids=[o.id for o in decision.options])
        else:
            answer(s, ['yes' if replacement == 'Notion Thief' else 'no'])
        settle(s)
    settle(s)
    count = 3 if replacement == 'Notion Thief' else 0
    assert len(sampled) == count
    assert s.state.players['p3'].life == 40 - 5 * count
    if replacement == 'Notion Thief':
        assert len(s.state.zones['p2:hand']) == before + 3
    roundtrip(s)


@pytest.mark.parametrize('protected', [['p2'], ['p2', 'p3']])
def test_random_reflexive_targets_only_actual_legal_opponents_after_draws(cards, monkeypatch, protected):
    s = setup(cards)
    for player in protected:
        put(s, 'Leyline of Sanctity', 'battlefield', player)
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert pool == ['p3']
        return 'p3'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    spell(s, 'Explosion of Riches', {'C': 5, 'R': 1})
    for _ in range(12):
        decision = s.state.rules.decision
        if decision is None:
            break
        if decision.kind == 'order':
            act(s, decision.player, type='choose', decision_id=decision.id, option_ids=[o.id for o in decision.options])
        else:
            answer(s, ['yes'])
        settle(s)
    settle(s)
    count = 3 if len(protected) == 1 else 0
    assert len(sampled) == count
    assert s.state.players['p2'].life == 40
    assert s.state.players['p3'].life == 40 - 5 * count
    assert s.state.rules.decision is None
    roundtrip(s)


def test_actual_copy_uses_copy_controller_opponents_and_own_draw_receipt(cards, monkeypatch):
    s = setup(cards)
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert set(pool) in ({'p1', 'p3'}, {'p2', 'p3'})
        return 'p3'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    source = spell(s, 'Explosion of Riches', {'C': 5, 'R': 1}, finish=False)
    spell(s, 'Twincast', {'U': 2}, target=[source.id], player='p2')
    for _ in range(16):
        decision = s.state.rules.decision
        if decision is None:
            settle(s)
            decision = s.state.rules.decision
            if decision is None:
                break
        if decision.kind == 'order':
            act(s, decision.player, type='choose', decision_id=decision.id, option_ids=[o.id for o in decision.options])
        elif any(o.id == 'keep' for o in decision.options):
            answer(s, ['keep'])
        else:
            answer(s, ['no'])
        settle(s)
    assert len(sampled) == 2
    assert set(sampled) == {('p1', 'p3'), ('p2', 'p3')}
    assert s.state.players['p3'].life == 30
    roundtrip(s)


def test_native_draw_doubling_creates_two_reflexives_for_one_draw_instruction(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Thought Reflection', 'battlefield')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        return 'p2'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    spell(s, 'Explosion of Riches', {'C': 5, 'R': 1})
    for _ in range(12):
        decision = s.state.rules.decision
        if decision is None:
            break
        if decision.kind == 'order':
            act(s, decision.player, type='choose', decision_id=decision.id, option_ids=[o.id for o in decision.options])
        else:
            answer(s, ['no'])
        settle(s)
    assert len(sampled) == 2
    assert s.state.players['p2'].life == 30
    roundtrip(s)


@pytest.mark.parametrize('response', ['Stifle', 'Blossoming Calm'])
def test_announced_native_random_trigger_is_counterable_and_rechecks_its_target(cards, monkeypatch, response):
    s = setup(cards)
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        return 'p2'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    spell(s, 'Explosion of Riches', {'C': 5, 'R': 1})
    for _ in range(2):
        decision = s.state.rules.decision
        assert decision is not None
        act(s, decision.player, type='choose', decision_id=decision.id, option_ids=['no'])
    assert len(sampled) == 1
    target = s.state.zones['stack'][-1]
    if response == 'Stifle':
        spell(s, response, {'U': 1}, target=[target])
        assert s.state.players['p2'].life == 40
    else:
        spell(s, response, {'W': 1}, player='p2')
        assert s.state.players['p2'].life == 42
    settle(s)
    assert len(sampled) == 1
    roundtrip(s)


@pytest.mark.parametrize('pause', ['optional_draw', 'announced_target'])
def test_fresh_process_optional_draw_or_announced_target_receipt(cards, monkeypatch, tmp_path, pause):
    import subprocess
    import sys
    from pathlib import Path

    s = setup(cards)
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        return 'p2'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    spell(s, 'Explosion of Riches', {'C': 5, 'R': 1})
    decision = s.state.rules.decision
    assert decision.player == 'p2'
    act(s, decision.player, type='choose', decision_id=decision.id,
        option_ids=['yes' if pause == 'optional_draw' else 'no'])
    decision = s.state.rules.decision
    assert decision.player == 'p3'
    assert not sampled
    if pause == 'announced_target':
        act(s, decision.player, type='choose', decision_id=decision.id, option_ids=['no'])
        assert len(sampled) == 1
        assert s.state.zones.get('stack')
    path = tmp_path / (pause + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import secrets,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,db,pause=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
sampled=[]
def choose(rng,pool):
 assert pause=='optional_draw', 'announced target was resampled'
 assert set(pool)=={'p2','p3'}
 sampled.append(tuple(pool))
 return 'p2'
secrets.SystemRandom.choice=choose
if pause=='optional_draw':
 d=s.state.rules.decision
 assert d.player=='p3'
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['no']})
for _ in range(40):
 d=s.state.rules.decision
 if d is not None:
  assert d.kind=='order'
  s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[o.id for o in d.options]})
 elif s.state.zones.get('stack'):
  s.perform(s.state.rules.priority,{'type':'pass_priority'})
 else:break
assert len(sampled)==(2 if pause=='optional_draw' else 0)
assert s.state.players['p2'].life==(30 if pause=='optional_draw' else 35)
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), pause],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_whole_printed_canonical_gate(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve('Explosion of Riches'))
    assert result.level == 'FULL', result
