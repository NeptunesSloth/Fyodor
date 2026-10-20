"""Linked owner returns keep source incarnations and heterogeneous targets separate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Bane Alley Broker", "Colfenor's Plans", "Kheru Mind-Eater", "Three Wishes", "Ixhel, Scion of Atraxa"]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/linked_exile_look_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='lor', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize("name", NAMES)
def test_canonical_cards_are_full(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == "FULL", result


def setup(cards, name):
    support = ['Grizzly Bears', 'Lightning Bolt', 'Counterspell', 'Unsummon', 'Naturalize', 'Word of Seizing', 'Song of the Dryads', 'Cloudshift']
    s = table(cards, [name, *support], support, support)
    for p in ['p1', 'p2', 'p3']:
        act(s, p, type='set_prefs', hold_priority=True)
    return s, put(s, name, 'battlefield' if name in ['Bane Alley Broker', 'Kheru Mind-Eater', 'Ixhel, Scion of Atraxa'] else 'hand')


def assert_look(s, cid, viewers):
    from app.game.visibility import SPECTATOR, can_see
    for p in ['p1', 'p2', 'p3', SPECTATOR]:
        assert can_see(s.state, s.state.cards[cid], p) == (p in viewers), (cid, p, viewers)
        payload = json.dumps(s.view(p)['cards'].get(cid, {}))
        if p not in viewers:
            assert s.state.cards[cid].card_id not in payload
            assert s.state.cards[cid].name not in payload


def broker_exile(s, broker):
    to_phase(s, 'main1', turn=4)
    bear = put(s, 'Grizzly Bears', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=broker.id, ability=0)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    return next(c for c in s.state.cards.values() if c.zone == 'p1:exile')


def test_broker_native_private_exile_then_return(cards):
    s, broker = setup(cards, 'Bane Alley Broker')
    exiled = broker_exile(s, broker)
    assert exiled.face_down
    assert_look(s, exiled.id, {'p1'})
    roundtrip(s)
    to_phase(s, 'main1', turn=7)
    mana(s, U=1, B=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=broker.id, ability=2)
    settle(s)
    assert not s.state.zones['p1:exile']
    assert any(s.state.cards[c].name == 'Grizzly Bears' for c in s.state.zones['p1:hand'])
    roundtrip(s)


def test_wishes_native_cast_and_exact_upkeep_cleanup(cards):
    s, source = setup(cards, 'Three Wishes')
    put(s, 'Grizzly Bears', 'library')
    bolt = put(s, 'Lightning Bolt', 'library')
    mana(s, C=1, U=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    exile = list(s.state.zones['p1:exile'])
    assert len(exile) == 3
    for cid in exile:
        assert_look(s, cid, {'p1'})
    cid = next(c for c in exile if s.state.cards[c].name == 'Lightning Bolt')
    mana(s, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    to_phase(s, 'main1', turn=4)
    assert not s.state.zones['p1:exile']
    assert s.state.cards[bolt.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_colfenor_native_entry_static_play_and_limit(cards):
    s, source = setup(cards, "Colfenor's Plans")
    put(s, 'Lightning Bolt', 'library')
    put(s, 'Grizzly Bears', 'library')
    mana(s, C=2, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    exile = list(s.state.zones['p1:exile'])
    assert len(exile) == 7
    for cid in exile:
        assert_look(s, cid, {'p1'})
    # Casting the Plans itself already consumed this turn's single spell allowance.
    bolt = next(c for c in exile if s.state.cards[c].name == 'Lightning Bolt')
    mana(s, R=1)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    to_phase(s, 'main1', turn=4)
    mana(s, R=1)
    act(s, 'p1', type='cast_spell', card_id=bolt, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_ixhel_qualifies_each_opponent_and_grants_cross_owner_play(cards):
    s, source = setup(cards, 'Ixhel, Scion of Atraxa')
    put(s, 'Lightning Bolt', 'library', pid='p2')
    put(s, 'Grizzly Bears', 'library', pid='p3')
    act(s, 'p1', type='set_resource', player='p2', key='poison', value=3)
    act(s, 'p1', type='set_resource', player='p3', key='poison', value=2)
    to_phase(s, 'end', turn=1)
    settle(s)
    assert len(s.state.zones['p2:exile']) == 1
    assert not s.state.zones['p3:exile']
    cid = s.state.zones['p2:exile'][0]
    assert_look(s, cid, {'p1'})
    # Resolved authority belongs to p1 even after its original source leaves.
    removal = put(s, 'Unsummon', 'hand', pid='p2')
    mana(s, 'p2', U=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert_look(s, cid, {'p1'})
    wait_priority(s, 'p1')
    mana(s, G=1)
    act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 37
    roundtrip(s)


def test_broker_source_gone_before_exile_never_grants_look(cards):
    s, broker = setup(cards, 'Bane Alley Broker')
    to_phase(s, 'main1', turn=4)
    bear = put(s, 'Grizzly Bears', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=broker.id, ability=0)
    removal = put(s, 'Unsummon', 'hand')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[broker.id])
    until(s, lambda s: s.state.rules.decision is not None)
    assert s.state.cards[broker.id].zone == 'p1:hand'
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    exiled = s.state.zones['p1:exile'][0]
    assert_look(s, exiled, set())
    roundtrip(s)


def test_broker_controller_change_retains_old_look_and_new_static_authority(cards):
    s, broker = setup(cards, 'Bane Alley Broker')
    exiled = broker_exile(s, broker)
    stealing = put(s, 'Word of Seizing', 'hand', pid='p2')
    mana(s, 'p2', C=3, R=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=stealing.id, targets=[broker.id])
    settle(s)
    assert s.state.cards[broker.id].controller == 'p2'
    assert_look(s, exiled.id, {'p1', 'p2'})
    mana(s, 'p2', U=1, B=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=broker.id, ability=2)
    settle(s)
    assert any(s.state.cards[c].name == 'Grizzly Bears' for c in s.state.zones['p1:hand'])
    roundtrip(s)


def test_kheru_native_combat_private_choice_and_cross_owner_cast(cards):
    s, source = setup(cards, 'Kheru Mind-Eater')
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    put(s, 'Grizzly Bears', 'hand', pid='p2')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'choose_cards')
    d = s.state.rules.decision
    assert d.player == 'p2'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[bolt.id])
    settle(s)
    cid = s.state.zones['p2:exile'][0]
    assert_look(s, cid, {'p1'})
    mana(s, R=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=cid, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 36  # one combat damage, then three from Bolt
    roundtrip(s)


def test_static_ability_loss_does_not_authorize_future_controller(cards):
    s, broker = setup(cards, 'Bane Alley Broker')
    exiled = broker_exile(s, broker)
    song = put(s, 'Song of the Dryads', 'hand')
    mana(s, C=2, G=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=song.id, targets=[broker.id])
    settle(s)
    stealing = put(s, 'Word of Seizing', 'hand', pid='p2')
    mana(s, 'p2', C=3, R=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=stealing.id, targets=[broker.id])
    settle(s)
    assert s.state.cards[broker.id].controller == 'p2'
    assert_look(s, exiled.id, {'p1'})
    roundtrip(s)


def test_broker_pending_hand_choice_cold_load_and_native_record(cards, tmp_path):
    from app.game.session import GameSession
    from app.game.state import GameState

    s, broker = setup(cards, 'Bane Alley Broker')
    to_phase(s, 'main1', turn=4)
    bear = put(s, 'Grizzly Bears', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=broker.id, ability=0)
    until(s, lambda s: s.state.rules.decision is not None)
    path = tmp_path / 'pending.json'
    out = tmp_path / 'resolved.json'
    path.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[1]), ImageStore(Path(sys.argv[2])))
s=GameSession(GameState.model_validate_json(Path(sys.argv[3]).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[sys.argv[5]]})
Path(sys.argv[4]).write_text(s.state.model_dump_json())
'''
    result = subprocess.run([sys.executable, '-c', code, str(cards.db_path),
                             str(tmp_path / 'images'), str(path), str(out), bear.id], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    resumed = GameSession(GameState.model_validate_json(out.read_text()), cards=cards)
    settle(resumed)
    cid = resumed.state.zones['p1:exile'][0]
    assert_look(resumed, cid, {'p1'})
    assert resumed.state.rules.exiled_with


def test_colfenor_source_departure_keeps_look_but_revokes_play(cards):
    s, source = setup(cards, "Colfenor's Plans")
    put(s, 'Grizzly Bears', 'library')
    mana(s, C=2, B=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    exiled = next(c for c in s.state.zones['p1:exile'] if s.state.cards[c].name == 'Grizzly Bears')
    to_phase(s, 'main1', turn=2)
    removal = put(s, 'Naturalize', 'hand', pid='p2')
    mana(s, 'p2', C=1, G=1)
    act(s, 'p2', type='cast_spell', card_id=removal.id, targets=[source.id])
    settle(s)
    assert_look(s, exiled, {'p1'})
    to_phase(s, 'main1', turn=4)
    mana(s, C=1, G=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=exiled)
    roundtrip(s)


def test_actual_skill_borrower_has_no_static_look_and_separate_donor_links(cards):
    from tests.test_rules_wave7b_activation import ability_index

    s = table(cards, ['Skill Borrower', 'Bane Alley Broker', 'Bane Alley Broker', 'Grizzly Bears', 'Lightning Bolt'], [], [])
    act(s, 'p1', type='set_prefs', hold_priority=True)
    borrower = put(s, 'Skill Borrower', 'battlefield')
    donors = [c.id for c in s.state.cards.values() if c.name == 'Bane Alley Broker']
    to_phase(s, 'main1', turn=4)
    for donor, cardname in zip(donors, ['Grizzly Bears', 'Lightning Bolt'], strict=True):
        act(s, 'p1', type='move', card_ids=[donor], to={'player': 'p1', 'zone': 'library'}, position='top')
        choice = put(s, cardname, 'hand')
        if s.state.cards[borrower.id].tapped:
            act(s, 'p1', type='tap', card_ids=[borrower.id], tapped=False)
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=borrower.id, ability=ability_index(s, s.state.cards[borrower.id], 'Draw a card'))
        until(s, lambda s: s.state.rules.decision is not None)
        d = s.state.rules.decision
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[choice.id])
        settle(s)
    pools = {key: value for key, value in s.state.rules.exiled_with.items() if '|borrowed:' in key}
    assert len(pools) == 2 and all(len(v) == 1 for v in pools.values())
    for cid in s.state.zones['p1:exile']:
        assert_look(s, cid, set())
    act(s, 'p1', type='move', card_ids=[donors[0]], to={'player': 'p1', 'zone': 'library'}, position='top')
    act(s, 'p1', type='tap', card_ids=[borrower.id], tapped=False)
    mana(s, U=1, B=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=borrower.id, ability=ability_index(s, s.state.cards[borrower.id], 'Return a card'))
    settle(s)
    # Drawing the donor moved it out of the library: reacquiring that physical
    # card after another zone change is a new ability incarnation, not its old link.
    assert len(s.state.zones['p1:exile']) == 2
    assert {s.state.cards[c].name for c in s.state.zones['p1:exile']} == {'Grizzly Bears', 'Lightning Bolt'}
    roundtrip(s)
