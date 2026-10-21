"""Native kicker alternatives and resolution-time follow-ups."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/kicked_rider_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='evc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Joint Exploration', "Zuko's Conviction", 'Reclaim the Wastes', 'Tribute to Urborg', 'Chocobo Kick']


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def cast(s, name, kicked, targets=()):
    source = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 3, 'U': 3, 'B': 3, 'C': 8})
    act(s, 'p1', type='cast_spell', card_id=source.id, kicker=int(kicked), targets=list(targets),
        **({'target_counts': [1, 1]} if len(targets) == 2 else {}))
    settle(s)
    return source


@pytest.mark.parametrize('kicked', [False, True])
def test_zuko_alternate_return_uses_same_graveyard_target(cards, kicked):
    s = table(cards, ["Zuko's Conviction", 'Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'graveyard')
    cast(s, "Zuko's Conviction", kicked, [bear.id])
    assert s.state.cards[bear.id].zone == ('p1:battlefield' if kicked else 'p1:hand')
    assert s.state.cards[bear.id].tapped == kicked
    roundtrip(s)


@pytest.mark.parametrize('kicked', [False, True])
def test_tribute_additional_reduction_counts_actual_graveyard_spells(cards, kicked):
    from app.rules.plan import Plan
    from app.rules.sba import power, toughness
    s = table(cards, ['Tribute to Urborg', 'Lightning Bolt', 'Reclaim the Wastes'], ['Air Elemental'])
    creature = put(s, 'Air Elemental', 'battlefield', 'p2')
    put(s, 'Lightning Bolt', 'graveyard')
    put(s, 'Reclaim the Wastes', 'graveyard')
    source = cast(s, 'Tribute to Urborg', kicked, [creature.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    if kicked:
        assert s.state.cards[creature.id].zone == 'p2:graveyard'
    else:
        plan = Plan(s.state, 'p1', cards, None)
        ch = plan.ch(s.state.cards[creature.id])
        assert (power(s.state.cards[creature.id], ch), toughness(s.state.cards[creature.id], ch)) == (2, 2)
    roundtrip(s)


@pytest.mark.parametrize('kicked', [False, True])
def test_reclaim_searches_once_with_correct_maximum(cards, kicked):
    s = table(cards, ['Reclaim the Wastes'])
    cast(s, 'Reclaim the Wastes', kicked)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'search'
    assert d.max_choices == (2 if kicked else 1)
    chosen = [o.id for o in d.options[:d.max_choices]]
    pick(s, chosen)
    settle(s)
    assert all(s.state.cards[c].zone == 'p1:hand' for c in chosen)
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('kicked,accept', [(False, False), (True, False), (True, True)])
def test_joint_mandatory_scry_draw_precedes_optional_land(cards, kicked, accept):
    s = table(cards, ['Joint Exploration', 'Forest'])
    land = put(s, 'Forest', 'hand')
    cast(s, 'Joint Exploration', kicked)
    before = len(s.state.zones['p1:hand'])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'look'
    pick(s, [])
    settle(s)
    # The draw has already happened before any optional kicker decision.
    assert len(s.state.zones['p1:hand']) == before + 1
    if kicked:
        d = s.state.rules.decision
        assert d is not None
        pick(s, ['yes' if accept else 'no'])
        settle(s)
        if accept:
            pick(s, [land.id])
            settle(s)
    assert s.state.cards[land.id].zone == ('p1:battlefield' if accept else 'p1:hand')
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('kicked', [False, True])
def test_chocobo_uses_creature_damage_source_and_paid_return_cost(cards, kicked):
    s = table(cards, ['Chocobo Kick', 'Grizzly Bears', 'Forest'], ['Air Elemental'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    land = put(s, 'Forest', 'battlefield')
    enemy = put(s, 'Air Elemental', 'battlefield', 'p2')
    cast(s, 'Chocobo Kick', kicked, [bear.id, enemy.id])
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert land.id in {o.id for o in d.options}
        pick(s, [land.id])
        settle(s)
    assert s.state.cards[land.id].zone == ('p1:hand' if kicked else 'p1:battlefield')
    assert s.state.cards[enemy.id].zone == ('p2:graveyard' if kicked else 'p2:battlefield')
    if not kicked:
        assert s.state.cards[enemy.id].damage == 2
    roundtrip(s)


def test_zuko_spell_copy_retains_paid_kicker(cards):
    s = table(cards, ["Zuko's Conviction", 'Reverberate', 'Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'graveyard')
    source = put(s, "Zuko's Conviction", 'hand')
    copy = put(s, 'Reverberate', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'R': 2, 'C': 4})
    act(s, 'p1', type='cast_spell', card_id=source.id, kicker=1, targets=[bear.id])
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[source.id])
    settle(s)
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert 'keep' in {o.id for o in d.options}
        pick(s, ['keep'])
        settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].tapped
    roundtrip(s)


def test_tribute_counts_spells_at_resolution_and_excludes_itself(cards):
    from app.rules.plan import Plan
    s = table(cards, ['Tribute to Urborg', 'Lightning Bolt', 'Reclaim the Wastes', 'Shock'], ['Colossal Dreadmaw'])
    enemy = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    put(s, 'Lightning Bolt', 'graveyard')
    put(s, 'Reclaim the Wastes', 'graveyard')
    source = put(s, 'Tribute to Urborg', 'hand')
    shock = put(s, 'Shock', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'U': 1, 'R': 1, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=source.id, kicker=1, targets=[enemy.id])
    act(s, 'p1', type='cast_spell', card_id=shock.id, targets=['p2'])
    settle(s)
    assert s.state.cards[enemy.id].zone == 'p2:battlefield'
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[enemy.id]).pt == (1, 1)
    roundtrip(s)


def test_chocobo_current_source_power_is_evaluated_at_resolution(cards):
    s = table(cards, ['Chocobo Kick', 'Grizzly Bears', 'Giant Growth'], ['Colossal Dreadmaw'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    enemy = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    source = put(s, 'Chocobo Kick', 'hand')
    growth = put(s, 'Giant Growth', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bear.id, enemy.id], target_counts=[1, 1])
    act(s, 'p1', type='cast_spell', card_id=growth.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[enemy.id].damage == 5
    roundtrip(s)


def test_kicked_zuko_obeys_noncast_creature_entry_replacement(cards):
    s = table(cards, ["Zuko's Conviction", 'Grizzly Bears'], ['Hallowed Moonlight'])
    bear = put(s, 'Grizzly Bears', 'graveyard')
    source = put(s, "Zuko's Conviction", 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1, 'C': 4})
    act(s, 'p1', type='cast_spell', card_id=source.id, kicker=1, targets=[bear.id])
    while s.state.rules.priority != 'p2':
        act(s, s.state.rules.priority, type='pass_priority')
    moonlight = put(s, 'Hallowed Moonlight', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'W': 1, 'C': 1})
    act(s, 'p2', type='cast_spell', card_id=moonlight.id)
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:exile'
    roundtrip(s)


def test_joint_optional_land_cold_resume_after_draw(cards, tmp_path):
    import subprocess
    import sys
    s = table(cards, ['Joint Exploration', 'Forest'])
    land = put(s, 'Forest', 'hand')
    cast(s, 'Joint Exploration', True)
    pick(s, [])
    settle(s)
    assert s.state.rules.decision is not None
    path = tmp_path / 'joint-land.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, land = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
for option in ['yes', land]:
    d = s.state.rules.decision
    assert d is not None and option in {o.id for o in d.options}
    s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
assert s.state.rules.decision is None
assert s.state.cards[land].zone == 'p1:battlefield'
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), land.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=90)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('kicked,replacement,loss', [(False, None, 20), (True, None, 20), (True, 'Bloodletter of Aclazotz', 40), (True, 'Platinum Emperion', 0)])
def test_blood_tribute_gains_only_actual_life_lost_after_native_cost(cards, kicked, replacement, loss):
    assert coverage.of_card_data(cards.resolve('Blood Tribute')).level == 'FULL'
    s = table(cards, ['Blood Tribute', 'Vampire Nighthawk', 'Bloodletter of Aclazotz'], ['Platinum Emperion'])
    bear = put(s, 'Vampire Nighthawk', 'battlefield')
    if replacement:
        put(s, replacement, 'battlefield', 'p1' if replacement == 'Bloodletter of Aclazotz' else 'p2')
    source = put(s, 'Blood Tribute', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 2, 'C': 4})
    act(s, 'p1', type='cast_spell', card_id=source.id, kicker=int(kicked), targets=['p2'])
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert bear.id in {o.id for o in d.options}
        pick(s, [bear.id])
    settle(s)
    assert s.state.players['p1'].life == 40 + (loss if kicked else 0)
    assert s.state.cards[bear.id].tapped == kicked
    if 'p2' in s.state.players:
        assert s.state.players['p2'].life == 40 - loss
    roundtrip(s)
