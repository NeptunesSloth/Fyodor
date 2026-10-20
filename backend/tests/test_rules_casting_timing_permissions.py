"""Conditional timing and next matching spell permissions retain native casting rules."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold


@pytest.fixture()
def cards(settings):
    data = json.loads((Path(__file__).parent / 'fixtures/casting_timing_permissions_cards.json').read_text())
    extra = [card(c['name'], set_code='vma', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')}) for i, c in enumerate(data)]
    settings.ensure_dirs()
    build_database([*fixture_cards(), *extra], settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()






FIRST = ['Quicken', "Scout's Warning", 'Ride the Avalanche', 'Rootwater Shaman', 'Dragon Grip', 'Swift Reckoning', 'Serpent of the Pass']


def setup(cards):
    names = [c['name'] for c in json.loads((Path(__file__).parent / 'fixtures/casting_timing_permissions_cards.json').read_text())]
    names += ['Grizzly Bears', 'Lightning Bolt', 'Rampant Growth', 'Pacifism', 'Giant Growth']
    s = three(cards, names, names, names)
    hold(s)
    return s


def opponent_turn(s):
    from tests.test_rules_wave30m_durations import stops, to_phase
    stops(s, 'main1')
    to_phase(s, 'main1', turn=2)


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


@pytest.mark.parametrize('name', FIRST)
def test_initial_timing_family_canonical_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


@pytest.mark.parametrize('permission', ['Quicken', "Scout's Warning"])
def test_next_matching_permission_casts_on_opponents_turn_once(cards, permission):
    from app.game.errors import ActionError
    s = setup(cards)
    opponent_turn(s)
    spell(s, permission, {'U': 1} if permission == 'Quicken' else {'W': 1})
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'])
    selected = put(s, 'Rampant Growth' if permission == 'Quicken' else 'Grizzly Bears', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=selected.id, sources=[])
    settle(s)
    if permission == 'Quicken':
        choose(s, [next(o.id for o in s.state.rules.decision.options if o.label == 'Forest')])
        assert any(c.zone == 'p1:battlefield' and c.name == 'Forest' and c.tapped for c in s.state.cards.values())
    else:
        assert s.state.cards[selected.id].zone == 'p1:battlefield'
    act(s, 'p1', type='move', card_ids=[selected.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=selected.id, sources=[])
    roundtrip(s)


def test_rootwater_exact_enchant_creature_aura_quality(cards):
    from app.game.errors import ActionError
    s = setup(cards)
    put(s, 'Rootwater Shaman', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    forest = put(s, 'Forest', 'battlefield')
    opponent_turn(s)
    source = spell(s, 'Pacifism', {'W': 1, 'C': 1}, [bear.id])
    assert s.state.cards[source.id].attached_to == bear.id
    other = put(s, 'Utopia Sprawl', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=other.id, targets=[forest.id], sources=[])
    roundtrip(s)


def test_dragon_grip_actual_ferocious_timing(cards):
    from app.game.errors import ActionError
    from app.rules.plan import Plan
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    opponent_turn(s)
    grip = put(s, 'Dragon Grip', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 2})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=grip.id, targets=[bear.id], sources=[])
    spell(s, 'Giant Growth', {'G': 1}, [bear.id])
    priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=grip.id, targets=[bear.id], sources=[])
    settle(s)
    assert s.state.cards[grip.id].attached_to == bear.id
    assert 'first strike' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).keywords
    roundtrip(s)


@pytest.mark.parametrize('other_count', [1, 2])
def test_swift_graveyard_flashback_requires_two_other_spell_cards(cards, other_count):
    from app.game.errors import ActionError
    s = setup(cards)
    swift = put(s, 'Swift Reckoning', 'graveyard')
    put(s, 'Lightning Bolt', 'graveyard')
    if other_count == 2:
        put(s, 'Rampant Growth', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    opponent_turn(s)
    act(s, 'p2', type='tap', card_ids=[bear.id], tapped=True)
    spell(s, 'Snapcaster Mage', {'U': 1, 'C': 1})
    choose(s, [swift.id])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 1})
    if other_count == 1:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=swift.id, targets=[bear.id], sources=[])
        assert s.state.cards[swift.id].zone == 'p1:graveyard'
    else:
        act(s, 'p1', type='cast_spell', card_id=swift.id, targets=[bear.id], sources=[])
        settle(s)
        assert s.state.cards[bear.id].zone == 'p2:graveyard'
        assert s.state.cards[swift.id].zone == 'p1:exile'
    roundtrip(s)


def test_serpent_lesson_timing_and_independent_discount(cards):
    s = setup(cards)
    for name in ('Environmental Sciences', 'Introduction to Annihilation', 'Expanded Anatomy'):
        put(s, name, 'graveyard')
    opponent_turn(s)
    source = spell(s, 'Serpent of the Pass', {'U': 2, 'C': 2})
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_ride_delayed_counter_trigger_uses_actual_next_spell_mv(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    opponent_turn(s)
    spell(s, 'Ride the Avalanche', {'U': 1, 'G': 1})
    source = spell(s, 'Rootwater Shaman', {'U': 1, 'C': 2})
    choose(s, [bear.id])
    assert s.state.cards[bear.id].counters.get('+1/+1') == 3
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


MORE = ['Savage Summoning', "Arlinn, the Pack's Hope // Arlinn, the Moon's Fury", 'Cherished Hatchling',
        'Fated Clash', 'Primal Prayers', "Tegwyll's Scouring", 'Molten Exhale', 'Quantum Reduction']


@pytest.mark.parametrize('name', MORE)
def test_remaining_timing_family_canonical_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_savage_multiple_rules_bind_same_creature_and_do_not_copy_to_spell_copy(cards):
    s = setup(cards)
    spell(s, 'Savage Summoning', {'G': 1})
    spell(s, 'Savage Summoning', {'G': 1})
    opponent_turn(s)
    # Waiting rules end in cleanup: establish both again during this turn.
    spell(s, 'Savage Summoning', {'G': 1})
    spell(s, 'Savage Summoning', {'G': 1})
    bear = put(s, 'Grizzly Bears', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    priority(s, 'p2')
    counter = put(s, 'Counterspell', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 2})
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[bear.id])
    priority(s, 'p1')
    major = put(s, 'Double Major', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=major.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].counters.get('+1/+1') == 2
    copies = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
    assert len(copies) == 1 and not copies[0].counters.get('+1/+1')
    roundtrip(s)


def test_arlinn_next_turn_permission_and_entry_counters_include_tokens(cards):
    from tests.test_rules_wave7b_activation import ability_index
    from tests.test_rules_wave30m_durations import stops, to_phase
    s = setup(cards)
    arlinn = spell(s, "Arlinn, the Pack's Hope // Arlinn, the Moon's Fury", {'R': 1, 'G': 1, 'C': 2})
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=arlinn.id, ability=ability_index(s, arlinn, 'Until your next turn'))
    settle(s)
    opponent_turn(s)
    bear = spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    spell(s, 'Raise the Alarm', {'W': 1, 'C': 1})
    assert s.state.cards[bear.id].counters.get('+1/+1') == 1
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
    assert len(tokens) == 2 and all(c.counters.get('+1/+1') == 1 for c in tokens)
    stops(s, 'main1')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'hand'})
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    settle(s)
    assert not s.state.cards[bear.id].counters.get('+1/+1')
    roundtrip(s)


def test_cherished_hatchling_multiple_dinosaurs_gain_actual_optional_etb_fight(cards):
    s = setup(cards)
    hatch = put(s, 'Cherished Hatchling', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    opponent_turn(s)
    spell(s, 'Lightning Bolt', {'R': 1}, [hatch.id])
    source = spell(s, 'Colossal Dreadmaw', {'G': 2, 'C': 4})
    d = s.state.rules.decision
    assert d is not None
    choose(s, [victim.id])
    if s.state.rules.decision is not None:
        choose(s, ['yes'])
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[victim.id].zone == 'p2:graveyard'
    second = spell(s, 'Raptor Companion', {'W': 1, 'C': 1})
    assert s.state.rules.decision is not None
    choose(s, [source.id])
    if s.state.rules.decision is not None:
        choose(s, ['no'])
    assert s.state.cards[second.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_primal_prayers_alternative_pays_energy_and_normal_mana_has_no_flash(cards):
    from app.game.errors import ActionError
    from app.rules.casting import alt_castable
    s = setup(cards)
    spell(s, 'Primal Prayers', {'G': 2, 'C': 2})
    assert s.state.players['p1'].resources.get('energy') == 2
    opponent_turn(s)
    bear = put(s, 'Grizzly Bears', 'hand')
    priority(s, 'p1')
    offers = alt_castable(s.state, 'p1', bear, cards)
    assert len(offers) == 1
    priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bear.id, alt_cost=offers[0]['id'], sources=[])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].resources.get('energy') == 1
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id, sources=[])
    act(s, 'p1', type='move', card_ids=[bear.id], to={'player': 'p1', 'zone': 'graveyard'})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id, alt_cost=offers[0]['id'], sources=[])
    roundtrip(s)


def test_tegwyl_flash_additional_cost_really_taps_three_flyers(cards):
    from app.game.errors import ActionError
    s = setup(cards)
    opponent_turn(s)
    flyers = [put(s, name, 'battlefield') for name in ('Ornithopter', 'Suntail Hawk', 'Storm Crow')]
    source = put(s, "Tegwyll's Scouring", 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 4})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, sources=[], optional_costs=[source.id + ':flash_tap'],
            cost_choices=[{'component': 0, 'cards': [c.id for c in flyers[:2]]}])
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[], optional_costs=[source.id + ':flash_tap'],
        cost_choices=[{'component': 0, 'cards': [c.id for c in flyers]}])
    assert all(s.state.cards[c.id].tapped for c in flyers)
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in flyers)
    assert sum(c.is_token and c.zone == 'p1:battlefield' and c.name == 'Faerie Rogue' for c in s.state.cards.values()) == 3
    roundtrip(s)


@pytest.mark.parametrize('where', ['battlefield', 'hand'])
def test_molten_exhale_flash_really_beholds_a_dragon(cards, where):
    from app.game.errors import ActionError
    s = setup(cards)
    opponent_turn(s)
    dragon = put(s, 'Shivan Dragon', where)
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = put(s, 'Molten Exhale', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[victim.id], sources=[])
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[victim.id], sources=[],
        optional_costs=[source.id + ':behold'], cost_choices=[{'component': 0, 'cards': [dragon.id]}])
    assert s.state.cards[dragon.id].zone == 'p1:' + where
    if where == 'hand':
        assert dragon.id in str(s.view('p2'))
    settle(s)
    assert s.state.cards[victim.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_quantum_reduction_flash_requires_actual_teamwork_payment(cards):
    from app.game.errors import ActionError
    from app.rules.plan import Plan
    s = setup(cards)
    opponent_turn(s)
    helper = put(s, 'Grizzly Bears', 'battlefield')
    victim = put(s, 'Shivan Dragon', 'battlefield', 'p2')
    source = put(s, 'Quantum Reduction', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'C': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[victim.id], sources=[])
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[victim.id], sources=[],
        optional_costs=[source.id + ':teamwork'], cost_choices=[{'component': 0, 'cards': [helper.id]}])
    assert s.state.cards[helper.id].tapped
    settle(s)
    actual = Plan(s.state, 'p1', cards, None).ch(s.state.cards[victim.id])
    assert actual.pt == (0, 5) and 'flying' not in actual.keywords
    roundtrip(s)


def test_fated_clash_flash_requires_actual_attack_and_block_and_resolves_destroy(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import stops, to_phase
    s = setup(cards)
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    blocker = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Storm Crow', 'battlefield', 'p3')
    opponent_turn(s)
    source = put(s, 'Fated Clash', 'hand')
    stops(s, 'declare_attackers', 'declare_blockers')
    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p1'}])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 2, 'C': 3})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[blocker.id, attacker.id], target_counts=[1, 1], sources=[])
    to_phase(s, 'declare_blockers', turn=2)
    act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': attacker.id}])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 2, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[blocker.id, attacker.id], target_counts=[1, 1], sources=[])
    settle(s)
    assert s.state.cards[attacker.id].zone == 'p2:battlefield'
    assert s.state.cards[blocker.id].zone == 'p1:battlefield'
    assert s.state.cards[other.id].zone == 'p3:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('kind', ['next', 'entry', 'energy', 'behold'])
def test_timing_permissions_resume_in_fresh_process(cards, tmp_path, kind):
    import subprocess
    import sys

    from app.rules.casting import alt_castable
    s = setup(cards)
    if kind == 'energy':
        spell(s, 'Primal Prayers', {'G': 2, 'C': 2})
    opponent_turn(s)
    if kind == 'entry':
        spell(s, 'Savage Summoning', {'G': 1})
    if kind == 'next':
        spell(s, "Scout's Warning", {'W': 1})
    selected = put(s, 'Molten Exhale' if kind == 'behold' else 'Grizzly Bears', 'hand')
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2') if kind == 'behold' else None
    dragon = put(s, 'Shivan Dragon', 'hand') if kind == 'behold' else None
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1} if kind == 'behold' else {'G': 1, 'C': 1})
    payload = {'type': 'cast_spell', 'card_id': selected.id, 'sources': []}
    if kind == 'energy':
        payload['alt_cost'] = alt_castable(s.state, 'p1', selected, cards)[0]['id']
    if kind == 'behold':
        payload.update(targets=[victim.id], optional_costs=[selected.id + ':behold'], cost_choices=[{'component': 0, 'cards': [dragon.id]}])
    path = tmp_path / (kind + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import json, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, kind, payload = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
a = json.loads(payload)
s.perform('p1', a)
for _ in range(80):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None, s.state.rules.decision
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('stack did not resolve')
if kind == 'behold':
    assert s.state.cards[a['targets'][0]].zone == 'p2:graveyard'
else:
    assert s.state.cards[a['card_id']].zone == 'p1:battlefield'
if kind == 'entry':
    assert s.state.cards[a['card_id']].counters.get('+1/+1') == 1
if kind == 'energy':
    assert s.state.players['p1'].resources.get('energy') == 1
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), kind, json.dumps(payload)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_two_scout_permissions_are_both_consumed_by_normal_main_phase_cast(cards):
    from app.game.errors import ActionError
    s = setup(cards)
    spell(s, "Scout's Warning", {'W': 1})
    spell(s, "Scout's Warning", {'W': 1})
    spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    opponent_turn(s)
    source = put(s, 'Grizzly Bears', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    roundtrip(s)


def test_primal_prayers_x_zero_energy_exhaustion_and_additional_costs(cards):
    from app.game.errors import ActionError
    from app.rules.casting import alt_castable
    s = setup(cards)
    spell(s, 'Primal Prayers', {'G': 2, 'C': 2})
    opponent_turn(s)
    priority(s, 'p1')
    walker = put(s, 'Hangarback Walker', 'hand')
    offer = alt_castable(s.state, 'p1', walker, cards)[0]['id']
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=walker.id, alt_cost=offer, x_value=1, sources=[])
    assert s.state.players['p1'].resources['energy'] == 2
    act(s, 'p1', type='cast_spell', card_id=walker.id, alt_cost=offer, x_value=0, sources=[])
    settle(s)
    assert s.state.cards[walker.id].zone == 'p1:graveyard'  # Actual 0/0, not an unpaid phantom spell.
    priority(s, 'p1')
    ruinator = put(s, 'Skaab Ruinator', 'hand')
    assert alt_castable(s.state, 'p1', ruinator, cards) == []
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ruinator.id, alt_cost=offer, sources=[])
    sacrifices = [put(s, name, 'graveyard') for name in ['Grizzly Bears', 'Suntail Hawk', 'Storm Crow']]
    offer = alt_castable(s.state, 'p1', ruinator, cards)[0]['id']
    act(s, 'p1', type='cast_spell', card_id=ruinator.id, alt_cost=offer, sources=[], cost_choices=[{'component': 0, 'cards': [c.id for c in sacrifices]}])
    settle(s)
    assert s.state.cards[ruinator.id].zone == 'p1:battlefield'
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in sacrifices)
    assert s.state.players['p1'].resources['energy'] == 0
    bear = put(s, 'Grizzly Bears', 'hand')
    priority(s, 'p1')
    assert alt_castable(s.state, 'p1', bear, cards) == []
    roundtrip(s)


def test_dragon_grip_locks_ferocious_before_sacrificing_power_for_mana(cards):
    s = setup(cards)
    opponent_turn(s)
    goblin = put(s, 'Skirk Prospector', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Giant Growth', {'G': 1}, [goblin.id])
    source = put(s, 'Dragon Grip', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id])
    assert s.state.rules.decision is not None and s.state.rules.decision.display['kind'] == 'tap_mana'
    act(s, 'p1', type='activate_ability', card_id=goblin.id, ability=0, cost_choices=[{'component': 0, 'cards': [goblin.id]}])
    settle(s)
    assert s.state.cards[goblin.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].attached_to == target.id
    roundtrip(s)


@pytest.mark.parametrize('permission,name,cost', [('Quicken', 'Rift Bolt', {'R': 1}), ("Scout's Warning", 'Durkwood Baloth', {'G': 1})])
def test_next_flash_permission_allows_native_suspend_on_opponents_turn(cards, permission, name, cost):
    from app.game.errors import ActionError
    from app.rules.plan import Plan
    s = setup(cards)
    opponent_turn(s)
    source = put(s, name, 'hand')
    ch = Plan(s.state, 'p1', cards, None).ch(source)
    index = next(ab.index for ab in ch.abilities if 'suspend' in ab.keywords)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana=cost)
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, sources=[])
    spell(s, permission, {'U': 1} if permission == 'Quicken' else {'W': 1})
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, sources=[])
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[source.id].counters.get('time') == (1 if name == 'Rift Bolt' else 5)
    roundtrip(s)


def test_scout_warning_never_allows_opponent_turn_dryad_arbor_land_play(cards):
    from app.game.errors import ActionError
    s = setup(cards)
    opponent_turn(s)
    spell(s, "Scout's Warning", {'W': 1})
    land = put(s, 'Dryad Arbor', 'hand')
    priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='play_land', card_id=land.id)
    assert s.state.cards[land.id].zone == 'p1:hand'
    roundtrip(s)


def test_ferocious_mana_payment_lock_resumes_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    opponent_turn(s)
    goblin = put(s, 'Skirk Prospector', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Giant Growth', {'G': 1}, [goblin.id])
    source = put(s, 'Dragon Grip', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id])
    assert s.state.rules.decision.resume['cast_timing_object'] == s.state.rules.object_id(source.id)
    path = tmp_path / 'locked-timing.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, goblin, source, target = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
s.perform('p1', {'type': 'activate_ability', 'card_id': goblin, 'ability': 0,
                 'cost_choices': [{'component': 0, 'cards': [goblin]}]})
for _ in range(60):
    if not s.state.zones.get('stack'):
        break
    assert s.state.rules.decision is None
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
assert s.state.cards[goblin].zone == 'p1:graveyard'
assert s.state.cards[source].zone == 'p1:battlefield'
assert s.state.cards[source].attached_to == target
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), goblin.id, source.id, target.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
