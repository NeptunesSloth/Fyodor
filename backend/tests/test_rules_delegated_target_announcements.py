"""Canonical Nova announcements delegate target choice before native activation costs."""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.rules_state import cancelable
from app.rules import delegated_target_announcements as delegate
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_prevention_outcomes import activate, cast, choose, game, source_choice


def begin(s, source, *, targets=(), add_mana=True):
    if add_mana:
        mana(s, C=3)
    wait_priority(s, 'p1')
    plan = Plan(s.state, 'p1', s.cards, None)
    ability = next(a for a in plan.ch(plan.state.cards[source.id]).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
        targets=list(targets), sources=[] if add_mana else None)
    return s



def test_opponent_chooses_another_players_creature_before_native_costs_and_stack(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Centaur Courser', 'battlefield')
    source = put(s, 'Pestilence', 'battlefield', 'p2')
    s = begin(s, nova)
    d = s.state.rules.decision
    assert d.player == 'p1' and d.resume['step'] == delegate.OPPONENT
    assert not s.state.cards[nova.id].tapped and not s.state.zones.get('stack')
    assert cancelable(d)
    roundtrip(s)
    choose(s, ['p2'])
    d = s.state.rules.decision
    assert d.player == 'p2' and d.resume['step'] == delegate.CREATURE
    assert victim.id in {o.id for o in d.options}  # need not belong to choosing opponent
    assert not cancelable(d)
    assert s.view('p2')['rules']['decision'].get('options')
    assert not s.view('p1')['rules']['decision'].get('options')
    assert not s.view('p3')['rules']['decision'].get('options')
    assert not s.state.cards[nova.id].tapped and not s.state.zones.get('stack')
    roundtrip(s)
    # Answer without auto-resolving: the selected target is now public on stack.
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[victim.id])
    assert s.state.cards[nova.id].tapped
    entry = s.state.rules.stack[s.state.zones['stack'][-1]]
    assert entry.controller == 'p1' and entry.targets[0].id == victim.id
    assert entry.targets[0].object_id == Plan(s.state, 'p1', cards, None).oid(victim.id)
    settle(s)
    assert s.state.rules.decision.player == 'p1'  # only source choice occurs on resolution
    source_choice(s, source)
    roundtrip(s)
    activate(s, source, 'each creature', pid='p2')
    assert s.state.players['p1'].life == 40
    assert s.state.cards[victim.id].damage == 2
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')  # different source is unaffected
    assert s.state.players['p1'].life == 37


def test_original_activator_can_cancel_before_delegation_without_costs(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    s = begin(s, nova)
    roundtrip(s)
    choose(s, ['cancel'])
    assert s.state.rules.decision is None
    assert not s.state.cards[nova.id].tapped and not s.state.zones.get('stack')
    assert s.state.rules.priority == 'p1'


def test_opponent_cannot_cancel_pay_or_choose_for_a_different_opponent(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    s = begin(s, nova)
    choose(s, ['p2'])
    d = s.state.rules.decision
    for actor, answer in [('p2', 'cancel'), ('p1', victim.id), ('p3', victim.id)]:
        with pytest.raises(ActionError):
            act(s, actor, type='choose', decision_id=d.id, option_ids=[answer])
    assert not s.state.cards[nova.id].tapped and not s.state.zones.get('stack')
    roundtrip(s)
    choose(s, [victim.id])
    assert s.state.rules.decision.player == 'p1'  # resolving source-choice still belongs to activator


def test_no_legal_creature_or_activator_supplied_target_is_rejected_before_costs(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    with pytest.raises(ActionError, match='no legal target'):
        begin(s, nova)
    victim = put(s, 'Grizzly Bears', 'battlefield')
    with pytest.raises(ActionError, match='chosen opponent'):
        begin(s, nova, targets=[victim.id])
    assert not s.state.cards[nova.id].tapped and not s.state.zones.get('stack')


def test_source_departure_returns_cancellation_only_to_original_activator(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    s = begin(s, nova)
    choose(s, ['p2'])
    act(s, 'p1', type='move', card_ids=[nova.id], to={'player':'p1', 'zone':'hand'})
    roundtrip(s)
    choose(s, [victim.id])
    d = s.state.rules.decision
    assert d.player == 'p1' and d.resume['invalid']
    assert not d.options and cancelable(d)
    choose(s, ['cancel'])
    assert s.state.rules.priority == 'p1' and not s.state.zones.get('stack')


def test_legality_uses_original_ability_controller_not_opponent_choosing_target(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    own_hexproof = put(s, 'Slippery Bogle', 'battlefield')
    enemy_hexproof = put(s, 'Slippery Bogle', 'battlefield', 'p2')
    s = begin(s, nova)
    choose(s, ['p2'])
    assert own_hexproof.id in {o.id for o in s.state.rules.decision.options}
    assert enemy_hexproof.id not in {o.id for o in s.state.rules.decision.options}
    roundtrip(s)

def test_target_departure_during_announcement_returns_only_original_payer_cancellation(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    s = begin(s, nova)
    choose(s, ['p2'])
    act(s, 'p1', type='move', card_ids=[victim.id], to={'player':'p1','zone':'hand'})
    choose(s, [victim.id])
    d = s.state.rules.decision
    assert d.player == 'p1' and d.resume['invalid']
    assert not s.state.cards[nova.id].tapped
    choose(s, ['cancel'])


def test_original_activation_legality_is_checked_again_before_any_costs(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    s = begin(s, nova)
    choose(s, ['p2'])
    act(s, 'p1', type='tap', card_ids=[nova.id], tapped=True)
    choose(s, [victim.id])
    d = s.state.rules.decision
    assert d.player == 'p1' and d.resume['invalid']
    assert not s.state.zones.get('stack')
    choose(s, ['cancel'])


def test_unpayable_announcement_is_returned_to_original_payer_for_cancellation(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    s = begin(s, nova, add_mana=False)
    choose(s, ['p2'])
    choose(s, [victim.id])
    d = s.state.rules.decision
    assert d.player == 'p1' and d.resume['invalid']
    assert not s.state.cards[nova.id].tapped and not s.state.zones.get('stack')
    choose(s, ['cancel'])


@pytest.mark.parametrize('returned', [False, True])
def test_resolved_target_is_bound_once_and_later_hexproof_or_new_incarnation_is_handled(cards, returned):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Centaur Courser' if returned else 'Slippery Bogle', 'battlefield')
    source = put(s, 'Pestilence', 'battlefield', 'p2')
    s = begin(s, nova)
    choose(s, ['p2'])
    choose(s, [victim.id])
    source_choice(s, source)
    if returned:
        cast(s, 'Cloudshift', [victim.id])
    else:
        act(s, 'p1', type='set_controller', card_ids=[victim.id], player='p2')
    roundtrip(s)
    activate(s, source, 'each creature', pid='p2')
    assert s.state.players['p1'].life == (39 if returned else 40)
    if returned:
        assert s.state.cards[victim.id].damage == 1
    else:
        assert s.state.cards[victim.id].zone == 'p1:graveyard'  # hexproof does not recheck targeting
    roundtrip(s)

def test_delegated_target_can_leave_during_native_mana_payment_and_keeps_original_ref(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    altar = put(s, "Ashnod's Altar", 'battlefield')
    act(s, 'p1', type='set_prefs', payment='self')
    mana(s, C=1)
    s = begin(s, nova, add_mana=False)
    choose(s, ['p2'])
    choose(s, [victim.id])
    assert s.state.rules.decision.player == 'p1'
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    old_oid = Plan(s.state, 'p1', cards, None).oid(victim.id)
    roundtrip(s)
    act(s, 'p1', type='activate_ability', card_id=altar.id, ability=0,
        cost_choices=[{'component':0, 'cards':[victim.id]}])
    assert s.state.rules.decision is None
    assert s.state.cards[victim.id].zone == 'p1:graveyard'
    entry = s.state.rules.stack[s.state.zones['stack'][-1]]
    assert entry.controller == 'p1' and entry.targets[0].object_id == old_oid
    roundtrip(s)
    settle(s)
    assert s.state.rules.decision is None and not s.state.rules.replacements

def test_original_source_reserved_for_tap_cost_cannot_be_sacrificed_for_native_mana(cards):
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    iron = put(s, 'Krark-Clan Ironworks', 'battlefield')
    act(s, 'p1', type='set_prefs', payment='self')
    mana(s, C=1)
    s = begin(s, nova, add_mana=False)
    choose(s, ['p2'])
    choose(s, [victim.id])
    assert s.state.rules.decision.resume['step'] == 'pay_mana'
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=iron.id, ability=0,
            cost_choices=[{'component':0,'cards':[nova.id]}])
    assert s.state.cards[nova.id].zone == 'p1:battlefield'
    assert not s.state.cards[nova.id].tapped and not s.state.zones.get('stack')
    roundtrip(s)

@pytest.mark.parametrize('pause', ['opponent', 'creature'])
def test_delegated_announcement_resumes_in_genuinely_cold_process(cards, tmp_path, pause):
    import subprocess
    import sys
    from pathlib import Path
    s = game(cards)
    nova = put(s, 'Nova Pentacle', 'battlefield')
    victim = put(s, 'Centaur Courser', 'battlefield')
    source = put(s, 'Pestilence', 'battlefield', 'p2')
    s = begin(s, nova)
    if pause == 'creature':
        choose(s, ['p2'])
    save = tmp_path / 'delegated.json'
    save.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
from tests.test_rules_damage_redirection import activate
save,db,victim,source=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
def answer(option):
 d=s.state.rules.decision
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[option])
 settle(s)
if s.state.rules.decision.resume['step']=='delegated_target_opponent':answer('p2')
assert s.state.rules.decision.player=='p2'
answer(victim)
assert s.state.rules.decision.player=='p1'
answer(next(o.id for o in s.state.rules.decision.options if o.card_id==source))
activate(s,s.state.cards[source],'each creature',pid='p2')
assert s.state.players['p1'].life==40 and s.state.cards[victim].damage==2
roundtrip(s)
repo.close()
"""
    result = subprocess.run([sys.executable,'-c',code,str(save),str(cards.db_path),victim.id,source.id],
                            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=60)
    assert result.returncode == 0, result.stderr


def test_canonical_nova_pentacle_is_whole_card_full(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('Nova Pentacle')).level == 'FULL'
