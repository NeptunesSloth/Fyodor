"""CR 702.29c/f, 614.1: cycling permissions and graveyard replacements."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/exiled_card_copy_sequences_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_mizzix_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Mizzix's Mastery")).level == 'FULL'


def answer(s, ids):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    d = s.state.rules.decision
    assert d
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


@pytest.mark.parametrize('accept', [False, True])
def test_mastery_exiles_target_then_optionally_casts_its_copy(cards, accept):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ["Mizzix's Mastery", 'Lightning Bolt'], [], [])
    source = put(s, "Mizzix's Mastery", 'hand')
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    mana(s, R=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bolt.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    d = s.state.rules.decision
    assert d and len(d.options) == 1
    copy_id = d.options[0].id
    assert copy_id != bolt.id
    answer(s, [copy_id] if accept else [])
    if accept:
        d = s.state.rules.decision
        assert d and 'p2' in {o.id for o in d.options}
        answer(s, ['p2'])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[bolt.id].zone == 'p1:exile'
    assert s.state.players['p2'].life == (37 if accept else 40)
    assert copy_id not in s.state.cards
    roundtrip(s)


@pytest.mark.parametrize('cast_count', [0, 1, 2])
def test_overload_exiles_only_spells_and_casts_copies_in_chosen_order(cards, cast_count):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ["Mizzix's Mastery", 'Lightning Bolt', 'Divination', 'Grizzly Bears'], [], [])
    source = put(s, "Mizzix's Mastery", 'hand')
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    divination = put(s, 'Divination', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    land = put(s, 'Forest', 'graveyard')
    before = len(s.state.zones['p1:hand'])
    mana(s, R=8)
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=f'{source.id}:1')
    settle(s)
    d = s.state.rules.decision
    assert d and {s.state.cards[o.id].name for o in d.options} == {'Lightning Bolt', 'Divination'}
    copies = {s.state.cards[o.id].name: o.id for o in d.options}
    if cast_count:
        answer(s, [copies['Divination']])
        d = s.state.rules.decision
        assert d
        answer(s, [copies['Lightning Bolt']] if cast_count == 2 else [])
        if cast_count == 2:
            answer(s, ['p2'])
    else:
        answer(s, [])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[bolt.id].zone == s.state.cards[divination.id].zone == 'p1:exile'
    assert s.state.cards[bear.id].zone == s.state.cards[land.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == (37 if cast_count == 2 else 40)
    assert len(s.state.zones['p1:hand']) == before - 1 + (2 if cast_count else 0)
    assert all(cid not in s.state.cards for cid in copies.values())
    roundtrip(s)


def test_mastery_with_departed_target_does_not_exile_itself(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ["Mizzix's Mastery", 'Lightning Bolt'], [], [])
    source = put(s, "Mizzix's Mastery", 'hand')
    bolt = put(s, 'Lightning Bolt', 'graveyard')
    mana(s, R=4)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bolt.id])
    act(s, 'p1', type='move', card_ids=[bolt.id], to={'player': 'p1', 'zone': 'hand'})
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[bolt.id].zone == 'p1:hand'
    roundtrip(s)


def test_overloaded_mastery_with_empty_graveyard_still_exiles_itself(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ["Mizzix's Mastery"], [], [])
    source = put(s, "Mizzix's Mastery", 'hand')
    mana(s, R=8)
    act(s, 'p1', type='cast_spell', card_id=source.id, alt_cost=f'{source.id}:1')
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:exile'
    roundtrip(s)
