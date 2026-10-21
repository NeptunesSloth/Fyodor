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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/cast_entry_permission_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='evc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Intrepid Paleontologist', 'Hundred-Battle Veteran', 'Worldheart Phoenix', 'Osteomancer Adept', 'Risen Executioner'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,mana,counters', [
    ('Hundred-Battle Veteran', {'B': 1, 'C': 3}, {'finality': 1}),
    ('Worldheart Phoenix', {'W': 1, 'U': 1, 'B': 1, 'R': 1, 'G': 1}, {'+1/+1': 2}),
])
@pytest.mark.parametrize('graveyard', [False, True])
def test_permission_entry_rider_actual_cast(cards, name, mana, counters, graveyard):
    s = table(cards, [name])
    obj = put(s, name, 'graveyard' if graveyard else 'hand')
    if not graveyard:
        mana = {'R': 1, 'C': 3} if name == 'Worldheart Phoenix' else mana
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=obj.id)
    settle(s)
    assert s.state.cards[obj.id].zone.endswith(':battlefield')
    assert s.state.cards[obj.id].counters == (counters if graveyard else {})
    roundtrip(s)


@pytest.mark.parametrize('others', [0, 1, 3])
def test_risen_graveyard_cost_counts_other_creature_cards(cards, others):
    from app.game.errors import ActionError
    from tests.game_helpers import mana_pool
    s = table(cards, ['Risen Executioner', 'Grizzly Bears', 'Hill Giant', 'Air Elemental'])
    obj = put(s, 'Risen Executioner', 'graveyard')
    for name in ['Grizzly Bears', 'Hill Giant', 'Air Elemental'][:others]:
        put(s, name, 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 2 + max(0, others - 1)})
    if others:
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=obj.id)
        assert s.state.model_dump_json() == before
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='cast_spell', card_id=obj.id)
    settle(s)
    assert s.state.cards[obj.id].zone.endswith(':battlefield')
    assert sum(mana_pool(s, 'p1').values()) == 0
    roundtrip(s)


def test_osteomancer_requires_forage_and_preserves_finality(cards):
    from app.game.errors import ActionError
    s = table(cards, ['Osteomancer Adept', 'Grizzly Bears', 'Forest', 'Island', 'Mountain'])
    adept = put(s, 'Osteomancer Adept', 'battlefield')
    s.state.rules.controlled_since[adept.id].turn = 0
    bear = put(s, 'Grizzly Bears', 'graveyard')
    act(s, 'p1', type='activate_ability', card_id=adept.id, ability=1)
    settle(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id)
    fodder = [put(s, name, 'graveyard') for name in ['Forest', 'Island', 'Mountain']]
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    d = s.state.rules.decision
    assert d is not None
    assert bear.id not in {o.card_id for o in d.options}
    pick(s, [o.id for o in d.options if o.card_id in {c.id for c in fodder}])
    settle(s)
    assert all(s.state.cards[c.id].zone.endswith(':exile') for c in fodder)
    assert s.state.cards[bear.id].counters == {'finality': 1}
    roundtrip(s)


def test_intrepid_linked_owned_dinosaur_permission(cards):
    s = table(cards, ['Intrepid Paleontologist', 'Carnage Tyrant', 'Grizzly Bears'])
    source = put(s, 'Intrepid Paleontologist', 'battlefield')
    dino = put(s, 'Carnage Tyrant', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[dino.id])
    settle(s)
    assert s.state.cards[dino.id].zone.endswith(':exile')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2, 'C': 4})
    act(s, 'p1', type='cast_spell', card_id=dino.id)
    settle(s)
    assert s.state.cards[dino.id].counters == {'finality': 1}
    roundtrip(s)


@pytest.mark.parametrize('name,mana,counters', [
    ('Hundred-Battle Veteran', {'B': 1, 'U': 1, 'G': 1, 'C': 3}, {'finality': 1}),
    ('Worldheart Phoenix', {'W': 1, 'U': 2, 'B': 1, 'R': 1, 'G': 2}, {'+1/+1': 2}),
])
def test_permission_consequent_is_not_copied_with_spell(cards, name, mana, counters):
    s = table(cards, [name, 'Double Major'])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    original = put(s, name, 'graveyard')
    copier = put(s, 'Double Major', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=original.id)
    act(s, 'p1', type='cast_spell', card_id=copier.id, targets=[original.id])
    settle(s)
    entered = [c for c in s.state.cards.values() if c.zone.endswith(':battlefield') and c.name == name]
    assert len(entered) == 2
    assert s.state.cards[original.id].counters == counters
    assert next(c for c in entered if c.id != original.id).counters == {}
    roundtrip(s)


def test_risen_cost_locks_before_mana_ability_adds_graveyard_creature(cards):
    from tests.game_helpers import mana_pool
    s = table(cards, ['Risen Executioner', "Ashnod's Altar", 'Grizzly Bears'])
    risen = put(s, 'Risen Executioner', 'graveyard')
    altar = put(s, "Ashnod's Altar", 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2})
    act(s, 'p1', type='cast_spell', card_id=risen.id)
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0)
    if s.state.rules.decision is not None and s.state.rules.decision.kind == 'choose_cards':
        pick(s, [bear.id])
    if s.state.rules.decision is not None:
        pick(s, ['pay'])
    settle(s)
    assert s.state.cards[bear.id].zone.endswith(':graveyard')
    assert s.state.cards[risen.id].zone.endswith(':battlefield')
    assert sum(mana_pool(s, 'p1').values()) == 0
    roundtrip(s)


@pytest.mark.parametrize('name,mana', [('Hundred-Battle Veteran', {'B': 1, 'C': 3}), ('Worldheart Phoenix', {'W': 1, 'U': 1, 'B': 1, 'R': 1, 'G': 1})])
def test_permission_counters_obey_solemnity(cards, name, mana):
    s = table(cards, [name, 'Solemnity'])
    put(s, 'Solemnity', 'battlefield')
    obj = put(s, name, 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='cast_spell', card_id=obj.id)
    settle(s)
    assert s.state.cards[obj.id].counters == {}
    roundtrip(s)


def test_forage_permission_cold_resume(cards, tmp_path):
    import subprocess
    import sys
    s = table(cards, ['Osteomancer Adept', 'Grizzly Bears', 'Forest', 'Island', 'Mountain'])
    adept = put(s, 'Osteomancer Adept', 'battlefield')
    s.state.rules.controlled_since[adept.id].turn = 0
    bear = put(s, 'Grizzly Bears', 'graveyard')
    fodder = [put(s, name, 'graveyard') for name in ['Forest', 'Island', 'Mountain']]
    act(s, 'p1', type='activate_ability', card_id=adept.id, ability=1)
    settle(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    assert s.state.rules.decision is not None
    save = tmp_path / 'forage.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,bear,fodder=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
ids=set(json.loads(fodder))
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[o.id for o in d.options if o.card_id in ids]})
for _ in range(30):
 if not s.state.zones.get('stack'): break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[bear].counters=={'finality':1}
assert all(s.state.cards[cid].zone.endswith(':exile') for cid in ids)
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), bear.id, json.dumps([c.id for c in fodder])],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('wrong_owner,wrong_type', [(True, False), (False, True)])
def test_intrepid_does_not_grant_other_owned_or_nondinosaur_cards(cards, wrong_owner, wrong_type):
    from app.game.errors import ActionError
    s = table(cards, ['Intrepid Paleontologist', 'Grizzly Bears'], ['Carnage Tyrant'])
    source = put(s, 'Intrepid Paleontologist', 'battlefield')
    obj = put(s, 'Carnage Tyrant' if wrong_owner else 'Grizzly Bears', 'graveyard', 'p2' if wrong_owner else 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[obj.id])
    settle(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2, 'C': 4})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=obj.id)
    assert s.state.cards[obj.id].zone.endswith(':exile')
    roundtrip(s)


def test_osteomancer_food_branch_and_source_departure(cards):
    from tests.test_rules_conditionals import creature
    s = table(cards, ['Osteomancer Adept', 'Grizzly Bears'])
    adept = put(s, 'Osteomancer Adept', 'battlefield')
    s.state.rules.controlled_since[adept.id].turn = 0
    bear = put(s, 'Grizzly Bears', 'graveyard')
    food = creature(s, 'p1', 'Food', pt='0/0', type_line='Token Artifact — Food')
    act(s, 'p1', type='activate_ability', card_id=adept.id, ability=1)
    settle(s)
    act(s, 'p1', type='move', card_ids=[adept.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=bear.id)
    if s.state.rules.decision is not None:
        pick(s, [food.id])
    settle(s)
    assert food.id not in s.state.cards
    assert s.state.cards[bear.id].counters == {'finality': 1}
    roundtrip(s)


def test_finality_from_permission_exiles_actual_death(cards):
    s = table(cards, ['Hundred-Battle Veteran'], ['Lightning Bolt'])
    obj = put(s, 'Hundred-Battle Veteran', 'graveyard')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'C': 3})
    act(s, 'p1', type='cast_spell', card_id=obj.id)
    settle(s)
    while s.state.rules.priority != 'p2':
        act(s, s.state.rules.priority, type='pass_priority')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[obj.id])
    settle(s)
    assert s.state.cards[obj.id].zone.endswith(':exile')
    roundtrip(s)


def test_risen_hand_cast_does_not_charge_graveyard_permission_cost(cards):
    from tests.game_helpers import mana_pool
    s = table(cards, ['Risen Executioner', 'Grizzly Bears', 'Hill Giant'])
    obj = put(s, 'Risen Executioner', 'hand')
    for name in ['Grizzly Bears', 'Hill Giant']:
        put(s, name, 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=obj.id)
    settle(s)
    assert s.state.cards[obj.id].zone.endswith(':battlefield')
    assert sum(mana_pool(s, 'p1').values()) == 0
    roundtrip(s)
