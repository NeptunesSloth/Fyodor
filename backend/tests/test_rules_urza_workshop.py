"""CR 111.2, 608.2h: conditional attached copy and actual creation fallback."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/urza_workshop_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




NAME = "Urza's Workshop"


def setup(cards, artifacts=3, extra_lands=True):
    s = table(cards, [NAME, "Urza's Tower", "Urza's Mine", 'Darksteel Citadel', 'Sol Ring', 'Mind Stone',
                     "Urza's Armor", 'Darksteel Ingot', 'Spreading Seas', "Brass's Bounty"], ["Urza's Power Plant"])
    source = put(s, NAME, 'battlefield')
    lands = [put(s, name, 'battlefield') for name in ["Urza's Tower", "Urza's Mine"]] if extra_lands else []
    other = put(s, "Urza's Power Plant", 'battlefield', 'p2')
    made = [put(s, name, 'battlefield') for name in ['Sol Ring', 'Mind Stone', 'Darksteel Citadel'][:artifacts]]
    return s, source, lands, other, made


def test_full_canonical_workshop(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


def test_ordinary_colorless_ability_remains_available_without_metalcraft(cards):
    s, source, _, _, _ = setup(cards, artifacts=0)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert mana_pool(s) == {'C': 1} and s.state.cards[source.id].tapped
    roundtrip(s)


def test_third_artifact_land_enables_scaled_mana_counts_each_urza_land_once(cards):
    from app.game.errors import ActionError

    s, source, _, _, _ = setup(cards, artifacts=2)
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert s.state.model_dump(mode='json') == before
    put(s, 'Darksteel Citadel', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    # Workshop (Urza's), Tower (Urza's Tower), Mine (Urza's Mine): three
    # objects, not five subtypes; the opponent's Power-Plant is excluded.
    assert mana_pool(s) == {'C': 3} and not s.state.zones.get('stack')
    roundtrip(s)


def test_workshop_counts_itself_and_artifact_name_does_not_count_as_a_land(cards):
    s, source, _, _, _ = setup(cards, artifacts=2, extra_lands=False)
    put(s, "Urza's Armor", 'battlefield')  # Third artifact; its name does not make it an Urza's land.
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert mana_pool(s) == {'C': 1}
    roundtrip(s)


def test_other_urza_land_control_change_changes_current_count(cards):
    s, source, lands, _, _ = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[lands[0].id], player='p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert mana_pool(s) == {'C': 2}
    roundtrip(s)


def test_source_controller_reads_own_artifacts_and_own_urza_lands(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import wait_priority

    s, source, _, _, artifacts = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    wait_priority(s, 'p2')
    with pytest.raises(ActionError):
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=1)
    act(s, 'p1', type='set_controller', card_ids=[c.id for c in artifacts], player='p2')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=1)
    assert mana_pool(s, 'p2') == {'C': 2} and mana_pool(s) == {}
    roundtrip(s)


def test_current_derived_land_types_determine_count(cards):

    s, source, lands, _, _ = setup(cards)
    spell = put(s, 'Spreading Seas', 'hand')
    mana(s, C=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[lands[0].id])
    settle(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert mana_pool(s) == {'C': 2}
    roundtrip(s)


@pytest.mark.parametrize('artifacts,succeeds', [(2, False), (3, True)])
def test_automatic_payment_respects_metalcraft_and_scaled_output(cards, artifacts, succeeds):
    from app.game.errors import ActionError

    s, source, lands, _, made = setup(cards, artifacts=artifacts)
    act(s, 'p1', type='configure', automation_options={'auto_mana_payment': True})
    act(s, 'p1', type='tap', card_ids=[c.id for c in [*lands, *made]], tapped=True)
    spell = put(s, 'Darksteel Ingot', 'hand')
    if succeeds:
        act(s, 'p1', type='cast_spell', card_id=spell.id)
        assert s.state.cards[source.id].tapped
        settle(s)
        assert s.state.cards[spell.id].zone == 'p1:battlefield'
        assert mana_pool(s) == {}
    else:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=spell.id)
        assert not s.state.cards[source.id].tapped
        assert s.state.cards[spell.id].zone == 'p1:hand'
    roundtrip(s)


def test_losing_third_artifact_disables_scaled_ability_again(cards):
    from app.game.errors import ActionError
    from app.rules.casting import mana_abilities

    s, source, _, _, made = setup(cards)
    assert 1 in dict(mana_abilities(s.state, s.state.cards[source.id], s.cards))
    act(s, 'p1', type='move', card_ids=[made[-1].id], to={'player': 'p1', 'zone': 'exile'})
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert not s.state.cards[source.id].tapped and mana_pool(s) == {}
    roundtrip(s)


def test_actual_treasure_tokens_count_toward_metalcraft(cards):
    from tests.test_rules_bandmate_references import mana

    s, source, _, _, _ = setup(cards, artifacts=0)
    spell = put(s, "Brass's Bounty", 'hand')
    mana(s, C=6, R=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.is_token and c.name == 'Treasure' and c.controller == 'p1']) == 3
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert mana_pool(s) == {'C': 3}
    roundtrip(s)
