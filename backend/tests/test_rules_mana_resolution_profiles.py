"""Canonical mana bodies and symbol production through native game actions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_activated_copy_family import answer
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = Path(__file__).parent / 'fixtures/mana_resolution_profiles_cards.json'


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c['name']] = card(c['name'], set_code='mrp40', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards, source_name=None, extra=()):
    names = [c['name'] for c in json.loads(DATA.read_text())] + list(extra)
    s = table(cards, names, names, names)
    for p in ('p1', 'p2', 'p3'):
        act(s, p, type='set_prefs', hold_priority=True)
    source = put(s, source_name, 'battlefield') if source_name else None
    to_phase(s, 'main1', 4)
    return (s, source) if source_name else s


def pool(s, color):
    p = s.state.players['p1']
    return p.mana.get(color, 0) + sum(u.sym == color for u in p.mana_units)


@pytest.mark.parametrize('name', ["Wizard's Rockets", 'Rubble Rouser', 'Shaun & Rebecca, Agents',
    'Vexing Puzzlebox', 'Tanuki Transplanter', 'Elemental Resonance', 'Bigger on the Inside', 'Scattering Stroke', 'Charmed Pendant',
    'Sasaya, Orochi Ascendant // Sasaya\'s Essence', 'Sorcerer Class', "Ugin's Labyrinth",
    'Sunbird Standard // Sunbird Effigy', "Forger's Foundry", 'Chaos Moon'])
def test_canonical_whole_card_coverage(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name,ability,color', [('Rubble Rouser', 1, 'R'), ('Shaun & Rebecca, Agents', 2, 'C')])
def test_production_precedes_separate_reflexive_stack_body(cards, name, ability, color):
    s, source = game(cards, name)
    fodder = put(s, 'Wizard\'s Rockets', 'graveyard')
    wait_priority(s, 'p1')
    kwargs = {'cost_choices': [{'component': 0, 'cards': [fodder.id]}]} if name == 'Rubble Rouser' else {}
    grave_before = len(s.state.zones.get('p1:graveyard', []))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability, **kwargs)
    assert pool(s, color) == 1
    assert s.state.players['p2'].life == 40
    assert len(s.state.zones.get('p1:graveyard', [])) == grave_before - (name == 'Rubble Rouser')
    assert s.state.zones.get('stack')
    roundtrip(s)
    answer(s)
    if name == 'Rubble Rouser':
        assert s.state.players['p2'].life == s.state.players['p3'].life == 39
    else:
        assert len(s.state.zones.get('p1:graveyard', [])) == grave_before + 2
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_rubble_rouser_actual_entry_discard_draw_is_optional(cards, accept):
    from tests.test_rules_activated_copy_family import cast, drawn

    s = game(cards)
    before_draw = drawn(s)
    before_grave = len(s.state.zones.get('p1:graveyard', []))
    cast(s, 'Rubble Rouser', {'C': 2, 'R': 1})
    answer(s, optional=accept)
    assert drawn(s) == before_draw + int(accept)
    assert len(s.state.zones.get('p1:graveyard', [])) == before_grave + int(accept)
    roundtrip(s)


@pytest.mark.parametrize('zone', ['hand', 'graveyard', 'library'])
def test_shaun_actual_entry_finds_animus_in_each_printed_zone(cards, zone):
    from tests.test_rules_activated_copy_family import cast
    from tests.test_rules_library_look import settle

    s = game(cards)
    animus = put(s, 'The Animus', zone)
    cast(s, 'Shaun & Rebecca, Agents', {'C': 1, 'G': 1, 'W': 1, 'U': 1})
    settle(s)
    d = s.state.rules.decision
    assert d is not None and animus.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[animus.id])
    answer(s)
    assert s.state.cards[animus.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_puzzlebox_actual_mana_roll_counters_and_hundred_counter_tutor(cards, monkeypatch):
    from tests.test_rules_library_look import settle

    monkeypatch.setattr('app.game.resolve._rng_int', lambda rng, lo, hi: 17)
    s, source = game(cards, 'Vexing Puzzlebox')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, mana_choice='U')
    assert pool(s, 'U') == 1
    assert s.state.cards[source.id].counters.get('charge', 0) == 0
    roundtrip(s)
    answer(s)
    assert s.state.cards[source.id].counters['charge'] == 17
    to_phase(s, 'main1', 7)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='charge', delta=83)
    target = put(s, "Wizard's Rockets", 'library')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    assert s.state.cards[source.id].counters.get('charge', 0) == 0
    settle(s)
    d = s.state.rules.decision
    assert d is not None and target.id in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    answer(s)
    assert s.state.cards[target.id].zone == 'p1:battlefield' and s.state.cards[target.id].tapped
    roundtrip(s)


def test_tanuki_self_attack_adds_actual_power_and_keeps_mana(cards):
    from app.rules import coverage
    from tests.test_rules_banding import attacks

    s, source = game(cards, 'Tanuki Transplanter')
    assert coverage.of_card_data(cards.resolve('Tanuki Transplanter')).level == 'FULL'
    put(s, 'Rubble Rouser', 'battlefield', 'p2')
    attacks(s, [(source, 'p2')])
    assert pool(s, 'G') == 2
    assert s.state.rules.kept_mana
    roundtrip(s)


def test_tanuki_native_reconfigure_host_attack_and_end_of_turn_cleanup(cards):
    from app.rules.plan import Plan
    from tests.test_rules_banding import attacks

    s, source = game(cards, 'Tanuki Transplanter')
    host = put(s, 'Shaun & Rebecca, Agents', 'battlefield')
    put(s, 'Rubble Rouser', 'battlefield', 'p2')
    # Age the host before the real sorcery-speed reconfigure activation.
    to_phase(s, 'main1', 7)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=[host.id])
    answer(s)
    assert s.state.cards[source.id].attached_to == host.id
    assert 'Creature' not in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).types
    attacks(s, [(host, 'p2')])
    assert pool(s, 'G') == 4
    to_phase(s, 'main2', 7)
    assert pool(s, 'G') == 4
    to_phase(s, 'main1', 10)
    assert pool(s, 'G') == 0
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=3)
    answer(s)
    assert s.state.cards[source.id].attached_to is None
    assert 'Creature' in Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).types
    roundtrip(s)


def test_elemental_resonance_produces_host_cost_during_next_first_main(cards):
    from tests.test_rules_activated_copy_family import cast

    s, host = game(cards, 'Tanuki Transplanter')
    aura = cast(s, 'Elemental Resonance', {'C': 2, 'G': 2}, targets=[host.id])
    answer(s)
    assert s.state.cards[aura.id].attached_to == host.id
    to_phase(s, 'main1', 7)
    answer(s)
    assert pool(s, 'C') == 3
    assert pool(s, 'G') == 1
    roundtrip(s)


def test_elemental_resonance_native_hybrid_symbol_choices_survive_json_recreation(cards):
    from tests.test_rules_activated_copy_family import cast
    from tests.test_rules_library_look import settle
    from tests.test_rules_qualified_attached_tutors import cold

    s, host = game(cards, 'Kitchen Finks')
    cast(s, 'Elemental Resonance', {'C': 2, 'G': 2}, targets=[host.id])
    answer(s)
    to_phase(s, 'main1', 7)
    for pick in ['0', '1']:
        settle(s)
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'mana_symbol_production'
        s = cold(s, cards)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[pick])
    answer(s)
    assert (pool(s, 'C'), pool(s, 'G'), pool(s, 'W')) == (1, 1, 1)
    roundtrip(s)


@pytest.mark.parametrize('cost,colored,expected', [
    ('{2}{W}{U}', False, [('CC',), ('W',), ('U',)]),
    ('{X}{G}', False, [('',), ('G',)]),
    ('{W/U}{2/B}{C/R}{G/P}{U/R/P}{S}', False,
     [('W', 'U'), ('CC', 'B'), ('C', 'R'), ('G',), ('U', 'R'), ('C',)]),
    ('{3}{X}{C}{W/U}{2/B}{C/R}{G/P}', True, [('W', 'U'), ('B',), ('R',), ('G',)]),
])
def test_mana_symbol_production_rule_interpretation(cost, colored, expected):
    from app.rules.mana_symbol_production import choices

    assert choices(cost, colored_only=colored) == expected


def test_bigger_inside_target_player_gets_mana_and_next_spell_cascade(cards):
    from app.rules import coverage
    from app.rules.plan import Plan
    from tests.test_rules_activated_copy_family import cast

    s, host = game(cards, 'Wizard\'s Rockets')
    aura = cast(s, 'Bigger on the Inside', {'C': 3, 'R': 1, 'G': 1}, targets=[host.id])
    answer(s)
    assert s.state.cards[aura.id].attached_to == host.id
    assert coverage.of_card_data(cards.resolve('Bigger on the Inside')).level == 'FULL'
    ability = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[host.id]).abilities
                   if 'Target player adds two mana' in a.text)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=host.id, ability=ability, targets=['p2'])
    assert not s.state.players['p2'].mana_units
    answer(s)
    p2 = s.state.players['p2']
    assert sum(p2.mana.values()) + len(p2.mana_units) == 2
    assert any(g.player == 'p2' and g.keyword == 'cascade' for g in s.state.rules.next_spell_grants)
    hit = put(s, "Wizard's Rockets", 'library', 'p2')
    target = cast(s, "Wizard's Rockets", {'C': 1})
    cast(s, 'Scattering Stroke', {'C': 2, 'U': 2}, targets=[target.id], pid='p2')
    assert not any(g.player == 'p2' and g.keyword == 'cascade' for g in s.state.rules.next_spell_grants)
    assert any(any(e.get('do') == 'cascade' for e in entry.effects) for entry in s.state.rules.stack.values())
    roundtrip(s)
    answer(s)
    assert s.state.cards[hit.id].zone == 'p2:battlefield'
    assert s.state.cards[hit.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_scattering_stroke_clash_delays_optional_all_mana_to_next_main(cards, accept):
    from tests.test_rules_activated_copy_family import cast

    s = game(cards)
    put(s, 'Bigger on the Inside', 'library')
    put(s, 'Wizard\'s Rockets', 'library', 'p2')
    put(s, 'Wizard\'s Rockets', 'library', 'p3')
    target = cast(s, 'Wizard\'s Rockets', {'C': 1})
    cast(s, 'Scattering Stroke', {'C': 2, 'U': 2}, targets=[target.id])
    answer(s)
    assert s.state.cards[target.id].zone == 'p1:graveyard'
    assert pool(s, 'C') == 0
    assert len(s.state.rules.delayed) == 1
    act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'hand'})
    roundtrip(s)
    to_phase(s, 'main2', 4)
    answer(s, optional=accept)
    assert pool(s, 'C') == int(accept)
    assert not s.state.rules.delayed
    roundtrip(s)


def test_elemental_resonance_reads_last_enchanted_permanent_after_host_leaves(cards):
    from tests.test_rules_activated_copy_family import cast

    s, host = game(cards, 'Tanuki Transplanter')
    aura = cast(s, 'Elemental Resonance', {'C': 2, 'G': 2}, targets=[host.id])
    answer(s)
    to_phase(s, 'main1', 7)
    assert s.state.zones.get('stack')
    act(s, 'p1', type='move', card_ids=[host.id], to={'player': 'p1', 'zone': 'graveyard'})
    answer(s)
    assert s.state.cards[aura.id].zone == 'p1:graveyard'
    assert (pool(s, 'C'), pool(s, 'G')) == (3, 1), [
        (oid, snap.card, snap.attached_to, snap.attached_object) for oid, snap in s.state.rules.lki.items()
        if snap.card == aura.id]
    roundtrip(s)


@pytest.mark.parametrize('depart', [False, True])
def test_elemental_resonance_reads_new_host_after_reattachment(cards, depart):
    from tests.test_rules_activated_copy_family import cast

    s, original = game(cards, 'Tanuki Transplanter')
    newer = put(s, 'Rubble Rouser', 'battlefield')
    aura = cast(s, 'Elemental Resonance', {'C': 2, 'G': 2}, targets=[original.id])
    answer(s)
    to_phase(s, 'main1', 7)
    assert s.state.zones.get('stack')
    act(s, 'p1', type='attach', card_ids=[aura.id], to=newer.id)
    if depart:
        act(s, 'p1', type='move', card_ids=[newer.id], to={'player': 'p1', 'zone': 'graveyard'})
    roundtrip(s)
    answer(s)
    assert (pool(s, 'C'), pool(s, 'R'), pool(s, 'G')) == (2, 1, 0)
    roundtrip(s)


def test_elemental_resonance_source_departure_retains_exact_host_cold(cards):
    from tests.test_rules_activated_copy_family import cast
    from tests.test_rules_qualified_attached_tutors import cold

    s, host = game(cards, 'Tanuki Transplanter')
    aura = cast(s, 'Elemental Resonance', {'C': 2, 'G': 2}, targets=[host.id])
    answer(s)
    to_phase(s, 'main1', 7)
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'graveyard'})
    s = cold(s, cards)
    answer(s)
    assert (pool(s, 'C'), pool(s, 'G')) == (3, 1)
    roundtrip(s)


def test_live_unattached_source_never_reuses_retained_host(cards):
    from app.rules import attached_kindred_look
    from app.rules.plan import Plan

    s, source = game(cards, 'Tanuki Transplanter')
    host = put(s, 'Rubble Rouser', 'battlefield')
    act(s, 'p1', type='attach', card_ids=[source.id], to=host.id)
    act(s, 'p1', type='detach', card_ids=[source.id])
    plan = Plan(s.state, 'p1', cards, None)
    oid = plan.oid(source)
    assert oid in plan.rules.last_attached_hosts
    assert attached_kindred_look.host_reference(plan, {'source_card': source.id, 'source_object': oid}, {}) is None
    roundtrip(s)


@pytest.mark.parametrize('replacement', ['none', 'double', 'exile'])
def test_pendant_ordinary_library_cost_retains_actual_milled_symbols(cards, replacement):
    from tests.test_rules_qualified_attached_tutors import cold

    s, source = game(cards, 'Charmed Pendant')
    if replacement == 'double':
        put(s, 'Bruvac the Grandiloquent', 'battlefield', 'p2')
    elif replacement == 'exile':
        put(s, 'Rest in Peace', 'battlefield')
    first = put(s, 'Kitchen Finks', 'library')
    if replacement == 'double':
        second = put(s, 'Disenchant', 'library')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert pool(s, 'G') == pool(s, 'W') == 0
    assert s.state.zones.get('stack')
    assert s.state.cards[first.id].zone == ('p1:exile' if replacement == 'exile' else 'p1:graveyard')
    if replacement == 'double':
        assert s.state.cards[second.id].zone == 'p1:graveyard'
    # Subsequent movement cannot substitute a fresh incarnation for the paid card.
    act(s, 'p1', type='move', card_ids=[first.id], to={'player': 'p1', 'zone': 'hand'})
    s = cold(s, cards)
    answer(s)
    assert (pool(s, 'C'), pool(s, 'G'), pool(s, 'W')) == (0, 2, int(replacement == 'double'))
    roundtrip(s)


def test_pendant_actual_rings_copy_reuses_original_cost_card_without_milling_again(cards):
    s, source = game(cards, 'Charmed Pendant')
    put(s, 'Rings of Brighthearth', 'battlefield')
    put(s, 'Kitchen Finks', 'library')
    before = len(s.state.zones['p1:library'])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    answer(s)
    assert len(s.state.zones['p1:library']) == before - 1
    assert (pool(s, 'C'), pool(s, 'G')) == (0, 4)
    roundtrip(s)


def test_pendant_old_unknown_cost_receipt_stops_with_manual_notice(cards):
    from tests.test_rules_library_look import settle

    s, source = game(cards, 'Charmed Pendant')
    put(s, 'Kitchen Finks', 'library')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    payment = next(p for p in s.state.rules.payments.values() if p.card in s.state.rules.stack)
    payment.milled_facts = None
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'manual_resolution'
    assert 'older activation' in d.prompt
    assert pool(s, 'G') == pool(s, 'W') == 0
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['done'])
    assert not s.state.rules.decision


def test_pendant_empty_library_rejects_unpaid_activation_atomically(cards):
    from app.game.errors import ActionError

    s, source = game(cards, 'Charmed Pendant')
    act(s, 'p1', type='move', card_ids=list(s.state.zones['p1:library']),
        to={'player': 'p1', 'zone': 'hand'})
    wait_priority(s, 'p1')
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert s.state.model_dump_json() == before


@pytest.mark.parametrize('lands', [0, 6, 7])
def test_sasaya_actual_reveal_entire_hand_activation_checks_seven_lands_on_resolution(cards, lands):
    s, source = game(cards, 'Sasaya, Orochi Ascendant // Sasaya\'s Essence', extra=['Forest'] * 6)
    hand = list(s.state.zones.get('p1:hand', []))
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'library'})
    paid = [c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1'][:lands]
    if paid:
        act(s, 'p1', type='move', card_ids=[c.id for c in paid], to={'player': 'p1', 'zone': 'hand'})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert s.state.zones.get('stack')
    assert all('*' in s.state.cards[c.id].revealed_to for c in paid)
    if lands == 7:
        from app.rules import characteristics
        from app.rules.plan import Plan

        plan = Plan(s.state, 'p1', cards, None)
        assert characteristics.flippable(s.state.cards[source.id], cards), cards.get(source.card_id)
        assert sum(c.zone == 'p1:hand' and plan.ch(c).is_land for c in s.state.cards.values()) >= 7
        assert any(e.get('do') == 'flip_if_seven_hand_lands' for entry in s.state.rules.stack.values() for e in entry.effects), s.state.rules.stack
    answer(s)
    assert s.state.cards[source.id].flipped == (lands >= 7)
    assert all(s.state.cards[c.id].zone == 'p1:hand' for c in paid)
    assert all(not s.state.cards[c.id].revealed_to for c in paid)
    roundtrip(s)


def test_sasaya_four_valleys_produce_mixed_three_additional_mana_atomically(cards):
    s, source = game(cards, 'Sasaya, Orochi Ascendant // Sasaya\'s Essence',
        extra=['Forest'] * 6 + ['Mossfire Valley'] * 3)
    forests = [c.id for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1']
    act(s, 'p1', type='move', card_ids=forests, to={'player': 'p1', 'zone': 'hand'})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    answer(s)
    assert s.state.cards[source.id].flipped
    from app.rules import tap_mana
    assert any(d.get('same_name_count') for _, d, _ in tap_mana._triggers(s.state, cards))
    valleys = [c for c in s.state.cards.values() if c.name == 'Mossfire Valley' and c.owner == 'p1']
    act(s, 'p1', type='move', card_ids=[c.id for c in valleys], to={'player': 'p1', 'zone': 'battlefield'})
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=valleys[0].id, ability=0)
    for pick in ['0', '1', '1']:
        assert (pool(s, 'R'), pool(s, 'G')) == (1, 1)
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'staged_mana_composition'
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[pick])
    assert (pool(s, 'C'), pool(s, 'R'), pool(s, 'G')) == (0, 2, 3)
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_sasaya_overlapping_reveal_costs_cleanup_removed_original_and_preserve_public_card(cards):
    from tests.test_rules_qualified_attached_tutors import cold

    s, source = game(cards, 'Sasaya, Orochi Ascendant // Sasaya\'s Essence', extra=['Forest'] * 5)
    forests = [c.id for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1']
    act(s, 'p1', type='move', card_ids=forests, to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='reveal', card_ids=[forests[0]])
    for _ in range(2):
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert len(s.state.rules.revealed_activation_costs) == 2
    s = cold(s, cards)
    removed = s.state.zones['stack'][-1]
    act(s, 'p1', type='move', card_ids=[removed], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='pass_priority')
    assert all('*' in s.state.cards[cid].revealed_to for cid in forests)
    assert len(s.state.rules.revealed_activation_costs) == 1
    answer(s)
    assert not s.state.rules.revealed_activation_costs
    assert '*' in s.state.cards[forests[0]].revealed_to
    assert all(not s.state.cards[cid].revealed_to for cid in forests[1:])
    roundtrip(s)


def test_class_actual_entry_levels_restricted_mana_and_spell_damage(cards):
    from app.rules.plan import Plan
    from tests.test_rules_activated_copy_family import cast, drawn

    s = game(cards)
    before = drawn(s)
    source = cast(s, 'Sorcerer Class', {'U': 1, 'R': 1})
    answer(s)
    assert drawn(s) == before + 2
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'U': 1, 'R': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    answer(s)
    host = put(s, 'Rubble Rouser', 'battlefield')
    to_phase(s, 'main1', 7)
    plan = Plan(s.state, 'p1', cards, None)
    index = next(a.index for a in plan.ch(s.state.cards[host.id]).abilities if 'gain a Class level' in a.text)
    for _ in range(1):
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=host.id, ability=index, mana_choice='U')
    assert any(u.only == 'instant_sorcery_or_class_level' for u in s.state.players['p1'].mana_units)
    from app.game.errors import ActionError
    denied = put(s, "Wizard's Rockets", 'hand')
    with pytest.raises(ActionError, match='mana|pay'):
        act(s, 'p1', type='cast_spell', card_id=denied.id, sources=[])
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'R': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=3)
    answer(s)
    target = cast(s, "Wizard's Rockets", {'C': 1})
    cast(s, 'Scattering Stroke', {'C': 2, 'U': 2}, targets=[target.id])
    answer(s)
    assert s.state.players['p2'].life == s.state.players['p3'].life == 39
    roundtrip(s)


@pytest.mark.parametrize('imprint', [False, True])
def test_ugin_native_optional_imprint_conditional_mana_and_linked_return(cards, imprint):
    s = game(cards)
    source = put(s, "Ugin's Labyrinth", 'hand')
    target = put(s, 'Emrakul, the Aeons Torn', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='play_land', card_id=source.id)
    answer(s, optional=imprint)
    assert s.state.cards[target.id].zone == ('p1:exile' if imprint else 'p1:hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert pool(s, 'C') == 1 + int(imprint)
    assert not s.state.zones.get('stack')
    roundtrip(s)
    to_phase(s, 'main1', 7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    answer(s)
    assert s.state.cards[target.id].zone == 'p1:hand'
    to_phase(s, 'main1', 10)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert pool(s, 'C') == 1
    roundtrip(s)


def test_class_spell_sources_use_lifelink_and_stack_lki_with_resolution_time_cast_count(cards):
    from tests.test_rules_activated_copy_family import cast

    s, source = game(cards, 'Sorcerer Class')
    for ability, mana in [(1, {'U': 1, 'R': 1}), (3, {'C': 3, 'U': 1, 'R': 1})]:
        wait_priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana=mana)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability)
        answer(s)
    grant = put(s, 'Soulfire Grand Master', 'battlefield')
    victim = put(s, "Wizard's Rockets", 'battlefield', 'p2')
    first = cast(s, 'Disenchant', {'C': 1, 'W': 1}, targets=[victim.id])
    first_oid = s.state.rules.object_id(first.id)
    cast(s, 'Scattering Stroke', {'C': 2, 'U': 2}, targets=[first.id])
    answer(s)
    assert s.state.cards[first.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == s.state.players['p3'].life == 36
    assert s.state.players['p1'].life == 48
    act(s, 'p1', type='move', card_ids=[grant.id], to={'player': 'p1', 'zone': 'graveyard'})
    from app.rules.plan import Plan
    from app.rules.triggers import _snapshot_card

    plan = Plan(s.state, 'p1', cards, None)
    assert 'lifelink' not in plan.ch(s.state.cards[first.id]).keywords
    assert 'lifelink' in _snapshot_card(plan, s.state.rules.lki[first_oid])[1].keywords
    roundtrip(s)


def test_class_native_spell_copy_does_not_create_another_cast_trigger(cards):
    from app.rules.plan import Plan
    from tests.test_rules_activated_copy_family import cast

    s, source = game(cards, 'Sorcerer Class')
    for ability, mana in [(1, {'U': 1, 'R': 1}), (3, {'C': 3, 'U': 1, 'R': 1})]:
        wait_priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana=mana)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability)
        answer(s)
    copier = put(s, 'Lithoform Engine', 'battlefield')
    victim = put(s, "Wizard's Rockets", 'battlefield', 'p2')
    spell = cast(s, 'Disenchant', {'C': 1, 'W': 1}, targets=[victim.id])
    ability = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(s.state.cards[copier.id]).abilities
                   if 'Copy target instant or sorcery spell' in a.text)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3})
    act(s, 'p1', type='activate_ability', card_id=copier.id, ability=ability, targets=[spell.id])
    answer(s)
    assert s.state.players['p2'].life == s.state.players['p3'].life == 39
    roundtrip(s)


def test_class_damage_source_is_named_spell_for_actual_player_protection(cards):
    from tests.test_rules_activated_copy_family import cast
    from tests.test_rules_library_look import settle

    s, source = game(cards, 'Sorcerer Class')
    for ability, mana in [(1, {'U': 1, 'R': 1}), (3, {'C': 3, 'U': 1, 'R': 1})]:
        wait_priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana=mana)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability)
        answer(s)
    to_phase(s, 'main1', 5)
    cast(s, 'Runed Halo', {'W': 2}, pid='p2')
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, name='Disenchant')
    answer(s)
    victim = put(s, "Wizard's Rockets", 'battlefield', 'p2')
    cast(s, 'Disenchant', {'C': 1, 'W': 1}, targets=[victim.id])
    answer(s)
    assert s.state.players['p2'].life == 40
    assert s.state.players['p3'].life == 39
    roundtrip(s)


def test_ugin_copied_imprint_links_two_actual_cards_and_return_returns_all(cards):
    s = game(cards, extra=['Emrakul, the Aeons Torn'])
    source = put(s, "Ugin's Labyrinth", 'hand')
    copier = put(s, 'Strionic Resonator', 'battlefield')
    material = [c.id for c in s.state.cards.values() if c.name == 'Emrakul, the Aeons Torn' and c.owner == 'p1']
    act(s, 'p1', type='move', card_ids=material, to={'player': 'p1', 'zone': 'hand'})
    wait_priority(s, 'p1')
    act(s, 'p1', type='play_land', card_id=source.id)
    trigger = s.state.zones['stack'][-1]
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=copier.id, ability=0, targets=[trigger])
    answer(s)
    assert all(s.state.cards[cid].zone == 'p1:exile' for cid in material)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    assert pool(s, 'C') == 2
    to_phase(s, 'main1', 7)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    answer(s)
    assert all(s.state.cards[cid].zone == 'p1:hand' for cid in material)
    roundtrip(s)


@pytest.mark.parametrize('moved', ['card', 'source', 'controller'])
def test_ugin_link_follows_exact_source_and_exiled_card_incarnations(cards, moved):
    s = game(cards)
    source = put(s, "Ugin's Labyrinth", 'hand')
    material = put(s, 'Emrakul, the Aeons Torn', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='play_land', card_id=source.id)
    answer(s)
    assert s.state.cards[material.id].zone == 'p1:exile'
    if moved == 'controller':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
        player = 'p2'
    else:
        target = material if moved == 'card' else source
        act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'hand'})
        act(s, 'p1', type='move', card_ids=[target.id], to={'player': 'p1', 'zone': 'exile' if moved == 'card' else 'battlefield'})
        answer(s, optional=False)
        player = 'p1'
    wait_priority(s, player)
    act(s, player, type='activate_ability', card_id=source.id, ability=1)
    p = s.state.players[player]
    assert p.mana.get('C', 0) + sum(u.sym == 'C' for u in p.mana_units) == (2 if moved == 'controller' else 1)
    roundtrip(s)


def test_sunbird_actual_front_mana_craft_entry_cda_and_exact_exiled_color_union(cards):
    from app.rules.plan import Plan

    s, source = game(cards, 'Sunbird Standard // Sunbird Effigy')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, mana_choice='U')
    assert pool(s, 'U') == 1
    materials = [put(s, name, 'graveyard') for name in ['Kitchen Finks', 'Rubble Rouser']]
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
        cost_choices=[{'component': 2, 'cards': [c.id for c in materials]}])
    assert s.state.cards[source.id].zone == 'p1:exile'
    answer(s)
    plan = Plan(s.state, 'p1', cards, None)
    back = s.state.cards[source.id]
    assert back.zone == 'p1:battlefield' and back.face == 1
    assert plan.ch(back).pt == (3, 3)
    assert {'flying', 'vigilance', 'haste'} <= plan.ch(back).keywords
    assert not s.state.rules.pending_crafts
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    assert (pool(s, 'U'), pool(s, 'W'), pool(s, 'G'), pool(s, 'R')) == (0, 1, 1, 1)
    act(s, 'p1', type='move', card_ids=[materials[1].id], to={'player': 'p1', 'zone': 'hand'})
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).pt == (2, 2)
    act(s, 'p1', type='move', card_ids=[materials[1].id], to={'player': 'p1', 'zone': 'exile'})
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).pt == (2, 2)
    act(s, 'p1', type='move', card_ids=[materials[0].id], to={'player': 'p1', 'zone': 'hand'})
    answer(s)
    act(s, 'p1', type='pass_priority')
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('kind', ['copied_ability', 'redirected_entry', 'copied_permanent'])
def test_sunbird_native_craft_links_do_not_leak_to_later_or_copied_objects(cards, kind):
    s, source = game(cards, 'Sunbird Standard // Sunbird Effigy')
    material = put(s, 'Kitchen Finks', 'graveyard')
    if kind == 'copied_ability':
        put(s, 'Rings of Brighthearth', 'battlefield')
    elif kind == 'redirected_entry':
        put(s, 'Containment Priest', 'battlefield', 'p2')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 7 if kind == 'copied_ability' else 5})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
        cost_choices=[{'component': 2, 'cards': [material.id]}])
    answer(s)
    assert not s.state.rules.pending_crafts
    if kind == 'redirected_entry':
        assert s.state.cards[source.id].zone == 'p1:exile'
        assert not any(s.state.rules.crafted_materials.values())
    else:
        from app.rules.plan import Plan

        plan = Plan(s.state, 'p1', cards, None)
        assert plan.ch(s.state.cards[source.id]).pt == (2, 2)
        if kind == 'copied_permanent':
            mirror = put(s, 'Mirage Mirror', 'battlefield')
            act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
            wait_priority(s, 'p1')
            act(s, 'p1', type='activate_ability', card_id=mirror.id, ability=0, targets=[source.id])
            answer(s)
            assert s.state.cards[mirror.id].zone == 'p1:graveyard'
        old = s.state.rules.object_id(source.id)
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
        assert s.state.rules.object_id(source.id) != old
        assert s.state.rules.crafted_materials[s.state.rules.object_id(source.id)] == []
    roundtrip(s)


def test_sunbird_legacy_absent_craft_knowledge_preserves_unknown_cda_and_notices_manual_mana(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    from app.rules.plan import Plan

    s, source = game(cards, 'Sunbird Standard // Sunbird Effigy')
    material = put(s, 'Kitchen Finks', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
        cost_choices=[{'component': 2, 'cards': [material.id]}])
    answer(s)
    saved = s.state.model_dump(mode='json')
    saved['rules'].pop('crafted_materials')
    saved['rules'].pop('pending_crafts')
    s = GameSession(GameState.model_validate(saved), cards=cards)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).pt is None
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2)
    d = s.state.rules.decision
    assert d is not None and d.kind == 'manual_resolution'
    assert 'no recorded craft materials' in d.prompt
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert pool(s, 'W') == pool(s, 'G') == 0


@pytest.mark.parametrize('accept', [False, True])
def test_foundry_native_spent_unit_optional_exile_then_freecast_packet(cards, accept):
    from tests.test_rules_activated_copy_family import cast, drawn
    from tests.test_rules_library_look import settle

    s, source = game(cards, "Forger's Foundry")
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert pool(s, 'U') == 1 and not s.state.zones.get('stack')
    before = drawn(s)
    spell = cast(s, 'Opt', {})
    assert len(s.state.zones['stack']) == 2
    for _ in range(40):
        settle(s)
        d = s.state.rules.decision
        assert d is not None
        if d.resume['step'] == 'optional_resolve_exile':
            break
        ids = [o.id for o in d.options]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep' if 'keep' in ids else ids[0]])
    else:
        raise AssertionError('Foundry optional replacement never offered')
    assert drawn(s) == before + 1
    assert s.state.cards[spell.id].zone == 'stack'
    roundtrip(s)

    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes' if accept else 'no'])
    assert s.state.cards[spell.id].zone == ('p1:exile' if accept else 'p1:graveyard')
    if accept:
        to_phase(s, 'main1', 7)
        wait_priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 2})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
        settle(s)
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'free_cast_pick'
        act(s, d.player, type='choose', decision_id=d.id,
            option_ids=[next(o.id for o in d.options if o.card_id == spell.id)])
        answer(s)
        assert s.state.cards[spell.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('first', ['rip', 'foundry_decline', 'foundry_accept'])
def test_foundry_optional_replacement_joins_native_616_frontier_before_may_choice(cards, first):
    from tests.test_rules_activated_copy_family import cast
    from tests.test_rules_library_look import settle
    from tests.test_rules_qualified_attached_tutors import cold

    s, source = game(cards, "Forger's Foundry")
    put(s, 'Rest in Peace', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    source_oid = s.state.rules.object_id(source.id)
    spell = cast(s, 'Opt', {})
    for _ in range(40):
        settle(s)
        d = s.state.rules.decision
        assert d is not None
        if d.resume['step'] == 'zone_replace_order':
            break
        assert d.resume['step'] != 'optional_resolve_exile'
        ids = [o.id for o in d.options]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep' if 'keep' in ids else ids[0]])
    else:
        raise AssertionError('No 616 replacement frontier')
    s = cold(s, cards)
    label = 'Rest in Peace' if first == 'rip' else "Forger's Foundry"
    option = next(o.id for o in d.options if label in o.label)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[option])
    if first != 'rip':
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'optional_resolve_exile'
        s = cold(s, cards)
        act(s, d.player, type='choose', decision_id=d.id,
            option_ids=['yes' if first == 'foundry_accept' else 'no'])
    else:
        assert s.state.rules.decision is None
    assert s.state.cards[spell.id].zone == 'p1:exile'
    linked = s.state.rules.exiled_with.get(source_oid, [])
    assert (s.state.rules.object_id(spell.id) in linked) == (first == 'foundry_accept')
    roundtrip(s)


@pytest.mark.parametrize('departure', ['before_spend', 'before_trigger', 'new_incarnation'])
def test_foundry_actual_spent_unit_keeps_original_link_after_source_departure(cards, departure):
    from tests.test_rules_activated_copy_family import cast

    s, source = game(cards, "Forger's Foundry")
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    old = s.state.rules.object_id(source.id)
    if departure == 'before_spend':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    spell = cast(s, 'Opt', {})
    if departure != 'before_spend':
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
        if departure == 'new_incarnation':
            act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
    answer(s)
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert s.state.rules.object_id(spell.id) in s.state.rules.exiled_with[old]
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(source.id))
    roundtrip(s)


def test_foundry_multiple_actual_spent_sources_decline_one_then_apply_other(cards):
    from tests.test_rules_activated_copy_family import cast
    from tests.test_rules_library_look import settle

    s = game(cards, extra=["Forger's Foundry"])
    foundries = [c for c in s.state.cards.values() if c.name == "Forger's Foundry" and c.owner == 'p1']
    act(s, 'p1', type='move', card_ids=[c.id for c in foundries], to={'player': 'p1', 'zone': 'battlefield'})
    target = cast(s, "Wizard's Rockets", {'C': 1})
    for source in foundries:
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    spell = cast(s, 'Counterspell', {}, targets=[target.id])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'zone_replace_order'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'optional_resolve_exile'
    first_source = d.resume['candidate']['rider']['resolve_exile_record']['source_object']
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['no'])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'optional_resolve_exile'
    second_source = d.resume['candidate']['rider']['resolve_exile_record']['source_object']
    assert second_source != first_source
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes'])
    assert s.state.cards[spell.id].zone == 'p1:exile'
    assert not s.state.rules.exiled_with.get(first_source)
    assert s.state.rules.object_id(spell.id) in s.state.rules.exiled_with[second_source]
    roundtrip(s)


def test_foundry_actual_stolen_spell_exiles_in_owners_zone_with_original_source_link(cards):
    from tests.test_rules_activated_copy_family import cast
    from tests.test_rules_library_look import settle

    s, source = game(cards, "Forger's Foundry")
    spell = put(s, 'Opt', 'library', 'p2')
    cast(s, 'Gonti, Lord of Luxury', {'C': 2, 'B': 2})
    for _ in range(50):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        ids = [o.id for o in d.options]
        selected = ['p2'] if 'p2' in ids else [o.id for o in d.options if o.card_id == spell.id]
        if not selected:
            selected = ids[:max(1, d.min_choices)]
        act(s, d.player, type='choose', decision_id=d.id, option_ids=selected)
    assert s.state.cards[spell.id].zone == 'p2:exile'
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    oid = s.state.rules.object_id(source.id)
    act(s, 'p1', type='cast_spell', card_id=spell.id, sources=[])
    answer(s)
    assert s.state.cards[spell.id].zone == 'p2:exile'
    assert s.state.rules.object_id(spell.id) in s.state.rules.exiled_with[oid]
    roundtrip(s)


def test_foundry_packet_casts_multiple_actual_linked_cards_without_cap(cards):
    from tests.test_rules_library_look import settle

    s, source = game(cards, "Forger's Foundry", extra=['Opt'])
    opts = [c.id for c in s.state.cards.values() if c.name == 'Opt' and c.owner == 'p1']
    for turn, cid in zip((4, 7), opts, strict=True):
        to_phase(s, 'main1', turn)
        act(s, 'p1', type='move', card_ids=[cid], to={'player': 'p1', 'zone': 'hand'})
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
        act(s, 'p1', type='cast_spell', card_id=cid, sources=[])
        answer(s)
        assert s.state.cards[cid].zone == 'p1:exile'
    assert len(s.state.rules.exiled_with[s.state.rules.object_id(source.id)]) == 2
    to_phase(s, 'main1', 10)
    wait_priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'U': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    for cid in opts:
        settle(s)
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'free_cast_pick'
        act(s, d.player, type='choose', decision_id=d.id,
            option_ids=[next(o.id for o in d.options if o.card_id == cid)])
    answer(s)
    assert all(s.state.cards[cid].zone == 'p1:graveyard' for cid in opts)
    roundtrip(s)


def test_chaos_moon_odd_fixed_red_cohort_and_source_preserving_extra_expire_at_cleanup(cards):
    from app.rules.plan import Plan

    s, source = game(cards, 'Chaos Moon', extra=['Rubble Rouser'])
    mountain = put(s, 'Mountain', 'battlefield')
    red = put(s, 'Rubble Rouser', 'battlefield')
    answer(s, optional=False)
    to_phase(s, 'upkeep', 5)
    answer(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[red.id]).pt == (2, 5)
    original = s.state.rules.object_id(source.id)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    late = next(c for c in s.state.cards.values() if c.name == 'Rubble Rouser' and c.owner == 'p1' and c.id != red.id)
    act(s, 'p1', type='move', card_ids=[late.id], to={'player': 'p1', 'zone': 'battlefield'})
    answer(s, optional=False)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[late.id]).pt == (1, 4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=mountain.id, ability=0)
    assert pool(s, 'R') == 2
    assert any(u.src == original and u.sym == 'R' for u in s.state.players['p1'].mana_units)
    to_phase(s, 'main1', 7)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[red.id]).pt == (1, 4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=mountain.id, ability=0)
    assert pool(s, 'R') == 1
    roundtrip(s)


def test_chaos_moon_reads_resolution_parity_and_preserves_replaced_mana_quantity(cards):
    s, source = game(cards, 'Chaos Moon')
    mountain = put(s, 'Mossfire Valley', 'battlefield')
    extra = put(s, 'Rubble Rouser', 'hand')
    put(s, 'Prismatic Omen', 'battlefield')
    to_phase(s, 'upkeep', 5)
    # Three permanents at trigger time, four at resolution: current parity wins.
    act(s, 'p1', type='move', card_ids=[extra.id], to={'player': 'p1', 'zone': 'battlefield'})
    answer(s, optional=False)
    from app.rules.plan import Plan

    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[extra.id]).pt == (0, 3)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=mountain.id, ability=0)
    answer(s)
    assert (pool(s, 'C'), pool(s, 'R'), pool(s, 'G')) == (2, 0, 0)
    roundtrip(s)


@pytest.mark.parametrize('x', [0, 3])
def test_wizards_rockets_pays_locked_announced_x_then_produces_mix_before_death_draw(cards, x):
    from tests.test_rules_activated_copy_family import drawn

    s, source = game(cards, 'Wizard\'s Rockets')
    before = drawn(s)
    if x:
        act(s, 'p1', type='add_mana', player='p1', mana={'C': x})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, x_value=x)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert pool(s, 'C') == 0
    for color in ['U', 'G', 'G'][:x]:
        assert drawn(s) == before
        assert not s.state.zones.get('stack')
        d = s.state.rules.decision
        assert d.resume['step'] == 'mana_composition'
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[color])
    assert (pool(s, 'U'), pool(s, 'G')) == ((1, 2) if x else (0, 0))
    answer(s)
    assert drawn(s) == before + 1
    roundtrip(s)


@pytest.mark.parametrize('family', ['composition', 'symbols', 'optional', 'pendant', 'sasaya', 'sasaya_reveal', 'class', 'ugin', 'sunbird', 'sunbird_legacy'])
def test_new_mana_pause_families_resume_in_fresh_process(cards, tmp_path, family):
    import subprocess
    import sys

    from tests.test_rules_activated_copy_family import cast
    from tests.test_rules_library_look import settle

    if family.startswith('sunbird'):
        s, source = game(cards, 'Sunbird Standard // Sunbird Effigy')
        material = put(s, 'Kitchen Finks', 'graveyard')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 5})
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
            cost_choices=[{'component': 2, 'cards': [material.id]}])
        if family == 'sunbird_legacy':
            answer(s)
        expected = None
    elif family == 'ugin':
        s = game(cards)
        source = put(s, "Ugin's Labyrinth", 'hand')
        put(s, 'Emrakul, the Aeons Torn', 'hand')
        wait_priority(s, 'p1')
        act(s, 'p1', type='play_land', card_id=source.id)
        expected = None
    elif family == 'class':
        s, source = game(cards, 'Sorcerer Class')
        for ability, mana in [(1, {'U': 1, 'R': 1}), (3, {'C': 3, 'U': 1, 'R': 1})]:
            wait_priority(s, 'p1')
            act(s, 'p1', type='add_mana', player='p1', mana=mana)
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability)
            answer(s)
        put(s, 'Soulfire Grand Master', 'battlefield')
        victim = put(s, "Wizard's Rockets", 'battlefield', 'p2')
        first = cast(s, 'Disenchant', {'C': 1, 'W': 1}, targets=[victim.id])
        cast(s, 'Scattering Stroke', {'C': 2, 'U': 2}, targets=[first.id])
        expected = None
    elif family in ('sasaya', 'sasaya_reveal'):
        s, source = game(cards, 'Sasaya, Orochi Ascendant // Sasaya\'s Essence',
            extra=['Forest'] * 6 + ['Mossfire Valley'] * 3)
        forests = [c.id for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p1']
        act(s, 'p1', type='move', card_ids=forests, to={'player': 'p1', 'zone': 'hand'})
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
        expected = None
        if family == 'sasaya':
            answer(s)
            valleys = [c.id for c in s.state.cards.values() if c.name == 'Mossfire Valley' and c.owner == 'p1']
            act(s, 'p1', type='move', card_ids=valleys, to={'player': 'p1', 'zone': 'battlefield'})
            act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
            wait_priority(s, 'p1')
            act(s, 'p1', type='activate_ability', card_id=valleys[0], ability=0)
            expected = 'staged_mana_composition'
    elif family == 'composition':
        s, source = game(cards, "Wizard's Rockets")
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, x_value=1)
        expected = 'mana_composition'
    elif family == 'pendant':
        s, source = game(cards, 'Charmed Pendant')
        put(s, 'Kitchen Finks', 'library')
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
        settle(s)
        expected = 'mana_symbol_production'
    elif family == 'symbols':
        s, host = game(cards, 'Kitchen Finks')
        cast(s, 'Elemental Resonance', {'C': 2, 'G': 2}, targets=[host.id])
        answer(s)
        to_phase(s, 'main1', 7)
        settle(s)
        expected = 'mana_symbol_production'
    else:
        s = game(cards)
        put(s, 'Bigger on the Inside', 'library')
        put(s, "Wizard's Rockets", 'library', 'p2')
        put(s, "Wizard's Rockets", 'library', 'p3')
        target = cast(s, "Wizard's Rockets", {'C': 1})
        cast(s, 'Scattering Stroke', {'C': 2, 'U': 2}, targets=[target.id])
        answer(s)
        to_phase(s, 'main2', 4)
        settle(s)
        expected = 'optional_mana_output'
    assert (s.state.rules.decision.resume['step'] if s.state.rules.decision else None) == expected
    path = tmp_path / 'mana.json'
    path.write_text(s.state.model_dump_json())
    if family == 'sunbird_legacy':
        old = json.loads(path.read_text())
        old['rules'].pop('crafted_materials')
        old['rules'].pop('pending_crafts')
        path.write_text(json.dumps(old))
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, family = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
for _ in range(80):
    d = s.state.rules.decision
    if d is not None:
        step = d.resume['step']
        ids = [o.id for o in d.options]
        option = 'G' if step == 'mana_composition' else '0' if step in ('mana_symbol_production', 'staged_mana_composition') else 'yes' if 'yes' in ids else 'keep' if 'keep' in ids else ids[0]
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': [option]})
    elif s.state.zones.get('stack'):
        s.perform(s.state.rules.priority, {'type': 'pass_priority'})
    else:
        break
p = s.state.players['p1']
got = lambda c: p.mana.get(c, 0) + sum(u.sym == c for u in p.mana_units)
if family == 'ugin':
    source = next(c for c in s.state.cards.values() if c.name == "Ugin's Labyrinth" and c.zone == 'p1:battlefield')
    s.perform('p1', {'type': 'activate_ability', 'card_id': source.id, 'ability': 1})
if family.startswith('sunbird'):
    from app.rules.plan import Plan
    source = next(c for c in s.state.cards.values() if c.zone == 'p1:battlefield' and c.owner == 'p1' and c.name.startswith('Sunbird'))
    assert Plan(s.state, 'p1', repo, None).ch(source).pt == (None if family == 'sunbird_legacy' else (2, 2))
    s.perform('p1', {'type': 'activate_ability', 'card_id': source.id, 'ability': 2})
    if family == 'sunbird_legacy':
        d = s.state.rules.decision
        assert d is not None and d.resume['step'] == 'unknown_crafted_mana'
        s.perform(d.player, {'type': 'choose', 'decision_id': d.id, 'option_ids': ['done']})
    else: assert got('W') == 1
    assert not s.state.rules.pending_crafts
assert (got('C'), got('G')) == {'composition': (0, 1), 'symbols': (1, 2), 'optional': (1, 0), 'pendant': (0, 2), 'sasaya': (0, 1), 'sasaya_reveal': (0, 0), 'class': (0, 0), 'ugin': (2, 0), 'sunbird': (0, 1), 'sunbird_legacy': (0, 0)}[family]
if family == 'class':
    assert s.state.players['p1'].life == 48
    assert s.state.players['p2'].life == s.state.players['p3'].life == 36
if family.startswith('sasaya'):
    assert next(c for c in s.state.cards.values() if c.name.startswith('Sasaya,') and c.owner == 'p1').flipped
    assert not s.state.rules.revealed_activation_costs
    assert not any(c.revealed_to for c in s.state.cards.values() if c.owner == 'p1' and c.zone == 'p1:hand')
    if family == 'sasaya': assert got('R') == 4
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), family],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr

@pytest.mark.parametrize('family', ['moon', 'foundry_order', 'foundry_may'])
def test_final_mana_families_true_cold_native_continuations(cards, tmp_path, family):
    import subprocess
    import sys

    from tests.test_rules_activated_copy_family import cast
    from tests.test_rules_library_look import settle

    if family == 'moon':
        s, source = game(cards, 'Chaos Moon')
        put(s, 'Mountain', 'battlefield')
        put(s, 'Rubble Rouser', 'battlefield')
        answer(s, optional=False)
        to_phase(s, 'upkeep', 5)
        answer(s)
        act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    else:
        s, source = game(cards, "Forger's Foundry")
        put(s, 'Rest in Peace', 'battlefield')
        wait_priority(s, 'p1')
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
        cast(s, 'Opt', {})
        for _ in range(40):
            settle(s)
            d = s.state.rules.decision
            assert d is not None
            if d.resume['step'] == 'zone_replace_order':
                break
            ids = [o.id for o in d.options]
            act(s, d.player, type='choose', decision_id=d.id, option_ids=['keep' if 'keep' in ids else ids[0]])
        assert d.resume['step'] == 'zone_replace_order'
        if family == 'foundry_may':
            act(s, d.player, type='choose', decision_id=d.id,
                option_ids=[next(o.id for o in d.options if "Forger's Foundry" in o.label)])
    path = tmp_path / 'native-cold.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, database, family = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
if family == 'moon':
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_wave30m_durations import to_phase
    mountain = next(c for c in s.state.cards.values() if c.name == 'Mountain' and c.zone == 'p1:battlefield')
    wait_priority(s, 'p1')
    s.perform('p1', {'type': 'activate_ability', 'card_id': mountain.id, 'ability': 0})
    p=s.state.players['p1']
    assert p.mana.get('R',0)+sum(u.sym=='R' for u in p.mana_units)==2
    moon = next(c for c in s.state.cards.values() if c.name == 'Chaos Moon' and c.owner == 'p1')
    assert any(u.src == r.get('source_object') for u in p.mana_units for r in s.state.rules.tap_mana), (p.mana, p.mana_units, s.state.rules.tap_mana)
    to_phase(s, 'main1', 7)
    wait_priority(s,'p1')
    s.perform('p1', {'type': 'activate_ability', 'card_id': mountain.id, 'ability': 0})
    p=s.state.players['p1']
    assert p.mana.get('R',0)+sum(u.sym=='R' for u in p.mana_units)==1
else:
    d=s.state.rules.decision
    if family=='foundry_order':
        assert d.resume['step']=='zone_replace_order'
        s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':[next(o.id for o in d.options if "Forger's Foundry" in o.label)]})
        d=s.state.rules.decision
    assert d.resume['step']=='optional_resolve_exile'
    s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':['yes']})
    spell=next(c for c in s.state.cards.values() if c.name=='Opt' and c.owner=='p1' and c.zone=='p1:exile')
    assert any(s.state.rules.object_id(spell.id) in refs for refs in s.state.rules.exiled_with.values())
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), family],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_sunbird_legacy_activation_receipt_does_not_invent_craft_materials(cards):
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.test_rules_library_look import settle

    s, source = game(cards, 'Sunbird Standard // Sunbird Effigy')
    material = put(s, 'Kitchen Finks', 'graveyard')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 5})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1,
        cost_choices=[{'component': 2, 'cards': [material.id]}])
    saved = s.state.model_dump(mode='json')
    for paid in saved['rules']['payments'].values():
        paid.pop('exiled_was', None)
        paid.pop('exiled_objects', None)
    s = GameSession(GameState.model_validate(saved), cards=cards)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'unknown_craft_cost'
    assert s.state.cards[source.id].zone == 'p1:exile'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['done'])
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert not s.state.rules.pending_crafts
    assert s.state.rules.card_modes[source.id] == 'manual'
    roundtrip(s)


@pytest.mark.parametrize('x', [1, 2])
def test_foundry_uses_actual_cast_x_for_mana_value_gate(cards, x):
    s, source = game(cards, "Forger's Foundry")
    spell = put(s, 'Mind Spring', 'hand')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    act(s, 'p1', type='add_mana', player='p1', mana={'U': x + 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, x_value=x, sources=[])
    answer(s)
    assert s.state.cards[spell.id].zone == ('p1:exile' if x == 1 else 'p1:graveyard')
    roundtrip(s)
