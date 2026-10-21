"""Native construction-time capture proofs; untap producer remains isolated."""
from pathlib import Path

import pytest

from app.rules import layers, read_pass
from app.rules import static_grant_capture45 as capture
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_untap_attempts45 import cards as cards
from tests.test_rules_untap_attempts45 import scene


def test_actual_two_same_text_grants_have_native_source_indices_and_exact_objects(cards):
    s, bear, first = scene(cards)
    second = put(s, 'Bewitching Leechcraft', 'battlefield', pid='p2')
    act(s, 'p1', type='attach', card_ids=[second.id], to=bear.id)
    plan = Plan(s.state, 'p1', cards, None)
    before = plan.state.model_dump(mode='json')
    actual = plan.state.cards[bear.id]
    regular = plan.ch(actual)
    for _ in range(3):
        ch, rows = capture.capture(plan.state, actual, cards)
        assert ch == regular and len(rows) == 2
        assert {r.source.object_id for r in rows} == {plan.oid(first), plan.oid(second)}
        assert len({(r.source.object_id, r.ability, r.ordinal) for r in rows}) == 2
        assert all(r.recipient.object_id == plan.oid(bear) and r.ability == 2 and r.ordinal == 0 for r in rows)
    assert plan.state.model_dump(mode='json') == before
    assert layers._T.grant_capture45 is None


def test_native_wipe_filters_old_grant_and_later_granter_is_captured(cards):
    names = ['Grizzly Bears', 'Bewitching Leechcraft', 'Humility']
    s = table(cards, names, names, names)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    old = put(s, 'Bewitching Leechcraft', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[old.id], to=bear.id)
    put(s, 'Humility', 'battlefield', pid='p3')
    plan = Plan(s.state, 'p1', cards, None)
    ch, rows = capture.capture(plan.state, plan.state.cards[bear.id], cards)
    assert ch.pt == (1, 1) and not rows
    new = put(s, 'Bewitching Leechcraft', 'battlefield', pid='p2')
    act(s, 'p1', type='attach', card_ids=[new.id], to=bear.id)
    plan = Plan(s.state, 'p1', cards, None)
    ch, rows = capture.capture(plan.state, plan.state.cards[bear.id], cards)
    assert ch.pt == (1, 1) and len(rows) == 1
    assert rows[0].source.object_id == plan.oid(new) and rows[0].source.object_id != plan.oid(old)


def test_blinked_granter_yields_new_source_identity_without_rebinding_old_receipt(cards):
    s, bear, aura = scene(cards)
    plan = Plan(s.state, 'p1', cards, None)
    _, original = capture.capture(plan.state, plan.state.cards[bear.id], cards)
    old = original[0].source.object_id
    act(s, 'p1', type='move', card_ids=[aura.id], to={'zone': 'hand'})
    act(s, 'p1', type='move', card_ids=[aura.id], to={'zone': 'battlefield'})
    act(s, 'p1', type='attach', card_ids=[aura.id], to=bear.id)
    plan = Plan(s.state, 'p1', cards, None)
    _, current = capture.capture(plan.state, plan.state.cards[bear.id], cards)
    assert len(current) == 1 and current[0].source.object_id == plan.oid(aura)
    assert current[0].source.object_id != old and original[0].source.object_id == old


def test_actual_derived_cache_is_bypassed_for_capture_without_clearing_or_replacing_it(cards):
    s, bear, _ = scene(cards)
    plan = Plan(s.state, 'p1', cards, None)
    actual = plan.state.cards[bear.id]
    with read_pass.scope(plan.state, cards) as scope:
        regular = plan.ch(actual)
        retained = scope.derived[id(actual)]
        ch, rows = capture.capture(plan.state, actual, cards)
        assert rows and ch == regular
        assert scope.derived[id(actual)] is retained
        assert plan.ch(actual) is regular


def test_capture_restores_thread_local_state_even_when_native_derivation_raises(cards, monkeypatch):
    s, bear, _ = scene(cards)
    plan = Plan(s.state, 'p1', cards, None)
    before = (layers._T.depth, layers._T.memo, layers._T.borrow_graph, layers._T.grant_capture45)

    def explode(*args, **kwargs):
        assert layers._T.grant_capture45 is not None
        raise RuntimeError('actual capture failure')

    monkeypatch.setattr(layers, '_derive', explode)
    with pytest.raises(RuntimeError, match='actual capture failure'):
        capture.capture(plan.state, plan.state.cards[bear.id], cards)
    assert (layers._T.depth, layers._T.memo, layers._T.borrow_graph, layers._T.grant_capture45) == before


def test_native_protection_expansion_keeps_original_grant_ordinal_and_separate_expansion_paths(cards):
    names = ['Grizzly Bears', "Commander's Plate"]
    s = table(cards, names, names, names)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    plate = put(s, "Commander's Plate", 'battlefield')
    act(s, 'p1', type='attach', card_ids=[plate.id], to=bear.id)
    plan = Plan(s.state, 'p1', cards, None)
    regular = plan.ch(plan.state.cards[bear.id])
    ch, rows = capture.capture(plan.state, plan.state.cards[bear.id], cards)
    assert ch == regular and len(rows) == 4
    assert {r.text for r in rows} == {'Protection from white', 'Protection from blue', 'Protection from black', 'Protection from green'}
    assert len({r.expansion for r in rows}) == 4
    assert all(r.source.object_id == plan.oid(plate) and r.ability == 0 and r.ordinal == 0 for r in rows)


def test_default_runtime_refuses_uninstalled_constructor_instead_of_returning_empty_provenance(cards, monkeypatch):
    s, bear, _ = scene(cards)
    plan = Plan(s.state, 'p1', cards, None)
    monkeypatch.setattr(layers, 'STATIC_GRANT_CAPTURE45', False)
    with pytest.raises(RuntimeError, match='not installed'):
        capture.capture(plan.state, plan.state.cards[bear.id], cards)


def test_actual_captured_same_text_grants_feed_saved_native_untap_ancestry_cold(cards, tmp_path):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.rules import context
    from app.rules import untap_attempts45 as model

    s, bear, _ = scene(cards, plus=2, stun=1)
    second = put(s, 'Bewitching Leechcraft', 'battlefield', pid='p2')
    act(s, 'p1', type='attach', card_ids=[second.id], to=bear.id)
    plan = Plan(s.state, 'p1', cards, None)
    _, origins = capture.capture(plan.state, plan.state.cards[bear.id], cards)
    assert len(origins) == 2 and all(r.source is not None and r.ability is not None and not r.static_path for r in origins)
    recipient = context.ref_of(plan, bear.id)
    frame = model.UntapAttempt(recipient=recipient, actor='p1', step_player='p1', grants=[
        model.NativeGrant(source=r.source, ability=r.ability, ordinal=r.ordinal) for r in origins])
    frame.ctx = {'controller': 'p1', 'source_card': bear.id, 'source_object': plan.oid(bear), 'name': 'Captured ancestry model',
                 'next': 0, 'stack_id': '', 'body_done': {'do': 'noop'}, 'effects': [{'do': 'gain_life', 'who': 'you', 'n': 7}]}
    model.begin(plan, frame)
    s = GameSession(plan.state, cards=cards)
    d = s.state.rules.decision
    first = frame.grants[0].key()
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[first])
    d = s.state.rules.decision
    saved_frame = model.UntapAttempt.model_validate(d.resume['frame'])
    assert saved_frame.ancestry == [first] and saved_frame.removals[0].actual == 1
    assert s.state.cards[bear.id].counters == {'+1/+1': 1, 'stun': 1}
    saved = tmp_path / 'captured-untap45.json'
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
state,db,bear,first=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(state).read_text()),cards=repo)
d=s.state.rules.decision
assert first not in {o.id for o in d.options}
second=next(o.id for o in d.options if o.id.startswith('grant:'))
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[second]})
assert s.state.rules.decision is None and s.state.cards[bear].tapped
assert not s.state.cards[bear].counters and s.state.players['p1'].life==47
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), bear.id, first],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_provenance_metadata_preserves_existing_native_static_equality():
    from dataclasses import replace

    base = layers.Static('original', 'p1', {}, 1)
    assert replace(base, ability_index=7, ability_path=(1,)) == base


@pytest.mark.parametrize('ability', [None, 7])
def test_unknown_static_origin_never_mints_current_successor_object_as_old_producer(cards, ability):
    s, bear, aura = scene(cards)
    plan = Plan(s.state, 'p1', cards, None)
    old = plan.oid(aura)
    # Explicit model of a nonauthoritative/resolved Static whose source ID
    # remains while its original source has left and returned as a successor.
    plan.do({'type': 'move', 'card_ids': [aura.id], 'to': {'zone': 'hand'}}, actor='p1')
    plan.do({'type': 'move', 'card_ids': [aura.id], 'to': {'zone': 'battlefield'}}, actor='p1')
    assert plan.oid(aura) != old
    unknown = layers.Static(aura.id, 'p1', {}, 1, effect_key=(1, 1, 1), ability_index=ability)
    collector = capture.Capture(plan.state, bear.id)
    collector.record(plan.state, plan.state.cards[bear.id], unknown, 0, (), 'Uncertain old effect')
    assert len(collector.grants) == 1
    row = collector.grants[0]
    assert row.source is None and row.ability is None and row.source_card == aura.id


def test_capture_explicitly_rejects_a_prospective_successor_probe(cards):
    s, bear, _ = scene(cards)
    plan = Plan(s.state, 'p1', cards, None)
    probe = plan.state.cards[bear.id].model_copy()
    with pytest.raises(RuntimeError, match='prospective probe'):
        capture.capture(plan.state, probe, cards)


@pytest.mark.parametrize('later', [False, True])
def test_combined_native_quoted_loss_filter_records_only_final_accepted_static_grant(cards, monkeypatch, later):
    """Explicit native Static input; no new printed quoted-grant producer claim."""
    from typing import Literal

    from app.game.rules_state import ContinuousEffect
    from app.rules import quoted_prevention_loss47 as loss
    from app.rules import statics

    class NativeLoss(ContinuousEffect):
        lose_quoted_ability: Literal['prevent_all_damage_to_self'] = 'prevent_all_damage_to_self'

    names = ['Grizzly Bears', 'Sol Ring']
    s = table(cards, names, names, names)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    granter = put(s, 'Sol Ring', 'battlefield')
    plan = Plan(s.state, 'p1', cards, None)
    loss_effect = NativeLoss(id='typed-kernel-loss', layer='6', controller='p1', affected=[plan.oid(bear)],
                             object_seq=layers.timestamp(plan.state, granter.id), timestamp=1)
    plan.rules.effects.append(loss_effect)
    if later:
        plan.do({'type': 'move', 'card_ids': [granter.id], 'to': {'zone': 'hand'}}, actor='p1')
        plan.do({'type': 'move', 'card_ids': [granter.id], 'to': {'zone': 'battlefield'}}, actor='p1')
    recipe = statics.parse('Creatures you control have flying.')
    assert recipe is not None
    recipe = {**recipe, 'keywords': [], 'grants': [loss.ABILITY]}
    native_table = layers.statics

    def input_table(state, info):
        current = state.cards[granter.id]
        return [*native_table(state, info), layers.Static(current.id, current.controller, recipe,
                                                        layers.timestamp(state, current.id))]

    monkeypatch.setattr(layers, 'statics', input_table)
    ch, rows = capture.capture(plan.state, plan.state.cards[bear.id], cards)
    assert sum(loss.matches(a.text, ch.name) for a in ch.abilities) == int(later)
    assert len(rows) == int(later)
    if later:
        assert rows[0].source is None and rows[0].ability is None
        assert rows[0].source_card == granter.id and loss.matches(rows[0].text, ch.name)


def test_actual_native_grant_capture_reacquires_same_original_refs_after_cold_rebuild(cards, tmp_path):
    import json
    import subprocess
    import sys

    names = ['Grizzly Bears', "Commander's Plate"]
    s = table(cards, names, names, names)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    plate = put(s, "Commander's Plate", 'battlefield')
    act(s, 'p1', type='attach', card_ids=[plate.id], to=bear.id)
    plan = Plan(s.state, 'p1', cards, None)
    _, rows = capture.capture(plan.state, plan.state.cards[bear.id], cards)
    assert len(rows) == 4
    expected = [[r.recipient.model_dump(mode='json'), r.source.model_dump(mode='json'), r.ability,
                 list(r.static_path), r.ordinal, list(r.expansion), r.text] for r in rows]
    state = tmp_path / 'native-capture-cold.json'
    state.write_text(plan.state.model_dump_json())
    receipt = tmp_path / 'native-capture-expected.json'
    receipt.write_text(json.dumps(expected))
    script = r'''
import json
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.rules.static_grant_capture45 import capture
state, db, bear, receipt = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
actual = GameState.model_validate_json(Path(state).read_text())
before = actual.model_dump(mode='json')
ch, rows = capture(actual, actual.cards[bear], repo)
assert len(rows) == 4
found = [[r.recipient.model_dump(mode='json'), r.source.model_dump(mode='json'), r.ability,
          list(r.static_path), r.ordinal, list(r.expansion), r.text] for r in rows]
assert found == json.loads(Path(receipt).read_text())
assert actual.model_dump(mode='json') == before
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(state), str(cards.db_path), bear.id, str(receipt)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
