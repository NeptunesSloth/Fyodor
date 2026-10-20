"""CR 305.1 / 305.4: restrictions on land plays, rather than putting lands onto the battlefield."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/land_play_limits_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Territorial Dispute', 'Solfatara', 'Turf Wound', 'Pardic Miner'])
def test_land_play_limit_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_territorial_dispute_stops_every_players_land_play_and_ends_when_it_leaves(cards):
    from app.game.errors import ActionError

    s = table(cards, ['Territorial Dispute'], [], [])
    source = put(s, 'Territorial Dispute', 'battlefield')
    for turn, pid in enumerate(['p1', 'p2', 'p3'], start=1):
        to_phase(s, 'main1', turn=turn)
        forest = put(s, 'Forest' if pid == 'p1' else 'Island', 'hand', pid)
        with pytest.raises(ActionError, match="can't play"):
            act(s, pid, type='play_land', card_id=forest.id)
        assert s.state.cards[forest.id].zone == f'{pid}:hand'
        roundtrip(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p3', type='play_land', card_id=forest.id)
    assert s.state.cards[forest.id].zone == 'p3:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Solfatara', 'Turf Wound'])
def test_temporary_land_play_limit_only_stops_the_target_for_this_turn_and_still_draws(cards, name):
    from app.game.errors import ActionError

    s = table(cards, [name], [], [])
    forest2 = put(s, 'Island', 'hand', 'p2')
    forest3 = put(s, 'Island', 'hand', 'p3')
    to_phase(s, 'main1', turn=2)
    spell = put(s, name, 'hand')
    wait_priority(s, 'p1')
    mana(s, C=2, R=1)
    before = len(s.state.zones['p1:hand'])
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p2'])
    settle(s)
    assert len(s.state.zones['p1:hand']) == before - (name == 'Solfatara')
    wait_priority(s, 'p2')
    with pytest.raises(ActionError, match="can't play"):
        act(s, 'p2', type='play_land', card_id=forest2.id)
    roundtrip(s)
    to_phase(s, 'main1', turn=3)
    assert len(s.state.zones['p1:hand']) == before
    act(s, 'p3', type='play_land', card_id=forest3.id)
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=forest2.id)
    roundtrip(s)


@pytest.mark.parametrize('name', ['Territorial Dispute', 'Solfatara', 'Turf Wound'])
def test_land_play_restrictions_do_not_stop_spells_or_putting_a_land_onto_the_battlefield(cards, name):
    from app.game.errors import ActionError

    s = table(cards, [name, 'Rampant Growth'], [], [])
    if name == 'Territorial Dispute':
        put(s, name, 'battlefield')
    else:
        source = put(s, name, 'hand')
        mana(s, C=2, R=1)
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p1'])
        settle(s)
    growth = put(s, 'Rampant Growth', 'hand')
    mana(s, C=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=growth.id)
    settle(s)
    d = s.state.rules.decision
    assert d and d.options
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert any(s.state.cards[cid].name == 'Forest' for cid in s.state.zones['p1:battlefield'])
    forest = put(s, 'Forest', 'hand')
    with pytest.raises(ActionError, match="can't play"):
        act(s, 'p1', type='play_land', card_id=forest.id)
    roundtrip(s)


def test_pardic_miner_sacrifices_itself_and_stops_the_targets_land_play_until_cleanup(cards):
    from app.game.errors import ActionError

    s = table(cards, ['Pardic Miner'], [], [])
    miner = put(s, 'Pardic Miner', 'battlefield')
    land = put(s, 'Island', 'hand', 'p2')
    to_phase(s, 'main1', turn=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=miner.id, ability=0, targets=['p2'])
    assert s.state.cards[miner.id].zone == 'p1:graveyard'
    roundtrip(s)
    settle(s)
    wait_priority(s, 'p2')
    with pytest.raises(ActionError, match="can't play"):
        act(s, 'p2', type='play_land', card_id=land.id)
    roundtrip(s)
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='play_land', card_id=land.id)
    roundtrip(s)
