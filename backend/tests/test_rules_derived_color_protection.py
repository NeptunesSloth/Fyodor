"""Derived colors are live for static grants and fixed for resolved grants (611.2c)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, protection
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import answer, priority
from tests.test_rules_wave30m_durations import three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = Path(__file__).parent / 'fixtures/derived_color_protection_cards.json'
NAMES = ['Éowyn, Fearless Knight', 'Samite Elder', 'Earnest Fellowship', 'Empty-Shrine Kannushi', 'Pledge of Loyalty', 'Opal Titan']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='dcp', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())] + ['Island']
    s = three(cards, names, names, names)
    hold(s)
    return s


def ch(s, c):
    return Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[c.id])


def qualities(s, c):
    return {color for color in 'WUBRG' if protection.protected_from(ch(s, c), Characteristics(name='Source', colors=frozenset(color)))}


def spell(s, name, mana, target=(), player='p1', finish=True):
    priority(s, player)
    c = put(s, name, 'hand', player)
    act(s, player, type='add_mana', player=player, mana=mana)
    act(s, player, type='cast_spell', card_id=c.id, targets=list(target))
    if finish:
        settle(s)
    return s.state.cards[c.id]


def color(s, c, value):
    lens = put(s, 'Distorting Lens', 'battlefield')
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=lens.id, ability=0, targets=[c.id])
    settle(s)
    answer(s, [value])
    return lens


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_fully_supported(cards, name):
    r = coverage.of_card_data(cards.resolve(name))
    assert r.level == 'FULL', r.manual_parts


def test_earnest_each_creatures_colors_follow_layer_five_and_colorless_has_none(cards):
    s = setup(cards)
    put(s, 'Earnest Fellowship', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Goblin Chainwhirler', 'battlefield', 'p2')
    artifact = put(s, 'Ornithopter', 'battlefield')
    multicolor = put(s, 'Fusion Elemental', 'battlefield', 'p3')
    assert qualities(s, bear) == {'G'} and qualities(s, other) == {'R'} and not qualities(s, artifact)
    assert qualities(s, multicolor) == set('WUBRG')
    color(s, bear, 'Blue')
    assert ch(s, bear).colors == frozenset('U') and qualities(s, bear) == {'U'}
    assert qualities(s, other) == {'R'}
    put(s, 'Humility', 'battlefield')
    assert not qualities(s, bear)  # Later ability loss removes the older protection grant.
    roundtrip(s)


def test_kannushi_union_changes_with_control_and_source_removal(cards):
    s = setup(cards)
    source = put(s, 'Empty-Shrine Kannushi', 'battlefield')
    red = put(s, 'Goblin Chainwhirler', 'battlefield')
    green = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    assert qualities(s, source) == {'W', 'R'}
    act(s, 'p1', type='set_controller', card_ids=[red.id], player='p2')
    assert qualities(s, source) == {'W'}
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    assert qualities(s, source) == {'W', 'R', 'G'}
    act(s, 'p2', type='move', card_ids=[green.id], to={'zone': 'exile'})
    assert qualities(s, source) == {'W', 'R'}
    roundtrip(s)


def test_pledge_uses_aura_controller_colors_and_keeps_only_itself(cards):
    s = setup(cards)
    target = put(s, 'Craw Wurm', 'battlefield', 'p2')
    other_aura = put(s, 'Pacifism', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[other_aura.id], to=target.id)
    pledge = spell(s, 'Pledge of Loyalty', {'W': 1, 'C': 1}, [target.id])
    assert s.state.cards[pledge.id].attached_to == target.id
    assert s.state.cards[other_aura.id].zone == 'p1:graveyard'
    assert qualities(s, target) == {'W'}
    act(s, 'p1', type='set_controller', card_ids=[pledge.id], player='p3')
    red = put(s, 'Goblin Chainwhirler', 'battlefield', 'p3')
    assert qualities(s, target) == {'W', 'R'}
    act(s, 'p3', type='move', card_ids=[red.id], to={'zone': 'exile'})
    assert qualities(s, target) == {'W'}
    roundtrip(s)


def test_samite_target_color_snapshot_recipient_set_and_native_tap_cost(cards):
    s = setup(cards)
    elder = put(s, 'Samite Elder', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=elder.id, ability=0, targets=[target.id])
    settle(s)
    assert s.state.cards[elder.id].tapped
    assert qualities(s, elder) == {'G'} and qualities(s, target) == {'G'}
    color(s, target, 'Blue')
    assert ch(s, target).colors == frozenset('U') and qualities(s, target) == {'G'}
    late = put(s, 'Craw Wurm', 'battlefield')
    assert not qualities(s, late)
    roundtrip(s)


def test_samite_colorless_target_and_illegal_target_do_not_grant_protection(cards):
    s = setup(cards)
    elder = put(s, 'Samite Elder', 'battlefield')
    land = put(s, 'Island', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=elder.id, ability=0, targets=[land.id])
    act(s, 'p1', type='move', card_ids=[land.id], to={'zone': 'exile'})
    settle(s)
    assert not qualities(s, elder)
    roundtrip(s)


def test_eowyn_exiles_greater_power_and_uses_colors_before_exile(cards):
    s = setup(cards)
    target = put(s, 'Craw Wurm', 'battlefield', 'p2')
    weak = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    color(s, target, 'Blue')
    ordinary = put(s, 'Grizzly Bears', 'battlefield')
    source = spell(s, 'Éowyn, Fearless Knight', {'R': 1, 'W': 1, 'C': 2})
    d = s.state.rules.decision
    assert target.id in {o.id for o in d.options} and weak.id not in {o.id for o in d.options}
    answer(s, [target.id])
    assert s.state.cards[target.id].zone == 'p2:exile' and ch(s, target).colors == frozenset('G')
    assert qualities(s, source) == {'U'} and not qualities(s, ordinary)
    roundtrip(s)


def test_eowyn_rechecks_greater_power_after_source_growth(cards):
    s = setup(cards)
    target = put(s, 'Craw Wurm', 'battlefield', 'p2')
    source = spell(s, 'Éowyn, Fearless Knight', {'R': 1, 'W': 1, 'C': 2})
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    spell(s, 'Giant Growth', {'G': 1}, [source.id])
    assert s.state.cards[target.id].zone == 'p2:battlefield'
    assert not qualities(s, source)
    roundtrip(s)


def test_opal_titan_opponent_creature_spell_colors_and_native_animation(cards):
    s = setup(cards)
    source = put(s, 'Opal Titan', 'battlefield')
    to_phase(s, 'main1', turn=2)
    spell(s, 'Grizzly Bears', {'G': 1, 'C': 1}, player='p2')
    assert ch(s, source).types == frozenset({'Creature'})
    assert ch(s, source).pt == (4, 4) and 'Giant' in ch(s, source).subtypes
    assert qualities(s, source) == {'G'}
    roundtrip(s)


def test_opal_titan_countered_creature_still_animates_from_stack_lki(cards):
    s = setup(cards)
    source = put(s, 'Opal Titan', 'battlefield')
    to_phase(s, 'main1', turn=2)
    creature = spell(s, 'Grizzly Bears', {'G': 1, 'C': 1}, player='p2', finish=False)
    spell(s, 'Counterspell', {'U': 2}, [creature.id])
    assert s.state.cards[creature.id].zone == 'p2:graveyard'
    assert ch(s, source).pt == (4, 4) and qualities(s, source) == {'G'}
    roundtrip(s)


def test_samite_colorless_land_target_grants_nothing_but_still_pays_tap(cards):
    s = setup(cards)
    elder = put(s, 'Samite Elder', 'battlefield')
    land = put(s, 'Island', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=elder.id, ability=0, targets=[land.id])
    settle(s)
    assert s.state.cards[elder.id].tapped and not qualities(s, elder)
    roundtrip(s)


def test_samite_uses_color_at_resolution_and_survives_source_departure(cards):
    s = setup(cards)
    elder = put(s, 'Samite Elder', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=elder.id, ability=0, targets=[target.id])
    act(s, 'p1', type='move', card_ids=[elder.id], to={'zone': 'exile'})
    color(s, target, 'Blue')  # Resolves above Elder; helper settles the Elder afterward.
    assert qualities(s, target) == {'U'}
    roundtrip(s)


def test_opal_titan_does_not_trigger_for_own_creature_spell(cards):
    s = setup(cards)
    source = put(s, 'Opal Titan', 'battlefield')
    spell(s, 'Grizzly Bears', {'G': 1, 'C': 1})
    assert ch(s, source).types == frozenset({'Enchantment'}) and ch(s, source).pt is None
    roundtrip(s)


def test_eowyn_pending_color_changed_target_resumes_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    target = put(s, 'Craw Wurm', 'battlefield', 'p2')
    color(s, target, 'Blue')
    source = spell(s, 'Éowyn, Fearless Knight', {'R': 1, 'W': 1, 'C': 2})
    assert s.state.rules.decision is not None
    roundtrip(s)
    saved = tmp_path / 'derived-protection.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, source, target = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
d = s.state.rules.decision
s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [target]})
for _ in range(12):
    if not s.state.zones['stack']:
        break
    s.perform(s.state.rules.priority, {'type': 'pass_priority'})
from app.rules import protection
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan
plan = Plan(s.state, 'p1', repo, None)
assert s.state.cards[target].zone == 'p2:exile'
assert plan.ch(s.state.cards[target]).colors == frozenset('G')
assert protection.protected_from(plan.ch(s.state.cards[source]), Characteristics(name='Blue source', colors=frozenset('U')))
assert not protection.protected_from(plan.ch(s.state.cards[source]), Characteristics(name='Green source', colors=frozenset('G')))
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, target.id],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert result.returncode == 0, result.stderr


def test_eowyn_trigger_survives_source_departure_and_uses_original_controller(cards):
    s = setup(cards)
    target = put(s, 'Craw Wurm', 'battlefield', 'p2')
    legend = put(s, 'Figure of Fable', 'battlefield')  # Ordinary creature is not a recipient.
    commander = put(s, 'Krenko, Mob Boss', 'battlefield')
    source = spell(s, 'Éowyn, Fearless Knight', {'R': 1, 'W': 1, 'C': 2})
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
    settle(s)
    assert s.state.cards[target.id].zone == 'p2:exile'
    assert qualities(s, commander) == {'G'} and not qualities(s, legend)
    roundtrip(s)


def test_samite_multicolor_permanent_grants_each_color_and_expires(cards):
    s = setup(cards)
    elder = put(s, 'Samite Elder', 'battlefield')
    target = put(s, 'Fusion Elemental', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=elder.id, ability=0, targets=[target.id])
    settle(s)
    assert qualities(s, elder) == set('WUBRG') and qualities(s, target) == set('WUBRG')
    to_phase(s, 'main1', turn=5)
    assert not qualities(s, elder) and not qualities(s, target)
    roundtrip(s)


def test_kannushi_live_global_color_change_and_ability_loss(cards):
    s = setup(cards)
    source = put(s, 'Empty-Shrine Kannushi', 'battlefield')
    red = put(s, 'Goblin Chainwhirler', 'battlefield')
    assert qualities(s, source) == {'W', 'R'}
    color(s, red, 'Blue')
    assert qualities(s, source) == {'W', 'U'}
    put(s, 'Humility', 'battlefield')
    assert not qualities(s, source)
    roundtrip(s)


def test_opal_titan_intervening_enchantment_condition_prevents_second_animation(cards):
    s = setup(cards)
    source = put(s, 'Opal Titan', 'battlefield')
    to_phase(s, 'main1', turn=2)
    spell(s, 'Grizzly Bears', {'G': 1, 'C': 1}, player='p2')
    assert qualities(s, source) == {'G'}
    spell(s, 'Goblin Chainwhirler', {'R': 3}, player='p2')
    assert qualities(s, source) == {'G'} and ch(s, source).types == frozenset({'Creature'})
    roundtrip(s)


def test_opal_titan_colorless_creature_spell_uses_no_protection_quality(cards):
    s = setup(cards)
    source = put(s, 'Opal Titan', 'battlefield')
    to_phase(s, 'main1', turn=2)
    spell(s, 'Ornithopter', {}, player='p2')
    assert ch(s, source).pt == (4, 4) and not qualities(s, source)
    roundtrip(s)
