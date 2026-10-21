"""Creature-source damage and current exact-source guards."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/creature_damage_followup_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='evc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = ['Bind the Monster', 'Cut Propulsion', 'Wisecrack', 'Stalking Yeti', 'Durkwood Tracker']


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def cast(s, name, targets=()):
    source = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 3, 'U': 3, 'R': 3, 'C': 5})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=list(targets))
    settle(s)
    return source


def test_bind_host_deals_its_power_to_aura_controller(cards):
    s = table(cards, ['Bind the Monster'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = cast(s, 'Bind the Monster', [bear.id])
    assert s.state.cards[source.id].attached_to == bear.id
    assert s.state.cards[bear.id].tapped
    assert s.state.players['p1'].life == 38
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_cut_flying_creature_deals_double_with_native_lifelink(cards):
    s = table(cards, ['Cut Propulsion'], ['Vampire Nighthawk'])
    creature = put(s, 'Vampire Nighthawk', 'battlefield', 'p2')
    cast(s, 'Cut Propulsion', [creature.id])
    assert s.state.cards[creature.id].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 44
    roundtrip(s)


def test_wisecrack_nonattacking_target_has_no_controller_damage(cards):
    s = table(cards, ['Wisecrack'], ['Grizzly Bears'])
    creature = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Wisecrack', [creature.id])
    assert s.state.cards[creature.id].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('leave', [False, True])
def test_yeti_requires_exact_source_still_on_battlefield(cards, leave):
    s = table(cards, ['Stalking Yeti'], ['Colossal Dreadmaw', 'Unsummon'])
    enemy = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    source = cast(s, 'Stalking Yeti')
    d = s.state.rules.decision
    assert d is not None
    pick(s, [enemy.id])
    if leave:
        while s.state.rules.priority != 'p2':
            act(s, s.state.rules.priority, type='pass_priority')
        bounce = put(s, 'Unsummon', 'hand', 'p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
        act(s, 'p2', type='cast_spell', card_id=bounce.id, targets=[source.id])
    settle(s)
    assert s.state.cards[enemy.id].damage == (0 if leave else 3)
    assert s.state.cards[source.id].zone == ('p1:hand' if leave else 'p1:graveyard')
    roundtrip(s)


def test_cut_nonflying_lifelink_creature_deals_ordinary_power(cards):
    s = table(cards, ['Cut Propulsion'], ['Child of Night'])
    creature = put(s, 'Child of Night', 'battlefield', 'p2')
    cast(s, 'Cut Propulsion', [creature.id])
    assert s.state.cards[creature.id].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 42
    roundtrip(s)


def test_cut_reads_current_power_after_actual_growth_response(cards):
    s = table(cards, ['Cut Propulsion', 'Giant Growth'], ['Vampire Nighthawk'])
    creature = put(s, 'Vampire Nighthawk', 'battlefield', 'p2')
    source = put(s, 'Cut Propulsion', 'hand')
    growth = put(s, 'Giant Growth', 'hand')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'R': 1, 'C': 5})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[creature.id])
    act(s, 'p1', type='cast_spell', card_id=growth.id, targets=[creature.id])
    settle(s)
    assert s.state.players['p2'].life == 50
    roundtrip(s)


def attack_opponent(s, creature):
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': creature.id, 'target': 'p1'}])
    while s.state.rules.priority != 'p1':
        act(s, s.state.rules.priority, type='pass_priority')


def test_wisecrack_attacking_target_controller_is_damaged(cards):
    s = table(cards, ['Wisecrack'], ['Grizzly Bears'])
    creature = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack_opponent(s, creature)
    cast(s, 'Wisecrack', [creature.id])
    assert s.state.cards[creature.id].zone == 'p2:graveyard'
    assert s.state.players['p2'].life == 38
    assert s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('leave', [False, True])
def test_tracker_native_activation_requires_source_still_present(cards, leave):
    s = table(cards, ['Durkwood Tracker', 'Thousand-Year Elixir'], ['Grizzly Bears', 'Unsummon'])
    source = put(s, 'Durkwood Tracker', 'battlefield')
    put(s, 'Thousand-Year Elixir', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack_opponent(s, enemy)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[enemy.id])
    if leave:
        while s.state.rules.priority != 'p2':
            act(s, s.state.rules.priority, type='pass_priority')
        bounce = put(s, 'Unsummon', 'hand', 'p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
        act(s, 'p2', type='cast_spell', card_id=bounce.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == ('p1:hand' if leave else 'p1:battlefield')
    assert s.state.cards[enemy.id].zone == ('p2:battlefield' if leave else 'p2:graveyard')
    if not leave:
        assert s.state.cards[source.id].damage == 2
    roundtrip(s)


def test_yeti_saved_target_choice_cold_resume(cards, tmp_path):
    import subprocess
    import sys
    s = table(cards, ['Stalking Yeti'], ['Colossal Dreadmaw'])
    enemy = put(s, 'Colossal Dreadmaw', 'battlefield', 'p2')
    source = cast(s, 'Stalking Yeti')
    assert s.state.rules.decision is not None
    path = tmp_path / 'yeti-target.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, source, enemy = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p1')
d = s.state.rules.decision
assert d is not None and enemy in {o.id for o in d.options}
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [enemy]})
for _ in range(30):
    assert s.state.rules.decision is None
    if not s.state.zones['stack']:
        break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('Yeti did not resolve')
assert s.state.cards[source].zone == 'p1:graveyard'
assert s.state.cards[enemy].damage == 3
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), source.id, enemy.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=90)
    assert result.returncode == 0, result.stderr


def test_tracker_blinked_source_cannot_deal_reciprocal_damage(cards):
    s = table(cards, ['Durkwood Tracker', 'Thousand-Year Elixir', 'Ephemerate'], ['Grizzly Bears'])
    source = put(s, 'Durkwood Tracker', 'battlefield')
    put(s, 'Thousand-Year Elixir', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attack_opponent(s, enemy)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1, 'W': 1, 'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[enemy.id])
    blink = put(s, 'Ephemerate', 'hand')
    act(s, 'p1', type='cast_spell', card_id=blink.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].damage == 0
    assert s.state.cards[enemy.id].zone == 'p2:battlefield'
    assert s.state.cards[enemy.id].damage == 0
    roundtrip(s)


def test_self_destruct_native_simultaneous_damage_and_lifelink(cards):
    assert coverage.of_card_data(cards.resolve('Self-Destruct')).level == 'FULL'
    s = table(cards, ['Self-Destruct', 'Vampire Nighthawk', "Ajani's Pridemate"])
    pridemate = put(s, "Ajani's Pridemate", 'battlefield')
    creature = put(s, 'Vampire Nighthawk', 'battlefield')
    source = put(s, 'Self-Destruct', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[creature.id, 'p2'], target_counts=[1, 1])
    settle(s)
    assert s.state.players['p1'].life == 44
    assert s.state.cards[pridemate.id].counters.get('+1/+1') == 1
    assert s.state.players['p2'].life == 38
    assert s.state.cards[creature.id].zone == 'p1:graveyard'  # deathtouch applies to itself too
    roundtrip(s)


def test_self_destruct_cannot_choose_its_creature_as_other_target(cards):
    from app.game.errors import ActionError
    s = table(cards, ['Self-Destruct', 'Grizzly Bears'])
    creature = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Self-Destruct', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[creature.id, creature.id], target_counts=[1, 1])
    assert s.state.model_dump_json() == before
    roundtrip(s)


@pytest.mark.parametrize('source_leaves', [False, True])
def test_self_destruct_partial_target_legality_preserves_required_damage_source(cards, source_leaves):
    s = table(cards, ['Self-Destruct', 'Vampire Nighthawk'], ['Grizzly Bears', 'Unsummon'])
    creature = put(s, 'Vampire Nighthawk', 'battlefield')
    enemy = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = put(s, 'Self-Destruct', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[creature.id, enemy.id], target_counts=[1, 1])
    while s.state.rules.priority != 'p2':
        act(s, s.state.rules.priority, type='pass_priority')
    bounce = put(s, 'Unsummon', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
    act(s, 'p2', type='cast_spell', card_id=bounce.id, targets=[creature.id if source_leaves else enemy.id])
    settle(s)
    assert s.state.players['p1'].life == (40 if source_leaves else 42)
    assert s.state.cards[creature.id].zone == ('p1:hand' if source_leaves else 'p1:graveyard')
    assert s.state.cards[enemy.id].zone == ('p2:battlefield' if source_leaves else 'p2:hand')
    assert s.state.cards[enemy.id].damage == 0
    roundtrip(s)
