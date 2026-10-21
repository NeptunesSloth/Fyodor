"""Production native activation/payment flow for exact hand-to-library costs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_conditional_prevention_grants45 import DATA as BASE_DATA
from tests.test_rules_damage_redirection import activate, attack, cast, damage
from tests.test_rules_designations import put, settle
from tests.test_rules_prevention_outcomes import source_choice
from tests.test_rules_prevention_unpreventable44 import NAMES as BASE_NAMES
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase

DATA = [*BASE_DATA, *json.loads((Path(__file__).parent / 'fixtures/ordered_zone_costs46_cards.json').read_text())]
DATA.append(next(r for r in json.loads((Path(__file__).parent / 'fixtures/activation_payment_provenance_cards.json').read_text()) if r['name'] == 'Suppression Field'))
HAND_NAMES = ['Penance', 'Hidden Retreat', 'Leashling']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate(DATA):
        base[row['name']] = card(row['name'], set_code='o46', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



def game(cards):
    names = [*BASE_NAMES, *HAND_NAMES, 'Alms', "Nature's Kiss", 'Stifle', 'Counterspell', 'Suppression Field', 'Command Beacon']
    return table(cards, names, names, names)


def clear_hand(s):
    for cid in list(s.state.zones['p1:hand']):
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'library'}, position='bottom')


def announce(s, source, targets=()):
    wait_priority(s, 'p1')
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, targets=list(targets), sources=[])


@pytest.mark.parametrize('name', HAND_NAMES)
def test_actual_activation_pays_hidden_hand_card_to_library_top_before_native_body(cards, name):
    s = game(cards)
    source = put(s, name, 'battlefield')
    clear_hand(s)
    paid = put(s, 'Forest', 'hand')
    kept = put(s, 'Island', 'hand')
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False) if name != 'Leashling' else None
    announce(s, source, [bolt.id] if name == 'Hidden Retreat' else [])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'ability_cost'
    assert s.state.cards[paid.id].zone == 'p1:hand'
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[paid.id])
    settle(s)
    if name == 'Penance':
        source_choice(s, bolt)
    assert s.state.zones['p1:library'][0] == paid.id
    assert s.state.cards[kept.id].zone == 'p1:hand'
    assert paid.id not in s.state.zones['p1:graveyard']
    assert s.state.players['p1'].life == 40
    if name == 'Leashling':
        assert s.state.cards[source.id].zone == 'p1:hand'
    else:
        assert s.state.cards[bolt.id].zone == 'p2:graveyard', str(s.state.rules.decision) + str(s.state.rules.stack)


@pytest.mark.parametrize('name', HAND_NAMES)
def test_empty_hand_native_cost_rejects_atomically(cards, name):
    s = game(cards)
    source = put(s, name, 'battlefield')
    clear_hand(s)
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False) if name == 'Hidden Retreat' else None
    wait_priority(s, 'p1')
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=index,
            targets=[bolt.id] if bolt is not None else [], sources=[])
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize('name', HAND_NAMES)
def test_native_hand_cost_can_be_declined_without_payment_or_ability_creation(cards, name):
    s = game(cards)
    source = put(s, name, 'battlefield')
    clear_hand(s)
    paid = put(s, 'Forest', 'hand')
    put(s, 'Island', 'hand')
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False) if name == 'Hidden Retreat' else None
    announce(s, source, [bolt.id] if bolt is not None else [])
    before_hand, before_library = list(s.state.zones['p1:hand']), list(s.state.zones['p1:library'])
    before_stack = list(s.state.zones.get('stack', []))
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    assert s.state.zones['p1:hand'] == before_hand
    assert s.state.zones['p1:library'] == before_library
    assert s.state.zones.get('stack', []) == before_stack
    assert s.state.cards[paid.id].zone == 'p1:hand'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.decision is None


def taxed_payment(cards):
    s = game(cards)
    source = put(s, 'Leashling', 'battlefield')
    put(s, 'Suppression Field', 'battlefield')
    lands = [put(s, n, 'battlefield') for n in ('Forest', 'Mountain')]
    clear_hand(s)
    paid = put(s, 'Island', 'hand')
    put(s, 'Black Knight', 'hand')
    act(s, 'p1', type='set_prefs', payment='self', hold_priority=True)
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[paid.id])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'pay_mana'
    assert d.resume['paid_then']['stage'] == 'activation_announced'
    assert s.state.cards[paid.id].zone == 'p1:hand'
    return s, source, paid, lands


@pytest.mark.parametrize('cold', [False, True])
def test_taxed_native_payment_cps_preserves_exact_hand_cost_until_mana_paid(cards, tmp_path, cold):
    s, source, paid, lands = taxed_payment(cards)
    if cold:
        import subprocess
        import sys
        save = tmp_path / 'top-hand-cost-payment.json'
        save.write_text(s.state.model_dump_json())
        code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
save,db,source,paid,first,second=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
assert s.state.cards[paid].zone=='p1:hand'
for land in (first,second):
 act(s,'p1',type='activate_ability',card_id=land,ability=0)
assert s.state.zones['p1:library'][0]==paid
old=s.state.rules.object_id(paid)
entry=next(reversed(s.state.rules.stack))
receipt=s.state.rules.payments[s.state.rules.object_id(entry)]
assert sum(receipt.mana_spent.values())==2
settle(s)
assert s.state.cards[source].zone=='p1:hand'
assert not s.view('p2')['cards'].get(paid,{}).get('name')
roundtrip(s)
settle(s)
assert s.state.rules.object_id(paid)==old and s.state.zones['p1:library'][0]==paid
repo.close()
'''
        result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), source.id, paid.id, *[c.id for c in lands]],
                                cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
        return
    for land in lands:
        act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
    assert s.state.zones['p1:library'][0] == paid.id
    entry = next(reversed(s.state.rules.stack))
    receipt = s.state.rules.payments[s.state.rules.object_id(entry)]
    assert sum(receipt.mana_spent.values()) == 2
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:hand'
    assert not s.view('p2')['cards'].get(paid.id, {}).get('name')


def test_taxed_native_payment_rejects_returned_new_incarnation_of_reserved_cost_card(cards):
    s, source, paid, lands = taxed_payment(cards)
    old = s.state.rules.object_id(paid.id)
    act(s, 'p1', type='move', card_ids=[paid.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[paid.id], to={'player': 'p1', 'zone': 'hand'})
    assert s.state.rules.object_id(paid.id) != old
    act(s, 'p1', type='activate_ability', card_id=lands[0].id, ability=0)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError, match='reserved'):
        act(s, 'p1', type='activate_ability', card_id=lands[1].id, ability=0)
    assert s.state.model_dump_json() == before
    assert s.state.cards[paid.id].zone == 'p1:hand'
    assert s.state.cards[source.id].zone == 'p1:battlefield'


@pytest.mark.parametrize('command', [False, True])
def test_hand_top_cost_native_commander_replacement_finishes_before_ability_body(cards, command):
    s = game(cards)
    source = put(s, 'Leashling', 'battlefield')
    beacon = put(s, 'Command Beacon', 'battlefield')
    clear_hand(s)
    index = next(a.index for a in chars(s, beacon).abilities if 'command zone' in a.text)
    act(s, 'p1', type='activate_ability', card_id=beacon.id, ability=index, sources=[])
    settle(s)
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        assert d.resume['step'] == 'commander_instead'
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['no'])
        settle(s)
    commander = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.commander_key)
    assert commander.zone == 'p1:hand'
    put(s, 'Forest', 'hand')
    announce(s, source)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[commander.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'commander_instead'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes' if command else 'no'])
    settle(s)
    current = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.commander_key)
    assert current.zone == ('p1:command' if command else 'p1:library')
    if not command:
        assert s.state.zones['p1:library'][0] == current.id
    assert s.state.cards[source.id].zone == 'p1:hand'


def paid_penance(cards, chosen_name, *, turn=1):
    s = game(cards)
    source = put(s, 'Penance', 'battlefield')
    chosen = put(s, chosen_name, 'battlefield', 'p2')
    if turn > 1:
        to_phase(s, 'main1', turn=turn)
    clear_hand(s)
    paid = put(s, 'Forest', 'hand')
    put(s, 'Island', 'hand')
    announce(s, source)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[paid.id])
    settle(s)
    source_choice(s, chosen)
    return s, source, chosen, paid


def test_penance_native_next_time_is_whole_simultaneous_occurrence_and_only_once(cards):
    s, source, pestilence, paid = paid_penance(cards, 'Pestilence')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    activate(s, pestilence, 'each creature', pid='p2')
    assert all(s.state.players[p].life == 40 for p in ('p1', 'p2', 'p3'))
    assert s.state.cards[bear.id].damage == 0
    assert not any(r.get('source_card') == source.id for r in s.state.rules.replacements)
    activate(s, pestilence, 'each creature', pid='p2')
    assert all(s.state.players[p].life == 39 for p in ('p1', 'p2', 'p3'))
    assert s.state.cards[bear.id].damage == 1
    assert s.state.zones['p1:library'][0] == paid.id


@pytest.mark.parametrize('blue', [False, True])
def test_penance_native_source_color_rechecked_and_failed_prevention_does_not_consume(cards, blue):
    s, source, knight, paid = paid_penance(cards, 'Black Knight', turn=2)
    if blue:
        cast(s, 'Turn to Frog', [knight.id])
    attack(s, [knight], pid='p2', target='p1', turn=2)
    damage(s)
    assert s.state.players['p1'].life == (39 if blue else 40)
    assert any(r.get('source_card') == source.id for r in s.state.rules.replacements) == blue
    assert s.state.zones['p1:library'][0] == paid.id


def retreat_pending(cards):
    s = game(cards)
    source = put(s, 'Hidden Retreat', 'battlefield')
    clear_hand(s)
    paid = put(s, 'Forest', 'hand')
    put(s, 'Island', 'hand')
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    announce(s, source, [bolt.id])
    return s, source, paid, bolt


def test_retreat_binds_only_original_spell_incarnation_and_outlives_source(cards):
    s, source, paid, bolt = retreat_pending(cards)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[paid.id])
    entry = next(reversed(s.state.rules.stack))
    original = s.state.rules.object_id(bolt.id)
    while entry in s.state.rules.stack:
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.cards[bolt.id].zone == 'stack'
    assert any(r.get('source_card') == source.id for r in s.state.rules.replacements)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.players['p1'].life == 40
    cast(s, 'Lightning Bolt', ['p1'], pid='p2')
    assert s.state.rules.object_id(bolt.id) != original
    assert s.state.players['p1'].life == 37
    assert s.state.zones['p1:library'][0] == paid.id


@pytest.mark.parametrize('counter_target', ['ability', 'spell'])
def test_retreat_real_counterspell_or_stifle_leaves_hand_top_cost_paid(cards, counter_target):
    s, source, paid, bolt = retreat_pending(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[paid.id])
    entry = next(reversed(s.state.rules.stack))
    cast(s, 'Stifle' if counter_target == 'ability' else 'Counterspell',
         [entry if counter_target == 'ability' else bolt.id], pid='p3')
    settle(s)
    assert s.state.zones['p1:library'][0] == paid.id
    assert not any(r.get('source_card') == source.id for r in s.state.rules.replacements)
    assert s.state.players['p1'].life == (37 if counter_target == 'ability' else 40)


@pytest.mark.parametrize('target_kind', ['permanent', 'ability'])
def test_retreat_rejects_nonspell_targets_before_hand_cost(cards, target_kind):
    s = game(cards)
    source = put(s, 'Hidden Retreat', 'battlefield')
    clear_hand(s)
    put(s, 'Forest', 'hand')
    if target_kind == 'permanent':
        target = put(s, 'Grizzly Bears', 'battlefield', 'p2').id
    else:
        pestilence = put(s, 'Pestilence', 'battlefield', 'p2')
        activate(s, pestilence, 'each creature', pid='p2', resolve=False)
        target = next(reversed(s.state.rules.stack))
    wait_priority(s, 'p1')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        announce(s, source, [target])
    assert s.state.model_dump_json() == before


def test_leashling_controller_pays_own_hand_card_but_creature_returns_to_owner(cards):
    s = game(cards)
    source = put(s, 'Leashling', 'battlefield')
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    paid = put(s, 'Forest', 'hand', 'p2')
    put(s, 'Island', 'hand', 'p2')
    wait_priority(s, 'p2')
    index = next(a.index for a in chars(s, source).abilities if a.kind == 'activated')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=index, sources=[])
    d = s.state.rules.decision
    assert d.player == 'p2'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[paid.id])
    settle(s)
    assert s.state.zones['p2:library'][0] == paid.id
    assert s.state.cards[source.id].zone == 'p1:hand'


def test_penance_cost_paid_source_choice_cold_needs_no_child_cost_or_source_adapter(cards, tmp_path):
    import subprocess
    import sys
    s = game(cards)
    source = put(s, 'Penance', 'battlefield')
    clear_hand(s)
    paid = put(s, 'Forest', 'hand')
    put(s, 'Island', 'hand')
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    announce(s, source)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[paid.id])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'source_shield'
    save = tmp_path / 'paid-penance-source.json'
    save.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
save,db,paid,bolt,source=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=repo)
old=s.state.rules.object_id(paid)
d=s.state.rules.decision
choice=next(o.id for o in d.options if o.card_id==bolt)
act(s,d.player,type='choose',decision_id=d.id,option_ids=[choice])
settle(s)
assert s.state.players['p1'].life==40 and s.state.cards[bolt].zone=='p2:graveyard'
assert s.state.zones['p1:library'][0]==paid and s.state.rules.object_id(paid)==old
assert not any(r.get('source_card')==source for r in s.state.rules.replacements)
roundtrip(s)
settle(s)
assert s.state.zones['p1:library'][0]==paid and s.state.rules.object_id(paid)==old
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(save), str(cards.db_path), paid.id, bolt.id, source.id],
                            cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_penance_unpreventable_attempt_does_not_consume_next_time_shield(cards):
    s = game(cards)
    source = put(s, 'Penance', 'battlefield')
    clear_hand(s)
    paid = put(s, 'Forest', 'hand')
    put(s, 'Island', 'hand')
    cast(s, 'Skullcrack', ['p3'], pid='p2')
    bolt = cast(s, 'Lightning Bolt', ['p1'], pid='p2', resolve=False)
    announce(s, source)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[paid.id])
    settle(s)
    source_choice(s, bolt)
    assert s.state.players['p1'].life == 37
    assert any(r.get('source_card') == source.id for r in s.state.rules.replacements)
    assert s.state.zones['p1:library'][0] == paid.id


@pytest.mark.parametrize('name', HAND_NAMES)
def test_hand_top_whole_canonical_coverage_requires_native_cost_and_body(cards, name):
    from app.rules import coverage
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == 'FULL', result.manual_parts
