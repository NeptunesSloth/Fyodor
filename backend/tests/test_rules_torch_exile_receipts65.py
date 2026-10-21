"""Bargained damage, scry continuations, and exile all retain native spell receipts."""
import pytest

from app.rules import coverage
from app.rules.view import hints
from tests import test_rules_fight_exile_receipts65 as support
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast


@pytest.fixture()
def cards(settings):
    yield from support.cards.__wrapped__(settings)


setup = support.setup


def test_whole_torch_canonical(cards):
    assert coverage.of_card_data(cards.resolve('Torch the Tower')).level == 'FULL'


def test_unbargained_two_damage_exiles_without_scry(cards):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, 'Torch the Tower', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert s.state.rules.decision is None
    roundtrip(s)


def bargain(s, target):
    ring = put(s, 'Sol Ring', 'battlefield')
    source = put(s, 'Torch the Tower', 'hand')
    mana(s, R=1)
    opt = hints(s.state, 'p1', s.cards)['optional_costs'][source.id][0]
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[target.id], optional_costs=[opt['id']], sources=[])
    settle(s)
    assert s.state.cards[ring.id].zone == 'p1:graveyard'
    return source


def test_actual_bargain_three_damage_scry_then_exile(cards):
    s = setup(cards)
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    bargain(s, target)
    d = s.state.rules.decision
    assert d is not None
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    assert s.state.cards[target.id].damage == 3
    answer(s, [])
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:exile'
    roundtrip(s)


def test_prevented_torch_damage_creates_no_exile_replacement(cards):
    from tests.test_rules_conditional_prevention import cast as preventing_cast

    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    preventing_cast(s, 'Healing Salve', targets=[target.id], modes=[1], pid='p2')
    cast(s, 'Torch the Tower', targets=[target.id])
    cast(s, 'Murder', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_nonlethal_damage_retains_replacement_for_later_destruction(cards):
    s = setup(cards)
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    cast(s, 'Torch the Tower', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    assert s.state.cards[target.id].damage == 2
    cast(s, 'Murder', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:exile'
    roundtrip(s)


def test_torch_damage_receipt_does_not_follow_blinked_successor(cards):
    from tests.test_rules_conditional_prevention import cast as response_cast

    s = setup(cards)
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    cast(s, 'Torch the Tower', targets=[target.id])
    response_cast(s, 'Cloudshift', targets=[target.id], pid='p2')
    cast(s, 'Murder', targets=[target.id])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_genuine_cold_mid_scry_retains_damage_receipt_until_exile_replacement(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    bargain(s, target)
    assert s.state.rules.decision is not None
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    saved = tmp_path / 'torch65.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import roundtrip
from tests.test_rules_library_look import settle
p=Path(sys.argv[1])
repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision
assert d is not None
act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p2:exile'
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), target.id],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_bargain_damage_exiles_planeswalker_after_scry(cards):
    s = setup(cards)
    target = cast(s, 'Jace Beleren')
    assert s.state.cards[target.id].counters.get('loyalty') == 3
    bargain(s, target)
    assert s.state.rules.decision is not None
    answer(s, [])
    settle(s)
    assert s.state.cards[target.id].zone == 'p1:exile'
    roundtrip(s)


def test_actual_reverberate_copy_preserves_paid_bargain_and_scry_receipts(cards):
    from tests.test_rules_conditional_prevention import cast as pending_cast

    s = setup(cards)
    original_target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    copy_target = put(s, 'Centaur Courser', 'battlefield', 'p3')
    ring = put(s, 'Sol Ring', 'battlefield')
    source = put(s, 'Torch the Tower', 'hand')
    mana(s, R=1)
    opt = hints(s.state, 'p1', s.cards)['optional_costs'][source.id][0]
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[original_target.id],
        optional_costs=[opt['id']], sources=[])
    assert s.state.cards[ring.id].zone == 'p1:graveyard'
    pending_cast(s, 'Reverberate', targets=[source.id])
    d = s.state.rules.decision
    assert d and copy_target.id in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[copy_target.id])
    settle(s)
    for _ in range(2):
        d = s.state.rules.decision
        assert d is not None and d.resume.get('step') != 'manual_done'
        answer(s, [])
        settle(s)
    assert s.state.cards[original_target.id].zone == 'p2:exile'
    assert s.state.cards[copy_target.id].zone == 'p3:exile'
    assert s.state.rules.decision is None
    roundtrip(s)
