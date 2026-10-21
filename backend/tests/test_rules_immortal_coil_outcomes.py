"""Whole-Coil native proofs, including mandatory loop responses."""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_prevention_outcomes import activate, cast, choose, game


@pytest.fixture()
def enabled(cards):
    return cards


def settle(s):
    for _ in range(80):
        if s.state.rules.draw_reason or s.state.rules.lost:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == 'order':
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
        elif d is None and s.state.zones.get('stack'):
            act(s, s.state.rules.priority, type='pass_priority')
        else:
            return
    raise AssertionError('Coil stack did not settle')


def enter_empty_coil(s):
    source = cast(s, 'Immortal Coil', resolve=False)
    for _ in range(12):
        if s.state.cards[source.id].zone == 'p1:battlefield':
            return s.state.cards[source.id]
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('Coil failed to enter')


def graveyard(s, names=('Forest', 'Grizzly Bears', 'Sacred Boon', 'Comeuppance', 'Hallow')):
    return [put(s, name, 'graveyard') for name in names]


def test_prevents_all_damage_and_chooses_actual_graveyard_exiles_cold(enabled):
    s = game(enabled)
    gy = graveyard(s)
    enter_empty_coil(s)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    settle(s)
    assert s.state.players['p1'].life == 40
    d = s.state.rules.decision
    assert d.player == 'p1' and d.min_choices == d.max_choices == 3
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in gy)
    roundtrip(s)
    choose(s, [gy[i].id for i in (0, 2, 4)])
    assert all(s.state.cards[gy[i].id].zone == 'p1:exile' for i in (0, 2, 4))
    assert all(s.state.cards[gy[i].id].zone == 'p1:graveyard' for i in (1, 3))
    roundtrip(s)


def test_exile_two_is_paid_before_draw_ability_can_be_responded_to(enabled):
    s = game(enabled)
    gy = graveyard(s, ('Forest', 'Grizzly Bears', 'Sacred Boon'))
    source = enter_empty_coil(s)
    activate(s, source, 'Draw a card', resolve=False)
    d = s.state.rules.decision
    assert d.player == 'p1' and d.resume['step'] == 'ability_cost'
    assert not s.state.cards[source.id].tapped and not s.state.zones.get('stack')
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[gy[0].id, gy[2].id])
    assert s.state.cards[source.id].tapped
    assert s.state.cards[gy[0].id].zone == s.state.cards[gy[2].id].zone == 'p1:exile'
    assert s.state.zones['stack']
    before = len(s.state.zones.get('p1:hand', []))
    settle(s)
    assert len(s.state.zones.get('p1:hand', [])) == before + 1
    roundtrip(s)


def test_cannot_activate_exile_two_with_only_one_card(enabled):
    s = game(enabled)
    graveyard(s, ('Forest',))
    source = enter_empty_coil(s)
    with pytest.raises(ActionError):
        activate(s, source, 'Draw a card')
    assert not s.state.cards[source.id].tapped


def test_state_trigger_is_genuine_and_countered_empty_graveyard_retriggers(enabled):
    s = game(enabled)
    enter_empty_coil(s)
    original = s.state.zones['stack'][-1]
    assert s.state.rules.stack[original].effects[0]['do'] == 'state_trigger'
    cast(s, 'Stifle', [original], pid='p2', resolve=False)
    for _ in range(12):
        if original not in s.state.zones.get('stack', []):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert original not in s.state.zones.get('stack', [])
    assert s.state.zones['stack'] and 'p1' not in s.state.rules.lost
    assert s.state.rules.stack[s.state.zones['stack'][-1]].effects[0]['do'] == 'state_trigger'
    roundtrip(s)


def test_later_nonempty_graveyard_does_not_save_already_triggered_loss(enabled):
    s = game(enabled)
    enter_empty_coil(s)
    graveyard(s, ('Forest',))
    settle(s)
    assert 'p1' in s.state.rules.lost and s.state.rules.draw_reason is None
    roundtrip(s)


def test_blocked_loss_and_empty_graveyard_draws_only_after_native_response_round(enabled):
    s = game(enabled)
    put(s, 'Platinum Angel', 'battlefield')
    enter_empty_coil(s)
    assert s.state.zones['stack'] and s.state.rules.priority is not None
    assert s.state.rules.draw_reason is None
    roundtrip(s)
    settle(s)
    assert s.state.rules.draw_reason == 'Mandatory state-trigger loop (104.4b, 732.4)'
    assert s.state.rules.priority is None and not s.state.rules.lost
    roundtrip(s)


def test_native_response_removing_angel_breaks_loop_and_original_loss_resolves(enabled):
    s = game(enabled)
    angel = put(s, 'Platinum Angel', 'battlefield')
    enter_empty_coil(s)
    cast(s, 'Murder', [angel.id], pid='p2', resolve=False)
    settle(s)
    assert 'p1' in s.state.rules.lost and s.state.rules.draw_reason is None
    roundtrip(s)


def test_native_response_giving_graveyard_card_breaks_blocked_loss_loop(enabled):
    s = game(enabled)
    put(s, 'Platinum Angel', 'battlefield')
    enter_empty_coil(s)
    # This real instant is cast in response and goes to its controller's GY.
    cast(s, 'Giant Growth', [next(c.id for c in s.state.cards.values() if c.name == 'Platinum Angel' and c.zone == 'p1:battlefield')], resolve=False)
    settle(s)
    assert not s.state.rules.lost and s.state.rules.draw_reason is None
    assert not s.state.zones.get('stack') and s.state.zones.get('p1:graveyard')
    roundtrip(s)


def test_departed_source_does_not_turn_blocked_original_loss_into_a_loop(enabled):
    s = game(enabled)
    put(s, 'Platinum Angel', 'battlefield')
    source = enter_empty_coil(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    settle(s)
    assert not s.state.rules.lost and s.state.rules.draw_reason is None
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_prevents_more_damage_than_available_cards_and_exiles_only_available(enabled):
    s = game(enabled)
    gy = graveyard(s, ('Forest',))
    put(s, 'Platinum Angel', 'battlefield')
    enter_empty_coil(s)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    settle(s)
    assert s.state.players['p1'].life == 40
    assert s.state.cards[gy[0].id].zone == 'p1:exile'
    assert not s.state.zones.get('p1:graveyard')
    assert s.state.rules.draw_reason == 'Mandatory state-trigger loop (104.4b, 732.4)'
    roundtrip(s)


def test_unpreventable_damage_exiles_no_cards(enabled):
    s = game(enabled)
    gy = graveyard(s)
    enter_empty_coil(s)
    cast(s, 'Skullcrack', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 37
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in gy)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    settle(s)
    assert s.state.players['p1'].life == 34
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in gy)
    roundtrip(s)


def test_copied_state_trigger_above_murder_above_original_does_not_prematurely_draw(enabled):
    s = game(enabled)
    angel = put(s, 'Platinum Angel', 'battlefield')
    copier = put(s, 'Lithoform Engine', 'battlefield')
    enter_empty_coil(s)
    original = s.state.zones['stack'][-1]
    cast(s, 'Murder', [angel.id], pid='p2', resolve=False)
    activate(s, copier, 'Copy target activated', [original], resolve=False)
    roundtrip(s)
    settle(s)
    assert 'p1' in s.state.rules.lost
    assert s.state.rules.draw_reason is None
    roundtrip(s)


@pytest.mark.parametrize('angel', [False, True])
def test_original_loss_survives_source_leaving_and_returning_new_incarnation(enabled, angel):
    s = game(enabled)
    if angel:
        put(s, 'Platinum Angel', 'battlefield')
    source = enter_empty_coil(s)
    original = s.state.zones['stack'][-1]
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    # Filling GY avoids a distinct new-incarnation state trigger. The original
    # instruction remains mandatory and cannot use the new source to prove a loop.
    graveyard(s, ('Forest',))
    assert original in s.state.zones['stack']
    roundtrip(s)
    settle(s)
    assert ('p1' in s.state.rules.lost) is not angel
    assert s.state.rules.draw_reason is None


@pytest.mark.parametrize('pause', ['state', 'exile', 'cost'])
def test_native_coil_continuations_resume_in_fresh_process(enabled, tmp_path, pause):
    import subprocess
    import sys
    from pathlib import Path

    s = game(enabled)
    if pause == 'state':
        put(s, 'Platinum Angel', 'battlefield')
        enter_empty_coil(s)
    else:
        gy = graveyard(s)
        source = enter_empty_coil(s)
        if pause == 'cost':
            activate(s, source, 'Draw a card', resolve=False)
        else:
            cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
            settle(s)
        assert s.state.rules.decision is not None
        assert gy
    save = tmp_path / 'coil.json'
    save.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
def settle(s):
 for _ in range(80):
  if s.state.rules.draw_reason or s.state.rules.lost:return
  d=s.state.rules.decision
  if d is not None and d.kind=='order':
   act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
  elif d is None and s.state.zones.get('stack'):
   act(s,s.state.rules.priority,type='pass_priority')
  else:return
 raise AssertionError('Unsettled native Coil stack')
save,db,pause=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
if pause!='state':
 d=s.state.rules.decision
 ids=(list(s.state.zones['p1:graveyard'])[:2] if pause=='cost' else [o.id for o in d.options[:d.min_choices]])
 assert len(ids)==(2 if pause=='cost' else 3)
 act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
settle(s)
if pause=='state':
 assert s.state.rules.draw_reason=='Mandatory state-trigger loop (104.4b, 732.4)'
else:
 assert s.state.rules.draw_reason is None
 assert len(s.state.zones['p1:exile'])==(2 if pause=='cost' else 3)
 assert s.state.players['p1'].life==40
 assert not s.state.zones.get('stack')
repo.close()
"""
    result = subprocess.run([sys.executable, '-c', code, str(save), str(enabled.db_path), pause],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr



def test_changed_source_controller_does_not_prove_original_blocked_loss_loop(enabled):
    s = game(enabled)
    put(s, 'Platinum Angel', 'battlefield')
    put(s, 'Forest', 'graveyard', 'p2')
    source = enter_empty_coil(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    roundtrip(s)
    settle(s)
    assert not s.state.rules.lost and s.state.rules.draw_reason is None
    assert not s.state.zones.get('stack')


def test_native_ability_removal_breaks_mandatory_loop_proof(enabled):
    s = game(enabled)
    put(s, 'Vedalken Orrery', 'battlefield', 'p2')
    put(s, 'Platinum Angel', 'battlefield')
    source = enter_empty_coil(s)
    cast(s, 'Song of the Dryads', [source.id], pid='p2', resolve=False)
    roundtrip(s)
    settle(s)
    assert not s.state.rules.lost and s.state.rules.draw_reason is None
    assert not s.state.zones.get('stack')


def test_canonical_immortal_coil_all_printed_lines_are_full(cards):
    from app.rules import coverage
    result = coverage.of_card_data(cards.resolve('Immortal Coil'))
    assert result.level == 'FULL', result.manual_parts


def test_native_damage_response_is_fully_prevented_with_zero_graveyard_cards(cards):
    s = game(cards)
    put(s, 'Platinum Angel', 'battlefield')
    enter_empty_coil(s)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    roundtrip(s)
    settle(s)
    assert s.state.players['p1'].life == 40
    assert not s.state.zones.get('p1:graveyard') and not s.state.zones.get('p1:exile')
    assert s.state.rules.decision is None
    assert s.state.rules.draw_reason == 'Mandatory state-trigger loop (104.4b, 732.4)'
