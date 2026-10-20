"""CR 500.8, 603.4, 603.7b: conditional extra combat and the next attack watch."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/conditional_extra_combat_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



ATTACK = 'Overpowering Attack'
ASSAULT = 'All-Out Assault'


@pytest.mark.parametrize('name', [ATTACK, ASSAULT])
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [ATTACK, ASSAULT, 'Grizzly Bears', 'Ornithopter', 'Vedalken Orrery'], ['Grizzly Bears'], [])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    idle = put(s, 'Ornithopter', 'battlefield')
    opponent = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    return s, bear, idle, opponent


def attack(s, bear):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle, until

    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p3'}])
    settle(s)


def cast(s, name):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put

    card = put(s, name, 'hand')
    mana(s, C=3, R=2, W=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=card.id)
    settle(s)
    return card


def test_overpowering_postcombat_untaps_only_your_current_creatures_that_attacked(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, bear, idle, opponent = setup(cards)
    attack(s, bear)
    to_phase(s, 'main2', turn=4)
    act(s, 'p1', type='tap', card_ids=[idle.id, opponent.id], tapped=True)
    cast(s, ATTACK)
    assert not s.state.cards[bear.id].tapped
    assert s.state.cards[idle.id].tapped and s.state.cards[opponent.id].tapped
    assert s.state.rules.extra_phases == ['begin_combat', 'main2', 'end']
    attack(s, bear)
    until(s, lambda s: s.state.turn.phase == 'main2' and s.state.rules.decision is None)
    assert s.state.players['p3'].life == 36
    assert s.state.turn.number == 4
    roundtrip(s)


def test_overpowering_outside_main_still_untaps_without_adding_phases(cards):
    from tests.test_rules_designations import put, roundtrip

    s, bear, _, _ = setup(cards)
    put(s, 'Vedalken Orrery', 'battlefield')
    attack(s, bear)
    assert s.state.cards[bear.id].tapped
    cast(s, ATTACK)
    assert not s.state.cards[bear.id].tapped
    assert not s.state.rules.extra_phases
    roundtrip(s)


@pytest.mark.parametrize('source_leaves', [False, True])
def test_all_out_assault_creates_delayed_untap_for_next_attack_only(cards, source_leaves):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import until
    from tests.test_rules_designations import roundtrip

    s, bear, idle, opponent = setup(cards)
    act(s, 'p1', type='tap', card_ids=[idle.id, opponent.id], tapped=True)
    source = cast(s, ASSAULT)
    if source_leaves:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert s.state.rules.extra_phases == ['begin_combat', 'main2', 'begin_combat']
    assert any(t.once and t.until_turn == 4 for t in s.state.rules.delayed)
    attack(s, bear)
    assert not s.state.cards[bear.id].tapped and not s.state.cards[idle.id].tapped
    assert s.state.cards[opponent.id].tapped
    assert not s.state.rules.delayed
    roundtrip(s)
    until(s, lambda s: s.state.turn.phase == 'main2' and s.state.rules.decision is None)
    act(s, 'p1', type='tap', card_ids=[idle.id], tapped=True)
    # Natural combat after the added main phase is a second attack this turn.
    attack(s, bear)
    assert s.state.cards[bear.id].tapped and s.state.cards[idle.id].tapped
    roundtrip(s)


def test_all_out_intervening_if_rechecks_when_etb_trigger_resolves(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip

    s, _, _, _ = setup(cards)
    card = put(s, ASSAULT, 'hand')
    mana(s, C=2, R=1, W=1, B=1)
    act(s, 'p1', type='cast_spell', card_id=card.id)
    until(s, lambda s: s.state.cards[card.id].zone == 'p1:battlefield' and bool(s.state.zones.get('stack')))
    act(s, 'p1', type='phase', to='begin_combat')
    settle(s)
    assert not s.state.rules.extra_phases and not s.state.rules.delayed
    roundtrip(s)


def test_all_out_entering_during_opponents_main_creates_no_combat_or_watch(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, _, _, _ = setup(cards)
    put(s, 'Vedalken Orrery', 'battlefield')
    to_phase(s, 'main1', turn=5)
    wait_priority(s, 'p1')
    cast(s, ASSAULT)
    assert not s.state.rules.extra_phases and not s.state.rules.delayed
    roundtrip(s)


def test_overpowering_does_not_untap_a_formerly_controlled_attacker(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip
    from tests.test_rules_wave30m_durations import to_phase

    s, bear, _, _ = setup(cards)
    attack(s, bear)
    to_phase(s, 'main2', turn=4)
    act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p2')
    cast(s, ATTACK)
    assert s.state.cards[bear.id].tapped
    roundtrip(s)


def test_delayed_attack_untap_uses_creatures_controlled_when_it_resolves(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, bear, _, opponent = setup(cards)
    cast(s, ASSAULT)
    act(s, 'p2', type='set_controller', card_ids=[opponent.id], player='p1')
    act(s, 'p1', type='tap', card_ids=[opponent.id], tapped=True)
    attack(s, bear)
    assert not s.state.cards[opponent.id].tapped
    roundtrip(s)
