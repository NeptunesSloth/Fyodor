"""Companion restrictions read original physical deck cards through native merges/copies."""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import casting
from app.rules.plan import Plan
from tests.game_helpers import act, enable
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_mana_followthrough_profiles import cards  # noqa: F401
from tests.test_rules_wave18d_merged import mutate_key
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Jegantha, the Wellspring'


def setup(cards, *, bad_commander=False, copied=False, legal_copy=False):  # noqa: F811
    commander = 'Progenitus' if bad_commander else 'Sliver Hivelord'
    main = [('Migratory Greathorn', 1), ('Forest', 97),
            ('Dress Down' if bad_commander else 'Clone' if legal_copy else 'Clever Impersonator' if copied else 'Walking Ballista', 1)]
    def dc(section, name, quantity=1):
        return DeckCard(section, quantity, name, cards.resolve(name)['id'])
    alice = [dc('commander', commander), dc('companion', NAME), *(dc('main', n, q) for n, q in main)]
    bob = [dc('commander', 'Sliver Hivelord'), dc('main', 'Forest', 98 if legal_copy else 99)]
    if legal_copy:
        bob.append(dc('main', 'Serra Angel'))
    s = GameSession(enable(new_game([PlayerSetup('Alice', cards=alice), PlayerSetup('Bob', cards=bob)], shuffle=False)), cards=cards)
    to_phase(s, 'main1', 3)
    wait_priority(s, 'p1')
    companion = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.origin == 'companion')
    return s, companion


def refuse(s, companion):
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError, match="can't be your companion"):
        act(s, 'p1', type='activate_ability', card_id=companion.id, ability=0)
    assert s.state.model_dump(mode='json') == before


def cold_refusal(s, cards, companion, tmp_path):  # noqa: F811
    import subprocess
    import sys
    from pathlib import Path

    path = tmp_path / 'physical-starting-deck.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from app.rules import casting
path,database,companion=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p2')
c=s.state.cards[companion]
assert casting.companion_problem(s.state,'p1',c,repo) is not None
before=s.state.model_dump(mode='json')
try:
 s.perform('p1',{'type':'activate_ability','card_id':companion,'ability':0})
except ActionError:
 pass
else:
 raise AssertionError('Invalid or unknown starting deck allowed companion special action')
assert s.state.model_dump(mode='json')==before
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), companion.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('over', ['over', 'under'])
@pytest.mark.parametrize('commander', [False, True])
def test_actual_mutate_keeps_all_starting_cards_and_commander_components(cards, over, commander, tmp_path):  # noqa: F811
    s, companion = setup(cards, bad_commander=commander)
    if commander:
        put(s, 'Dress Down', 'battlefield')
        host = put(s, 'Progenitus', 'battlefield')
    else:
        host = put(s, 'Walking Ballista', 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
        act(s, 'p1', type='cast_spell', card_id=host.id, x_value=1, sources=[])
        answer(s)
    refuse(s, companion)
    spell = put(s, 'Migratory Greathorn', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 3})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[host.id], alt_cost=mutate_key(s, spell), sources=[])
    for _ in range(50):
        d = s.state.rules.decision
        if d is not None and d.resume.get('step') == 'mutate_choice':
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[over])
            break
        if d is not None:
            raise AssertionError(d)
        act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('Native mutate did not reach its over/under choice')
    answer(s)
    merged = s.state.cards[host.id]
    assert len(merged.merged) == 2 and spell.id not in s.state.cards
    assert any(p.origin == 'command' for p in merged.merged) == commander
    assert casting.companion_problem(s.state, 'p1', companion, cards) is not None
    refuse(s, companion)
    roundtrip(s)
    cold_refusal(s, cards, companion, tmp_path)


def test_native_entering_copy_keeps_the_original_physical_starting_cost(cards, tmp_path):  # noqa: F811
    s, companion = setup(cards, copied=True)
    target = put(s, 'Migratory Greathorn', 'battlefield')
    source = put(s, 'Clever Impersonator', 'hand')
    original = source.card_id
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'U': 2})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            assert any(o.id == target.id for o in d.options)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
            break
        act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('Actual entering copy did not reach its native choice')
    answer(s)
    current = s.state.cards[source.id]
    assert current.card_id == original and current.copy_of is None
    assert Plan(s.state, 'p1', cards, None).ch(current).name == 'Migratory Greathorn'
    refuse(s, companion)
    roundtrip(s)
    cold_refusal(s, cards, companion, tmp_path)


def test_opaque_table_copy_never_hides_an_unknown_original_starting_card(cards, tmp_path):  # noqa: F811
    s, companion = setup(cards)
    target = put(s, 'Migratory Greathorn', 'battlefield')
    source = put(s, 'Walking Ballista', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='cast_spell', card_id=source.id, x_value=1, sources=[])
    answer(s)
    act(s, 'p1', type='set_copy_source', card_id=source.id, source_id=target.id)
    problem = casting.companion_problem(s.state, 'p1', companion, cards)
    assert problem is not None and "doesn't know every card" in problem
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    with pytest.raises(ActionError, match="doesn't know every card"):
        act(s, 'p1', type='activate_ability', card_id=companion.id, ability=0)
    roundtrip(s)
    cold_refusal(s, cards, companion, tmp_path)


def test_unknown_physical_starting_card_printing_refuses_instead_of_omitting_it(cards):  # noqa: F811
    from app.game.state import GameState

    s, companion = setup(cards)
    data = s.state.model_dump(mode='json')
    unknown = next(c for c in data['cards'].values() if c['name'] == 'Walking Ballista')
    unknown['card_id'] = None
    restored = GameState.model_validate(data)
    problem = casting.companion_problem(restored, 'p1', restored.cards[companion.id], cards)
    assert problem is not None and "doesn't know every card" in problem


def test_native_copy_of_opponents_repeated_cost_preserves_legal_original_deck_in_cold(cards, tmp_path):  # noqa: F811
    import subprocess
    import sys
    from pathlib import Path

    s, companion = setup(cards, legal_copy=True)
    target = put(s, 'Serra Angel', 'battlefield', 'p2')
    source = put(s, 'Clone', 'hand')
    original = source.card_id
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            assert any(o.id == target.id for o in d.options)
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
            break
        act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('Actual Clone did not reach its native entering choice')
    answer(s)
    current = s.state.cards[source.id]
    assert current.card_id == original and current.copy_of is None
    assert Plan(s.state, 'p1', cards, None).ch(current).mana_cost == '{3}{W}{W}'
    assert casting.companion_problem(s.state, 'p1', companion, cards) is None
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    roundtrip(s)
    path = tmp_path / 'legal-native-copy.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import casting
path,database,companion=sys.argv[1:]
repo=CardRepository(Path(database),ImageStore(Path(database).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
s.view('p2')
assert casting.companion_problem(s.state,'p1',s.state.cards[companion],repo) is None
s.perform('p1',{'type':'activate_ability','card_id':companion,'ability':0})
assert s.state.cards[companion].zone=='p1:hand'
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), companion.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr
