"""Opt-in actual engine routing only; the production bridge remains unregistered."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import prevention_frontier_bridge as bridge
from app.rules import prevention_frontier_journal as journal
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_prevention_outcomes import cast, source_choice
from tests.test_rules_shared_damage_choices import table

ROOT = Path(__file__).parent / 'fixtures'
DATA = json.loads((ROOT / 'prevention_outcomes_cards.json').read_text())
DATA.append(next(c for c in json.loads((ROOT / 'red_source_damage_floor_cards.json').read_text()) if c['name'] == 'Earthquake'))
DATA.append(next(c for c in fixture_cards() if c['name'] == 'Pyroclasm'))
DATA.append(next(c for c in json.loads((ROOT / 'group_unblocked_cards.json').read_text()) if c['name'] == 'Mirran Crusader'))


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(DATA):
        base[row['name']] = card(row['name'], set_code='jfb', number=str(i), **{k: v for k, v in row.items() if k not in ('name', 'id', 'set', 'collector_number')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()

def game(cards):
    names = list(dict.fromkeys(c['name'] for c in DATA))
    return table(cards, names, names, names)


def earth_harm(cards, *, furnace=False):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    if furnace:
        put(s, 'Furnace of Rath', 'battlefield')
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'main1', turn=2)
    quake = cast(s, 'Earthquake', pid='p2', x_value=2, resolve=False)
    cast(s, "Harm's Way", ['p3'])
    source_choice(s, quake)
    assert s.state.rules.decision.resume['step'] == bridge.STEP
    return s, bear, quake


def answer(s, value):
    d = s.state.rules.decision
    assert d and d.resume['step'] == bridge.STEP
    frame = journal.Frame.loads(d.resume['frame'])
    from app.rules.plan import Plan
    q = journal.question(Plan(s.state, d.player, s.cards, None), frame)
    assert isinstance(q, journal.Question)
    if q.kind == 'order':
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[value])
    else:
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[], name=str(value))
    settle(s)


def test_native_earthquake_harm_one_plus_one_cross_recipient_split(cards):
    s, bear, quake = earth_harm(cards)
    for _ in range(8):
        if s.state.rules.decision is None:
            break
        roundtrip(s)
        answer(s, 1)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == 39 and s.state.cards[bear.id].damage == 1
    assert s.state.players['p2'].life == 38 and s.state.players['p3'].life == 36
    assert not s.state.rules.replacements and not s.state.zones.get('stack')
    assert s.state.cards[quake.id].zone == 'p2:graveyard'


def test_native_numeric_text_bounds_and_actor_reject_atomically(cards):
    s, bear, quake = earth_harm(cards)
    d = s.state.rules.decision
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[], name='1')
    assert s.state.model_dump_json() == before
    for value in ('-1', '3', 'not a number'):
        with pytest.raises(ActionError):
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[], name=value)
        assert s.state.model_dump_json() == before
