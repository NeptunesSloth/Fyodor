"""Actual dealt damage and recipient statistics bound Drain Life/Soul Burn life gain."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/drain_life_soul_burn_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='cdl', number=str(i), **{k:v for k,v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    return table(cards, ['Drain Life', 'Soul Burn', 'Grizzly Bears', 'Jace Beleren', 'Furnace of Rath', 'Boon Reflection', 'Sulfuric Vortex', 'Gideon Blackblade', 'Flaring Pain', 'Reverberate'],
                 ['Grizzly Bears', 'Jace Beleren', 'Healing Salve', 'Pariah', 'Tainted Remedy'], ['Grizzly Bears'])


def cast(s, name, target, x, player='p1', pool=None):
    from tests.test_rules_bandmate_references import wait_priority
    spell = put(s, name, 'hand', pid=player)
    if pool is None:
        pool = {'B':x+1, 'C':1 if name == 'Drain Life' else 2}
    act(s, player, type='add_mana', player=player, mana=pool)
    wait_priority(s, player)
    act(s, player, type='cast_spell', card_id=spell.id, targets=[target], x_value=x, sources=[])
    return spell


def test_drain_life_full(cards):
    assert coverage.of_card_data(cards.resolve('Drain Life')).level == 'FULL'


@pytest.mark.parametrize('x', [1, 2, 5])
def test_damage_to_creature_capped_by_toughness_and_actual_damage(cards, x):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    cast(s, 'Drain Life', bear.id, x)
    settle(s)
    assert s.state.players['p1'].life == 40 + min(x,2)
    assert s.state.cards[bear.id].zone == ('p2:graveyard' if x >= 2 else 'p2:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('life,x', [(2,5), (40,5), (0,0)])
def test_player_cap_uses_life_before_damage(cards, life, x):
    s = game(cards)
    if life:
        act(s, 'p1', type='set_life', player='p2', value=life)
    cast(s, 'Drain Life', 'p2', x)
    settle(s)
    assert s.state.players['p1'].life == 40 + min(x, life or 40)
    roundtrip(s)


def test_planeswalker_cap_uses_loyalty_before_damage(cards):
    s = game(cards)
    target = put(s, 'Jace Beleren', 'battlefield', pid='p2')
    act(s, 'p1', type='set_counter', card_id=target.id, kind='loyalty', value=3)
    cast(s, 'Drain Life', target.id, 5)
    settle(s)
    assert s.state.players['p1'].life == 43
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('loyalty,expected', [(2,2), (6,4)])
def test_creature_planeswalker_recipient_obeys_both_bounds(cards, loyalty, expected):
    s = game(cards)
    from tests.test_rules_remaining_talents import pay
    pain = put(s, 'Flaring Pain', 'hand')
    pay(s, 'p1', 'Flaring Pain')
    act(s, 'p1', type='cast_spell', card_id=pain.id, sources=[])
    settle(s)
    target = put(s, 'Gideon Blackblade', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=target.id, kind='loyalty', value=loyalty)
    cast(s, 'Drain Life', target.id, 5)
    settle(s)
    assert s.state.players['p1'].life == 40 + expected
    roundtrip(s)


def test_redirected_damage_uses_actual_recipient_not_original_target(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    aura = put(s, 'Pariah', 'battlefield', pid='p2')
    act(s, 'p1', type='attach', card_ids=[aura.id], to=bear.id)
    cast(s, 'Drain Life', 'p2', 5)
    settle(s)
    assert s.state.players['p2'].life == 40
    assert s.state.players['p1'].life == 42
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('replacement,expected', [('Furnace of Rath',42), ('Boon Reflection',44), ('Sulfuric Vortex',40)])
def test_native_damage_and_life_replacements_remain_in_force(cards, replacement, expected):
    s = game(cards)
    put(s, replacement, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    cast(s, 'Drain Life', bear.id, 5)
    settle(s)
    assert s.state.players['p1'].life == expected
    roundtrip(s)


def test_prevention_limits_gain_to_actual_damage(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_remaining_talents import pay
    s = game(cards)
    cast(s, 'Drain Life', 'p2', 5)
    salve = put(s, 'Healing Salve', 'hand', pid='p2')
    pay(s, 'p2', 'Healing Salve')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=salve.id, targets=['p2'], modes=[1], sources=[])
    settle(s)
    assert s.state.players['p2'].life == 38
    assert s.state.players['p1'].life == 42
    roundtrip(s)



@pytest.mark.parametrize('keyword', ['wither', 'infect'])
def test_native_damage_cap_reads_toughness_after_counter_damage(keyword, cards):
    # Isolated damage-pipeline contract: inject source keyword metadata, not fictional Drain Life Oracle.
    from app.rules import capped_damage_life, effects
    from app.rules.plan import Plan
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p1', type='set_counter', card_id=bear.id, kind='+1/+1', value=1)
    spell = put(s, 'Drain Life', 'stack')
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    e = {'do':'damage', 'who':'target', 'n':2, 'bind_life_caps':'probe'}
    ctx = {'controller':'p1', 'source_card':spell.id, 'source_object':plan.oid(spell.id), 'effects':[e], 'next':1}
    source = effects._Source(plan.oid(spell.id), frozenset({keyword}), plan.ch(plan.state.cards[spell.id]), 'p1', spell.id)
    assert effects._deal(plan, ctx, [(source, bear.id, 2)], e)
    assert plan.ch(plan.state.cards[bear.id]).pt == (1,1)
    assert capped_damage_life.gain(plan, ctx, {'do':'gain_capped_damage', 'life_caps':'probe'})
    assert plan.state.players['p1'].life == 41



def test_damage_replacement_order_retains_original_recipient_caps(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_remaining_talents import pay
    s = game(cards)
    put(s, 'Furnace of Rath', 'battlefield')
    cast(s, 'Drain Life', 'p2', 5)
    salve = put(s, 'Healing Salve', 'hand', pid='p2')
    pay(s, 'p2', 'Healing Salve')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=salve.id, targets=['p2'], modes=[1], sources=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    option = next(o for o in d.options if 'Furnace of Rath' in o.label)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    settle(s)
    assert s.state.players['p2'].life == 33
    assert s.state.players['p1'].life == 47
    roundtrip(s)


def test_saved_gain_replacement_order_resumes_capped_gain_without_redealing(cards, tmp_path):
    import subprocess
    import sys
    s = game(cards)
    put(s, 'Boon Reflection', 'battlefield')
    put(s, 'Tainted Remedy', 'battlefield', pid='p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    cast(s, 'Drain Life', bear.id, 5)
    settle(s)
    d = s.state.rules.decision
    assert d and any('Boon Reflection' in o.label for o in d.options)
    roundtrip(s)
    saved = tmp_path / 'capped-gain.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state_path, database, bear = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
d = s.state.rules.decision
option = next(o for o in d.options if 'Boon Reflection' in o.label)
s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[option.id]})
for _ in range(12):
    if s.state.rules.decision is not None or not s.state.rules.stack: break
    s.perform(s.state.rules.priority, {'type':'pass_priority'})
assert s.state.players['p1'].life == 36
assert s.state.cards[bear].zone == 'p2:graveyard'
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()).model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), bear.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr



def test_legacy_missing_black_x_has_bounded_manual_gain_and_cold_resume(cards, tmp_path):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState
    s = game(cards)
    put(s, 'Furnace of Rath', 'battlefield')
    spell = cast(s, 'Soul Burn', 'p2', 2)
    assert s.state.rules.decision is None
    old = s.state.model_dump(mode='json')
    oid = s.state.rules.object_id(spell.id)
    old['rules']['payments'][oid].pop('x_black_spent')
    s = GameSession(GameState.model_validate(old), cards=cards)
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'manual_resolution'
    assert 'at most 2' in d.prompt  # Damage doubled to4; actual black-on-X can never exceed announcedX2.
    assert s.state.players['p2'].life == 36
    assert s.state.players['p1'].life == 40
    saved = tmp_path / 'legacy-soul.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state_path,database = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent/'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
d = s.state.rules.decision
assert d.resume['step'] == 'capped_damage_legacy_done'
s.perform('p1', {'type':'life','player':'p1','delta':2})
s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':['done']})
for _ in range(12):
    if s.state.rules.decision is not None or not s.state.rules.stack: break
    s.perform(s.state.rules.priority, {'type':'pass_priority'})
assert s.state.players['p1'].life == 42
assert s.state.players['p2'].life == 36
assert not s.state.rules.decision
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr



def test_actual_soul_burn_copy_does_damage_but_spends_no_black_on_x(cards):
    from tests.test_rules_bandmate_references import wait_priority
    s = game(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    original = cast(s, 'Soul Burn', 'p2', 2)
    copy = put(s, 'Reverberate', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'R':2})
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[original.id], sources=[])
    for _ in range(20):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        roundtrip(s)
        assert 'keep' in {o.id for o in d.options}, (d.kind, d.prompt)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'])
    assert s.state.players['p2'].life == 36
    assert s.state.players['p1'].life == 42
    assert s.state.rules.decision is None
    roundtrip(s)
