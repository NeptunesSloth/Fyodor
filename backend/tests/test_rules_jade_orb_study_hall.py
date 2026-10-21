"""Counterable spent-mana triggers carry timed spell riders and exact commander counts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.state import GameState
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

JADE, HALL = 'Jade Orb of Dragonkind', 'Study Hall'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / 'fixtures/jade_orb_study_hall_cards.json').read_text())
    for i, c in enumerate(data):
        base[c['name']] = card(c['name'], set_code='sec', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize('name', [JADE, HALL, 'Scaled Nurturer', 'Gilanra, Caller of Wirewood',
                                  'Lapis Orb of Dragonkind', 'Path of Ancestry', "Pyromancer's Goggles"])
def test_canonical_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def answer(s, ids):
    d = s.state.rules.decision
    assert d is not None
    roundtrip(s)
    s.state = GameState.model_validate(s.state.model_dump(mode='json'))
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)


def keywords(s, source):
    return Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[source.id]).keywords


def jade(cards, support=(), *, stolen=False, doubled=False, as_though=False):
    names = [JADE, 'Shivan Dragon', 'Grizzly Bears', 'Lightning Bolt', 'Disenchant', 'Time Warp',
             'Mana Reflection', 'Mycosynth Lattice', *support]
    s = table(cards, list(dict.fromkeys(names)), ['Shivan Dragon', 'Stifle', 'Counterspell', 'Insurrection', 'Lightning Bolt'])
    orb = put(s, JADE, 'battlefield')
    if doubled:
        put(s, 'Mana Reflection', 'battlefield')
    if as_though:
        put(s, 'Mycosynth Lattice', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=orb.id, ability=0)
    roundtrip(s)
    dragon = put(s, 'Shivan Dragon', 'hand', 'p2' if stolen else 'p1')
    if stolen:
        act(s, 'p1', type='move', card_ids=[dragon.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, **({'C': 5} if as_though else {'C': 2 if doubled else 3, 'R': 2}))
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=dragon.id)
    if s.state.rules.decision and s.state.rules.decision.kind == 'order':
        answer(s, [o.id for o in s.state.rules.decision.options])
    return s, orb, dragon


def test_actual_mana_trigger_adds_counter_and_hexproof_until_casters_next_turn(cards):
    s, _, dragon = jade(cards)
    entries = [e for e in s.state.rules.stack.values() if e.kind == 'trigger']
    assert len(entries) == 1
    assert not s.state.cards[dragon.id].counters
    roundtrip(s)
    settle(s)
    assert s.state.cards[dragon.id].zone == 'p1:battlefield'
    assert s.state.cards[dragon.id].counters.get('+1/+1') == 1 and 'hexproof' in keywords(s, dragon)
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert 'hexproof' in keywords(s, dragon)
    to_phase(s, 'main1', turn=4)
    assert 'hexproof' not in keywords(s, dragon) and s.state.cards[dragon.id].counters['+1/+1'] == 1
    roundtrip(s)


@pytest.mark.parametrize('counter_trigger', [True, False])
def test_rider_trigger_and_creature_spell_can_each_be_countered(cards, counter_trigger):
    s, _, dragon = jade(cards)
    trigger = next(sid for sid, e in s.state.rules.stack.items() if e.kind == 'trigger')
    wait_priority(s, 'p2')
    spell = put(s, 'Stifle' if counter_trigger else 'Counterspell', 'hand', 'p2')
    mana(s, 'p2', U=1 if counter_trigger else 2)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[trigger if counter_trigger else dragon.id])
    settle(s)
    assert s.state.rules.decision is None
    if counter_trigger:
        assert s.state.cards[dragon.id].zone == 'p1:battlefield'
        assert not s.state.cards[dragon.id].counters and 'hexproof' not in keywords(s, dragon)
    else:
        assert s.state.cards[dragon.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('replacement,expected', [('Doubling Season', 2), ('Solemnity', 0)])
def test_entering_counter_uses_native_replacements(cards, replacement, expected):
    s, _, dragon = jade(cards, [replacement])
    put(s, replacement, 'battlefield')
    settle(s)
    assert s.state.cards[dragon.id].counters.get('+1/+1', 0) == expected
    assert 'hexproof' in keywords(s, dragon)
    roundtrip(s)


@pytest.mark.parametrize('doubled,as_though', [(True, False), (False, True)])
def test_each_actual_spent_unit_triggers_and_as_though_keeps_provenance(cards, doubled, as_though):
    s, _, dragon = jade(cards, doubled=doubled, as_though=as_though)
    assert len([e for e in s.state.rules.stack.values() if e.kind == 'trigger']) == (2 if doubled else 1)
    settle(s)
    assert s.state.cards[dragon.id].counters['+1/+1'] == (2 if doubled else 1)
    assert 'hexproof' in keywords(s, dragon)
    assert not mana_pool(s)
    roundtrip(s)


def test_opponent_owned_dragon_uses_casters_clock_and_source_departure_does_not_remove_grant(cards):
    s, orb, dragon = jade(cards, stolen=True)
    act(s, 'p1', type='move', card_ids=[orb.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert s.state.cards[dragon.id].owner == 'p2' and s.state.cards[dragon.id].controller == 'p1'
    to_phase(s, 'main1', turn=2)
    assert 'hexproof' in keywords(s, dragon)
    to_phase(s, 'main1', turn=4)
    assert 'hexproof' not in keywords(s, dragon)
    roundtrip(s)


def test_original_casters_extra_turn_expires_hexproof(cards):
    s, _, dragon = jade(cards)
    settle(s)
    warp = put(s, 'Time Warp', 'hand')
    mana(s, C=3, U=2)
    act(s, 'p1', type='cast_spell', card_id=warp.id, targets=['p1'])
    settle(s)
    to_phase(s, 'main1', turn=2)
    assert s.state.turn.active_player == 'p1' and 'hexproof' not in keywords(s, dragon)
    roundtrip(s)


def hall(cards, *, hand=False, support=(), settle_cast=True):
    s = table(cards, [HALL, *support])
    source = put(s, HALL, 'battlefield')
    commander = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.commander_key)
    if hand:
        act(s, 'p1', type='move', card_ids=[commander.id], to={'player': 'p1', 'zone': 'hand'})
    mana(s, C=3, R=1)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, mana_choice='R')
    roundtrip(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=commander.id)
    if settle_cast:
        settle(s)
    return s, source, commander


def test_study_hall_counts_the_commander_cast_including_this_one(cards):
    s, source, commander = hall(cards)
    d = s.state.rules.decision
    assert d and len(d.options) == 1 and d.player == 'p1'
    assert s.view('p2')['rules']['decision']['kind'] == 'waiting'
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    answer(s, [])
    settle(s)
    assert s.state.cards[commander.id].zone == 'p1:battlefield' and s.state.rules.decision is None
    roundtrip(s)


def test_study_hall_hand_cast_does_not_increment_command_zone_count(cards):
    s, _, commander = hall(cards, hand=True)
    assert s.state.rules.decision is None and s.state.cards[commander.id].zone == 'p1:battlefield'
    assert not s.state.players['p1'].commander_casts
    roundtrip(s)


def resolve_jade_trigger_only(s):
    for _ in range(8):
        if not any(e.kind == 'trigger' for e in s.state.rules.stack.values()):
            return
        act(s, s.state.rules.priority, type='pass_priority')
    raise AssertionError('rider trigger did not resolve')


def test_pending_dragon_does_not_gain_spell_hexproof_after_rider_resolves(cards):
    s, _, dragon = jade(cards)
    resolve_jade_trigger_only(s)
    assert 'hexproof' not in keywords(s, dragon)
    wait_priority(s, 'p2')
    counter = put(s, 'Counterspell', 'hand', 'p2')
    mana(s, 'p2', U=2)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[dragon.id])
    settle(s)
    assert s.state.cards[dragon.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_stored_rider_that_has_expired_does_not_restart_keyword_on_entry(cards):
    # Boundary contract for a resumed payment record: advance its caster clock,
    # without pretending that a normal legal stack persists across turns.
    s, _, dragon = jade(cards)
    resolve_jade_trigger_only(s)
    rec = s.state.rules.payments[s.state.rules.object_id(dragon.id)]
    rider = next(r for r in rec.mana_riders if r['kind'] == 'keyword')
    s.state.rules.turns_taken['p1'] = rider['turns_taken'] + 1
    from app.game.session import GameSession

    loaded = GameSession(GameState.model_validate(s.state.model_dump(mode='json')), cards=cards)
    settle(loaded)
    assert loaded.state.cards[dragon.id].counters['+1/+1'] == 1
    assert 'hexproof' not in keywords(loaded, dragon)
    roundtrip(loaded)


@pytest.mark.parametrize('non_dragon', [False, True])
def test_unspent_or_wrong_spell_jade_mana_gives_no_rider(cards, non_dragon):
    s = table(cards, [JADE, 'Shivan Dragon', 'Grizzly Bears'])
    orb = put(s, JADE, 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=orb.id, ability=0)
    spell = put(s, 'Grizzly Bears' if non_dragon else 'Shivan Dragon', 'hand')
    mana(s, **({'C': 1} if non_dragon else {'C': 4, 'R': 2}))
    act(s, 'p1', type='cast_spell', card_id=spell.id)
    assert not any(e.kind == 'trigger' for e in s.state.rules.stack.values())
    settle(s)
    assert not s.state.cards[spell.id].counters and 'hexproof' not in keywords(s, spell)
    assert sum(u.sym == 'G' for u in s.state.players['p1'].mana_units) == (0 if non_dragon else 1)
    roundtrip(s)


def test_jade_mana_spent_on_study_halls_activation_input_does_not_leak_to_dragon(cards):
    s = table(cards, [JADE, HALL, 'Shivan Dragon'])
    orb = put(s, JADE, 'battlefield')
    study = put(s, HALL, 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=orb.id, ability=0)
    act(s, 'p1', type='activate_ability', card_id=study.id, ability=1, mana_choice='R')
    dragon = put(s, 'Shivan Dragon', 'hand')
    mana(s, C=4, R=1)
    act(s, 'p1', type='cast_spell', card_id=dragon.id)
    settle(s)
    assert not s.state.cards[dragon.id].counters and 'hexproof' not in keywords(s, dragon)
    roundtrip(s)


def test_copied_dragon_spell_does_not_copy_spent_mana_grants(cards):
    s, _, dragon = jade(cards, ['Double Major'])
    resolve_jade_trigger_only(s)
    copy = put(s, 'Double Major', 'hand')
    mana(s, G=1, U=1)
    act(s, 'p1', type='cast_spell', card_id=copy.id, targets=[dragon.id])
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.name == 'Shivan Dragon']
    assert len(tokens) == 1 and not tokens[0].counters and 'hexproof' not in keywords(s, tokens[0])
    assert s.state.cards[dragon.id].counters['+1/+1'] == 1 and 'hexproof' in keywords(s, dragon)
    roundtrip(s)


def test_partner_cast_counts_are_per_particular_commander(cards):
    from app.game.factory import DeckCard, PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    rogue, other = 'Rograkh, Son of Rohgahh', 'Thrasios, Triton Hero'
    own = deck(cards, rogue, [(1, HALL), (20, 'Forest')])
    own.append(DeckCard('commander', 1, other, cards.resolve(other)['id']))
    opponent = deck(cards, 'Atraxa, Praetors\' Voice', [(20, 'Island')])
    s = GameSession(enable(new_game([PlayerSetup('Alice', cards=own), PlayerSetup('Bob', cards=opponent)], shuffle=False)), cards=cards)
    for pid in ['p1', 'p2']:
        act(s, pid, type='set_prefs', response='on')
    act(s, 'p1', type='pass_priority')
    to_phase(s, 'main1', turn=1)
    study = put(s, HALL, 'battlefield')
    commanders = {c.name: c for c in s.state.cards.values() if c.owner == 'p1' and c.commander_key}
    act(s, 'p1', type='cast_spell', card_id=commanders[rogue].id)
    settle(s)
    mana(s, C=1, U=1)
    act(s, 'p1', type='activate_ability', card_id=study.id, ability=1, mana_choice='G')
    act(s, 'p1', type='cast_spell', card_id=commanders[other].id)
    settle(s)
    assert len(s.state.rules.decision.options) == 1  # not two commanders' combined casts
    answer(s, [])
    settle(s)
    act(s, 'p1', type='move', card_ids=[commanders[other].id], to={'player': 'p1', 'zone': 'command'})
    to_phase(s, 'main1', turn=3)
    mana(s, C=3, U=1)
    act(s, 'p1', type='activate_ability', card_id=study.id, ability=1, mana_choice='G')
    act(s, 'p1', type='cast_spell', card_id=commanders[other].id)
    settle(s)
    assert len(s.state.rules.decision.options) == 2  # Thrasios twice, Rograkh once
    d = s.state.rules.decision
    answer(s, [o.id for o in d.options])
    settle(s)
    assert s.state.cards[commanders[other].id].zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('destroy', [False, True])
def test_floating_mana_remembers_source_after_departure_or_control_change(cards, destroy):
    s = table(cards, [JADE, 'Disenchant', 'Shivan Dragon'])
    source = put(s, JADE, 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    if destroy:
        removal = put(s, 'Disenchant', 'hand')
        mana(s, C=1, W=1)
        act(s, 'p1', type='cast_spell', card_id=removal.id, targets=[source.id])
        settle(s)
        assert s.state.cards[source.id].zone == 'p1:graveyard'
    else:
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    assert sum(u.sym == 'G' for u in s.state.players['p1'].mana_units) == 1
    roundtrip(s)
    dragon = put(s, 'Shivan Dragon', 'hand')
    mana(s, C=3, R=2)
    act(s, 'p1', type='cast_spell', card_id=dragon.id)
    settle(s)
    assert s.state.cards[dragon.id].counters['+1/+1'] == 1 and 'hexproof' in keywords(s, dragon)
    to_phase(s, 'main1', turn=4)
    assert 'hexproof' not in keywords(s, dragon)
    roundtrip(s)


def test_another_players_extra_turn_does_not_expire_the_grant(cards):
    s, _, dragon = jade(cards)
    settle(s)
    warp = put(s, 'Time Warp', 'hand')
    mana(s, C=3, U=2)
    act(s, 'p1', type='cast_spell', card_id=warp.id, targets=['p2'])
    settle(s)
    to_phase(s, 'main1', turn=2)
    assert s.state.turn.active_player == 'p2' and 'hexproof' in keywords(s, dragon)
    to_phase(s, 'main1', turn=3)
    assert s.state.turn.active_player == 'p2' and 'hexproof' in keywords(s, dragon)
    to_phase(s, 'main1', turn=5)
    assert s.state.turn.active_player == 'p1' and 'hexproof' not in keywords(s, dragon)
    roundtrip(s)


def test_blinking_the_dragon_loses_old_object_riders(cards):
    s, _, dragon = jade(cards, ['Cloudshift'])
    settle(s)
    old = s.state.rules.object_id(dragon.id)
    flicker = put(s, 'Cloudshift', 'hand')
    mana(s, W=1)
    act(s, 'p1', type='cast_spell', card_id=flicker.id, targets=[dragon.id])
    settle(s)
    assert s.state.rules.object_id(dragon.id) != old
    assert s.state.cards[dragon.id].zone == 'p1:battlefield'
    assert not s.state.cards[dragon.id].counters and 'hexproof' not in keywords(s, dragon)
    roundtrip(s)


def test_spent_mana_delayed_trigger_keeps_producer_source_and_is_not_a_permanent_trigger(cards):
    s = table(cards, ['Scaled Nurturer', 'Delney, Streetwise Lookout', 'Shivan Dragon'])
    source = put(s, 'Scaled Nurturer', 'battlefield')
    put(s, 'Delney, Streetwise Lookout', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    dragon = put(s, 'Shivan Dragon', 'hand')
    mana(s, C=3, R=2)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=dragon.id)
    triggers = [e for e in s.state.rules.stack.values() if e.kind == 'trigger']
    assert len(triggers) == 1 and triggers[0].source_card == source.id
    assert triggers[0].source_object == s.state.rules.object_id(source.id)
    settle(s)
    assert s.state.players['p1'].life == 42
    roundtrip(s)


def test_hexproof_tracks_current_creature_controller_but_original_caster_expiry(cards):
    s, _, dragon = jade(cards)
    settle(s)
    to_phase(s, 'main1', turn=2)
    reins = put(s, 'Insurrection', 'hand', 'p2')
    mana(s, 'p2', C=5, R=3)
    act(s, 'p2', type='cast_spell', card_id=reins.id)
    settle(s)
    assert s.state.cards[dragon.id].controller == 'p2' and 'hexproof' in keywords(s, dragon)
    wait_priority(s, 'p1')
    bolt = put(s, 'Lightning Bolt', 'hand')
    mana(s, R=1)
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=bolt.id, targets=[dragon.id])
    to_phase(s, 'main1', turn=3)
    assert s.state.cards[dragon.id].controller == 'p1' and 'hexproof' in keywords(s, dragon)
    to_phase(s, 'main1', turn=4)
    assert 'hexproof' not in keywords(s, dragon)
    roundtrip(s)


def test_copying_halls_trigger_does_not_increment_commander_casts(cards):
    s, _, commander = hall(cards, support=['Strionic Resonator'], settle_cast=False)
    resonator = put(s, 'Strionic Resonator', 'battlefield')
    trigger = next(sid for sid, entry in s.state.rules.stack.items() if entry.kind == 'trigger')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=resonator.id, ability=0, targets=[trigger])
    settle(s)
    for _ in range(2):
        d = s.state.rules.decision
        assert d and d.resume['step'] == 'look' and len(d.options) == 1
        answer(s, [])
        settle(s)
    assert s.state.rules.decision is None and s.state.cards[commander.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].commander_casts[commander.commander_key] == 1
    roundtrip(s)
