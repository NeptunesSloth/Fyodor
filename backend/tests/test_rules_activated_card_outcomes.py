"""Actual revealed-card outcomes, rather than parser-only claims."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/activated_outcomes37_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='aco', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def mana(s, pid='p1'):
    act(s, pid, type='add_mana', player=pid, mana={'C': 30, 'W': 8, 'U': 8, 'B': 8, 'R': 8, 'G': 8})


def cast(s, name, targets=(), pid='p1'):
    from tests.test_rules_bandmate_references import wait_priority

    source = put(s, name, 'hand', pid)
    mana(s, pid)
    wait_priority(s, pid)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[],
        **({'target_counts': [len(targets)]} if name == 'Kaboom!' else {}))
    settle(s)
    return source




def activate(s, source, *, targets=(), x=None):
    from app.rules.plan import Plan
    from tests.test_rules_bandmate_references import wait_priority

    mana(s)
    wait_priority(s, 'p1')
    ability = next(a for a in Plan(s.state, 'p1', s.cards, None).ch(source).abilities
                   if a.kind == 'activated' and not a.text.startswith(('Crew', '{1}, {T}: Put a winch', '{R}: Put a charge')))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, targets=list(targets),
        **({'x_value': x, 'target_counts': [len(targets)]} if source.name in ('Deepwood Elder', 'Dwarven Armorer') else {'x_value': x} if x is not None else {}))


def ready(cards, name, more=()):
    s = table(cards, [name, 'Fervor', 'Sol Ring', *more])
    source = put(s, name, 'battlefield')
    put(s, 'Fervor', 'battlefield')
    fodder = put(s, 'Sol Ring', 'hand')
    return s, source, fodder


@pytest.mark.parametrize('name,token', [('Cloudseeder', 'Cloud Sprite'), ('Sparkspitter', 'Spark Elemental')])
def test_actual_discard_tap_named_token(cards, name, token):
    from app.rules.plan import Plan

    s, source, fodder = ready(cards, name)
    activate(s, source)
    if s.state.cards[fodder.id].zone == 'p1:hand':
        pick(s, [fodder.id])
    settle(s)
    made = [c for c in s.state.cards.values() if c.token and c.zone == 'p1:battlefield']
    assert len(made) == 1 and made[0].name == token
    ch = Plan(s.state, 'p1', cards, None).ch(made[0])
    assert ch.mana_value == 0
    assert ('flying' in ch.keywords) if name == 'Cloudseeder' else {'trample', 'haste'} <= ch.keywords
    assert s.state.cards[fodder.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('option,kind', [('0', '+0/+1'), ('1', '+1/+0')])
def test_armorer_counter_is_chosen_after_cost_payment(cards, option, kind):
    s, source, fodder = ready(cards, 'Dwarven Armorer', ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    activate(s, source, targets=[bear.id])
    if s.state.cards[fodder.id].zone == 'p1:hand':
        pick(s, [fodder.id])
    settle(s)
    assert s.state.cards[fodder.id].zone == 'p1:graveyard'
    pick(s, [option])
    settle(s)
    assert s.state.cards[bear.id].counters.get(kind) == 1
    roundtrip(s)


@pytest.mark.parametrize('option', ['0', '1', '2', '3'])
def test_sculpture_resolution_choices_persist(cards, option):
    from app.rules.plan import Plan

    s, source, fodder = ready(cards, 'Flowstone Sculpture')
    activate(s, source)
    if s.state.cards[fodder.id].zone == 'p1:hand':
        pick(s, [fodder.id])
    settle(s)
    pick(s, [option])
    settle(s)
    if option == '0':
        assert s.state.cards[source.id].counters.get('+1/+1') == 1
    else:
        assert ['flying', 'first strike', 'trample'][int(option)-1] in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).keywords
    roundtrip(s)


@pytest.mark.parametrize('option', ['counters', 'token'])
def test_krumar_announced_x_life_and_native_endure(cards, option):
    s, source, _ = ready(cards, 'Krumar Initiate')
    activate(s, source, x=3)
    settle(s)
    assert s.state.players['p1'].life == 37
    pick(s, [option])
    settle(s)
    if option == 'counters':
        assert s.state.cards[source.id].counters.get('+1/+1') == 3
    else:
        assert any(c.token and c.name == 'Spirit' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    roundtrip(s)


def test_mondo_choice_sets_color_and_grants_hexproof(cards):
    from app.rules.plan import Plan

    s, source, fodder = ready(cards, 'Mondo Gecko')
    activate(s, source)
    if s.state.cards[fodder.id].zone == 'p1:hand':
        pick(s, [fodder.id])
    settle(s)
    pick(s, ['Blue'])
    settle(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.colors == frozenset({'U'})
    assert 'hexproof from blue' in ch.keywords
    roundtrip(s)


def test_possessed_goat_adds_demon_and_black(cards):
    from app.rules.plan import Plan

    s, source, fodder = ready(cards, 'Possessed Goat')
    activate(s, source)
    if s.state.cards[fodder.id].zone == 'p1:hand':
        pick(s, [fodder.id])
    settle(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert {'Goat', 'Demon'} <= ch.subtypes and {'W', 'B'} <= ch.colors
    assert s.state.cards[source.id].counters.get('+1/+1') == 3
    roundtrip(s)


def test_turret_pays_exact_fifty_counters(cards):
    s, source, _ = ready(cards, 'Fire Nation Turret')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='charge', value=50)
    activate(s, source, targets=['p2'])
    settle(s)
    assert s.state.cards[source.id].counters.get('charge', 0) == 0
    assert s.state.players['p2'].life == -10 or not s.state.players['p2'].alive
    roundtrip(s)


def test_mercadian_lift_uses_announced_counter_x(cards):
    s, source, _ = ready(cards, 'Mercadian Lift', ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='winch', value=2)
    activate(s, source, x=2)
    settle(s)
    assert s.state.rules.decision is not None and bear.id in {o.id for o in s.state.rules.decision.options}
    pick(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_deepwood_actual_x_targets_become_forests(cards):
    from app.rules.plan import Plan

    s, source, fodder = ready(cards, 'Deepwood Elder', ['Darksteel Citadel'])
    land = put(s, 'Darksteel Citadel', 'battlefield')
    activate(s, source, targets=[land.id], x=1)
    if s.state.cards[fodder.id].zone == 'p1:hand':
        pick(s, [fodder.id])
    settle(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[land.id])
    assert 'Forest' in ch.subtypes and {'Land', 'Artifact'} <= ch.types
    assert 'indestructible' not in ch.keywords
    roundtrip(s)


def test_bankbuster_final_charge_creates_actual_pilot_and_treasure(cards):
    s = table(cards, ['Reckoner Bankbuster'])
    source = cast(s, 'Reckoner Bankbuster')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='charge', value=1)
    activate(s, source)
    settle(s)
    assert {c.name for c in s.state.cards.values() if c.token and c.zone == 'p1:battlefield'} == {'Pilot', 'Treasure'}
    roundtrip(s)


def test_sage_discards_only_one_of_actual_three_drawn_cards(cards):
    s, source, older = ready(cards, 'Soldevi Sage', ['Grizzly Bears', 'Llanowar Elves'])
    lands = [c for c in s.state.cards.values() if c.name == 'Forest'][:2]
    for land in lands:
        act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'battlefield'})
    before = set(s.state.zones['p1:hand'])
    activate(s, source)
    settle(s)
    drawn = set(s.state.zones['p1:hand']) - before
    assert len(drawn) == 3
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == drawn
    assert older.id not in {o.id for o in d.options}
    assert not s.view('p2')['rules']['decision'].get('options')
    selected = next(iter(drawn))
    pick(s, [selected])
    settle(s)
    assert s.state.cards[selected].zone == 'p1:graveyard'
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in lands)
    roundtrip(s)


def test_trade_caravan_untaps_opponent_basic_only_in_opponent_upkeep(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s, source, _ = ready(cards, 'Trade Caravan')
    land = put(s, 'Island', 'battlefield', 'p2')
    act(s, 'p2', type='tap', card_ids=[land.id], tapped=True)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='currency', value=2)
    to_phase(s, 'upkeep', turn=2)
    wait_priority(s, 'p1')
    activate(s, source, targets=[land.id])
    settle(s)
    assert not s.state.cards[land.id].tapped
    assert s.state.cards[source.id].counters.get('currency', 0) == 0
    roundtrip(s)


def test_krumar_forced_spirit_when_counters_are_prohibited(cards):
    s, source, _ = ready(cards, 'Krumar Initiate', ['Solemnity'])
    put(s, 'Solemnity', 'battlefield')
    activate(s, source, x=2)
    settle(s)
    assert s.state.rules.decision is None
    assert any(c.token and c.name == 'Spirit' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    assert s.state.players['p1'].life == 38
    roundtrip(s)


@pytest.mark.parametrize('name,option', [('Flowstone Sculpture', '2'), ('Dwarven Armorer', '1'), ('Mondo Gecko', 'Red'), ('Krumar Initiate', 'token')])
def test_resolution_choice_resumes_in_fresh_process(cards, tmp_path, name, option):
    from tests.test_rules_reveal_outcomes import cold_answer

    s, source, fodder = ready(cards, name, ['Grizzly Bears'])
    target = put(s, 'Grizzly Bears', 'battlefield')
    activate(s, source, targets=[target.id] if name == 'Dwarven Armorer' else (), x=2 if name == 'Krumar Initiate' else None)
    if s.state.cards[fodder.id].zone == 'p1:hand' and name != 'Krumar Initiate':
        pick(s, [fodder.id])
    settle(s)
    s = cold_answer(s, cards, tmp_path, [option])
    assert s.state.rules.decision is None
    assert s.history.rebuild() == s.state


def test_bankbuster_initial_charge_branch_and_pilot_native_crew(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Reckoner Bankbuster'])
    source = cast(s, 'Reckoner Bankbuster')
    assert s.state.cards[source.id].counters.get('charge') == 3
    activate(s, source)
    settle(s)
    assert not any(c.token for c in s.state.cards.values())
    act(s, 'p1', type='tap', card_ids=[source.id], tapped=False)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='charge', value=1)
    activate(s, source)
    settle(s)
    pilot = next(c for c in s.state.cards.values() if c.token and c.name == 'Pilot')
    crew = next(a for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).abilities if a.text.startswith('Crew'))
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=crew.index, crew=[pilot.id])
    settle(s)
    assert 'Creature' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).types
    assert s.state.cards[pilot.id].tapped
    roundtrip(s)


def test_spark_token_sacrifices_itself_at_actual_endstep(cards):
    s, source, fodder = ready(cards, 'Sparkspitter')
    activate(s, source)
    if s.state.cards[fodder.id].zone == 'p1:hand':
        pick(s, [fodder.id])
    settle(s)
    token = next(c for c in s.state.cards.values() if c.token and c.name == 'Spark Elemental')
    to_phase(s, 'end', turn=1)
    settle(s)
    assert token.id not in s.state.cards or s.state.cards[token.id].zone != 'p1:battlefield'
    roundtrip(s)


def test_mondo_repeated_color_choice_preserves_earlier_hexproof(cards):
    from app.rules.plan import Plan

    s, source, fodder = ready(cards, 'Mondo Gecko', ['Grizzly Bears'])
    activate(s, source)
    if s.state.cards[fodder.id].zone == 'p1:hand':
        pick(s, [fodder.id])
    settle(s)
    pick(s, ['Blue'])
    settle(s)
    put(s, 'Grizzly Bears', 'hand')
    activate(s, source)
    settle(s)
    pick(s, ['Green'])
    settle(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.colors == frozenset({'G'})
    assert {'hexproof from blue', 'hexproof from green'} <= ch.keywords
    to_phase(s, 'main1', turn=2)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    assert ch.colors == frozenset({'U'})
    assert not {'hexproof from blue', 'hexproof from green'} & ch.keywords
    roundtrip(s)


@pytest.mark.parametrize('name,x', [('Fire Nation Turret', None), ('Krumar Initiate', 41)])
def test_activation_unpayable_cost_is_atomic(cards, name, x):
    from app.game.errors import ActionError
    from app.rules.plan import Plan

    s, source, _ = ready(cards, name)
    if name == 'Fire Nation Turret':
        act(s, 'p1', type='set_counter', card_id=source.id, kind='charge', value=49)
    mana(s)
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated' and not a.text.startswith('{R}:'))
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index,
            targets=['p2'] if name == 'Fire Nation Turret' else [], **({'x_value': x} if x is not None else {}))
    assert s.state.model_dump_json() == before


def test_krumar_zero_cost_does_not_offer_endure_choice(cards):
    s, source, _ = ready(cards, 'Krumar Initiate')
    activate(s, source, x=0)
    settle(s)
    assert s.state.rules.decision is None and s.state.players['p1'].life == 40
    assert not any(c.token for c in s.state.cards.values())
    roundtrip(s)


def test_sage_draw_subset_cold_choice_keeps_private_pool(cards, tmp_path):
    from tests.test_rules_reveal_outcomes import cold_answer

    s, source, older = ready(cards, 'Soldevi Sage')
    for land in [c for c in s.state.cards.values() if c.name == 'Forest'][:2]:
        act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'battlefield'})
    activate(s, source)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and older.id not in {o.id for o in d.options}
    selected = d.options[0].id
    s = cold_answer(s, cards, tmp_path, [selected])
    assert s.state.cards[selected].zone == 'p1:graveyard'
    assert s.state.cards[older.id].zone == 'p1:hand'


def test_cloud_sprite_cannot_block_actual_ground_attacker(cards):
    from app.game.errors import ActionError
    from tests.test_rules_conditionals import until

    s = table(cards, ['Cloudseeder', 'Fervor', 'Sol Ring'], ['Grizzly Bears'])
    source = put(s, 'Cloudseeder', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    put(s, 'Sol Ring', 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate(s, source)
    settle(s)
    token = next(c for c in s.state.cards.values() if c.token and c.name == 'Cloud Sprite')
    to_phase(s, 'declare_attackers', turn=2)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p1'}])
    until(s, lambda game: game.state.rules.decision is not None and game.state.rules.decision.kind == 'declare_blockers')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_blockers', blocks=[{'blocker_id': token.id, 'attacker_id': bear.id}])
    assert s.state.model_dump_json() == before
    act(s, 'p1', type='declare_blockers', blocks=[])
    roundtrip(s)


def test_sage_replaced_draws_do_not_discard_old_or_replacement_cards(cards):
    s, source, older = ready(cards, 'Soldevi Sage', ['Abundance'])
    put(s, 'Abundance', 'battlefield')
    for land in [c for c in s.state.cards.values() if c.name == 'Forest'][:2]:
        act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'battlefield'})
    before = len(s.state.zones['p1:hand'])
    activate(s, source)
    for _ in range(12):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options]
        assert d.kind != 'choose_cards', 'replacement cards must not enter the discard pool'
        pick(s, ['land'] if 'land' in ids else [next(o.id for o in d.options if o.id != 'decline')])
    else:
        raise AssertionError('draw replacements did not finish')
    assert len(s.state.zones['p1:hand']) == before + 3
    assert s.state.cards[older.id].zone == 'p1:hand'
    roundtrip(s)


def test_krumar_source_dies_before_endure_still_creates_spirit(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = table(cards, ['Krumar Initiate', 'Fervor'], ['Murder'])
    source = put(s, 'Krumar Initiate', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    activate(s, source, x=3)
    murder = put(s, 'Murder', 'hand', 'p2')
    mana(s, 'p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=murder.id, targets=[source.id], sources=[])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert any(c.token and c.name == 'Spirit' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    assert s.state.players['p1'].life == 37
    roundtrip(s)


def test_goat_once_limit_is_actual_paid_object_lifetime(cards):
    from app.game.errors import ActionError
    from app.rules.plan import Plan

    s, source, _ = ready(cards, 'Possessed Goat', ['Grizzly Bears'])
    activate(s, source)
    settle(s)
    put(s, 'Grizzly Bears', 'hand')
    mana(s)
    before = s.state.model_dump_json()
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).abilities if a.kind == 'activated')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index)
    assert s.state.model_dump_json() == before


def test_krumar_x_life_survives_actual_cryptex_payment_continuation(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Krumar Initiate', 'Fervor', 'Cryptex', 'Grizzly Bears', 'Sol Ring'])
    source = put(s, 'Krumar Initiate', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    cryptex = put(s, 'Cryptex', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'graveyard')
    ring = put(s, 'Sol Ring', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='set_prefs', payment='self')
    ability = next(a for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.kind == 'activated')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability.index, x_value=3)
    assert s.state.rules.decision is not None and s.state.rules.decision.resume['step'] == 'pay_mana'
    act(s, 'p1', type='activate_ability', card_id=cryptex.id, ability=0, mana_choice='B')
    d = s.state.rules.decision
    if d is not None and {bear.id, ring.id} <= {o.id for o in d.options}:
        pick(s, [bear.id, ring.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'endure'
    assert s.state.players['p1'].life == 37
    assert s.state.cards[bear.id].zone == 'p1:exile' and s.state.cards[ring.id].zone == 'p1:exile'
    assert s.state.cards[cryptex.id].counters.get('unlock') == 1
    pick(s, ['counters'])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1') == 3
    roundtrip(s)


def test_casting_bones_collateral_actual_aura_death_and_cold_draw_subset(cards, tmp_path):
    from tests.test_rules_reveal_outcomes import cold_answer

    s = table(cards, ['Casting of Bones', 'Murder', 'Sol Ring'], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    aura = cast(s, 'Casting of Bones', [bear.id])
    assert s.state.cards[aura.id].attached_to == bear.id
    older = put(s, 'Sol Ring', 'hand')
    before = set(s.state.zones['p1:hand'])
    murder = cast(s, 'Murder', [bear.id])
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    drawn = set(s.state.zones['p1:hand']) - before
    d = s.state.rules.decision
    assert d is not None and len(drawn) == 3
    assert {o.id for o in d.options} == drawn and older.id not in {o.id for o in d.options}
    assert not s.view('p2')['rules']['decision'].get('options')
    selected = d.options[0].id
    s = cold_answer(s, cards, tmp_path, [selected])
    assert s.state.cards[selected].zone == 'p1:graveyard'
    assert s.state.cards[older.id].zone == 'p1:hand'
    assert s.state.cards[murder.id].zone == 'p1:graveyard'
    assert s.history.rebuild() == s.state
