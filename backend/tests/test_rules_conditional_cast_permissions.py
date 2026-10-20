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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/conditional_permission_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='evc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', ['Undead Sprinter', 'Demilich', 'Sproutback Trudge', 'Qasali Ambusher', 'Lightwheel Enhancements'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('speed', [0, 3, 4, 5])
def test_lightwheel_uses_live_max_speed_in_graveyard(cards, speed):
    from app.game.errors import ActionError
    s = table(cards, ['Lightwheel Enhancements', 'Grizzly Bears'])
    target = put(s, 'Grizzly Bears', 'battlefield')
    aura = put(s, 'Lightwheel Enhancements', 'graveyard')
    act(s, 'p1', type='set_resource', player='p1', key='speed', value=speed)
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    if speed < 4:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[target.id])
    else:
        act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[target.id])
        settle(s)
        assert s.state.cards[aura.id].zone.endswith(':battlefield')
    roundtrip(s)


@pytest.mark.parametrize('instant_count', [0, 3, 4])
def test_demilich_additional_four_spell_cards_atomic(cards, instant_count):
    from app.game.errors import ActionError
    s = table(cards, ['Demilich', 'Lightning Bolt', 'Counterspell', 'Divination', 'Ponder', 'Grizzly Bears'])
    source = put(s, 'Demilich', 'graveyard')
    put(s, 'Grizzly Bears', 'graveyard')
    spells = [put(s, name, 'graveyard') for name in ['Lightning Bolt', 'Counterspell', 'Divination', 'Ponder'][:instant_count]]
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 4})
    if instant_count < 4:
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=source.id)
        assert s.state.model_dump_json() == before
    else:
        act(s, 'p1', type='cast_spell', card_id=source.id)
        if s.state.rules.decision is not None:
            pick(s, [o.id for o in s.state.rules.decision.options if o.card_id in {c.id for c in spells}])
        settle(s)
        assert s.state.cards[source.id].zone.endswith(':battlefield')
        assert all(s.state.cards[c.id].zone.endswith(':exile') for c in spells)
    roundtrip(s)


@pytest.mark.parametrize('victim', [None, 'Walking Corpse', 'Grizzly Bears'])
def test_sprinter_requires_actual_non_zombie_death(cards, victim):
    from app.game.errors import ActionError
    s = table(cards, ['Undead Sprinter', 'Lightning Bolt'], ['Walking Corpse', 'Grizzly Bears'])
    source = put(s, 'Undead Sprinter', 'graveyard')
    bolt = put(s, 'Lightning Bolt', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'R': 2})
    if victim is not None:
        target = put(s, victim, 'battlefield', 'p2')
        act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[target.id])
        settle(s)
    if victim != 'Grizzly Bears':
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=source.id)
    else:
        act(s, 'p1', type='cast_spell', card_id=source.id)
        settle(s)
        assert s.state.cards[source.id].counters == {'+1/+1': 1}
    roundtrip(s)


@pytest.mark.parametrize('target,land,allowed', [('p1', None, False), ('p1', 'Forest', False), ('p3', 'Temple Garden', False), ('p1', 'Temple Garden', True)])
def test_qasali_free_flash_requires_attack_on_you_and_both_land_subtypes(cards, target, land, allowed):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import to_phase
    from tests.test_rules_wave30p_combat import attack
    s = table(cards, ['Qasali Ambusher', 'Temple Garden'], ['Grizzly Bears'])
    source = put(s, 'Qasali Ambusher', 'hand')
    if land is not None:
        put(s, land, 'battlefield')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (attacker, target), pid='p2')
    while s.state.rules.priority != 'p1':
        act(s, s.state.rules.priority, type='pass_priority')
    if allowed:
        act(s, 'p1', type='cast_spell', card_id=source.id, free=True)
        settle(s)
        assert s.state.cards[source.id].zone.endswith(':battlefield')
    else:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=source.id, free=True)
    roundtrip(s)


@pytest.mark.parametrize('gain', [False, True])
def test_sproutback_graveyard_end_step_cast_pays_discounted_cost(cards, gain):
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards, ['Sproutback Trudge', 'Healing Salve'])
    source = put(s, 'Sproutback Trudge', 'graveyard')
    if gain:
        salve = put(s, 'Healing Salve', 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
        act(s, 'p1', type='cast_spell', card_id=salve.id, modes=[0], targets=['p1'])
        settle(s)
    to_phase(s, 'end', turn=1)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2, 'C': 4})
    settle(s)
    if gain:
        d = s.state.rules.decision
        assert d is not None and source.id in {o.card_id for o in d.options}
        pick(s, [next(o.id for o in d.options if o.card_id == source.id)])
        settle(s)
        assert s.state.cards[source.id].zone.endswith(':battlefield')
    else:
        assert s.state.rules.decision is None
        assert s.state.cards[source.id].zone.endswith(':graveyard')
    roundtrip(s)



def test_demilich_cold_additional_cost_choice_is_atomic(cards, tmp_path):
    import subprocess
    import sys
    s = table(cards, ['Demilich', 'Lightning Bolt', 'Counterspell', 'Divination', 'Ponder', 'Healing Salve'])
    source = put(s, 'Demilich', 'graveyard')
    fodder = [put(s, name, 'graveyard') for name in ['Lightning Bolt', 'Counterspell', 'Divination', 'Ponder', 'Healing Salve']]
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 4})
    act(s, 'p1', type='cast_spell', card_id=source.id)
    assert s.state.rules.decision is not None
    assert all(s.state.cards[c.id].zone.endswith(':graveyard') for c in fodder)
    save = tmp_path / 'demilich.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
save,db,source,ids=sys.argv[1:]
ids=json.loads(ids)
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[o.id for o in d.options if o.card_id in ids[:4]]})
for _ in range(30):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[source].zone.endswith(':battlefield')
assert all(s.state.cards[c].zone.endswith(':exile') for c in ids[:4])
assert s.state.cards[ids[4]].zone.endswith(':graveyard')
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), source.id, json.dumps([c.id for c in fodder])],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_lightwheel_permission_only_needs_speed_when_cast(cards):
    s = table(cards, ['Lightwheel Enhancements', 'Grizzly Bears'])
    target = put(s, 'Grizzly Bears', 'battlefield')
    aura = put(s, 'Lightwheel Enhancements', 'graveyard')
    act(s, 'p1', type='set_resource', player='p1', key='speed', value=4)
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[target.id])
    act(s, 'p1', type='set_resource', player='p1', key='speed', value=0)
    settle(s)
    assert s.state.cards[aura.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_sprinter_permission_entry_counter_is_not_copied(cards):
    s = table(cards, ['Undead Sprinter', 'Lightning Bolt', 'Double Major'], ['Grizzly Bears'])
    source = put(s, 'Undead Sprinter', 'graveyard')
    bolt = put(s, 'Lightning Bolt', 'hand')
    copy = put(s, 'Double Major', 'hand')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 2, 'B': 1, 'U': 1, 'G': 1})
    act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[target.id])
    settle(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[source.id])
    settle(s)
    entered = [c for c in s.state.cards.values() if c.zone.endswith(':battlefield') and c.name == 'Undead Sprinter']
    assert len(entered) == 2
    assert s.state.cards[source.id].counters == {'+1/+1': 1}
    assert next(c for c in entered if c.id != source.id).counters == {}
    roundtrip(s)


@pytest.mark.parametrize('exile', [False, True])
def test_sproutback_declined_or_departed_trigger_grants_no_later_permission(cards, exile):
    from app.game.errors import ActionError
    from tests.test_rules_wave30m_durations import to_phase
    s = table(cards, ['Sproutback Trudge', 'Healing Salve', "Tormod's Crypt"])
    source = put(s, 'Sproutback Trudge', 'graveyard')
    salve = put(s, 'Healing Salve', 'hand')
    crypt = put(s, "Tormod's Crypt", 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='cast_spell', card_id=salve.id, modes=[0], targets=['p1'])
    settle(s)
    to_phase(s, 'end', turn=1)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2, 'C': 4})
    if exile:
        act(s, 'p1', type='activate_ability', card_id=crypt.id, ability=0, targets=['p1'])
    settle(s)
    if not exile:
        assert s.state.rules.decision is not None
        pick(s, [])
        settle(s)
    assert s.state.rules.decision is None
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id)
    assert s.state.cards[source.id].zone.endswith(':exile' if exile else ':graveyard')
    roundtrip(s)
