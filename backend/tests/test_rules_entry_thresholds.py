"""Entry values bind payment objects, draw history, and a chosen opponent."""
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
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/entry_threshold_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='evc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Apocalypse Hydra', 'Dust Animus', 'Grimdancer'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('x', [0, 1, 4, 5, 7])
def test_apocalypse_actual_announced_x_and_threshold(cards, x):
    s = table(cards, ['Apocalypse Hydra'])
    obj = put(s, 'Apocalypse Hydra', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'G': 1, 'C': x})
    act(s, 'p1', type='cast_spell', card_id=obj.id, x_value=x)
    settle(s)
    if x:
        assert s.state.cards[obj.id].counters == {'+1/+1': x * (2 if x >= 5 else 1)}
    else:
        assert s.state.cards[obj.id].zone.endswith(':graveyard')
    roundtrip(s)


@pytest.mark.parametrize('land_count,tap,expected', [(4, 0, False), (5, 0, True), (5, 1, False), (6, 1, True)])
def test_dust_untapped_land_threshold_applies_both_counter_kinds(cards, land_count, tap, expected):
    s = table(cards, ['Dust Animus'])
    lands = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest'][:land_count]
    for c in lands:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
    for c in lands[:tap]:
        act(s, 'p1', type='tap', card_ids=[c.id], tapped=True)
    obj = put(s, 'Dust Animus', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=obj.id)
    settle(s)
    assert s.state.cards[obj.id].counters == ({'+1/+1': 2, 'lifelink': 1} if expected else {})
    roundtrip(s)


@pytest.mark.parametrize('pair', ['menace + deathtouch', 'menace + lifelink', 'deathtouch + lifelink'])
def test_grimdancer_chooses_two_distinct_native_keyword_counters(cards, pair):
    from app.rules.plan import Plan
    s = table(cards, ['Grimdancer'])
    obj = put(s, 'Grimdancer', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=obj.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    pick(s, [next(o.id for o in d.options if o.label == pair or o.id == pair)])
    settle(s)
    assert s.state.cards[obj.id].counters == {k: 1 for k in pair.split(' + ')}
    assert set(pair.split(' + ')) <= Plan(s.state, 'p1', cards, None).ch(s.state.cards[obj.id]).keywords
    roundtrip(s)


def test_dust_does_not_count_itself_as_a_land_under_ashaya(cards):
    s = table(cards, ['Dust Animus', 'Ashaya, Soul of the Wild'])
    lands = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest'][:3]
    for c in lands:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
    put(s, 'Ashaya, Soul of the Wild', 'battlefield')
    obj = put(s, 'Dust Animus', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=obj.id)
    settle(s)
    assert s.state.cards[obj.id].counters == {}
    roundtrip(s)


def test_apocalypse_copy_retains_original_x_and_threshold(cards):
    s = table(cards, ['Apocalypse Hydra', 'Double Major', 'Doubling Season'])
    put(s, 'Doubling Season', 'battlefield')
    obj = put(s, 'Apocalypse Hydra', 'hand')
    copy = put(s, 'Double Major', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'G': 2, 'U': 1, 'C': 5})
    act(s, 'p1', type='cast_spell', card_id=obj.id, x_value=5)
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[obj.id])
    settle(s)
    entered = [c for c in s.state.cards.values() if c.zone.endswith(':battlefield') and c.name == 'Apocalypse Hydra']
    assert len(entered) == 2  # A resolving spell copy's token is not created (111.12).
    assert all(c.counters == {'+1/+1': 20} for c in entered)
    roundtrip(s)


def test_grimdancer_pair_choice_cold_resume(cards, tmp_path):
    import subprocess
    import sys
    s = table(cards, ['Grimdancer'])
    obj = put(s, 'Grimdancer', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=obj.id)
    settle(s)
    save = tmp_path / 'grimdancer.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,obj=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
option=next(o.id for o in d.options if 'menace + lifelink' in (o.label,o.id))
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[option]})
assert s.state.cards[obj].counters=={'menace':1,'lifelink':1}
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), obj.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('name,mana,x', [('Dust Animus', {'W': 1, 'C': 1}, None), ('Grimdancer', {'B': 2, 'C': 1}, None), ('Apocalypse Hydra', {'R': 1, 'G': 1, 'C': 5}, 5)])
def test_entry_counter_replacements_obey_solemnity(cards, name, mana, x):
    s = table(cards, [name, 'Solemnity'])
    put(s, 'Solemnity', 'battlefield')
    lands = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest'][:5]
    for c in lands:
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'battlefield'})
    obj = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=obj.id, **({'x_value': x} if x is not None else {}))
    settle(s)
    if s.state.rules.decision is not None:
        pick(s, [s.state.rules.decision.options[0].id])
        settle(s)
    assert s.state.cards[obj.id].counters == {}
    if name == 'Apocalypse Hydra':
        assert s.state.cards[obj.id].zone.endswith(':graveyard')
    roundtrip(s)
