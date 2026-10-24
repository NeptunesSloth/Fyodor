"""Conditional declaration requirements preserve origin, legality and native optimization."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/text_changes71_cards.json').read_text())
@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    s = table(cards, [c['name'] for c in DATA] + ['Swamp', 'Grizzly Bears', 'Sol Ring'], ['Grizzly Bears', 'Icy Manipulator', 'Elvish Visionary', 'Deathmark', 'Reach Through Mists', 'Glacial Ray', 'Sleight of Mind'], ['Grizzly Bears'])
    land = put(s, 'Swamp', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    return s, land, bear


def choose(s, value):
    d = s.state.rules.decision
    assert d is not None and value in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[value])
    settle(s)


def cast(s, name, targets, **kwargs):
    c = put(s, name, 'hand')
    mana(s, C=8, U=5, W=5, B=5, R=5, G=5)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=list(targets), sources=[], **kwargs)
    settle(s)
    return c


def test_native_paid_mind_bend_changes_actual_land_mana(cards):
    from tests.test_rules_wave5a_mana_riders import mana_pool

    s, land, _ = setup(cards)
    cast(s, 'Mind Bend', [land.id])
    choose(s, 'Swamp')
    assert 'Swamp' not in [o.id for o in s.state.rules.decision.options]
    choose(s, 'Island')
    ch = Plan(s.state, 'p1', s.cards, None).ch(land)
    assert ch.name == 'Swamp' and ch.subtypes == frozenset({'Island'})
    before_pool = mana_pool(s)
    ability = next(a.index for a in ch.abilities if a.intrinsic)
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=ability, targets=[], sources=[])
    assert land.tapped and mana_pool(s) == {**before_pool, 'U': before_pool.get('U', 0) + 1}
    roundtrip(s)


def test_valid_textless_target_and_same_word_negative(cards):
    s, _, bear = setup(cards)
    cast(s, 'Sleight of Mind', [bear.id])
    choose(s, 'black')
    d = s.state.rules.decision
    assert d is not None and 'black' not in [o.id for o in d.options]
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['black'])
    assert s.state.model_dump_json() == before
    choose(s, 'green')
    assert Plan(s.state, 'p1', s.cards, None).ch(bear).oracle_text == ''
    roundtrip(s)


@pytest.mark.parametrize('kind', ['activated', 'trigger'])
def test_actual_stack_abilities_are_not_spell_targets(cards, kind):
    s, _, bear = setup(cards)
    if kind == 'activated':
        icy = put(s, 'Icy Manipulator', 'battlefield', 'p2')
        wait_priority(s, 'p2')
        mana(s, pid='p2', C=1)
        ability = next(a.index for a in Plan(s.state, 'p2', s.cards, None).ch(icy).abilities if a.kind == 'activated')
        act(s, 'p2', type='activate_ability', card_id=icy.id, ability=ability, targets=[bear.id], sources=[])
    else:
        to_phase(s, 'main1', turn=8)
        vision = put(s, 'Elvish Visionary', 'hand', 'p2')
        mana(s, pid='p2', G=2)
        wait_priority(s, 'p2')
        act(s, 'p2', type='cast_spell', card_id=vision.id, targets=[], sources=[])
        for _ in range(12):
            if any(e.kind == 'trigger' for e in s.state.rules.stack.values()):
                break
            act(s, s.state.rules.priority, type='pass_priority')
    target = s.state.zones['stack'][-1]
    assert s.state.rules.stack[target].kind == kind
    source = put(s, 'Sleight of Mind', 'hand')
    mana(s, U=1)
    wait_priority(s, 'p1')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target], sources=[])
    assert s.state.model_dump_json() == before


def test_changed_spell_keeps_old_target_and_rechecks_new_selector(cards):
    s, _, bear = setup(cards)
    to_phase(s, 'main1', turn=8)
    death = put(s, 'Deathmark', 'hand', 'p2')
    mana(s, pid='p2', B=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=death.id, targets=[bear.id], sources=[])
    source = put(s, 'Sleight of Mind', 'hand')
    mana(s, U=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[death.id], sources=[])
    settle(s)
    choose(s, 'green')
    choose(s, 'red')
    assert bear.zone == 'p1:battlefield'
    assert death.zone == 'p2:graveyard'
    roundtrip(s)


def modified_knight(cards):
    s, _, _ = setup(cards)
    knight = put(s, 'Black Knight', 'hand')
    mana(s, B=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=knight.id, targets=[], sources=[])
    old = s.state.rules.object_id(knight.id)
    assert knight.zone == 'stack'
    source = put(s, 'Sleight of Mind', 'hand', 'p2')
    mana(s, pid='p2', U=1)
    wait_priority(s, 'p2')
    assert knight.zone == 'stack'
    act(s, 'p2', type='cast_spell', card_id=source.id, targets=[knight.id], sources=[])
    settle(s)
    choose(s, 'white')
    choose(s, 'green')
    return s, knight, old


def test_modified_permanent_spell_keeps_change_on_resolution(cards):
    s, knight, old = modified_knight(cards)
    ch = Plan(s.state, 'p1', s.cards, None).ch(knight)
    assert knight.zone == 'p1:battlefield' and ch.colors == frozenset({'B'}) and ch.name == 'Black Knight'
    assert any('protection from green' in a.text.lower() for a in ch.abilities)
    assert old != s.state.rules.object_id(knight.id)
    assert any(e.text_change71 is not None and s.state.rules.object_id(knight.id) in e.affected for e in s.state.rules.effects)
    roundtrip(s)


def test_native_copy_excludes_layer3_text_change_and_blink_resets_it(cards):
    s, knight, _ = modified_knight(cards)
    copied = cast(s, 'Phyrexian Metamorph', [])
    choose(s, knight.id)
    copych = Plan(s.state, 'p1', s.cards, None).ch(copied)
    assert any('protection from white' in a.text.lower() for a in copych.abilities)
    assert not any('protection from green' in a.text.lower() for a in copych.abilities)
    cast(s, 'Cloudshift', [knight.id])
    ch = Plan(s.state, 'p1', s.cards, None).ch(knight)
    assert any('protection from white' in a.text.lower() for a in ch.abilities)
    assert not any('protection from green' in a.text.lower() for a in ch.abilities)
    roundtrip(s)


def test_entwined_native_modes_keep_distinct_original_targets(cards):
    s, land, _ = setup(cards)
    knight = cast(s, 'Black Knight', [])
    cast(s, 'Spectral Shift', [land.id, knight.id], modes=[0, 1], kicker=1)
    choose(s, 'Swamp')
    choose(s, 'Island')
    choose(s, 'white')
    choose(s, 'green')
    plan = Plan(s.state, 'p1', s.cards, None)
    assert plan.ch(land).subtypes == frozenset({'Island'})
    assert any('protection from green' in a.text.lower() for a in plan.ch(knight).abilities)
    roundtrip(s)


def test_modified_modal_spell_preserves_modes_and_changes_effect_color(cards):
    s, _, _ = setup(cards)
    guile = put(s, "Kaya's Guile", 'hand')
    mana(s, C=1, W=1, B=1)
    wait_priority(s, 'p1')
    life = s.state.players['p1'].life
    act(s, 'p1', type='cast_spell', card_id=guile.id, modes=[2, 3], targets=[], sources=[])
    assert guile.zone == 'stack'
    source = put(s, 'Sleight of Mind', 'hand', 'p2')
    mana(s, pid='p2', U=1)
    wait_priority(s, 'p2')
    assert guile.zone == 'stack'
    act(s, 'p2', type='cast_spell', card_id=source.id, targets=[guile.id], sources=[])
    settle(s)
    choose(s, 'white')
    choose(s, 'red')
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
    assert len(tokens) == 1 and Plan(s.state, 'p1', s.cards, None).ch(tokens[0]).colors == frozenset({'B', 'R'})
    assert s.state.players['p1'].life == life + 4
    roundtrip(s)


def test_modified_spliced_spell_keeps_original_paid_extra_text(cards):
    s, _, bear = setup(cards)
    reach = put(s, 'Reach Through Mists', 'hand', 'p2')
    ray = put(s, 'Glacial Ray', 'hand', 'p2')
    mana(s, pid='p2', C=1, U=1, R=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=reach.id, splice=[ray.id], targets=[bear.id], sources=[])
    record = s.state.rules.payments[s.state.rules.object_id(reach.id)]
    assert record.splice_text71 is not None and record.splice_text71.abilities
    source = put(s, 'Sleight of Mind', 'hand')
    mana(s, U=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[reach.id], sources=[])
    settle(s)
    choose(s, 'red')
    choose(s, 'green')
    assert bear.zone == 'p1:graveyard' and ray.zone == 'p2:hand' and reach.zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('changed', ['host', 'sword'])
def test_text_change_affects_grant_source_but_not_granted_holder_text(cards, changed):
    from tests.test_rules_combat_equipment_blocks70 import equip

    s, _, bear = setup(cards)
    sword = cast(s, 'Sword of Fire and Ice', [])
    if changed == 'sword':
        equip(s, sword, bear)
    cast(s, 'Sleight of Mind', [bear.id if changed == 'host' else sword.id])
    choose(s, 'red')
    choose(s, 'green')
    if changed == 'host':
        equip(s, sword, bear)
    for name, blocked in [('Lightning Bolt', changed == 'host'), ('Giant Growth', changed == 'sword')]:
        source = put(s, name, 'hand')
        mana(s, R=1, G=1)
        wait_priority(s, 'p1')
        if blocked:
            before = s.state.model_dump_json()
            with pytest.raises(ActionError):
                act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bear.id], sources=[])
            assert s.state.model_dump_json() == before
        else:
            act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bear.id], sources=[])
            settle(s)
    roundtrip(s)


WHOLE = ['Mind Bend', 'Sleight of Mind', 'Magical Hack', 'Alter Reality', 'Glamerdye', 'Spectral Shift',
         'Crystal Spray', 'Whim of Volrath', 'Trait Doctoring', 'Artificial Evolution']


@pytest.mark.parametrize('name', WHOLE)
def test_canonical_paid_whole_card_positive(name, cards):
    s, land, bear = setup(cards)
    knight = put(s, 'Black Knight', 'battlefield')
    merfolk = put(s, 'Merfolk of the Pearl Trident', 'battlefield')
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
    if name == 'Artificial Evolution':
        target, old, new = merfolk, 'Merfolk', 'Goblin'
    elif name in ('Magical Hack', 'Spectral Shift'):
        target, old, new = land, 'Swamp', 'Island'
    else:
        target, old, new = knight, 'white', 'green'
    source = put(s, name, 'hand')
    hand_before = len(s.state.zones['p1:hand'])
    mana(s, U=5, C=5)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id], sources=[],
        **({'modes': [0]} if name == 'Spectral Shift' else {}))
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.total_cost
    settle(s)
    choose(s, old)
    if name == 'Artificial Evolution':
        assert 'Wall' not in [o.id for o in s.state.rules.decision.options]
    choose(s, new)
    if name == 'Trait Doctoring':
        choose(s, bear.id)
        assert source.zone == 'p1:exile'
    else:
        assert source.zone == 'p1:graveyard'
    current = Plan(s.state, 'p1', s.cards, None).ch(target)
    if old == 'white':
        assert any('protection from green' in a.text.lower() for a in current.abilities)
    else:
        assert new in current.subtypes and old not in current.subtypes
    if name == 'Artificial Evolution':
        assert current.name == 'Merfolk of the Pearl Trident'
    if name == 'Crystal Spray':
        assert len(s.state.zones['p1:hand']) == hand_before
    roundtrip(s)


def test_whim_buyback_and_end_of_turn_duration(cards):
    s, _, _ = setup(cards)
    knight = put(s, 'Black Knight', 'battlefield')
    source = cast(s, 'Whim of Volrath', [knight.id], buyback=True)
    choose(s, 'white')
    choose(s, 'green')
    assert source.zone == 'p1:hand'
    assert any('protection from green' in a.text.lower() for a in Plan(s.state, 'p1', s.cards, None).ch(knight).abilities)
    to_phase(s, 'main1', turn=7)
    assert any('protection from white' in a.text.lower() for a in Plan(s.state, 'p1', s.cards, None).ch(knight).abilities)
    roundtrip(s)


def test_alter_reality_native_flashback_exiles_after_resolution(cards):
    s, _, _ = setup(cards)
    knight = put(s, 'Black Knight', 'battlefield')
    source = put(s, 'Alter Reality', 'graveyard')
    mana(s, U=2, C=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[knight.id], sources=[])
    settle(s)
    choose(s, 'white')
    choose(s, 'green')
    assert source.zone == 'p1:exile'
    assert any('protection from green' in a.text.lower() for a in Plan(s.state, 'p1', s.cards, None).ch(knight).abilities)
    roundtrip(s)


def test_glamerdye_native_retrace_discards_actual_land(cards):
    s, _, _ = setup(cards)
    knight = put(s, 'Black Knight', 'battlefield')
    source = put(s, 'Glamerdye', 'graveyard')
    land = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest')
    act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, U=1, C=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[knight.id], sources=[],
        cost_choices=[{'component': 0, 'cards': [land.id]}])
    settle(s)
    choose(s, 'white')
    choose(s, 'green')
    assert source.zone == 'p1:graveyard' and land.zone == 'p1:graveyard'
    assert any('protection from green' in a.text.lower() for a in Plan(s.state, 'p1', s.cards, None).ch(knight).abilities)
    roundtrip(s)


def cold_run(s, cards, tmp_path, code, *args):
    import os
    import subprocess
    import sys

    import app

    saved = tmp_path / 'text71.json'
    saved.write_text(s.state.model_dump_json())
    backend = Path(app.__file__).resolve().parents[1]
    prefix = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_text_changes71 import choose, cast
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
"""
    result = subprocess.run([sys.executable, '-c', prefix + code, str(saved), str(cards.db_path), *args],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=180, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_true_cold_pending_replacement_word(cards, tmp_path):
    s, land, _ = setup(cards)
    cast(s, 'Mind Bend', [land.id])
    choose(s, 'Swamp')
    cold_run(s, cards, tmp_path, r"""
assert s.state.rules.decision.player=='p1'
choose(s,'Island')
land=s.state.cards[sys.argv[3]]
assert Plan(s.state,'p1',s.cards,None).ch(land).subtypes==frozenset({'Island'})
roundtrip(s)
""", land.id)


def test_true_cold_pending_splice_text_receipt(cards, tmp_path):
    s, _, bear = setup(cards)
    reach = put(s, 'Reach Through Mists', 'hand', 'p2')
    ray = put(s, 'Glacial Ray', 'hand', 'p2')
    mana(s, pid='p2', C=1, U=1, R=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=reach.id, splice=[ray.id], targets=[bear.id], sources=[])
    source = put(s, 'Sleight of Mind', 'hand')
    mana(s, U=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[reach.id], sources=[])
    settle(s)
    choose(s, 'red')
    cold_run(s, cards, tmp_path, r"""
reach=s.state.cards[sys.argv[3]]
receipt=s.state.rules.payments[s.state.rules.object_id(reach.id)].splice_text71
assert receipt is not None and receipt.abilities
choose(s,'green')
assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
assert s.state.cards[sys.argv[5]].zone=='p2:hand'
assert reach.zone=='p2:graveyard'
roundtrip(s)
""", reach.id, bear.id, ray.id)


def test_true_cold_modified_static_source(cards, tmp_path):
    from tests.test_rules_combat_equipment_blocks70 import equip

    s, _, bear = setup(cards)
    sword = cast(s, 'Sword of Fire and Ice', [])
    equip(s, sword, bear)
    cast(s, 'Sleight of Mind', [sword.id])
    choose(s, 'red')
    choose(s, 'green')
    cold_run(s, cards, tmp_path, r"""
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_bandmate_references import mana,wait_priority
bear=s.state.cards[sys.argv[3]]
cast(s,'Lightning Bolt',[bear.id])
source=put(s,'Giant Growth','hand')
mana(s,G=1)
wait_priority(s,'p1')
before=s.state.model_dump_json()
try:
    act(s,'p1',type='cast_spell',card_id=source.id,targets=[bear.id],sources=[])
except ActionError:
    pass
else:
    raise AssertionError('changed source protection must reject green spell')
assert s.state.model_dump_json()==before
roundtrip(s)
""", bear.id)


def test_cipher_native_combat_trigger_casts_free_text_change_copy(cards):
    s, _, bear = setup(cards)
    knight = put(s, 'Black Knight', 'battlefield')
    source = cast(s, 'Trait Doctoring', [knight.id])
    choose(s, 'white')
    choose(s, 'green')
    choose(s, bear.id)
    assert source.zone == 'p1:exile'
    to_phase(s, 'declare_attackers', turn=7)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p3'}])
    seen_words = []
    for _ in range(90):
        d = s.state.rules.decision
        if s.state.turn.phase == 'main2' and not s.state.zones.get('stack') and d is None:
            break
        if d is None:
            act(s, s.state.rules.priority, type='pass_priority')
        elif d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
        else:
            ids = [o.id for o in d.options]
            if 'yes' in ids:
                value = 'yes'
            elif knight.id in ids:
                value = knight.id
            elif len(ids) == 1 and ids[0] in s.state.cards and s.state.cards[ids[0]].name == 'Trait Doctoring' and s.state.cards[ids[0]].zone.endswith(':exile'):
                value = ids[0]
            elif 'white' in ids:
                value = 'white'
                seen_words.append(value)
            elif 'green' in ids:
                value = 'green'
                seen_words.append(value)
            else:
                raise AssertionError((d.prompt, ids))
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[value])
    assert seen_words == ['white', 'green']
    assert source.zone == 'p1:exile'
    assert any('protection from green' in a.text.lower() for a in Plan(s.state, 'p1', s.cards, None).ch(knight).abilities)
    roundtrip(s)
