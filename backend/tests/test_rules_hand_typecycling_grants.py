"""CR 702.29 / 113.6: typecycling granted to cards in each players hand."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/hand_typecycling_grants_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_homing_sliver_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Homing Sliver')).level == 'FULL'


@pytest.mark.parametrize('pid', ['p1', 'p2', 'p3'])
def test_homing_sliver_grants_typecycling_to_each_players_hand_and_searches_their_library(cards, pid):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Homing Sliver', 'Metallic Sliver', 'Metallic Sliver'],
              ['Metallic Sliver', 'Metallic Sliver'], ['Metallic Sliver', 'Metallic Sliver'])
    put(s, 'Homing Sliver', 'battlefield')
    source = put(s, 'Metallic Sliver', 'hand', pid)
    own = s.view(pid)['rules']['stats'][source.id]['abilities']
    grant = next(a for a in own if a['text'] == 'Slivercycling {3}')
    assert grant['index'] >= 100
    for other in ['p1', 'p2', 'p3']:
        if other != pid:
            assert source.id not in s.view(other)['rules']['stats']
    wait_priority(s, pid)
    mana(s, pid, C=3)
    act(s, pid, type='activate_ability', card_id=source.id, ability=grant['index'])
    assert s.state.cards[source.id].zone == f'{pid}:graveyard'
    roundtrip(s)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == pid
    assert {s.state.cards[o.id].owner for o in d.options} == {pid}
    assert {s.state.cards[o.id].name for o in d.options} == {'Metallic Sliver'}
    chosen = d.options[0].id
    act(s, pid, type='choose', decision_id=d.id, option_ids=[chosen])
    settle(s)
    assert s.state.cards[chosen].zone == f'{pid}:hand'
    roundtrip(s)


def test_hand_grant_uses_changeling_and_excludes_non_slivers_without_leaking_opponent_cards(cards):
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Homing Sliver'], ['Universal Automaton', 'Grizzly Bears', 'Sol Ring'], [])
    put(s, 'Homing Sliver', 'battlefield')
    automaton = put(s, 'Universal Automaton', 'hand', 'p2')
    bear = put(s, 'Grizzly Bears', 'hand', 'p2')
    ring = put(s, 'Sol Ring', 'hand', 'p2')
    mine = s.view('p2')['rules']['stats']
    assert any(a['text'] == 'Slivercycling {3}' for a in mine[automaton.id]['abilities'])
    assert bear.id not in mine and ring.id not in mine
    for viewer in ['p1', 'p3']:
        stats = s.view(viewer)['rules']['stats']
        assert not {automaton.id, bear.id, ring.id} & set(stats)
    roundtrip(s)


def test_homing_grant_disappears_when_its_source_leaves(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Homing Sliver'], ['Metallic Sliver'], [])
    homing = put(s, 'Homing Sliver', 'battlefield')
    source = put(s, 'Metallic Sliver', 'hand', 'p2')
    index = s.view('p2')['rules']['stats'][source.id]['abilities'][0]['index']
    act(s, 'p1', type='move', card_ids=[homing.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert source.id not in s.view('p2')['rules']['stats']
    wait_priority(s, 'p2')
    mana(s, 'p2', C=3)
    with pytest.raises(ActionError):
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.cards[source.id].zone == 'p2:hand'
    roundtrip(s)


def test_existing_own_hand_cycling_grants_are_visible_only_where_they_apply(cards):
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Rhet-Tomb Mystic', 'Grizzly Bears'], ['Grizzly Bears'], [])
    put(s, 'Rhet-Tomb Mystic', 'battlefield')
    bear1 = put(s, 'Grizzly Bears', 'hand')
    bear2 = put(s, 'Grizzly Bears', 'hand', 'p2')
    assert any(a['text'] == 'Cycling {1}{U}' for a in s.view('p1')['rules']['stats'][bear1.id]['abilities'])
    assert bear2.id not in s.view('p2')['rules']['stats']
    assert bear1.id not in s.view('p2')['rules']['stats']
    roundtrip(s)


def test_stabilizer_prevents_granted_typecycling_too(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Homing Sliver', 'Stabilizer'], ['Metallic Sliver'], [])
    put(s, 'Homing Sliver', 'battlefield')
    put(s, 'Stabilizer', 'battlefield')
    source = put(s, 'Metallic Sliver', 'hand', 'p2')
    index = s.view('p2')['rules']['stats'][source.id]['abilities'][0]['index']
    wait_priority(s, 'p2')
    mana(s, 'p2', C=3)
    with pytest.raises(ActionError, match="can't cycle"):
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=index)
    assert s.state.cards[source.id].zone == 'p2:hand'
    roundtrip(s)


def test_an_activated_granted_cycle_keeps_its_search_when_the_grant_source_leaves(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Homing Sliver'], ['Metallic Sliver', 'Metallic Sliver'], [])
    homing = put(s, 'Homing Sliver', 'battlefield')
    source = put(s, 'Metallic Sliver', 'hand', 'p2')
    index = s.view('p2')['rules']['stats'][source.id]['abilities'][0]['index']
    wait_priority(s, 'p2')
    mana(s, 'p2', C=3)
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=index)
    act(s, 'p1', type='move', card_ids=[homing.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2' and d.options
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    roundtrip(s)
