"""Kicked and unkicked native effect bundles retain caster, target and stack authority."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, split_second
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_table_activation_modifiers52 import game

NAMES = ['Vines of Vastwood', "Urza's Rage", 'Scorching Lava', 'Molten Disaster']


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for filename in ['kicked_spell_outcomes59_cards.json', 'kicked_spell_outcomes59_supports.json']:
        for i, c in enumerate(json.loads((Path(__file__).parent/'fixtures'/filename).read_text())):
            base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', NAMES)
def test_canonical_complete(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def cast(s, name, mana, *, pid='p1', targets=(), kicker=0, x=None, resolve=True):
    wait_priority(s, pid)
    c = put(s, name, 'hand', pid=pid)
    act(s, pid, type='add_mana', player=pid, mana=mana)
    action = dict(type='cast_spell', card_id=c.id, targets=list(targets), kicker=kicker, sources=[])
    if x is not None:
        action['x_value'] = x
    act(s, pid, **action)
    if resolve:
        answer(s)
    return c


@pytest.mark.parametrize('kicked', [0, 1])
def test_vines_protects_opponents_creature_relative_to_caster(cards, kicked):
    s = game(cards, ['Vines of Vastwood', 'Giant Growth'], opponents=['Hill Giant', 'Giant Growth'])
    bear = put(s, 'Hill Giant', 'battlefield', pid='p2')
    cast(s, 'Vines of Vastwood', {'G': 1+kicked}, targets=[bear.id], kicker=kicked)
    ch = Plan(s.state, 'p1', cards, None).ch(bear)
    assert ch.pt == (3+4*kicked, 3+4*kicked) and 'hexproof' not in ch.keywords
    wait_priority(s, 'p2')
    growth = put(s, 'Giant Growth', 'hand', pid='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'G': 1})
    with pytest.raises(ActionError):
        act(s, 'p2', type='cast_spell', card_id=growth.id, targets=[bear.id], sources=[])
    cast(s, 'Giant Growth', {'G': 1}, targets=[bear.id])
    assert Plan(s.state, 'p1', cards, None).ch(bear).pt == (6+4*kicked, 6+4*kicked)
    roundtrip(s)


@pytest.mark.parametrize('kicked', [0, 1])
def test_urza_rage_only_kicked_damage_ignores_prevention(cards, kicked):
    s = game(cards, ["Urza's Rage"], opponents=['Safe Passage'])
    cast(s, 'Safe Passage', {'C': 2, 'W': 1}, pid='p2')
    before = s.state.players['p2'].life
    cast(s, "Urza's Rage", {'C': 2+8*kicked, 'R': 1+kicked}, targets=['p2'], kicker=kicked)
    assert s.state.players['p2'].life == before-(10 if kicked else 0)
    roundtrip(s)


@pytest.mark.parametrize('kicked', [0, 1])
def test_scorching_lava_exile_applies_even_when_initial_damage_prevented(cards, kicked):
    s = game(cards, ['Scorching Lava', 'Terror'], opponents=['Safe Passage', 'Hill Giant'])
    target = put(s, 'Hill Giant', 'battlefield', pid='p2')
    cast(s, 'Safe Passage', {'C': 2, 'W': 1}, pid='p2')
    cast(s, 'Scorching Lava', {'C': 1, 'R': 1+kicked}, targets=[target.id], kicker=kicked)
    assert target.zone == 'p2:battlefield' and target.damage == 0
    cast(s, 'Terror', {'C': 1, 'B': 1}, targets=[target.id])
    assert target.zone == ('p2:exile' if kicked else 'p2:graveyard')
    roundtrip(s)


@pytest.mark.parametrize('kicked', [0, 1])
def test_molten_disaster_actual_stack_split_second_and_native_x_damage(cards, kicked):
    s = game(cards, ['Molten Disaster', 'Forest', 'Staff of Domination'], opponents=['Hill Giant', 'Shivan Dragon', 'Lightning Bolt'])
    forest = put(s, 'Forest', 'battlefield')
    staff = put(s, 'Staff of Domination', 'battlefield')
    ground = put(s, 'Hill Giant', 'battlefield', pid='p2')
    flying = put(s, 'Shivan Dragon', 'battlefield', pid='p2')
    spell = cast(s, 'Molten Disaster', {'C': 2, 'R': 2+kicked}, kicker=kicked, x=2, resolve=False)
    assert bool(split_second.on_stack(s.state, cards)) == bool(kicked)
    before = [s.state.players[p].life for p in ('p1','p2','p3')]
    if kicked:
        act(s, 'p1', type='activate_ability', card_id=forest.id, ability=0)
        assert split_second.on_stack(s.state, cards) is not None
        with pytest.raises(ActionError, match='split second'):
            act(s, 'p1', type='activate_ability', card_id=staff.id, ability=0, sources=[])
        wait_priority(s, 'p2')
        bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
        with pytest.raises(ActionError, match='split second'):
            act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p1'], sources=[])
    answer(s)
    assert spell.zone == 'p1:graveyard' and ground.damage == 2 and flying.damage == 0
    assert [s.state.players[p].life for p in ('p1','p2','p3')] == [x-2 for x in before]
    assert split_second.on_stack(s.state, cards) is None
    roundtrip(s)


def test_copy_of_kicked_molten_keeps_actual_kicker_x_and_split_second(cards):
    s = game(cards, ['Doublecast', 'Molten Disaster'])
    cast(s, 'Doublecast', {'R': 2})
    original = cast(s, 'Molten Disaster', {'C': 2, 'R': 3}, kicker=1, x=2, resolve=False)
    for _ in range(12):
        spells = [cid for cid in s.state.zones['stack'] if s.state.rules.stack.get(cid) is not None
                  and s.state.rules.stack[cid].kind == 'spell']
        if len(spells) == 2:
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    assert len(spells) == 2
    for cid in spells:
        entry = s.state.rules.stack[cid]
        assert entry.kicked == 1 and entry.x == 2
        assert 'split second' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[cid]).keywords
    before = s.state.players['p2'].life
    answer(s)
    assert s.state.players['p2'].life == before-4 and original.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_native_kicked_spell_or_stack_keyword(cards, tmp_path, name):
    import subprocess
    import sys

    from app.rules import kicked_spell_outcomes59
    s = game(cards, [name], opponents=['Hill Giant'])
    target = put(s, 'Hill Giant', 'battlefield', pid='p2')
    spell = put(s, name, 'hand')
    mana = {'G': 2} if name == 'Vines of Vastwood' else {'C': 10, 'R': 2} if name == "Urza's Rage" else {'C': 1, 'R': 2} if name == 'Scorching Lava' else {'C': 2, 'R': 3}
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    action = dict(type='cast_spell', card_id=spell.id, kicker=1, sources=[], targets=[target.id])
    if name == 'Molten Disaster':
        action.update(x_value=2, targets=[])
        act(s, 'p1', **action)
    saved = tmp_path/'game.json'
    saved.write_text(s.state.model_dump_json())
    spec = tmp_path/'spec.json'
    spec.write_text(json.dumps(dict(name=name, action=action, target=target.id)))
    code = '''
import json,sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import split_second
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
spec=json.loads(Path(sys.argv[3]).read_text());target=s.state.cards[spec['target']]
if spec['name']=='Molten Disaster':
 assert split_second.on_stack(s.state,repo)=='Molten Disaster'
else:act(s,'p1',**spec['action'])
answer(s)
if spec['name']=='Vines of Vastwood':
 assert Plan(s.state,'p1',repo,None).ch(target).pt==(7,7)
 assert 'untargetable_by_opponents_of:p1' in Plan(s.state,'p1',repo,None).ch(target).imposed
elif spec['name']=="Urza's Rage":assert target.zone=='p2:graveyard'
elif spec['name']=='Scorching Lava':
 assert target.damage==2
 assert s.state.rules.no_regen
 assert any(r.get('kind')=='exile_if_dies' for r in s.state.rules.replacements)
else:
 assert target.damage==2 and split_second.on_stack(s.state,repo) is None
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), str(spec)],
                            cwd=Path(kicked_spell_outcomes59.__file__).resolve().parents[2], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
