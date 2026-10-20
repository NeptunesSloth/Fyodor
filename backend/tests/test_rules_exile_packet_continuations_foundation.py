"""Native exact-packet, grouped permission and frozen event-actor foundations."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.rules import exile_packet_continuations as leaf
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_qualified_attached_tutors import cold
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = Path(__file__).parent / 'fixtures/exile_packet_continuation_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((DATA.parent / 'name_search_family_cards.json').read_text())):
        if c['name'] in ('Aven Mindcensor', 'Opposition Agent', 'Stranglehold'):
            base[c['name']] = card(c['name'], set_code='epc', number='search' + str(i),
                                   **{k: v for k, v in c.items() if k != 'name'})
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='epc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns = [c['name'] for c in json.loads(DATA.read_text())]
    s = table(cards, ns, ns, ns)
    to_phase(s, 'main1', turn=1)
    return s


def test_exact_multiplayer_top_packet_is_one_native_move_and_departure_does_not_rebind(cards):
    s = setup(cards)
    a = stack_library(s, ['Forest'])[0]
    b = stack_library(s, ['Island'], pid='p2')[0]
    plan = Plan(s.state, 'p1', cards, random.Random(1))
    ctx = {'controller': 'p1', 'effects': [], 'next': 0, 'name': 'Packet foundation'}
    e = {'binding': 'ref:test_packet', 'mode': 'mezzio'}
    assert set(leaf.top_packet(plan, ctx, e, ['p1', 'p2'])) == {a, b}
    moves = [step for step in plan.steps if step['type'] == 'move']
    assert len(moves) == 1 and set(moves[0]['card_ids']) == {a, b}
    plan.do({'type': 'move', 'card_ids': [a], 'to': {'zone': 'hand'}}, actor='p1')
    plan.do({'type': 'move', 'card_ids': [a], 'to': {'zone': 'exile'}}, actor='p1')
    assert leaf.remaining(plan, ctx, e) == [b]


@pytest.mark.parametrize('first_type', ['Artifact', 'Creature'])
def test_native_grouped_type_permissions_choose_one_type_and_consume_only_that_group(cards, first_type):
    s = setup(cards)
    ids = stack_library(s, ['Memnite', 'Ornithopter', 'Phyrexian Walker'])
    plan = Plan(s.state, 'p1', cards, random.Random(1))
    ctx = {'controller': 'p1', 'effects': [], 'next': 0, 'name': "Aminatou's Augury foundation"}
    e = {'binding': 'ref:test_augury', 'mode': 'augury'}
    leaf.top_packet(plan, ctx, e, ['p1'], 3)
    leaf.typed_groups(plan, ctx, e)
    s = GameSession(plan.state, cards=cards)
    for i, kind in enumerate([first_type, 'Creature' if first_type == 'Artifact' else 'Artifact']):
        act(s, 'p1', type='cast_spell', card_id=ids[i], free=True)
        d = s.state.rules.decision
        if i == 0:
            assert d is not None and d.resume['step'] == 'slot'
            option = next(o.id for o in d.options if kind + ' permission' in o.label)
            s = cold(s, cards)
            answer(s, [option])
        else:
            assert d is None  # Only the other type's permission remains.
        settle(s)
        assert s.state.cards[ids[i]].zone == 'p1:battlefield'
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=ids[2], free=True)
    roundtrip(s)


def test_damage_event_actor_is_frozen_before_same_resolution_control_change(cards):
    from app.rules import effects, triggers
    from tests.test_rules_designations import put

    s = setup(cards)
    creature = put(s, 'Memnite', 'battlefield')
    plan = Plan(s.state, 'p1', cards, random.Random(7))
    ctx = {'controller': 'p1', 'source_card': creature.id, 'source_object': plan.oid(creature.id),
           'effects': [], 'next': 0, 'name': 'Damage actor foundation'}
    assert effects.damage(plan, ctx, {'do': 'damage', 'n': 1, 'who': 'player:p2'})
    plan.do({'type': 'set_controller', 'card_ids': [creature.id], 'player': 'p3'}, actor='p1')
    event = next(e for e in reversed(plan.rules.events) if e.kind == 'damage')
    assert event.actor == 'p1' and plan.state.cards[creature.id].controller == 'p3'
    fact = next(f for f in triggers._damage_facts(plan, event) if f[0] == 'deal_damage')
    frozen = triggers._event(plan, fact, event.batch)
    assert frozen.actor == 'p1' and frozen.players == ['p2']
    assert type(frozen).model_validate_json(frozen.model_dump_json()).actor == 'p1'
    step = next(a for a in plan.steps if a['type'] == 'rules_damage')
    assert step['dealt'][0]['source_controller'] == 'p1'
