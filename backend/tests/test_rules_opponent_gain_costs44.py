"""Isolated native gain-cost payment stage and typed continuation proofs."""
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import mana as M
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/opponent_gain_costs44_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='ogc', number=str(i), **{('card_faces' if k == 'faces' else k): v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@dataclass
class Finished:
    opponent_gain_receipts: list[dict] = field(default_factory=list)


def prepare(cards, modifier=None):
    from app.rules import opponent_gain_costs44 as leaf
    from app.rules import payment_continuations as pc

    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    if modifier:
        put(s, modifier, 'battlefield', pid='p1' if modifier == 'Tainted Remedy' else 'p2')
    plan = Plan(s.state, 'p1', cards, None)
    result = []

    def finish(plan, data, payment):
        result.append((data.opponent_gain_receipts, payment))

    pc.register('opponent_gain44_test_finished', Finished, finish)
    payment = M.Payment(spent={'C': 1}, slots=[('unit:original', ('C',))], selected_options=[('original', 2)])
    after = pc.continuation(plan, 'opponent_gain44_test_finished', Finished())
    frame = leaf.GainLifeCosts([leaf.GainLifeCost('p1', 'p2', 3)], after, payment)
    return plan, frame, result


@pytest.mark.parametrize('modifier,life', [(None, 43), ('Sulfuric Vortex', 40), ('Tainted Remedy', 37)])
def test_native_gain_cost_receipt_after_actual_normal_zero_or_loss_event(cards, modifier, life):
    from app.rules import opponent_gain_costs44 as leaf

    plan, frame, result = prepare(cards, modifier)
    leaf.start(plan, frame)
    assert plan.state.players['p2'].life == life
    assert plan.state.players['p1'].life == plan.state.players['p3'].life == 40
    assert len(result) == 1 and result[0][0] == [{'recipient': 'p2', 'nominal_amount': 3}]
    assert result[0][1] == frame.payment
    assert frame.next == 1 and frame.pending is None


def test_native_prohibition_is_not_zero_gain_replacement_and_boundary_is_unchanged(cards):
    from app.game.errors import ActionError
    from app.rules import opponent_gain_costs44 as leaf

    plan, frame, result = prepare(cards, 'Platinum Emperion')
    assert leaf.opponents(plan, 'p1') == ['p3']
    before = plan.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        leaf.start(plan, frame)
    assert plan.state.model_dump(mode='json') == before and not plan.steps and not result


@pytest.mark.parametrize('first,expected', [('Archive', 47), ('Angel', 48)])
def test_native_saved_gain_616_stage_preserves_nominal_receipt_and_payment_allocation(cards, first, expected):
    from app.game import actions as A
    from app.game.state import GameState
    from app.rules import engine
    from app.rules import opponent_gain_costs44 as leaf

    plan, frame, result = prepare(cards, "Alhammarret's Archive")
    # Add the actual canonical Angel to the native prospective table; it has
    # its own independent add-one replacement, so 616 order is observable.
    angel = next(c for c in plan.state.cards.values() if c.name == 'Angel of Vitality' and c.owner == 'p2')
    plan.do({'type': 'move', 'card_ids': [angel.id], 'to': {'zone': 'battlefield', 'player': 'p2'}})
    leaf.start(plan, frame)
    assert plan.rules.decision is not None and not result
    assert plan.state.players['p2'].life == 40
    saved = GameState.model_validate_json(plan.state.model_dump_json())
    restored = Plan(saved, 'p2', cards, None)
    d = restored.rules.decision
    option = next(o.id for o in d.options if first in o.label)
    engine.choose(restored, A.Choose(decision_id=d.id, option_ids=[option]))
    assert restored.rules.decision is None
    assert restored.state.players['p2'].life == expected
    assert len(result) == 1 and result[0][0] == [{'recipient': 'p2', 'nominal_amount': 3}]
    assert result[0][1] == frame.payment
