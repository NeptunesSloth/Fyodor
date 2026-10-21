"""CR 701.67a, 702.21a: ward waterbending during resolution."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/waterbend_ward_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'The Unagi of Kyoshi Island'


def test_unagi_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup(cards, *, helpers=(), mana_left=0, tapped=False):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Grizzly Bears', 'Ornithopter', 'Memnite', 'Sol Ring'],
              ['Murder', 'Grizzly Bears', 'Ornithopter', 'Memnite', 'Sol Ring'])
    source = put(s, NAME, 'battlefield')
    objects = [put(s, name, 'battlefield', pid='p2') for name in helpers]
    if tapped:
        act(s, 'p2', type='tap', card_ids=[c.id for c in objects], tapped=True)
    wait_priority(s, 'p2')
    spell = put(s, 'Murder', 'hand', pid='p2')
    mana(s, pid='p2', C=1 + mana_left, B=2)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    return s, source, objects, spell


def pay(s, picks):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle

    d = s.state.rules.decision
    assert d is not None and d.player == 'p2' and {o.id for o in d.options} == {'pay', 'decline'}
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    if d is not None:
        assert d.player == 'p2' and d.kind == 'choose_cards'
        assert d.min_choices == 0
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=[c.id for c in picks])
    else:
        assert not picks
    settle(s)


@pytest.mark.parametrize('count', [0, 2, 4])
def test_ward_payment_combines_mana_and_summoning_sick_artifact_creatures(cards, count):
    from tests.test_rules_designations import roundtrip

    s, source, helpers, spell = setup(cards, helpers=['Grizzly Bears', 'Ornithopter', 'Memnite', 'Sol Ring'][:count], mana_left=4-count)
    roundtrip(s)
    pay(s, helpers)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    assert all(s.state.cards[c.id].tapped for c in helpers)
    assert not any(s.state.players['p2'].mana.values())
    roundtrip(s)


def test_helper_choice_reserves_sol_ring_for_mana_in_mixed_payment(cards):
    from tests.test_rules_designations import roundtrip

    s, source, helpers, _ = setup(cards, helpers=['Grizzly Bears', 'Ornithopter', 'Sol Ring'])
    pay(s, helpers[:2])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert all(s.state.cards[c.id].tapped for c in helpers)
    assert not any(s.state.players['p2'].mana.values())
    roundtrip(s)


def test_no_helpers_can_be_chosen_and_mana_sources_still_work(cards):
    from tests.test_rules_designations import roundtrip

    s, source, helpers, _ = setup(cards, helpers=['Sol Ring'], mana_left=2)
    pay(s, [])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[helpers[0].id].tapped
    assert not any(s.state.players['p2'].mana.values())
    roundtrip(s)


def test_selected_sol_ring_cannot_also_produce_mana_for_the_same_payment(cards):
    from tests.test_rules_designations import roundtrip

    s, source, helpers, spell = setup(cards, helpers=['Grizzly Bears', 'Ornithopter', 'Sol Ring'])
    # Paying with all three would still require one mana, and Sol Ring is
    # reserved as a helper. Nothing may be paid when that choice cannot finish.
    pay(s, helpers)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    assert all(not s.state.cards[c.id].tapped for c in helpers)
    roundtrip(s)


@pytest.mark.parametrize('helpers,tapped', [([], False), (['Sol Ring', 'Grizzly Bears'], False),
                                          (['Grizzly Bears', 'Ornithopter', 'Memnite', 'Sol Ring'], True)])
def test_unpayable_ward_counters_spell_without_partial_payment(cards, helpers, tapped):
    from tests.test_rules_designations import roundtrip

    s, source, objects, spell = setup(cards, helpers=helpers, tapped=tapped)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    assert all(s.state.cards[c.id].tapped == tapped for c in objects)
    roundtrip(s)


def test_payer_may_decline_without_tapping_available_helpers(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, helpers, spell = setup(cards, helpers=['Grizzly Bears', 'Ornithopter', 'Memnite', 'Sol Ring'])
    d = s.state.rules.decision
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    assert all(not s.state.cards[c.id].tapped for c in helpers)
    roundtrip(s)


def test_helper_revalidation_prevents_partial_payment_after_control_changes(cards):
    from tests.game_helpers import act
    from tests.test_rules_conditionals import settle
    from tests.test_rules_designations import roundtrip

    s, source, helpers, spell = setup(cards, helpers=['Grizzly Bears', 'Ornithopter', 'Memnite', 'Sol Ring'])
    d = s.state.rules.decision
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    act(s, 'p1', type='set_controller', card_ids=[helpers[0].id], player='p1')
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[c.id for c in helpers])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[spell.id].zone == 'p2:graveyard'
    assert all(not s.state.cards[c.id].tapped for c in helpers)
    roundtrip(s)
