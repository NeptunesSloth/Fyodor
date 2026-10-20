"""CR 702.29c/f, 614.1: cycling permissions and graveyard replacements."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/conditional_search_cast_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_beseech_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Beseech the Mirror')).level == 'FULL'


@pytest.mark.parametrize('bargain', [False, True])
@pytest.mark.parametrize('accept', [False, True])
def test_beseech_casts_only_when_bargained_and_accepted_otherwise_returns_card(cards, bargain, accept):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Beseech the Mirror', 'Grizzly Bears', 'Sol Ring'], [], [])
    source = put(s, 'Beseech the Mirror', 'hand')
    bear = put(s, 'Grizzly Bears', 'library')
    ring = put(s, 'Sol Ring', 'battlefield')
    mana(s, B=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, optional_costs=[f'{source.id}:bargain'] if bargain else [])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    assert bear.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    if bargain:
        d = s.state.rules.decision
        assert d and d.player == 'p1'
        assert bear.id in {o.id for o in d.options}
        assert s.state.cards[bear.id].face_down
        # Exile remains private until casting reveals the card.
        for viewer in ['p2', 'p3']:
            visible = [c for c in s.view(viewer)['cards'].values() if c.get('name') == 'Grizzly Bears']
            assert not visible
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id] if accept else [])
        settle(s)
    assert s.state.cards[bear.id].zone == ('p1:battlefield' if bargain and accept else 'p1:hand')
    assert not s.state.cards[bear.id].face_down
    assert s.state.cards[ring.id].zone == ('p1:graveyard' if bargain else 'p1:battlefield')
    roundtrip(s)


@pytest.mark.parametrize('name', ['Hill Giant', 'Colossal Dreadmaw', 'Forest'])
def test_beseech_mana_value_boundary_and_land_cannot_be_cast(cards, name):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Beseech the Mirror', 'Sol Ring', *([] if name == 'Forest' else [name])], [], [])
    source = put(s, 'Beseech the Mirror', 'hand')
    found = put(s, name, 'library')
    put(s, 'Sol Ring', 'battlefield')
    mana(s, B=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, optional_costs=[f'{source.id}:bargain'])
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[found.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1'  # hidden-card choice is shown even if it has no legal spell
    if name == 'Hill Giant':
        assert found.id in {o.id for o in d.options}
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[found.id])
    else:
        assert not d.options
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[found.id].zone == ('p1:battlefield' if name == 'Hill Giant' else 'p1:hand')
    roundtrip(s)


def test_cancelling_cast_target_returns_searched_card_to_hand(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Beseech the Mirror', 'Giant Growth', 'Sol Ring', 'Grizzly Bears'], [], [])
    source = put(s, 'Beseech the Mirror', 'hand')
    growth = put(s, 'Giant Growth', 'library')
    put(s, 'Sol Ring', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    mana(s, B=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, optional_costs=[f'{source.id}:bargain'])
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[growth.id])
    settle(s)
    d = s.state.rules.decision
    assert d
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[growth.id])
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'cast_target'
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['cancel'])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[growth.id].zone == 'p1:hand'
    assert not s.state.cards[growth.id].face_down
    roundtrip(s)


def test_countered_beseech_does_not_search_or_refund_bargain(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Beseech the Mirror', 'Sol Ring'], ['Counterspell'], [])
    source = put(s, 'Beseech the Mirror', 'hand')
    ring = put(s, 'Sol Ring', 'battlefield')
    counter = put(s, 'Counterspell', 'hand', 'p2')
    mana(s, B=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, optional_costs=[f'{source.id}:bargain'])
    wait_priority(s, 'p2')
    mana(s, 'p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == s.state.cards[ring.id].zone == 'p1:graveyard'
    roundtrip(s)
