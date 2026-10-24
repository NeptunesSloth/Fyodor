"""Real Ian exile producers and Kaya loyalty/emblem authorities keep their native scopes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/damage_retention83_cards.json').read_text())
ANCIENT, PATIENT, FURY, VICTORY, CASE = [c['name'] for c in DATA[:5]]
NAMES = [ANCIENT, PATIENT, FURY, VICTORY, CASE]
BIRGI = 'Birgi, God of Storytelling // Harnfel, Horn of Bounty'
DOG = 'Isamaru, Hound of Konda'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['exile_outcomes42_cards.json', 'exile_cast_outcomes45_cards.json',
                     'fight_exile_receipts65_cards.json', 'top_library_authorities69_cards.json',
                     'pooled_casting_authorities71_cards.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())):
            base[c['name']] = card(c['name'], set_code='lc76', number=str(i), **{k: v for k, v in c.items() if k not in {'name', 'set_code'}})
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='lc76', number='a' + str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *[c['name'] for c in DATA], 'Lightning Bolt', 'Disperse', 'Counterspell', 'Sol Ring', 'Forest', 'Serra Angel', 'Serra Angel', 'Serra Angel',
                          'Jacob Hauken, Inspector // Hauken\'s Insight')




@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical83(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'



def board(s, name, pid='p1'):
    c = next(c for c in s.state.cards.values() if c.owner == pid and c.name == name
             and not c.zone.endswith(':battlefield'))
    act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': 'battlefield'})
    return c.id


def bolt(s, target):
    cast(s, 'Lightning Bolt', targets=[target])


def test_ancient_retains_real_damage_and_death_still_exiles_and_makes_ten_tapped_treasures83(cards):
    s = setup(cards)
    source = cast(s, ANCIENT).id
    other = board(s, 'Serra Angel', 'p2')
    bolt(s, source)
    bolt(s, other)
    assert s.state.cards[source].damage == s.state.cards[other].damage == 3
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert s.state.cards[source].damage == 3 and s.state.cards[other].damage == 0
    to_phase(s, 'main1', turn=4)
    settle(s)
    cast(s, 'Murder', targets=[source])
    assert s.state.cards[source].zone == 'p1:exile'
    treasure = [c for c in s.state.cards.values() if c.is_token and c.name == 'Treasure' and c.controller == 'p1']
    assert len(treasure) == 10 and all(c.tapped for c in treasure)
    roundtrip(s)


def test_ancient_redirects_real_damage_to_you_and_other_permanents_into_retained_damage83(cards):
    s = setup(cards)
    source = cast(s, ANCIENT).id
    friend = board(s, 'Serra Angel')
    life = s.state.players['p1'].life
    bolt(s, 'p1')
    bolt(s, friend)
    assert s.state.players['p1'].life == life and s.state.cards[friend].damage == 0
    assert s.state.cards[source].damage == 6
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert s.state.cards[source].damage == 6
    roundtrip(s)


@pytest.mark.parametrize('mode', ['phase_out', 'regenerate'])
def test_official_ancient_phase_out_and_regeneration_remove_damage_normally83(cards, mode):
    s = setup(cards)
    source = cast(s, ANCIENT).id
    bolt(s, source)
    assert s.state.cards[source].damage == 3
    if mode == 'phase_out':
        cast(s, 'Reality Ripple', targets=[source])
        assert s.state.cards[source].zone == 'p1:phased'
        to_phase(s, 'upkeep', turn=2)
        settle(s)
        assert s.state.cards[source].zone == 'p1:phased' and s.state.cards[source].damage == 0
    else:
        cast(s, 'Regenerate', targets=[source])
        cast(s, 'Murder', targets=[source])
        assert s.state.cards[source].zone == 'p1:battlefield' and s.state.cards[source].damage == 0
        assert s.state.cards[source].tapped
    roundtrip(s)


def patient_pool(cards):
    s = setup(cards)
    source = cast(s, PATIENT).id
    own = board(s, 'Serra Angel')
    foe = board(s, 'Serra Angel', 'p2')
    bolt(s, own)
    bolt(s, foe)
    assert s.state.cards[own].damage == s.state.cards[foe].damage == 3
    return s, source, own, foe


def test_patient_current_opponents_only_and_control_change_recomputes_before_cleanup83(cards):
    s, source, own, foe = patient_pool(cards)
    act(s, 'p1', type='set_controller', card_ids=[source], player='p2')
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert s.state.cards[own].damage == 3 and s.state.cards[foe].damage == 0
    roundtrip(s)


def test_native_ability_removal_before_simultaneous_cleanup_turns_off_retention83(cards):
    s, source, own, foe = patient_pool(cards)
    to_phase(s, 'end', turn=1)
    settle(s)
    cast(s, 'Dress Down')
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert s.state.cards[own].damage == s.state.cards[foe].damage == 0
    roundtrip(s)


def test_fury_real_old_wording_etb_deals_four_then_retains_only_opponents_damage83(cards):
    from tests.test_rules_controller_tutors import answer

    s = setup(cards)
    life = s.state.players['p2'].life
    cast(s, FURY)
    answer(s, ['p2'])
    assert s.state.players['p2'].life == life - 4
    own = board(s, 'Serra Angel')
    foe = board(s, 'Serra Angel', 'p2')
    bolt(s, own)
    bolt(s, foe)
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert s.state.cards[own].damage == 0 and s.state.cards[foe].damage == 3
    roundtrip(s)


def test_victory_real_chapter_grants_literal_global_ability_and_damage_accumulates_until_it_leaves83(cards):
    s = setup(cards)
    own = board(s, 'Colossal Dreadmaw')
    foe = board(s, 'Colossal Dreadmaw', 'p2')
    undying = board(s, 'Darksteel Myr')
    source = cast(s, VICTORY).id
    quote = "Damage isn't removed from creatures during cleanup steps."
    assert any(a.text == quote for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source]).abilities)
    assert all(s.state.cards[c].damage == 4 for c in [own, foe, undying])
    to_phase(s, 'main1', turn=4)
    settle(s)
    assert all(s.state.cards[c].damage == 5 for c in [own, foe, undying])
    to_phase(s, 'main1', turn=7)
    settle(s)
    assert s.state.cards[source].zone == 'p1:graveyard'
    assert s.state.cards[own].zone == 'p1:graveyard' and s.state.cards[foe].zone == 'p2:graveyard'
    assert s.state.cards[undying].damage == 6 and s.state.cards[undying].zone == 'p1:battlefield'
    to_phase(s, 'upkeep', turn=8)
    settle(s)
    assert s.state.cards[undying].damage == 0
    roundtrip(s)


def case_pool(cards, *, foreign=False):
    from tests.test_rules_controller_tutors import answer

    s = setup(cards)
    creatures = [board(s, 'Serra Angel', pid) for pid in ['p1', 'p2', 'p3']] if foreign else [board(s, 'Serra Angel') for _ in range(3)]
    source = cast(s, CASE).id
    answer(s, [creatures[0]])
    bolt(s, creatures[1])
    bolt(s, creatures[2])
    assert [s.state.cards[c].damage for c in creatures] == [1, 3, 3]
    return s, source, creatures


def test_case_solves_from_three_actual_current_damaged_creatures_then_native_attack_ability_is_present83(cards):
    s, source, creatures = case_pool(cards)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert 'Solved' in s.state.cards[source].choices
    assert any('Whenever you attack' in a.text for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source]).abilities)
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert [s.state.cards[c].damage for c in creatures] == [1, 3, 3]
    roundtrip(s)


def test_case_intervening_condition_counts_current_marked_damage_not_turn_history83(cards):
    s, source, creatures = case_pool(cards)
    to_phase(s, 'end', turn=1)
    # A real response removes a damaged object after the native solve trigger exists.
    assert s.state.rules.stack
    cast(s, 'Disperse', targets=[creatures[0]])
    assert 'Solved' not in s.state.cards[source].choices
    assert s.state.cards[creatures[0]].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['ancient', 'case_global'])
def test_genuine_fresh_process_preserves_damage_retention_and_current_solve_condition83(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    if mode == 'ancient':
        s = setup(cards)
        source = cast(s, ANCIENT).id
        bolt(s, source)
        creatures = [source]
    else:
        s, source, creatures = case_pool(cards, foreign=True)
    saved = tmp_path / 'cleanup83.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys,json
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.state import GameState
from app.game.session import GameSession
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
source,mode=sys.argv[3:5]
creatures=json.loads(sys.argv[5])
if mode=='case_global':
 assert {s.state.cards[c].controller for c in creatures}=={'p1','p2','p3'}
 to_phase(s,'end',turn=1);settle(s)
 assert 'Solved' in s.state.cards[source].choices
 to_phase(s,'upkeep',turn=2);settle(s)
 assert [s.state.cards[c].damage for c in creatures]==[1,3,3]
else:
 to_phase(s,'upkeep',turn=2);settle(s)
 assert s.state.cards[source].damage==3
roundtrip(s)
r.close()
'''
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source, mode, json.dumps(creatures)],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr
