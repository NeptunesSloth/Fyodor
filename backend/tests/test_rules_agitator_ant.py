"""Untargeted, APNAP counter offers preserve putters and goad actual recipients."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_wave30m_durations import three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/agitator_ant_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='ago', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, *, extras=(), opponents=(), bear='Grizzly Bears'):
    s = three(cards, ['Agitator Ant', bear, *extras], [bear, *opponents], [bear, *opponents])
    hold(s)
    ant = put(s, 'Agitator Ant', 'battlefield')
    creatures = [put(s, bear, 'battlefield', p) for p in ['p1', 'p2', 'p3']]
    return s, ant, creatures


def trigger(s):
    to_phase(s, 'end')
    settle(s)


def choose(s, creature=None):
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'counter_offer'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[creature.id] if creature else [])
    settle(s)


def goaders(s, card):
    from app.rules import keyword_actions

    return keyword_actions.goaded_by(Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[card.id]))


def test_real_card_is_fully_supported(cards):
    result = coverage.of_card_data(cards.resolve('Agitator Ant'))
    assert result.level == 'FULL', result.manual_parts


def test_every_player_chooses_before_counters_are_placed_together_by_their_actual_player(cards):
    s, _, creatures = setup(cards)
    trigger(s)
    for p, creature in zip(['p1', 'p2', 'p3'], creatures, strict=True):
        assert s.state.rules.decision.player == p
        assert all(not s.state.cards[c.id].counters for c in creatures)
        choose(s, creature)
    assert all(s.state.cards[c.id].counters['+1/+1'] == 2 and goaders(s, c) == {'p1'} for c in creatures)
    events = [e for e in s.state.rules.events if e.kind == 'counters' and e.card in {c.id for c in creatures}]
    assert len(events) == 3 and len({e.group for e in events}) == 1 and events[0].group is not None
    assert {e.card: e.actor for e in events} == {c.id: p for c, p in zip(creatures, ['p1', 'p2', 'p3'], strict=True)}
    roundtrip(s)


def test_players_can_decline_even_with_only_one_creature_and_are_not_targeted(cards):
    s, _, creatures = setup(cards, bear='Slippery Bogle')
    trigger(s)
    choose(s)
    choose(s, creatures[1])
    choose(s)
    assert not s.state.cards[creatures[0].id].counters and not goaders(s, creatures[0])
    assert s.state.cards[creatures[1].id].counters['+1/+1'] == 2 and goaders(s, creatures[1]) == {'p1'}
    assert not s.state.cards[creatures[2].id].counters and not goaders(s, creatures[2])
    roundtrip(s)


def test_counter_prohibition_excludes_creatures_instead_of_goading_without_counters(cards):
    s, _, creatures = setup(cards, extras=['Solemnity'])
    put(s, 'Solemnity', 'battlefield')
    trigger(s)
    assert s.state.rules.decision is None
    assert all(not s.state.cards[c.id].counters and not goaders(s, c) for c in creatures)
    roundtrip(s)


def test_counter_doubling_uses_the_resolution_effect_and_goads_once(cards):
    s, _, creatures = setup(cards, extras=['Doubling Season'])
    put(s, 'Doubling Season', 'battlefield')
    trigger(s)
    for creature in creatures:
        choose(s, creature)
    assert [s.state.cards[c.id].counters['+1/+1'] for c in creatures] == [4, 2, 2]
    assert all(goaders(s, c) == {'p1'} for c in creatures)
    roundtrip(s)


def test_replacements_that_reduce_counters_to_zero_do_not_goad_the_selected_creature(cards):
    s, _, creatures = setup(cards, opponents=['Vorinclex, Monstrous Raider'])
    for p in ['p2', 'p3']:
        put(s, 'Vorinclex, Monstrous Raider', 'battlefield', p)
    trigger(s)
    choose(s, creatures[0])
    choose(s)
    choose(s)
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            break
        assert d.resume['step'] != 'counter_offer'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
    assert not s.state.cards[creatures[0].id].counters and not goaders(s, creatures[0])
    roundtrip(s)


def test_source_departure_does_not_stop_pending_counter_offer_or_goad(cards):
    s, ant, creatures = setup(cards)
    trigger(s)
    act(s, 'p1', type='move', card_ids=[ant.id], to={'zone': 'graveyard'})
    for creature in creatures:
        choose(s, creature)
    assert all(s.state.cards[c.id].counters['+1/+1'] == 2 and goaders(s, c) == {'p1'} for c in creatures)
    roundtrip(s)


def test_blinked_chosen_creature_is_not_the_original_counter_recipient(cards):
    s, _, creatures = setup(cards)
    trigger(s)
    choose(s, creatures[0])
    act(s, 'p1', type='move', card_ids=[creatures[0].id], to={'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[creatures[0].id], to={'zone': 'battlefield'})
    choose(s, creatures[1])
    choose(s, creatures[2])
    assert not s.state.cards[creatures[0].id].counters and not goaders(s, creatures[0])
    assert all(s.state.cards[c.id].counters['+1/+1'] == 2 and goaders(s, c) == {'p1'} for c in creatures[1:])
    roundtrip(s)


def test_goad_expires_at_controllers_next_turn_and_next_trigger_offers_again(cards):
    s, _, creatures = setup(cards)
    trigger(s)
    for creature in creatures:
        choose(s, creature)
    to_phase(s, 'main1', turn=2)
    assert all(goaders(s, c) == {'p1'} for c in creatures)
    act(s, 'p2', type='tap', card_ids=[creatures[1].id], tapped=True)
    to_phase(s, 'main1', turn=3)
    act(s, 'p3', type='tap', card_ids=[creatures[2].id], tapped=True)
    to_phase(s, 'main1', turn=4)
    assert all(not goaders(s, c) for c in creatures)
    trigger(s)
    choose(s)
    choose(s, creatures[1])
    choose(s)
    assert s.state.cards[creatures[1].id].counters['+1/+1'] == 4
    assert goaders(s, creatures[1]) == {'p1'}
    assert not goaders(s, creatures[0]) and not goaders(s, creatures[2])
    roundtrip(s)


@pytest.mark.parametrize('stage', ['offer', 'replacement'])
def test_offer_and_counter_replacement_continue_in_a_fresh_process(cards, tmp_path, stage):
    import subprocess
    import sys

    s, _, creatures = setup(cards, extras=['Doubling Season', 'Hardened Scales'] if stage == 'replacement' else ())
    if stage == 'replacement':
        put(s, 'Doubling Season', 'battlefield')
        put(s, 'Hardened Scales', 'battlefield')
    trigger(s)
    choose(s, creatures[0])
    if stage == 'replacement':
        choose(s)
        choose(s)
        assert s.state.rules.decision.resume['step'] != 'counter_offer'
    else:
        assert s.state.rules.decision.resume['step'] == 'counter_offer'
    roundtrip(s)
    saved = tmp_path / 'ant.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
path, database, creature, stage = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
for _ in range(20):
    d = s.state.rules.decision
    if d is not None:
        ids = [] if d.resume['step'] == 'counter_offer' else [d.options[0].id]
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ids})
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
assert s.state.rules.decision is None
n = s.state.cards[creature].counters['+1/+1']
assert n in (5, 6) if stage == 'replacement' else n == 2
assert 'goaded:p1' in Plan(s.state, 'p1', repo, None).ch(s.state.cards[creature]).imposed
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), creatures[0].id, stage],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_control_changed_ant_triggers_on_new_controllers_turn_in_rotated_order(cards):
    s, ant, creatures = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[ant.id], player='p2')
    to_phase(s, 'main1', turn=2)
    trigger(s)
    for player, creature in [('p2', creatures[1]), ('p3', creatures[2]), ('p1', creatures[0])]:
        assert s.state.rules.decision.player == player
        choose(s, creature)
    assert all(goaders(s, c) == {'p2'} for c in creatures)
    roundtrip(s)
