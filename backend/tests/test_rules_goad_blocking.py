"""CR 701.15, 509.1b: conditional blocking restrictions for goaded creatures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/goad_blocking_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_quasit_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Bothersome Quasit')).level == 'FULL'


def check_block(s, blocker, attacker, forbidden):
    from app.rules.combat import block_problem
    from app.rules.plan import Plan

    plan = Plan(s.state, blocker.controller, s.cards, None)
    b, a = s.state.cards[blocker.id], s.state.cards[attacker.id]
    reason = block_problem(s.state, b, plan.ch(b), a, plan.ch(a), s.cards)
    assert bool(reason) == forbidden, reason
    if forbidden:
        assert 'goaded' in reason


@pytest.mark.parametrize('quasit_first', [True, False])
def test_continuous_goad_blocks_regardless_of_source_timestamp_and_ends_with_goad(cards, quasit_first):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Bothersome Quasit', 'Grizzly Bears'], ['Grizzly Bears', 'Bloodthirsty Blade'])
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    if quasit_first:
        put(s, 'Bothersome Quasit', 'battlefield')
    blade = put(s, 'Bloodthirsty Blade', 'battlefield', 'p2')
    act(s, 'p2', type='attach', card_ids=[blade.id], to=blocker.id)
    if not quasit_first:
        put(s, 'Bothersome Quasit', 'battlefield')
    check_block(s, blocker, attacker, True)
    roundtrip(s)
    act(s, 'p2', type='move', card_ids=[blade.id], to={'player': 'p2', 'zone': 'graveyard'})
    check_block(s, blocker, attacker, False)
    roundtrip(s)


@pytest.mark.parametrize('quasit_first', [True, False])
def test_resolved_goad_then_source_departure(cards, quasit_first):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Bothersome Quasit', 'Grizzly Bears', 'Disrupt Decorum'], ['Grizzly Bears'])
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    check_block(s, blocker, attacker, False)
    if quasit_first:
        source = put(s, 'Bothersome Quasit', 'battlefield')
    spell = put(s, 'Disrupt Decorum', 'hand')
    mana(s, R=4)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    if quasit_first:
        d = s.state.rules.decision
        assert d and any(o.id == blocker.id for o in d.options)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[blocker.id])
        settle(s)
    else:
        source = put(s, 'Bothersome Quasit', 'battlefield')
    check_block(s, blocker, attacker, True)
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    check_block(s, blocker, attacker, False)
    roundtrip(s)


def test_only_opponents_goaded_creatures_are_restricted_and_control_changes_apply(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Bothersome Quasit', 'Grizzly Bears', 'Bloodthirsty Blade'], ['Grizzly Bears', 'Bloodthirsty Blade'])
    put(s, 'Bothersome Quasit', 'battlefield')
    own = put(s, 'Grizzly Bears', 'battlefield')
    opponent = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    for pid, creature in [('p1', own), ('p2', opponent)]:
        blade = put(s, 'Bloodthirsty Blade', 'battlefield', pid)
        act(s, pid, type='attach', card_ids=[blade.id], to=creature.id)
    check_block(s, own, opponent, False)
    check_block(s, opponent, own, True)
    act(s, 'p2', type='set_controller', card_ids=[opponent.id], player='p1')
    check_block(s, opponent, own, False)
    roundtrip(s)


def test_blocker_declaration_rejects_goaded_blocker_then_allows_after_quasit_leaves(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only, until_block
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Bothersome Quasit', 'Grizzly Bears'], ['Grizzly Bears', 'Bloodthirsty Blade'])
    attacker = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    source = put(s, 'Bothersome Quasit', 'battlefield')
    blade = put(s, 'Bloodthirsty Blade', 'battlefield', 'p2')
    act(s, 'p2', type='attach', card_ids=[blade.id], to=blocker.id)
    put(s, "Atraxa, Praetors' Voice", 'battlefield', 'p2')
    declare_only(s, [attacker], {})
    until_block(s)
    d = s.state.rules.decision
    assert d and d.kind == 'declare_blockers' and d.player == 'p2'
    blocks = [{'blocker_id': blocker.id, 'attacker_id': attacker.id}]
    with pytest.raises(ActionError, match='goaded'):
        act(s, 'p2', type='declare_blockers', blocks=blocks)
    assert s.state.rules.decision.id == d.id and not s.state.cards[blocker.id].blocking
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p2', type='declare_blockers', blocks=blocks)
    assert s.state.cards[blocker.id].blocking == attacker.id
    roundtrip(s)
