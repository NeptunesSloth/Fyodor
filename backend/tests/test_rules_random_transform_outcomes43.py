"""Production whole-card native proofs for both transforming faces."""
import pytest

from tests.game_helpers import act
from tests.test_rules_characteristic_recipes39 import ch
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_random_native_outcomes42 import cards as cards
from tests.test_rules_random_native_outcomes42 import setup
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import stops, to_phase

NAME = 'Path of Mettle // Metzali, Tower of Triumph'


def test_actual_front_entry_excludes_each_of_the_four_keywords(cards):
    s = setup(cards)
    protected = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator', 'Questing Beast']]
    bear = put(s, 'Grizzly Bears', 'battlefield')
    source = spell(s, NAME, {'R': 1, 'W': 1})
    assert s.state.cards[bear.id].damage == 1
    assert all(not s.state.cards[c.id].damage for c in protected)
    assert source.face == 0
    roundtrip(s)


@pytest.mark.parametrize('count', [1, 2])
def test_actual_attack_counts_creatures_once_and_transforms_at_two(cards, count):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    attackers = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator']][:count]
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in attackers])
    settle(s)
    assert s.state.cards[source.id].face == int(count == 2)
    if count == 2:
        assert ch(s, source).name == 'Metzali, Tower of Triumph'
        priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, sources=[])
        settle(s)
        assert s.state.players['p2'].life == s.state.players['p3'].life == 38
    roundtrip(s)


@pytest.mark.parametrize('selected_name', ['Fervent Champion', 'Swiftblade Vindicator', 'Darksteel Myr', 'Slippery Bogle'])
def test_random_destroy_samples_all_declared_attackers_without_targeting(cards, monkeypatch, selected_name):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    attackers = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator', 'Darksteel Myr', 'Slippery Bogle']]
    nonattacker = put(s, 'Grizzly Bears', 'battlefield')
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in attackers])
    settle(s)
    assert s.state.cards[source.id].face == 1
    sampled = []
    selected = next(c for c in attackers if c.name == selected_name)
    if selected_name == 'Slippery Bogle':
        act(s, 'p1', type='set_controller', card_ids=[selected.id], player='p2')
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert set(pool) == {c.id for c in attackers}
        assert nonattacker.id not in pool
        return selected.id
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, sources=[])
    settle(s)
    assert len(sampled) == 1
    assert s.state.cards[selected.id].zone == ('p1:battlefield' if selected_name == 'Darksteel Myr' else 'p1:graveyard')
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('color', list('WUBRG'))
def test_actual_transformed_land_produces_each_color_immediately(cards, color):
    from app.rules.mana_units import visible_pool

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    attackers = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator']]
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in attackers])
    settle(s)
    assert s.state.cards[source.id].face == 1
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, mana_choice=color)
    assert visible_pool(s.state, 'p1').get(color) == 1
    assert s.state.cards[source.id].tapped
    assert not s.state.zones.get('stack')
    roundtrip(s)


@pytest.mark.parametrize('choice,zone', [('yes', 'command'), ('no', 'graveyard')])
def test_saved_random_commander_destroy_finishes_without_runtime_sampler(cards, monkeypatch, tmp_path, choice, zone):
    import subprocess
    import sys
    from pathlib import Path

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    commander = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.commander_key)
    act(s, 'p1', type='move', card_ids=[commander.id], to={'player': 'p1', 'zone': 'battlefield'})
    attackers = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator']]
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in [commander, *attackers]])
    settle(s)
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert commander.id in pool
        return commander.id
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, sources=[])
    settle(s)
    assert len(sampled) == 1
    assert s.state.rules.decision.resume['step'] == 'commander_zone'
    path = tmp_path / 'metzali.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import secrets,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,db,choice,zone,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
secrets.SystemRandom.choice=lambda *a: (_ for _ in ()).throw(AssertionError('Metzali resampled'))
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[choice]})
for _ in range(30):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[cid].zone=='p1:'+zone
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), choice, zone, commander.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_random_pool_excludes_blinked_attackers_and_expires_on_next_turn(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    first, second = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator']]
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in [first, second]])
    settle(s)
    spell(s, 'Cloudshift', {'W': 1}, target=[first.id])
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert pool == [second.id]
        return second.id
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, sources=[])
    settle(s)
    assert len(sampled) == 1
    assert s.state.cards[first.id].zone == 'p1:battlefield'
    assert s.state.cards[second.id].zone == 'p1:graveyard'
    to_phase(s, 'main1', turn=7)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, sources=[])
    settle(s)
    assert len(sampled) == 1  # Empty current-turn pool does not sample or ask a target.
    assert s.state.rules.decision is None
    roundtrip(s)


def test_two_attackers_require_two_qualifying_creatures_not_two_keywords(cards):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    attackers = [put(s, n, 'battlefield') for n in ['Swiftblade Vindicator', 'Grizzly Bears']]
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in attackers])
    settle(s)
    assert s.state.cards[source.id].face == 0
    roundtrip(s)


def test_old_transform_trigger_does_not_transform_returned_new_source(cards):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    attackers = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator']]
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in attackers])
    decision = s.state.rules.decision
    if decision is not None and decision.kind == 'order':
        act(s, decision.player, type='choose', decision_id=decision.id, option_ids=[o.id for o in decision.options])
    assert s.state.zones.get('stack')
    spell(s, 'Flicker of Fate', {'C': 1, 'W': 1}, target=[source.id])
    settle(s)
    assert s.state.cards[source.id].face == 0
    roundtrip(s)


def test_random_destroy_can_select_opponent_declared_attacker_on_their_turn(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    attackers = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator']]
    opponent = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in attackers])
    settle(s)
    to_phase(s, 'declare_attackers', turn=5)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': opponent.id, 'target': 'p1'}])
    settle(s)
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert pool == [opponent.id]
        return opponent.id
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, sources=[])
    settle(s)
    assert len(sampled) == 1
    assert s.state.cards[opponent.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_native_ability_copy_samples_each_current_pool_independently(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    engine = put(s, 'Lithoform Engine', 'battlefield')
    attackers = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator']]
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in attackers])
    settle(s)
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        return pool[0]
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4, 'W': 1})
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, sources=[])
    target = s.state.zones['stack'][-1]
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=0, targets=[target], sources=[])
    settle(s)
    if s.state.rules.decision is not None:
        answer(s, ['keep'])
        settle(s)
    assert list(map(len, sampled)) == [2, 1]
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in attackers)
    roundtrip(s)


@pytest.mark.parametrize('case', ['planeswalker', 'put_attacking'])
def test_actual_attack_receipts_include_walker_attackers_but_exclude_put_attacking_tokens(cards, monkeypatch, case):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    first = put(s, 'Fervent Champion', 'battlefield')
    second = put(s, 'Adeline, Resplendent Cathar' if case == 'put_attacking' else 'Swiftblade Vindicator', 'battlefield')
    defender = 'p2'
    if case == 'planeswalker':
        defender = spell(s, 'Jace Beleren', {'C': 1, 'U': 2}).id
        act(s, 'p1', type='set_controller', card_ids=[defender], player='p2')
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': first.id, 'target': defender},
                                                     {'card_id': second.id, 'target': 'p3'}])
    from tests.test_rules_wave30m_durations import settle as settle_choices
    settle_choices(s)
    assert s.state.cards[source.id].face == 1
    if case == 'put_attacking':
        assert any(c.is_token and c.attacking for c in s.state.cards.values())
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert set(pool) == {first.id, second.id}
        return first.id
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, sources=[])
    settle(s)
    assert len(sampled) == 1
    assert s.state.cards[first.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_departed_land_source_does_not_stop_original_random_destroy(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    attackers = [put(s, n, 'battlefield') for n in ['Fervent Champion', 'Swiftblade Vindicator']]
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in attackers])
    settle(s)
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert set(pool) == {c.id for c in attackers}
        return attackers[0].id
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, sources=[])
    spell(s, 'Beast Within', {'C': 2, 'G': 1}, target=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert len(sampled) == 1
    assert s.state.cards[attackers[0].id].zone == 'p1:graveyard'
    roundtrip(s)


def test_both_printed_faces_canonical_gate(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve(NAME))
    assert result.level == 'FULL', result
