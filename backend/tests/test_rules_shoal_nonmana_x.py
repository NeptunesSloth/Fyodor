"""Production nonmana-X costs and the native Shining Shoal body."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import alt_costs, casting
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_prevention_outcomes import game as base_game


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    root = Path(__file__).parent / 'fixtures'
    rows = json.loads((root / 'prevention_outcomes_cards.json').read_text())
    for filename, wanted in [('wave53d_cards.json', 'Restore Balance'), ('review29b_cards.json', 'Thalia, Guardian of Thraben'),
                             ('semblance_anvil_cards.json', 'Desperate Ritual'), ('wave22c_cards.json', 'Progenitus'),
                             ('wave29a_hints_cards.json', 'Omniscience')]:
        rows.append(next(c for c in json.loads((root / filename).read_text()) if c['name'] == wanted))
    for i, data in enumerate(rows):
        base[data['name']] = card(data['name'], set_code='snx', number=str(i), **{k: v for k, v in data.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    from tests.test_rules_shared_damage_choices import table
    base = base_game(cards)
    names = list(dict.fromkeys(c.name for c in base.state.cards.values()))
    names += ['Restore Balance', 'Thalia, Guardian of Thraben', 'Desperate Ritual', 'Progenitus', 'Omniscience']
    return table(cards, names, names, names)


def begin(s, x):
    shoal = put(s, 'Shining Shoal', 'hand')
    wait_priority(s, 'p1')
    plan = Plan(s.state, 'p1', s.cards, None)
    offers = alt_costs.offers(plan.state, 'p1', plan.state.cards[shoal.id], plan.ch(plan.state.cards[shoal.id]), plan.info)
    assert len(offers) == 1
    act(s, 'p1', type='cast_spell', card_id=shoal.id, targets=['p2'], x_value=x, alt_cost=offers[0].key, sources=[])
    return shoal


def test_actual_white_card_x_cost_is_private_and_paid_without_mana(cards):
    s = game(cards)
    white = put(s, "Acolyte's Reward", 'hand')
    other = put(s, 'Samite Ministration', 'hand')
    wrong = put(s, 'Grizzly Bears', 'hand')
    shoal = begin(s, 2)
    d = s.state.rules.decision
    assert d and d.player == 'p1'
    assert white.id in {o.id for o in d.options} and other.id in {o.id for o in d.options}
    assert wrong.id not in {o.id for o in d.options} and shoal.id not in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[white.id])
    assert s.state.cards[white.id].zone == 'p1:exile'
    assert s.state.cards[shoal.id].zone == 'stack'
    entry = s.state.rules.stack[shoal.id]
    assert entry.x == 2


def test_single_legal_white_card_automatically_pays_actual_x(cards):
    s = game(cards)
    white = put(s, 'Selfless Squire', 'hand')
    shoal = begin(s, 4)
    assert s.state.rules.decision is None
    assert s.state.cards[white.id].zone == 'p1:exile'
    assert s.state.rules.stack[shoal.id].x == 4
    paid = s.state.rules.payments[s.state.rules.object_id(shoal.id)]
    assert paid.exiled == [white.id] and not paid.mana_spent


def test_real_white_zero_mana_value_card_pays_x_zero(cards):
    s = game(cards)
    white = put(s, 'Restore Balance', 'hand')
    shoal = begin(s, 0)
    assert s.state.cards[white.id].zone == 'p1:exile'
    assert s.state.rules.stack[shoal.id].x == 0


@pytest.mark.parametrize('x', [0, 3, 99])
def test_wrong_mana_value_cannot_pay_and_nothing_moves(cards, x):
    s = game(cards)
    white = put(s, 'Selfless Squire', 'hand')
    with pytest.raises(ActionError):
        begin(s, x)
    assert s.state.cards[white.id].zone == 'p1:hand' and not s.state.zones.get('stack')


def test_cancel_private_cost_does_not_pay_or_cast(cards):
    s = game(cards)
    white = put(s, "Acolyte's Reward", 'hand')
    other = put(s, 'Samite Ministration', 'hand')
    shoal = begin(s, 2)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert all(s.state.cards[c.id].zone == 'p1:hand' for c in (shoal, white, other))


def test_native_hint_requires_other_white_card_and_has_no_invented_maximum(cards):
    s = game(cards)
    shoal = put(s, 'Shining Shoal', 'hand')
    wait_priority(s, 'p1')
    assert casting.alt_castable(s.state, 'p1', s.state.cards[shoal.id], s.cards) == []
    put(s, 'Selfless Squire', 'hand')
    hints = casting.alt_castable(s.state, 'p1', s.state.cards[shoal.id], s.cards)
    assert len(hints) == 1 and hints[0]['x'] is True
    assert set(hints[0]) == {'id', 'label', 'x'}
