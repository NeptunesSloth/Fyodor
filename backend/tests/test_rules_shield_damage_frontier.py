"""Canonical shield counters must participate in damage replacement ordering."""
from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_damage_redirection import activate, cast
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


def shielded(cards, name):
    s = table(cards, ['Boon of Safety', name, 'Pestilence', 'Skullcrack', 'Furnace of Rath', 'Forest'],
              ['Forest'], ['Forest'])
    creature = put(s, name, 'battlefield')
    cast(s, 'Boon of Safety', [creature.id])
    if s.state.rules.decision:
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    assert s.state.cards[creature.id].counters.get('shield') == 1
    return s, creature.id


def test_actual_boon_shield_is_removed_when_skullcrack_damage_cannot_be_prevented(cards):
    s, creature = shielded(cards, 'Centaur Courser')
    cast(s, 'Skullcrack', ['p3'])
    source = put(s, 'Pestilence', 'battlefield')
    activate(s, source, 'deals 1 damage')
    assert s.state.cards[creature].damage == 1
    assert s.state.cards[creature].counters.get('shield', 0) == 0
    roundtrip(s)


def test_actual_boon_shield_is_a_native_order_option_with_protection_and_furnace(cards):
    s, creature = shielded(cards, 'White Knight')
    put(s, 'Furnace of Rath', 'battlefield')
    source = put(s, 'Pestilence', 'battlefield')
    activate(s, source, 'deals 1 damage')
    d = s.state.rules.decision
    assert d is not None
    assert any('shield counter' in o.label.lower() for o in d.options)
    assert s.state.cards[creature].counters.get('shield') == 1


def test_shield_projection_does_not_remove_a_counter_or_report_unpreventable_damage_prevented(cards):
    from app.rules import replace
    from app.rules.plan import Plan

    s, creature = shielded(cards, 'Centaur Courser')
    source = put(s, 'Pestilence', 'battlefield')
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    events = [{'source_card': source.id, 'source_oid': plan.oid(source), 'target': creature,
               'amount': 1, 'combat': False, 'unpreventable': True,
               'src': replace.source_info(plan, source.id, plan.oid(source), plan.ch(source), 'p1')}]
    out = replace.damage_outcome(plan, events, answers={}, order=None, ask=True)
    assert isinstance(out, replace.DamageOutcome)
    assert out.shield_counters == [creature]
    assert not out.preventions
    assert plan.state.cards[creature].counters.get('shield') == 1
    assert replace.do_damage(plan, out, actor='p1', combat=False)
    assert plan.state.cards[creature].counters.get('shield', 0) == 0
    assert plan.state.cards[creature].damage == 1
    assert not any(e.kind == 'damage_prevented' for e in plan.rules.events)


def test_shield_and_protection_order_cold_resume_does_not_consume_during_preview(cards, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    s, creature = shielded(cards, 'White Knight')
    put(s, 'Furnace of Rath', 'battlefield')
    source = put(s, 'Pestilence', 'battlefield')
    activate(s, source, 'deals 1 damage')
    assert s.state.cards[creature].counters.get('shield') == 1
    saved = tmp_path / 'shield.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
save,db,creature=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
choice=next(o.id for o in d.options if 'shield counter' in o.label.lower())
assert s.state.cards[creature].counters.get('shield')==1
act(s,'p1',type='choose',decision_id=d.id,option_ids=[choice])
settle(s)
assert s.state.cards[creature].counters.get('shield',0)==0
assert s.state.cards[creature].damage==0
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), creature],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
