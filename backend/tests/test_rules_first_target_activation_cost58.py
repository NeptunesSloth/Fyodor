"""Native first qualifying activation cost history and actual selected targets."""
import pytest

from app.game.errors import ActionError
from app.rules import mana_units
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_targeting_sources77 import setup


@pytest.fixture
def cards(settings):
    import json
    from pathlib import Path

    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import card, fixture_cards
    base = {c["name"]: c for c in fixture_cards()}
    for filename in ["targeting_sources77_cards.json", "first_target_activation_cost58_supports.json"]:
        for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / filename).read_text())):
            base[c["name"]] = card(c["name"], number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def equip(s, gear, target):
    act(s, 'p1', type='activate_ability', card_id=gear.id, ability=2, targets=[target.id], sources=[])
    settle(s)


def test_first_qualifying_equip_reduced_second_not(cards):
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    equip(s, gear, bear)
    assert gear.attached_to == bear.id and not mana_units.visible_pool(s.state, 'p1')
    with pytest.raises(ActionError):
        equip(s, gear, elf)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    equip(s, gear, elf)
    assert gear.attached_to == elf.id and not mana_units.visible_pool(s.state, 'p1')
    roundtrip(s)


def test_prior_qualifying_activation_before_hojo_enters_counts(cards):
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    equip(s, gear, bear)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    with pytest.raises(ActionError):
        equip(s, gear, elf)
    assert gear.attached_to == bear.id
    roundtrip(s)


def test_legacy_unknown_current_turn_history_cannot_guess_first(cards):
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    s.state.rules.target_activation_history_turn = None
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        equip(s, gear, bear)
    assert s.state.model_dump_json() == before


def test_own_creature_is_second_of_actual_x_multiple_targets(cards):
    from app.rules.plan import Plan
    from tests.test_rules_table_activation_modifiers52 import game
    s = game(cards, ['Professor Hojo', 'Magus of the Candelabra', 'Treetop Village', 'Forest'])
    put(s, 'Professor Hojo', 'battlefield')
    magus = put(s, 'Magus of the Candelabra', 'battlefield')
    tree = put(s, 'Treetop Village', 'battlefield')
    forest = put(s, 'Forest', 'battlefield')
    s.state.rules.controlled_since[magus.id].turn = 0
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(tree).abilities if a.kind == 'activated')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=tree.id, ability=ability.index, sources=[])
    settle(s)
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(magus).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=magus.id, ability=ability.index, x_value=2,
        targets=[forest.id, tree.id], target_counts=[2], sources=[])
    settle(s)
    assert not tree.tapped and not mana_units.visible_pool(s.state, 'p1')
    assert s.state.rules.once_per_turn['activated:p1:controlled_creature_target'] == s.state.turn.number
    roundtrip(s)


def test_target_sacrificed_as_payment_still_consumes_first_qualification(cards):
    from app.rules.plan import Plan
    from tests.test_rules_table_activation_modifiers52 import game
    s = game(cards, ['Professor Hojo', 'Attrition', 'Grizzly Bears', 'Silver-Inlaid Dagger'])
    hojo = put(s, 'Professor Hojo', 'battlefield')
    source = put(s, 'Attrition', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[bear.id],
        cost_choices=[{'component': 1, 'cards': [bear.id]}], sources=[])
    settle(s)
    assert bear.zone == 'p1:graveyard'
    with pytest.raises(ActionError):
        equip(s, gear, hojo)
    assert s.state.rules.once_per_turn['activated:p1:controlled_creature_target'] == s.state.turn.number
    roundtrip(s)


def test_tax_paid_before_first_target_reduction(cards):
    from tests.test_rules_table_activation_modifiers52 import game
    s = game(cards, ['Professor Hojo', 'Grizzly Bears', 'Silver-Inlaid Dagger', 'Suppression Field'])
    put(s, 'Professor Hojo', 'battlefield')
    put(s, 'Suppression Field', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    with pytest.raises(ActionError):
        equip(s, gear, bear)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    equip(s, gear, bear)
    assert gear.attached_to == bear.id and not mana_units.visible_pool(s.state, 'p1')
    roundtrip(s)


def test_colored_mana_is_not_reduced(cards):
    from app.rules.plan import Plan
    from tests.test_rules_table_activation_modifiers52 import game
    s = game(cards, ['Professor Hojo', 'Captain of the Mists', 'Grizzly Bears'])
    put(s, 'Professor Hojo', 'battlefield')
    source = put(s, 'Captain of the Mists', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    s.state.rules.controlled_since[source.id].turn = 0
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[bear.id], sources=[])
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[bear.id], sources=[])
    settle(s)
    assert source.tapped and not mana_units.visible_pool(s.state, 'p1')
    roundtrip(s)


def test_opponents_hojo_does_not_reduce_own_activation(cards):
    from tests.test_rules_table_activation_modifiers52 import game
    s = game(cards, ['Grizzly Bears', 'Silver-Inlaid Dagger'], opponents=['Professor Hojo'])
    put(s, 'Professor Hojo', 'battlefield', pid='p2')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        equip(s, gear, bear)
    assert s.state.model_dump_json() == before


def test_floored_reduction_precedes_unrestricted_first_target_cut(cards):
    from app.rules.plan import Plan
    from tests.test_rules_table_activation_modifiers52 import game
    s = game(cards, ['Professor Hojo', 'Zirda, the Dawnwaker', 'Staff of Domination', 'Grizzly Bears'])
    put(s, 'Professor Hojo', 'battlefield')
    put(s, 'Zirda, the Dawnwaker', 'battlefield')
    source = put(s, 'Staff of Domination', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.text.startswith('{3}'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[bear.id], sources=[])
    settle(s)
    assert source.tapped and not mana_units.visible_pool(s.state, 'p1')
    roundtrip(s)


@pytest.mark.parametrize('legacy', [False, True])
def test_true_cold_complete_or_unknown_first_activation(cards, tmp_path, legacy):
    import subprocess
    import sys
    from pathlib import Path

    from app.rules import first_target_activation_cost58
    s, source, bear, elf = setup(cards, 'Professor Hojo')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    data = s.state.model_dump(mode='json')
    if legacy:
        data['rules'].pop('target_activation_history_turn')
    import json
    saved = tmp_path/'game.json'
    saved.write_text(json.dumps(data))
    code = '''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
a=dict(type='activate_ability',card_id=sys.argv[3],ability=2,targets=[sys.argv[4]],sources=[])
if sys.argv[5]=='True':
 before=s.state.model_dump_json()
 try:act(s,'p1',**a)
 except ActionError:pass
 else:raise AssertionError('Unknown historical activation guessed free first cost')
 assert s.state.model_dump_json()==before
else:
 act(s,'p1',**a);settle(s)
 assert s.state.cards[sys.argv[3]].attached_to==sys.argv[4]
 roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), gear.id, bear.id, str(legacy)],
                            cwd=Path(first_target_activation_cost58.__file__).resolve().parents[2], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_own_hojo_cannot_reduce_during_opponents_turn(cards):
    from app.rules.plan import Plan
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_table_activation_modifiers52 import game
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards, ['Professor Hojo', 'Staff of Domination', 'Grizzly Bears'])
    put(s, 'Professor Hojo', 'battlefield')
    source = put(s, 'Staff of Domination', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', 5)
    wait_priority(s, 'p1')
    assert s.state.turn.active_player == 'p2'
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.text.startswith('{3}'))
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[bear.id], sources=[])
    assert not source.tapped


def test_true_cold_locked_payment_freezes_original_target_qualification(cards, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    from app.rules import first_target_activation_cost58
    from app.rules.plan import Plan
    from tests.test_rules_table_activation_modifiers52 import game
    s = game(cards, ['Professor Hojo', 'Staff of Domination', 'Grizzly Bears', "Ashnod's Altar", 'Silver-Inlaid Dagger'])
    hojo = put(s, 'Professor Hojo', 'battlefield')
    source = put(s, 'Staff of Domination', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    altar = put(s, "Ashnod's Altar", 'battlefield')
    gear = put(s, 'Silver-Inlaid Dagger', 'battlefield')
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.text.startswith('{3}'))
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=[bear.id])
    decision = s.state.rules.decision
    assert decision.resume['step'] == 'pay_mana'
    saved = tmp_path/'payment.json'
    saved.write_text(s.state.model_dump_json())
    code = '''
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
act(s,'p1',type='activate_ability',card_id=sys.argv[3],ability=0,cost_choices=[{'component':0,'cards':[sys.argv[4]]}])
assert s.state.rules.decision is None and s.state.cards[sys.argv[4]].zone=='p1:graveyard'
assert s.state.rules.once_per_turn['activated:p1:controlled_creature_target']==s.state.turn.number
settle(s)
try:act(s,'p1',type='activate_ability',card_id=sys.argv[5],ability=2,targets=[sys.argv[6]],sources=[])
except ActionError:pass
else:raise AssertionError('Target lost during payment wrongly restored first discount')
roundtrip(s)
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), altar.id, bear.id, gear.id, hojo.id],
                            cwd=Path(first_target_activation_cost58.__file__).resolve().parents[2], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
