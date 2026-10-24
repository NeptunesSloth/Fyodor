"""Native alternative and upkeep taxes retain actual payers and affected objects."""
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
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Lim-Dûl's Hex", 'Thrull Wizard', 'Erosion', 'Slow Motion', 'Soul Tithe', 'In the Eye of Chaos', 'Draco']
DATA = json.loads((Path(__file__).parent / 'fixtures/upkeep_tax79_cards.json').read_text())
ALL = [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves', 'Lightning Bolt', 'Counterspell', 'Forest', 'Island', 'Mountain']


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


def choose(s, ids, resolve=True):
    d = s.state.rules.decision
    assert d
    result = act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    if resolve:
        settle(s)
    return result


def cast(s, name, targets=(), pid='p1', resolve=True, **extra):
    c = put(s, name, 'hand', pid)
    wait_priority(s, pid)
    act(s, pid, type='add_mana', player=pid, mana={'C': 30, 'W': 4, 'U': 5, 'R': 2, 'B': 3, 'G': 3})
    act(s, pid, type='cast_spell', card_id=c.id, targets=list(targets), sources=[], **extra)
    if resolve:
        settle(s)
    return c


@pytest.mark.parametrize('name', [n for i, n in enumerate(NAMES) if i != 5])
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def aura_game(cards, name):
    s = game(cards)
    host = put(s, 'Forest' if name == NAMES[2] else 'Grizzly Bears', 'battlefield', 'p2')
    aura = cast(s, name, [host.id])
    assert s.state.cards[aura.id].attached_to == host.id
    to_phase(s, 'upkeep', 2)
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 5})
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.player == 'p2'
    return s, aura, host


@pytest.mark.parametrize('name,pick', [(NAMES[2], 'pay:0'), (NAMES[2], 'pay:1'), (NAMES[2], 'decline'),
                                      (NAMES[3], 'pay'), (NAMES[3], 'decline'), (NAMES[4], 'pay'), (NAMES[4], 'decline')])
def test_aura_actual_cast_and_affected_players_upkeep_alternative_or_sacrifice(cards, name, pick):
    s, aura, host = aura_game(cards, name)
    choose(s, [pick])
    if pick == 'decline':
        assert s.state.cards[host.id].zone == 'p2:graveyard'
        assert s.state.cards[aura.id].zone == ('p1:hand' if name == NAMES[3] else 'p1:graveyard')
    else:
        assert s.state.cards[host.id].zone == 'p2:battlefield'
    assert s.state.players['p2'].life == (39 if pick == 'pay:1' else 40)
    assert s.state.players['p1'].life == 40
    roundtrip(s)


@pytest.mark.parametrize('name', [NAMES[3], NAMES[4]])
def test_original_upkeep_player_cannot_sacrifice_creature_after_controller_changes(cards, name):
    s, aura, host = aura_game(cards, name)
    act(s, 'p2', type='set_controller', card_ids=[host.id], player='p3')
    assert s.state.rules.decision.player == 'p2'
    choose(s, ['decline'])
    assert s.state.cards[host.id].zone == 'p3:battlefield' and s.state.cards[aura.id].attached_to == host.id
    roundtrip(s)


def test_tithe_reads_current_mana_value_of_native_artifact_host(cards):
    s = game(cards)
    host = put(s, 'Sol Ring', 'battlefield', 'p2')
    cast(s, NAMES[4], [host.id])
    to_phase(s, 'upkeep', 2)
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1})
    settle(s)
    assert s.state.rules.decision.resume['opt']['cost'] == '{1}'
    choose(s, ['pay'])
    assert s.state.cards[host.id].zone == 'p2:battlefield' and not s.state.players['p2'].mana
    roundtrip(s)


@pytest.mark.parametrize('pay', [False, True])
def test_draco_whole_actual_domain_cast_then_current_domain_upkeep_payment(cards, pay):
    s = game(cards)
    lands = [put(s, n, 'battlefield') for n in ['Tropical Island', 'Savannah', 'Badlands']]
    source = cast(s, NAMES[6])
    record = s.state.rules.payments[Plan(s.state, 'p1', cards, None).oid(source.id)]
    assert record.mana_spent == {'C': 6}
    assert 'flying' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).keywords
    # Remove all actual land types before the next upkeep: ten is recomputed at resolution.
    act(s, 'p1', type='move', card_ids=[c.id for c in lands], to={'player': 'p1', 'zone': 'graveyard'})
    to_phase(s, 'upkeep', 4)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 10})
    settle(s)
    assert s.state.rules.decision and s.state.rules.decision.resume['opt']['cost'] == '{10}'
    choose(s, ['pay' if pay else 'decline'])
    assert s.state.cards[source.id].zone == ('p1:battlefield' if pay else 'p1:graveyard')
    roundtrip(s)


def test_hex_native_each_player_selects_own_alternative_before_any_damage(cards):
    s = game(cards)
    cast(s, NAMES[0])
    to_phase(s, 'upkeep', 4)
    act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 3})
    settle(s)
    assert s.state.rules.decision.player == 'p1'
    choose(s, ['pay:0'])
    assert s.state.rules.decision.player == 'p2' and s.state.players['p3'].life == 40
    assert {o.id for o in s.state.rules.decision.options} == {'pay:1', 'decline'}
    choose(s, ['pay:1'])
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [40, 40, 39]
    roundtrip(s)


def test_hex_unpaid_damage_is_one_native_batch_and_replacement_doubles_each(cards):
    s = game(cards)
    cast(s, NAMES[0])
    put(s, 'Furnace of Rath', 'battlefield')
    to_phase(s, 'upkeep', 4)
    settle(s)
    assert [s.state.players[p].life for p in ('p1', 'p2', 'p3')] == [38, 38, 38]
    facts = [e for e in s.state.rules.events if e.kind == 'damage' and e.player in {'p1', 'p2', 'p3'}]
    assert len(facts) == 3 and len({e.batch for e in facts}) == 1
    roundtrip(s)


def wizard_spell(cards, resource):
    s = game(cards)
    wizard = cast(s, NAMES[1])
    act(s, 'p2', type='set_prefs', hold_priority=True)
    target = cast(s, 'Dark Ritual', pid='p2', resolve=False)
    act(s, 'p2', type='clear_mana', player='p2')
    act(s, 'p2', type='add_mana', player='p2', mana=resource)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=wizard.id, ability=0, targets=[target.id], sources=[])
    settle(s)
    return s, wizard, target


@pytest.mark.parametrize('pick,resource', [('pay:0', {'B': 1}), ('pay:1', {'C': 3}), ('decline', {'B': 1, 'C': 3})])
def test_wizard_actual_cast_and_activation_native_black_or_three_tax(cards, pick, resource):
    s, wizard, target = wizard_spell(cards, resource)
    assert s.state.rules.decision and s.state.rules.decision.player == 'p2'
    choose(s, [pick])
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    from app.rules.mana_units import visible_pool
    assert visible_pool(s.state, 'p2') == (resource if pick == 'decline' else {'B': 3})
    assert s.state.cards[wizard.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_wizard_repeated_native_activations_require_independent_black_and_generic_payments(cards):
    s, wizard, target = wizard_spell(cards, {'B': 1, 'C': 3})
    choose(s, ['pay:0'], resolve=False)
    assert s.state.cards[target.id].zone == 'stack'
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=wizard.id, ability=0, targets=[target.id], sources=[])
    settle(s)
    assert {o.id for o in s.state.rules.decision.options} == {'pay:1', 'decline'}
    choose(s, ['pay:1'])
    from app.rules.mana_units import visible_pool
    assert visible_pool(s.state, 'p2') == {'B': 3} and s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_wizard_target_black_spell_rejects_red_spell_without_paying_activation_cost(cards):
    from app.game.errors import ActionError
    s = game(cards)
    wizard = cast(s, NAMES[1])
    target = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    wait_priority(s, 'p1')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=wizard.id, ability=0, targets=[target.id], sources=[])
    assert s.state.model_dump_json() == before
    settle(s)
    assert s.state.players['p1'].life == 37
    roundtrip(s)




@pytest.mark.parametrize('pay', [False, True])
def test_tithe_native_zero_mana_value_token_cost_is_known_zero_not_missing_metadata(cards, pay):
    s = game(cards)
    cast(s, 'Midnight Haunting', pid='p2')
    token = next(c for c in s.state.cards.values() if c.is_token and c.zone == 'p2:battlefield' and c.name == 'Spirit')
    aura = cast(s, NAMES[4], [token.id])
    to_phase(s, 'upkeep', 2)
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p2' and d.resume.get('opt') and d.resume['opt']['cost'] == '{0}'
    choose(s, ['pay' if pay else 'decline'])
    if pay:
        assert s.state.cards[token.id].zone == 'p2:battlefield' and s.state.cards[aura.id].zone == 'p1:battlefield'
    else:
        assert token.id not in s.state.cards and s.state.cards[aura.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('name', [NAMES[2], NAMES[3], NAMES[4]])
def test_upkeep_receipt_keeps_original_host_after_actual_aura_attachment_changes(cards, name):
    s, aura, old = aura_game(cards, name)
    other = put(s, 'Island' if name == NAMES[2] else 'Llanowar Elves', 'battlefield', 'p2')
    act(s, 'p1', type='attach', card_ids=[aura.id], to=other.id)
    choose(s, ['decline'])
    assert s.state.cards[old.id].zone == 'p2:graveyard'
    assert s.state.cards[other.id].zone == 'p2:battlefield'
    assert s.state.cards[aura.id].zone == 'p1:battlefield' and s.state.cards[aura.id].attached_to == other.id
    roundtrip(s)


@pytest.mark.parametrize('name', [NAMES[2], NAMES[3], NAMES[4]])
def test_legacy_missing_original_upkeep_object_uses_explicit_manual_not_current_host_or_zero(cards, name):
    from app.game.session import GameSession
    from app.game.state import GameState
    s = game(cards)
    host = put(s, 'Forest' if name == NAMES[2] else 'Grizzly Bears', 'battlefield', 'p2')
    aura = cast(s, name, [host.id])
    to_phase(s, 'upkeep', 2)
    entry = next(e for e in s.state.rules.stack.values() if e.source_card == aura.id)
    assert entry.event and entry.event.objects
    entry.event.objects = []  # Faithful old-save omission, not invented current-host history.
    s = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    settle(s)
    d = s.state.rules.decision
    assert d and d.kind == 'manual_resolution' and d.resume['step'] == 'tax_event_known79'
    choose(s, ['done'])
    assert s.state.cards[host.id].zone == 'p2:battlefield' and s.state.players['p2'].life == 40


@pytest.mark.parametrize('name', [n for i, n in enumerate(NAMES) if i != 5])
def test_genuine_cold_pending_tax_keeps_original_payer_amount_source_and_native_cost(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    if name in NAMES[2:5]:
        s, source, host = aura_game(cards, name)
    elif name == NAMES[1]:
        s, source, host = wizard_spell(cards, {'B': 1})
    else:
        s = game(cards)
        if name == NAMES[6]:
            for land in ['Tropical Island', 'Savannah', 'Badlands']:
                put(s, land, 'battlefield')
        source = cast(s, name)
        host = source
        to_phase(s, 'upkeep', 4)
        if name == NAMES[0]:
            act(s, 'p1', type='add_mana', player='p1', mana={'B': 1})
            act(s, 'p2', type='add_mana', player='p2', mana={'C': 3})
        settle(s)
    assert s.state.rules.decision is not None and s.state.rules.decision.resume.get('opt')
    saved = tmp_path / 'pending-tax.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.mana_units import visible_pool
from tests.game_helpers import act
from tests.test_rules_library_look import settle
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
name,source,host=sys.argv[3:]
def pick(value):
 d=s.state.rules.decision
 assert d and d.kind!='manual_resolution'
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[value])
 settle(s)
if name=="Lim-Dûl's Hex":
 pick('pay:0');pick('pay:1')
 assert [s.state.players[p].life for p in ['p1','p2','p3']]==[40,40,39]
elif name=='Thrull Wizard':
 pick('pay:0')
 assert visible_pool(s.state,'p2')=={'B':3} and s.state.cards[host].zone=='p2:graveyard'
elif name=='Erosion':
 pick('pay:1')
 assert s.state.players['p2'].life==39 and s.state.cards[host].zone=='p2:battlefield'
elif name=='Draco':
 assert s.state.rules.decision.resume['opt']['cost']=='{0}'
 pick('pay')
 assert s.state.cards[source].zone=='p1:battlefield'
else:
 pick('decline')
 assert s.state.cards[host].zone=='p2:graveyard'
 assert s.state.cards[source].zone==('p1:hand' if name=='Slow Motion' else 'p1:graveyard')
assert s.state.rules.decision is None
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, source.id, host.id],
                            capture_output=True, text=True, timeout=90, env=os.environ.copy())
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('name', [NAMES[2], NAMES[3], NAMES[4]])
def test_erosion_destroys_but_other_taxes_sacrifice_through_actual_indestructibility(cards, name):
    s = game(cards)
    host = put(s, 'Forest' if name == NAMES[2] else 'Grizzly Bears', 'battlefield', 'p2')
    aura = cast(s, name, [host.id])
    to_phase(s, 'upkeep', 2)
    cast(s, 'Heroic Intervention', pid='p2')
    assert s.state.rules.decision and s.state.rules.decision.player == 'p2'
    choose(s, ['decline'])
    assert s.state.cards[host.id].zone == ('p2:battlefield' if name == NAMES[2] else 'p2:graveyard')
    assert s.state.cards[aura.id].zone == ('p1:battlefield' if name == NAMES[2] else 'p1:hand' if name == NAMES[3] else 'p1:graveyard')
    roundtrip(s)


def test_wizard_black_uncounterable_spell_can_decline_without_being_countered(cards):
    s = game(cards)
    wizard = cast(s, NAMES[1])
    victim = put(s, 'Sol Ring', 'battlefield')
    spell = cast(s, 'Abrupt Decay', [victim.id], pid='p2', resolve=False)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=wizard.id, ability=0, targets=[spell.id], sources=[])
    settle(s)
    choose(s, ['decline'])
    assert s.state.cards[victim.id].zone == 'p1:graveyard' and s.state.cards[spell.id].zone == 'p2:graveyard'
    roundtrip(s)
