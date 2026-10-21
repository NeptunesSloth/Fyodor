"""One opponent must satisfy each historical Trap condition on their own."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import alt_costs, conditions, coverage
from app.rules import characteristics as chars
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Whiplash Trap', 'Baloth Cage Trap', 'Lavaball Trap', 'Runeflare Trap', 'Needlebite Trap']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/history_trap_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='htr', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    support = ['Unsummon', 'Counterspell', 'Healing Salve', 'Act of Treason', 'Cerulean Wisps', 'Viridescent Wisps', 'Dominate']
    s = table(cards, [name, *support], ['Divination', 'Ornithopter', 'Rampant Growth', 'Act of Treason', 'Llanowar Elves'], [])
    spell = put(s, name, 'hand')
    to_phase(s, 'main1', turn=2)
    for p in ['p1', 'p2', 'p3']:
        act(s, p, type='set_prefs', hold_priority=True)
    return s, spell


def token(s, player='p2', type_line='Token Creature — Scout'):
    name = f'Probe{len(s.state.cards)}'
    act(s, 'p1', type='create_token', player=player, token={
        'name': name, 'type_line': type_line, 'power': '3', 'toughness': '3', 'colors': ['G']})
    return next(c for c in s.state.cards.values() if c.name == name)


def offers(s, spell):
    return alt_costs.offers(s.state, 'p1', spell, chars.of(spell, s.cards), s.cards)


def cast(s, spell, pool, targets=()):
    wait_priority(s, 'p1')
    mana(s, **pool)
    options = offers(s, spell)
    assert len(options) == 1
    groups = {'target_counts': [2]} if len(targets) == 2 else {}
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=list(targets), alt_cost=options[0].key, **groups)
    assert s.state.rules.payments[s.state.rules.object_id(spell.id)].alternative == 'alternative'
    roundtrip(s)
    settle(s)


@pytest.mark.parametrize('name', NAMES)
def test_canonical_history_traps_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,type_line', [('Whiplash Trap', 'Token Creature — Scout'),
                                         ('Lavaball Trap', 'Token Land — Forest')])
def test_two_entries_must_belong_to_one_opponent(cards, name, type_line):
    s, spell = setup(cards, name)
    token(s, 'p2', type_line)
    token(s, 'p3', type_line)
    assert not offers(s, spell)
    what = 'creatures' if name == 'Whiplash Trap' else 'lands'
    aggregate = conditions.parse(f"two or more {what} entered the battlefield under an opponent's control this turn")
    assert aggregate is not None
    assert conditions.holds(Plan.view(s.state, 'p1', s.cards), {'controller': 'p1'}, aggregate)
    token(s, 'p1', type_line)
    assert not offers(s, spell)
    token(s, 'p2', type_line)
    assert offers(s, spell)
    roundtrip(s)


def test_whiplash_actual_alternative_and_two_bounces(cards):
    s, spell = setup(cards, 'Whiplash Trap')
    a, b = token(s), token(s)
    cast(s, spell, {'U': 1}, [a.id, b.id])
    assert a.id not in s.state.cards and b.id not in s.state.cards
    roundtrip(s)


def test_baloth_native_artifact_entry_then_actual_beast(cards):
    s, spell = setup(cards, 'Baloth Cage Trap')
    artifact = put(s, 'Ornithopter', 'hand', pid='p2')
    act(s, 'p2', type='cast_spell', card_id=artifact.id)
    settle(s)
    cast(s, spell, {'C': 1, 'G': 1})
    beasts = [c for c in s.state.cards.values() if c.name == 'Beast' and c.zone == 'p1:battlefield']
    assert len(beasts) == 1 and beasts[0].token.power == '4' and beasts[0].token.toughness == '4'
    roundtrip(s)


def test_lavaball_destroys_two_lands_and_deals_four_to_all_creatures(cards):
    s, spell = setup(cards, 'Lavaball Trap')
    a = token(s, type_line='Token Land — Forest')
    b = token(s, type_line='Token Land — Forest')
    creature = token(s, 'p3')
    cast(s, spell, {'C': 3, 'R': 2}, [a.id, b.id])
    assert all(c.id not in s.state.cards for c in [a, b, creature])
    roundtrip(s)


def draw(s, player, n):
    act(s, player, type='draw', player=player, count=n)


def test_runeflare_draw_threshold_is_per_player_and_real_damage_uses_current_hand(cards):
    s, spell = setup(cards, 'Runeflare Trap')
    # p2 drew once for the turn. Two other players drawing cannot complete p2's threshold.
    draw(s, 'p3', 2)
    draw(s, 'p1', 3)
    assert not offers(s, spell)
    divination = put(s, 'Divination', 'hand', pid='p2')
    mana(s, pid='p2', C=2, U=1)
    act(s, 'p2', type='cast_spell', card_id=divination.id)
    settle(s)
    hand = len(s.state.zones['p3:hand'])
    life = s.state.players['p3'].life
    cast(s, spell, {'R': 1}, ['p3'])
    assert s.state.players['p3'].life == life - hand
    roundtrip(s)


def test_needlebite_uses_opponent_life_gain_even_after_life_loss(cards):
    s, spell = setup(cards, 'Needlebite Trap')
    salve = put(s, 'Healing Salve', 'hand')
    mana(s, W=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=salve.id, modes=[0], targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 43
    act(s, 'p1', type='set_life', player='p2', value=20)
    own = s.state.players['p1'].life
    cast(s, spell, {'B': 1}, ['p3'])
    assert s.state.players['p3'].life == 35 and s.state.players['p1'].life == own + 5
    roundtrip(s)


def test_own_life_gain_does_not_enable_needlebite(cards):
    s, spell = setup(cards, 'Needlebite Trap')
    salve = put(s, 'Healing Salve', 'hand')
    mana(s, W=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=salve.id, modes=[0], targets=['p1'])
    settle(s)
    assert not offers(s, spell)


def test_history_condition_resets_on_next_turn(cards):
    s, spell = setup(cards, 'Whiplash Trap')
    token(s)
    token(s)
    assert offers(s, spell)
    to_phase(s, 'main1', turn=3)
    assert not offers(s, spell)


def test_invalid_alternate_cost_is_atomic(cards):
    s, spell = setup(cards, 'Baloth Cage Trap')
    wait_priority(s, 'p1')
    mana(s, C=1, G=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=f'{spell.id}:0')
    assert s.state.model_dump_json() == before


def test_departed_creatures_still_count_as_entries(cards):
    s, spell = setup(cards, 'Whiplash Trap')
    a = token(s)
    token(s)
    bounce = put(s, 'Unsummon', 'hand')
    mana(s, U=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[a.id])
    settle(s)
    assert a.id not in s.state.cards
    assert offers(s, spell)
    roundtrip(s)


def test_gaining_control_of_another_players_entry_is_not_an_entry(cards):
    s, spell = setup(cards, 'Whiplash Trap')
    token(s, 'p2')
    other = token(s, 'p3')
    theft = put(s, 'Act of Treason', 'hand', pid='p2')
    mana(s, pid='p2', C=2, R=1)
    act(s, 'p2', type='cast_spell', card_id=theft.id, targets=[other.id])
    settle(s)
    assert s.state.cards[other.id].controller == 'p2'
    assert not offers(s, spell)
    token(s, 'p2')
    assert offers(s, spell)
    roundtrip(s)


def test_native_land_play_and_search_count_for_same_opponent(cards):
    s, spell = setup(cards, 'Lavaball Trap')
    land = put(s, 'Island', 'hand', pid='p2')
    act(s, 'p2', type='play_land', card_id=land.id)
    assert not offers(s, spell)
    growth = put(s, 'Rampant Growth', 'hand', pid='p2')
    mana(s, pid='p2', C=1, G=1)
    act(s, 'p2', type='cast_spell', card_id=growth.id)
    settle(s)
    lands = [c for c in s.state.cards.values() if c.zone == 'p2:battlefield' and 'Land' in chars.of(c, s.cards).types]
    assert len(lands) == 2 and offers(s, spell)
    cast(s, spell, {'C': 3, 'R': 2}, [c.id for c in lands])
    assert all(s.state.cards[c.id].zone == 'p2:graveyard' for c in lands)
    roundtrip(s)


def test_cold_paid_baloth_trap_and_native_counter(cards, tmp_path):
    s, spell = setup(cards, 'Baloth Cage Trap')
    token(s, type_line='Token Artifact — Clue')
    wait_priority(s, 'p1')
    mana(s, C=1, G=1, U=2)
    act(s, 'p1', type='cast_spell', card_id=spell.id, alt_cost=offers(s, spell)[0].key)
    saved = tmp_path / 'history-trap.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
saved,db,spell=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(saved).read_text()),cards=repo)
assert s.state.rules.payments[s.state.rules.object_id(spell)].alternative=='alternative'
for _ in range(12):
 if not s.state.zones.get('stack'):break
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert len([c for c in s.state.cards.values() if c.name=='Beast' and c.zone=='p1:battlefield'])==1
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), spell.id],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    counter = put(s, 'Counterspell', 'hand')
    act(s, 'p1', type='cast_spell', card_id=counter.id, targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert not any(c.name == 'Beast' for c in s.state.cards.values())
    roundtrip(s)


def test_permafrost_canonical_full_and_native_green_entry_cost_tap_skip_untap(cards):
    assert coverage.of_card_data(cards.resolve('Permafrost Trap')).level == 'FULL'
    s, spell = setup(cards, 'Permafrost Trap')
    elf = put(s, 'Llanowar Elves', 'hand', pid='p2')
    mana(s, pid='p2', G=1)
    act(s, 'p2', type='cast_spell', card_id=elf.id)
    settle(s)
    artifact = put(s, 'Ornithopter', 'hand', pid='p2')
    act(s, 'p2', type='cast_spell', card_id=artifact.id)
    settle(s)
    cast(s, spell, {'U': 1}, [elf.id, artifact.id])
    assert s.state.cards[elf.id].tapped and s.state.cards[artifact.id].tapped
    to_phase(s, 'main1', turn=5)
    assert s.state.cards[elf.id].tapped and s.state.cards[artifact.id].tapped
    to_phase(s, 'main1', turn=8)
    assert not s.state.cards[elf.id].tapped and not s.state.cards[artifact.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('green,change,eligible', [(True, 'Cerulean Wisps', True),
                                                (False, 'Viridescent Wisps', False)])
def test_permafrost_uses_arrival_color_not_later_recoloring(cards, green, change, eligible):
    s, spell = setup(cards, 'Permafrost Trap')
    name = 'Llanowar Elves' if green else 'Ornithopter'
    creature = put(s, name, 'hand', pid='p2')
    if green:
        mana(s, pid='p2', G=1)
    act(s, 'p2', type='cast_spell', card_id=creature.id)
    settle(s)
    recolor = put(s, change, 'hand')
    wait_priority(s, 'p1')
    mana(s, U=1, G=1)
    act(s, 'p1', type='cast_spell', card_id=recolor.id, targets=[creature.id])
    settle(s)
    current = Plan.view(s.state, 'p1', cards).ch(s.state.cards[creature.id])
    assert ('G' in current.colors) != green
    assert bool(offers(s, spell)) == eligible
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    assert bool(offers(loaded, loaded.state.cards[spell.id])) == eligible
    roundtrip(s)


def test_permafrost_green_entry_remains_counted_after_departure(cards):
    s, spell = setup(cards, 'Permafrost Trap')
    creature = put(s, 'Llanowar Elves', 'hand', pid='p2')
    mana(s, pid='p2', G=1)
    act(s, 'p2', type='cast_spell', card_id=creature.id)
    settle(s)
    bounce = put(s, 'Unsummon', 'hand')
    mana(s, U=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=bounce.id, targets=[creature.id])
    settle(s)
    assert s.state.cards[creature.id].zone == 'p2:hand' and offers(s, spell)
    roundtrip(s)


def test_permafrost_legacy_unknown_colors_are_not_inferred_from_current_green(cards):
    s, spell = setup(cards, 'Permafrost Trap')
    token(s)
    token(s)
    state = s.state.model_dump(mode='json')
    for entry in state['rules']['turn_log']['entered']:
        entry.pop('colors', None)
    loaded = GameSession(GameState.model_validate(state), cards=cards)
    assert not offers(loaded, loaded.state.cards[spell.id])
    ordinary = conditions.parse("two or more creatures entered the battlefield under an opponent's control this turn")
    assert ordinary is not None and conditions.holds(Plan.view(loaded.state, 'p1', cards), {'controller': 'p1'}, ordinary)


def test_permafrost_control_change_does_not_rewrite_arrival_recipient(cards):
    s, spell = setup(cards, 'Permafrost Trap')
    creature = put(s, 'Llanowar Elves', 'hand', pid='p2')
    mana(s, pid='p2', G=1)
    act(s, 'p2', type='cast_spell', card_id=creature.id)
    settle(s)
    theft = put(s, 'Dominate', 'hand')
    mana(s, C=2, U=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=theft.id, x_value=1, targets=[creature.id])
    settle(s)
    assert s.state.cards[creature.id].controller == 'p1' and offers(s, spell)
    roundtrip(s)
