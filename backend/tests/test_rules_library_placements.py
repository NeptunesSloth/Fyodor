"""Aetherspouts: APNAP public placements followed by private pile orders, one move."""
from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.view import decision_view
from tests.conftest import connect_game
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_owner_library_choices import cards as _cards
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

cards = _cards


def settle(s):
    for _ in range(100):
        if s.state.rules.decision or not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("Resolution did not finish")


def setup(cards):
    names = ['Grizzly Bears', 'Goblin Piker', 'Serra Angel', 'Arbor Elf', 'Gemrazer', 'Carnage Tyrant', 'Dregscape Zombie']
    return table(cards, ['Aetherspouts', 'Tolarian Contempt', *names], names, names)


def cast_spouts(s):
    spell = put(s, 'Aetherspouts', 'hand')
    wait_priority(s, 'p1')
    mana(s, U=2, C=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[])
    settle(s)
    return spell


def choose(s, player, ids):
    d = s.state.rules.decision
    assert d and d.player == player
    roundtrip(s)
    act(s, player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


@pytest.mark.parametrize('name', ['Aetherspouts', 'Tolarian Contempt'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_no_attackers_no_choices(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    cast_spouts(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    roundtrip(s)


def test_two_phase_placements_then_private_order_and_one_batch(cards):
    s = setup(cards)
    bears = [put(s, name, 'battlefield', pid='p2') for name in ['Grizzly Bears', 'Goblin Piker', 'Serra Angel', 'Arbor Elf']]
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, *((c, 'p1') for c in bears), pid='p2')
    cast_spouts(s)
    choose(s, 'p2', [bears[0].id, bears[1].id])
    assert all(s.state.cards[c.id].zone == 'p2:battlefield' for c in bears)
    d = s.state.rules.decision
    assert d and d.kind == 'order'
    assert 'options' not in decision_view(s.state, d, 'p1')
    assert 'options' not in decision_view(s.state, d, 'p3')
    choose(s, 'p2', [bears[1].id, bears[0].id])
    assert all(s.state.cards[c.id].zone == 'p2:battlefield' for c in bears)
    choose(s, 'p2', [bears[2].id, bears[3].id])
    lib = s.state.zones['p2:library']
    assert lib[:2] == [bears[1].id, bears[0].id]
    assert lib[-2:] == [bears[3].id, bears[2].id]
    events = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in {c.id for c in bears} and e.to_zone == 'p2:library']
    assert len(events) == 4 and len({e.batch for e in events}) == 1
    roundtrip(s)


def test_multiple_owners_choose_apnap_not_controller_order(cards):
    s = setup(cards)
    creatures = [put(s, 'Grizzly Bears', 'battlefield', pid=p) for p in ['p1', 'p2', 'p3']]
    act(s, 'p2', type='set_controller', card_ids=[creatures[0].id, creatures[2].id], player='p2')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, *((c, 'p1') for c in creatures), pid='p2')
    cast_spouts(s)
    for player, c in [('p2', creatures[1]), ('p3', creatures[2]), ('p1', creatures[0])]:
        assert all(s.state.cards[x.id].zone.endswith(':battlefield') for x in creatures)
        choose(s, player, [c.id])
    for c in creatures:
        assert s.state.zones[f'{c.owner}:library'][0] == c.id
    roundtrip(s)


def test_tolarian_contmpt_rejection_and_per_opponent_optional_targets_share_one_instruction(cards):
    s = setup(cards)
    first = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    second = put(s, 'Goblin Piker', 'battlefield', pid='p3')
    own = put(s, 'Serra Angel', 'battlefield', pid='p1')
    enchantment = put(s, 'Tolarian Contempt', 'hand')
    mana(s, U=2, C=3)
    act(s, 'p1', type='cast_spell', card_id=enchantment.id, targets=[])
    settle(s)
    assert s.state.cards[first.id].counters.get('rejection') == 1
    assert s.state.cards[second.id].counters.get('rejection') == 1
    assert not s.state.cards[own.id].counters.get('rejection')
    to_phase(s, 'end', turn=1)
    settle(s)
    for target in [first, second]:
        d = s.state.rules.decision
        assert d and d.player == 'p1' and d.min_choices == 0
        assert target.id in {o.id for o in d.options}
        choose(s, 'p1', [target.id])
    assert s.state.rules.decision and s.state.rules.decision.player == 'p2'
    choose(s, 'p2', [first.id])
    assert s.state.cards[first.id].zone == 'p2:battlefield'
    choose(s, 'p3', [])
    assert s.state.zones['p2:library'][0] == first.id
    assert s.state.zones['p3:library'][-1] == second.id
    events = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in {first.id, second.id} and (e.to_zone or '').endswith(':library')]
    assert len(events) == 2 and len({e.batch for e in events}) == 1
    roundtrip(s)


@pytest.mark.parametrize('command', [True, False])
def test_commander_replacement_prepared_before_atomic_move(cards, command):
    s = setup(cards)
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    act(s, 'p2', type='set_controller', card_ids=[commander.id], player='p2')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (bear, 'p1'), (commander, 'p1'), pid='p2')
    cast_spouts(s)
    choose(s, 'p2', [bear.id])
    choose(s, 'p1', [commander.id])
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {'yes', 'no'}
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    choose(s, 'p1', ['yes' if command else 'no'])
    assert s.state.cards[commander.id].zone == ('p1:command' if command else 'p1:library')
    assert s.state.zones['p2:library'][0] == bear.id
    events = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in {bear.id, commander.id} and (e.from_zone or '').endswith(':battlefield')]
    assert len(events) == 2 and len({e.batch for e in events}) == 1
    roundtrip(s)


def test_unearth_replacement_stays_atomic_with_other_library_moves(cards):
    s = setup(cards)
    zombie = put(s, 'Dregscape Zombie', 'graveyard', pid='p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    to_phase(s, 'main1', turn=2)
    mana(s, pid='p2', B=1)
    act(s, 'p2', type='activate_ability', card_id=zombie.id, ability=0)
    settle(s)
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (bear, 'p1'), (zombie, 'p1'), pid='p2')
    cast_spouts(s)
    choose(s, 'p2', [bear.id])
    assert s.state.cards[zombie.id].zone == 'p2:exile'
    assert s.state.zones['p2:library'][0] == bear.id
    events = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in {bear.id, zombie.id} and e.from_zone == 'p2:battlefield']
    assert len(events) == 2 and len({e.batch for e in events}) == 1
    roundtrip(s)


def test_new_incarnation_while_placement_pending_is_not_moved(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    piker = put(s, 'Goblin Piker', 'battlefield', pid='p2')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (bear, 'p1'), (piker, 'p1'), pid='p2')
    cast_spouts(s)
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'exile'})
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'battlefield'})
    choose(s, 'p2', [bear.id])
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    assert s.state.zones['p2:library'][-1] == piker.id
    roundtrip(s)


@pytest.mark.parametrize('command', [True, False])
def test_merged_commander_components_keep_private_order_and_one_batch(cards, command):
    from tests.test_rules_wave18d_merged import mutate

    s = setup(cards)
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    own = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Goblin Piker', 'battlefield', pid='p2')
    mutate(s, 'Gemrazer', commander, G=3)
    host = s.state.cards[commander.id]
    gem_part = next(p.id for p in host.merged if p.name == 'Gemrazer')
    act(s, 'p2', type='set_controller', card_ids=[host.id, own.id], player='p2')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (host, 'p1'), (own, 'p1'), (other, 'p1'), pid='p2')
    cast_spouts(s)
    choose(s, 'p2', [])
    choose(s, 'p1', [host.id, own.id])
    choose(s, 'p1', ['yes' if command else 'no'])
    d = s.state.rules.decision
    assert d and d.kind == 'order' and d.player == 'p1'
    order = [own.id, gem_part] + ([] if command else [commander.id])
    assert {o.id for o in d.options} == set(order)
    assert s.state.cards[commander.id].zone.endswith(':battlefield')
    choose(s, 'p1', order)
    assert s.state.zones['p1:library'][:len(order)] == order
    assert s.state.cards[commander.id].zone == ('p1:command' if command else 'p1:library')
    assert s.state.zones['p2:library'][-1] == other.id
    events = [e for e in s.state.rules.events if e.kind == 'zone_change' and e.card in {commander.id, own.id, other.id} and (e.from_zone or '').endswith(':battlefield')]
    assert len(events) == 3 and len({e.batch for e in events}) == 1
    roundtrip(s)


def test_token_attacker_ceases_but_other_attackers_move(cards):
    s = setup(cards)
    krenko = put(s, 'Krenko, Mob Boss', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=krenko.id, ability=0)
    settle(s)
    token = next(c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield')
    act(s, 'p2', type='set_controller', card_ids=[token.id], player='p2')
    to_phase(s, 'declare_attackers', turn=5)
    attack(s, (bear, 'p1'), (token, 'p1'), pid='p2')
    cast_spouts(s)
    choose(s, 'p2', [bear.id])
    choose(s, 'p1', [token.id])
    assert token.id not in s.state.cards
    assert s.state.zones['p2:library'][0] == bear.id
    roundtrip(s)


def test_private_library_order_does_not_enter_rest_websocket_or_history_payloads(cards, settings):
    import json

    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    piker = put(s, 'Goblin Piker', 'battlefield', pid='p2')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (bear, 'p1'), (piker, 'p1'), pid='p2')
    cast_spouts(s)
    choose(s, 'p2', [bear.id, piker.id])
    d = s.state.rules.decision
    assert d and d.kind == 'order'
    with TestClient(create_app(settings)) as client:
        room = client.app.state.services.hub.create_room(s, mode='lan')
        room.seats['p1'].token = 'library-observer'
        room.seats['p2'].token = 'library-owner'
        headers = {'X-Seat-Token': 'library-observer'}
        pending = client.get(f'/api/games/{room.id}/view', headers=headers)
        assert pending.status_code == 200
        assert 'options' not in pending.json()['rules']['decision']
        with connect_game(client, room.id, 'library-observer') as ws:
            initial = ws.receive_json()
            assert 'library_order' not in json.dumps(initial)
            response = client.post(f'/api/games/{room.id}/actions', headers={'X-Seat-Token': 'library-owner'},
                                   json={'action': {'type': 'choose', 'decision_id': d.id, 'option_ids': [piker.id, bear.id]}})
            assert response.status_code == 200, response.text
            for _ in range(4):
                frame = ws.receive_json()
                assert 'library_order' not in json.dumps(frame)
                if frame.get('type') == 'state' and frame['view']['rules']['decision'] is None:
                    break
            else:
                raise AssertionError('No completed state broadcast')
        for path in ['view', 'history', f'history/{s.history.cursor}']:
            response = client.get(f'/api/games/{room.id}/{path}', headers=headers)
            assert response.status_code == 200, response.text
            assert 'library_order' not in response.text and 'library_positions' not in response.text
            if path != 'history':
                assert response.json()['zones']['p2:library']['known'] == []
                assert bear.id not in response.json()['cards'] and piker.id not in response.json()['cards']
    assert s.state.zones['p2:library'][:2] == [piker.id, bear.id]
    roundtrip(s)


@pytest.mark.parametrize('stage', ['place', 'commander', 'order'])
def test_saved_placement_stages_resume_in_fresh_process(cards, tmp_path, stage):
    import subprocess
    import sys
    from pathlib import Path

    s = setup(cards)
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    piker = put(s, 'Goblin Piker', 'battlefield', pid='p2')
    act(s, 'p2', type='set_controller', card_ids=[commander.id], player='p2')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (commander, 'p1'), (bear, 'p1'), (piker, 'p1'), pid='p2')
    cast_spouts(s)
    if stage != 'place':
        choose(s, 'p2', [bear.id, piker.id])
        choose(s, 'p1', [commander.id])
    if stage == 'order':
        choose(s, 'p1', ['yes'])
    assert s.state.rules.decision.resume['stage'] == stage
    saved = tmp_path / 'library-placement.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import engine
from tests.game_helpers import act
state = GameState.model_validate_json(Path(sys.argv[1]).read_text())
repo = CardRepository(Path(sys.argv[2]), ImageStore(Path(sys.argv[2]).parent / 'images'))
s = GameSession(state, cards=repo)
assert 'library_placements' in engine.RESUME
for _ in range(100):
    d = s.state.rules.decision
    if d:
        stage = d.resume['stage']
        chosen = ['yes'] if stage == 'commander' else [o.id for o in d.options]
        if stage == 'order': chosen.reverse()
        act(s, d.player, type='choose', decision_id=d.id, option_ids=chosen)
    elif s.state.zones.get('stack'):
        act(s, s.state.rules.priority, type='pass_priority')
    else: break
else: raise AssertionError('did not finish')
assert s.state.cards[sys.argv[3]].zone == 'p1:command'
assert s.state.cards[sys.argv[4]].zone == 'p2:library'
assert s.state.cards[sys.argv[5]].zone == 'p2:library'
assert s.state.zones['p2:library'][:2] == [sys.argv[5],sys.argv[4]]
assert s.history.state_at(s.history.cursor).model_dump() == s.state.model_dump()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), commander.id, bear.id, piker.id],
                            cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


def test_tolarian_can_choose_no_targets_for_every_opponent(cards):
    s = setup(cards)
    first = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    second = put(s, 'Goblin Piker', 'battlefield', pid='p3')
    enchantment = put(s, 'Tolarian Contempt', 'hand')
    mana(s, U=2, C=3)
    act(s, 'p1', type='cast_spell', card_id=enchantment.id, targets=[])
    settle(s)
    to_phase(s, 'end', turn=1)
    settle(s)
    while s.state.rules.decision:
        d = s.state.rules.decision
        assert d.player == 'p1' and d.min_choices == 0
        choose(s, 'p1', [])
    assert s.state.cards[first.id].zone == 'p2:battlefield'
    assert s.state.cards[second.id].zone == 'p3:battlefield'
    roundtrip(s)


def test_aetherspouts_is_untargeted_and_leaves_nonattackers_alone(cards):
    s = setup(cards)
    tyrant = put(s, 'Carnage Tyrant', 'battlefield', pid='p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    nonattacker = put(s, 'Goblin Piker', 'battlefield', pid='p2')
    to_phase(s, 'declare_attackers', turn=2)
    attack(s, (tyrant, 'p1'), (bear, 'p1'), pid='p2')
    cast_spouts(s)
    choose(s, 'p2', [tyrant.id])
    assert s.state.zones['p2:library'][0] == tyrant.id
    assert s.state.zones['p2:library'][-1] == bear.id
    assert s.state.cards[nonattacker.id].zone == 'p2:battlefield'
    roundtrip(s)
