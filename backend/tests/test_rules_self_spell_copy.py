"""CR 707.10: conditional copies of the resolving spell."""
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
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/self_spell_copy_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def test_sevinne_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Sevinne's Reclamation")).level == 'FULL'


@pytest.mark.parametrize('origin', ['hand', 'graveyard'])
@pytest.mark.parametrize('accept', [False, True])
def test_self_copy_only_if_cast_from_graveyard_and_copy_is_not_cast(cards, origin, accept):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ["Sevinne's Reclamation", 'Sol Ring', 'Grizzly Bears'], [], [])
    spell = put(s, "Sevinne's Reclamation", origin)
    ring = put(s, 'Sol Ring', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    mana(s, W=5)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ring.id])
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    if origin == 'graveyard':
        d = s.state.rules.decision
        assert d and 'copy this spell' in d.prompt.lower()
        roundtrip(s)
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay' if accept else 'decline'])
        if accept:
            d = s.state.rules.decision
            assert d and bear.id in {o.id for o in d.options}
            roundtrip(s)
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[bear.id])
        settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].zone == ('p1:battlefield' if origin == 'graveyard' and accept else 'p1:graveyard')
    assert s.state.cards[spell.id].zone == ('p1:exile' if origin == 'graveyard' else 'p1:graveyard')
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_self_copy_can_keep_now_illegal_target_and_does_not_return_it_twice(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ["Sevinne's Reclamation", 'Sol Ring', 'Grizzly Bears'], [], [])
    spell = put(s, "Sevinne's Reclamation", 'graveyard')
    ring = put(s, 'Sol Ring', 'graveyard')
    put(s, 'Grizzly Bears', 'graveyard')
    mana(s, W=5)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ring.id])
    settle(s)
    d = s.state.rules.decision
    assert d and 'copy this spell' in d.prompt.lower()
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['pay'])
    d = s.state.rules.decision
    assert d and 'keep' in {o.id for o in d.options}
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:battlefield'
    assert not s.state.zones.get('stack')
    assert s.state.rules.decision is None
    roundtrip(s)


def test_original_with_illegal_target_does_not_offer_self_copy(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ["Sevinne's Reclamation", 'Sol Ring'], [], [])
    spell = put(s, "Sevinne's Reclamation", 'graveyard')
    ring = put(s, 'Sol Ring', 'graveyard')
    mana(s, W=5)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[ring.id])
    act(s, 'p1', type='move', card_ids=[ring.id], to={'player': 'p1', 'zone': 'exile'})
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.zones.get('stack')
    assert s.state.cards[spell.id].zone == 'p1:exile'
    roundtrip(s)
