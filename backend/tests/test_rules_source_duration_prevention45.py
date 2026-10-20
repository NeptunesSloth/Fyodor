"""Canonical source duration through native Saga progression, damage and phasing."""
from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_conditional_prevention_grants45 import cards as cards
from tests.test_rules_damage_redirection import attack, cast, damage
from tests.test_rules_designations import put, settle
from tests.test_rules_prevention_unpreventable44 import NAMES
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase

NAME = "Old Fat Spider Can't See Me"



def choose_card(s, card):
    d = s.state.rules.decision
    assert d is not None
    option = next(o for o in d.options if o.card_id == card.id or o.id == card.id)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    settle(s)


def saga_setup(cards, *, answer=True):
    ns = [*NAMES, NAME, 'Clever Concealment', 'Copy Enchantment', 'Stifle']
    s = table(cards, ns, ns, ns)
    own = put(s, 'Grizzly Bears', 'battlefield')
    opponent = put(s, 'Centaur Courser', 'battlefield', 'p2')
    saga = cast(s, NAME)
    choose_card(s, own)
    assert 'hexproof' in chars(s, own).keywords
    to_phase(s, 'main1', turn=4)
    if not answer:
        return s, own, opponent, saga
    choose_card(s, opponent)
    records = [r for r in s.state.rules.replacements if r.get('source_card') == saga.id]
    assert len(records) == 1 and records[0]['until'] == 'source_on_battlefield'
    assert records[0]['source'] == s.state.rules.object_id(saga.id)
    assert records[0]['match']['source']['oids'] == [s.state.rules.object_id(opponent.id)]

    return s, own, opponent, saga


def test_saga_actual_all_chapters_draw_and_sacrifice_end_both_source_durations(cards):
    s, own, opponent, saga = saga_setup(cards)
    hand = len(s.state.zones['p1:hand'])
    for turn, expected in ((7, hand + 2), (10, hand + 4)):
        to_phase(s, 'main1', turn=turn)
        settle(s)
        assert len(s.state.zones['p1:hand']) == expected
    assert s.state.cards[saga.id].zone == 'p1:graveyard'
    assert 'hexproof' not in chars(s, own).keywords
    attack(s, [opponent], pid='p2', target='p1', turn=11)
    damage(s)
    assert s.state.players['p1'].life == 37


@pytest.mark.parametrize('change', ['none', 'control', 'departure', 'blink'])
def test_saga_original_source_duration_survives_turns_and_control_but_not_departure_or_blink(cards, change):
    s, own, opponent, saga = saga_setup(cards)
    if change == 'control':
        act(s, 'p1', type='set_controller', card_ids=[saga.id], player='p3')
    elif change in ('departure', 'blink'):
        act(s, 'p1', type='move', card_ids=[saga.id], to={'player': 'p1', 'zone': 'hand'})
        if change == 'blink':
            cast(s, NAME)
            choose_card(s, own)
    attack(s, [opponent], pid='p2', target='p1', turn=5)
    damage(s)
    assert s.state.players['p1'].life == (40 if change in ('none', 'control') else 37)


@pytest.mark.parametrize('case', ['zero', 'illegal', 'source_left'])
def test_saga_second_chapter_native_zero_target_and_resolution_legality(cards, case):
    s, own, opponent, saga = saga_setup(cards, answer=False)
    d = s.state.rules.decision
    option = next(o for o in d.options if o.card_id == opponent.id or o.id == opponent.id)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[] if case == 'zero' else [option.id])
    if case != 'zero':
        target = opponent if case == 'illegal' else saga
        act(s, 'p1', type='move', card_ids=[target.id], to={'player': target.owner, 'zone': 'hand'})
    settle(s)
    assert not any(r.get('source_card') == saga.id for r in s.state.rules.replacements)
    assert s.state.rules.decision is None


@pytest.mark.parametrize('depart', [False, True])
def test_saga_exact_original_source_duration_cold_across_cleanup(cards, tmp_path, depart):
    import subprocess
    import sys
    from pathlib import Path
    s, own, opponent, saga = saga_setup(cards)
    saved = tmp_path / 'saga-source-duration.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_damage_redirection import attack,damage
from tests.test_rules_designations import settle,roundtrip
saved,db,saga,attacker,depart=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
if depart=='True':
 act(s,'p1',type='move',card_ids=[saga],to={'player':'p1','zone':'hand'})
attack(s,[s.state.cards[attacker]],pid='p2',target='p1',turn=5)
damage(s)
assert s.state.players['p1'].life==(37 if depart=='True' else 40)
roundtrip(s)
settle(s)
assert s.state.players['p1'].life==(37 if depart=='True' else 40)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), saga.id, opponent.id, str(depart)],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('subject', ['source', 'target'])
def test_saga_source_phasing_ends_duration_irreversibly_but_target_phasing_preserves_it(cards, subject):
    s, own, opponent, saga = saga_setup(cards)
    source_oid, target_oid = (s.state.rules.object_id(c.id) for c in (saga, opponent))
    selected = saga if subject == 'source' else opponent
    pid = 'p1' if subject == 'source' else 'p2'
    cast(s, 'Clever Concealment', [selected.id], pid=pid, target_counts=[1])
    assert s.state.cards[selected.id].zone == pid + ':phased'
    assert any(r.get('source_card') == saga.id for r in s.state.rules.replacements) == (subject == 'target')
    if subject == 'source':
        assert 'hexproof' not in chars(s, own).keywords
        to_phase(s, 'main1', turn=7)
        turn = 8
    else:
        to_phase(s, 'main1', turn=5)
        turn = 5
    assert s.state.rules.object_id(saga.id) == source_oid
    assert s.state.rules.object_id(opponent.id) == target_oid
    attack(s, [opponent], pid='p2', target='p1', turn=turn)
    damage(s)
    assert s.state.players['p1'].life == (37 if subject == 'source' else 40)


def test_saga_native_copy_owns_independent_source_and_target_duration(cards):
    s, own, opponent, saga = saga_setup(cards)
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    copied = cast(s, 'Copy Enchantment')
    choose_card(s, saga)
    choose_card(s, own)
    assert s.state.rules.object_id(copied.id) != s.state.rules.object_id(saga.id)
    to_phase(s, 'main1', turn=7)
    while s.state.rules.decision is not None and s.state.rules.decision.kind == 'order':
        d = s.state.rules.decision
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[o.id for o in d.options])
        settle(s)
    choose_card(s, other)
    records = [r for r in s.state.rules.replacements if r.get('until') == 'source_on_battlefield']
    assert {r['source_card'] for r in records} == {saga.id, copied.id}
    act(s, 'p1', type='move', card_ids=[saga.id], to={'player': 'p1', 'zone': 'hand'})
    from app.rules.plan import Plan
    from app.rules.timed_damage_replacements import active
    p = Plan(s.state, 'p1', cards, None)
    assert {r['source_card'] for r in s.state.rules.replacements if r.get('until') == 'source_on_battlefield' and active(p, r)} == {copied.id}
    attack(s, [opponent, other], pid='p2', target='p1', turn=8)
    damage(s)
    assert s.state.players['p1'].life == 37


def test_saga_source_duration_survives_effect_creator_departure_when_original_source_remains(cards):
    ns = [*NAMES, NAME, 'Clever Concealment', 'Copy Enchantment', 'Stifle']
    s = table(cards, ns, ns, ns)
    own = put(s, 'Grizzly Bears', 'battlefield')
    opponent = put(s, 'Centaur Courser', 'battlefield', 'p3')
    saga = cast(s, NAME)
    choose_card(s, own)
    act(s, 'p1', type='set_controller', card_ids=[saga.id], player='p2')
    to_phase(s, 'main1', turn=2)
    choose_card(s, opponent)
    record, = (r for r in s.state.rules.replacements if r.get('source_card') == saga.id)
    assert record['controller'] == 'p2'
    act(s, 'p2', type='set_controller', card_ids=[saga.id], player='p1')
    act(s, 'p2', type='concede')
    assert s.state.cards[saga.id].zone == 'p1:battlefield'
    attack(s, [opponent], pid='p3', target='p1', turn=3)
    damage(s)
    assert s.state.players['p1'].life == 40


def test_saga_whole_canonical_definition_coverage(cards):
    from app.rules import coverage
    result = coverage.of_card_data(cards.resolve(NAME))
    assert result.level == 'FULL', result.manual_parts


def test_saga_second_chapter_remains_native_counterable_trigger(cards):
    s, own, opponent, saga = saga_setup(cards, answer=False)
    d = s.state.rules.decision
    option = next(o for o in d.options if o.card_id == opponent.id or o.id == opponent.id)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option.id])
    trigger = next(reversed(s.state.rules.stack))
    cast(s, 'Stifle', [trigger], pid='p3')
    assert not any(r.get('source_card') == saga.id for r in s.state.rules.replacements)
    attack(s, [opponent], pid='p2', target='p1', turn=5)
    damage(s)
    assert s.state.players['p1'].life == 37
