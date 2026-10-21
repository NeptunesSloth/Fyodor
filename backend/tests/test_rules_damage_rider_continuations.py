"""Low-level prevention continuation contracts; no new card grammar admission."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.rules import damage_rider_continuations as queue
from app.rules import effects, replace
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_abundance import set_library, setup
from tests.test_rules_designations import put, roundtrip, settle


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = json.loads((Path(__file__).parent / 'fixtures/prevention_outcomes_cards.json').read_text())
    for i, data in enumerate(rows):
        base[data['name']] = card(data['name'], set_code='pvo', number=str(i), **{k: v for k, v in data.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def frame(plan, source, *, draw):
    def rider(body):
        return {'rider': {'effects': body}, 'ev': {'target': 'p1', 'src': {'controller': 'p2'}},
                'n': 2, 'by': 'p1', 'card': source.id, 'oid': plan.oid(source), 'name': source.name}
    tail = {'controller': 'p1', 'source_card': source.id, 'source_object': plan.oid(source),
            'name': source.name, 'effects': [{'do': 'gain_life', 'who': 'you', 'n': 7}],
            'next': 0, 'stack_id': '', 'body_done': {'do': 'noop'}}
    body = ([{'do': 'draw', 'who': 'you', 'n': 1}] if draw else []) + [
        {'do': 'gain_life', 'who': 'you', 'n': 2}]
    return queue.DamageRiderFrame([rider(body), rider([{'do': 'gain_life', 'who': 'you', 'n': 3}])],
                                 {'do': 'continue', 'ctx': tail})


def test_synchronous_queue_does_not_dispatch_callers_terminal(cards):
    s = setup(cards)
    source = put(s, 'Revitalize', 'graveyard')
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    saved = frame(plan, source, draw=False)
    assert queue.run(plan, saved)
    assert plan.state.players['p1'].life == 45
    replace.run_then(plan, saved.then)
    assert plan.state.players['p1'].life == 52


def test_paused_body_resumes_remaining_body_riders_and_real_terminal_once(cards):
    s = setup(cards)
    source = put(s, 'Revitalize', 'graveyard')
    put(s, 'Abundance', 'battlefield')
    top = set_library(s, ['Forest', 'Lightning Bolt'])
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    assert not queue.run(plan, frame(plan, source, draw=True))
    s = GameSession(plan.state, cards=cards)
    assert s.state.players['p1'].life == 40
    roundtrip(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.cards[top[0]].zone == 'p1:hand'
    assert s.state.players['p1'].life == 52
    assert s.state.rules.decision is None
    roundtrip(s)


def test_joined_damage_and_bound_amount_tail_wait_for_immediate_prevention_draw(cards):
    """An injected descriptor exercises the native foundation, not printed card support."""
    s = setup(cards)
    source = put(s, 'Lightning Bolt', 'hand')
    put(s, 'Abundance', 'battlefield')
    set_library(s, ['Forest', 'Lightning Bolt'])
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    replace.add_record(plan, controller='p1', label='Prototype prevention', event='damage', match={'to': {'players': 'you'}},
                       op={'do': 'prevent_all', 'prevention': True,
                        'rider': {'effects': [{'do': 'draw', 'who': 'you', 'n': 1}]}},
                       until='eot', source_card=source.id, source=plan.oid(source))
    ctx = {'controller': 'p1', 'source_card': source.id, 'source_object': plan.oid(source),
           'name': source.name, 'stack_id': '', 'next': 0, 'body_done': {'do': 'noop'},
           'effects': [{'do': 'damage', 'who': 'player:p1', 'n': 1, 'with_next': True},
                       {'do': 'damage', 'who': 'player:p2', 'n': 1},
                       {'do': 'gain_life', 'who': 'you', 'n': 9}]}
    effects.continue_effects(plan, ctx)
    s = GameSession(plan.state, cards=cards)
    assert s.state.players['p1'].life == 40
    assert s.state.players['p2'].life == 39
    roundtrip(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
    settle(s)
    assert s.state.players['p1'].life == 49
    assert s.state.players['p2'].life == 39  # joined second instruction was not replayed
    assert s.state.rules.decision is None


def test_actual_pestilence_protection_and_furnace_offer_native_order(cards):
    from tests.test_rules_damage_redirection import activate
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Pestilence', 'White Knight', 'Furnace of Rath'], ['Forest'], ['Forest'])
    knight = put(s, 'White Knight', 'battlefield')
    put(s, 'Furnace of Rath', 'battlefield')
    source = put(s, 'Pestilence', 'battlefield')
    activate(s, source, 'deals 1 damage')
    d = s.state.rules.decision
    assert d is not None, 'Protection and Furnace must both be eligible at the damage frontier'
    assert d.player == 'p1'
    assert any('protection' in o.label.lower() for o in d.options)
    assert s.state.cards[knight.id].damage == 0


@pytest.mark.parametrize('accept', [True, False])
def test_external_optional_controller_chooses_only_after_affected_players_order(cards, accept):
    from app.rules import selectors
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Blood of the Martyr'], ['Grizzly Bears'], ['Lightning Bolt', 'Furnace of Rath'])
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    gift = put(s, 'Blood of the Martyr', 'graveyard')
    source = put(s, 'Lightning Bolt', 'hand', 'p3')
    put(s, 'Furnace of Rath', 'battlefield', 'p3')
    plan = Plan(s.state.model_copy(deep=True), 'p3', cards, None)
    creature = selectors.parse('creatures')
    replace.add_record(plan, controller='p1', label=gift.name, event='damage',
                               source=plan.oid(gift), source_card=gift.id,
                               match={'to': {'objects': {'sel': creature.key()}}},
                               op={'do': 'redirect', 'to': 'pid', 'pid': 'p1',
                                   'optional': True, 'external_optional': True})
    ctx = {'controller': 'p3', 'source_card': source.id, 'source_object': plan.oid(source),
           'name': source.name, 'stack_id': '', 'next': 0, 'body_done': {'do': 'noop'},
           'targets': [{'id': victim.id, 'object_id': plan.oid(victim)}],
           'effects': [{'do': 'damage', 'who': 'target', 'n': 3}]}
    effects.continue_effects(plan, ctx)
    s = GameSession(plan.state, cards=cards)
    d = s.state.rules.decision
    assert d.player == 'p2'  # original affected controller owns616 ordering
    furnace = next(o.id for o in d.options if 'Furnace of Rath' in o.label)
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=[furnace])
    d = s.state.rules.decision
    assert d.player == 'p1'  # the printed YOU owns only the optional application
    roundtrip(s)
    act(s, 'p1', type='choose', decision_id=d.id,
        option_ids=[next(o.id for o in d.options if o.id != 'decline') if accept else 'decline'])
    settle(s)
    assert s.state.players['p1'].life == (34 if accept else 40)
    assert s.state.cards[victim.id].zone.endswith(':battlefield' if accept else ':graveyard')


@pytest.mark.parametrize('first,total', [('Furnace of Rath', 2), ('protection', 1)])
def test_prevention_receipts_are_pure_until_commit_and_count_chosen_order(cards, first, total):
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['White Knight', 'Furnace of Rath', 'Pestilence'], ['Forest'], ['Forest'])
    knight = put(s, 'White Knight', 'battlefield')
    put(s, 'Furnace of Rath', 'battlefield')
    source = put(s, 'Pestilence', 'battlefield')
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    events = [{'source_card': source.id, 'source_oid': plan.oid(source), 'target': knight.id,
               'amount': 1, 'combat': False,
               'src': replace.source_info(plan, source.id, plan.oid(source), plan.ch(source), 'p1')}]
    ask = replace.damage_outcome(plan, events, answers={}, order=None, ask=True)
    assert isinstance(ask, replace.Ask)
    assert not any(e.kind == 'damage_prevented' for e in plan.rules.events)
    chosen = next(c.id for c in ask.applicable if first in c.label)
    out = replace.damage_outcome(plan, events, answers={ask.fp: chosen}, order=None, ask=True)
    assert isinstance(out, replace.DamageOutcome)
    assert sum(r['amount'] for r in out.preventions) == total
    assert not any(e.kind == 'damage_prevented' for e in plan.rules.events)
    assert replace.do_damage(plan, out, actor='p1', combat=False)
    receipts = [e for e in plan.rules.events if e.kind == 'damage_prevented']
    assert len(receipts) == 1 and receipts[0].amount == total
    assert receipts[0].source == plan.oid(source)
    assert receipts[0].object_id == plan.oid(knight)
    assert receipts[0].prevention['source']['colors'] == ['B']


def pain_payment_pending(cards):
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_shared_damage_choices import table

    names = ['Llanowar Wastes', 'Grizzly Bears', 'Abundance', 'Forest', 'Lightning Bolt', 'Revitalize']
    s = table(cards, names, ['Forest'], ['Forest'])
    source = put(s, 'Llanowar Wastes', 'battlefield')
    spell = put(s, 'Grizzly Bears', 'hand')
    gift = put(s, 'Revitalize', 'graveyard')
    put(s, 'Abundance', 'battlefield')
    top = set_library(s, ['Forest', 'Lightning Bolt'])
    mana(s, C=1)
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    replace.add_record(plan, controller='p1', label='Injected foundation rider', event='damage',
                       source=plan.oid(gift), source_card=gift.id, match={'to': {'players': 'you'}},
                       op={'do': 'prevent_all', 'prevention': True,
                           'rider': {'effects': [{'do': 'draw', 'who': 'you', 'n': 1}]}})
    s = GameSession(plan.state, cards=cards)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[source.id])
    assert s.state.cards[source.id].tapped
    assert spell.id not in s.state.rules.stack
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 0
    assert s.state.players['p1'].life == 40
    assert s.state.rules.decision is not None
    return s, spell.id, top[0]


def test_true_pain_mana_payment_waits_for_prevention_body_and_commits_spell_once(cards):
    s, spell, top = pain_payment_pending(cards)
    roundtrip(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['decline'])
    assert s.state.cards[top].zone == 'p1:hand'
    assert s.state.cards[spell].zone == 'stack'
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 1
    settle(s)
    assert s.state.cards[spell].zone == 'p1:battlefield'
    roundtrip(s)


def combat_pending(cards):
    from tests.test_rules_damage_redirection import attack, damage
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Revitalize', 'Abundance', 'Forest', 'Lightning Bolt'],
              ['Grizzly Bears', 'Forest', 'Island'], ['Forest', 'Island'])
    gift = put(s, 'Revitalize', 'graveyard')
    put(s, 'Abundance', 'battlefield')
    attacker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=2)
    top = set_library(s, ['Forest', 'Lightning Bolt'])
    act(s, 'p1', type='set_monarch', player='p1')
    plan = Plan(s.state.model_copy(deep=True), 'p1', cards, None)
    replace.add_record(plan, controller='p1', label='Injected combat rider', event='damage',
                       source=plan.oid(gift), source_card=gift.id, match={'to': {'players': 'you'}},
                       op={'do': 'prevent', 'n': 1, 'prevention': True,
                           'rider': {'effects': [{'do': 'draw', 'who': 'you', 'n': 1}]}})
    s = GameSession(plan.state, cards=cards)
    attack(s, [attacker], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.rules.decision is not None
    assert s.state.players['p1'].life == 39
    assert s.state.table.monarch == 'p1'
    assert not any(t.name == 'The Monarch' for t in s.state.rules.pending_triggers)
    return s, attacker.id, top[0]


def sba_pending(cards):
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Revitalize', 'Abundance', 'Forest', 'Lightning Bolt', 'Grizzly Bears'],
              ['Lightning Bolt'], ['Forest'])
    gift = put(s, 'Revitalize', 'graveyard')
    put(s, 'Abundance', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    source = put(s, 'Lightning Bolt', 'hand', 'p2')
    top = set_library(s, ['Forest', 'Lightning Bolt'])
    plan = Plan(s.state.model_copy(deep=True), 'p2', cards, None)
    replace.add_record(plan, controller='p1', label='Injected immediate counter rider', event='damage',
                       source=plan.oid(gift), source_card=gift.id,
                       match={'to': {'objects': {'oids': [plan.oid(victim)]}}},
                       op={'do': 'prevent', 'n': 1, 'prevention': True,
                           'rider': {'effects': [{'do': 'draw', 'who': 'you', 'n': 1},
                                                {'do': 'add_counters', 'who': 'ref:to', 'kind': '+1/+1', 'n': 1}]}})
    ctx = {'controller': 'p2', 'source_card': source.id, 'source_object': plan.oid(source),
           'name': source.name, 'stack_id': '', 'next': 0, 'body_done': {'do': 'noop'},
           'targets': [{'id': victim.id, 'object_id': plan.oid(victim)}],
           'effects': [{'do': 'damage', 'who': 'target', 'n': 3}]}
    effects.continue_effects(plan, ctx)
    s = GameSession(plan.state, cards=cards)
    assert s.state.rules.decision is not None
    assert s.state.cards[victim.id].zone.endswith(':battlefield')
    assert s.state.cards[victim.id].damage == 2  # lethal pending its immediate additional effect
    return s, victim.id, top[0]


@pytest.mark.parametrize('stage', ['pain', 'combat', 'sba'])
def test_native_damage_rider_cold_resume_preserves_callers_terminal(cards, tmp_path, stage):
    import subprocess
    import sys

    s, subject, top = {'pain': pain_payment_pending, 'combat': combat_pending, 'sba': sba_pending}[stage](cards)
    saved = tmp_path / f'{stage}.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
save,db,stage,subject,top=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
d=s.state.rules.decision
act(s,'p1',type='choose',decision_id=d.id,option_ids=['decline'])
assert s.state.cards[top].zone=='p1:hand'
if stage=='pain':
 assert s.state.cards[subject].zone=='stack'
 assert s.state.rules.spells_this_turn('p1',s.state.turn.number)==1
settle(s)
if stage=='pain':assert s.state.cards[subject].zone=='p1:battlefield'
elif stage=='combat':
 assert s.state.table.monarch=='p2'
 assert s.state.players['p1'].life==39
else:
 assert s.state.cards[subject].zone=='p1:battlefield'
 assert s.state.cards[subject].damage==2
 assert s.state.cards[subject].counters.get('+1/+1')==1
assert s.state.rules.decision is None
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), stage, subject, top],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
