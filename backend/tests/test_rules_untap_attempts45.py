"""Isolated typed untap ancestry model, not a Leechcraft production admission."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.rules import context, effects, scripts
from app.rules import untap_attempts45 as model
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings, monkeypatch):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(json.loads((Path(__file__).parent / 'fixtures/untap_attempts45_cards.json').read_text())):
        base[row['name']] = card(row['name'], set_code='uat', number=str(i), **{
            ('card_faces' if k == 'faces' else k): v for k, v in row.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    original = scripts.define

    def define(ability, ch):
        return model.definition(ability.text) or original(ability, ch)

    monkeypatch.setattr(scripts, 'define', define)
    from app.rules import engine

    monkeypatch.setitem(effects.RESUME, model.STEP, model.resume)
    monkeypatch.setitem(engine.RESUME, model.STEP, model.resume)
    yield repo
    # These explicit temporary grammar descriptors must not outlive their
    # isolated staging fixture. No cache clearing happens inside a scenario.
    scripts._cached.cache_clear()
    scripts.granted_ability.cache_clear()
    repo.close()


def scene(cards, plus=1, stun=1, owner='p1'):
    names = ['Grizzly Bears', 'Bewitching Leechcraft', 'Fear of Sleep Paralysis']
    s = table(cards, names, names, names)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    aura = put(s, 'Bewitching Leechcraft', 'battlefield', pid=owner)
    act(s, 'p1', type='attach', card_ids=[aura.id], to=bear.id)
    act(s, 'p1', type='tap', card_ids=[bear.id], tapped=True)
    for kind, amount in [('+1/+1', plus), ('stun', stun)]:
        act(s, 'p1', type='set_counter', card_id=bear.id, kind=kind, value=amount)
    return s, bear, aura


def frame_of(plan, bear, aura, step_player='p1'):
    ref = context.ref_of(plan, bear.id)
    source = context.ref_of(plan, aura.id)
    assert ref is not None and source is not None
    # Explicit producer-input model: native printed definition/index, not the
    # rendered holder's positional100+k. General final-grant capture is held.
    defs = scripts.definitions(plan.ch(plan.state.cards[aura.id]))
    index = next(i for i, d in defs.items() if any(model.quoted(t) for t in d.get('grants') or []))
    return model.UntapAttempt(recipient=ref, actor='p1', step_player=step_player,
                             grants=[model.NativeGrant(source=source, ability=index, ordinal=0)])


def start(s, bear, aura, step_player='p1', ordinary=False):
    plan = Plan(s.state, 'p1', s.cards, None)
    frame = frame_of(plan, bear, aura, step_player)
    if ordinary:
        previous = (plan.active, plan.state.turn.number)
        plan.do({'type': 'phase', 'to': 'cleanup', 'force': True}, actor=plan.active)
        plan.do({'type': 'next_turn', 'force': True, 'keep_tapped': [bear.id]}, actor=plan.active)
        assert plan.active == 'p1' and plan.state.turn.phase == 'untap'
        frame.turn_finish = model.TurnFinish(previous=previous, plain=True, keep=[bear.id])
    else:
        frame.ctx = {'controller': 'p1', 'source_card': bear.id, 'source_object': plan.oid(bear),
                     'name': 'Explicit untap model', 'stack_id': '', 'next': 0, 'body_done': {'do': 'noop'},
                     'effects': [{'do': 'gain_life', 'who': 'you', 'n': 7}]}
    model.begin(plan, frame)
    return GameSession(plan.state, cards=s.cards)


@pytest.mark.parametrize('plus', [0, 1])
@pytest.mark.parametrize('leech_first', [False, True])
def test_explicit_own_step_competing_replacement_truth_table(cards, plus, leech_first):
    s, bear, aura = scene(cards, plus=plus)
    s = start(s, bear, aura)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    assert len(d.options) == 2 and s.state.players['p1'].life == 40
    roundtrip(s)
    key = next(o.id for o in d.options if o.id.startswith('grant:' if leech_first else 'stun:'))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[key])
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].tapped
    assert s.state.cards[bear.id].counters.get('+1/+1', 0) == (0 if leech_first else plus)
    assert s.state.cards[bear.id].counters.get('stun', 0) == int(leech_first and plus == 0)
    assert s.state.players['p1'].life == 47
    roundtrip(s)


@pytest.mark.parametrize('plus', [0, 1])
def test_explicit_only_leech_replaces_untap_with_failed_or_successful_payment(cards, plus):
    s, bear, aura = scene(cards, plus=plus, stun=0)
    s = start(s, bear, aura)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].tapped == (plus == 0)
    assert not s.state.cards[bear.id].counters
    assert s.state.players['p1'].life == 47


@pytest.mark.parametrize('step', [None, 'p2'])
def test_explicit_outside_own_step_ignores_leech_granted_by_foreign_owner(cards, step):
    s, bear, aura = scene(cards, plus=1, stun=0, owner='p2')
    s = start(s, bear, aura, step_player=step)
    assert s.state.rules.decision is None and not s.state.cards[bear.id].tapped
    assert s.state.cards[bear.id].counters == {'+1/+1': 1}
    assert s.state.players['p1'].life == 47


def test_explicit_native_ordinary_turn_finisher_waits_for_untap_choice(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s, bear, aura = scene(cards, plus=1, stun=1)
    to_phase(s, 'end', turn=3)
    s = start(s, bear, aura, ordinary=True)
    d = s.state.rules.decision
    assert d is not None and s.state.turn.phase == 'untap' and s.state.turn.number == 4
    assert s.state.cards[bear.id].counters == {'+1/+1': 1, 'stun': 1}
    act(s, d.player, type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if o.id.startswith('grant:'))])
    assert s.state.rules.decision is None and s.state.turn.phase == 'upkeep'
    assert s.state.cards[bear.id].tapped and not s.state.cards[bear.id].counters
    roundtrip(s)


def test_explicit_two_native_granter_identities_do_not_repeat_first_leech(cards):
    s, bear, aura = scene(cards, plus=2, stun=1)
    second = put(s, 'Bewitching Leechcraft', 'battlefield', pid='p2')
    act(s, 'p1', type='attach', card_ids=[second.id], to=bear.id)
    plan = Plan(s.state, 'p1', cards, None)
    frame = frame_of(plan, bear, aura)
    other = frame_of(plan, bear, second).grants[0]
    frame.grants.append(other)
    frame.ctx = {'controller': 'p1', 'source_card': bear.id, 'source_object': plan.oid(bear), 'name': 'Explicit model',
                 'next': 0, 'stack_id': '', 'body_done': {'do': 'noop'}, 'effects': [{'do': 'gain_life', 'who': 'you', 'n': 7}]}
    first = frame.grants[0].key()
    model.begin(plan, frame)
    s = GameSession(plan.state, cards=cards)
    d = s.state.rules.decision
    assert len(d.options) == 3
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[first])
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 2 and first not in {o.id for o in d.options}
    saved = model.UntapAttempt.model_validate(d.resume['frame'])
    assert saved.ancestry == [first] and saved.removals[0].actual == 1
    assert {o.id for o in d.options} == {other.key(), 'stun:' + saved.recipient.object_id}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[other.key()])
    assert s.state.rules.decision is None and s.state.cards[bear.id].tapped
    assert not s.state.cards[bear.id].counters and s.state.players['p1'].life == 47


@pytest.mark.parametrize('ordinary', [False, True])
def test_explicit_untap_saved_choice_true_cold_finishes_original_continuation_once(cards, tmp_path, ordinary):
    import subprocess
    import sys

    s, bear, aura = scene(cards, plus=1, stun=1)
    if ordinary:
        from tests.test_rules_wave30m_durations import to_phase

        to_phase(s, 'end', turn=3)
    s = start(s, bear, aura, ordinary=ordinary)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'untap45.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from tests.staged_untap45 import install
install()
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state,db,bear,ordinary=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(state).read_text()),cards=repo)
d=s.state.rules.decision
assert d is not None
pick=next(o.id for o in d.options if o.id.startswith('grant:'))
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[pick]})
assert s.state.rules.decision is None and s.state.cards[bear].tapped
assert not s.state.cards[bear].counters
assert s.state.players['p1'].life==(40 if ordinary=='True' else 47)
if ordinary=='True': assert s.state.turn.phase=='upkeep' and s.state.turn.number==4
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), bear.id, str(ordinary)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('leech_first', [False, True])
def test_explicit_native_fear_prohibition_never_restores_the_replaced_untap(cards, leech_first):
    s, bear, aura = scene(cards, plus=1, stun=1)
    put(s, 'Fear of Sleep Paralysis', 'battlefield', pid='p2')
    s = start(s, bear, aura)
    d = s.state.rules.decision
    assert d is not None
    key = next(o.id for o in d.options if o.id.startswith('grant:' if leech_first else 'stun:'))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[key])
    assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters.get('stun') == 1
    assert s.state.cards[bear.id].counters.get('+1/+1', 0) == int(not leech_first)
    assert s.state.rules.decision is None and s.state.players['p1'].life == 47


@pytest.mark.parametrize('changed', ['holder', 'granter'])
def test_explicit_saved_attempt_never_rebinds_a_blinked_original(cards, changed):
    s, bear, aura = scene(cards, plus=1, stun=1)
    s = start(s, bear, aura)
    d = s.state.rules.decision
    assert d is not None
    oldkey = next(o.id for o in d.options if o.id.startswith('grant:'))
    obj = bear if changed == 'holder' else aura
    old = s.state.rules.object_id(obj.id)
    act(s, 'p1', type='move', card_ids=[obj.id], to={'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[obj.id], to={'zone': 'battlefield'})
    assert s.state.rules.object_id(obj.id) != old
    if changed == 'holder':
        act(s, 'p1', type='tap', card_ids=[bear.id], tapped=True)
        act(s, 'p1', type='set_counter', card_id=bear.id, kind='charge', value=3)
    # A blinked Aura is a new, unattached object, not the old granting effect.
    # Discovery of newly applicable grants remains the explicit producer gate.
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[oldkey])
    assert s.state.rules.decision is None and s.state.players['p1'].life == 47
    if changed == 'holder':
        assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters == {'charge': 3}
    else:
        assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters == {'+1/+1': 1}
