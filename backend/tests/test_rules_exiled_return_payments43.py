"""Canonical Gilraen native return payment and delayed as-entry counters."""
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
from tests.test_rules_linked_aggregates import activate, cast
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Gilraen, Dúnedain Protector'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/exiled_return_payments43_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='erp', number=str(i), **{('card_faces' if k == 'faces' else k): v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def scene(cards, priest=False, modifier=None):
    names = [NAME, 'Grizzly Bears', 'Containment Priest', 'Doubling Season', 'Vorinclex, Monstrous Raider',
             'Solemnity', 'Act of Treason', 'Startled Awake // Persistent Nightmare', 'Raise the Alarm', 'Lightning Bolt']
    s = table(cards, names, names, names)
    source = put(s, NAME, 'hand')
    cast(s, source)
    settle(s)
    target = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=4)
    if priest:
        put(s, 'Containment Priest', 'battlefield', pid='p2')
    if modifier:
        put(s, modifier, 'battlefield', pid='p2' if modifier == 'Vorinclex, Monstrous Raider' else 'p1')
    return s, source, target


def setup(cards, priest=False, modifier=None):
    s, source, target = scene(cards, priest=priest, modifier=modifier)
    activate(s, source, targets=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'yes', 'no'}
    assert s.state.cards[target.id].zone == 'p1:exile'
    assert s.state.cards[source.id].tapped
    return s, source, target


def answer(s, yes):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes' if yes else 'no'])
    settle(s)


def test_full_canonical(cards):
    q = coverage.of_card_data(cards.resolve(NAME))
    assert q.level == 'FULL', [(f.label, f.supported) for f in q.features]


@pytest.mark.parametrize('accept', [False, True])
def test_actual_choose_immediate_no_counters_or_delayed_both_entry_counters(cards, accept):
    s, _, target = setup(cards)
    old = s.state.rules.object_id(target.id)
    answer(s, accept)
    if accept:
        assert s.state.cards[target.id].zone == 'p1:battlefield'
        assert s.state.rules.object_id(target.id) != old
        assert not s.state.cards[target.id].counters and not s.state.rules.delayed
    else:
        assert s.state.cards[target.id].zone == 'p1:exile'
        assert len(s.state.rules.delayed) == 1
        to_phase(s, 'end', turn=4)
        settle(s)
        assert s.state.cards[target.id].zone == 'p1:battlefield'
        assert s.state.cards[target.id].counters == {'vigilance': 1, 'lifelink': 1}
    roundtrip(s)


def test_actual_replacement_modified_return_is_paid_and_has_no_delayed_fallback(cards):
    s, _, target = setup(cards, priest=True)
    answer(s, True)
    assert s.state.cards[target.id].zone == 'p1:exile'
    assert not s.state.rules.delayed
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:exile'
    assert not s.state.cards[target.id].counters
    roundtrip(s)


@pytest.mark.parametrize('modifier,expected', [('Doubling Season', 2), ('Vorinclex, Monstrous Raider', 0), ('Solemnity', 0)])
def test_actual_delayed_keyword_counters_are_native_as_entry_counters(cards, modifier, expected):
    from app.rules.plan import Plan

    s, _, target = setup(cards, modifier=modifier)
    answer(s, False)
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters == ({'vigilance': expected, 'lifelink': expected} if expected else {})
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[target.id])
    assert ('vigilance' in ch.keywords) == bool(expected)
    assert ('lifelink' in ch.keywords) == bool(expected)
    roundtrip(s)


def test_actual_delayed_return_uses_exact_exiled_object_and_is_source_independent(cards):
    s, source, target = setup(cards)
    answer(s, False)
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[target.id], to={'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[target.id], to={'zone': 'exile'})
    new = s.state.rules.object_id(target.id)
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:exile' and s.state.rules.object_id(target.id) == new
    assert not s.state.cards[target.id].counters
    roundtrip(s)


def test_actual_delayed_return_survives_source_departure(cards):
    s, source, target = setup(cards)
    answer(s, False)
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'graveyard'})
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters == {'vigilance': 1, 'lifelink': 1}
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_actual_stolen_creature_returns_under_its_owners_control(cards, accept):
    s, source, _ = scene(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    steal = put(s, 'Act of Treason', 'hand')
    cast(s, steal, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].controller == 'p1'
    activate(s, source, targets=[target.id])
    settle(s)
    answer(s, accept)
    if not accept:
        to_phase(s, 'end', turn=4)
        settle(s)
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    assert s.state.cards[target.id].controller == 'p2'
    assert s.state.cards[target.id].counters == ({} if accept else {'vigilance': 1, 'lifelink': 1})
    roundtrip(s)


def test_actual_token_cost_is_impossible_but_delayed_trigger_is_still_created(cards):
    s, source, _ = scene(cards)
    spell = put(s, 'Raise the Alarm', 'hand')
    cast(s, spell)
    settle(s)
    target = next(c for c in s.state.cards.values() if c.is_token and c.name == 'Soldier')
    activate(s, source, targets=[target.id])
    settle(s)
    assert s.state.rules.decision is None
    assert len(s.state.rules.delayed) == 1
    assert target.id not in s.state.cards or not s.state.cards[target.id].zone.endswith(':battlefield')
    to_phase(s, 'end', turn=4)
    settle(s)
    assert not s.state.rules.delayed
    assert target.id not in s.state.cards or not s.state.cards[target.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_actual_another_target_and_insufficient_mana_reject_atomically(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, source, target = scene(cards)
    act(s, 'p1', type='clear_mana', player='p1')
    wait_priority(s, 'p1')
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[target.id])
    assert s.state.model_dump(mode='json') == before
    mana(s, C=2)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, targets=[source.id])
    assert s.state.model_dump(mode='json') == before


@pytest.mark.parametrize('first,expected', [('Doubling Season', 1), ('Vorinclex', 0)])
def test_actual_delayed_as_entry_counter_order_true_cold(cards, tmp_path, first, expected):
    import subprocess
    import sys

    s, source, target = scene(cards, modifier='Doubling Season')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', pid='p2')
    activate(s, source, targets=[target.id])
    settle(s)
    answer(s, False)
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.rules.decision is not None
    assert s.state.cards[target.id].zone == 'p1:exile' and not s.state.cards[target.id].counters
    saved = tmp_path / 'gilraen43-entry.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle
saved, db, target, first, expected = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
for _ in range(10):
    d = s.state.rules.decision
    if d is None: break
    assert s.state.cards[target].zone == 'p1:exile'
    option = next(o for o in d.options if first in o.label)
    s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[option.id]})
    settle(s)
assert s.state.rules.decision is None
assert s.state.cards[target].zone == 'p1:battlefield'
expected = int(expected)
assert s.state.cards[target].counters == ({'vigilance':expected,'lifelink':expected} if expected else {})
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), target.id, first, str(expected)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_actual_back_creature_with_sorcery_front_cannot_pay_return_cost(cards):
    s, source, _ = scene(cards)
    # Seed the real printed back-face object: its front graveyard activation
    # remains a separate PARTIAL card. Gilraen below resolves natively.
    target = put(s, 'Startled Awake // Persistent Nightmare', 'battlefield')
    act(s, 'p1', type='set_face', card_id=target.id, face=1)
    assert s.state.cards[target.id].zone == 'p1:battlefield' and s.state.cards[target.id].face == 1
    activate(s, source, targets=[target.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[target.id].zone == 'p1:exile'
    assert len(s.state.rules.delayed) == 1
    to_phase(s, 'end', turn=4)
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:exile' and not s.state.cards[target.id].counters
    roundtrip(s)
