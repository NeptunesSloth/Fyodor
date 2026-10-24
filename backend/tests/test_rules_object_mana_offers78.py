"""Actual APNAP mana offers with saved original objects and one final batch."""
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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ['Cut the Tethers', 'Whirlwind Denial', 'Heroism']
DATA = json.loads((Path(__file__).parent / 'fixtures/object_mana_offers78_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Lightning Bolt', 'Counterspell', 'Island', 'Forest']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    s = table(cards, ALL, ALL, ALL)
    to_phase(s, 'main1', 1)
    return s


def choose(s, ids):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def cast(s, name, targets=(), pid='p1', resolve=True):
    c = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana={'C': 6, 'W': 3, 'U': 4, 'R': 2, 'B': 1, 'G': 2})
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets), sources=[])
    if resolve:
        settle(s)
    return c


@pytest.mark.parametrize('name', NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_cut_each_owner_selects_and_pays_before_any_spirit_returns(cards):
    s = game(cards)
    a = put(s, 'Lantern Kami', 'battlefield')
    b = put(s, "Will-o'-the-Wisp", 'battlefield')
    foreign = put(s, 'Lantern Kami', 'battlefield', 'p2')
    act(s, 'p2', type='set_controller', card_ids=[foreign.id], player='p1')
    ordinary = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, NAMES[0])
    d = s.state.rules.decision
    assert d and d.player == 'p1' and {o.id for o in d.options} == {a.id, b.id}
    choose(s, [a.id])
    assert s.state.rules.decision.player == 'p1' and s.state.rules.decision.resume.get('opt')
    choose(s, ['pay'])
    assert s.state.rules.decision.player == 'p2' and foreign.id in {o.id for o in s.state.rules.decision.options}
    assert all(s.state.cards[c.id].zone == 'p1:battlefield' for c in [a, b])
    assert s.state.cards[foreign.id].zone == 'p1:battlefield'
    choose(s, [])
    assert s.state.cards[a.id].zone == s.state.cards[ordinary.id].zone == 'p1:battlefield'
    assert s.state.cards[b.id].zone == 'p1:hand' and s.state.cards[foreign.id].zone == 'p2:hand'
    left = [x for x in s.state.rules.events if x.kind == 'zone_change' and x.card in {b.id, foreign.id} and x.to_zone.endswith(':hand')]
    assert len(left) == 2 and len({x.batch for x in left}) == 1
    roundtrip(s)


def test_cut_selected_but_unpayable_set_is_unpaid_and_cannot_reuse_one_payment(cards):
    s = game(cards)
    a = put(s, 'Lantern Kami', 'battlefield', 'p2')
    b = put(s, "Will-o'-the-Wisp", 'battlefield', 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 3})
    cast(s, NAMES[0])
    from app.game.errors import ActionError
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        choose(s, [a.id, b.id])
    assert s.state.model_dump_json() == before
    choose(s, [a.id])
    choose(s, ['pay'])
    assert s.state.rules.decision is None
    assert s.state.cards[a.id].zone == 'p2:battlefield' and s.state.cards[b.id].zone == 'p2:hand'
    assert not s.state.players['p2'].mana
    roundtrip(s)


def test_whirlwind_non_targeting_filters_own_spells_and_native_counterable(cards):
    s = game(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p2', type='set_prefs', hold_priority=True)
    own = cast(s, 'Lightning Bolt', ['p3'], resolve=False)
    other = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    # An uncounterable spell is still offered; declining cannot counter it.
    uncounterable = cast(s, 'Last Word', [own.id], pid='p2', resolve=False)
    cast(s, NAMES[1])
    d = s.state.rules.decision
    assert d and d.player == 'p2' and {o.id for o in d.options} == {other.id, uncounterable.id}
    choose(s, [])
    assert s.state.cards[other.id].zone == 'p2:graveyard'
    assert s.state.cards[uncounterable.id].zone == 'p2:graveyard'
    assert s.state.cards[own.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].life == s.state.players['p3'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_heroism_actual_white_sacrifice_only_attacking_red_and_paid_subset(cards, pay):
    from tests.test_rules_damage_redirection import attack, damage
    s = game(cards)
    source = put(s, NAMES[2], 'battlefield', 'p3')
    white = put(s, 'Lantern Kami', 'battlefield', 'p3')
    red = put(s, 'Lightning Elemental', 'battlefield')
    green = put(s, 'Grizzly Bears', 'battlefield')
    idle = put(s, 'Raging Goblin', 'battlefield')
    attack(s, [red, green])
    to_phase(s, 'declare_blockers')
    if s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_blockers':
        act(s, 'p2', type='declare_blockers', blocks=[])
        settle(s)
    wait_priority(s, 'p3')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'R': 1})
    act(s, 'p3', type='activate_ability', card_id=source.id, ability=0, sources=[],
        cost_choices=[{'component': 0, 'cards': [white.id]}])
    settle(s)
    assert s.state.cards[white.id].zone == 'p3:graveyard'
    d = s.state.rules.decision
    assert d and d.player == 'p1' and {o.id for o in d.options} == {red.id}
    choose(s, [red.id] if pay else [])
    if pay:
        choose(s, ['pay'])
    damage(s)
    assert s.state.players['p2'].life == (34 if pay else 38)
    assert s.state.cards[idle.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_whirlwind_native_activated_ability_and_two_opponents_paid_before_one_batch(cards):
    s = game(cards)
    for pid in ('p1', 'p2', 'p3'):
        act(s, pid, type='set_prefs', hold_priority=True)
    own = cast(s, 'Lightning Bolt', ['p3'], resolve=False)
    paid = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    unpaid = cast(s, 'Lightning Bolt', ['p1'], pid='p3', resolve=False)
    millstone = put(s, 'Millstone', 'battlefield', 'p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=millstone.id, ability=0, targets=['p1'], sources=[])
    ability = next(c.id for c in s.state.cards.values() if c.zone == 'stack' and c.ability is not None)
    cast(s, NAMES[1])
    d = s.state.rules.decision
    assert d and d.player == 'p2' and {o.id for o in d.options} == {paid.id, ability}
    act(s, 'p2', type='clear_mana', player='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 4})
    choose(s, [paid.id])
    choose(s, ['pay'])
    assert s.state.rules.decision.player == 'p3'
    assert ability in s.state.rules.stack and unpaid.id in s.state.rules.stack
    d = s.state.rules.decision
    result = act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    moves = [step for step in result.r if step['type'] == 'move' and set(step['card_ids']) == {ability, unpaid.id}]
    assert len(moves) == 1
    settle(s)
    assert s.state.players['p1'].life == s.state.players['p3'].life == 37
    assert s.state.cards[own.id].zone == 'p1:graveyard'
    assert s.state.cards[unpaid.id].zone == 'p3:graveyard'
    assert ability not in s.state.rules.stack
    assert len(s.state.zones['p1:graveyard']) == 2  # Whirlwind and own Bolt; the mill never resolved.
    roundtrip(s)


def test_cut_ignores_phased_spirit_and_rejects_foreign_or_duplicate_payment_choices(cards):
    from app.game.errors import ActionError
    s = game(cards)
    phased = put(s, 'Lantern Kami', 'battlefield')
    act(s, 'p1', type='phase_shift', card_ids=[phased.id], out=True)
    spirit = put(s, "Will-o'-the-Wisp", 'battlefield', 'p2')
    other = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, NAMES[0])
    d = s.state.rules.decision
    assert d and d.player == 'p2' and [o.id for o in d.options] == [spirit.id]
    for picks in ([other.id], [spirit.id, spirit.id]):
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            choose(s, picks)
        assert s.state.model_dump_json() == before
    choose(s, [])
    assert s.state.cards[phased.id].zone == 'p1:phased'
    assert s.state.cards[other.id].zone == 'p1:battlefield'
    assert s.state.cards[spirit.id].zone == 'p2:hand'
    roundtrip(s)


@pytest.mark.parametrize('name', [NAMES[0], NAMES[1]])
def test_no_eligible_objects_resolves_without_invented_choices(cards, name):
    s = game(cards)
    cast(s, name)
    assert s.state.rules.decision is None and not s.state.rules.stack
    roundtrip(s)


def test_whirlwind_actual_flashback_spell_and_actual_copy_share_one_counter_batch(cards):
    s = game(cards)
    for pid in ('p1', 'p2', 'p3'):
        act(s, pid, type='set_prefs', hold_priority=True)
    source = put(s, 'Think Twice', 'graveyard', 'p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2, 'U': 1})
    act(s, 'p2', type='cast_spell', card_id=source.id, sources=[], flashback_choice=0)
    copier = cast(s, 'Twincast', [source.id], pid='p3', resolve=False)
    copied = None
    for _ in range(25):
        d = s.state.rules.decision
        if d:
            assert 'keep' in {o.id for o in d.options}
            act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep'])
        else:
            act(s, s.state.rules.priority, type='pass_priority')
        copied = next((cid for cid, entry in s.state.rules.stack.items() if entry.copy_of and cid != copier.id), None)
        if copied is not None and s.state.rules.decision is None:
            break
    assert copied is not None and s.state.cards[source.id].zone == 'stack'
    cast(s, NAMES[1])
    assert s.state.rules.decision.player == 'p2'
    choose(s, [])
    assert s.state.rules.decision.player == 'p3'
    d = s.state.rules.decision
    result = act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    moves = [step for step in result.r if step['type'] == 'move' and set(step['card_ids']) == {source.id, copied}]
    assert len(moves) == 1
    settle(s)
    assert s.state.cards[source.id].zone == 'p2:exile'
    assert copied not in s.state.cards and copied not in s.state.rules.stack
    roundtrip(s)


def test_whirlwind_counters_actual_enter_trigger_not_its_source_permanent(cards):
    s = game(cards)
    act(s, 'p2', type='set_prefs', auto_resolve_own_triggers='off')
    warden = put(s, 'Soul Warden', 'battlefield', 'p2')
    creature = cast(s, 'Grizzly Bears', resolve=False)
    for _ in range(20):
        if s.state.cards[creature.id].zone != 'stack':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    trigger = next(cid for cid, entry in s.state.rules.stack.items() if entry.source_card == warden.id)
    before = s.state.players['p2'].life
    cast(s, NAMES[1])
    assert trigger in {o.id for o in s.state.rules.decision.options}
    choose(s, [])
    assert trigger not in s.state.rules.stack and s.state.cards[warden.id].zone == 'p2:battlefield'
    assert s.state.players['p2'].life == before
    roundtrip(s)


def test_pending_cut_original_object_receipt_does_not_follow_blinked_physical_card(cards):
    s = game(cards)
    first = put(s, 'Lantern Kami', 'battlefield')
    old = put(s, "Will-o'-the-Wisp", 'battlefield', 'p2')
    cast(s, NAMES[0])
    act(s, 'p2', type='move', card_ids=[old.id], to={'player': 'p2', 'zone': 'exile'})
    act(s, 'p2', type='move', card_ids=[old.id], to={'player': 'p2', 'zone': 'battlefield'})
    choose(s, [])
    assert s.state.rules.decision is None
    assert s.state.cards[first.id].zone == 'p1:hand' and s.state.cards[old.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_genuine_cold_selected_set_pending_payment_preserves_other_players_and_original_refs(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    s = game(cards)
    ids = []
    if name == NAMES[0]:
        a = put(s, 'Lantern Kami', 'battlefield')
        b = put(s, "Will-o'-the-Wisp", 'battlefield', 'p2')
        cast(s, name)
        choose(s, [a.id])
        ids = [a.id, b.id]
    elif name == NAMES[1]:
        for pid in ('p1', 'p2', 'p3'):
            act(s, pid, type='set_prefs', hold_priority=True)
        a = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
        b = cast(s, 'Lightning Bolt', ['p1'], pid='p3', resolve=False)
        cast(s, name)
        choose(s, [a.id])
        ids = [a.id, b.id]
    else:
        from tests.test_rules_damage_redirection import attack
        source = put(s, NAMES[2], 'battlefield', 'p3')
        white = put(s, 'Lantern Kami', 'battlefield', 'p3')
        a = put(s, 'Lightning Elemental', 'battlefield')
        attack(s, [a])
        to_phase(s, 'declare_blockers')
        wait_priority(s, 'p3')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'R': 1})
        act(s, 'p3', type='activate_ability', card_id=source.id, ability=0, sources=[],
            cost_choices=[{'component': 0, 'cards': [white.id]}])
        settle(s)
        choose(s, [a.id])
        ids = [a.id, white.id]
    assert s.state.rules.decision and s.state.rules.decision.resume.get('opt')
    saved = tmp_path / 'pending-payment.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_damage_redirection import damage
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
name,a,b=sys.argv[3:]
d=s.state.rules.decision
assert d and d.resume.get('opt')
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
settle(s)
if name=='Heroism':
 assert s.state.rules.decision is None
 damage(s)
 assert s.state.players['p2'].life==36 and s.state.cards[b].zone=='p3:graveyard'
else:
 d=s.state.rules.decision
 assert d and d.player==('p2' if name=='Cut the Tethers' else 'p3')
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
 settle(s)
 if name=='Cut the Tethers':assert s.state.cards[a].zone=='p1:battlefield' and s.state.cards[b].zone=='p2:hand'
 else:assert s.state.players['p1'].life==37 and s.state.cards[a].zone=='p2:graveyard' and s.state.cards[b].zone=='p3:graveyard'
assert s.state.rules.decision is None
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, *ids],
                            capture_output=True, text=True, timeout=90, env=os.environ.copy())
    assert result.returncode == 0, result.stdout + result.stderr


def test_cut_native_mana_abilities_during_payment_prompt_pay_owners_own_sources(cards):
    s = game(cards)
    spirit = put(s, "Will-o'-the-Wisp", 'battlefield', 'p2')
    lands = [c for c in s.state.cards.values() if c.owner == 'p2' and c.name == 'Island'][:3]
    assert len(lands) == 3
    act(s, 'p2', type='move', card_ids=[c.id for c in lands], to={'player': 'p2', 'zone': 'battlefield'})
    cast(s, NAMES[0])
    choose(s, [spirit.id])
    assert s.state.rules.decision.resume.get('opt')
    for land in lands:
        act(s, 'p2', type='activate_ability', card_id=land.id, ability=0, sources=[])
    choose(s, ['pay'])
    assert s.state.cards[spirit.id].zone == 'p2:battlefield'
    assert all(s.state.cards[c.id].tapped for c in lands) and not s.state.players['p2'].mana
    roundtrip(s)


def test_whirlwind_exact_eight_mana_preserves_two_selected_opponent_spells(cards):
    s = game(cards)
    act(s, 'p2', type='set_prefs', hold_priority=True)
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    draw = cast(s, 'Think Twice', pid='p2', resolve=False)
    cast(s, NAMES[1])
    act(s, 'p2', type='clear_mana', player='p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 8})
    choose(s, [bolt.id, draw.id])
    assert s.state.rules.decision.resume['opt']['cost'] == '{8}'
    choose(s, ['pay'])
    assert s.state.players['p1'].life == 37 and not s.state.players['p2'].mana
    assert s.state.cards[bolt.id].zone == s.state.cards[draw.id].zone == 'p2:graveyard'
    roundtrip(s)
