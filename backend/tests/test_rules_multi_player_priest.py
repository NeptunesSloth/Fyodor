"""CR 115.1c, 601.2c, 608.2b: optional player targets and independent controller instructions."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/multi_player_priest_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Priest of Forgotten Gods'


def black_mana(s):
    p = s.state.players['p1']
    return p.mana.get('B', 0) + sum(u.sym == 'B' for u in p.mana_units)


def setup(cards):
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [NAME, 'Grizzly Bears', 'Ornithopter'], ['Grizzly Bears', 'Leyline of Sanctity', 'Stifle'], ['Grizzly Bears'])
    priest = put(s, NAME, 'battlefield')
    payments = [put(s, n, 'battlefield') for n in ['Grizzly Bears', 'Ornithopter']]
    others = [put(s, 'Grizzly Bears', 'battlefield', pid) for pid in ['p2', 'p3']]
    to_phase(s, 'main1', turn=4)
    return s, priest, payments, others


def activate(s, priest, payments, targets):
    from tests.game_helpers import act

    act(s, 'p1', type='activate_ability', card_id=priest.id, ability=0, targets=targets, target_counts=[len(targets)],
        cost_choices=[{'component': 1, 'cards': [c.id for c in payments]}])


def test_priest_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('targets', [[], ['p2'], ['p2', 'p3'], ['p1', 'p2', 'p3']])
def test_any_number_including_zero_and_yourself(cards, targets):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, priest, payments, others = setup(cards)
    before = len(s.state.zones['p1:hand'])
    activate(s, priest, payments, targets)
    assert s.state.zones['stack']  # Targeting makes this an ordinary activated ability, CR 605.1a.
    assert black_mana(s) == 0
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in payments)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    assert black_mana(s) == 2
    for pid in ['p1', 'p2', 'p3']:
        assert s.state.players[pid].life == 40 - (2 if pid in targets else 0)
    for c in others:
        assert s.state.cards[c.id].zone == f'{c.owner}:' + ('graveyard' if c.owner in targets else 'battlefield')
    if 'p1' in targets:
        assert s.state.cards[priest.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('all_illegal', [False, True])
def test_targets_rechecked_and_all_illegal_counters_the_whole_ability(cards, all_illegal):
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, priest, payments, others = setup(cards)
    before = len(s.state.zones['p1:hand'])
    activate(s, priest, payments, ['p2'] if all_illegal else ['p2', 'p3'])
    put(s, 'Leyline of Sanctity', 'battlefield', 'p2')
    settle(s)
    assert s.state.players['p2'].life == 40
    assert s.state.cards[others[0].id].zone == 'p2:battlefield'
    assert s.state.players['p3'].life == (40 if all_illegal else 38)
    assert len(s.state.zones['p1:hand']) == before + (0 if all_illegal else 1)
    assert black_mana(s) == (0 if all_illegal else 2)
    roundtrip(s)


def test_cannot_pay_sacrifice_with_priest_itself(cards):
    from app.game.errors import ActionError
    from tests.test_rules_designations import roundtrip

    s, priest, payments, _ = setup(cards)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        activate(s, priest, [priest, payments[0]], ['p2'])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_duplicate_targets_rejected_without_paying(cards):
    from app.game.errors import ActionError
    from tests.test_rules_designations import roundtrip

    s, priest, payments, _ = setup(cards)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        activate(s, priest, payments, ['p2', 'p2'])
    assert s.state.model_dump_json() == before
    roundtrip(s)


def test_stifle_counters_ability_after_sacrifices_without_mana_or_draw(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import put, roundtrip

    s, priest, payments, others = setup(cards)
    before = len(s.state.zones['p1:hand'])
    activate(s, priest, payments, ['p2', 'p3'])
    stacked = s.state.zones['stack'][0]
    stifle = put(s, 'Stifle', 'hand', 'p2')
    mana(s, 'p2', U=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[stacked])
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in payments)
    assert all(s.state.cards[c.id].zone == f'{c.owner}:battlefield' for c in others)
    assert all(s.state.players[pid].life == 40 for pid in ['p1', 'p2', 'p3'])
    assert black_mana(s) == 0
    assert len(s.state.zones['p1:hand']) == before
    roundtrip(s)
