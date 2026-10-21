"""CR 101.4, 701.23: each targeted player searches their own library."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/multi_target_search_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Scheming Symmetry'


def test_symmetry_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_search(cards, targets, *, barred=False, empty=None):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Grizzly Bears'], ['Sol Ring'], ['Grizzly Bears', 'Ashiok, Dream Render'])
    source = put(s, NAME, 'hand')
    if barred:
        ash = put(s, 'Ashiok, Dream Render', 'battlefield', 'p3')
        act(s, 'p3', type='set_counter', card_id=ash.id, kind='loyalty', value=5)
    if empty:
        act(s, empty, type='move', card_ids=list(s.state.zones[f'{empty}:library']), to={'player': empty, 'zone': 'exile'})
    mana(s, B=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=targets, target_counts=[2])
    settle(s)
    return s


@pytest.mark.parametrize('targets', [['p1', 'p2'], ['p3', 'p1'], ['p3', 'p2']])
def test_each_target_searches_privately_in_apnap_order_and_puts_card_on_top(cards, targets):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s = setup_search(cards, targets)
    order = [p for p in ['p1', 'p2', 'p3'] if p in targets]
    selected = {}
    for pid in order:
        d = s.state.rules.decision
        assert d and d.player == pid
        assert d.min_choices == d.max_choices == 1
        assert all(s.state.cards[o.card_id].owner == pid for o in d.options if o.card_id)
        for other in ['p1', 'p2', 'p3']:
            if other != pid:
                assert not s.view(other)['rules']['decision'].get('options')
        pick = next(o for o in d.options if o.card_id)
        selected[pid] = s.state.cards[pick.card_id].name
        roundtrip(s)
        act(s, pid, type='choose', decision_id=d.id, option_ids=[pick.id])
        settle(s)
    assert s.state.rules.decision is None
    for pid, name in selected.items():
        cid = s.state.zones[f'{pid}:library'][0]
        assert s.state.cards[cid].name == name
        for other in ['p1', 'p2', 'p3']:
            if other != pid:
                assert not s.view(other)['cards'].get(cid, {}).get('name')
    roundtrip(s)


def test_unqualified_search_cannot_fail_to_find_in_nonempty_library(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s = setup_search(cards, ['p1', 'p2'])
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    assert s.state.rules.decision.id == d.id
    roundtrip(s)


def test_ashiok_stops_only_the_spells_controller_search_and_both_still_shuffle(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s = setup_search(cards, ['p1', 'p2'], barred=True)
    d = s.state.rules.decision
    assert d and d.player == 'p2'
    roundtrip(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert s.state.rules.decision is None
    steps = [step for a in s.history.actions if isinstance(getattr(a, 'r', None), list) for step in a.r]
    assert [step['player'] for step in steps if step.get('type') == 'shuffle'][-2:] == ['p1', 'p2']
    roundtrip(s)


@pytest.mark.parametrize('targets', [['p1'], ['p1', 'p1'], ['p1', 'p2', 'p3']])
def test_requires_exactly_two_distinct_player_targets_before_payment(cards, targets):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME], [])
    source = put(s, NAME, 'hand')
    mana(s, B=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=targets, target_counts=[len(targets)])
    assert s.state.cards[source.id].zone == 'p1:hand' and s.state.players['p1'].mana == {'B': 1}
    roundtrip(s)


def test_empty_second_library_does_not_cancel_first_players_search(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s = setup_search(cards, ['p1', 'p2'], empty='p2')
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2' and not d.options and d.min_choices == 0
    roundtrip(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.rules.decision is None and not s.state.zones['p2:library']
    assert 'p2' not in s.state.rules.lost
    roundtrip(s)
