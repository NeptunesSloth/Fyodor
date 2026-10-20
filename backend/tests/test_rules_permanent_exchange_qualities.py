"""Current cross-target qualities bind at announcement, retargeting and resolution."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import answer
from tests.test_rules_source_quality_protection import ch, spell
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave30m_durations import stops, three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/permanent_exchange_quality_cards.json'
NAMES = ['Djinn of Infinite Deceits', 'Conjured Currency', "Puca's Mischief", 'Daring Thief', 'Legerdemain', 'Spawnbroker']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='peq', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())]
    s = three(cards, names, names, names)
    hold(s)
    return s


def may(s, yes=True):
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'yes', 'no'}, d
    answer(s, ['yes' if yes else 'no'])


def upkeep(s):
    stops(s, 'main1', 'upkeep')
    to_phase(s, 'upkeep', turn=4)
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_actual_canonical_six_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_legerdemain_native_exchange_retains_exact_object_identity(cards):
    s = setup(cards)
    first = put(s, 'Triarch Stalker', 'battlefield')
    second = put(s, 'Cursed Rack', 'battlefield', 'p2')
    before = [Plan(s.state, 'p1', cards, None).oid(c) for c in (first, second)]
    spell(s, 'Legerdemain', {'U': 2, 'C': 2}, [first.id, second.id], target_counts=[1, 1])
    assert s.state.cards[first.id].controller == 'p2' and s.state.cards[second.id].controller == 'p1'
    assert [Plan(s.state, 'p1', cards, None).oid(s.state.cards[c.id]) for c in (first, second)] == before
    roundtrip(s)


def test_legerdemain_rejects_duplicate_and_only_incidental_shared_enchantment(cards):
    s = setup(cards)
    put(s, 'Mycosynth Lattice', 'battlefield')
    first = put(s, 'Fervor', 'battlefield')
    second = put(s, 'Bitterblossom', 'battlefield', 'p2')
    with pytest.raises(ActionError, match='Another target|legal target|another target'):
        spell(s, 'Legerdemain', {'U': 2, 'C': 2}, [first.id, first.id], target_counts=[1, 1])
    # Both are currently artifacts, so this pair really is legal before Lattice leaves.
    spell(s, 'Legerdemain', {'U': 2, 'C': 2}, [first.id, second.id], target_counts=[1, 1])
    assert s.state.cards[first.id].controller == 'p2'
    roundtrip(s)


@pytest.mark.parametrize('accept', [True, False])
def test_spawnbroker_actual_etb_chooses_pair_before_optional_exchange(cards, accept):
    s = setup(cards)
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Giant Spider', 'battlefield', 'p2')
    source = spell(s, 'Spawnbroker', {'U': 1, 'C': 2})
    assert s.state.rules.decision is not None
    answer(s, [first.id])
    answer(s, [second.id])
    assert s.state.cards[first.id].controller == 'p1' and s.state.cards[second.id].controller == 'p2'
    may(s, accept)
    assert s.state.cards[first.id].controller == ('p2' if accept else 'p1')
    assert s.state.cards[second.id].controller == ('p1' if accept else 'p2')
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_puca_native_upkeep_prunes_first_targets_without_legal_completion(cards):
    s = setup(cards)
    source = put(s, "Puca's Mischief", 'battlefield')
    small = put(s, 'Grizzly Bears', 'battlefield')
    equal = put(s, 'Giant Spider', 'battlefield')
    other = put(s, 'Cursed Rack', 'battlefield', 'p2')
    upkeep(s)
    d = s.state.rules.decision
    assert d is not None
    offered = {o.id for o in d.options}
    assert small.id not in offered and equal.id in offered and source.id in offered
    answer(s, [equal.id])
    assert s.state.rules.decision is not None, [(x.kind, ''.join(p.t or '' for p in x.parts)) for x in s.state.log[-8:]]
    answer(s, [other.id])
    may(s)
    assert s.state.cards[equal.id].controller == 'p2' and s.state.cards[other.id].controller == 'p1'
    roundtrip(s)


def test_daring_thief_native_untap_can_exchange_kindred_only_shared_type(cards):
    s = setup(cards)
    source = put(s, 'Daring Thief', 'battlefield')
    first = put(s, 'Bitterblossom', 'battlefield')
    second = put(s, 'Thornbite Staff', 'battlefield', 'p2')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    spell(s, 'Cerulean Wisps', {'U': 1}, [source.id])
    answer(s, [first.id])
    answer(s, [second.id])
    may(s)
    assert s.state.cards[first.id].controller == 'p2' and s.state.cards[second.id].controller == 'p1'
    roundtrip(s)


def test_conjured_currency_stolen_source_uses_original_trigger_controller_for_targets(cards):
    s = setup(cards)
    source = put(s, 'Conjured Currency', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    own = put(s, 'Giant Spider', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[own.id], player='p2')
    upkeep(s)
    d = s.state.rules.decision
    assert d is not None and own.id not in {o.id for o in d.options} and other.id in {o.id for o in d.options}
    answer(s, [other.id])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    may(s)
    assert s.state.cards[source.id].controller == 'p3' and s.state.cards[other.id].controller == 'p2'
    roundtrip(s)


def djinn(s):
    put(s, 'Fervor', 'battlefield')
    source = put(s, 'Djinn of Infinite Deceits', 'battlefield')
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    second = put(s, 'Giant Spider', 'battlefield', 'p3')
    return source, first, second


def test_djinn_native_tap_ability_can_exchange_other_players_creatures(cards):
    s = setup(cards)
    source, first, second = djinn(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Exchange control'),
        targets=[first.id, second.id], target_counts=[2])
    assert s.state.cards[source.id].tapped
    settle(s)
    assert s.state.cards[first.id].controller == 'p3' and s.state.cards[second.id].controller == 'p2'
    roundtrip(s)


def test_djinn_native_combat_restriction_prevents_activation_without_paying_tap(cards):
    s = setup(cards)
    source, first, second = djinn(s)
    stops(s, 'main1', 'begin_combat')
    to_phase(s, 'begin_combat')
    with pytest.raises(ActionError, match='combat'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Exchange control'),
            targets=[first.id, second.id], target_counts=[2])
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def pick_only(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


def test_legerdemain_does_not_treat_shared_enchantment_as_one_of_artifact_or_creature(cards):
    s = setup(cards)
    first = put(s, 'Courser of Kruphix', 'battlefield')
    second = put(s, 'Bitterblossom', 'battlefield', 'p2')
    assert 'Enchantment' in ch(s, first).types & ch(s, second).types
    with pytest.raises(ActionError, match='legal target'):
        spell(s, 'Legerdemain', {'U': 2, 'C': 2}, [first.id, second.id], target_counts=[1, 1])
    assert s.state.cards[first.id].controller == 'p1' and s.state.cards[second.id].controller == 'p2'
    roundtrip(s)


def test_spawnbroker_rechecks_power_after_targets_are_announced(cards):
    s = setup(cards)
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Giant Spider', 'battlefield', 'p2')
    spell(s, 'Spawnbroker', {'U': 1, 'C': 2})
    answer(s, [first.id])
    pick_only(s, [second.id])
    spell(s, 'Giant Growth', {'G': 1}, [second.id], player='p2', finish=False)
    settle(s)
    may(s)
    assert s.state.cards[first.id].controller == 'p1' and s.state.cards[second.id].controller == 'p2'
    roundtrip(s)


def test_daring_thief_card_type_relation_rechecks_after_lattice_leaves(cards):
    s = setup(cards)
    lattice = put(s, 'Mycosynth Lattice', 'battlefield')
    source = put(s, 'Daring Thief', 'battlefield')
    first = put(s, 'Fervor', 'battlefield')
    second = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    spell(s, 'Cerulean Wisps', {'U': 1}, [source.id])
    answer(s, [first.id])
    pick_only(s, [second.id])
    act(s, 'p1', type='move', card_ids=[lattice.id], to={'zone': 'exile'})
    settle(s)
    may(s)
    assert s.state.cards[first.id].controller == 'p1' and s.state.cards[second.id].controller == 'p2'
    roundtrip(s)


def test_daring_thief_second_permanent_may_be_an_artifact_land(cards):
    s = setup(cards)
    source = put(s, 'Daring Thief', 'battlefield')
    first = put(s, 'Cursed Rack', 'battlefield')
    second = put(s, 'Darksteel Citadel', 'battlefield', 'p2')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    spell(s, 'Cerulean Wisps', {'U': 1}, [source.id])
    answer(s, [first.id])
    answer(s, [second.id])
    may(s)
    assert s.state.cards[first.id].controller == 'p2' and s.state.cards[second.id].controller == 'p1'
    roundtrip(s)


def test_djinn_pending_ability_exchanges_after_its_source_leaves(cards):
    s = setup(cards)
    source, first, second = djinn(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Exchange control'),
        targets=[first.id, second.id], target_counts=[2])
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    settle(s)
    assert s.state.cards[first.id].controller == 'p3' and s.state.cards[second.id].controller == 'p2'
    roundtrip(s)


@pytest.mark.parametrize('removed', [1, 2])
def test_djinn_one_illegal_target_prevents_whole_exchange_and_all_illegal_fizzles(cards, removed):
    s = setup(cards)
    source, first, second = djinn(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Exchange control'),
        targets=[first.id, second.id], target_counts=[2])
    for c in [first, second][:removed]:
        act(s, 'p1', type='move', card_ids=[c.id], to={'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[first.id].controller == 'p2' and s.state.cards[second.id].controller == 'p3'
    assert not s.state.zones['stack']
    roundtrip(s)


def test_spawnbroker_signed_power_threshold_does_not_allow_zero_power_over_negative(cards):
    s = setup(cards)
    put(s, 'Meishin, the Mind Cage', 'battlefield')
    for name in ['Lightning Bolt', 'Giant Growth', 'Healing Salve']:
        put(s, name, 'hand')
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Giant Spider', 'battlefield', 'p2')
    higher = put(s, 'Triarch Stalker', 'battlefield', 'p2')
    spell(s, 'Spawnbroker', {'U': 1, 'C': 2})
    assert ch(s, first).pt[0] < 0 and ch(s, higher).pt[0] > ch(s, first).pt[0]
    answer(s, [first.id])
    d = s.state.rules.decision
    assert d is not None and second.id in {o.id for o in d.options} and higher.id not in {o.id for o in d.options}
    answer(s, [second.id])
    may(s)
    assert s.state.cards[first.id].controller == 'p2' and s.state.cards[second.id].controller == 'p1'
    roundtrip(s)


def test_conjured_currency_source_blink_prevents_old_pending_exchange(cards):
    s = setup(cards)
    source = put(s, 'Conjured Currency', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    original = Plan(s.state, 'p1', cards, None).oid(source)
    upkeep(s)
    pick_only(s, [other.id])
    spell(s, 'Flicker of Fate', {'W': 1, 'C': 1}, [source.id], finish=False)
    settle(s)
    may(s)
    assert Plan(s.state, 'p1', cards, None).oid(s.state.cards[source.id]) != original
    assert s.state.cards[source.id].controller == 'p1' and s.state.cards[other.id].controller == 'p2'
    roundtrip(s)


def test_puca_without_any_complete_pair_drops_trigger_without_optional_prompt(cards):
    s = setup(cards)
    source = put(s, "Puca's Mischief", 'battlefield')
    put(s, 'Meishin, the Mind Cage', 'battlefield', 'p2')
    upkeep(s)
    assert s.state.rules.decision is None and not s.state.zones.get('stack', [])
    assert s.state.cards[source.id].controller == 'p1'
    roundtrip(s)


def test_djinn_may_target_two_creatures_controlled_by_same_player_without_swap(cards):
    s = setup(cards)
    source, first, second = djinn(s)
    act(s, 'p1', type='set_controller', card_ids=[second.id], player='p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Exchange control'),
        targets=[first.id, second.id], target_counts=[2])
    settle(s)
    assert s.state.cards[first.id].controller == s.state.cards[second.id].controller == 'p2'
    roundtrip(s)


def test_relative_power_uses_exact_old_object_lki_after_first_target_reenters(cards):
    s = setup(cards)
    first = put(s, 'Grizzly Bears', 'battlefield')
    second = put(s, 'Triarch Stalker', 'battlefield', 'p2')
    spell(s, 'Giant Growth', {'G': 1}, [first.id])
    assert ch(s, first).pt[0] == 5 and ch(s, second).pt[0] == 4
    spell(s, 'Spawnbroker', {'U': 1, 'C': 2})
    answer(s, [first.id])
    pick_only(s, [second.id])
    original = Plan(s.state, 'p1', cards, None).oid(s.state.cards[first.id])
    spell(s, 'Flicker of Fate', {'W': 1, 'C': 1}, [first.id], finish=False)
    settle(s)
    assert Plan(s.state, 'p1', cards, None).oid(s.state.cards[first.id]) != original
    assert ch(s, first).pt[0] == 2
    # Target1 is illegal, but target2 remains legal relative to target1's old5power.
    # The ability resolves to its optional exchange; it cannot perform the whole swap.
    may(s)
    assert s.state.cards[first.id].controller == 'p1' and s.state.cards[second.id].controller == 'p2'
    roundtrip(s)


def test_copy_retarget_rebinds_shared_type_and_rejects_incompatible_kept_target(cards):
    s = setup(cards)
    first = put(s, 'Triarch Stalker', 'battlefield')
    second = put(s, 'Cursed Rack', 'battlefield', 'p2')
    new_first = put(s, 'Courser of Kruphix', 'battlefield', 'p3')
    new_second = put(s, 'Giant Spider', 'battlefield', 'p2')
    original = spell(s, 'Legerdemain', {'U': 2, 'C': 2}, [first.id, second.id], target_counts=[1, 1], finish=False)
    spell(s, 'Twincast', {'U': 2}, [original.id], player='p2')
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'copy_target'
    answer(s, [new_first.id])
    d = s.state.rules.decision
    assert d is not None and new_second.id in {o.id for o in d.options}
    assert second.id not in {o.id for o in d.options}  # Its old artifact-only type no longer matches.
    answer(s, ['keep'])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'copy_target'  # Invalid final pair must be chosen again.
    answer(s, [new_first.id])
    answer(s, [new_second.id])
    assert s.state.cards[new_first.id].controller == 'p2' and s.state.cards[new_second.id].controller == 'p3'
    assert s.state.cards[first.id].controller == 'p2' and s.state.cards[second.id].controller == 'p1'
    roundtrip(s)


@pytest.mark.parametrize('kind', ['mv', 'power', 'types'])
def test_second_target_relative_quality_resumes_in_fresh_process(cards, tmp_path, kind):
    import subprocess
    import sys

    s = setup(cards)
    if kind == 'mv':
        put(s, "Puca's Mischief", 'battlefield')
        first = put(s, 'Giant Spider', 'battlefield')
        second = put(s, 'Cursed Rack', 'battlefield', 'p2')
        upkeep(s)
    elif kind == 'power':
        first = put(s, 'Grizzly Bears', 'battlefield')
        second = put(s, 'Giant Spider', 'battlefield', 'p2')
        spell(s, 'Spawnbroker', {'U': 1, 'C': 2})
    else:
        source = put(s, 'Daring Thief', 'battlefield')
        first = put(s, 'Bitterblossom', 'battlefield')
        second = put(s, 'Thornbite Staff', 'battlefield', 'p2')
        act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
        spell(s, 'Cerulean Wisps', {'U': 1}, [source.id])
    answer(s, [first.id])
    d = s.state.rules.decision
    assert d is not None and second.id in {o.id for o in d.options}
    path = tmp_path / f'relative-{kind}.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, first, second = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
assert s.view('p1')['rules']['decision'] is not None
assert not s.view('p2')['rules']['decision'].get('options')
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [second]})
for _ in range(16):
    d = s.state.rules.decision
    if d is not None:
        assert {o.id for o in d.options} == {'yes', 'no'}
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['yes']})
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
else:
    raise AssertionError('exchange did not resolve')
assert s.state.cards[first].controller == 'p2' and s.state.cards[second].controller == 'p1'
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), first.id, second.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_daring_thief_untap_step_trigger_waits_for_upkeep_target_selection(cards):
    s = setup(cards)
    source = put(s, 'Daring Thief', 'battlefield')
    first = put(s, 'Cursed Rack', 'battlefield')
    second = put(s, 'Darksteel Citadel', 'battlefield', 'p2')
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=True)
    stops(s, 'upkeep', 'main1')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert s.state.turn.phase == 'upkeep' and not s.state.cards[source.id].tapped
    answer(s, [first.id])
    answer(s, [second.id])
    may(s)
    assert s.state.cards[first.id].controller == 'p2' and s.state.cards[second.id].controller == 'p1'
    roundtrip(s)


def test_djinn_tap_cost_still_requires_haste_or_control_since_turn_began(cards):
    s = setup(cards)
    source = put(s, 'Djinn of Infinite Deceits', 'battlefield')
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    second = put(s, 'Giant Spider', 'battlefield', 'p3')
    with pytest.raises(ActionError, match='sick|summon'):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability_index(s, source, 'Exchange control'),
            targets=[first.id, second.id], target_counts=[2])
    assert not s.state.cards[source.id].tapped
    roundtrip(s)
