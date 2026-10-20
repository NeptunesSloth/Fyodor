"""Case File Auditor sees native To solve resolution, with exact private look choices."""
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
from tests.test_rules_player_protection import priority
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold


@pytest.fixture()
def cards(settings):
    data = json.loads((Path(__file__).parent / 'fixtures/case_solve_watchers_cards.json').read_text())
    extra = [card(c['name'], set_code='vma', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code')}) for i, c in enumerate(data)]
    settings.ensure_dirs()
    build_database([*fixture_cards(), *extra], settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards):
    names = ['Case File Auditor', 'Case of the Locked Hothouse', 'Stifle', 'Strionic Resonator', 'Grizzly Bears', 'Pacifism']
    s = three(cards, names, names, names)
    hold(s)
    return s


def choose(s, ids=()):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=list(ids))
    settle(s)


def top(s, name):
    c = put(s, name, 'library')
    act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    return c


def test_auditor_canonical_etb_optional_enchantment_and_case_only_mana(cards):
    from app.game.errors import ActionError
    s = setup(cards)
    case = top(s, 'Case of the Locked Hothouse')
    spell(s, 'Case File Auditor', {'W': 1, 'C': 2})
    assert case.id not in str(s.view('p2').get('rules', {}).get('decision', {}))
    choose(s, [case.id])
    assert s.state.cards[case.id].zone == 'p1:hand'
    assert coverage.of_card_data(cards.resolve('Case File Auditor')).level == 'FULL'
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 4})
    act(s, 'p1', type='cast_spell', card_id=case.id, sources=[])
    settle(s)
    assert s.state.cards[case.id].zone == 'p1:battlefield'
    bear = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 2})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bear.id, sources=[])
    roundtrip(s)


def to_solve(s):
    from tests.test_rules_wave30m_durations import stops, to_phase
    case = put(s, 'Case of the Locked Hothouse', 'battlefield')
    forests = [c.id for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest'][:7]
    act(s, 'p1', type='move', card_ids=forests, to={'player': 'p1', 'zone': 'battlefield'})
    stops(s, 'end')
    to_phase(s, 'end')
    assert any(e.source_card == case.id for e in s.state.rules.stack.values())
    return case, forests


@pytest.mark.parametrize('edge', ['resolve', 'countered', 'condition_false', 'source_left', 'manual'])
def test_auditor_only_actual_to_solve_resolution_triggers(cards, edge):
    s = setup(cards)
    source = spell(s, 'Case File Auditor', {'W': 1, 'C': 2})
    choose(s)
    selected = top(s, 'Pacifism')
    if edge == 'manual':
        case = put(s, 'Case of the Locked Hothouse', 'battlefield')
        act(s, 'p1', type='set_choice', card_id=case.id, key='Solved', value='Yes')
        settle(s)
        assert s.state.rules.decision is None
        roundtrip(s)
        return
    case, forests = to_solve(s)
    if edge == 'condition_false':
        act(s, 'p1', type='move', card_ids=[forests[0]], to={'player': 'p1', 'zone': 'hand'})
    if edge == 'source_left':
        act(s, 'p1', type='move', card_ids=[case.id], to={'player': 'p1', 'zone': 'hand'})
    if edge == 'countered':
        target = next(cid for cid, e in s.state.rules.stack.items() if e.source_card == case.id)
        priority(s, 'p2')
        stifle = put(s, 'Stifle', 'hand', 'p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
        act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[target])
    settle(s)
    if edge in ('resolve', 'source_left'):
        assert s.state.rules.decision is not None
        choose(s, [selected.id])
        assert s.state.cards[selected.id].zone == 'p1:hand'
    else:
        assert s.state.rules.decision is None
        assert s.state.cards[selected.id].zone == 'p1:library'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    if edge == 'resolve':
        assert 'Solved' in s.state.cards[case.id].choices
    roundtrip(s)


@pytest.mark.parametrize('source_left', [False, True])
def test_auditor_to_solve_copy_counts_actual_resolutions_and_source_last_known(cards, source_left):
    s = setup(cards)
    spell(s, 'Case File Auditor', {'W': 1, 'C': 2})
    choose(s)
    case, _ = to_solve(s)
    target = next(cid for cid, e in s.state.rules.stack.items() if e.source_card == case.id)
    resonator = put(s, 'Strionic Resonator', 'battlefield')
    if source_left:
        act(s, 'p1', type='move', card_ids=[case.id], to={'player': 'p1', 'zone': 'hand'})
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=resonator.id, ability=0, targets=[target])
    settle(s)
    count = 0
    while s.state.rules.decision is not None:
        count += 1
        assert count <= 2
        choose(s)
    # With its source present the original now fails its unsolved intervening-if.
    # With its source absent both native To solve abilities still resolve but cannot mark it.
    assert count == (2 if source_left else 1)
    assert ('Solved' in s.state.cards[case.id].choices) == (not source_left)
    roundtrip(s)


@pytest.mark.parametrize('kind', ['enters', 'solve'])
def test_auditor_private_native_look_resumes_in_fresh_process(cards, tmp_path, kind):
    import subprocess
    import sys

    s = setup(cards)
    if kind == 'solve':
        spell(s, 'Case File Auditor', {'W': 1, 'C': 2})
        choose(s)
    selected = top(s, 'Pacifism')
    if kind == 'enters':
        spell(s, 'Case File Auditor', {'W': 1, 'C': 2})
    else:
        to_solve(s)
        settle(s)
    assert s.state.rules.decision is not None
    assert selected.id not in str(s.view('p2').get('rules', {}).get('decision', {}))
    path = tmp_path / (kind + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, selected = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [selected]})
assert s.state.cards[selected].zone == 'p1:hand'
assert s.state.rules.decision is None
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), selected.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
