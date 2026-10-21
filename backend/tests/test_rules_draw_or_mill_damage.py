"""CR 608.2d, 701.13, 202.3: opponent choices and milled-card mana values."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/draw_or_mill_damage_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_gearhulk_is_full(cards):
    assert coverage.of_card_data(cards.resolve('Combustible Gearhulk')).level == 'FULL'


def setup_trigger(cards, names, *, rest_in_peace=False, target='p2', leave=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Combustible Gearhulk', *names, *(['Rest in Peace'] if rest_in_peace else [])], [], [])
    source = put(s, 'Combustible Gearhulk', 'hand')
    chosen = []
    for name in names:
        chosen.append(next(c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == name and c.id not in chosen and c.id != source.id))
    if s.state.zones.get('p1:library'):
        act(s, 'p1', type='move', card_ids=list(s.state.zones['p1:library']), to={'player': 'p1', 'zone': 'exile'})
    if chosen:
        act(s, 'p1', type='move', card_ids=chosen, to={'player': 'p1', 'zone': 'library'}, index=0)
    if rest_in_peace:
        put(s, 'Rest in Peace', 'battlefield')
    mana(s, R=6)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1' and target in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target])
    if leave:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    return s, source, chosen


def answer(s, choice):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    d = s.state.rules.decision
    assert d
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[choice])
    settle(s)


@pytest.mark.parametrize('target', ['p2', 'p3'])
@pytest.mark.parametrize('draw', [False, True])
def test_targeted_opponent_chooses_casters_draw_or_takes_total_mana_value_damage(cards, target, draw):
    from tests.test_rules_designations import roundtrip

    s, _, chosen = setup_trigger(cards, ['Grizzly Bears', 'Sol Ring', 'Island'], target=target)
    d = s.state.rules.decision
    assert d and d.player == target
    before = len(s.state.zones['p1:hand'])
    answer(s, 'pay' if draw else 'decline')
    assert s.state.players[target].life == (40 if draw else 37)
    assert s.state.players['p3' if target == 'p2' else 'p2'].life == 40
    assert len(s.state.zones['p1:hand']) == before + (3 if draw else 0)
    assert all(s.state.cards[cid].zone == ('p1:hand' if draw else 'p1:graveyard') for cid in chosen)
    roundtrip(s)


@pytest.mark.parametrize('names,total', [(['Fire // Ice', 'Walking Ballista', 'Grizzly Bears'], 6),
                                       (['Grizzly Bears'], 2), ([], 0)])
def test_mana_values_use_all_milled_cards_with_split_and_x_cost_rules_and_short_libraries(cards, names, total):
    from tests.test_rules_designations import roundtrip

    s, _, _ = setup_trigger(cards, names)
    answer(s, 'decline')
    assert s.state.players['p2'].life == 40 - total
    assert 'p1' not in s.state.rules.lost
    roundtrip(s)


def test_graveyard_exile_replacement_still_counts_milled_cards(cards):
    from tests.test_rules_designations import roundtrip

    s, _, chosen = setup_trigger(cards, ['Grizzly Bears', 'Sol Ring', 'Island'], rest_in_peace=True)
    answer(s, 'decline')
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in chosen)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_source_departure_keeps_trigger_and_damage_source_information(cards):
    from tests.test_rules_designations import roundtrip

    s, source, _ = setup_trigger(cards, ['Grizzly Bears', 'Sol Ring', 'Island'], leave=True)
    answer(s, 'decline')
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_self_shuffle_replacement_keeps_milled_mana_value(cards):
    from tests.test_rules_designations import roundtrip

    s, _, chosen = setup_trigger(cards, ['Blightsteel Colossus', 'Sol Ring', 'Island'])
    answer(s, 'decline')
    assert any(c.name == 'Blightsteel Colossus' and c.zone == 'p1:library' for c in s.state.cards.values())
    assert all(s.state.cards[cid].zone == 'p1:graveyard' for cid in chosen[1:])
    assert s.state.players['p2'].life == 27
    roundtrip(s)


@pytest.mark.parametrize('names', [[], ['Island']])
def test_opponent_can_choose_draw_even_when_caster_cannot_draw_three(cards, names):
    from tests.test_rules_designations import roundtrip

    s, _, _ = setup_trigger(cards, names)
    answer(s, 'pay')
    assert 'p1' in s.state.rules.lost
    assert s.state.players['p2'].life == 40
    roundtrip(s)
