"""Current color histograms, resolution comparisons and native state triggers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import answer, priority
from tests.test_rules_source_quality_protection import ch, spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/common_color_comparison_cards.json'
NAMES = ["Tsabo's Assassin", "Barrin's Unmaking", 'Heroic Defiance', 'Jaded Response', 'Call to Arms']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='ccc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
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


@pytest.mark.parametrize('name', NAMES)
def test_canonical_five_full(cards, name):
    r = coverage.of_card_data(cards.resolve(name))
    assert r.level == 'FULL', r.manual_parts


def assassin(s, target, finish=True):
    source = put(s, "Tsabo's Assassin", 'battlefield')
    put(s, 'Fervor', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[target.id])
    if finish:
        settle(s)
    return source


def test_assassin_targets_nonmatching_colorless_creature_but_does_nothing(cards):
    s = setup(cards)
    target = put(s, 'Ornithopter', 'battlefield', 'p2')
    source = assassin(s, target)
    assert s.state.cards[source.id].tapped
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_assassin_tied_color_can_destroy_and_regeneration_is_forbidden(cards):
    s = setup(cards)
    troll = put(s, 'Mossbridge Troll', 'battlefield', 'p2')
    assassin(s, troll)
    assert s.state.cards[troll.id].zone == 'p2:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_assassin_color_condition_changes_between_activation_and_resolution(cards):
    s = setup(cards)
    target = put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p2')
    bear1 = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    assassin(s, target, finish=False)
    spell(s, 'Thoughtlace', {'U': 1}, [bear1.id])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_barrin_permanent_target_legality_is_not_restricted_to_common_colors(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p1')
    put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p2')
    spell(s, "Barrin's Unmaking", {'U': 1, 'C': 2}, [target.id])
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_barrin_counts_multicolored_permanents_once_in_each_color(cards):
    s = setup(cards)
    target = put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p2')
    put(s, 'Baleful Strix', 'battlefield')
    put(s, 'Baleful Strix', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield')
    spell(s, "Barrin's Unmaking", {'U': 1, 'C': 2}, [target.id])
    assert s.state.cards[target.id].zone == 'p2:hand'
    roundtrip(s)


def test_heroic_aura_counts_its_own_color_and_reacts_to_global_changes(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    aura = spell(s, 'Heroic Defiance', {'W': 1, 'C': 1}, [bear.id])
    assert ch(s, bear).pt == (2, 2)  # Green1 and Aura White1 tie.
    put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p2')
    blue = put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p3')
    assert ch(s, bear).pt == (5, 5)
    act(s, 'p1', type='move', card_ids=[blue.id], to={'zone': 'graveyard'})
    assert ch(s, bear).pt == (2, 2)
    act(s, 'p1', type='set_controller', card_ids=[aura.id], player='p3')
    assert ch(s, bear).pt == (2, 2)
    roundtrip(s)


def call(s, color='Red', player='p2'):
    source = spell(s, 'Call to Arms', {'W': 1, 'C': 1})
    assert s.state.rules.decision is not None
    answer(s, [color])
    if s.state.rules.decision:
        answer(s, [player])
    return s.state.cards[source.id]


def test_call_native_paired_entry_and_global_white_creature_buff(cards):
    from app.rules import chosen

    s = setup(cards)
    put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    own = put(s, 'Savannah Lions', 'battlefield')
    other = put(s, 'Savannah Lions', 'battlefield', 'p3')
    source = call(s)
    assert source.zone == 'p1:battlefield'
    assert source.choices == {'Chosen color': 'Red', 'Chosen opponent': s.state.players['p2'].name}
    assert chosen.player_of(Plan(s.state, 'p1', cards, None), source.id) == 'p2'
    assert ch(s, own).pt == (3, 2) and ch(s, other).pt == (3, 2)
    roundtrip(s)


def test_heroic_current_layer_five_colors_from_painters_servant(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Heroic Defiance', {'W': 1, 'C': 1}, [bear.id])
    put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p2')
    put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p3')
    assert ch(s, bear).pt == (5, 5)
    spell(s, "Painter's Servant", {'C': 2})
    answer(s, ['Blue'])
    assert 'U' in ch(s, bear).colors
    assert ch(s, bear).pt == (2, 2)
    roundtrip(s)


def test_heroic_colorless_host_gets_pump_even_if_all_present_colors_tie(cards):
    s = setup(cards)
    host = put(s, 'Ornithopter', 'battlefield')
    put(s, 'Sol Ring', 'battlefield')
    put(s, 'Sol Ring', 'battlefield', 'p2')
    spell(s, 'Heroic Defiance', {'W': 1, 'C': 1}, [host.id])
    assert ch(s, host).pt == (3, 5)
    roundtrip(s)


@pytest.mark.parametrize('shared', [True, False])
def test_jaded_legal_target_does_not_require_matching_color_until_resolution(cards, shared):
    s = setup(cards)
    put(s, 'Prodigal Pyromancer' if shared else 'Merfolk of the Pearl Trident', 'battlefield')
    bolt = spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p2', finish=False)
    spell(s, 'Jaded Response', {'U': 1, 'G': 1}, [bolt.id])
    assert s.state.cards[bolt.id].zone == 'p2:graveyard'
    assert s.state.players['p3'].life == (40 if shared else 37)
    roundtrip(s)


def test_jaded_rechecks_creature_control_and_spell_current_colors(cards):
    s = setup(cards)
    red = put(s, 'Prodigal Pyromancer', 'battlefield')
    bolt = spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p2', finish=False)
    spell(s, 'Jaded Response', {'U': 1, 'G': 1}, [bolt.id], finish=False)
    act(s, 'p1', type='set_controller', card_ids=[red.id], player='p2')
    settle(s)
    assert s.state.players['p3'].life == 37
    blue = put(s, 'Merfolk of the Pearl Trident', 'battlefield')
    assert 'U' in ch(s, blue).colors
    bolt2 = spell(s, 'Lightning Bolt', {'R': 1}, ['p3'], player='p3', finish=False)
    spell(s, 'Jaded Response', {'U': 1, 'G': 1}, [bolt2.id], finish=False)
    spell(s, 'Thoughtlace', {'U': 1}, [bolt2.id])
    assert s.state.players['p3'].life == 37
    assert s.state.cards[bolt2.id].zone == 'p3:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('fused', [False, True])
def test_jaded_uses_actual_split_face_colors_or_fused_color_union(cards, fused):
    s = setup(cards)
    put(s, 'Savannah Lions', 'battlefield')
    ring = put(s, 'Sol Ring', 'battlefield')
    halo = put(s, 'Runed Halo', 'battlefield')
    if fused:
        wear = spell(s, 'Wear // Tear', {'R': 1, 'W': 1, 'C': 1}, [ring.id, halo.id], player='p2',
                     finish=False, fuse=True, target_counts=[1, 1])
    else:
        wear = spell(s, 'Wear // Tear', {'R': 1, 'C': 1}, [ring.id], player='p2', finish=False, face=0)
    spell(s, 'Jaded Response', {'U': 1, 'G': 1}, [wear.id])
    assert s.state.cards[ring.id].zone == ('p1:battlefield' if fused else 'p1:graveyard')
    assert s.state.cards[halo.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_call_ignores_tokens_and_preserves_chosen_player_after_control_change(cards):
    from app.rules import chosen

    s = setup(cards)
    red = put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    white = put(s, 'Savannah Lions', 'battlefield')
    put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p3')
    put(s, 'Baleful Strix', 'battlefield', 'p3')
    source = call(s)
    act(s, 'p1', type='create_token', player='p2', count=3,
        token={'name': 'Bird', 'type_line': 'Token Creature — Bird', 'colors': ['U'], 'power': '1', 'toughness': '1'})
    assert ch(s, white).pt == (3, 2)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    assert chosen.player_of(Plan(s.state, 'p1', cards, None), source.id) == 'p2'
    assert ch(s, white).pt == (3, 2)
    spell(s, 'Lightning Bolt', {'R': 1}, [red.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert ch(s, white).pt == (2, 1)
    roundtrip(s)


def tie_call(s):
    blue = spell(s, 'Spectral Sailor', {'U': 1}, player='p2', finish=False)
    for _ in range(12):
        if s.state.cards[blue.id].zone == 'p2:battlefield':
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[blue.id].zone == 'p2:battlefield'
    return s.state.cards[blue.id]


def test_call_state_trigger_remains_when_counts_recover_before_resolution(cards):
    s = setup(cards)
    put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    white = put(s, 'Savannah Lions', 'battlefield')
    source = call(s)
    blue = tie_call(s)
    assert ch(s, white).pt == (2, 1)  # Equal counts immediately stop the static buff.
    assert len(s.state.rules.stack) == 1 and source.id in s.state.zones['p1:battlefield']
    act(s, 'p1', type='move', card_ids=[blue.id], to={'zone': 'graveyard'})
    assert ch(s, white).pt == (3, 2)
    assert len(s.state.rules.stack) == 1  # No duplicate state trigger while one is pending.
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_call_countered_state_trigger_retriggers_while_condition_remains(cards):
    s = setup(cards)
    put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    source = call(s)
    tie_call(s)
    assert len(s.state.rules.stack) == 1
    old = next(iter(s.state.rules.stack))
    stifle = spell(s, 'Stifle', {'U': 1}, [old], finish=False)
    for _ in range(12):
        if s.state.cards[stifle.id].zone == 'p1:graveyard':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[stifle.id].zone == 'p1:graveyard'
    assert old not in s.state.rules.stack
    assert len(s.state.rules.stack) == 1 and s.state.cards[source.id].zone == 'p1:battlefield'
    new = next(iter(s.state.rules.stack))
    assert new != old and s.state.rules.stack[new].source_card == source.id
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_call_blink_enters_with_fresh_color_and_opponent_choices(cards):
    from app.rules import chosen

    s = setup(cards)
    put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p3')
    source = call(s)
    old = s.state.rules.object_id(source.id)
    spell(s, 'Flicker of Fate', {'W': 1, 'C': 1}, [source.id])
    answer(s, ['Blue'])
    answer(s, ['p3'])
    assert s.state.rules.object_id(source.id) != old
    current = s.state.cards[source.id]
    assert current.choices['Chosen color'] == 'Blue'
    assert chosen.player_of(Plan(s.state, 'p1', cards, None), source.id) == 'p3'
    assert current.zone == 'p1:battlefield'
    roundtrip(s)


def test_call_pending_old_state_trigger_cannot_sacrifice_blinked_new_object(cards):
    from app.rules import chosen

    s = setup(cards)
    put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p3')
    source = call(s)
    old = s.state.rules.object_id(source.id)
    tie_call(s)
    assert len(s.state.rules.stack) == 1
    spell(s, 'Flicker of Fate', {'W': 1, 'C': 1}, [source.id])
    answer(s, ['Blue'])
    answer(s, ['p3'])
    assert s.state.rules.object_id(source.id) != old
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert chosen.player_of(Plan(s.state, 'p1', cards, None), source.id) == 'p3'
    assert not s.state.rules.stack and s.state.rules.decision is None
    roundtrip(s)


def test_call_copy_chooses_independent_color_and_player(cards):
    from app.rules import chosen

    s = setup(cards)
    put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    blue = put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p3')
    white = put(s, 'Savannah Lions', 'battlefield')
    original = call(s)
    copied = spell(s, 'Copy Enchantment', {'U': 1, 'C': 2})
    answer(s, [original.id])
    answer(s, ['Blue'])
    answer(s, ['p3'])
    assert ch(s, white).pt == (4, 3)
    plan = Plan(s.state, 'p1', cards, None)
    assert chosen.player_of(plan, original.id) == 'p2'
    assert chosen.player_of(plan, copied.id) == 'p3'
    spell(s, 'Lightning Bolt', {'R': 1}, [blue.id])
    assert s.state.cards[original.id].zone == 'p1:battlefield'
    assert s.state.cards[copied.id].zone == 'p1:graveyard'
    assert ch(s, white).pt == (3, 2)
    roundtrip(s)


def test_call_no_colored_chosen_player_permanents_triggers_sacrifice(cards):
    s = setup(cards)
    put(s, 'Sol Ring', 'battlefield', 'p2')
    source = call(s)
    assert source.zone == 'p1:graveyard'
    assert s.state.rules.decision is None
    roundtrip(s)


def test_call_paired_entering_choice_resumes_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    # Identical display names do not turn a player-ID choice into a guessed name.
    act(s, 'p1', type='rename_player', player='p2', name='Opponent')
    act(s, 'p1', type='rename_player', player='p3', name='Opponent')
    put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    put(s, 'Merfolk of the Pearl Trident', 'battlefield', 'p3')
    white = put(s, 'Savannah Lions', 'battlefield')
    source = spell(s, 'Call to Arms', {'W': 1, 'C': 1})
    answer(s, ['Red'])
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'p2', 'p3'}
    assert s.state.cards[source.id].zone == 'stack'  # Neither entry nor the buff happens between choices.
    assert ch(s, white).pt == (2, 1)
    path = tmp_path / 'call-paired-choice.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import chosen
from app.rules.plan import Plan
path, database, source, white = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
assert {o.id for o in d.options} == {'p2', 'p3'}
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['p2']})
for _ in range(12):
    assert s.state.rules.decision is None
    if not s.state.zones['stack']:
        break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('entry failed to finish')
assert s.state.cards[source].choices == {'Chosen color': 'Red', 'Chosen opponent': 'Opponent'}
plan = Plan(s.state, 'p1', repo, None)
assert chosen.player_of(plan, source) == 'p2'
assert plan.ch(s.state.cards[white]).pt == (3, 2)
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), source.id, white.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
    roundtrip(s)
