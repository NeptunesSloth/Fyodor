"""CR 118.7, 702.27: reductions restricted to the buyback additional cost."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/buyback_cost_reduction_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Memory Crystal'


def test_crystal_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_crystals(cards, count=1):
    from tests.game_helpers import act
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Capsize', 'Whispers of the Muse', 'Constant Mists', 'Wurmcalling', 'Grizzly Bears'],
              ['Capsize', 'Grizzly Bears', 'Counterspell'], [NAME] * count)
    copies = [c.id for c in s.state.cards.values() if c.owner == 'p3' and c.name == NAME]
    assert len(copies) == count
    if copies:
        act(s, 'p3', type='move', card_ids=copies, to={'player': 'p3', 'zone': 'battlefield'})
    return s, copies


@pytest.mark.parametrize('pid', ['p1', 'p2'])
@pytest.mark.parametrize('count', [0, 1, 2, 3])
def test_global_reductions_stack_but_never_spill_into_the_base_spell_cost(cards, pid, count):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle

    s, _ = setup_crystals(cards, count)
    source = put(s, 'Capsize', 'hand', pid)
    target = put(s, 'Grizzly Bears', 'battlefield', pid)
    wait_priority(s, pid)
    generic = 1 + max(0, 3 - 2 * count)
    mana(s, pid, C=generic, U=2)
    act(s, pid, type='cast_spell', card_id=source.id, buyback=True, targets=[target.id])
    assert not any(s.state.players[pid].mana.values())
    assert s.state.rules.payments[s.state.rules.object_id(source.id)].total_cost == f'{{{generic}}}{{U}}{{U}}'
    roundtrip(s)
    settle(s)
    assert s.state.cards[source.id].zone == f'{pid}:hand' and s.state.cards[target.id].zone == f'{pid}:hand'
    roundtrip(s)


def test_without_buyback_crystal_does_not_reduce_the_spell_cost(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    s, _ = setup_crystals(cards, 2)
    source = put(s, 'Capsize', 'hand')
    target = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, U=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id])
    assert s.state.cards[source.id].zone == 'p1:hand' and s.state.players['p1'].mana == {'U': 2}
    mana(s, C=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('count', [1, 2])
def test_colored_buyback_costs_and_x_mana_are_preserved(cards, count):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    s, _ = setup_crystals(cards, count)
    source = put(s, 'Wurmcalling', 'hand')
    mana(s, C=1, G=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, buyback=True, x_value=1)
    assert not any(s.state.players['p1'].mana.values())
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:hand'
    wurms = [c for c in s.state.cards.values() if c.is_token and c.name == 'Wurm']
    assert len(wurms) == 1 and wurms[0].token.power == '1' and wurms[0].token.toughness == '1'
    roundtrip(s)


def test_nonmana_buyback_cost_is_still_paid_in_full(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    s, _ = setup_crystals(cards, 2)
    land = put(s, 'Forest', 'battlefield')
    source = put(s, 'Constant Mists', 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, buyback=True)
    if (d := s.state.rules.decision) is not None:
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[land.id])
    settle(s)
    assert s.state.cards[land.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].zone == 'p1:hand'
    roundtrip(s)


def test_countering_the_bought_back_spell_does_not_return_it_to_hand(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle

    s, _ = setup_crystals(cards)
    source = put(s, 'Capsize', 'hand')
    target = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=2, U=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, buyback=True, targets=[target.id])
    wait_priority(s, 'p2')
    counter = put(s, 'Counterspell', 'hand', 'p2')
    mana(s, 'p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard' and s.state.cards[target.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_crystal_can_reduce_its_own_bounce_but_not_the_next_spell_after_leaving(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle

    s, copies = setup_crystals(cards)
    source = put(s, 'Capsize', 'hand')
    target = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=2, U=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, buyback=True, targets=[copies[0]])
    settle(s)
    assert s.state.cards[copies[0]].zone == 'p3:hand' and s.state.cards[source.id].zone == 'p1:hand'
    mana(s, C=2, U=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, buyback=True, targets=[target.id])
    assert s.state.cards[source.id].zone == 'p1:hand' and s.state.players['p1'].mana == {'C': 2, 'U': 2}
    mana(s, C=2)
    roundtrip(s)
    act(s, 'p1', type='cast_spell', card_id=source.id, buyback=True, targets=[target.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:hand' and s.state.cards[target.id].zone == 'p1:hand'
    roundtrip(s)
