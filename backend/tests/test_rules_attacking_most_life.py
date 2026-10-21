"""CR 603.4, 608.2h: Scourge checks current defending-player life twice."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/attacking_most_life_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Scourge of the Throne'


def setup(cards, life=(40, 40, 40)):
    from tests.game_helpers import act
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Grizzly Bears', 'Ornithopter', 'Relentless Assault', 'Invasion of Zendikar // Awakened Skyclave'], ['Jace Beleren'], [])
    dragon = put(s, NAME, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    idle = put(s, 'Ornithopter', 'battlefield')
    to_phase(s, 'main1', turn=4)
    for pid, n in zip(['p1', 'p2', 'p3'], life, strict=True):
        act(s, 'p1', type='set_life', player=pid, value=n)
    return s, dragon, bear, idle


def attack(s, dragon, bear, target='p2'):
    from tests.game_helpers import act
    from tests.test_rules_banding import attack_step

    attack_step(s)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': dragon.id, 'target': target}, {'card_id': bear.id, 'target': 'p3'}])


def test_scourge_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('life,works', [((40, 40, 40), True), ((30, 40, 35), True), ((40, 40, 30), True),
                                      ((41, 40, 30), False), ((30, 40, 41), False)])
def test_highest_life_includes_controller_and_ties(cards, life, works):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, dragon, bear, idle = setup(cards, life)
    act(s, 'p1', type='tap', card_ids=[idle.id], tapped=True)
    attack(s, dragon, bear)
    settle(s)
    assert bool(s.state.rules.extra_phases) == works
    assert s.state.cards[dragon.id].tapped != works
    assert s.state.cards[bear.id].tapped != works
    assert s.state.cards[idle.id].tapped
    assert s.state.cards[dragon.id].counters.get('+1/+1', 0) == int(works)
    roundtrip(s)


@pytest.mark.parametrize('higher', ['p1', 'p3'])
def test_intervening_if_rechecks_but_dethrone_does_not(cards, higher):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, dragon, bear, _ = setup(cards)
    attack(s, dragon, bear)
    act(s, 'p1', type='set_life', player=higher, value=41)
    settle(s)
    assert not s.state.rules.extra_phases
    assert s.state.cards[dragon.id].tapped
    assert s.state.cards[dragon.id].counters.get('+1/+1') == 1
    roundtrip(s)


@pytest.mark.parametrize('change', ['removed', 'departed', 'blinked'])
def test_source_combat_state_uses_current_object_or_old_object_lki(cards, change):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, dragon, bear, _ = setup(cards)
    attack(s, dragon, bear)
    if change == 'removed':
        act(s, 'p1', type='attack', card_ids=[dragon.id], target=None)
    else:
        act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'graveyard'})
        if change == 'blinked':
            act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert bool(s.state.rules.extra_phases) == (change != 'removed')
    assert s.state.cards[bear.id].tapped == (change == 'removed')
    if change == 'blinked':
        assert not s.state.cards[dragon.id].counters
    roundtrip(s)


def test_attacking_planeswalker_does_not_qualify(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, dragon, bear, _ = setup(cards)
    pw = put(s, 'Jace Beleren', 'battlefield', 'p2')
    act(s, 'p2', type='set_counter', card_id=pw.id, kind='loyalty', value=3)
    attack(s, dragon, bear, pw.id)
    settle(s)
    assert not s.state.rules.extra_phases
    assert not s.state.cards[dragon.id].counters
    roundtrip(s)


@pytest.mark.parametrize('first_qualifies', [False, True])
def test_only_the_first_attack_counts_even_when_first_condition_failed(cards, first_qualifies):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_conditionals import settle, until
    from tests.test_rules_designations import put, roundtrip

    s, dragon, bear, _ = setup(cards, (40 if first_qualifies else 41, 40, 40))
    attack(s, dragon, bear)
    settle(s)
    if not first_qualifies:
        until(s, lambda s: s.state.turn.phase == 'main2' and s.state.rules.decision is None)
        assault = put(s, 'Relentless Assault', 'hand')
        mana(s, C=2, R=2)
        act(s, 'p1', type='cast_spell', card_id=assault.id)
        settle(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_attackers')
    for pid in ['p1', 'p2', 'p3']:
        act(s, 'p1', type='set_life', player=pid, value=40)
    before = list(s.state.rules.extra_phases)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': dragon.id, 'target': 'p2'}, {'card_id': bear.id, 'target': 'p3'}])
    settle(s)
    assert s.state.rules.extra_phases == before
    assert s.state.cards[dragon.id].tapped
    assert s.state.cards[bear.id].tapped
    assert s.state.cards[dragon.id].counters.get('+1/+1') == 1 + int(first_qualifies)
    roundtrip(s)


def test_attacking_battle_does_not_qualify_even_when_protector_has_most_life(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, dragon, bear, _ = setup(cards)
    siege = put(s, 'Invasion of Zendikar // Awakened Skyclave', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=siege.id, kind='defense', value=4)
    attack(s, dragon, bear, siege.id)
    settle(s)
    assert not s.state.rules.extra_phases
    assert not s.state.cards[dragon.id].counters
    roundtrip(s)
