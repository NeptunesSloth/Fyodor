"""Canonical same-name searches preserve subjects and native private decisions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_banding import attack_step
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_player_choices import assert_observer_sees_only_who
from tests.test_rules_shared_damage_choices import table

NAMES = ['Test of Talents', 'The End', 'Necromentia', 'Lobotomy', 'Shimian Specter']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/name_search_family_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='nsf', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name, donor='Grizzly Bears'):
    s = table(cards, [name, 'Unsummon', 'Grizzly Bears', 'Act of Treason'],
              [donor] * 4 + ['Parallel Lives', 'Doubling Season', 'Stinkweed Imp', 'Chatterfang, Squirrel General', 'Divine Visitation'], [])
    for pid in ['p1', 'p2', 'p3']:
        act(s, pid, type='set_prefs', hold_priority=True)
    source = put(s, name, 'hand')
    copies = [c for c in s.state.cards.values() if c.name == donor and c.owner == 'p2']
    for c, z in zip(copies, ['hand', 'graveyard', 'library', 'battlefield'], strict=True):
        act(s, 'p2', type='move', card_ids=[c.id], to={'player': 'p2', 'zone': z})
    return s, source, copies


def drive(s, name='Grizzly Bears', take=None):
    searches = []
    for _ in range(90):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get('stack'):
                return searches
            act(s, s.state.rules.priority, type='pass_priority')
        elif d.options and d.options[0].id == '__name__':
            act(s, d.player, type='choose', decision_id=d.id, name=name)
        elif d.resume and d.resume.get('step') == 'name_search':
            searches.append(d)
            assert_observer_sees_only_who(s, 'p3', 'Alice')
            ids = [o.id for o in d.options]
            roundtrip(s)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=ids if take is None else ids[:take])
        elif d.resume and d.resume.get('step') == 'choose_from_hand':
            selected = next((o.id for o in d.options if o.label == name), d.options[0].id if d.options else None)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[selected] if selected else [])
        else:
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options][:d.min_choices])
    raise AssertionError('did not finish')


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('life,pool', [(40, {'C': 2, 'B': 2}), (5, {'B': 2})])
def test_the_end_actual_exile_search_draw_and_native_reduced_cost(cards, life, pool):
    s, source, copies = setup(cards, 'The End')
    act(s, 'p1', type='set_life', player='p1', value=life)
    mana(s, **pool)
    hand = len(s.state.zones['p2:hand'])
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[copies[-1].id])
    decisions = drive(s)
    assert len(decisions) == 1 and decisions[0].player == 'p1'
    assert all(s.state.cards[c.id].zone == 'p2:exile' for c in copies)
    assert len(s.state.zones['p2:hand']) == hand
    roundtrip(s)


def test_necromentia_makes_zombies_only_for_hand_cards(cards):
    s, source, copies = setup(cards, 'Necromentia')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
    drive(s)
    assert all(s.state.cards[c.id].zone == 'p2:exile' for c in copies[:3])
    assert s.state.cards[copies[-1].id].zone == 'p2:battlefield'
    zombies = [c for c in s.state.cards.values() if c.name == 'Zombie' and c.zone == 'p2:battlefield']
    assert len(zombies) == 1 and zombies[0].token.power == '2'
    roundtrip(s)


@pytest.mark.parametrize('donor', ['Grizzly Bears', 'Wasteland'])
def test_lobotomy_native_hand_choice_search_and_fail_to_find(cards, donor):
    s, source, copies = setup(cards, 'Lobotomy', donor=donor)
    mana(s, C=2, U=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
    found = drive(s, name=donor, take=2)
    assert len(found) == 1 and len(found[0].options) == 3
    assert sum(s.state.cards[c.id].zone == 'p2:exile' for c in copies) == 2
    roundtrip(s)


def test_test_of_talents_counters_then_searches_original_spell_controller_and_draws(cards):
    s, source, copies = setup(cards, 'Test of Talents', donor='Counterspell')
    # A second copy in hand will be exiled and replaced by exactly one draw.
    act(s, 'p2', type='move', card_ids=[copies[1].id], to={'player': 'p2', 'zone': 'hand'})
    bear = put(s, 'Grizzly Bears', 'battlefield')
    bounce = put(s, 'Unsummon', 'hand')
    mana(s, C=1, U=2)
    mana(s, pid='p2', U=2)
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[bear.id])
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=copies[0].id, targets=[bounce.id])
    wait_priority(s, 'p1')
    hand = len(s.state.zones['p2:hand'])
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[copies[0].id])
    drive(s, name='Counterspell')
    assert all(s.state.cards[c.id].zone == 'p2:exile' for c in copies[:3])
    assert len(s.state.zones['p2:hand']) == hand
    assert s.state.cards[bear.id].zone == 'p1:hand'
    roundtrip(s)


def test_shimian_actual_combat_trigger_uses_damaged_players_hand(cards):
    s, source, copies = setup(cards, 'Shimian Specter')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    attack_step(s)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume is not None
          and s.state.rules.decision.resume.get('step') == 'choose_from_hand')
    found = drive(s)
    assert len(found) == 1 and found[0].resume['pid'] == 'p2'
    assert all(s.state.cards[c.id].zone == 'p2:exile' for c in copies[:3])
    roundtrip(s)


def test_the_end_searches_stolen_permanents_controller_not_owner(cards):
    s, source, copies = setup(cards, 'The End')
    theft = put(s, 'Act of Treason', 'hand')
    own = put(s, 'Grizzly Bears', 'hand')
    mana(s, C=4, R=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=theft.id, targets=[copies[-1].id])
    drive(s)
    assert s.state.cards[copies[-1].id].controller == 'p1'
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[copies[-1].id])
    decisions = drive(s)
    assert decisions[0].resume['pid'] == 'p1'
    assert s.state.cards[own.id].zone == 'p1:exile'
    assert s.state.cards[copies[0].id].zone == 'p2:hand'
    roundtrip(s)


def test_lobotomy_empty_eligible_hand_skips_card_dependent_search(cards):
    s, source, copies = setup(cards, 'Lobotomy')
    act(s, 'p2', type='move', card_ids=[copies[0].id], to={'player': 'p2', 'zone': 'graveyard'})
    mana(s, C=2, U=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
    assert drive(s) == []
    assert all(s.state.cards[c.id].zone != 'p2:exile' for c in copies)
    roundtrip(s)


@pytest.mark.parametrize('stage', ['hand', 'search'])
def test_lobotomy_cold_pending_native_choices(cards, tmp_path, stage):
    s, source, copies = setup(cards, 'Lobotomy')
    mana(s, C=2, U=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume is not None
          and s.state.rules.decision.resume.get('step') == 'choose_from_hand')
    if stage == 'search':
        d = s.state.rules.decision
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[copies[0].id])
        assert s.state.rules.decision.resume['step'] == 'name_search'
    saved = tmp_path / f'name-search-{stage}.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved,db,*copies=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
for _ in range(30):
 d=s.state.rules.decision
 if d is not None:
  ids=[o.id for o in d.options]
  if d.resume['step']=='choose_from_hand':ids=[copies[0]]
  s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':ids})
 elif not s.state.zones.get('stack'):break
 else:s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert all(s.state.cards[c].zone=='p2:exile' for c in copies)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), *[c.id for c in copies[:3]]],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_uncounterable_target_still_allows_test_of_talents_search(cards):
    s, source, copies = setup(cards, 'Test of Talents', donor='Last Word')
    act(s, 'p2', type='move', card_ids=[copies[1].id], to={'player': 'p2', 'zone': 'hand'})
    bear = put(s, 'Grizzly Bears', 'battlefield')
    bounce = put(s, 'Unsummon', 'hand')
    mana(s, C=1, U=2)
    mana(s, pid='p2', C=1, U=3)
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[bear.id])
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=copies[0].id, targets=[bounce.id])
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[copies[0].id])
    found = drive(s, name='Last Word')
    assert len(found) == 1
    assert s.state.cards[copies[0].id].zone == 'p2:graveyard'
    assert all(s.state.cards[c.id].zone == 'p2:exile' for c in copies[1:3])
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_hand_exile_draw_uses_native_dredge_pause(cards):
    s, source, copies = setup(cards, 'The End')
    imp = put(s, 'Stinkweed Imp', 'graveyard', pid='p2')
    mana(s, C=2, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[copies[-1].id])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume is not None
          and s.state.rules.decision.resume.get('step') == 'name_search')
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and any(o.id == 'decline' for o in d.options)
    roundtrip(s)
    library = len(s.state.zones['p2:library'])
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['o0'])
    drive(s)
    assert s.state.cards[imp.id].zone == 'p2:hand'
    assert len(s.state.zones['p2:library']) == library - 5
    roundtrip(s)


@pytest.mark.parametrize('cold', [False, True])
def test_necromentia_native_token_replacement_choice_resume(cards, tmp_path, cold):
    s, source, _ = setup(cards, 'Necromentia')
    put(s, 'Chatterfang, Squirrel General', 'battlefield', pid='p2')
    put(s, 'Divine Visitation', 'battlefield', pid='p2')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.options
          and s.state.rules.decision.options[0].id == '__name__')
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, name='Grizzly Bears')
    d = s.state.rules.decision
    assert d.resume['step'] == 'name_search'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
    assert s.state.rules.decision is not None and s.state.rules.decision.player == 'p2'
    roundtrip(s)
    if cold:
        saved = tmp_path / 'name-search-tokens.json'
        saved.write_text(s.state.model_dump_json())
        code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved,db=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
for _ in range(30):
 d=s.state.rules.decision
 if d is not None:s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[d.options[0].id]})
 elif not s.state.zones.get('stack'):break
 else:s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert sum(c.quantity for c in s.state.cards.values() if c.is_token and c.zone=='p2:battlefield')==2
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
        result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
    drive(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p2:battlefield']
    assert sum(c.quantity for c in tokens) == 2
    roundtrip(s)
