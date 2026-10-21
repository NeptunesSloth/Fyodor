"""Actual contextual activation and mana-trigger cards, saved native continuations."""
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
from tests.test_rules_activated_copy_family import answer, cast
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_discard_outcomes import cold_run
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = Path(__file__).parent / 'fixtures/contextual_mana_triggers_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='cmt39', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    names = [c['name'] for c in json.loads(DATA.read_text())]
    s = table(cards, names, names, names)
    for p in ('p1', 'p2', 'p3'):
        act(s, p, type='set_prefs', hold_priority=True)
    to_phase(s, 'main1', 4)
    return s


def test_unbound_canonical_full(cards):
    assert coverage.of_card_data(cards.resolve('Unbound Flourishing')).level == 'FULL'


@pytest.mark.parametrize('count', [1, 2])
def test_unbound_doubles_current_permanent_x_without_paying_again(cards, count):
    s = game(cards)
    put(s, 'Unbound Flourishing', 'battlefield')
    if count == 2:
        put(s, 'Unbound Flourishing', 'battlefield', 'p2')
        c = next(c for c in s.state.cards.values() if c.name == 'Unbound Flourishing' and c.controller == 'p2' and c.zone.endswith('battlefield'))
        act(s, 'p1', type='set_controller', card_ids=[c.id], player='p1')
    spell = cast(s, 'Walking Ballista', {'C': 4}, x_value=2)
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert sum(record.mana_spent.values()) == 4
    answer(s)
    assert s.state.cards[spell.id].counters['+1/+1'] == 2 * 2 ** count
    roundtrip(s)


def test_unbound_copies_instant_sorcery_with_actual_x(cards):
    s = game(cards)
    put(s, 'Unbound Flourishing', 'battlefield')
    cast(s, 'Blaze', {'R': 1, 'C': 3}, targets=['p2'], x_value=3)
    answer(s, optional=False)
    assert s.state.players['p2'].life == 34
    roundtrip(s)


def test_unbound_x_mana_ability_not_stack_copy(cards):
    s = game(cards)
    put(s, 'Unbound Flourishing', 'battlefield')
    source = put(s, 'Astral Cornucopia', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=3)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, mana_choice='G')
    answer(s)
    assert not s.state.zones.get('stack')
    assert sum(u.sym == 'G' for u in s.state.players['p1'].mana_units) + s.state.players['p1'].mana.get('G', 0) == 3
    roundtrip(s)


@pytest.mark.parametrize('name', ['Keeper of Progenitus', 'Overabundance', 'Barbflare Gremlin'])
def test_new_tapped_mana_profiles_canonical_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', ['Keeper of Progenitus', 'Overabundance', 'Barbflare Gremlin'])
def test_actual_triggered_output_retains_its_producer_identity(cards, name):
    s = game(cards)
    producer = put(s, name, 'battlefield')
    if name == 'Barbflare Gremlin':
        act(s, 'p1', type='tap', card_ids=[producer.id], tapped=True)
    land = put(s, 'Forest', 'battlefield')
    before = s.state.players['p1'].life
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
    answer(s)
    units = s.state.players['p1'].mana_units
    assert sum(u.sym == 'G' for u in units) == 2
    assert {u.src for u in units} == {s.state.rules.object_id(land.id), s.state.rules.object_id(producer.id)}
    assert s.state.players['p1'].life == before - (name != 'Keeper of Progenitus')
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_barbflare_untapped_does_not_trigger(cards):
    s = game(cards)
    put(s, 'Barbflare Gremlin', 'battlefield')
    land = put(s, 'Forest', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
    answer(s)
    assert len(s.state.players['p1'].mana_units) == 1 and s.state.players['p1'].life == 40
    roundtrip(s)


def test_keeper_does_not_multiply_land_with_two_qualifying_types(cards):
    s = game(cards)
    put(s, 'Keeper of Progenitus', 'battlefield')
    land = put(s, 'Stomping Ground', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=1)
    answer(s)
    assert len(s.state.players['p1'].mana_units) == 2
    roundtrip(s)


@pytest.mark.parametrize('name', ['Snowfall', 'Adarkar Unicorn'])
def test_cumulative_upkeep_mana_cards_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('snow', [False, True])
def test_snowfall_extra_is_optional_restricted_and_source_correct(cards, snow):
    s = game(cards)
    producer = put(s, 'Snowfall', 'battlefield')
    land = put(s, 'Snow-Covered Island' if snow else 'Island', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'staged_mana_option'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['1'])
    answer(s)
    units = s.state.players['p1'].mana_units
    assert len(units) == (3 if snow else 2)
    from app.rules import casting
    from app.rules import mana as M
    assert sum(u.src == s.state.rules.object_id(producer.id) for u in units) == (2 if snow else 1)
    assert casting.pool_covers(s.state, 'p1', M.parse_cost('{U}'*(len(units))),
                               purpose=casting.Purpose(special='cumulative_upkeep'), info=cards)
    assert not casting.pool_covers(s.state, 'p1', M.parse_cost('{U}'*len(units)), info=cards)
    roundtrip(s)


def test_unicorn_restricted_mana_actually_pays_snowfall_upkeep(cards):
    s = game(cards)
    source = put(s, 'Adarkar Unicorn', 'battlefield')
    snow = put(s, 'Snowfall', 'battlefield')
    to_phase(s, 'upkeep', 7)
    # The cumulative-upkeep resolution asks for payment after adding its age counter.
    from tests.test_rules_designations import settle
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'pay_or_sacrifice'
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, mana_choice='U')
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['pay'])
    answer(s)
    assert s.state.cards[snow.id].zone == 'p1:battlefield'
    assert s.state.cards[snow.id].counters['age'] == 1
    roundtrip(s)


def test_boreal_full(cards):
    assert coverage.of_card_data(cards.resolve('Boreal Outrider')).level == 'FULL'


@pytest.mark.parametrize('matching', [False, True])
def test_boreal_requires_color_of_actual_snow_mana_not_aggregate_intersection(cards, matching):
    s = game(cards)
    put(s, 'Boreal Outrider', 'battlefield')
    land = put(s, 'Snow-Covered Forest' if matching else 'Snow-Covered Island', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=land.id, ability=0)
    answer(s)
    # Wrong-color snow U pays generic, ordinary G pays green: no matched snow G.
    c = cast(s, 'Grizzly Bears', {'C': 1} if matching else {'G': 1})
    answer(s)
    assert s.state.cards[c.id].counters.get('+1/+1', 0) == int(matching)
    roundtrip(s)


def treasure(s, pid='p1', count=1):
    before = set(s.state.cards)
    act(s, pid, type='create_token', player=pid, count=count,
        token={'name': 'Treasure', 'type_line': 'Token Artifact — Treasure',
               'text': '{T}, Sacrifice this artifact: Add one mana of any color.'})
    return [s.state.cards[c] for c in set(s.state.cards) - before]


def vazi_answers(s, vazi):
    from tests.test_rules_designations import settle
    for _ in range(40):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        opts = {o.id for o in d.options}
        chosen = [vazi.id] if vazi.id in opts else ['keep'] if 'keep' in opts else [d.options[0].id]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=chosen)
    raise AssertionError('Unfinished Vazi decision')


def test_vazi_full(cards):
    assert coverage.of_card_data(cards.resolve('Vazi, Keen Negotiator')).level == 'FULL'


def test_vazi_counts_created_treasures_even_after_they_leave(cards):
    s = game(cards)
    vazi = put(s, 'Vazi, Keen Negotiator', 'battlefield')
    made = treasure(s, count=2)
    act(s, 'p1', type='move', card_ids=[c.id for c in made], to={'zone': 'graveyard'})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=vazi.id, ability=1, targets=['p2'])
    answer(s)
    assert sum(c.is_token and c.name == 'Treasure' and c.zone == 'p2:battlefield' for c in s.state.cards.values()) == 2
    roundtrip(s)


@pytest.mark.parametrize('kind', ['spell', 'ordinary', 'mana_filter'])
def test_vazi_actual_treasure_paid_for_spell_or_either_activation_kind(cards, kind):
    s = game(cards)
    vazi = put(s, 'Vazi, Keen Negotiator', 'battlefield')
    if kind == 'spell':
        to_phase(s, 'main1', 5)
    from app.rules import history
    from app.rules.plan import Plan
    before_draws = history.log_for(Plan(s.state, 'p1', cards, None)).drew.get('p1', 0)
    t = treasure(s, pid='p2')[0]
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=t.id, ability=0, mana_choice='U')
    if kind == 'spell':
        spell = put(s, 'Sol Ring', 'hand', 'p2')
        wait_priority(s, 'p2')
        act(s, 'p2', type='cast_spell', card_id=spell.id, sources=[])
    elif kind == 'ordinary':
        source = put(s, 'Azure Mage', 'battlefield', 'p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'C': 3})
        wait_priority(s, 'p2')
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=0, sources=[])
    else:
        source = put(s, 'Mana Cylix', 'battlefield', 'p2')
        wait_priority(s, 'p2')
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=0, mana_choice='G')
    vazi_answers(s, vazi)
    assert s.state.cards[vazi.id].counters.get('+1/+1', 0) == 1
    from app.rules import history
    from app.rules.plan import Plan
    assert history.log_for(Plan(s.state, 'p1', cards, None)).drew.get('p1', 0) == before_draws + 1
    roundtrip(s)


def sunken_mana(s):
    source = put(s, 'Sunken Palace', 'battlefield')
    gy = [put(s, name, 'graveyard') for name in ['Forest', 'Island', 'Sol Ring', 'Llanowar Elves', 'Walking Ballista', 'Rosheen Meanderer', 'Blaze']]
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2,
        cost_choices=[{'component': 1, 'cards': [c.id for c in gy]}])
    answer(s)
    assert all(s.state.cards[c.id].zone == 'p1:exile' for c in gy)
    assert sum(u.sym == 'U' for u in s.state.players['p1'].mana_units) == 1
    return source


def test_sunken_palace_full(cards):
    assert coverage.of_card_data(cards.resolve('Sunken Palace')).level == 'FULL'


def test_sunken_palace_actual_spent_unit_copies_spell(cards):
    s = game(cards)
    sunken_mana(s)
    # Native any-type generic selection uses the retained U unit, not input mana.
    c = cast(s, 'Sol Ring', {})
    answer(s, optional=False)
    assert s.state.cards[c.id].zone == 'p1:battlefield'
    assert sum(c.name == 'Sol Ring' and c.zone == 'p1:battlefield' for c in s.state.cards.values()) == 2
    roundtrip(s)


def test_sunken_palace_actual_spent_unit_copies_ordinary_ability(cards):
    s = game(cards)
    sunken_mana(s)
    source = put(s, 'Azure Mage', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    answer(s, optional=False)
    from app.rules import history
    from app.rules.plan import Plan
    assert history.log_for(Plan(s.state, 'p1', cards, None)).drew['p1'] == 3
    roundtrip(s)


def test_sunken_mana_spent_on_true_mana_ability_does_not_fabricate_stack_copy(cards):
    s = game(cards)
    sunken_mana(s)
    source = put(s, 'Mana Cylix', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, mana_choice='G')
    answer(s)
    assert not s.state.zones.get('stack')
    assert sum(u.sym == 'G' for u in s.state.players['p1'].mana_units) == 1
    roundtrip(s)


def test_mana_cache_full(cards):
    assert coverage.of_card_data(cards.resolve('Mana Cache')).level == 'FULL'


def test_mana_cache_actual_endstep_counts_only_active_players_current_untapped_lands(cards):
    s = game(cards)
    source = put(s, 'Mana Cache', 'battlefield')
    put(s, 'Forest', 'battlefield')
    tapped = put(s, 'Island', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[tapped.id], tapped=True)
    put(s, 'Forest', 'battlefield', 'p2')
    to_phase(s, 'end', 4)
    answer(s)
    assert s.state.cards[source.id].counters['charge'] == 1
    roundtrip(s)


def test_mana_cache_other_player_gets_mana_and_removes_only_one_counter(cards):
    s = game(cards)
    source = put(s, 'Mana Cache', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=3)
    to_phase(s, 'main1', 5)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=1)
    answer(s)
    assert s.state.cards[source.id].counters['charge'] == 2
    assert sum(u.sym == 'C' for u in s.state.players['p2'].mana_units) == 1
    assert not s.state.players['p1'].mana_units
    roundtrip(s)


def test_mana_cache_rejects_other_turn_and_end_step_atomically(cards):
    from app.game.errors import ActionError
    s = game(cards)
    source = put(s, 'Mana Cache', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=3)
    wait_priority(s, 'p2')
    with pytest.raises(ActionError):
        act(s, 'p2', type='activate_ability', card_id=source.id, ability=1)
    assert s.state.cards[source.id].counters['charge'] == 3
    to_phase(s, 'end', 4)
    answer(s)
    wait_priority(s, 'p1')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert s.state.cards[source.id].counters['charge'] == 3
    roundtrip(s)


@pytest.mark.parametrize('name', ['Domri, Chaos Bringer', 'Rhystic Cave'])
def test_remaining_contextual_mana_cards_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def domri_mana(s):
    source = cast(s, 'Domri, Chaos Bringer', {'C': 2, 'R': 1, 'G': 1})
    answer(s)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    answer(s)
    return source


@pytest.mark.parametrize('haste', [False, True])
def test_domri_actual_loyalty_mana_grants_riot_to_paid_creature(cards, haste):
    from app.rules.plan import Plan
    s = game(cards)
    domri = domri_mana(s)
    # Add only one generic: the creature must use Domri's mana for G or generic.
    c = cast(s, 'Grizzly Bears', {'G': 1})
    from tests.test_rules_designations import settle
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['what'] == 'riot'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['haste' if haste else 'counter'])
    answer(s)
    ch = Plan(s.state, 'p1', cards, None).ch(s.state.cards[c.id])
    assert s.state.cards[c.id].counters.get('+1/+1', 0) == (0 if haste else 1)
    assert ('haste' in ch.keywords) == haste
    assert 'riot' in ch.keywords
    assert s.state.cards[domri.id].counters['loyalty'] == 6
    roundtrip(s)


def test_domri_riot_multiple_instances_and_counter_prohibition(cards):
    from tests.test_rules_designations import settle
    s = game(cards)
    domri_mana(s)
    c = cast(s, 'Zhur-Taa Goblin', {'G': 1})
    settle(s)
    for _ in range(2):
        d = s.state.rules.decision
        assert d is not None
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['counter'])
        settle(s)
    answer(s)
    assert s.state.cards[c.id].counters['+1/+1'] == 2
    roundtrip(s)


def test_domri_riot_cannot_put_counter_gains_haste(cards):
    from app.rules.plan import Plan
    s = game(cards)
    domri_mana(s)
    put(s, 'Solemnity', 'battlefield')
    c = cast(s, 'Grizzly Bears', {'G': 1})
    answer(s)
    assert not s.state.cards[c.id].counters
    assert 'haste' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[c.id]).keywords
    roundtrip(s)


@pytest.mark.parametrize('payer', [None, 'p1', 'p2', 'p3'])
def test_rhystic_cave_actual_all_refuse_or_one_pays(cards, payer):
    from tests.test_rules_designations import settle
    s = game(cards)
    source = put(s, 'Rhystic Cave', 'battlefield')
    if payer:
        act(s, 'p1', type='add_mana', player=payer, mana={'C': 1})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['Green'])
    for _ in range(10):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = {o.id for o in d.options}
        act(s, d.player, type='choose', decision_id=d.id,
            option_ids=['pay' if d.player == payer and 'pay' in ids else 'decline'])
    assert s.state.rules.decision is None
    assert sum(u.sym == 'G' for u in s.state.players['p1'].mana_units) == (payer is None)
    assert s.state.cards[source.id].tapped
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_triggered_mana_cold_order_occurs_after_base_body(cards, tmp_path):
    s = game(cards)
    source = put(s, 'Trenzalore Clocktower', 'battlefield')
    a = put(s, 'Mana Flare', 'battlefield')
    b = put(s, 'Overabundance', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert s.state.rules.decision.resume['step'] == 'staged_mana_order'
    assert s.state.cards[source.id].counters['time'] == 1
    assert s.state.players['p1'].life == 40
    cold_run(s, cards, tmp_path, """
from tests.test_rules_contextual_mana_triggers import answer
answer(s)
units=s.state.players['p1'].mana_units
assert len(units)==3
assert {u.src for u in units}=={s.state.rules.object_id(c) for c in args}
assert s.state.players['p1'].life==39
assert s.state.cards[args[0]].counters['time']==1
""", source.id, a.id, b.id)


def test_sunken_copied_spell_retargets_after_fresh_process_load(cards, tmp_path):
    from tests.test_rules_designations import settle
    s = game(cards)
    sunken_mana(s)
    cast(s, 'Blaze', {'R': 1, 'C': 2}, targets=['p2'], x_value=3)
    settle(s)
    assert s.state.rules.decision is not None
    cold_run(s, cards, tmp_path, """
answer(s,optional=False)
assert s.state.rules.decision is None
assert s.state.players['p2'].life==34
assert not s.state.zones.get('stack')
""")


def test_vazi_filter_input_receipt_cold_does_not_leak_to_paid_spell(cards, tmp_path):
    from tests.test_rules_designations import settle
    s = game(cards)
    vazi = put(s, 'Vazi, Keen Negotiator', 'battlefield')
    to_phase(s, 'main1', 5)
    t = treasure(s, pid='p2')[0]
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=t.id, ability=0, mana_choice='U')
    source = put(s, 'Mana Cylix', 'battlefield', 'p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=source.id, ability=0, mana_choice='G')
    settle(s)
    assert s.state.rules.decision is not None
    cold_run(s, cards, tmp_path, """
from tests.test_rules_contextual_mana_triggers import vazi_answers
from tests.test_rules_designations import put
from tests.test_rules_bandmate_references import wait_priority
vazi=s.state.cards[args[0]]
vazi_answers(s,vazi)
assert s.state.cards[vazi.id].counters['+1/+1']==1
spell=put(s,'Sol Ring','hand','p2')
wait_priority(s,'p2')
act(s,'p2',type='cast_spell',card_id=spell.id,sources=[])
vazi_answers(s,vazi)
assert s.state.cards[vazi.id].counters['+1/+1']==1
assert s.state.cards[spell.id].zone=='p2:battlefield'
""", vazi.id)


def test_cumulative_upkeep_native_purpose_survives_cold_payment(cards, tmp_path):
    from tests.test_rules_designations import settle
    s = game(cards)
    source = put(s, 'Adarkar Unicorn', 'battlefield')
    snow = put(s, 'Snowfall', 'battlefield')
    to_phase(s, 'upkeep', 7)
    settle(s)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, mana_choice='U')
    assert s.state.rules.decision.resume['purpose_special'] == 'cumulative_upkeep'
    cold_run(s, cards, tmp_path, """
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
answer(s)
assert s.state.cards[args[0]].zone=='p1:battlefield'
assert s.state.cards[args[0]].counters['age']==1
assert not s.state.players['p1'].mana_units
""", snow.id)


def test_domri_riot_source_departed_and_cold_entry_choice(cards, tmp_path):
    from tests.test_rules_designations import settle
    s = game(cards)
    source = domri_mana(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'graveyard'})
    c = cast(s, 'Grizzly Bears', {'G': 1})
    settle(s)
    assert s.state.rules.decision.resume['what'] == 'riot'
    cold_run(s, cards, tmp_path, """
from app.rules.plan import Plan
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['haste'])
answer(s)
ch=Plan(s.state,'p1',r,None).ch(s.state.cards[args[0]])
assert 'riot' in ch.keywords and 'haste' in ch.keywords
assert s.state.cards[args[1]].zone=='p1:graveyard'
""", c.id, source.id)


def test_rhystic_cave_cold_uses_active_player_order_and_zero_production_does_not_trigger(cards, tmp_path):
    s = game(cards)
    source = put(s, 'Rhystic Cave', 'battlefield')
    put(s, 'Overabundance', 'battlefield')
    to_phase(s, 'main1', 5)
    for pid in ('p1', 'p2', 'p3'):
        act(s, 'p1', type='add_mana', player=pid, mana={'C': 1})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['Green'])
    d = s.state.rules.decision
    assert d.player == 'p2'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['decline'])
    assert s.state.rules.decision.player == 'p3'
    cold_run(s, cards, tmp_path, """
d=s.state.rules.decision
assert d.player=='p3'
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay'])
answer(s)
assert not s.state.players['p1'].mana_units
assert all(p.life==40 for p in s.state.players.values())
assert s.state.cards[args[0]].tapped
""", source.id)


def test_domri_other_printed_loyalty_modes_use_native_look_and_emblem(cards):
    from app.rules.plan import Plan
    from tests.test_rules_designations import settle
    s = game(cards)
    domri = cast(s, 'Domri, Chaos Bringer', {'C': 2, 'R': 1, 'G': 1})
    answer(s)
    bear = put(s, 'Grizzly Bears', 'hand')
    elf = put(s, 'Llanowar Elves', 'hand')
    for c in (bear, elf):
        act(s, 'p1', type='move', card_ids=[c.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=domri.id, ability=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {bear.id, elf.id}.issubset({o.id for o in d.options})
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id, elf.id])
    answer(s)
    assert s.state.cards[bear.id].zone == s.state.cards[elf.id].zone == 'p1:hand'
    assert s.state.cards[domri.id].counters['loyalty'] == 2
    to_phase(s, 'main1', 7)
    act(s, 'p1', type='counter', card_ids=[domri.id], kind='loyalty', delta=6)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=domri.id, ability=2)
    answer(s)
    assert s.state.cards[domri.id].zone == 'p1:graveyard'
    to_phase(s, 'end', 7)
    answer(s)
    beasts = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield' and c.name == 'Beast']
    assert len(beasts) == 1
    ch = Plan(s.state, 'p1', cards, None).ch(beasts[0])
    assert ch.pt == (4, 4) and 'trample' in ch.keywords and ch.colors == frozenset({'R', 'G'})
    roundtrip(s)


def test_zero_mana_land_activation_does_not_trigger_overabundance(cards):
    s = game(cards)
    put(s, 'Overabundance', 'battlefield')
    source = put(s, "Gaea's Cradle", 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    answer(s)
    assert s.state.cards[source.id].tapped
    assert not s.state.players['p1'].mana_units and s.state.players['p1'].life == 40
    assert not s.state.zones.get('stack')
    roundtrip(s)


@pytest.mark.parametrize('shield', [False, True])
def test_barbflare_foreign_land_is_real_damage_source_for_lifelink_and_land_prevention(cards, shield):
    from app.rules import history
    from app.rules.plan import Plan
    s = game(cards)
    gremlin = put(s, 'Barbflare Gremlin', 'battlefield')
    act(s, 'p1', type='tap', card_ids=[gremlin.id], tapped=True)
    land = put(s, 'Dryad Arbor', 'battlefield', 'p2')
    spear = put(s, 'Shadowspear', 'battlefield', 'p2')
    rune = put(s, 'Rune of Protection: Lands', 'battlefield', 'p2')
    to_phase(s, 'main1', 5)
    wait_priority(s, 'p2')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 2})
    act(s, 'p2', type='activate_ability', card_id=spear.id, ability=2, targets=[land.id], sources=[])
    answer(s)
    assert s.state.cards[spear.id].attached_to == land.id
    if shield:
        wait_priority(s, 'p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'W': 1})
        act(s, 'p2', type='activate_ability', card_id=rune.id, ability=0, sources=[])
        from tests.test_rules_designations import settle
        settle(s)
        d = s.state.rules.decision
        if d is not None:
            assert land.id in {o.id for o in d.options}
            act(s, d.player, type='choose', decision_id=d.id, option_ids=[land.id])
        answer(s)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=land.id, ability=0)
    answer(s)
    assert s.state.players['p1'].life == s.state.players['p2'].life == 40
    log = history.log_for(Plan(s.state, 'p1', cards, None))
    assert log.lost.get('p2', 0) == log.gained.get('p2', 0) == (0 if shield else 1)
    assert not log.gained.get('p1', 0)
    roundtrip(s)


def x_trigger_order(s, double_first):
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'order_triggers'
    pending = s.state.rules.pending_triggers
    double = next(t.id for t in pending if t.name == 'Unbound Flourishing')
    other = next(t.id for t in pending if t.id != double)
    act(s, d.player, type='choose', decision_id=d.id,
        option_ids=[other, double] if double_first else [double, other])


@pytest.mark.parametrize('double_first', [False, True])
@pytest.mark.parametrize('watcher', ['Hydroid Krasis', 'Zaxara, the Exemplary'])
def test_unbound_native_cast_trigger_reads_current_x_in_both_orders(cards, double_first, watcher):
    from app.rules import history
    from app.rules.plan import Plan
    s = game(cards)
    put(s, 'Unbound Flourishing', 'battlefield')
    if watcher.startswith('Zaxara'):
        put(s, watcher, 'battlefield')
    spell = cast(s, 'Hydroid Krasis' if watcher == 'Hydroid Krasis' else 'Walking Ballista',
                 {'C': 2, 'G': 1, 'U': 1} if watcher == 'Hydroid Krasis' else {'C': 4}, x_value=2)
    x_trigger_order(s, double_first)
    answer(s)
    assert s.state.cards[spell.id].counters['+1/+1'] == 4
    if watcher == 'Hydroid Krasis':
        assert s.state.players['p1'].life == 40 + (2 if double_first else 1)
        assert history.log_for(Plan(s.state, 'p1', cards, None)).drew['p1'] == 1 + (2 if double_first else 1)
    else:
        hydras = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield' and c.name == 'Hydra']
        assert len(hydras) == 1 and hydras[0].counters['+1/+1'] == (4 if double_first else 2)
    roundtrip(s)


def test_unbound_current_x_cast_trigger_uses_countered_spell_lki_and_paid_receipt_is_original(cards):
    from tests.test_rules_wave31d_spell_copies import resolve_one
    s = game(cards)
    put(s, 'Unbound Flourishing', 'battlefield')
    spell = cast(s, 'Hydroid Krasis', {'C': 2, 'G': 1, 'U': 1}, x_value=2)
    oid = s.state.rules.object_id(spell.id)
    x_trigger_order(s, True)
    resolve_one(s)
    assert s.state.cards[spell.id].stack_info.x == 4
    assert s.state.rules.payments[oid].x == 2
    # The Krasis cast trigger is still on the stack. Counter its referenced spell.
    cast(s, 'Counterspell', {'U': 2}, targets=[spell.id], pid='p2')
    answer(s)
    assert s.state.cards[spell.id].zone == 'p1:graveyard'
    assert s.state.rules.lki[oid].x == 4
    assert s.state.players['p1'].life == 42
    roundtrip(s)


def test_unbound_actual_resolved_x_used_for_gadwick_etb_while_original_receipt_stays_paid_x(cards):
    from app.rules import history
    from app.rules.plan import Plan
    s = game(cards)
    put(s, 'Unbound Flourishing', 'battlefield')
    spell = cast(s, 'Gadwick, the Wizened', {'C': 2, 'U': 3}, x_value=2)
    answer(s)
    record = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert record.x == 2 and record.resolved_x == 4 and sum(record.mana_spent.values()) == 5
    assert history.log_for(Plan(s.state, 'p1', cards, None)).drew['p1'] == 5
    roundtrip(s)


def test_unbound_copied_permanent_spell_uses_its_current_x_but_spends_no_mana(cards):
    from app.rules import history
    from app.rules.plan import Plan
    from tests.test_rules_wave31d_spell_copies import resolve_one
    s = game(cards)
    put(s, 'Unbound Flourishing', 'battlefield')
    spell = cast(s, 'Gadwick, the Wizened', {'C': 2, 'U': 3}, x_value=2)
    resolve_one(s)
    assert s.state.cards[spell.id].stack_info.x == 4
    cast(s, 'Double Major', {'G': 1, 'U': 1}, targets=[spell.id])
    answer(s)
    records = [r for r in s.state.rules.payments.values() if r.resolved_x == 4]
    assert any(r.x == 2 and sum(r.mana_spent.values()) == 5 for r in records)
    assert any(r.x == 2 and r.mana_spent == {} and r.cast_from is None for r in records)
    assert history.log_for(Plan(s.state, 'p1', cards, None)).drew['p1'] == 9
    roundtrip(s)


@pytest.mark.parametrize('card_name', ['Hydroid Krasis', 'Gadwick, the Wizened'])
def test_unbound_changed_x_current_or_lki_pointer_and_resolved_x_cold(cards, tmp_path, card_name):
    from tests.test_rules_wave31d_spell_copies import resolve_one
    s = game(cards)
    put(s, 'Unbound Flourishing', 'battlefield')
    spell = cast(s, card_name, {'C': 2, 'G': 1, 'U': 1} if card_name == 'Hydroid Krasis' else {'C': 2, 'U': 3}, x_value=2)
    oid = s.state.rules.object_id(spell.id)
    if card_name == 'Hydroid Krasis':
        x_trigger_order(s, True)
    resolve_one(s)
    assert s.state.cards[spell.id].stack_info.x == 4 and s.state.rules.payments[oid].x == 2
    if card_name == 'Hydroid Krasis':
        cast(s, 'Counterspell', {'U': 2}, targets=[spell.id], pid='p2')
    cold_run(s, cards, tmp_path, """
answer(s)
if args[0]=='Hydroid Krasis':
    assert s.state.players['p1'].life==42
    assert s.state.cards[args[1]].zone=='p1:graveyard'
    assert s.state.rules.lki[args[2]].x==4
else:
    assert s.state.cards[args[1]].zone=='p1:battlefield'
    record=s.state.rules.payments[s.state.rules.object_id(args[1])]
    assert record.x==2 and record.resolved_x==4
    assert drawn(s)==5
""", card_name, spell.id, oid)
