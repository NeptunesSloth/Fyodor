"""Whole printed production Saga creature and random chapter announcement proofs."""
import pytest

from tests.test_rules_designations import put, roundtrip
from tests.test_rules_random_consequences import answer
from tests.test_rules_random_native_outcomes42 import cards as cards
from tests.test_rules_random_native_outcomes42 import setup
from tests.test_rules_source_quality_protection import spell


def choose_mode(monkeypatch, mode):
    sampled = []
    def pick(rng, allowed):
        sampled.append(tuple(allowed))
        assert mode in allowed
        return mode
    monkeypatch.setattr('secrets.SystemRandom.choice', pick)
    return sampled


@pytest.mark.parametrize('mode', [0, 1, 2])
def test_actual_cast_chapter_random_mode_announced_before_targets_and_native_consequence(cards, monkeypatch, mode):
    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    sampled = choose_mode(monkeypatch, mode)
    source = spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    assert sampled == [(0, 1, 2)]
    assert s.state.cards[source.id].counters['lore'] == 1
    assert s.state.rules.decision is not None
    answer(s, [enemy.id if mode == 2 else own.id])
    if mode == 0:
        assert s.state.cards[own.id].counters['+1/+1'] == 3
    elif mode == 1:
        assert s.state.cards[own.id].counters['shield'] == 1
        assert s.state.players['p1'].life == 43
    else:
        assert s.state.cards[enemy.id].zone == 'p2:graveyard'
        assert s.state.cards[source.id].damage == 2
    assert sampled == [(0, 1, 2)]
    roundtrip(s)


def test_native_fight_mode_remains_legal_with_zero_opponent_creatures_and_can_choose_none(cards, monkeypatch):
    s = setup(cards)
    sampled = choose_mode(monkeypatch, 2)
    source = spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    if s.state.rules.decision is not None:
        answer(s, [])
    assert sampled == [(0, 1, 2)]
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not s.state.cards[source.id].damage
    roundtrip(s)


def test_native_shield_prevents_damage_and_is_consumed_before_later_lethal_damage(cards, monkeypatch):
    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    choose_mode(monkeypatch, 1)
    spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    answer(s, [own.id])
    spell(s, 'Lightning Bolt', {'R': 1}, target=[own.id])
    assert s.state.cards[own.id].zone == 'p1:battlefield'
    assert not s.state.cards[own.id].counters.get('shield')
    assert not s.state.cards[own.id].damage
    spell(s, 'Lightning Bolt', {'R': 1}, target=[own.id])
    assert s.state.cards[own.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_actual_natural_chapter_two_and_three_then_sacrifice_after_final_resolves(cards, monkeypatch):
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    sampled = choose_mode(monkeypatch, 0)
    source = spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    answer(s, [own.id])
    for turn, chapter_n in [(4, 2), (7, 3)]:
        to_phase(s, 'main1', turn=turn)
        assert s.state.cards[source.id].counters['lore'] == chapter_n
        # The next native turn-based lore action announces a random chapter.
        if s.state.rules.decision is not None:
            answer(s, [own.id])
        else:
            from tests.test_rules_designations import settle
            settle(s)
            if s.state.rules.decision is not None:
                answer(s, [own.id])
        assert s.state.cards[source.id].zone == ('p1:battlefield' if chapter_n == 2 else 'p1:graveyard')
    assert len(sampled) == 3
    assert s.state.cards[own.id].counters['+1/+1'] == 9
    roundtrip(s)


@pytest.mark.parametrize('mode', [0, 2])
def test_saved_random_mode_and_pending_target_announcement_resume_cold_without_resampling(cards, monkeypatch, tmp_path, mode):
    import subprocess
    import sys
    from pathlib import Path
    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    sampled = choose_mode(monkeypatch, mode)
    source = spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    assert sampled == [(0, 1, 2)]
    assert s.state.rules.decision is not None
    path = tmp_path / f'mode{mode}.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import secrets,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,db,mode,own,enemy,source=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
secrets.SystemRandom.choice=lambda *a: (_ for _ in ()).throw(AssertionError('mode sampled twice'))
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[own if mode=='0' else enemy]})
for _ in range(50):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
if mode=='0':assert s.state.cards[own].counters['+1/+1']==3
else:
 assert s.state.cards[enemy].zone=='p2:graveyard'
 assert s.state.cards[source].damage==2
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), str(mode), own.id, enemy.id, source.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_actual_lithoform_copy_inherits_chosen_mode_and_targets_without_resampling(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    engine = put(s, 'Lithoform Engine', 'battlefield')
    own = put(s, 'Grizzly Bears', 'battlefield')
    sampled = choose_mode(monkeypatch, 0)
    spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[own.id])
    target = s.state.zones['stack'][-1]
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=0, targets=[target], sources=[])
    settle(s)
    if s.state.rules.decision is not None:
        answer(s, ['keep'])
    assert s.state.cards[own.id].counters['+1/+1'] == 6
    assert sampled == [(0, 1, 2)]
    roundtrip(s)


@pytest.mark.parametrize('mode', [0, 1])
def test_original_target_blinked_after_native_announcement_fizzles_entire_mode(cards, monkeypatch, mode):
    from tests.game_helpers import act
    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    choose_mode(monkeypatch, mode)
    spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[own.id])
    spell(s, 'Cloudshift', {'W': 1}, target=[own.id])
    assert not s.state.cards[own.id].counters
    assert s.state.players['p1'].life == 40
    roundtrip(s)


def test_old_chapter_fight_never_uses_new_saga_object_after_native_blink(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.game_helpers import act
    s = setup(cards)
    own = put(s, 'Grizzly Bears', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    modes = iter([2, 0])
    sampled = []
    def choose(rng, allowed):
        sampled.append(tuple(allowed))
        return next(modes)
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    source = spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    old = Plan(s.state, 'p1', cards, None).oid(s.state.cards[source.id])
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[enemy.id])
    spell(s, 'Cloudshift', {'W': 1}, target=[source.id])
    answer(s, [own.id])
    assert Plan(s.state, 'p1', cards, None).oid(s.state.cards[source.id]) != old
    assert s.state.cards[enemy.id].zone == 'p2:battlefield' and not s.state.cards[enemy.id].damage
    assert not s.state.cards[source.id].damage
    assert s.state.cards[own.id].counters['+1/+1'] == 3
    assert len(sampled) == 2
    roundtrip(s)


def test_printed_haste_allows_actual_attack_on_the_cast_turn(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    choose_mode(monkeypatch, 2)
    source = spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    if s.state.rules.decision is not None:
        answer(s, [])
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    assert s.state.cards[source.id].is_attacking
    roundtrip(s)


def test_native_doubled_entry_lore_announces_both_crossed_chapters_and_native_counter_replacement(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    s = setup(cards)
    put(s, 'Doubling Season', 'battlefield')
    own = put(s, 'Grizzly Bears', 'battlefield')
    sampled = choose_mode(monkeypatch, 0)
    source = spell(s, 'Summon: Magus Sisters', {'C': 4, 'G': 1})
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options]
        chosen = [own.id] if own.id in ids else ids[:max(1, d.min_choices)]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=chosen)
        settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].counters['lore'] == 2
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert len(sampled) == 2
    assert s.state.cards[own.id].counters['+1/+1'] == 12
    roundtrip(s)


def test_magus_sisters_whole_printed_canonical_gate(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('Summon: Magus Sisters')).level == 'FULL'
