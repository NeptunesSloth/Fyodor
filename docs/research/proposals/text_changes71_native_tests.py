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
    s = table(cards, [c['name'] for c in DATA] + ['Swamp', 'Grizzly Bears', 'Sol Ring'], ['Grizzly Bears', 'Icy Manipulator', 'Elvish Visionary', 'Deathmark'], ['Grizzly Bears'])
    land = put(s, 'Swamp', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    start(s)
    return s, land, bear


def choose(s, value):
    d = s.state.rules.decision
    assert d is not None and value in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[value])
    settle(s)


def cast(s, name, targets):
    c = put(s, name, 'hand')
    mana(s, C=8, U=5, W=5, B=5, R=5, G=5)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=c.id, targets=list(targets), sources=[])
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
