"""CR 208.1 / 603.2: trigger filters compare current power and toughness."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/equal_power_toughness_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Symmetry Matrix', 'Master Symmetrist'])
def test_equal_power_toughness_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def cast_creature(s, name, pid='p1'):
    source = put(s, name, 'hand', pid)
    act(s, pid, type='add_mana', player=pid, mana={'C': 2, 'G': 1})
    act(s, pid, type='cast_spell', card_id=source.id, targets=[])
    return source


@pytest.mark.parametrize('name', ['Grizzly Bears', 'Ornithopter'])
@pytest.mark.parametrize('castle', [False, True])
@pytest.mark.parametrize('pay', [False, True])
def test_matrix_uses_current_entering_power_and_toughness(cards, name, castle, pay):
    s = table(cards, ['Symmetry Matrix', name, *(['Castle'] if castle else [])])
    put(s, 'Symmetry Matrix', 'battlefield')
    if castle:
        put(s, 'Castle', 'battlefield')
    creature = cast_creature(s, name)
    before = len(s.state.zones['p1:hand'])
    settle(s)
    eligible = name == 'Grizzly Bears' and not castle
    if eligible:
        d = s.state.rules.decision
        assert d is not None and d.player == 'p1'
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if pay else 'decline'])
        settle(s)
    else:
        assert s.state.rules.decision is None
    assert creature.id in s.state.zones['p1:battlefield']
    assert len(s.state.zones['p1:hand']) == before + int(eligible and pay)
    roundtrip(s)


def test_matrix_does_not_trigger_for_an_opponents_creature(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Symmetry Matrix'], ['Grizzly Bears'])
    put(s, 'Symmetry Matrix', 'battlefield')
    to_phase(s, 'main1', turn=2)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    creature = cast_creature(s, 'Grizzly Bears', 'p2')
    settle(s)
    assert creature.id in s.state.zones['p2:battlefield']
    assert s.state.rules.decision is None and s.state.players['p1'].mana['C'] == 1
    roundtrip(s)


@pytest.mark.parametrize('source_leaves', [False, True])
def test_matrix_trigger_does_not_recheck_equality_or_source_on_resolution(cards, source_leaves):
    s = table(cards, ['Symmetry Matrix', 'Grizzly Bears', 'Fists of the Anvil'])
    matrix = put(s, 'Symmetry Matrix', 'battlefield')
    bear = cast_creature(s, 'Grizzly Bears')
    for _ in range(10):
        if bear.id in s.state.zones['p1:battlefield']:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert bear.id in s.state.zones['p1:battlefield'] and s.state.zones['stack']
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[matrix.id], to={'player': 'p1', 'zone': 'graveyard'})
    fist = put(s, 'Fists of the Anvil', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=fist.id, targets=[bear.id])
    before = len(s.state.zones['p1:hand'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    from app.rules.plan import Plan

    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id]).pt == (6, 2)
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)


def attackers(s, pairs):
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.number >= 4 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == 'declare_attackers' and s.state.turn.active_player == 'p1')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': p} for c, p in pairs])


@pytest.mark.parametrize('oriflamme', [False, True])
@pytest.mark.parametrize('damage', [0, 1])
def test_symmetrist_checks_the_current_attacking_stats_and_triggers_per_creature(cards, oriflamme, damage):
    from app.rules.plan import Plan

    s = table(cards, ['Master Symmetrist', 'Grizzly Bears', 'Ornithopter', *(['Orcish Oriflamme'] if oriflamme else [])])
    master = put(s, 'Master Symmetrist', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    orni = put(s, 'Ornithopter', 'battlefield')
    if oriflamme:
        put(s, 'Orcish Oriflamme', 'battlefield')
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=4)
    if damage:
        act(s, 'p1', type='set_damage', card_ids=[bear.id], delta=damage)
    attackers(s, [(master, 'p2'), (bear, 'p3'), (orni, 'p3')])
    settle(s)
    for c in [master, bear]:
        assert ('trample' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[c.id]).keywords) == (not oriflamme)
    assert 'trample' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[orni.id]).keywords
    roundtrip(s)


def test_symmetrist_does_not_recheck_equality_after_its_trigger_is_on_the_stack(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Master Symmetrist', 'Grizzly Bears', 'Fists of the Anvil'])
    put(s, 'Master Symmetrist', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    attackers(s, [(bear, 'p2')])
    assert s.state.zones['stack']
    fist = put(s, 'Fists of the Anvil', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=fist.id, targets=[bear.id])
    roundtrip(s)
    settle(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[bear.id])
    assert ch.pt == (6, 2) and 'trample' in ch.keywords
    roundtrip(s)


@pytest.mark.parametrize('x', [0, 1])
def test_zero_zero_entries_trigger_even_if_the_creature_immediately_dies(cards, x):
    s = table(cards, ['Symmetry Matrix', 'Walking Ballista'])
    put(s, 'Symmetry Matrix', 'battlefield')
    ballista = put(s, 'Walking Ballista', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': x * 2 + 1})
    act(s, 'p1', type='cast_spell', card_id=ballista.id, targets=[], x_value=x)
    before = len(s.state.zones['p1:hand'])
    settle(s)
    assert ballista.id in s.state.zones['p1:battlefield' if x else 'p1:graveyard']
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    roundtrip(s)
