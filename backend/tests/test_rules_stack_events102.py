"""Original cast targets, native stack copies, and once loyalty-copy watches."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import pick, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

DATA = json.loads((Path(__file__).parent / 'fixtures/stack_events102_cards.json').read_text())
NAMES = ['Hive Mind', 'Ivy, Gleeful Spellthief', 'Frontline Heroism', 'Volo, Guide to Monsters', "Jaya's Phoenix", 'Voracious Bibliophile']


@pytest.fixture
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='s102', number=str(i), **{k: v for k, v in c.items() if k not in ('name', 'set_code', 'number')})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns = [c['name'] for c in DATA if c['name'] not in ('Krenko, Mob Boss', "Atraxa, Praetors' Voice")]
    ns += ['Grizzly Bears', 'Grizzly Bears']
    s = table(cards, ns, ns, ns)
    to_phase(s, 'main1', 1)
    return s


def put(s, name, zone='battlefield', pid='p1'):
    found = [c for c in s.state.cards.values() if c.owner == pid and c.name == name]
    c = next((c for c in found if c.zone != f'{pid}:{zone}'), found[0])
    act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': zone})
    return s.state.cards[c.id]


def cast(s, name, targets=(), pid='p1', **extra):
    found = [c for c in s.state.cards.values() if c.owner == pid and c.name == name and not c.zone.endswith((':battlefield', ':graveyard'))]
    c = next((c for c in found if c.zone == f'{pid}:hand'), found[0])
    act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': 'hand'})
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana={c: 20 for c in ['C','W','U','B','R','G']})
    act(s, pid, type='cast_spell', card_id=c.id, sources=[], targets=list(targets), **extra)
    return c


def finish(s, prefer=()):
    for _ in range(60):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        ids = [o.id for o in d.options]
        wanted = [x for x in [*prefer, 'yes', 'copy', 'keep'] if x in ids]
        pick(s, wanted[:1] if wanted else ids[:max(1,d.min_choices)])
    raise AssertionError('did not finish')


def pt(s, card):
    return Plan.view(s.state, 'p1', s.cards).ch(s.state.cards[card.id]).pt


@pytest.mark.parametrize('name', NAMES)
def test_whole102(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('duplicate', [False, True])
def test_bibliophile_counts_unique_creatures_or_player_targets(cards, duplicate):
    s = setup(cards)
    put(s, 'Voracious Bibliophile')
    bear = put(s, 'Grizzly Bears')
    hand = len(s.state.zones['p1:hand'])
    source = cast(s, 'Common Bond', [bear.id,bear.id], target_counts=[1,1]) if duplicate else cast(s, 'Lightning Bolt', ['p2'])
    after_cast = len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand']) == after_cast + 1
    assert len(s.state.zones['p1:hand']) >= hand - 1
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('where,owner', [('battlefield','p1'),('graveyard','p1'),('graveyard','p2')])
def test_volo_actual_current_own_creature_types_all_zones(cards, where, owner):
    s = setup(cards)
    put(s, 'Volo, Guide to Monsters')
    put(s, 'Universal Automaton', where, owner)
    source = cast(s, 'Grizzly Bears')
    finish(s)
    bears = [c for c in s.state.cards.values() if c.name == 'Grizzly Bears' and c.zone == 'p1:battlefield']
    assert len(bears) == (2 if owner == 'p2' else 1)
    assert sum(c.is_token for c in bears) == (1 if owner == 'p2' else 0)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_hive_each_other_player_native_copy_and_no_cast_recursion(cards):
    s = setup(cards)
    put(s, 'Hive Mind')
    source = cast(s, 'Lightning Bolt', ['p3'])
    finish(s)
    assert s.state.players['p3'].life == 31
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert not s.state.zones.get('stack')
    roundtrip(s)


@pytest.mark.parametrize('countered', [False, True])
def test_ivy_native_other_player_spell_fixed_copy_even_if_original_countered(cards, countered):
    s = setup(cards)
    ivy = put(s, 'Ivy, Gleeful Spellthief')
    bear = put(s, 'Grizzly Bears', pid='p2')
    source = cast(s, 'Giant Growth', [bear.id], pid='p2')
    if countered:
        cast(s, 'Counterspell', [source.id], pid='p3')
        while len(s.state.zones.get('stack', [])) > 1:
            assert s.state.rules.decision is None
            act(s, s.state.rules.priority, type='pass_priority')
    finish(s)
    assert pt(s, ivy) == (5,4)
    assert pt(s, bear) == ((2,2) if countered else (5,5))
    roundtrip(s)


def test_ivy_illegal_copy_target_is_not_created(cards):
    s = setup(cards)
    ivy = put(s, 'Ivy, Gleeful Spellthief')
    bear = put(s, 'Grizzly Bears', pid='p2')
    cast(s, 'Ultimate Price', [bear.id], pid='p2')
    finish(s)
    assert pt(s, ivy) == (2,1) and s.state.cards[bear.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_frontline_created_token_is_fixed_copy_destination_and_aura_copy_is_token(cards):
    s = setup(cards)
    cast(s, 'Frontline Heroism')
    finish(s)
    bear = put(s, 'Grizzly Bears')
    old_soldiers = {c.id for c in s.state.cards.values() if c.name == 'Soldier' and c.zone == 'p1:battlefield'}
    source = cast(s, 'Rancor', [bear.id])
    finish(s)
    soldiers = [c for c in s.state.cards.values() if c.name == 'Soldier' and c.zone == 'p1:battlefield']
    assert len(soldiers) == 2
    rancors = [c for c in s.state.cards.values() if c.name == 'Rancor' and c.zone == 'p1:battlefield']
    assert len(rancors) == 2 and sum(c.is_token for c in rancors) == 1
    assert {c.attached_to for c in rancors} == {bear.id, next(c.attached_to for c in rancors if c.is_token)}
    assert any(c.attached_to in {x.id for x in soldiers} - old_soldiers for c in rancors if c.is_token)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_jaya_real_combat_then_next_loyalty_copy_does_not_pay_loyalty_twice(cards):
    s = setup(cards)
    phoenix = put(s, "Jaya's Phoenix")
    to_phase(s, 'declare_attackers', 1)
    attack(s, (phoenix, 'p2'))
    to_phase(s, 'main2', 1)
    finish(s)
    assert s.state.players['p2'].life == 37
    source = cast(s, 'Jace Beleren')
    finish(s)
    wait_priority(s, 'p1')
    before = {p: len(s.state.zones[p+':hand']) for p in ['p1','p2','p3']}
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    finish(s)
    assert s.state.cards[source.id].counters['loyalty'] == 5
    assert all(len(s.state.zones[p+':hand']) == n+2 for p,n in before.items())
    roundtrip(s)


def test_bibliophile_two_distinct_players_and_aura_target_count(cards):
    s = setup(cards)
    put(s, 'Voracious Bibliophile')
    cast(s, 'Forked Bolt', ['p2','p3'], target_counts=[2], division=[1,1])
    hand = len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand']) == hand+2
    bear = put(s, 'Grizzly Bears')
    cast(s, 'Rancor', [bear.id])
    hand = len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand']) == hand+1
    cast(s, 'Divination')
    hand = len(s.state.zones['p1:hand'])
    finish(s)
    assert len(s.state.zones['p1:hand']) == hand+2
    roundtrip(s)


def test_hive_nontarget_copies_each_controller_draws_their_own_cards(cards):
    s = setup(cards)
    put(s, 'Hive Mind')
    to_phase(s, 'main1', 2)
    cast(s, 'Divination', pid='p2')
    before = {p: len(s.state.zones[p+':hand']) for p in ['p1','p2','p3']}
    finish(s)
    assert all(len(s.state.zones[p+':hand']) == n+2 for p,n in before.items())
    roundtrip(s)


def test_frontline_doubled_tokens_choose_one_of_only_new_tokens_for_one_copy(cards):
    s = setup(cards)
    put(s, 'Doubling Season')
    cast(s, 'Frontline Heroism')
    finish(s)
    old = {c.id for c in s.state.cards.values() if c.name == 'Soldier' and c.zone == 'p1:battlefield'}
    assert len(old) == 2
    bear = put(s, 'Grizzly Bears')
    cast(s, 'Giant Growth', [bear.id])
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.player == 'p1'
    assert len(s.state.rules.decision.options) == 2
    assert not old.intersection(o.id for o in s.state.rules.decision.options)
    chosen = s.state.rules.decision.options[-1].id
    pick(s, [chosen])
    finish(s)
    assert Plan.view(s.state, 'p1', cards).ch(s.state.cards[chosen]).pt == (4,4)
    assert pt(s, bear) == (5,5)
    roundtrip(s)


def test_ivy_native_copy_replacement_additional_copy_can_keep_original_targets(cards):
    s = setup(cards)
    ivy = put(s, 'Ivy, Gleeful Spellthief')
    put(s, 'Twinning Staff')
    bear = put(s, 'Grizzly Bears', pid='p2')
    cast(s, 'Giant Growth', [bear.id], pid='p2')
    finish(s)
    assert pt(s, ivy) == (5,4) and pt(s, bear) == (8,8)
    roundtrip(s)


def cold(s, tmp_path, body):
    import subprocess
    import sys

    saved = tmp_path / 'stack102.json'
    saved.write_text(s.state.model_dump_json())
    code = '''import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import pick,roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_stack_events102 import cast,finish,pt
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_bandmate_references import wait_priority
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
'''+body+'\nroundtrip(s);repo.close()\n'
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(s.cards.db_path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr


def test_genuine_cold_countered_aura_original_target_retained_and_copy_attaches_to_ivy(cards, tmp_path):
    s = setup(cards)
    ivy = put(s, 'Ivy, Gleeful Spellthief')
    bear = put(s, 'Grizzly Bears', pid='p2')
    to_phase(s, 'main1', 2)
    source = cast(s, 'Rancor', [bear.id], pid='p2')
    cast(s, 'Counterspell', [source.id], pid='p3')
    while len(s.state.zones.get('stack', [])) > 1:
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type='pass_priority')
    settle(s)
    assert s.state.rules.decision
    cold(s, tmp_path, f'''finish(s)
assert pt(s,s.state.cards[{ivy.id!r}])==(4,1)
auras=[c for c in s.state.cards.values() if c.name=='Rancor' and c.zone.endswith(':battlefield')]
assert len(auras)==1 and auras[0].is_token and auras[0].attached_to=={ivy.id!r}
assert pt(s,s.state.cards[{bear.id!r}])==(2,2)''')


def test_genuine_cold_hive_each_other_controller_retargets_own_copy(cards, tmp_path):
    s = setup(cards)
    put(s, 'Hive Mind')
    cast(s, 'Lightning Bolt', ['p3'])
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.player == 'p2'
    cold(s, tmp_path, '''finish(s,['p1'])
assert s.state.players['p1'].life==34 and s.state.players['p3'].life==37''')


def test_genuine_cold_jaya_watches_next_loyalty_once_and_expires_this_turn(cards, tmp_path):
    s = setup(cards)
    phoenix = put(s, "Jaya's Phoenix")
    to_phase(s, 'declare_attackers', 1)
    attack(s, (phoenix, 'p2'))
    to_phase(s, 'main2', 1)
    finish(s)
    source = cast(s, 'Jace Beleren')
    finish(s)
    cold(s, tmp_path, f'''before={{p:len(s.state.zones[p+':hand']) for p in ['p1','p2','p3']}}
wait_priority(s,'p1')
act(s,'p1',type='activate_ability',card_id={source.id!r},ability=0,sources=[])
finish(s)
assert all(len(s.state.zones[p+':hand'])==n+2 for p,n in before.items())
to_phase(s,'main1',4)
before={{p:len(s.state.zones[p+':hand']) for p in ['p1','p2','p3']}}
wait_priority(s,'p1')
act(s,'p1',type='activate_ability',card_id={source.id!r},ability=0,sources=[])
finish(s)
assert all(len(s.state.zones[p+':hand'])==n+1 for p,n in before.items())''')
