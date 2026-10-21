"""Production whole-card and fresh-process proofs for batch42."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_immortal_coil_outcomes import settle
from tests.test_rules_prevention_outcomes import activate, cast, choose
from tests.test_rules_shared_damage_choices import table

DATA = json.loads((Path(__file__).parent / 'fixtures/prevention_outcomes_cards.json').read_text())
DATA += json.loads((Path(__file__).parent / 'fixtures/life_prevention_outcomes42_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='lp42', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names = list(dict.fromkeys(c['name'] for c in DATA))
    return table(cards, names, names, names)


def life(s, amount):
    act(s, 'p1', type='life', player='p1', delta=amount - s.state.players['p1'].life)


def enter_transcendence(s):
    source = cast(s, 'Transcendence', resolve=False)
    for _ in range(12):
        if s.state.cards[source.id].zone == 'p1:battlefield':
            return s.state.cards[source.id]
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('Transcendence did not enter')


def nemesis_hit(s):
    source = put(s, 'Screaming Nemesis', 'battlefield')
    cast(s, 'Lightning Bolt', [source.id], pid='p2', resolve=False)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    return source


@pytest.mark.parametrize('name', ['Transcendence', 'Screaming Nemesis', 'Flames of the Blood Hand'])
def test_staged_whole_card_native_coverage(cards, name):
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts


@pytest.mark.parametrize('starting,after', [(10, 13), (2, 5)])
def test_transcendence_genuine_loss_trigger_gains_twice_and_survives_negative_life(cards, starting, after):
    s = game(cards)
    life(s, starting)
    enter_transcendence(s)
    cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    settle(s)
    assert not s.state.rules.lost and s.state.players['p1'].life == after
    roundtrip(s)


def test_transcendence_twenty_state_loop_waits_for_response_round_and_draws(cards):
    s = game(cards)
    life(s, 20)
    put(s, 'Platinum Angel', 'battlefield')
    enter_transcendence(s)
    assert s.state.zones['stack'] and s.state.rules.draw_reason is None
    roundtrip(s)
    settle(s)
    assert s.state.rules.draw_reason == 'Mandatory state-trigger loop (104.4b, 732.4)'


def test_transcendence_state_loss_still_resolves_after_response_drops_below_twenty(cards):
    s = game(cards)
    life(s, 20)
    enter_transcendence(s)
    cast(s, 'Skullcrack', ['p1'], pid='p2', resolve=False)
    settle(s)
    assert 'p1' in s.state.rules.lost and s.state.rules.draw_reason is None


def test_transcendence_native_response_breaks_blocked_loop_by_changing_condition(cards):
    s = game(cards)
    life(s, 20)
    put(s, 'Platinum Angel', 'battlefield')
    enter_transcendence(s)
    cast(s, 'Skullcrack', ['p1'], pid='p2', resolve=False)
    settle(s)
    assert s.state.players['p1'].life == 17 and not s.state.rules.lost
    assert s.state.rules.draw_reason is None and not s.state.zones.get('stack')


def test_transcendence_copy_above_murder_above_original_does_not_prematurely_draw(cards):
    s = game(cards)
    angel = put(s, 'Platinum Angel', 'battlefield')
    copier = put(s, 'Lithoform Engine', 'battlefield')
    enter_transcendence(s)
    original = s.state.zones['stack'][-1]
    cast(s, 'Murder', [angel.id], pid='p2', resolve=False)
    activate(s, copier, 'Copy target activated', [original], resolve=False)
    roundtrip(s)
    settle(s)
    assert 'p1' in s.state.rules.lost and s.state.rules.draw_reason is None


def test_nemesis_lethal_damage_uses_original_source_and_locks_actual_player(cards):
    s = game(cards)
    source = nemesis_hit(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)
    choose(s, ['p2'])
    assert s.state.players['p2'].life == 37
    assert [r['player'] for r in s.state.rules.cant_gain] == ['p2']
    before = len(s.state.zones['p2:hand'])
    cast(s, 'Revitalize', pid='p2')
    assert s.state.players['p2'].life == 37
    assert len(s.state.zones['p2:hand']) == before + 1  # helper moves spell to hand; native spell draws one
    assert s.state.rules.cant_gain[0]['turn'] is None
    roundtrip(s)


def test_nemesis_new_incarnation_is_other_and_creature_damage_locks_no_player(cards):
    s = game(cards)
    copier = put(s, 'Lithoform Engine', 'battlefield')
    original_target = put(s, 'Centaur Courser', 'battlefield', 'p2')
    other_target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    source = nemesis_hit(s)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[original_target.id])
    original = s.state.zones['stack'][-1]
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    activate(s, copier, 'Copy target activated', [original])
    assert source.id in {o.id for o in s.state.rules.decision.options}
    roundtrip(s)
    choose(s, [source.id])
    # Damage to the new incarnation independently triggers its own printed ability.
    choose(s, [other_target.id])
    assert not s.state.rules.cant_gain and not s.state.zones.get('stack')


def test_flames_unpreventable_damage_replaces_gain_but_keeps_other_spell_effects(cards):
    s = game(cards)
    cast(s, 'Comeuppance', pid='p2')
    cast(s, 'Flames of the Blood Hand', ['p2'])
    assert s.state.players['p2'].life == 36
    before = len(s.state.zones['p2:hand'])
    cast(s, 'Revitalize', pid='p2')
    assert s.state.players['p2'].life == 36 and len(s.state.zones['p2:hand']) == before + 1
    assert not s.state.rules.cant_gain  # replacement, never a prohibition
    cast(s, 'Revitalize', pid='p3')
    assert s.state.players['p3'].life == 43
    roundtrip(s)


def test_flames_dying_planeswalker_controller_is_frozen_before_damage(cards):
    s = game(cards)
    walker = put(s, 'Narset, Parter of Veils', 'battlefield', 'p2')
    act(s, 'p2', type='counter', card_ids=[walker.id], kind='loyalty', delta=3 - s.state.cards[walker.id].counters.get('loyalty', 0))
    cast(s, 'Flames of the Blood Hand', [walker.id])
    assert s.state.cards[walker.id].zone == 'p2:graveyard'
    cast(s, 'Revitalize', pid='p2')
    assert s.state.players['p2'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('choose_flames,expected', [(True, 36), (False, 33)])
def test_flames_replacement_competes_with_tainted_remedy_through_normal_616(cards, choose_flames, expected):
    s = game(cards)
    put(s, 'Tainted Remedy', 'battlefield')
    cast(s, 'Flames of the Blood Hand', ['p2'])
    cast(s, 'Revitalize', pid='p2')
    d = s.state.rules.decision
    assert d.player == 'p2'
    desired = 'Flames of the Blood Hand' if choose_flames else 'Tainted Remedy'
    answer = next(o.id for o in d.options if desired in o.label)
    roundtrip(s)
    choose(s, [answer])
    assert s.state.players['p2'].life == expected and not s.state.rules.cant_gain


def test_transcendence_life_loss_without_damage_creates_the_same_genuine_gain_trigger(cards):
    s = game(cards)
    life(s, 10)
    enter_transcendence(s)
    cast(s, 'Sign in Blood', ['p1'])
    assert s.state.players['p1'].life == 12  # lose2, then gain4
    assert not s.state.rules.lost
    roundtrip(s)


def test_nemesis_final_redirected_split_binds_both_actual_players(cards):
    from app.rules import replace
    from app.rules.plan import Plan

    s = game(cards)
    nemesis_hit(s)
    plan = Plan(s.state, 'p1', cards, None)
    replace.add_record(plan, event='damage', match={'to': {'pids': ['p2']}},
                       op={'do': 'redirect', 'limit': 1, 'allocate': True, 'to': 'pid', 'pid': 'p3'},
                       controller='p3', source=None, source_card=None, label='Native split interference')
    s = GameSession(plan.state, cards=cards)
    choose(s, ['p2'])
    assert s.state.players['p2'].life == 38 and s.state.players['p3'].life == 39
    assert {r['player'] for r in s.state.rules.cant_gain} == {'p2', 'p3'}
    roundtrip(s)


def test_nemesis_prevented_damage_creates_no_life_lock(cards):
    s = game(cards)
    cast(s, 'Comeuppance', pid='p2')
    nemesis_hit(s)
    choose(s, ['p2'])
    assert s.state.players['p2'].life == 40 and not s.state.rules.cant_gain


def test_flames_redirects_damage_but_replaces_gain_only_for_original_target_player(cards):
    from app.rules import replace
    from app.rules.plan import Plan

    s = game(cards)
    plan = Plan(s.state, 'p1', cards, None)
    replace.add_record(plan, event='damage', match={'to': {'pids': ['p2']}},
                       op={'do': 'redirect', 'to': 'pid', 'pid': 'p3'},
                       controller='p3', source=None, source_card=None, label='Native redirect interference')
    s = GameSession(plan.state, cards=cards)
    cast(s, 'Flames of the Blood Hand', ['p2'])
    assert s.state.players['p2'].life == 40 and s.state.players['p3'].life == 36
    cast(s, 'Revitalize', pid='p2')
    cast(s, 'Revitalize', pid='p3')
    assert s.state.players['p2'].life == 40 and s.state.players['p3'].life == 39
    roundtrip(s)


@pytest.mark.parametrize('pause', ['state', 'gain', 'nemesis_target', 'nemesis_616', 'flames_616', 'flames_pw_616'])
def test_staged_native_continuations_resume_in_genuinely_fresh_process(cards, tmp_path, pause):
    import subprocess
    import sys

    from app.rules import replace
    from app.rules.plan import Plan

    s = game(cards)
    if pause in ('state', 'gain'):
        life(s, 20 if pause == 'state' else 10)
        if pause == 'state':
            put(s, 'Platinum Angel', 'battlefield')
        enter_transcendence(s)
        if pause == 'gain':
            cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
            for _ in range(12):
                if s.state.players['p1'].life == 7:
                    break
                act(s, s.state.rules.priority, type='pass_priority')
            assert s.state.zones['stack'] and s.state.players['p1'].life == 7
    elif pause.startswith('nemesis'):
        nemesis_hit(s)
        if pause == 'nemesis_616':
            put(s, 'Furnace of Rath', 'battlefield')
            plan = Plan(s.state, 'p1', cards, None)
            replace.add_record(plan, event='damage', match={'to': {'pids': ['p2']}},
                               op={'do': 'finite_prevention', 'prevention': True, 'limit': 1, 'allocate': True},
                               controller='p2', source=None, source_card=None, label='Native finite prevention')
            s = GameSession(plan.state, cards=cards)
            choose(s, ['p2'])
            assert s.state.rules.decision is not None
    else:
        put(s, 'Furnace of Rath', 'battlefield')
        target = 'p2'
        recipient_match = {'pids': ['p2']}
        if pause == 'flames_pw_616':
            walker = put(s, 'Narset, Parter of Veils', 'battlefield', 'p2')
            act(s, 'p2', type='counter', card_ids=[walker.id], kind='loyalty', delta=3)
            target = walker.id
            recipient_match = {'objects': {'oids': [Plan(s.state, 'p1', cards, None).oid(walker)]}}
        plan = Plan(s.state, 'p1', cards, None)
        replace.add_record(plan, event='damage', match={'to': recipient_match},
                           op={'do': 'redirect', 'limit': 1, 'allocate': True, 'to': 'pid', 'pid': 'p3'},
                           controller='p3', source=None, source_card=None, label='Native split interference')
        s = GameSession(plan.state, cards=cards)
        cast(s, 'Flames of the Blood Hand', [target])
        assert s.state.rules.decision is not None
    save = tmp_path / 'life42.json'
    save.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.state import GameState
from app.game.session import GameSession
from tests.game_helpers import act
save,db,pause=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
def answer(option):
 d=s.state.rules.decision
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[option])
def settle():
 for _ in range(80):
  if s.state.rules.draw_reason or s.state.rules.lost:return
  d=s.state.rules.decision
  if d and d.kind=='order':
   act(s,d.player,type='choose',decision_id=d.id,option_ids=[o.id for o in d.options])
  elif d is None and s.state.zones.get('stack'):
   act(s,s.state.rules.priority,type='pass_priority')
  else:return
 raise AssertionError('Unsettled native staged life stack')
if pause=='nemesis_target':answer('p2')
elif pause.endswith('616'):
 answer(next(o.id for o in s.state.rules.decision.options if 'Furnace of Rath' in o.label))
settle()
if pause=='state':
 assert s.state.rules.draw_reason=='Mandatory state-trigger loop (104.4b, 732.4)'
elif pause=='gain':
 assert s.state.players['p1'].life==13 and not s.state.rules.lost
elif pause.startswith('nemesis'):
 assert s.state.players['p2'].life==(35 if pause.endswith('616') else 37)
 assert [r['player'] for r in s.state.rules.cant_gain]==['p2']
else:
 assert s.state.players['p2'].life==(40 if pause=='flames_pw_616' else 33) and s.state.players['p3'].life==39
 if pause=='flames_pw_616':assert any(c.name=='Narset, Parter of Veils' and c.zone=='p2:graveyard' for c in s.state.cards.values())
 assert not s.state.rules.cant_gain
 rec=next(r for r in s.state.rules.replacements if r.get('event')=='life')
 assert rec['match']=={'players':['p2']} and rec['op']=={'do':'set','n':0}
assert s.state.rules.decision is None
repo.close()
"""
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), pause],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
