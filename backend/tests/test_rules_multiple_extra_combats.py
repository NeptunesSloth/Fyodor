"""CR 500.8, 603.7b: consecutive combats and a repeating turn-long untap."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/multiple_extra_combats_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Full Throttle'


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Grizzly Bears', 'Ornithopter', 'Vedalken Orrery'], ['Grizzly Bears'], [])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    idle = put(s, 'Ornithopter', 'battlefield')
    spell = put(s, NAME, 'hand')
    to_phase(s, 'main1', turn=4)
    return s, spell, bear, idle


def cast(s, spell):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle

    mana(s, C=4, R=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)


def attack_next(s, bear):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle, until

    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_attackers')
    act(s, s.state.rules.decision.player, type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    settle(s)


def test_full_throttle_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('phase', ['main1', 'main2'])
def test_two_consecutive_extra_combats_and_repeating_untap(cards, phase):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, spell, bear, idle = setup(cards)
    if phase == 'main2':
        attack_next(s, bear)
        to_phase(s, 'main2', turn=4)
        assert s.state.players['p2'].life == 38
    act(s, 'p1', type='tap', card_ids=[idle.id], tapped=True)
    cast(s, spell)
    assert s.state.rules.extra_phases == ['begin_combat', 'begin_combat', 'begin_combat' if phase == 'main1' else 'end']
    assert any(not t.once and t.until_turn == 4 for t in s.state.rules.delayed)
    start_life = s.state.players['p2'].life
    for _ in range(3 if phase == 'main1' else 2):
        until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_attackers')
        assert not s.state.cards[bear.id].tapped
        assert s.state.cards[idle.id].tapped
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
        roundtrip(s)
    until(s, lambda s: s.state.turn.phase == ('main2' if phase == 'main1' else 'end') and s.state.rules.decision is None)
    assert s.state.players['p2'].life == start_life - (6 if phase == 'main1' else 4)
    assert s.state.turn.number == 4
    assert s.state.rules.combats == 3
    to_phase(s, 'main1', turn=5)
    assert not s.state.rules.delayed
    roundtrip(s)


def test_cast_during_combat_creates_watch_without_extra_phases_or_immediate_untap(cards):
    from tests.test_rules_designations import put, roundtrip

    s, spell, bear, _ = setup(cards)
    put(s, 'Vedalken Orrery', 'battlefield')
    attack_next(s, bear)
    assert s.state.cards[bear.id].tapped
    cast(s, spell)
    assert not s.state.rules.extra_phases
    assert s.state.cards[bear.id].tapped
    assert any(not t.once and t.until_turn == 4 for t in s.state.rules.delayed)
    roundtrip(s)


def test_opponents_main_phase_adds_combats_for_active_opponent(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, spell, _, _ = setup(cards)
    put(s, 'Vedalken Orrery', 'battlefield')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=5)
    wait_priority(s, 'p1')
    cast(s, spell)
    assert s.state.rules.extra_phases == ['begin_combat', 'begin_combat', 'begin_combat']
    for _ in range(3):
        until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_attackers')
        assert s.state.rules.decision.player == 'p2'
        assert not s.state.cards[attacker.id].tapped
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': attacker.id, 'target': 'p3'}])
    until(s, lambda s: s.state.turn.phase == 'main2' and s.state.rules.decision is None)
    assert s.state.players['p3'].life == 34
    assert s.state.turn.number == 5
    roundtrip(s)
