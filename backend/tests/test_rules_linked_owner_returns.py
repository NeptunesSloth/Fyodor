"""Linked owner returns keep source incarnations and heterogeneous targets separate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Parallax Wave', 'Parallax Tide', 'Parallax Nexus', 'Gravegouger', 'Angel of Serenity']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/linked_owner_return_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='lor', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    support = ['Naturalize', 'Unsummon', 'Cloudshift', 'Doom Blade', 'Act of Treason', 'Grizzly Bears', 'Llanowar Elves']
    s = table(cards, [name, name, *support], ['Grizzly Bears', 'Llanowar Elves', 'Clone', 'Word of Seizing'], ['Grizzly Bears', 'Llanowar Elves'])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, name, 'hand')
    mana(s, C=20, W=20, U=20, B=20, R=20, G=20)
    return s, source


def resolve_trigger(s, targets):
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=list(targets))
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', ['Parallax Wave', 'Parallax Tide', 'Parallax Nexus'])
def test_native_fading_cost_exiles_and_returns_to_original_owner(cards, name):
    s, source = setup(cards, name)
    name_target = 'Island' if name == 'Parallax Tide' else 'Grizzly Bears'
    target = put(s, name_target, 'hand' if name == 'Parallax Nexus' else 'battlefield', pid='p2')
    if name == 'Parallax Nexus':
        put(s, 'Llanowar Elves', 'hand', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].counters.get('fade') == 5
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
        targets=['p2' if name == 'Parallax Nexus' else target.id])
    if name == 'Parallax Nexus':
        until(s, lambda s: s.state.rules.decision is not None)
        d = s.state.rules.decision
        assert d.player == 'p2'
        assert 'options' not in s.view('p3')['rules']['decision']
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[target.id])
    settle(s)
    assert s.state.cards[source.id].counters['fade'] == 4
    assert s.state.cards[target.id].zone == 'p2:exile'
    removal = put(s, 'Naturalize', 'hand')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    expected = 'p2:hand' if name == 'Parallax Nexus' else 'p2:battlefield'
    assert s.state.cards[target.id].zone == expected and s.state.cards[target.id].controller == 'p2'
    roundtrip(s)


def test_gravegouger_native_exile_and_return_to_owners_graveyard(cards):
    s, source = setup(cards, 'Gravegouger')
    a = put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    b = put(s, 'Llanowar Elves', 'graveyard', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    resolve_trigger(s, [a.id, b.id])
    assert all(s.state.cards[c.id].zone == 'p2:exile' for c in [a, b])
    bounce = put(s, 'Unsummon', 'hand')
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[source.id])
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p2:graveyard' for c in [a, b])
    roundtrip(s)


def test_angel_actual_three_mixed_targets_return_to_multiple_owner_hands(cards):
    s, source = setup(cards, 'Angel of Serenity')
    battlefield = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    graveyard = put(s, 'Llanowar Elves', 'graveyard', pid='p2')
    third = put(s, 'Grizzly Bears', 'graveyard', pid='p3')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    resolve_trigger(s, [battlefield.id, graveyard.id, third.id])
    assert all(s.state.cards[c.id].zone.endswith(':exile') for c in [battlefield, graveyard, third])
    bounce = put(s, 'Unsummon', 'hand')
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[source.id])
    settle(s)
    assert s.state.cards[battlefield.id].zone == s.state.cards[graveyard.id].zone == 'p2:hand'
    assert s.state.cards[third.id].zone == 'p3:hand'
    roundtrip(s)


def test_angel_cannot_target_its_own_battlefield_object_and_can_choose_zero(cards):
    s, source = setup(cards, 'Angel of Serenity')
    put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert source.id not in [o.id for o in d.options]
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[source.id])
    assert s.state.model_dump_json() == before
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(source.id))
    roundtrip(s)


def test_parallax_returns_stolen_creature_to_owner_not_previous_controller(cards):
    s, source = setup(cards, 'Parallax Wave')
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    theft = put(s, 'Act of Treason', 'hand')
    act(s, 'p1', type='cast_spell', card_id=theft.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].controller == 'p1'
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id])
    settle(s)
    removal = put(s, 'Naturalize', 'hand')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:battlefield' and s.state.cards[target.id].controller == 'p2'
    roundtrip(s)


def test_source_leaves_before_exiling_ability_resolves_never_retroactively_returns(cards):
    s, source = setup(cards, 'Parallax Wave')
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id])
    removal = put(s, 'Naturalize', 'hand')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard' and s.state.cards[target.id].zone == 'p2:exile'
    roundtrip(s)


def test_separate_parallax_sources_keep_separate_linked_pools(cards):
    s, first = setup(cards, 'Parallax Wave')
    second = next(c for c in s.state.cards.values() if c.name == 'Parallax Wave' and c.id != first.id)
    act(s, 'p1', type='move', card_ids=[second.id], to={'player': 'p1', 'zone': 'hand'})
    a = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    b = put(s, 'Grizzly Bears', 'battlefield', pid='p3')
    for source, target in [(first, a), (second, b)]:
        act(s, 'p1', type='cast_spell', card_id=source.id)
        settle(s)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[target.id])
        settle(s)
    removal = put(s, 'Naturalize', 'hand')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[first.id])
    settle(s)
    assert s.state.cards[a.id].zone == 'p2:battlefield' and s.state.cards[b.id].zone == 'p3:exile'
    roundtrip(s)


def test_gravegouger_rejects_two_different_graveyards_atomically(cards):
    s, source = setup(cards, 'Gravegouger')
    a = put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    b = put(s, 'Grizzly Bears', 'graveyard', pid='p3')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[a.id, b.id])
    assert s.state.model_dump_json() == before
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[a.id])
    settle(s)
    assert s.state.cards[a.id].zone == 'p2:exile' and s.state.cards[b.id].zone == 'p3:graveyard'
    roundtrip(s)


def test_angel_partial_illegal_mixed_targets_keeps_legal_graveyard_card(cards):
    s, source = setup(cards, 'Angel of Serenity')
    a = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    b = put(s, 'Grizzly Bears', 'graveyard', pid='p3')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[a.id, b.id])
    bounce = put(s, 'Unsummon', 'hand')
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[a.id])
    settle(s)
    assert s.state.cards[a.id].zone == 'p2:hand' and s.state.cards[b.id].zone == 'p3:exile'
    roundtrip(s)


def test_parallax_return_cold_native_clone_entry_choice(cards, tmp_path):
    s, source = setup(cards, 'Parallax Wave')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    to_phase(s, 'main1', turn=2)
    clone = put(s, 'Clone', 'hand', pid='p2')
    mana(s, pid='p2', C=3, U=1)
    act(s, 'p2', type='cast_spell', card_id=clone.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    option = next(o.id for o in d.options if o.card_id == bear.id)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    settle(s)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[clone.id])
    settle(s)
    mana(s, C=1, G=1)
    removal = put(s, 'Naturalize', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    until(s, lambda s: s.state.rules.decision is not None)
    assert s.state.rules.decision.player == 'p2'
    roundtrip(s)
    saved = tmp_path / 'linked-return-entry.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
saved,db,bear,clone=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
d=s.state.rules.decision
option=next(o.id for o in d.options if o.card_id==bear)
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[option]})
for _ in range(20):
 if not s.state.zones.get('stack'):break
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[clone].zone=='p2:battlefield' and s.state.cards[clone].controller=='p2'
assert Plan.view(s.state,'p2',repo).ch(s.state.cards[clone]).name=='Grizzly Bears'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), bear.id, clone.id],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_nexus_source_leaves_before_hand_exile_is_not_retroactively_returned(cards):
    s, source = setup(cards, 'Parallax Nexus')
    target = put(s, 'Grizzly Bears', 'hand', pid='p2')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=['p2'])
    removal = put(s, 'Naturalize', 'hand')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard' and s.state.cards[target.id].zone == 'p2:exile'
    roundtrip(s)


def test_nexus_source_control_changes_keep_original_ability_link_and_card_owner(cards):
    s, source = setup(cards, 'Parallax Nexus')
    target = put(s, 'Grizzly Bears', 'hand', pid='p3')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    original_oid = s.state.rules.object_id(source.id)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=['p3'])
    theft = put(s, 'Word of Seizing', 'hand', pid='p2')
    mana(s, pid='p2', C=3, R=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=theft.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].controller == 'p2'
    assert s.state.rules.exiled_with[original_oid] == [s.state.rules.object_id(target.id)]
    removal = put(s, 'Naturalize', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert s.state.cards[target.id].zone == 'p3:hand'
    roundtrip(s)


def test_nexus_cold_private_hand_choice_keeps_link_flag(cards, tmp_path):
    s, source = setup(cards, 'Parallax Nexus')
    target = put(s, 'Grizzly Bears', 'hand', pid='p2')
    put(s, 'Llanowar Elves', 'hand', pid='p2')
    removal = put(s, 'Naturalize', 'hand')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=['p2'])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == 'p2' and d.resume['link']
    assert 'options' not in s.view('p3')['rules']['decision']
    saved = tmp_path / 'nexus-hand-choice.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved,db,source,target,removal=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[target]})
for _ in range(12):
 if not s.state.zones.get('stack') and s.state.rules.priority=='p1':break
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.rules.exiled_with[s.state.rules.object_id(source)]==[s.state.rules.object_id(target)]
s.perform('p1',{'type':'cast_spell','card_id':removal,'targets':[source]})
for _ in range(20):
 if not s.state.zones.get('stack'):break
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[target].zone=='p2:hand'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, target.id, removal.id],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_angel_own_graveyard_card_is_legal_when_it_dies_before_trigger_targets(cards):
    s = table(cards, ['Angel of Serenity'], ['Dread of Night'] * 6, [])
    for permanent in [c for c in s.state.cards.values() if c.name == 'Dread of Night']:
        act(s, 'p2', type='move', card_ids=[permanent.id], to={'player': 'p2', 'zone': 'battlefield'})
    source = put(s, 'Angel of Serenity', 'hand')
    mana(s, C=4, W=3)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    until(s, lambda s: s.state.rules.decision is not None and any(o.id == source.id for o in s.state.rules.decision.options))
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone in ('p1:exile', 'p1:hand')
    roundtrip(s)
