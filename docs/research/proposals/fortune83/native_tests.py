"""Fortune's delayed blink uses original source and chosen contributor identities."""
import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_crew_saddle_readers81 import cards as cards
from tests.test_rules_crew_saddle_readers81 import crew81, setup81
from tests.test_rules_designations import pick
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack


def test_fortune_whole83(cards):
    assert coverage.of_card_data(cards.resolve('Fortune, Loyal Steed')).level == 'FULL'


@pytest.mark.parametrize('choose', [True, False])
def test_fortune_actual_saddled_attack_delayed_contributor_blink(cards, choose):
    s, source, bear = setup81(cards, 'Fortune, Loyal Steed')
    crew81(s, source, bear, saddle=True)
    before = s.state.rules.object_id(source.id), s.state.rules.object_id(bear.id)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    settle(s)
    assert any(d.when.get('step') == 'end_combat' for d in s.state.rules.delayed)
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and bear.id in {o.id for o in d.options}:
            break
        if d is not None:
            assert d.kind == 'declare_blockers', d.model_dump()
            act(s, d.player, type='declare_blockers', blocks=[])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.decision is not None
    assert bear.id in {o.id for o in s.state.rules.decision.options}, {'decision': s.state.rules.decision.model_dump(), 'facts': [f.model_dump() for f in s.state.rules.turn_log.facts], 'before':before, 'current':(s.state.rules.object_id(source.id),s.state.rules.object_id(bear.id))}
    pick(s, [bear.id] if choose else [])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.object_id(source.id) != before[0]
    assert (s.state.rules.object_id(bear.id) != before[1]) == choose


def finish_scry83(s):
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            return
        if 'scry' in d.prompt.lower():
            pick(s, [])
        elif d.kind == 'order':
            pick(s, [o.id for o in d.options])
        else:
            return
        settle(s)


def test_fortune_source_blink_preserves_original_contributor_without_blinking_new_fortune(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    s, source, bear = setup81(cards, 'Fortune, Loyal Steed')
    crew81(s, source, bear, saddle=True)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    settle(s)
    old_bear = s.state.rules.object_id(bear.id)
    assert s.state.rules.delayed
    spell = put(s, 'Cloudshift', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[source.id])
    settle(s)
    finish_scry83(s)
    new_source = s.state.rules.object_id(source.id)
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and bear.id in {o.id for o in d.options}:
            break
        if d is not None:
            assert d.kind == 'declare_blockers', d.model_dump()
            act(s, d.player, type='declare_blockers', blocks=[])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.decision is not None
    assert bear.id in {o.id for o in s.state.rules.decision.options}
    pick(s, [bear.id])
    settle(s)
    assert s.state.rules.object_id(source.id) == new_source
    assert s.state.rules.object_id(bear.id) != old_bear


def test_fortune_unsaddled_attack_does_not_schedule_blink(cards):
    s, source, bear = setup81(cards, 'Fortune, Loyal Steed')
    original = s.state.rules.object_id(source.id)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    settle(s)
    assert not s.state.rules.delayed
    assert s.state.rules.object_id(source.id) == original


def test_fortune_does_not_exile_returned_new_object_of_contributor(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put
    s, source, bear = setup81(cards, 'Fortune, Loyal Steed')
    crew81(s, source, bear, saddle=True)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    settle(s)
    source_before = s.state.rules.object_id(source.id)
    spell = put(s, 'Cloudshift', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    new_bear = s.state.rules.object_id(bear.id)
    to_phase(s, 'end_combat', turn=4)
    settle(s)
    finish_scry83(s)
    assert s.state.rules.object_id(bear.id) == new_bear
    assert s.state.rules.object_id(source.id) != source_before


def test_genuine_cold_pending_fortune_delayed_choice(cards, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    import app
    s, source, bear = setup81(cards, 'Fortune, Loyal Steed')
    crew81(s, source, bear, saddle=True)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    settle(s)
    assert s.state.rules.delayed
    before = s.state.rules.object_id(source.id), s.state.rules.object_id(bear.id)
    saved = tmp_path / 'fortune83.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import pick
from tests.game_helpers import act
from tests.test_rules_fortune83 import finish_scry83
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source,bear,source_old,bear_old=sys.argv[3:]
for _ in range(80):
 d=s.state.rules.decision
 if d is not None and bear in {o.id for o in d.options}:break
 if d is not None:
  assert d.kind=='declare_blockers'
  act(s,d.player,type='declare_blockers',blocks=[])
 else:act(s,s.state.rules.priority,type='pass_priority')
assert s.state.rules.decision is not None
assert bear in {o.id for o in s.state.rules.decision.options}
pick(s,[bear]);settle(s);finish_scry83(s)
assert s.state.cards[source].zone=='p1:battlefield'
assert s.state.cards[bear].zone=='p1:battlefield'
assert s.state.rules.object_id(source)!=source_old
assert s.state.rules.object_id(bear)!=bear_old
assert not s.state.rules.delayed
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, bear.id, *before],
        capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


def test_fortune_exiled_token_contributor_does_not_return(cards):
    from tests.test_rules_effects import token
    s, source, bear = setup81(cards, 'Fortune, Loyal Steed')
    payer = token(s, 'p1', 'Fortune saddle token83', pt='1/1')
    crew81(s, source, payer, saddle=True)
    old_source = s.state.rules.object_id(source.id)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    settle(s)
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and payer.id in {o.id for o in d.options}:
            break
        if d is not None:
            assert d.kind == 'declare_blockers'
            act(s, d.player, type='declare_blockers', blocks=[])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.decision is not None
    pick(s, [payer.id])
    settle(s)
    finish_scry83(s)
    assert payer.id not in s.state.cards
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.object_id(source.id) != old_source


def test_fortune_actual_printed_cast_scry_completion(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_crew_saddle_readers81 import DATA
    from tests.test_rules_declaration_requirements33 import start
    from tests.test_rules_designations import put
    from tests.test_rules_shared_damage_choices import table
    s = table(cards, [c['name'] for c in DATA], ['Forest'], [])
    source = put(s, 'Fortune, Loyal Steed', 'hand')
    start(s)
    mana(s, W=1, C=2)
    act(s, 'p1', type='cast_spell', card_id=source.id)
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.decision is not None and 'scry' in s.state.rules.decision.prompt.lower()
    finish_scry83(s)
    assert s.state.rules.decision is None


@pytest.mark.parametrize('changed', ['source', 'contributor'])
def test_fortune_native_controller_change_retains_choice_and_returns_to_owners(cards, changed):
    s, source, bear = setup81(cards, 'Fortune, Loyal Steed')
    crew81(s, source, bear, saddle=True)
    to_phase(s, 'declare_attackers', turn=4)
    attack(s, (source, 'p2'))
    settle(s)
    act(s, 'p1', type='set_controller', card_ids=[source.id if changed == 'source' else bear.id], player='p2')
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and bear.id in {o.id for o in d.options}:
            break
        if d is not None:
            assert d.kind == 'declare_blockers'
            act(s, d.player, type='declare_blockers', blocks=[])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.decision is not None and s.state.rules.decision.player == 'p1'
    assert bear.id in {o.id for o in s.state.rules.decision.options}
    pick(s, [bear.id])
    settle(s)
    finish_scry83(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].controller == s.state.cards[source.id].controller == 'p1'
