"""Actual printed Cover costs with the native shared damage definition."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip, settle
from tests.test_rules_wave7e_activated import EXTRA as SNOW_ROWS
from tests.test_rules_wave43c_keywords import answer, drain, lands, prompt
from tests.wave9c_kit import build, put


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/prevention_outcomes_cards.json').read_text())
    for i, c in enumerate(rows):
        base[c['name']] = card(c['name'], set_code='cvw', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    snow = next(c for c in SNOW_ROWS if c['name'] == 'Snow-Covered Forest')
    base[snow['name']] = snow
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_printed_snow_activation_rejects_plain_pool_and_uses_actual_snow_source(cards):
    s = build(cards, ['Cover of Winter', 'Snow-Covered Forest', 'Forest'])
    act(s, 'p1', type='set_prefs', hold_priority=True, response='on')
    act(s, 'p2', type='set_prefs', response='on')
    cover = put(s, 'Cover of Winter')
    snow = lands(s, 'Snow-Covered Forest', 1)[0]
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 3})
    plan = Plan(s.state, 'p1', cards, None)
    index = next(a.index for a in plan.ch(plan.state.cards[cover.id]).abilities if a.kind == 'activated')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=cover.id, ability=index, sources=[])
    assert not s.state.cards[cover.id].counters and not s.state.cards[snow].tapped
    before = set(s.state.rules.payments)
    act(s, 'p1', type='activate_ability', card_id=cover.id, ability=index, sources=[snow])
    receipt = next(p for key, p in s.state.rules.payments.items() if key not in before)
    assert receipt.snow_spent == {'G': 1}
    roundtrip(s)
    settle(s)
    assert s.state.cards[cover.id].counters.get('age') == 1
    assert s.state.cards[snow].tapped and s.state.players['p1'].mana.get('G') == 3


def test_native_cumulative_snow_upkeep_counts_every_age_then_declines(cards):
    s = build(cards, ['Cover of Winter', *(['Snow-Covered Forest'] * 3)])
    cover = put(s, 'Cover of Winter')
    snow = lands(s, 'Snow-Covered Forest', 3)
    for count in (1, 2):
        d = prompt(s, 'Cover of Winter')
        assert s.state.cards[cover.id].counters.get('age') == count
        assert {o.id for o in d.options} == {'pay', 'sacrifice'} and d.prompt.count('{S}') == count
        roundtrip(s)
        answer(s, s.state.rules.decision, 'pay')
        drain(s)
        assert s.state.cards[cover.id].zone == 'p1:battlefield'
        assert sum(s.state.cards[c].tapped for c in snow) == count
    d = prompt(s, 'Cover of Winter')
    assert s.state.cards[cover.id].counters.get('age') == 3
    answer(s, d, 'sacrifice')
    drain(s)
    assert s.state.cards[cover.id].zone == 'p1:graveyard'


def test_cumulative_snow_cost_cannot_be_partially_paid_with_plain_mana(cards):
    s = build(cards, ['Cover of Winter', 'Snow-Covered Forest', 'Forest'])
    cover = put(s, 'Cover of Winter')
    snow = lands(s, 'Snow-Covered Forest', 1)[0]
    act(s, 'p1', type='counter', card_ids=[cover.id], kind='age', delta=1)
    d = prompt(s, 'Cover of Winter')
    assert s.state.cards[cover.id].counters.get('age') == 2
    with pytest.raises(ActionError):
        answer(s, d, 'pay')
    assert not s.state.cards[snow].tapped
    answer(s, s.state.rules.decision, 'sacrifice')
    drain(s)
    assert s.state.cards[cover.id].zone == 'p1:graveyard' and not s.state.cards[snow].tapped
