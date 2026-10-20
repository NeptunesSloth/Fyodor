"""Ninjutsu activation events drive Satoru's once-per-turn selection independently of resolution."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, ninjutsu
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

NAME = 'Satoru Umezawa'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/satoru_ninjutsu_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    from tests.test_rules_conditionals import token_of
    from tests.test_rules_wave33a_turn_triggers import attack

    s = table(cards, [NAME, 'Ninja of the Deep Hours', 'Grizzly Bears', "Yuriko, the Tiger's Shadow", 'Azure Mage', 'Lightning Bolt', 'Island'], ['Stifle', 'Grizzly Bears'])
    source = put(s, NAME, 'hand')
    mana(s, U=1, B=1, C=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[])
    settle(s)
    native = put(s, 'Ninja of the Deep Hours', 'hand')
    granted = put(s, 'Grizzly Bears', 'hand')
    yuriko = put(s, "Yuriko, the Tiger's Shadow", 'hand')
    attacker = token_of(s, 'p1', 'Rat', 'Token Creature — Rat', '1/1', 'Haste')
    act(s, 'p1', type='set_prefs', stops_my_turn=['main1', 'declare_blockers', 'main2'])
    attack(s, attacker)
    for _ in range(40):
        d = s.state.rules.decision
        if d and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
            break
        if s.state.turn.phase == 'declare_blockers' and d is None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('did not reach blockers')
    top = [put(s, n, 'library') for n in ['Forest', 'Island', 'Lightning Bolt']]
    for c in reversed(top):
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    return s, source, native, granted, yuriko, attacker, top


def activate(s, creature):
    from app.rules.plan import Plan

    ch = Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[creature.id])
    ability = next(a.index for a in ch.abilities if ninjutsu.cost_of(ch, a.index) is not None)
    mana(s, U=1, B=1, C=2)
    act(s, 'p1', type='activate_ability', card_id=creature.id, ability=ability)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('kind', ['native', 'granted', 'commander', 'command_zone'])
def test_actual_keyword_activations_trigger_selection_above_ninjutsu(cards, kind):
    s, _, native, granted, yuriko, _, top = setup(cards)
    creature = {'native': native, 'granted': granted, 'commander': yuriko, 'command_zone': yuriko}[kind]
    if kind == 'command_zone':
        act(s, 'p1', type='set_commander', card_id=yuriko.id, value=True)
        act(s, 'p1', type='move', card_ids=[yuriko.id], to={'player': 'p1', 'zone': 'command'})
    activate(s, creature)
    settle(s)
    d = s.state.rules.decision
    assert d and {o.card_id for o in d.options} == {c.id for c in top}
    assert s.state.cards[creature.id].zone == ('p1:command' if kind == 'command_zone' else 'p1:hand')  # Ninjutsu remains below the Satoru trigger.
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[1].id])
    settle(s)
    d = s.state.rules.decision
    if d:
        assert {o.id for o in d.options} == {top[0].id, top[2].id}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[2].id, top[0].id])
        settle(s)
    assert s.state.cards[top[1].id].zone == 'p1:hand'
    assert s.state.zones['p1:library'][-2:] == [top[2].id, top[0].id]
    assert s.state.cards[creature.id].zone == 'p1:battlefield'
    roundtrip(s)


def finish_selection(s, top):
    settle(s)
    d = s.state.rules.decision
    assert d and {o.card_id for o in d.options} == {c.id for c in top}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[1].id])
    settle(s)
    d = s.state.rules.decision
    if d:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[top[2].id, top[0].id])
        settle(s)


def test_second_ninjutsu_same_turn_does_not_trigger_again(cards):
    s, _, native, granted, _, _, top = setup(cards)
    activate(s, native)
    finish_selection(s, top)
    before = len(s.state.zones['p1:hand'])
    activate(s, granted)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[granted.id].zone == 'p1:battlefield'
    assert s.state.cards[native.id].zone == 'p1:hand'
    assert len(s.state.zones['p1:hand']) == before  # One hand card enters, one returns; no new selection.
    roundtrip(s)


def test_other_activation_does_not_trigger_or_consume_ninjutsu_limit(cards):
    s, _, native, _, _, _, top = setup(cards)
    mage = put(s, 'Azure Mage', 'battlefield')
    mana(s, U=1, C=3)
    act(s, 'p1', type='activate_ability', card_id=mage.id, ability=0)
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[top[0].id].zone == 'p1:hand'
    # Restore three known cards after the independent draw.
    for c in reversed(top):
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    activate(s, native)
    finish_selection(s, top)
    roundtrip(s)


def test_trigger_survives_source_leaving_after_activation(cards):
    s, source, native, _, _, _, top = setup(cards)
    activate(s, native)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    finish_selection(s, top)
    assert s.state.cards[top[1].id].zone == 'p1:hand'
    assert s.state.cards[native.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_countering_selection_still_consumes_once_per_turn_limit(cards):
    s, _, native, granted, _, _, top = setup(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    activate(s, native)
    trigger = next(cid for cid, entry in s.state.rules.stack.items() if entry.name == NAME)
    stifle = put(s, 'Stifle', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', U=1)
    act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[trigger])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[top[1].id].zone == 'p1:library'
    activate(s, granted)
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[top[1].id].zone == 'p1:library'
    roundtrip(s)


def test_ninjutsu_trigger_limit_resets_next_turn(cards):
    from tests.test_rules_wave30m_durations import to_phase
    from tests.test_rules_wave33a_turn_triggers import attack

    s, _, native, granted, _, _, top = setup(cards)
    activate(s, native)
    finish_selection(s, top)
    activate(s, granted)
    settle(s)
    to_phase(s, 'main1', turn=4)
    attack(s, granted)
    for _ in range(40):
        d = s.state.rules.decision
        if d and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
            break
        if s.state.turn.phase == 'declare_blockers' and d is None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    for c in reversed(top):
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    activate(s, native)
    finish_selection(s, top)
    assert s.state.cards[top[1].id].zone == 'p1:hand'
    roundtrip(s)


def test_returning_satoru_as_ninjutsu_cost_does_not_trigger_departed_source(cards):
    from tests.test_rules_wave30m_durations import to_phase
    from tests.test_rules_wave33a_turn_triggers import attack

    s, source, native, _, _, _, top = setup(cards)
    to_phase(s, 'main1', turn=4)
    attack(s, source)
    for _ in range(40):
        d = s.state.rules.decision
        if d and d.kind == 'declare_blockers':
            act(s, d.player, type='declare_blockers', blocks=[])
            break
        if s.state.turn.phase == 'declare_blockers' and d is None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    activate(s, native)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert s.state.cards[native.id].zone == 'p1:battlefield'
    assert s.state.cards[top[1].id].zone == 'p1:library'
    roundtrip(s)
