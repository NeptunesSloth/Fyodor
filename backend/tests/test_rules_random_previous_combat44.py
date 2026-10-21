"""Production Hellkite native previous-combat receipts and attack requirements."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_random_consequences import answer
from tests.test_rules_random_native_outcomes42 import DATA
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import stops, three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

NAME = 'Territorial Hellkite'
ROWS = json.loads((Path(__file__).parent / 'fixtures/random_previous_combat44_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate([*DATA, *ROWS]):
        base[row['name']] = card(row['name'], set_code='pc44', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def setup(cards):
    names = [r['name'] for r in [*DATA, *ROWS]] + ['Grizzly Bears', 'Lightning Bolt', 'Forest']
    s = three(cards, names, names, names)
    hold(s)
    stops(s, 'begin_combat', 'declare_attackers', 'declare_blockers')
    return s


def begin_combat(s, turn):
    to_phase(s, 'begin_combat', turn=turn)
    settle(s)


def attack(s, source, player='p2'):
    to_phase(s, 'declare_attackers', turn=s.state.turn.number)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': player}])
    settle(s)


def test_first_fresh_combat_selects_uniform_all_opponents_and_uses_native_haste_flying(cards, monkeypatch):
    from app.game.errors import ActionError

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert pool == ['p2', 'p3']
        return 'p2'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    begin_combat(s, 1)
    to_phase(s, 'declare_attackers', turn=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[])
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p3'}])
    attack(s, source)
    assert sampled == [('p2', 'p3')]
    current = s.state.rules.combat_memory.current
    assert current.players_attacked == {s.state.rules.object_id(source.id): ['p2']}
    roundtrip(s)


def test_previous_own_combat_survives_three_player_rotation_and_excludes_actual_player(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        return pool[0]
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    begin_combat(s, 1)
    attack(s, source, 'p2')
    begin_combat(s, 4)
    assert sampled == [('p2', 'p3'), ('p3',)]
    assert s.state.rules.combat_memory.previous['p1'].turn == 1
    attack(s, source, 'p3')
    roundtrip(s)


@pytest.mark.parametrize('older', ['midgame_enable', 'missing_legacy_field'])
def test_unknown_history_is_per_trigger_manual_without_random_and_next_observed_combat_recovers(cards, monkeypatch, older):
    from app.game.rules_state import start_rules
    from app.game.session import GameSession
    from app.game.state import GameState

    s = setup(cards)
    state = s.state.model_copy(deep=True)
    if older == 'midgame_enable':
        state.rules = None
        start_rules(state)
        assert not state.rules.combat_memory.known_empty
    else:
        data = state.model_dump(mode='json')
        del data['rules']['combat_memory']
        state = GameState.model_validate(data)
        assert state.rules.combat_memory is None
    s = GameSession(state, cards=cards)
    hold(s)
    stops(s, 'begin_combat', 'declare_attackers', 'declare_blockers')
    source = put(s, NAME, 'battlefield')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert pool == ['p3']
        return 'p3'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    begin_combat(s, 1)
    assert not sampled
    decision = s.state.rules.decision
    assert decision.kind == 'manual_resolution'
    assert 'whole trigger by hand' in decision.prompt
    act(s, decision.player, type='choose', decision_id=decision.id, option_ids=['done'])
    settle(s)
    assert not sampled
    assert not s.state.cards[source.id].tapped
    attack(s, source, 'p2')
    begin_combat(s, 4)
    assert sampled == [('p3',)]
    attack(s, source, 'p3')
    roundtrip(s)


def assault(s, source):
    to_phase(s, 'main2', turn=s.state.turn.number)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    settle(s)


def test_extra_combat_uses_immediately_previous_combat_and_empty_combat_replaces_earlier_attack(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    extra = put(s, 'Aggravated Assault', 'battlefield')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        return pool[0]
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    begin_combat(s, 1)
    attack(s, source, 'p2')
    assault(s, extra)
    begin_combat(s, 1)
    assert sampled == [('p2', 'p3'), ('p3',)]
    assert s.state.rules.combat_memory.previous['p1'].combat == 1
    # A genuine response after the random selection makes attacking impossible.
    spell(s, 'Twiddle', {'U': 1}, target=[source.id], player='p2')
    answer(s, ['tap'])
    to_phase(s, 'declare_attackers', turn=1)
    if s.state.rules.decision is not None:
        act(s, 'p1', type='declare_attackers', attackers=[])
    else:
        assert s.state.rules.no_attackers
    assault(s, extra)
    begin_combat(s, 1)
    assert sampled == [('p2', 'p3'), ('p3',), ('p2', 'p3')]
    previous = s.state.rules.combat_memory.previous['p1']
    assert previous.combat == 2 and not previous.players_attacked
    attack(s, source, 'p2')
    roundtrip(s)


def test_skipped_combat_does_not_replace_last_actual_own_combat(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        return pool[0]
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    begin_combat(s, 1)
    attack(s, source, 'p2')
    to_phase(s, 'main1', turn=2)
    spell(s, 'Stonehorn Dignitary', {'C': 3, 'W': 1}, player='p2')
    answer(s, ['p1'])
    to_phase(s, 'main2', turn=4)
    assert s.state.rules.combats == 0
    assert sampled == [('p2', 'p3')]
    begin_combat(s, 7)
    assert sampled == [('p2', 'p3'), ('p3',)]
    assert s.state.rules.combat_memory.previous['p1'].turn == 1
    attack(s, source, 'p3')
    roundtrip(s)


def test_planeswalker_attack_is_not_an_attack_on_its_controller(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    walker = spell(s, 'Jace Beleren', {'C': 1, 'U': 2})
    act(s, 'p1', type='set_controller', card_ids=[walker.id], player='p2')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert pool == ['p2', 'p3']
        return 'p2'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    to_phase(s, 'begin_combat', turn=1)
    trigger = s.state.zones['stack'][-1]
    spell(s, 'Stifle', {'U': 1}, target=[trigger])
    assert not sampled
    attack(s, source, walker.id)
    begin_combat(s, 4)
    assert sampled == [('p2', 'p3')]
    assert not s.state.rules.combat_memory.previous['p1'].players_attacked
    attack(s, source, 'p2')
    roundtrip(s)


def test_kaalia_put_attacking_hellkite_did_not_declare_an_attack_last_combat(cards, monkeypatch):
    s = setup(cards)
    captain = put(s, 'Kaalia of the Vast', 'battlefield')
    source = put(s, NAME, 'hand')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert pool == ['p2', 'p3']
        return 'p2'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': captain.id, 'target': 'p2'}])
    settle(s)
    answer(s, [source.id])
    assert s.state.cards[source.id].attacking is not None
    assert not sampled
    begin_combat(s, 7)
    previous = s.state.rules.combat_memory.previous['p1']
    assert s.state.rules.object_id(source.id) not in previous.players_attacked
    assert sampled == [('p2', 'p3')]
    attack(s, source, 'p2')
    roundtrip(s)


def test_declared_attack_still_counts_after_native_removal_from_combat(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    retreat = put(s, 'Reconnaissance', 'battlefield')
    sampled = []
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda rng, pool: sampled.append(tuple(pool)) or pool[0])
    begin_combat(s, 1)
    attack(s, source, 'p2')
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=retreat.id, ability=0, targets=[source.id], sources=[])
    settle(s)
    assert s.state.cards[source.id].attacking is None
    assert not s.state.cards[source.id].tapped
    begin_combat(s, 4)
    assert sampled == [('p2', 'p3'), ('p3',)]
    attack(s, source, 'p3')
    roundtrip(s)


def test_blinked_source_between_combats_has_no_previous_incarnations_attack(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    sampled = []
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda rng, pool: sampled.append(tuple(pool)) or pool[0])
    begin_combat(s, 1)
    attack(s, source, 'p2')
    old = s.state.rules.object_id(source.id)
    spell(s, 'Cloudshift', {'W': 1}, target=[source.id])
    assert s.state.rules.object_id(source.id) != old
    begin_combat(s, 4)
    assert sampled == [('p2', 'p3'), ('p2', 'p3')]
    attack(s, source, 'p2')
    roundtrip(s)


@pytest.mark.parametrize('response', ['Flicker of Fate', 'Beast Within'])
def test_original_trigger_retains_old_history_but_does_not_restrict_new_or_missing_source(cards, monkeypatch, response):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    sampled = []
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda rng, pool: sampled.append(tuple(pool)) or pool[0])
    begin_combat(s, 1)
    attack(s, source, 'p2')
    to_phase(s, 'begin_combat', turn=4)
    old = s.state.rules.object_id(source.id)
    spell(s, response, {'C': 1, 'W': 1} if response == 'Flicker of Fate' else {'C': 2, 'G': 1}, target=[source.id], player='p2')
    assert s.state.rules.object_id(source.id) != old
    assert sampled == [('p2', 'p3'), ('p3',)]
    assert s.state.cards[source.id].zone == ('p1:battlefield' if response == 'Flicker of Fate' else 'p1:graveyard')
    to_phase(s, 'declare_attackers', turn=4)
    if s.state.rules.decision is not None:
        act(s, 'p1', type='declare_attackers', attackers=[])
    else:
        assert s.state.rules.no_attackers
    roundtrip(s)


def test_copied_trigger_uses_copy_controllers_previous_own_combat(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    sampled = []
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda rng, pool: sampled.append(tuple(pool)) or pool[0])
    begin_combat(s, 1)
    attack(s, source, 'p2')
    to_phase(s, 'begin_combat', turn=4)
    trigger = s.state.zones['stack'][-1]
    spell(s, 'Return the Favor', {'C': 1, 'R': 2}, target=[trigger], player='p2', modes=[0])
    if s.state.rules.decision is not None:
        answer(s, ['keep'])
    settle(s)
    assert sampled == [('p2', 'p3'), ('p1', 'p3'), ('p3',)]
    attack(s, source, 'p3')
    roundtrip(s)


@pytest.mark.parametrize('stage', ['between_combats', 'after_selection', 'legacy_done'])
def test_fresh_process_native_combat_memory_or_frozen_destination_never_resamples(cards, monkeypatch, tmp_path, stage):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    s = setup(cards)
    if stage == 'legacy_done':
        data = s.state.model_dump(mode='json')
        del data['rules']['combat_memory']
        s = GameSession(GameState.model_validate(data), cards=cards)
        hold(s)
        stops(s, 'begin_combat', 'declare_attackers', 'declare_blockers')
    source = put(s, NAME, 'battlefield')
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda rng, pool: pool[0])
    begin_combat(s, 1)
    if stage == 'legacy_done':
        assert s.state.rules.decision.kind == 'manual_resolution'
    else:
        attack(s, source, 'p2')
        if stage == 'between_combats':
            to_phase(s, 'main2', turn=1)
        else:
            begin_combat(s, 4)
    path = tmp_path / (stage + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import secrets,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle
from tests.test_rules_wave30m_durations import to_phase
path,db,stage,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
sampled=[]
def choose(rng,pool):
 assert stage=='between_combats', 'saved destination was resampled'
 assert pool==['p3']
 sampled.append(tuple(pool))
 return 'p3'
secrets.SystemRandom.choice=choose
if stage=='legacy_done':
 d=s.state.rules.decision
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['done']})
 settle(s)
 assert not s.state.cards[cid].tapped
 assert not s.state.rules.combat_memory.known_empty
 assert 'p1' not in s.state.rules.combat_memory.previous
else:
 if stage=='between_combats':
  to_phase(s,'begin_combat',turn=4)
  settle(s)
 to_phase(s,'declare_attackers',turn=4)
 try:
  s.perform('p1',{'type':'declare_attackers','attackers':[{'card_id':cid,'target':'p2'}]})
 except ActionError:pass
 else:raise AssertionError('saved requirement lost')
 s.perform('p1',{'type':'declare_attackers','attackers':[{'card_id':cid,'target':'p3'}]})
 assert s.state.rules.combat_memory.previous['p1'].turn==1
 assert s.state.rules.combat_memory.previous['p1'].players_attacked=={s.state.rules.object_id(cid):['p2']}
assert len(sampled)==int(stage=='between_combats')
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), stage, source.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_control_change_uses_new_ability_controllers_own_previous_combat(cards, monkeypatch):
    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    sampled = []
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda rng, pool: sampled.append(tuple(pool)) or pool[0])
    begin_combat(s, 1)
    attack(s, source, 'p2')
    oid = s.state.rules.object_id(source.id)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    assert s.state.rules.object_id(source.id) == oid
    begin_combat(s, 2)
    assert sampled == [('p2', 'p3'), ('p1', 'p3')]
    assert s.state.rules.combat_memory.previous['p1'].players_attacked == {oid: ['p2']}
    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p1'}])
    roundtrip(s)


@pytest.mark.parametrize('prohibition,destination', [
    ('none', 'walker'), ('prison', 'p3'), ('prison', 'walker'), ('prison', 'none'),
    ('archon', 'p3'), ('archon', 'none'),
])
def test_chosen_player_requirement_keeps_native_tax_and_impossible_destination_exceptions(cards, monkeypatch, prohibition, destination):
    from app.game.errors import ActionError
    from app.rules.mana_units import visible_pool

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    walker = spell(s, 'Jace Beleren', {'C': 1, 'U': 2})
    act(s, 'p1', type='set_controller', card_ids=[walker.id], player='p2')
    if prohibition != 'none':
        put(s, 'Ghostly Prison' if prohibition == 'prison' else 'Blazing Archon', 'battlefield', 'p2')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert pool == ['p2', 'p3']  # Taxed and unattackable opponents remain eligible for the random choice.
        return 'p2'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    begin_combat(s, 1)
    to_phase(s, 'declare_attackers', turn=1)
    selected = walker.id if destination == 'walker' else destination
    declaration = [] if destination == 'none' else [{'card_id': source.id, 'target': selected}]
    if prohibition == 'none':
        with pytest.raises(ActionError):
            act(s, 'p1', type='declare_attackers', attackers=declaration)
        declaration = [{'card_id': source.id, 'target': 'p2'}]
    act(s, 'p1', type='declare_attackers', attackers=declaration)
    assert sampled == [('p2', 'p3')]
    assert visible_pool(s.state, 'p1') == {}
    roundtrip(s)


@pytest.mark.parametrize('attack_chosen', [False, True])
def test_global_attack_cost_allows_declining_attack_but_cannot_pay_for_wrong_destination(cards, monkeypatch, attack_chosen):
    from app.game.errors import ActionError
    from app.rules.mana_units import visible_pool

    s = setup(cards)
    source = put(s, NAME, 'battlefield')
    tax = put(s, 'War Tax', 'battlefield', 'p2')
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda rng, pool: 'p2')
    begin_combat(s, 1)
    priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2, 'U': 1})
    act(s, 'p2', type='activate_ability', card_id=tax.id, ability=0, x_value=2, sources=[])
    settle(s)
    priority(s, 'p1')
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    # Official Hellkite ruling: a cost to attack at all permits only the chosen
    # player or declining to attack; it does not permit paying to attack elsewhere.
    if attack_chosen:
        with pytest.raises(ActionError):
            act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p3'}])
        assert visible_pool(s.state, 'p1') == {'C': 2}
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}], sources=[])
        assert visible_pool(s.state, 'p1') == {}
    else:
        act(s, 'p1', type='declare_attackers', attackers=[])
        assert visible_pool(s.state, 'p1') == {'C': 2}
    roundtrip(s)


def test_sole_previous_opponent_is_not_selectable_and_native_tap_replaces_random_choice(cards, monkeypatch):
    s = setup(cards)
    act(s, 'p3', type='concede')
    source = put(s, NAME, 'battlefield')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert pool == ['p2']
        return 'p2'
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    begin_combat(s, 1)
    attack(s, source, 'p2')
    begin_combat(s, 4)
    assert sampled == [('p2',)]
    assert s.state.cards[source.id].tapped
    roundtrip(s)


def test_whole_printed_canonical_gate(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve(NAME))
    assert result.level == 'FULL', result
