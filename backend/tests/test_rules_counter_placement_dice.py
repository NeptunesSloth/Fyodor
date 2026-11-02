"""Real Hinder counter replacement and Power of Persuasion native dice rows."""
from __future__ import annotations

import json
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_wave12a_counters_keywords import rolls
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_placement_dice_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='cpd', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    from tests.test_rules_shared_damage_choices import table

    return table(cards, ['Hinder', 'Power of Persuasion', 'Memory Lapse', 'Spell Crumple', 'Dissipate', 'Commandeer', 'Pixie Guide', 'Barbarian Class', 'Grizzly Bears', 'Act of Treason'],
                 ['Lightning Bolt', 'Grizzly Bears', 'Carnage Tyrant', 'Think Twice', 'Counterspell'], ['Commandeer', 'Reanimate'])


def cast_hinder(s, target):
    wait_priority(s, 'p1')
    hinder = put(s, 'Hinder', 'hand')
    mana(s, U=2, C=1)
    act(s, 'p1', type='cast_spell', card_id=hinder.id, targets=[target.id])
    return hinder


def bolt_on_stack(s):
    bolt = put(s, 'Lightning Bolt', 'hand', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=['p3'])
    return bolt


def answer(s, player, choice):
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == player
    roundtrip(s)
    act(s, player, type='choose', decision_id=d.id, option_ids=[choice])
    settle(s)


@pytest.mark.parametrize('name', ['Hinder', 'Power of Persuasion'])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('place', ['top', 'bottom'])
def test_hinder_caster_selects_counter_destination_once(cards, place):
    s = setup(cards)
    bolt = bolt_on_stack(s)
    cast_hinder(s, bolt)
    settle(s)
    assert s.state.cards[bolt.id].zone == 'stack'
    assert not any(e.kind == 'designation' and e.counter == 'counters_spell' for e in s.state.rules.events)
    answer(s, 'p1', place)
    assert s.state.zones['p2:library'][0 if place == 'top' else -1] == bolt.id
    events = [e for e in s.state.rules.events if e.kind == 'designation' and e.counter == 'counters_spell']
    assert len(events) == 1 and events[0].player == 'p1'
    assert s.state.players['p3'].life == 40
    roundtrip(s)


def test_hinder_does_not_tuck_uncounterable_creature_or_offer_false_choice(cards):
    s = setup(cards)
    tyrant = put(s, 'Carnage Tyrant', 'hand', pid='p2')
    to_phase(s, 'main1', turn=2)
    mana(s, pid='p2', G=2, C=4)
    act(s, 'p2', type='cast_spell', card_id=tyrant.id, targets=[])
    cast_hinder(s, tyrant)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[tyrant.id].zone == 'p2:battlefield'
    assert not any(e.kind == 'designation' and e.counter == 'counters_spell' for e in s.state.rules.events)
    roundtrip(s)


@pytest.mark.parametrize('place', ['top', 'bottom'])
def test_hinder_flashback_is_exiled_instead_of_selected_library_destination(cards, place):
    s = setup(cards)
    think = put(s, 'Think Twice', 'graveyard', pid='p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', U=1, C=2)
    act(s, 'p2', type='cast_spell', card_id=think.id, targets=[])
    cast_hinder(s, think)
    answer(s, 'p1', place)
    assert s.state.cards[think.id].zone == 'p2:exile'
    roundtrip(s)


def cast_power(s, target):
    power = put(s, 'Power of Persuasion', 'hand')
    mana(s, U=1, C=2)
    act(s, 'p1', type='cast_spell', card_id=power.id, targets=[target.id])
    return power


@pytest.mark.parametrize('result', [1, 9, 10, 19, 20])
def test_power_rolls_after_cast_target_and_applies_exact_native_row(cards, monkeypatch, result):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    rolls(monkeypatch, result)
    cast_power(s, bear)
    assert not any(e.kind == 'designation' and e.counter == 'roll_die' for e in s.state.rules.events)
    settle(s)
    if result in [10, 19]:
        d = s.state.rules.decision
        assert d and d.player == 'p2'
        answer(s, 'p2', 'bottom')
        assert s.state.zones['p2:library'][-1] == bear.id
    elif result < 10:
        assert s.state.cards[bear.id].zone == 'p2:hand'
    else:
        assert s.state.cards[bear.id].zone.endswith(':battlefield') and s.state.cards[bear.id].controller == 'p1'
    events = [e for e in s.state.rules.events if e.kind == 'designation' and e.counter == 'roll_die']
    assert len(events) == 1 and events[0].amount == result
    roundtrip(s)


def test_power_only_targets_an_opponents_creature(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    power = put(s, 'Power of Persuasion', 'hand')
    mana(s, U=1, C=2)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=power.id, targets=[bear.id])
    assert s.state.cards[power.id].zone == 'p1:hand'
    roundtrip(s)


def test_actual_commandeer_changes_hinder_chooser_to_resolving_controller(cards):
    from tests.test_rules_narset_rebound import steal_bolt

    s = setup(cards)
    bolt = bolt_on_stack(s)
    hinder = cast_hinder(s, bolt)
    act(s, 'p3', type='set_prefs', hold_priority=True)
    steal_bolt(s, hinder, player='p3', target='keep')
    answer(s, 'p3', 'bottom')
    assert s.state.zones['p2:library'][-1] == bolt.id
    events = [e for e in s.state.rules.events if e.kind == 'designation' and e.counter == 'counters_spell']
    assert len(events) == 1 and events[0].player == 'p3'
    roundtrip(s)


def test_countering_hinder_does_not_counter_its_original_target(cards):
    s = setup(cards)
    bolt = bolt_on_stack(s)
    hinder = cast_hinder(s, bolt)
    wait_priority(s, 'p2')
    counter = put(s, 'Counterspell', 'hand', pid='p2')
    mana(s, pid='p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[hinder.id])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[hinder.id].zone == 'p1:graveyard'
    assert s.state.cards[bolt.id].zone == 'p2:graveyard'
    assert s.state.players['p3'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('command', [True, False])
@pytest.mark.parametrize('place', ['top', 'bottom'])
def test_hinder_commander_replacement_precedes_single_committed_counter(cards, command, place):
    s = setup(cards)
    atraxa = put(s, "Atraxa, Praetors' Voice", 'hand', pid='p2')
    to_phase(s, 'main1', turn=2)
    mana(s, pid='p2', W=1, U=1, B=1, G=1)
    act(s, 'p2', type='cast_spell', card_id=atraxa.id, targets=[])
    cast_hinder(s, atraxa)
    answer(s, 'p1', place)
    assert s.state.cards[atraxa.id].zone == 'stack'
    assert s.state.rules.decision and s.state.rules.decision.resume['step'] == 'commander_first'
    assert not any(e.kind == 'designation' and e.counter == 'counters_spell' for e in s.state.rules.events)
    answer(s, 'p2', 'yes' if command else 'no')
    assert s.state.cards[atraxa.id].zone == ('p2:command' if command else 'p2:library')
    events = [e for e in s.state.rules.events if e.kind == 'designation' and e.counter == 'counters_spell']
    assert len(events) == 1
    if not command:
        assert s.state.zones['p2:library'][0 if place == 'top' else -1] == atraxa.id
    roundtrip(s)


def test_hinder_pending_choice_does_not_counter_a_new_incarnation(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'hand', pid='p2')
    to_phase(s, 'main1', turn=2)
    mana(s, pid='p2', G=1, C=1)
    act(s, 'p2', type='cast_spell', card_id=bear.id, targets=[])
    cast_hinder(s, bear)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume['step'] == 'counter_destination'
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'hand'})
    act(s, 'p2', type='move', card_ids=[bear.id], to={'zone': 'stack'})
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['top'])
    assert s.state.cards[bear.id].zone != 'p2:library'
    assert not any(e.kind == 'designation' and e.counter == 'counters_spell' for e in s.state.rules.events)
    roundtrip(s)


@pytest.mark.parametrize('extra_source', ['Pixie Guide', 'Barbarian Class'])
def test_power_uses_kept_roll_and_ignores_the_lowest(cards, monkeypatch, extra_source):
    s = setup(cards)
    put(s, extra_source, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    rolls(monkeypatch, 2, 19)
    cast_power(s, bear)
    answer(s, 'p2', 'top')
    assert s.state.zones['p2:library'][0] == bear.id
    events = [e for e in s.state.rules.events if e.kind == 'designation' and e.counter == 'roll_die']
    assert [e.amount for e in events] == [19]
    # the roll's log line (and the dice on the table) say which roll was ignored and why, and count only the kept one (706.6)
    entry = next(e for e in reversed(s.state.log) if e.roll is not None)
    assert entry.roll.results == [2, 19] and entry.roll.ignored == [0]
    assert "".join(p.t or "" for p in entry.parts).endswith(f"rolled a d20 and one extra die ({extra_source}): 19; ignored 2")
    assert not any("ignores the lowest" in "".join(p.t or "" for p in e.parts) for e in s.state.log)  # (said once, on the roll)
    roundtrip(s)


def test_a_players_own_table_roll_ignores_nothing(cards):
    """Only the rules engine ignores rolls: a roll a player makes at the table is shown as rolled (resolve drops the fields)."""
    s = setup(cards)
    act(s, 'p1', type='roll', sides=20, count=2, ignore_lowest=1, because='Barbarian Class')
    entry = next(e for e in reversed(s.state.log) if e.roll is not None)
    assert entry.roll.ignored == [] and "extra die" not in "".join(p.t or "" for p in entry.parts)
    roundtrip(s)


def test_power_lost_target_does_not_roll(cards, monkeypatch):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    rolls(monkeypatch)  # any accidental roll fails rather than returning a fabricated result
    cast_power(s, bear)
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'exile'})
    settle(s)
    assert not any(e.kind == 'designation' and e.counter == 'roll_die' for e in s.state.rules.events)
    roundtrip(s)


def test_power_control_lasts_through_cleanup_of_casters_next_turn_and_restores_prior_controller(cards, monkeypatch):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    reanimate = put(s, 'Reanimate', 'hand', pid='p3')
    to_phase(s, 'main1', turn=3)
    mana(s, pid='p3', B=1)
    act(s, 'p3', type='cast_spell', card_id=reanimate.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].controller == 'p3' and s.state.cards[bear.id].owner == 'p2'
    to_phase(s, 'main1', turn=4)
    rolls(monkeypatch, 20)
    cast_power(s, bear)
    settle(s)
    assert s.state.cards[bear.id].controller == 'p1'
    to_phase(s, 'main1', turn=5)
    assert s.state.cards[bear.id].controller == 'p1'
    to_phase(s, 'main1', turn=7)
    assert s.state.cards[bear.id].controller == 'p1'
    roundtrip(s)
    to_phase(s, 'main1', turn=8)
    assert s.state.cards[bear.id].controller == 'p3'
    roundtrip(s)


def test_power_middle_row_asks_owner_of_creature_reanimated_by_another_player(cards, monkeypatch):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'graveyard', pid='p2')
    spell = put(s, 'Reanimate', 'hand', pid='p3')
    to_phase(s, 'main1', turn=3)
    mana(s, pid='p3', B=1)
    act(s, 'p3', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    to_phase(s, 'main1', turn=4)
    rolls(monkeypatch, 10)
    cast_power(s, bear)
    answer(s, 'p2', 'top')
    assert s.state.zones['p2:library'][0] == bear.id
    roundtrip(s)


def test_power_control_effect_does_not_follow_blinked_creature(cards, monkeypatch):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    rolls(monkeypatch, 20)
    cast_power(s, bear)
    settle(s)
    assert s.state.cards[bear.id].controller == 'p1'
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'exile'})
    act(s, 'p2', type='move', card_ids=[bear.id], to={'player': 'p2', 'zone': 'battlefield'})
    assert s.state.cards[bear.id].controller == 'p2'
    to_phase(s, 'main1', turn=5)
    assert s.state.cards[bear.id].controller == 'p2'
    roundtrip(s)


@pytest.mark.parametrize('stage', ['hinder', 'commander', 'power'])
def test_saved_counter_and_dice_choices_resume_cold_without_repeating_events(cards, monkeypatch, tmp_path, stage):
    import subprocess
    import sys

    s = setup(cards)
    if stage == 'commander':
        target = put(s, "Atraxa, Praetors' Voice", 'hand', pid='p2')
        to_phase(s, 'main1', turn=2)
        mana(s, pid='p2', W=1, U=1, B=1, G=1)
        act(s, 'p2', type='cast_spell', card_id=target.id, targets=[])
        cast_hinder(s, target)
        answer(s, 'p1', 'bottom')
    elif stage == 'hinder':
        target = bolt_on_stack(s)
        cast_hinder(s, target)
        settle(s)
    else:
        target = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
        rolls(monkeypatch, 19)
        cast_power(s, target)
        settle(s)
    assert s.state.rules.decision
    saved = tmp_path / 'counter-dice.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import engine
from tests.game_helpers import act
repo = CardRepository(Path(sys.argv[2]), ImageStore(Path(sys.argv[2]).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()), cards=repo)
assert 'counter_destination' in engine.RESUME
for _ in range(60):
    d = s.state.rules.decision
    if d:
        step = d.resume['step']
        answer = 'yes' if step == 'commander_first' else 'bottom'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[answer])
    elif s.state.zones.get('stack'):
        act(s, s.state.rules.priority, type='pass_priority')
    else: break
else: raise AssertionError('resolution did not finish')
kind = sys.argv[4]
assert s.state.cards[sys.argv[3]].zone == ('p2:command' if kind == 'commander' else 'p2:library')
events = s.state.rules.events
assert len([e for e in events if e.kind == 'designation' and e.counter == 'counters_spell']) == (0 if kind == 'power' else 1)
assert len([e for e in events if e.kind == 'designation' and e.counter == 'roll_die']) == (1 if kind == 'power' else 0)
assert s.history.state_at(s.history.cursor).model_dump() == s.state.model_dump()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id, stage],
                            cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('change', [('1—9', '1—8'), ('10—19', '9—19'), ('20 |', '21 |')])
def test_targeted_results_table_refuses_gaps_overlaps_and_out_of_range_rows(cards, change):
    from app.rules import targeted_dice_rows

    text = cards.resolve('Power of Persuasion')['oracle_text']
    assert targeted_dice_rows.parse(text.replace(*change)) is None


@pytest.mark.parametrize(('name', 'cost', 'place'), [('Memory Lapse', {'U': 1, 'C': 1}, 'top'), ('Spell Crumple', {'U': 2, 'C': 1}, 'bottom')])
@pytest.mark.parametrize('command', [True, False])
def test_existing_fixed_library_counters_also_preflight_commander_destination(cards, name, cost, place, command):
    s = setup(cards)
    atraxa = put(s, "Atraxa, Praetors' Voice", 'hand', pid='p2')
    to_phase(s, 'main1', turn=2)
    mana(s, pid='p2', W=1, U=1, B=1, G=1)
    act(s, 'p2', type='cast_spell', card_id=atraxa.id, targets=[])
    wait_priority(s, 'p1')
    counter = put(s, name, 'hand')
    mana(s, **cost)
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[atraxa.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2' and d.resume['step'] == 'commander_first'
    assert s.state.cards[atraxa.id].zone == 'stack'
    answer(s, 'p2', 'yes' if command else 'no')
    assert s.state.cards[atraxa.id].zone == ('p2:command' if command else 'p2:library')
    if not command:
        assert s.state.zones['p2:library'][0 if place == 'top' else -1] == atraxa.id
    if name == 'Spell Crumple':
        assert s.state.zones['p1:library'][-1] == counter.id
    events = [e for e in s.state.rules.events if e.kind == 'designation' and e.counter == 'counters_spell']
    assert len(events) == 1
    roundtrip(s)
