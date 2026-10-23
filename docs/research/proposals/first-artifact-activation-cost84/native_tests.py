"""Native first artifact activations preserve actor, order, and source types."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Tezzeret, Betrayer of Flesh"]
DATA = json.loads((Path(__file__).parent / "fixtures/first_artifact_activation_cost84_cards.json").read_text())


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, tezz=True):
    ns = [c["name"] for c in DATA] * 3
    s = table(cards, ns, ns, ns)
    for pid in ['p1', 'p2', 'p3']:
        act(s, pid, type='set_prefs', hold_priority=True, response='on')
    to_phase(s, 'main1', 4)
    if tezz:
        put(s, NAMES[0], 'battlefield')
    assert s.state.rules.artifact_activation_history_turn84 == s.state.turn.number
    return s


def source(s, name='Basalt Monolith', pid='p1'):
    c = put(s, name, 'battlefield', pid)
    act(s, pid, type='tap', card_ids=[c.id], tapped=True)
    return c


def activate(s, c, price, pid='p1', sources=()):
    wait_priority(s, pid)
    if price:
        act(s, pid, type='add_mana', player=pid, mana={'C': price})
    index = next(a.index for a in Plan(s.state, pid, s.cards, None).ch(c).abilities if a.kind == 'activated')
    act(s, pid, type='activate_ability', card_id=c.id, ability=index, sources=list(sources))
    a = next(a for a in s.state.cards.values() if a.zone == 'stack' and a.ability is not None)
    paid = s.state.rules.payments[s.state.rules.object_id(a.id)]
    assert paid.mana_spent == ({'C': price} if price else {})
    assert sum(s.state.players[pid].mana.values()) == 0
    return a


def mana(s, c, pid='p1'):
    wait_priority(s, pid)
    index = next(a.index for a in Plan(s.state, pid, s.cards, None).ch(c).abilities if a.kind == 'mana')
    act(s, pid, type='activate_ability', card_id=c.id, ability=index, sources=[])


def test_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[0])).level == 'FULL'


def test_first_then_second_actual_untap_prices(cards):
    s = setup(cards)
    c = source(s)
    activate(s, c, 1)
    answer(s)
    assert not s.state.cards[c.id].tapped
    act(s, 'p1', type='tap', card_ids=[c.id], tapped=True)
    activate(s, c, 3)
    answer(s)
    assert not s.state.cards[c.id].tapped


def test_zero_cost_mana_activation_consumes_first(cards):
    s = setup(cards)
    ring = put(s, 'Sol Ring', 'battlefield')
    mana(s, ring)
    assert s.state.players['p1'].mana == {'C': 2}
    c = source(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': -2})
    activate(s, c, 3)


def test_actual_activation_before_tezzeret_enters_counts(cards):
    s = setup(cards, False)
    ring = put(s, 'Sol Ring', 'battlefield')
    mana(s, ring)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': -2})
    put(s, NAMES[0], 'battlefield')
    activate(s, source(s), 3)


def test_opponents_actual_mana_activation_does_not_consume_yours(cards):
    s = setup(cards)
    ring = put(s, 'Sol Ring', 'battlefield', 'p2')
    mana(s, ring, 'p2')
    activate(s, source(s), 1)


def test_automatic_nested_filter_must_not_get_parents_first_discount(cards):
    s = setup(cards)
    c = source(s)
    prism = put(s, 'Mana Prism', 'battlefield')
    wait_priority(s, 'p1')
    index = next(a.index for a in Plan(s.state, 'p1', s.cards, None).ch(c).abilities if a.kind == 'activated')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=c.id, ability=index, sources=[prism.id])
    assert s.state.model_dump_json() == before
