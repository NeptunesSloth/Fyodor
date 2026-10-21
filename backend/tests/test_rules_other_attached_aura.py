"""CR 702: distinguish keyword forms from names and qualified enchant abilities."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/other_attached_aura_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



NAME = 'Daybreak Coronet'


def test_coronet_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def setup_coronet(cards, *, enchanted=True):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, NAME, 'Rancor', 'Grizzly Bears'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    rancor = put(s, 'Rancor', 'hand')
    if enchanted:
        mana(s, G=1)
        act(s, 'p1', type='cast_spell', card_id=rancor.id, targets=[bear.id])
        settle(s)
    source = put(s, NAME, 'hand')
    mana(s, W=2)
    return s, source, bear, rancor, other


def test_requires_another_aura_before_cast_payment(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip

    s, source, bear, _, _ = setup_coronet(cards, enchanted=False)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bear.id])
    assert s.state.cards[source.id].zone == 'p1:hand' and s.state.players['p1'].mana == {'W': 2}
    roundtrip(s)


def test_legal_cast_grants_stats_and_keywords_then_falls_when_other_aura_leaves(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, source, bear, rancor, _ = setup_coronet(cards)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bear.id])
    settle(s)
    ch = chars(s, bear)
    assert ch.pt == (7, 5) and {'first strike', 'vigilance', 'lifelink', 'trample'} <= ch.keywords
    assert s.state.cards[source.id].attached_to == bear.id
    roundtrip(s)
    act(s, 'p1', type='move', card_ids=[rancor.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='pass_priority')
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert chars(s, bear).pt == (2, 2)
    roundtrip(s)


def test_two_coronets_count_each_other_after_original_aura_leaves(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import roundtrip, settle
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, first, bear, rancor, _ = setup_coronet(cards)
    act(s, 'p1', type='cast_spell', card_id=first.id, targets=[bear.id])
    settle(s)
    second = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.name == NAME and c.id != first.id)
    act(s, 'p1', type='move', card_ids=[second.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, W=2)
    act(s, 'p1', type='cast_spell', card_id=second.id, targets=[bear.id])
    settle(s)
    act(s, 'p1', type='move', card_ids=[rancor.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='pass_priority')
    settle(s)
    assert all(s.state.cards[c.id].zone == 'p1:battlefield' for c in [first, second])
    assert chars(s, bear).pt == (8, 8)
    roundtrip(s)


def test_other_aura_moving_to_a_different_creature_ends_legal_enchantment(cards):
    from tests.game_helpers import act
    from tests.test_rules_designations import roundtrip, settle

    s, source, bear, rancor, other = setup_coronet(cards)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bear.id])
    settle(s)
    act(s, 'p1', type='attach', card_ids=[rancor.id], to=other.id)
    act(s, 'p1', type='pass_priority')
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard' and s.state.cards[rancor.id].attached_to == other.id
    roundtrip(s)


def test_equipment_attached_to_creature_is_not_an_aura(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Grizzly Bears', 'Bonesplitter'], [])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    equipment = put(s, 'Bonesplitter', 'battlefield')
    source = put(s, NAME, 'hand')
    act(s, 'p1', type='attach', card_ids=[equipment.id], to=bear.id)
    from tests.test_rules_bandmate_references import mana

    mana(s, W=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=[bear.id])
    roundtrip(s)


@pytest.mark.parametrize('other_aura', [False, True])
@pytest.mark.parametrize('shroud', [False, True])
def test_noncast_entry_requires_a_legal_host_with_another_aura(cards, other_aura, shroud):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, [NAME, 'Replenish', 'Grizzly Bears', 'Rancor', 'Lightning Greaves'], [])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    if shroud:
        greaves = put(s, 'Lightning Greaves', 'battlefield')
        act(s, 'p1', type='attach', card_ids=[greaves.id], to=bear.id)
    if other_aura:
        rancor = put(s, 'Rancor', 'battlefield')
        act(s, 'p1', type='attach', card_ids=[rancor.id], to=bear.id)
    source = put(s, NAME, 'graveyard')
    replenish = put(s, 'Replenish', 'hand')
    mana(s, W=4)
    act(s, 'p1', type='cast_spell', card_id=replenish.id)
    settle(s)
    if other_aura:
        d = s.state.rules.decision
        if d:
            assert bear.id in {o.id for o in d.options}
            roundtrip(s)
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
            settle(s)
        assert s.state.cards[source.id].attached_to == bear.id
    assert s.state.cards[source.id].zone == ('p1:battlefield' if other_aura else 'p1:graveyard')
    roundtrip(s)
