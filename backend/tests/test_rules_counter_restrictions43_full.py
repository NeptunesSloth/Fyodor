"""Full canonical Fear compound events and live counter-removal prohibition."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_linked_aggregates import cast
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_restrictions43_full_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='crf', number=str(i), **{('card_faces' if k == 'faces' else k): v for k, v in c.items() if k not in ('name', 'set_code')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = ['Fear of Sleep Paralysis', 'Grizzly Bears', 'Glorious Anthem', 'Dazzling Theater // Prop Room', 'Pili-Pala', 'Halo Fountain', 'Vampire Hexmage', 'Nesting Grounds', 'Clockspinning']
    s = table(cards, names, names, names)
    bear = put(s, 'Grizzly Bears', 'battlefield', pid='p2')
    source = put(s, 'Fear of Sleep Paralysis', 'hand')
    cast(s, source)
    settle(s)
    return s, source, bear


def choose(s, who=None):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[] if who is None else [who.id])
    settle(s)


def test_full_canonical(cards):
    q = coverage.of_card_data(cards.resolve('Fear of Sleep Paralysis'))
    assert q.level == 'FULL', [(f.label, f.supported) for f in q.features]


def test_actual_self_entry_one_trigger_taps_and_stuns(cards):
    from app.rules.plan import Plan

    s, source, bear = setup(cards)
    choose(s, bear)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters == {'stun': 1}
    assert 'flying' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).keywords
    roundtrip(s)


def test_actual_other_enchantment_arrival_and_optional_zero(cards):
    s, _, bear = setup(cards)
    choose(s)
    assert not s.state.cards[bear.id].tapped and not s.state.cards[bear.id].counters
    enchantment = put(s, 'Glorious Anthem', 'hand')
    cast(s, enchantment)
    settle(s)
    choose(s, bear)
    assert s.state.cards[bear.id].counters == {'stun': 1}
    roundtrip(s)


def test_actual_room_entry_then_fully_unlock_each_trigger_once(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, _, bear = setup(cards)
    choose(s)
    room = put(s, 'Dazzling Theater // Prop Room', 'hand')
    cast(s, room, face=0)
    settle(s)
    choose(s, bear)
    assert s.state.cards[bear.id].counters == {'stun': 1}
    mana(s, W=1, C=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='unlock_door', card_id=room.id, door=2)
    settle(s)
    choose(s, bear)
    assert s.state.cards[bear.id].counters == {'stun': 2}
    assert s.state.rules.decision is None
    roundtrip(s)


def test_actual_hexmage_removes_other_kinds_but_not_prohibited_stun(cards):
    from tests.test_rules_linked_aggregates import activate

    s, _, bear = setup(cards)
    choose(s, bear)
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=2)
    source = put(s, 'Vampire Hexmage', 'hand')
    cast(s, source)
    settle(s)
    activate(s, source, ability=1, targets=[bear.id])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.cards[bear.id].counters == {'stun': 1}
    roundtrip(s)


def test_actual_nesting_grounds_cannot_move_stun_away_from_protected_source(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s, _, bear = setup(cards)
    choose(s, bear)
    source = put(s, 'Nesting Grounds', 'battlefield', pid='p2')
    dest = put(s, 'Pili-Pala', 'battlefield', pid='p2')
    to_phase(s, 'main1', turn=2)
    mana(s, pid='p2', C=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=1, targets=[bear.id, dest.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[bear.id].counters == {'stun': 1}
    assert not s.state.cards[dest.id].counters
    assert s.state.cards[source.id].tapped
    roundtrip(s)


def test_actual_live_fear_blocks_untap_step_q_and_other_untap_cost_atomically(cards):
    from app.game.errors import ActionError
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s, _, bear = setup(cards)
    choose(s, bear)
    pili = put(s, 'Pili-Pala', 'battlefield', pid='p2')
    fountain = put(s, 'Halo Fountain', 'battlefield', pid='p2')
    act(s, 'p2', type='tap', card_ids=[pili.id], tapped=True)
    act(s, 'p2', type='counter', card_ids=[pili.id], kind='stun', delta=2)
    to_phase(s, 'main1', turn=2)
    assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters == {'stun': 1}
    assert s.state.cards[pili.id].tapped and s.state.cards[pili.id].counters == {'stun': 2}
    mana(s, pid='p2', W=1, C=2)
    wait_priority(s, 'p2')
    before = s.state.model_dump(mode='json')
    for source, index in [(pili, 1), (fountain, 0)]:
        with pytest.raises(ActionError):
            act(s, 'p2', type='activate_ability', card_id=source.id, ability=index)
        assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_actual_clockspinning_cannot_choose_prohibited_removal(cards):
    s, _, bear = setup(cards)
    choose(s, bear)
    spell = put(s, 'Clockspinning', 'hand')
    cast(s, spell, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {'stun'}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['stun'])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[bear.id].counters == {'stun': 2}
    roundtrip(s)


def test_actual_opponent_enchantment_does_not_trigger_eerie(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_wave30m_durations import to_phase

    s, _, bear = setup(cards)
    choose(s)
    other = put(s, 'Glorious Anthem', 'hand', pid='p2')
    to_phase(s, 'main1', turn=2)
    mana(s, pid='p2', W=2, C=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=other.id)
    settle(s)
    assert s.state.rules.decision is None
    assert not s.state.cards[bear.id].tapped and not s.state.cards[bear.id].counters
    roundtrip(s)


def test_actual_eerie_target_choice_true_cold_then_source_departure_ends_static(cards, tmp_path):
    import subprocess
    import sys

    s, source, bear = setup(cards)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'fear43.json'
    saved.write_text(s.state.model_dump_json())
    script = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import prohibitions
from app.rules.plan import Plan
from tests.test_rules_designations import settle
from tests.test_rules_wave30m_durations import to_phase
saved, db, source, bear = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(saved).read_text()), cards=repo)
d = s.state.rules.decision
s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[bear]})
settle(s)
assert s.state.cards[bear].tapped and s.state.cards[bear].counters == {'stun':1}
assert prohibitions.cant_remove_counters(Plan(s.state,'p1',repo,None), bear, 'stun') is not None
s.perform('p1', {'type':'move','card_ids':[source],'to':{'zone':'hand'}})
assert prohibitions.cant_remove_counters(Plan(s.state,'p1',repo,None), bear, 'stun') is None
to_phase(s, 'main1', turn=2)
assert s.state.cards[bear].tapped and not s.state.cards[bear].counters
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(saved), str(cards.db_path), source.id, bear.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
