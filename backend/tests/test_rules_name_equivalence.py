"""Actual name equivalence uses object characteristics, not printing display names."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

NAME = "Pack Hunt"
DATA = Path(__file__).parent / 'fixtures/name_equivalence_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='csc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())] + ['Bonecrusher Giant // Stomp', 'Grizzly Bears', 'Lightning Bolt', 'Forest', 'Winnow', 'Thassa, God of the Sea', 'Cylian Sunsinger', 'Ornithopter', 'Grizzly Bears', 'Kami of Ancient Law', 'Reap Intellect', 'Breeding Pool', 'Breeding Pool']
    s = three(cards, names, names, names)
    hold(s)
    return s


def test_pack_hunt_adventure_front_name_finds_same_creature_card(cards):
    s = setup(cards)
    copies = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Bonecrusher Giant // Stomp']
    assert len(copies) == 2
    act(s, 'p1', type='move', card_ids=[copies[0].id], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='move', card_ids=[copies[1].id], to={'player': 'p1', 'zone': 'library'})
    spell(s, NAME, {'G': 1, 'C': 3}, [copies[0].id])
    d = s.state.rules.decision
    assert d is not None and any(o.id == copies[1].id for o in d.options)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[copies[1].id])
    assert s.state.cards[copies[1].id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Cylian Sunsinger', 'Winnow', 'Moratorium Stone', 'Bloodbond March'])
def test_first_native_name_instructions_parse(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_sunsinger_pumps_source_and_other_controllers_matching_creatures(cards):
    from app.rules.plan import Plan
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    source = put(s, 'Cylian Sunsinger', 'battlefield')
    other = put(s, 'Cylian Sunsinger', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'G': 1, 'W': 1})
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    p = Plan(s.state, 'p1', s.cards, None)
    assert p.ch(source).pt == (5, 5)
    assert p.ch(other).pt == (5, 5)
    assert p.ch(bear).pt == (2, 2)
    roundtrip(s)


@pytest.mark.parametrize('duplicate', [False, True])
def test_winnow_draws_even_without_duplicate_and_destroys_only_with_one(cards, duplicate):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if duplicate:
        put(s, 'Grizzly Bears', 'battlefield', 'p3')
    drew = s.state.rules.turn_log.drew.get('p1', 0)
    spell(s, 'Winnow', {'W': 1, 'C': 1}, [target.id])
    assert s.state.cards[target.id].zone == ('p2:graveyard' if duplicate else 'p2:battlefield')
    assert s.state.rules.turn_log.drew.get('p1', 0) == drew + 1
    roundtrip(s)


def test_bloodbond_returns_matching_cards_for_each_owner(cards):
    s = setup(cards)
    put(s, 'Bloodbond March', 'battlefield')
    a = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    b = put(s, 'Grizzly Bears', 'graveyard', 'p3')
    spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    assert s.state.cards[a.id].zone == 'p2:battlefield'
    assert s.state.cards[b.id].zone == 'p3:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', [c['name'] for c in json.loads(DATA.read_text())][:20])
def test_family_canonical_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def test_moratorium_stone_exiles_same_names_across_controllers_and_graveyards(cards):
    s = setup(cards)
    source = put(s, 'Moratorium Stone', 'battlefield')
    a = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    b = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    c = put(s, 'Grizzly Bears', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'B': 1, 'C': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[a.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert all(s.state.cards[x.id].zone.endswith(':exile') for x in (a, b, c))
    roundtrip(s)


def test_legions_end_exiles_same_controllers_creatures_and_hand_and_graveyard(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    own = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    copy = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Grizzly Bears' and c.id != target.id)
    act(s, 'p2', type='move', card_ids=[copy.id], to={'player': 'p2', 'zone': 'hand'})
    spell(s, "Legion's End", {'B': 1, 'C': 1}, [target.id])
    assert s.state.cards[target.id].zone == s.state.cards[copy.id].zone == 'p2:exile'
    assert s.state.cards[own.id].zone == 'p1:battlefield'
    assert s.state.cards[other.id].zone == 'p3:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('god', [False, True])
def test_hour_of_glory_uses_battlefield_god_condition_and_controller_hand(cards, god):
    s = setup(cards)
    name = 'Thassa, God of the Sea' if god else 'Grizzly Bears'
    target = put(s, name, 'battlefield', 'p2')
    # Thassa remains a God enchantment without devotion, so make it a creature with real blue devotion.
    if god:
        put(s, 'Bazaar of Wonders', 'battlefield', 'p2')
        put(s, 'Detention Sphere', 'battlefield', 'p2')
        put(s, 'Reflector Mage', 'battlefield', 'p2')
    copy = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == name and c.id != target.id)
    act(s, 'p2', type='move', card_ids=[copy.id], to={'player': 'p2', 'zone': 'hand'})
    spell(s, 'Hour of Glory', {'B': 1, 'C': 3}, [target.id])
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert s.state.cards[copy.id].zone == ('p2:exile' if god else 'p2:hand')
    roundtrip(s)


def test_locket_reduces_for_each_matching_graveyard_card(cards):
    s = setup(cards)
    put(s, 'Locket of Yesterdays', 'battlefield')
    copies = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Winnow']
    act(s, 'p1', type='move', card_ids=[copies[0].id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[copies[1].id], to={'player': 'p1', 'zone': 'hand'})
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='cast_spell', card_id=copies[1].id, targets=[target.id])
    settle(s)
    assert s.state.cards[copies[1].id].zone == 'p1:graveyard'
    roundtrip(s)


def test_chrome_replicator_creates_actual_construct_for_distinct_duplicate_permanents(cards):
    s = setup(cards)
    copies = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Ornithopter']
    act(s, 'p1', type='move', card_ids=[c.id for c in copies], to={'player': 'p1', 'zone': 'battlefield'})
    spell(s, 'Chrome Replicator', {'C': 5})
    constructs = [c for c in s.state.cards.values() if c.name == 'Construct' and c.zone == 'p1:battlefield']
    assert len(constructs) == 1
    roundtrip(s)


def test_mimeofacture_searches_target_controller_library_into_casters_battlefield(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    other = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Grizzly Bears' and c.id != target.id)
    act(s, 'p2', type='move', card_ids=[other.id], to={'player': 'p2', 'zone': 'library'})
    spell(s, 'Mimeofacture', {'U': 1, 'C': 3}, [target.id])
    choose(s, [other.id])
    assert s.state.cards[other.id].zone == 'p1:battlefield' and s.state.cards[other.id].owner == 'p2'
    roundtrip(s)


def test_eye_of_singularity_destroys_duplicates_but_preserves_basic_lands(cards):
    s = setup(cards)
    a = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    b = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    forest_a = put(s, 'Forest', 'battlefield', 'p2')
    forest_b = put(s, 'Forest', 'battlefield', 'p3')
    spell(s, 'Eye of Singularity', {'W': 1, 'C': 3})
    assert s.state.cards[a.id].zone == 'p2:graveyard' and s.state.cards[b.id].zone == 'p3:graveyard'
    assert all(s.state.cards[c.id].zone.endswith(':battlefield') for c in (forest_a, forest_b))
    roundtrip(s)


def test_bazaar_counters_actual_cast_matching_a_graveyard_card(cards):
    s = setup(cards)
    put(s, 'Bazaar of Wonders', 'battlefield')
    put(s, 'Lightning Bolt', 'graveyard', 'p2')
    life = s.state.players['p3'].life
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'])
    assert s.state.players['p3'].life == life
    roundtrip(s)


def test_reflector_bounces_then_bans_owner_casting_the_name(cards):
    from app.game.errors import ActionError
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    spell(s, 'Reflector Mage', {'W': 1, 'U': 1, 'C': 1})
    choose(s, [target.id])
    assert s.state.cards[target.id].zone == 'p2:hand'
    from tests.test_rules_wave30m_durations import stops, to_phase
    stops(s, 'main1')
    to_phase(s, 'main1', turn=2)
    with pytest.raises(ActionError, match="can't cast"):
        spell(s, 'Grizzly Bears', {'G': 1, 'C': 1}, player='p2')
    roundtrip(s)


def test_academic_probation_named_mode_only_bans_opponents(cards):
    from app.game.errors import ActionError
    s = setup(cards)
    spell(s, 'Academic Probation', {'W': 1, 'C': 1}, modes=[0])
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[], name='Grizzly Bears')
    settle(s)
    spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    from tests.test_rules_wave30m_durations import stops, to_phase
    stops(s, 'main1')
    to_phase(s, 'main1', turn=2)
    with pytest.raises(ActionError, match="can't cast"):
        spell(s, 'Grizzly Bears', {'G': 1, 'C': 1}, player='p2')
    roundtrip(s)


def test_cornered_market_dynamically_bans_actual_same_name_spells(cards):
    from app.game.errors import ActionError
    s = setup(cards)
    put(s, 'Cornered Market', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    with pytest.raises(ActionError):
        spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p2', 'zone': 'graveyard'})
    spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    roundtrip(s)


def delirium(s):
    for name in ('Grizzly Bears', 'Ornithopter', 'Fervor', 'Lightning Bolt'):
        put(s, name, 'graveyard')


def test_pick_the_brain_exiles_chosen_hand_card_then_matching_library_card(cards):
    s = setup(cards)
    delirium(s)
    hand = put(s, 'Winnow', 'hand', 'p2')
    other = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Winnow' and c.id != hand.id)
    act(s, 'p2', type='move', card_ids=[other.id], to={'player': 'p2', 'zone': 'library'})
    from app.rules import conditions
    from app.rules.plan import Plan
    assert conditions.holds(Plan(s.state, 'p1', s.cards, None), {'controller': 'p1'}, conditions.parse('there are four or more card types among cards in your graveyard'))
    spell(s, 'Pick the Brain', {'B': 1, 'C': 2}, ['p2'])
    choose(s, [hand.id])
    choose(s, [other.id])
    assert s.state.cards[hand.id].zone == s.state.cards[other.id].zone == 'p2:exile'
    roundtrip(s)


def test_reap_intellect_exiles_multiple_hand_names_and_matching_cards(cards):
    s = setup(cards)
    hand = put(s, 'Winnow', 'hand', 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    other = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Winnow' and c.id != hand.id)
    act(s, 'p2', type='move', card_ids=[other.id], to={'player': 'p2', 'zone': 'library'})
    spell(s, 'Reap Intellect', {'U': 1, 'B': 1, 'C': 4}, ['p2'], x_value=2)
    choose(s, [hand.id, bolt.id])
    choose(s, [other.id])
    assert all(s.state.cards[c.id].zone == 'p2:exile' for c in (hand, bolt, other))
    roundtrip(s)


def test_detention_sphere_exiles_matching_permanents_and_returns_on_departure(cards):
    s = setup(cards)
    a = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    b = put(s, 'Grizzly Bears', 'battlefield', 'p3')
    sphere = spell(s, 'Detention Sphere', {'W': 1, 'U': 1, 'C': 1})
    choose(s, [a.id])
    if s.state.rules.decision is not None:
        choose(s, ['yes'])
    assert s.state.cards[a.id].zone == 'p2:exile' and s.state.cards[b.id].zone == 'p3:exile'
    kami = put(s, 'Kami of Ancient Law', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=kami.id, ability=0, targets=[sphere.id])
    settle(s)
    assert s.state.cards[a.id].zone == 'p2:battlefield' and s.state.cards[b.id].zone == 'p3:battlefield'
    roundtrip(s)


def test_dichotomancy_separate_name_slots_find_distinct_copies(cards):
    s = setup(cards)
    a = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    b = put(s, 'Cylian Sunsinger', 'battlefield', 'p2')
    act(s, 'p2', type='tap', card_ids=[a.id, b.id], tapped=True)
    matches = [next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == old.name and c.id != old.id) for old in (a, b)]
    act(s, 'p2', type='move', card_ids=[c.id for c in matches], to={'player': 'p2', 'zone': 'library'})
    spell(s, 'Dichotomancy', {'U': 2, 'C': 7}, ['p2'])
    for _ in range(2):
        d = s.state.rules.decision
        assert d is not None
        chosen = next(c.id for c in matches if any(o.id == c.id for o in d.options))
        choose(s, [chosen])
    assert all(s.state.cards[c.id].zone == 'p1:battlefield' for c in matches)
    roundtrip(s)


def test_deicide_uses_actual_exiled_god_card_and_searches_its_controller(cards):
    s = setup(cards)
    god = put(s, 'Thassa, God of the Sea', 'battlefield', 'p2')
    other = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == god.name and c.id != god.id)
    act(s, 'p2', type='move', card_ids=[other.id], to={'player': 'p2', 'zone': 'library'})
    spell(s, 'Deicide', {'W': 1, 'C': 1}, [god.id])
    choose(s, [other.id])
    assert s.state.cards[god.id].zone == s.state.cards[other.id].zone == 'p2:exile'
    roundtrip(s)


def test_invasive_surgery_counters_then_searches_even_after_spell_left_stack(cards):
    s = setup(cards)
    delirium(s)
    sorcery = put(s, 'Reap Intellect', 'hand')
    other = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Reap Intellect' and c.id != sorcery.id)
    act(s, 'p1', type='move', card_ids=[other.id], to={'player': 'p1', 'zone': 'library'})
    sorcery = spell(s, 'Reap Intellect', {'U': 1, 'B': 1, 'C': 2}, ['p2'], x_value=0, finish=False)
    assert s.state.cards[sorcery.id].zone == 'stack'
    from tests.test_rules_player_protection import priority
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    invasive = put(s, 'Invasive Surgery', 'hand')
    act(s, 'p1', type='cast_spell', card_id=invasive.id, targets=[sorcery.id])
    settle(s)
    choose(s, [other.id, sorcery.id])
    assert s.state.cards[sorcery.id].zone == s.state.cards[other.id].zone == 'p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('kind', ['hand', 'tutor', 'name'])
def test_name_bound_sequences_resume_in_a_fresh_process(cards, tmp_path, kind):
    import subprocess
    import sys

    s = setup(cards)
    followup = ''
    if kind == 'hand':
        delirium(s)
        selected = put(s, 'Winnow', 'hand', 'p2')
        other = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == selected.name and c.id != selected.id)
        act(s, 'p2', type='move', card_ids=[other.id], to={'player': 'p2', 'zone': 'library'})
        followup = other.id
        spell(s, 'Pick the Brain', {'B': 1, 'C': 2}, ['p2'])
    elif kind == 'tutor':
        target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
        selected = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == target.name and c.id != target.id)
        act(s, 'p2', type='move', card_ids=[selected.id], to={'player': 'p2', 'zone': 'library'})
        spell(s, 'Mimeofacture', {'U': 1, 'C': 3}, [target.id])
    else:
        selected = put(s, 'Grizzly Bears', 'hand', 'p2')
        spell(s, 'Academic Probation', {'W': 1, 'C': 1}, modes=[0])
    assert s.state.rules.decision is not None
    path = tmp_path / f'{kind}.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, kind, selected, followup = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
def settle():
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == 'order':
            s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [o.id for o in d.options]})
        elif d is None and s.state.zones.get('stack'):
            s.perform(s.state.rules.priority, {'type': 'pass_priority'})
        else:
            return
    raise AssertionError('did not settle')
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [] if kind == 'name' else [selected],
                     **({'name': 'Grizzly Bears'} if kind == 'name' else {})})
settle()
if kind == 'hand':
    d = s.state.rules.decision
    assert d is not None and any(o.id == followup for o in d.options)
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [followup]})
    settle()
    assert s.state.cards[selected].zone == s.state.cards[followup].zone == 'p2:exile'
elif kind == 'tutor':
    assert s.state.cards[selected].zone == 'p1:battlefield'
else:
    assert any(x.get('player') == 'p2' and 'Grizzly Bears' in x.get('filter', '') for x in s.state.rules.cast_limits)
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), kind, selected.id, followup],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_sunsinger_retains_source_last_known_name_after_source_dies(cards):
    from app.rules.plan import Plan
    s = setup(cards)
    source = put(s, 'Cylian Sunsinger', 'battlefield')
    other = put(s, 'Cylian Sunsinger', 'battlefield', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2, 'G': 1, 'W': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    spell(s, 'Lightning Bolt', {'R': 1}, [source.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[other.id]).pt == (5, 5)
    roundtrip(s)


def test_chrome_replicator_intervening_if_rechecks_after_a_duplicate_leaves(cards):
    s = setup(cards)
    copies = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Ornithopter']
    act(s, 'p1', type='move', card_ids=[c.id for c in copies], to={'player': 'p1', 'zone': 'battlefield'})
    source = spell(s, 'Chrome Replicator', {'C': 5}, finish=False)
    for _ in range(10):
        if s.state.cards[source.id].zone.endswith(':battlefield'):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.zones['stack']
    spell(s, 'Lightning Bolt', {'R': 1}, [copies[0].id])
    assert not any(c.name == 'Construct' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    roundtrip(s)


def test_chrome_replicator_does_not_count_duplicate_across_different_controllers(cards):
    s = setup(cards)
    put(s, 'Ornithopter', 'battlefield')
    put(s, 'Ornithopter', 'battlefield', 'p2')
    spell(s, 'Chrome Replicator', {'C': 5})
    assert not any(c.name == 'Construct' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    roundtrip(s)


def test_deicide_non_god_exile_does_not_search(cards):
    s = setup(cards)
    target = put(s, 'Fervor', 'battlefield', 'p2')
    spell(s, 'Deicide', {'W': 1, 'C': 1}, [target.id])
    assert s.state.cards[target.id].zone == 'p2:exile' and s.state.rules.decision is None
    roundtrip(s)


def test_eye_of_singularity_later_entry_destroys_old_match_and_keeps_new_entry(cards):
    s = setup(cards)
    put(s, 'Eye of Singularity', 'battlefield')
    old = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    new = spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    assert s.state.cards[old.id].zone == 'p2:graveyard' and s.state.cards[new.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_reap_intellect_zero_selected_hand_cards_does_not_search(cards):
    s = setup(cards)
    put(s, 'Winnow', 'hand', 'p2')
    spell(s, 'Reap Intellect', {'U': 1, 'B': 1, 'C': 3}, ['p2'], x_value=1)
    choose(s, [])
    assert s.state.rules.decision is None
    roundtrip(s)


def test_pick_the_brain_without_delirium_exiles_only_selected_hand_card(cards):
    s = setup(cards)
    selected = put(s, 'Winnow', 'hand', 'p2')
    other = next(c for c in s.state.cards.values() if c.owner == 'p2' and c.name == selected.name and c.id != selected.id)
    act(s, 'p2', type='move', card_ids=[other.id], to={'player': 'p2', 'zone': 'graveyard'})
    spell(s, 'Pick the Brain', {'B': 1, 'C': 2}, ['p2'])
    choose(s, [selected.id])
    assert s.state.cards[selected.id].zone == 'p2:exile' and s.state.cards[other.id].zone == 'p2:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_academic_probation_permanent_mode_stops_activated_abilities(cards):
    from app.game.errors import ActionError
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    target = put(s, 'Kami of Ancient Law', 'battlefield', 'p2')
    enchantment = put(s, 'Fervor', 'battlefield')
    spell(s, 'Academic Probation', {'W': 1, 'C': 1}, [target.id], modes=[1])
    priority(s, 'p2')
    with pytest.raises(ActionError, match="activated"):
        act(s, 'p2', type='activate_ability', card_id=target.id, ability=0, targets=[enchantment.id])
    roundtrip(s)


@pytest.mark.parametrize('basic', [False, True])
def test_cornered_market_separately_checks_nonbasic_land_plays(cards, basic):
    from app.game.errors import ActionError
    s = setup(cards)
    put(s, 'Cornered Market', 'battlefield')
    name = 'Forest' if basic else 'Breeding Pool'
    put(s, name, 'battlefield', 'p2')
    land = put(s, name, 'hand')
    if basic:
        act(s, 'p1', type='play_land', card_id=land.id)
        assert s.state.cards[land.id].zone == 'p1:battlefield'
    else:
        with pytest.raises(ActionError, match='nonbasic land'):
            act(s, 'p1', type='play_land', card_id=land.id)
        assert s.state.cards[land.id].zone == 'p1:hand'
    roundtrip(s)


def test_deicide_exiling_an_actual_copied_god_token_does_not_search(cards):
    s = setup(cards)
    original = put(s, 'Thassa, God of the Sea', 'battlefield')
    for name in ('Bazaar of Wonders', 'Detention Sphere', 'Reflector Mage'):
        put(s, name, 'battlefield')
    spell(s, 'Cackling Counterpart', {'U': 2, 'C': 1}, [original.id])
    token = next(c for c in s.state.cards.values() if c.name == original.name and c.token and c.zone == 'p1:battlefield')
    if s.state.rules.decision is not None:
        choose(s, [token.id])
    assert s.state.cards[original.id].zone == 'p1:graveyard'
    spell(s, 'Deicide', {'W': 1, 'C': 1}, [token.id])
    assert s.state.rules.decision is None
    assert s.state.cards[original.id].zone == 'p1:graveyard'
    roundtrip(s)
