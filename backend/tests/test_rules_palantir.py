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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/palantir_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_full(cards):
    assert coverage.of_card_data(cards.resolve('Palantír of Orthanc')).level == 'FULL'


def trigger(cards, names, *, counters=0, leave=False, rip=False, doubling=False, bottom=False, illegal=False):
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    extras = (['Rest in Peace'] if rip else []) + (['Doubling Season'] if doubling else [])
    s = table(cards, ['Palantír of Orthanc', 'Leyline of Sanctity', *names, *extras], [], [])
    source = put(s, 'Palantír of Orthanc', 'battlefield')
    for name in extras:
        put(s, name, 'battlefield')
    if counters:
        act(s, 'p1', type='set_counter', card_id=source.id, kind='influence', value=counters)
    chosen = []
    for name in names:
        chosen.append(next(c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == name and c.id not in chosen))
    if s.state.zones.get('p1:library'):
        act(s, 'p1', type='move', card_ids=list(s.state.zones['p1:library']), to={'player': 'p1', 'zone': 'exile'})
    if chosen:
        act(s, 'p1', type='move', card_ids=chosen, to={'player': 'p1', 'zone': 'library'}, index=0)
    to_phase(s, 'end')
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1' and 'p2' in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p2'])
    if illegal:
        shield = put(s, 'Leyline of Sanctity', 'battlefield')
        act(s, 'p1', type='set_controller', card_ids=[shield.id], player='p2')
    if leave:
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    if illegal:
        return s, source, chosen
    while s.state.rules.decision and s.state.rules.decision.player == 'p1':
        d = s.state.rules.decision
        roundtrip(s)
        if d.resume['step'] == 'look':
            ids = [d.options[0].id] if bottom else []
        else:
            ids = [o.id for o in d.options]
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=ids)
        settle(s)
    assert s.state.rules.decision and s.state.rules.decision.player == 'p2'
    return s, source, chosen


def answer(s, draw):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    d = s.state.rules.decision
    roundtrip(s)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay' if draw else 'decline'])
    settle(s)
    roundtrip(s)


@pytest.mark.parametrize('draw', [False, True])
def test_counter_scry_precede_opponent_choice(cards, draw):
    s, source, chosen = trigger(cards, ['Grizzly Bears', 'Sol Ring', 'Island'], counters=2)
    assert s.state.cards[source.id].counters['influence'] == 3
    before = len(s.state.zones['p1:hand'])
    answer(s, draw)
    assert len(s.state.zones['p1:hand']) == before + int(draw)
    assert s.state.players['p2'].life == (40 if draw else 37)
    assert s.state.players['p3'].life == 40
    assert all(s.state.cards[cid].zone == ('p1:graveyard' if not draw else ('p1:hand' if cid == chosen[0] else 'p1:library')) for cid in chosen)


@pytest.mark.parametrize('names,total', [(['Fire // Ice', 'Walking Ballista', 'Grizzly Bears'], 6), (['Grizzly Bears'], 2), ([], 0)])
def test_total_milled_values_with_short_libraries(cards, names, total):
    s, _, _ = trigger(cards, names, counters=2)
    answer(s, False)
    assert s.state.players['p2'].life == 40-total
    assert 'p1' not in s.state.rules.lost


@pytest.mark.parametrize('rip', [False, True])
def test_replacements_preserve_milled_values(cards, rip):
    names = ['Grizzly Bears', 'Sol Ring', 'Island'] if rip else ['Blightsteel Colossus', 'Sol Ring', 'Island']
    s, _, _ = trigger(cards, names, counters=2, rip=rip)
    answer(s, False)
    assert s.state.players['p2'].life == (37 if rip else 27)


def test_source_departure_uses_last_known_counters_without_adding_one(cards):
    s, _, _ = trigger(cards, ['Grizzly Bears', 'Sol Ring', 'Grizzly Bears'], counters=2, leave=True)
    answer(s, False)
    assert s.state.players['p2'].life == 37


def test_doubled_influence_counter_changes_mill_count(cards):
    s, source, chosen = trigger(cards, ['Grizzly Bears', 'Sol Ring', 'Island'], doubling=True)
    assert s.state.cards[source.id].counters['influence'] == 2
    answer(s, False)
    assert s.state.players['p2'].life == 37
    assert s.state.cards[chosen[2]].zone == 'p1:library'


def test_scry_changes_which_cards_are_milled(cards):
    s, _, chosen = trigger(cards, ['Grizzly Bears', 'Sol Ring', 'Island'], bottom=True)
    answer(s, False)
    assert s.state.cards[chosen[1]].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 39


def test_illegal_opponent_target_prevents_counter_and_scry(cards):
    from tests.test_rules_designations import roundtrip

    s, source, chosen = trigger(cards, ['Grizzly Bears', 'Sol Ring', 'Island'], illegal=True)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].counters.get('influence', 0) == 0
    assert all(s.state.cards[c].zone == 'p1:library' for c in chosen)
    assert all(p.life == 40 for p in s.state.players.values())
    roundtrip(s)
