"""CR 111.2, 608.2h: conditional attached copy and actual creation fallback."""
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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/faithbound_judge_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = "Faithbound Judge // Sinner's Judgment"


def setup(cards, curse=False):
    from app.rules import disturb

    s = table(cards, [NAME, 'Murder', 'Disenchant'])
    source = put(s, NAME, 'graveyard' if curse else 'hand')
    mana(s, C=5 if curse else 1, W=2)
    extra = {}
    if curse:
        [offer] = disturb.offers(s.state, 'p1', source, s.cards)
        extra = {'alt_cost': offer.key, 'targets': ['p2']}
    act(s, 'p1', type='cast_spell', card_id=source.id, **extra)
    settle(s)
    assert s.state.cards[source.id].face == int(curse)
    return s, source


def phase(s, turn, step='main1'):
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, step, turn=turn)
    if step != 'upkeep':
        settle(s)


def test_full_canonical_double_faced_card(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_front_upkeep_counters_cap_at_three_and_allow_attack(cards):
    from app.game.errors import ActionError
    from tests.test_rules_wave6c_tokens_pumps import chars
    from tests.test_rules_wave30m_durations import to_phase

    s, source = setup(cards)
    assert chars(s, source).pt == (4, 4)
    for turn, n in [(4, 1), (7, 2)]:
        phase(s, turn)
        assert s.state.cards[source.id].counters == {'judgment': n}
        roundtrip(s)
    to_phase(s, 'declare_attackers', turn=7)
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    phase(s, 10)
    assert s.state.cards[source.id].counters == {'judgment': 3}
    to_phase(s, 'declare_attackers', turn=10)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    assert s.state.cards[source.id].attacking is not None
    assert 'defender' in chars(s, source).keywords and not s.state.cards[source.id].tapped
    phase(s, 13)
    assert s.state.cards[source.id].counters == {'judgment': 3}
    roundtrip(s)


def test_disturbed_curse_ticks_on_controller_upkeep_and_loses_enchanted_player(cards):
    s, source = setup(cards, curse=True)
    assert s.state.cards[source.id].attached_player == 'p2'
    phase(s, 2)
    assert s.state.cards[source.id].counters == {}
    for turn, n in [(4, 1), (7, 2)]:
        phase(s, turn)
        assert s.state.cards[source.id].counters == {'judgment': n}
        roundtrip(s)
    phase(s, 10)
    assert 'p2' in s.state.rules.lost and 'p3' not in s.state.rules.lost
    roundtrip(s)


@pytest.mark.parametrize('count,loses', [(2, False), (3, True)])
def test_curse_removed_in_response_uses_last_known_counter_count_and_player(cards, count, loses):
    from tests.test_rules_bandmate_references import wait_priority

    s, source = setup(cards, curse=True)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='judgment', value=count)
    phase(s, 4, 'upkeep')
    wait_priority(s, 'p1')
    spell = put(s, 'Disenchant', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'  # Curse's own graveyard replacement.
    assert ('p2' in s.state.rules.lost) == loses and 'p3' not in s.state.rules.lost
    roundtrip(s)


def test_curse_uses_current_enchanted_player_when_it_remains_on_battlefield(cards):
    s, source = setup(cards, curse=True)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='judgment', value=2)
    phase(s, 4, 'upkeep')
    act(s, 'p1', type='attach', card_ids=[source.id], to='p3')
    settle(s)
    assert 'p3' in s.state.rules.lost and 'p2' not in s.state.rules.lost
    roundtrip(s)


def test_curse_upkeep_follows_its_controller_after_control_change(cards):
    s, source = setup(cards, curse=True)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    phase(s, 2)
    assert s.state.cards[source.id].counters == {'judgment': 1}
    phase(s, 4)
    assert s.state.cards[source.id].counters == {'judgment': 1}
    phase(s, 5)
    assert s.state.cards[source.id].counters == {'judgment': 2}
    roundtrip(s)


def test_front_dies_normally_then_actual_disturb_casts_curse_face(cards):
    from app.rules import disturb

    s, source = setup(cards)
    kill = put(s, 'Murder', 'hand')
    mana(s, C=1, B=2)
    act(s, 'p1', type='cast_spell', card_id=kill.id, targets=[source.id])
    settle(s)
    current = s.state.cards[source.id]
    assert current.zone == 'p1:graveyard' and current.face == 0
    [offer] = disturb.offers(s.state, 'p1', current, s.cards)
    mana(s, C=5, W=2)
    act(s, 'p1', type='cast_spell', card_id=current.id, alt_cost=offer.key, targets=['p3'])
    settle(s)
    current = s.state.cards[source.id]
    assert current.zone == 'p1:battlefield' and current.face == 1 and current.attached_player == 'p3'
    roundtrip(s)
