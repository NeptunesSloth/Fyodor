"""Resolving protection qualities bind actual source provenance and choices."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, protection, targets
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import answer, priority
from tests.test_rules_source_quality_protection import ch, spell
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/source_quality_grant_cards.json'
NAMES = ['Crypsis', 'Devoted Caretaker', 'Floating Shield', "Dominaria's Judgment", 'Lord of the Nazgûl']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='sqg', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())] + ['Island', 'Forest', 'Plains', 'Mountain', 'Swamp']
    s = three(cards, names, names, names)
    hold(s)
    return s


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_full(cards, name):
    r = coverage.of_card_data(cards.resolve(name))
    assert r.level == 'FULL', r.manual_parts


def test_crypsis_untaps_and_protects_from_each_opponents_creatures(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[bear.id], tapped=True)
    spell(s, 'Crypsis', {'U': 1, 'C': 1}, [bear.id])
    assert not s.state.cards[bear.id].tapped
    for player in ('p1', 'p2', 'p3'):
        creature = put(s, 'Grizzly Bears', 'battlefield', player)
        plan = Plan(s.state, player, s.cards, None)
        assert protection.protected_from(ch(s, bear), targets.source_of(plan, creature.id)) == (player != 'p1')
    roundtrip(s)
    act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p2')
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Creature', types=frozenset({'Creature'}), object_controller='p2'))
    assert protection.protected_from(ch(s, bear), Characteristics(name='Creature', types=frozenset({'Creature'}), object_controller='p1'))
    assert protection.protected_from(ch(s, bear), Characteristics(name='Creature card in graveyard', types=frozenset({'Creature'}), object_owner='p3'))
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Artifact', types=frozenset({'Artifact'}), object_controller='p2'))


def test_caretaker_actual_activation_protects_spells_not_abilities(cards):
    s = setup(cards)
    caretaker = put(s, 'Devoted Caretaker', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='activate_ability', card_id=caretaker.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[caretaker.id].tapped
    for kind in ('Instant', 'Sorcery'):
        assert protection.protected_from(ch(s, bear), Characteristics(name='Spell', types=frozenset({kind}), is_spell=True))
        assert not protection.protected_from(ch(s, bear), Characteristics(name='Ability source', types=frozenset({kind}), is_ability=True))
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Creature', types=frozenset({'Creature'}), is_spell=True))
    roundtrip(s)


def test_shield_sacrificed_source_retains_exact_chosen_color(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    shield = spell(s, 'Floating Shield', {'W': 1, 'C': 2}, [bear.id])
    while s.state.rules.decision:
        answer(s, ['Red'])
        settle(s)
    assert s.state.cards[shield.id].choices.get('Chosen color') == 'Red'
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=shield.id, ability=3, targets=[bear.id])
    assert s.state.cards[shield.id].zone == 'p1:graveyard'
    roundtrip(s)
    settle(s)
    assert protection.protected_from(ch(s, bear), Characteristics(name='Red', colors=frozenset({'R'})))
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Blue', colors=frozenset({'U'})))


def test_judgment_lands_and_recipients_locked_at_resolution(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    plains = put(s, 'Plains', 'battlefield')
    put(s, 'Island', 'battlefield')
    spell(s, "Dominaria's Judgment", {'W': 1, 'C': 2})
    assert protection.protected_from(ch(s, bear), Characteristics(name='White', colors=frozenset({'W'})))
    assert protection.protected_from(ch(s, bear), Characteristics(name='Blue', colors=frozenset({'U'})))
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Green', colors=frozenset({'G'})))
    act(s, 'p1', type='move', card_ids=[plains.id], to={'zone': 'graveyard'})
    put(s, 'Forest', 'battlefield')
    later = put(s, 'Ornithopter', 'battlefield')
    assert protection.protected_from(ch(s, bear), Characteristics(name='White', colors=frozenset({'W'})))
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Green', colors=frozenset({'G'})))
    assert not protection.protected_from(ch(s, later), Characteristics(name='White', colors=frozenset({'W'})))
    roundtrip(s)


def test_caretaker_rejects_real_bolt_but_allows_creature_ability(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    put(s, 'Fervor', 'battlefield')
    caretaker = put(s, 'Devoted Caretaker', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='activate_ability', card_id=caretaker.id, ability=0, targets=[bear.id])
    settle(s)
    priority(s, 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'R': 1})
    with pytest.raises(ActionError, match='legal target'):
        act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[bear.id])
    pyromancer = put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    put(s, 'Fervor', 'battlefield', 'p2')
    act(s, 'p2', type='activate_ability', card_id=pyromancer.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].damage == 1
    roundtrip(s)


def test_shield_returned_new_incarnation_cannot_overwrite_pending_color(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    shield = spell(s, 'Floating Shield', {'W': 1, 'C': 2}, [bear.id])
    answer(s, ['Red'])
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=shield.id, ability=3, targets=[bear.id])
    oid = s.state.rules.stack[next(cid for cid in s.state.zones['stack'])].source_object
    assert s.state.rules.lki[oid].choices['Chosen color'] == 'Red'
    put(s, 'Leyline of Anticipation', 'battlefield')
    act(s, 'p1', type='move', card_ids=[shield.id], to={'zone': 'hand'})
    # A new physical incarnation choosing Blue must not change the pending Red grant.
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1, 'C': 2})
    act(s, 'p1', type='cast_spell', card_id=shield.id, targets=[bear.id])
    settle(s)
    answer(s, ['Blue'])
    settle(s)
    act(s, 'p1', type='move', card_ids=[shield.id], to={'zone': 'exile'})
    assert protection.protected_from(ch(s, bear), Characteristics(name='Red', colors=frozenset({'R'})))
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Blue', colors=frozenset({'U'})))
    roundtrip(s)


def test_judgment_dual_land_and_dryad_current_subtypes(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Sacred Foundry', 'battlefield')
    spell(s, "Dominaria's Judgment", {'W': 1, 'C': 2})
    for color in 'WR':
        assert protection.protected_from(ch(s, bear), Characteristics(name='Source', colors=frozenset(color)))
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Source', colors=frozenset('B')))
    put(s, 'Dryad of the Ilysian Grove', 'battlefield')
    spell(s, "Dominaria's Judgment", {'W': 1, 'C': 2})
    for color in 'WUBRG':
        assert protection.protected_from(ch(s, bear), Characteristics(name='Source', colors=frozenset(color)))
    roundtrip(s)


def tempt(s, bearer, player='p2'):
    spell(s, 'Dreadful as the Storm', {'U': 1, 'C': 2}, [bearer.id], player=player)
    if s.state.rules.decision:
        answer(s, [bearer.id])
    assert s.state.rules.ring_bearers[player] == s.state.rules.object_id(bearer.id)


def test_nazgul_live_ring_designation_and_source_lki(cards):
    s = setup(cards)
    lord = put(s, 'Lord of the Nazgûl', 'battlefield')
    # A real Wraith token is produced by the fully native cast trigger.
    spell(s, 'Lightning Bolt', {'R': 1}, ['p3'])
    wraith = next(c for c in s.state.cards.values() if c.name == 'Wraith' and c.zone == 'p1:battlefield')
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    second = put(s, 'Goblin Arsonist', 'battlefield', 'p2')
    tempt(s, first)
    plan = Plan(s.state, 'p1', cards, None)
    assert protection.protected_from(ch(s, wraith), targets.source_of(plan, first.id))
    ordinary = put(s, 'Grizzly Bears', 'battlefield')
    assert protection.protected_from(ch(s, lord), targets.source_of(plan, first.id))  # Lord is itself a Wraith
    assert not protection.protected_from(ch(s, ordinary), targets.source_of(plan, first.id))
    tempt(s, second)
    plan = Plan(s.state, 'p1', cards, None)
    assert not protection.protected_from(ch(s, wraith), targets.source_of(plan, first.id))
    assert protection.protected_from(ch(s, wraith), targets.source_of(plan, second.id))
    oid = s.state.rules.object_id(second.id)
    act(s, 'p1', type='move', card_ids=[second.id], to={'zone': 'graveyard'})
    # The dead Arsonist's real trigger may target the Wraith, but damage is prevented using its exact departing designation.
    if s.state.rules.decision:
        answer(s, [wraith.id])
    settle(s)
    assert not s.state.cards[wraith.id].damage
    plan = Plan(s.state, 'p1', cards, None)
    assert targets.source_of(plan, second.id, object_id=oid).object_ring_bearer
    assert not targets.source_of(plan, second.id).object_ring_bearer
    roundtrip(s)


def test_caretaker_prevents_real_untargeted_instant_sorcery_damage(cards):
    s = setup(cards)
    put(s, 'Fervor', 'battlefield')
    caretaker = put(s, 'Devoted Caretaker', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='activate_ability', card_id=caretaker.id, ability=0, targets=[bear.id])
    settle(s)
    spell(s, 'Pyroclasm', {'R': 1, 'C': 1})
    assert s.state.cards[bear.id].zone == 'p1:battlefield' and not s.state.cards[bear.id].damage
    assert s.state.cards[other.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_sacrificed_shield_choice_resolves_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    shield = spell(s, 'Floating Shield', {'W': 1, 'C': 2}, [bear.id])
    answer(s, ['Red'])
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=shield.id, ability=3, targets=[bear.id])
    oid = next(iter(s.state.rules.stack.values())).source_object
    assert s.state.rules.lki[oid].choices == {'Chosen color': 'Red'}
    path = tmp_path / 'shield-paid.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import protection
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan
path, database, bear = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
for _ in range(15):
    assert s.state.rules.decision is None
    if not s.state.zones['stack']:
        break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('shield activation did not finish')
ch = Plan(s.state, 'p1', repo, None).ch(s.state.cards[bear])
assert protection.protected_from(ch, Characteristics(name='Red', colors=frozenset('R')))
assert not protection.protected_from(ch, Characteristics(name='Blue', colors=frozenset('U')))
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), bear.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
    roundtrip(s)


def test_crypsis_native_enemy_creature_ability_is_illegal_and_expires(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Crypsis', {'U': 1, 'C': 1}, [bear.id])
    put(s, 'Fervor', 'battlefield', 'p2')
    enemy = put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    priority(s, 'p2')
    with pytest.raises(ActionError, match='legal target'):
        act(s, 'p2', type='activate_ability', card_id=enemy.id, ability=0, targets=[bear.id])
    # Enemy noncreature spells have no forbidden quality.
    spell(s, 'Giant Growth', {'G': 1}, [bear.id], player='p2')
    assert ch(s, bear).pt == (5, 5)
    # Official Crypsis ruling: the new controller's own creatures are now allowed.
    act(s, 'p1', type='set_controller', card_ids=[bear.id], player='p2')
    priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=enemy.id, ability=0, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].damage == 1
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', s.state.turn.number + 1)
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Creature', types=frozenset({'Creature'}), object_controller='p2'))
    roundtrip(s)


def test_nazgul_designation_not_copied_and_control_change_removes_it(cards):
    s = setup(cards)
    lord = put(s, 'Lord of the Nazgûl', 'battlefield')
    first = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    tempt(s, first)
    put(s, 'Leyline of Anticipation', 'battlefield')
    clone = spell(s, 'Clone', {'U': 1, 'C': 3})
    answer(s, [first.id])
    plan = Plan(s.state, 'p1', cards, None)
    assert not targets.source_of(plan, clone.id).object_ring_bearer
    assert not protection.protected_from(ch(s, lord), targets.source_of(plan, clone.id))
    assert protection.protected_from(ch(s, lord), targets.source_of(plan, first.id))
    act(s, 'p1', type='set_controller', card_ids=[first.id], player='p3')
    plan = Plan(s.state, 'p1', cards, None)
    assert not targets.source_of(plan, first.id).object_ring_bearer
    assert not protection.protected_from(ch(s, lord), targets.source_of(plan, first.id))
    roundtrip(s)


def test_caretaker_prevents_real_instant_damage_redirected_by_pariah(cards):
    s = setup(cards)
    put(s, 'Fervor', 'battlefield')
    caretaker = put(s, 'Devoted Caretaker', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Pariah', {'W': 1, 'C': 2}, [bear.id])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'W': 1})
    act(s, 'p1', type='activate_ability', card_id=caretaker.id, ability=0, targets=[bear.id])
    settle(s)
    spell(s, 'Lightning Bolt', {'R': 1}, ['p1'], player='p2')
    assert s.state.players['p1'].life == 40
    assert s.state.cards[bear.id].zone == 'p1:battlefield' and not s.state.cards[bear.id].damage
    roundtrip(s)


def test_crypsis_actual_source_controller_separate_from_trigger_controller(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Crypsis', {'U': 1, 'C': 1}, [bear.id])
    bowmasters = spell(s, 'Orcish Bowmasters', {'B': 1, 'C': 1}, finish=False)
    for _ in range(12):
        if s.state.rules.decision:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    assert s.state.rules.stack
    act(s, 'p1', type='set_controller', card_ids=[bowmasters.id], player='p2')
    roundtrip(s)
    settle(s)
    assert not any(c.name == 'Orc Army' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    assert not s.state.cards[bear.id].damage
    assert not s.state.rules.decision
    roundtrip(s)


def test_dynamic_opponent_quality_requires_source_controller_or_owner(cards):
    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Crypsis', {'U': 1, 'C': 1}, [bear.id])
    assert not protection.protected_from(ch(s, bear), Characteristics(name='Unknown creature', types=frozenset({'Creature'})))
    assert protection.protected_from(ch(s, bear), Characteristics(name='Owned creature card', types=frozenset({'Creature'}), object_owner='p2'))


def test_stolen_bowmasters_source_rechecks_quality_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell(s, 'Crypsis', {'U': 1, 'C': 1}, [bear.id])
    bowmasters = spell(s, 'Orcish Bowmasters', {'B': 1, 'C': 1}, finish=False)
    for _ in range(12):
        if s.state.rules.decision:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    act(s, 'p1', type='set_controller', card_ids=[bowmasters.id], player='p2')
    path = tmp_path / 'stolen-source-trigger.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, bear = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
for _ in range(15):
    assert s.state.rules.decision is None
    if not s.state.zones['stack']:
        break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
else:
    raise AssertionError('trigger did not finish')
assert not any(c.name == 'Orc Army' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
assert not s.state.cards[bear].damage
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), bear.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr
