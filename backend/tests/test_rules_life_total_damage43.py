"""Native life doubling and pre-damage Phyrexian Unlife eligibility."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import attack, damage
from tests.test_rules_conditional_prevention import cast as begin_cast
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/life_total_damage43_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(DATA):
        base[row['name']] = card(row['name'], number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.fixture(autouse=True)
def native_scripts():
    scripts._cached.cache_clear()
    yield
    scripts._cached.cache_clear()


def game(cards):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    for player in ('p1', 'p2', 'p3'):
        act(s, player, type='set_prefs', auto_resolve_own_triggers='off', hold_priority=True)
    return s


def resolved_one(s, name, targets=(), pid='p1', **kw):
    spell = begin_cast(s, name, targets, pid=pid, resolve=False, **kw)
    for _ in range(20):
        if spell.id not in s.state.zones['stack']:
            return spell
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('spell did not resolve')


def mantle_combat(s, creature='Grizzly Bears', controller='p1', *, archive=False):
    bear = put(s, creature, 'battlefield', controller)
    if archive:
        put(s, "Alhammarret's Archive", 'battlefield')
    mantle = cast(s, 'Celestial Mantle', targets=[bear.id])
    assert Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[bear.id]).pt == ((5, 6) if creature == 'Vampire Nighthawk' else (5, 5))
    start(s, turn=4 if controller == 'p1' else 5)
    attack(s, [bear], pid=controller, target='p2' if controller == 'p1' else 'p1', turn=4 if controller == 'p1' else 5)
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'combat_damage')
    assert any(entry.event for entry in s.state.rules.stack.values())
    return bear, mantle


def test_mantle_aura_controller_does_not_receive_opponent_creature_life(cards):
    s = game(cards)
    mantle_combat(s, controller='p2')
    settle(s)
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [35, 80, 40]
    roundtrip(s)


@pytest.mark.parametrize('archive', [False, True])
def test_mantle_lifelink_is_applied_before_doubling_and_gain_replacement(cards, archive):
    s = game(cards)
    mantle_combat(s, 'Vampire Nighthawk', archive=archive)
    assert s.state.players['p1'].life == (50 if archive else 45)
    settle(s)
    assert s.state.players['p1'].life == (150 if archive else 90)
    roundtrip(s)


def test_mantle_current_controller_is_read_after_actual_control_change(cards):
    s = game(cards)
    bear, _ = mantle_combat(s)
    resolved_one(s, 'Act of Aggression', [bear.id], pid='p2', life_symbols=[])
    assert s.state.cards[bear.id].controller == 'p2'
    settle(s)
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [40, 70, 40]
    roundtrip(s)


@pytest.mark.parametrize('life', [-4, 0, 14])
def test_mantle_signed_life_uses_native_gain_or_loss(cards, life):
    s = game(cards)
    put(s, 'Platinum Angel', 'battlefield')
    bear, _ = mantle_combat(s)
    act(s, 'p1', type='life', player='p1', delta=life - s.state.players['p1'].life)
    assert s.state.players['p1'].life == life
    settle(s)
    assert s.state.players['p1'].life == life * 2
    assert s.state.cards[bear.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_unlife_positive_crossing_does_not_convert_that_damage_to_poison(cards):
    s = game(cards)
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-37)
    cast(s, 'Lava Axe', ['p1'])
    assert s.state.players['p1'].life == -2 and not s.state.players['p1'].resources.get('poison')
    assert 'p1' not in s.state.rules.lost
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == -2 and s.state.players['p1'].resources['poison'] == 3
    roundtrip(s)


def test_unlife_destruction_at_nonpositive_life_causes_native_loss(cards):
    s = game(cards)
    source = cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-40)
    assert 'p1' not in s.state.rules.lost
    cast(s, 'Disenchant', [source.id], pid='p2')
    assert 'p1' in s.state.rules.lost
    roundtrip(s)


def test_unlife_poison_still_loses_and_explicit_life_loss_stays_life_loss(cards):
    s = game(cards)
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-40)
    cast(s, 'Sign in Blood', ['p1'])
    assert s.state.players['p1'].life == -2 and not s.state.players['p1'].resources.get('poison')
    for _ in range(4):
        cast(s, 'Lightning Bolt', ['p1'], pid='p2')
        if 'p1' in s.state.rules.lost:
            break
    assert 'p1' in s.state.rules.lost
    roundtrip(s)


def test_mantle_also_triggers_for_combat_damage_redirected_to_its_source_controller(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, 'Celestial Mantle', [bear.id])
    start(s)
    cast(s, "Captain's Maneuver", ['p2', 'p1'], x_value=2, target_counts=[1, 1])
    attack(s, [bear])
    to_phase(s, 'combat_damage')
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [38, 37, 40]
    events = [entry.event for entry in s.state.rules.stack.values() if entry.event]
    assert len(events) == 2 and {tuple(event.players) for event in events} == {('p1',), ('p2',)}
    settle(s)
    assert s.state.players['p1'].life == 152
    roundtrip(s)


@pytest.mark.parametrize('departed', [False, True])
def test_mantle_original_creature_survives_aura_move_and_uses_lki_if_it_dies(cards, departed):
    s = game(cards)
    other = put(s, 'Runeclaw Bear', 'battlefield', 'p3')
    bear, mantle = mantle_combat(s)
    resolved_one(s, 'Aura Finesse', [mantle.id, other.id], target_counts=[1, 1])
    assert s.state.cards[mantle.id].attached_to == other.id
    if departed:
        resolved_one(s, 'Act of Aggression', [bear.id], pid='p2', life_symbols=[])
        resolved_one(s, 'Murder', [bear.id])
        assert s.state.cards[bear.id].zone == 'p1:graveyard'
    settle(s)
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == ([40, 70, 40] if departed else [80, 35, 40])
    roundtrip(s)


def test_unlife_simultaneous_sources_all_use_the_positive_starting_life(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    one = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    two = put(s, 'Runeclaw Bear', 'battlefield', 'p2')
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-39)
    start(s, turn=5)
    attack(s, [one, two], pid='p2', target='p1', turn=5)
    to_phase(s, 'combat_damage')
    settle(s)
    assert s.state.players['p1'].life == -3 and not s.state.players['p1'].resources.get('poison')
    roundtrip(s)


@pytest.mark.parametrize('life', [0, 1])
def test_unlife_preview_and_commit_preserve_damage_lifelink_and_source_infect(cards, life):
    from app.rules import combat, replace
    from tests.test_rules_wave30m_durations import to_phase

    s = game(cards)
    attacker = put(s, 'Vampire Nighthawk', 'battlefield', 'p2')
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=life - 40)
    start(s, turn=5)
    attack(s, [attacker], pid='p2', target='p1', turn=5)
    to_phase(s, 'declare_blockers')
    plan = Plan(s.state, 'p1', s.cards, None)
    events = combat.combat_damage_events(plan, combat.compute_combat_damage(plan, 'only'))
    before = s.state.model_dump_json()
    out = replace.damage_outcome(plan, events, answers={}, order=None, ask=False)
    assert isinstance(out, replace.DamageOutcome)
    assert out.poison.get('p1', 0) == (2 if life == 0 else 0)
    assert out.players.get('p1', 0) == (0 if life == 0 else 2)
    assert s.state.model_dump_json() == before
    to_phase(s, 'combat_damage')
    settle(s)
    assert s.state.players['p1'].life == (0 if life == 0 else -1)
    assert s.state.players['p1'].resources.get('poison', 0) == (2 if life == 0 else 0)
    assert s.state.players['p2'].life == 42
    assert 'infect' not in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[attacker.id]).keywords
    roundtrip(s)


def test_unlife_existing_infect_at_positive_life_and_poison_replacement(cards):
    s = game(cards)
    elf = put(s, 'Glistener Elf', 'battlefield', 'p2')
    cast(s, 'Phyrexian Unlife')
    start(s, turn=5)
    attack(s, [elf], pid='p2', target='p1', turn=5)
    damage(s)
    assert s.state.players['p1'].life == 40 and s.state.players['p1'].resources['poison'] == 1
    put(s, 'Solemnity', 'battlefield')
    act(s, 'p1', type='life', player='p1', delta=-40)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.players['p1'].life == 0 and s.state.players['p1'].resources['poison'] == 1
    roundtrip(s)


def test_unlife_prevention_still_prevents_damage_and_lifelink(cards):
    s = game(cards)
    attacker = put(s, 'Vampire Nighthawk', 'battlefield', 'p2')
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-40)
    start(s, turn=5)
    attack(s, [attacker], pid='p2', target='p1', turn=5)
    cast(s, 'Holy Day')
    damage(s)
    assert s.state.players['p1'].life == 0 and not s.state.players['p1'].resources.get('poison')
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_unlife_does_not_turn_poison_into_archons_ordinary_life_result_filter(cards):
    s = game(cards)
    cast(s, 'Archon of Coronation')
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-40)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.table.monarch == 'p1'
    assert s.state.players['p1'].life == 0 and s.state.players['p1'].resources['poison'] == 3
    roundtrip(s)


def test_unlife_does_not_prevent_empty_library_loss(cards):
    s = game(cards)
    cast(s, 'Phyrexian Unlife')
    spell = put(s, 'Sign in Blood', 'hand')
    library = list(s.state.zones['p1:library'])
    act(s, 'p1', type='move', card_ids=library, to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='life', player='p1', delta=-40)
    from tests.test_rules_bandmate_references import mana

    mana(s, B=3)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=['p1'])
    settle(s)
    assert 'p1' in s.state.rules.lost
    roundtrip(s)


def test_unlife_positive_life_payment_fails_but_zero_payment_succeeds(cards):
    from app.game.errors import ActionError
    from tests.test_rules_characteristic_recipes39 import activate

    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    greed = put(s, 'Greed', 'battlefield')
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-40)
    with pytest.raises(ActionError, match='life|pay'):
        activate(s, greed, 'Draw a card')
    cast(s, 'Hatred', [bear.id], x_value=0)
    assert s.state.rules.decision is None and s.state.players['p1'].life == 0
    assert 'p1' not in s.state.rules.lost
    roundtrip(s)


@pytest.mark.parametrize('kind', ['mantle', 'unlife'])
def test_saved_life_total_or_damage_counter_choice_resumes_fresh(cards, tmp_path, kind):
    import subprocess
    import sys

    s = game(cards)
    if kind == 'mantle':
        other = put(s, 'Runeclaw Bear', 'battlefield', 'p3')
        bear, mantle = mantle_combat(s)
        resolved_one(s, 'Aura Finesse', [mantle.id, other.id], target_counts=[1, 1])
        assert s.state.cards[mantle.id].attached_to == other.id
        extra = bear.id
    else:
        put(s, 'Winding Constrictor', 'battlefield')
        put(s, 'Vorinclex, Monstrous Raider', 'battlefield', 'p2')
        cast(s, 'Phyrexian Unlife')
        act(s, 'p1', type='life', player='p1', delta=-40)
        cast(s, 'Lightning Bolt', ['p1'], pid='p2')
        assert s.state.rules.decision is not None
        assert any('Winding Constrictor' in option.label for option in s.state.rules.decision.options)
        assert s.state.players['p1'].life == 0 and not s.state.players['p1'].resources.get('poison')
        extra = ''
    saved = tmp_path / (kind + '.json')
    saved.write_text(s.state.model_dump_json())
    worker = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_declaration_requirements33 import cast
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
s.view('p3')
if sys.argv[3]=='mantle':
 cast(s,'Murder',[sys.argv[4]])
 assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
 assert [s.state.players[p].life for p in ('p1','p2','p3')]==[80,35,40]
else:
 d=s.state.rules.decision
 option=next(o.id for o in d.options if 'Winding Constrictor' in o.label)
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[option]});settle(s)
 assert s.state.rules.decision is None
 assert s.state.players['p1'].life==0 and s.state.players['p1'].resources['poison']==8
 assert 'p1' not in s.state.rules.lost
roundtrip(s);repo.close()
"""
    result = subprocess.run([sys.executable, '-c', worker, str(saved), str(cards.db_path), kind, extra],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_mantle_does_not_trigger_from_its_creatures_noncombat_damage(cards):
    from tests.test_rules_characteristic_recipes39 import activate

    s = game(cards)
    pyro = put(s, 'Prodigal Pyromancer', 'battlefield')
    cast(s, 'Celestial Mantle', [pyro.id])
    start(s)
    activate(s, pyro, '1 damage', targets=['p2'])
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [40, 39, 40]
    assert not s.state.zones['stack']
    roundtrip(s)


def test_unlife_does_not_convert_damage_to_its_controllers_creature(cards):
    s = game(cards)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-40)
    cast(s, 'Lightning Bolt', [bear.id], pid='p2')
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].life == 0 and not s.state.players['p1'].resources.get('poison')
    roundtrip(s)


@pytest.mark.parametrize('first,expected', [('Winding Constrictor', 8), ('Vorinclex', 7)])
def test_unlife_uses_native_poison_replacement_order(cards, first, expected):
    s = game(cards)
    put(s, 'Winding Constrictor', 'battlefield')
    put(s, 'Vorinclex, Monstrous Raider', 'battlefield', 'p2')
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-40)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    decision = s.state.rules.decision
    assert decision is not None
    option = next(option.id for option in decision.options if first in option.label)
    act(s, decision.player, type='choose', decision_id=decision.id, option_ids=[option])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == 0 and s.state.players['p1'].resources['poison'] == expected
    assert 'p1' not in s.state.rules.lost
    roundtrip(s)


@pytest.mark.parametrize('name', ['Celestial Mantle', 'Phyrexian Unlife'])
def test_whole_canonical_life_cards_supported(cards, name):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


def test_unlife_preserves_native_commander_damage_and_lifelink(cards):
    s = game(cards)
    commander = put(s, "Atraxa, Praetors' Voice", 'battlefield', 'p2')
    assert commander.commander_key is not None
    cast(s, 'Phyrexian Unlife')
    act(s, 'p1', type='life', player='p1', delta=-40)
    start(s, turn=5)
    attack(s, [commander], pid='p2', target='p1', turn=5)
    damage(s)
    assert s.state.players['p1'].life == 0 and s.state.players['p1'].resources['poison'] == 4
    assert sum(s.state.players['p1'].commander_damage.values()) == 4
    assert s.state.players['p2'].life == 44
    roundtrip(s)
