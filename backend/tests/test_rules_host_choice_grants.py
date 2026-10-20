"""CR 608.2d/611.2: nonmodal choices use the attached host, not the source."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, roundtrip, settle

DATA = Path(__file__).parent / 'fixtures/host_choice_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='hch', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, opponent=False):
    from tests.test_rules_wave31d_spell_copies import hold

    s = build(cards, ["Pemmin's Aura", 'Hill Giant', 'Disenchant'], bob=[(1, 'Grizzly Bears'), (10, 'Island')])
    host = put(s, 'Grizzly Bears' if opponent else 'Hill Giant', 'battlefield', 'p2' if opponent else 'p1')
    source = put(s, "Pemmin's Aura", 'hand')
    hold(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[host.id])
    settle(s)
    assert s.state.cards[source.id].attached_to == host.id
    return s, source, host


def pt(s, cards, host):
    from app.rules.sba import power, toughness

    ch = Plan(s.state, host.controller, cards, None).ch(s.state.cards[host.id])
    return power(s.state.cards[host.id], ch), toughness(s.state.cards[host.id], ch)


def activate(s, cards, source):
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    index = next(a.index for a in ch.abilities if '+1/-1 or -1/+1' in a.text)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)


def choose(s, option):
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'choose_one'
    assert [o.label for o in d.options] == ['+1/-1', '-1/+1']
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[str(option)])
    settle(s)
    roundtrip(s)


def test_canonical_pemmins_aura_is_fully_automated(cards):
    c = coverage.of_card_data(cards.resolve("Pemmin's Aura"))
    assert c.level == 'FULL', c.manual_parts


@pytest.mark.parametrize('option,expected', [(0, (4, 2)), (1, (2, 4))])
def test_actual_aura_pump_choice_applies_to_host_until_end_of_turn(cards, option, expected):
    from tests.test_rules_wave34b_activated import to_phase

    s, source, host = setup(cards)
    activate(s, cards, source)
    assert pt(s, cards, host) == (3, 3)  # Choice is made on resolution, not activation.
    choose(s, option)
    assert pt(s, cards, host) == expected
    to_phase(s, 'main1', turn=s.state.turn.number + 1)
    assert pt(s, cards, host) == (3, 3)
    roundtrip(s)


def test_aura_controller_chooses_even_when_host_has_another_controller(cards):
    s, source, host = setup(cards, opponent=True)
    activate(s, cards, source)
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, 1)
    assert pt(s, cards, host) == (1, 3)


def test_source_leaving_before_resolution_uses_its_last_known_host(cards):
    s, source, host = setup(cards)
    activate(s, cards, source)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    choose(s, 0)
    assert pt(s, cards, host) == (4, 2)


def test_host_blink_before_resolution_does_not_modify_the_new_object(cards):
    s, source, host = setup(cards)
    activate(s, cards, source)
    act(s, 'p1', type='move', card_ids=[host.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[host.id], to={'player': 'p1', 'zone': 'battlefield'})
    settle(s)
    assert s.state.rules.decision is None and pt(s, cards, host) == (3, 3)
    roundtrip(s)


def test_reattached_aura_reads_its_current_host_when_ability_resolves(cards):
    s, source, old_host = setup(cards)
    new_host = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate(s, cards, source)
    act(s, 'p1', type='attach', card_ids=[source.id], to=new_host.id)
    choose(s, 0)
    assert pt(s, cards, old_host) == (3, 3)
    assert pt(s, cards, new_host) == (3, 1)


def test_host_blink_after_choice_is_offered_does_not_rebind_the_pump(cards):
    s, source, host = setup(cards)
    activate(s, cards, source)
    settle(s)
    assert s.state.rules.decision is not None
    act(s, 'p1', type='move', card_ids=[host.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[host.id], to={'player': 'p1', 'zone': 'battlefield'})
    choose(s, 0)
    assert pt(s, cards, host) == (3, 3)
