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

DATA = json.loads((Path(__file__).parent / 'fixtures/reveal_consequences_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='rvc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
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


@pytest.mark.parametrize('accept', [False, True])
def test_matter_native_death_optional_permanent_or_hand(cards, accept):
    s = table(cards, ['Matter Reshaper', 'Sol Ring'], ['Murder'])
    source = put(s, 'Matter Reshaper', 'battlefield')
    ring = put(s, 'Sol Ring', 'library')
    cast(s, 'Murder', [source.id], 'p2')
    d = s.state.rules.decision
    assert d is not None and ring.id in {o.id for o in d.options}
    pick(s, [ring.id] if accept else [])
    settle(s)
    assert s.state.cards[ring.id].zone == ('p1:battlefield' if accept else 'p1:hand')
    roundtrip(s)


def attack(s, name):
    source = put(s, name, 'battlefield')
    put(s, 'Fervor', 'battlefield')
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    return source


def test_bronco_actual_unsaddled_attack_reveals_moves_then_loses_value(cards):
    s = table(cards, ['Caustic Bronco', 'Fervor', 'Counterspell'])
    found = put(s, 'Counterspell', 'library')
    attack(s, 'Caustic Bronco')
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert s.state.players['p1'].life == 38
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_raider_raid_trigger_after_actual_attack_reads_top_card(cards):
    s = table(cards, ['Ruin Raider', 'Fervor', 'Counterspell'])
    found = put(s, 'Counterspell', 'library')
    attack(s, 'Ruin Raider')
    to_phase(s, 'end', turn=1)
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert s.state.players['p1'].life == 38
    roundtrip(s)


def test_matter_failed_creature_entry_still_puts_original_card_into_hand(cards):
    s = table(cards, ['Matter Reshaper', 'Grizzly Bears', "Grafdigger's Cage"], ['Murder'])
    put(s, "Grafdigger's Cage", 'battlefield')
    source = put(s, 'Matter Reshaper', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'library')
    cast(s, 'Murder', [source.id], 'p2')
    pick(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:hand'
    roundtrip(s)


def test_sarkhan_native_reveal_deals_damage_to_own_loyalty(cards):
    s = table(cards, ['Sarkhan the Mad', 'Counterspell'])
    source = cast(s, 'Sarkhan the Mad')
    found = put(s, 'Counterspell', 'library')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert s.state.cards[source.id].counters['loyalty'] == 5
    assert s.state.players['p1'].life == 40
    roundtrip(s)


def test_sarkhan_controller_sacrifice_dragon_then_native_all_dragon_damage(cards):
    s = table(cards, ['Sarkhan the Mad', 'Grizzly Bears'], ['Grizzly Bears'])
    source = cast(s, 'Sarkhan the Mad')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    dragons = [c for c in s.state.cards.values() if c.zone == 'p2:battlefield' and c.is_token]
    assert len(dragons) == 1 and dragons[0].name == 'Dragon'
    roundtrip(s)


def test_sarkhan_native_dragon_damage_reads_its_current_power(cards):
    s = table(cards, ['Sarkhan the Mad', 'Grizzly Bears'])
    source = cast(s, 'Sarkhan the Mad')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[bear.id])
    settle(s)
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 35
    roundtrip(s)


@pytest.mark.parametrize('mask,life', [(0, 40), (1, 43), (2, 43), (3, 46)])
def test_arena_native_two_independent_kickers(cards, mask, life):
    s = table(cards, ['Stronghold Arena'])
    source = put(s, 'Stronghold Arena', 'hand')
    mana(s)
    act(s, 'p1', type='cast_spell', card_id=source.id, kicker=mask, sources=[])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.players['p1'].life == life
    roundtrip(s)


def test_arena_actual_combat_optional_reveal_and_life_loss(cards):
    s = table(cards, ['Stronghold Arena', 'Grizzly Bears', 'Fervor', 'Counterspell'])
    put(s, 'Stronghold Arena', 'battlefield')
    found = put(s, 'Counterspell', 'library')
    attack(s, 'Grizzly Bears')
    to_phase(s, 'combat_damage', turn=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    pick(s, ['yes'])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert s.state.players['p1'].life == 38
    roundtrip(s)


def test_heirloom_equipped_actual_death_reveals_matching_creature(cards):
    s = table(cards, ['Heirloom Blade', 'Grizzly Bears', 'Runeclaw Bear', 'Llanowar Elves'], ['Murder'])
    blade = put(s, 'Heirloom Blade', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    found = put(s, 'Runeclaw Bear', 'library')
    elf = put(s, 'Llanowar Elves', 'library')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=blade.id, ability=2, targets=[bear.id])
    settle(s)
    assert s.state.cards[blade.id].attached_to == bear.id
    cast(s, 'Murder', [bear.id], 'p2')
    pick(s, ['yes'])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert s.state.cards[elf.id].zone == 'p1:library'
    assert not s.state.cards[elf.id].revealed_to
    roundtrip(s)


def test_amplifire_actual_upkeep_sets_twice_current_revealed_stats(cards):
    from app.rules.plan import Plan

    s = table(cards, ['Amplifire', 'Grizzly Bears'])
    source = put(s, 'Amplifire', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    found = put(s, 'Grizzly Bears', 'library')
    settle(s)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).pt == (4, 4)
    assert s.state.cards[found.id].zone == 'p1:library'
    to_phase(s, 'upkeep', turn=7)
    assert Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id]).pt == (1, 1)
    roundtrip(s)


def test_unbinding_actual_enchanted_upkeep_enters_under_curse_controller(cards):
    s = table(cards, ['Curse of Unbinding'], ['Grizzly Bears', 'Sol Ring'])
    source = cast(s, 'Curse of Unbinding', ['p2'])
    assert s.state.cards[source.id].attached_player == 'p2'
    to_phase(s, 'upkeep', turn=2)
    bear = put(s, 'Grizzly Bears', 'library', 'p2')
    ring = put(s, 'Sol Ring', 'library', 'p2')
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].owner == 'p2'
    assert s.state.cards[ring.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_fury_actual_combat_selects_only_damage_creature_and_reveals_match(cards):
    s = table(cards, ["Descendants' Fury", 'Grizzly Bears', 'Runeclaw Bear', 'Llanowar Elves', 'Fervor'])
    put(s, "Descendants' Fury", 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    found = put(s, 'Runeclaw Bear', 'library')
    bear = attack(s, 'Grizzly Bears')
    to_phase(s, 'combat_damage', turn=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and bear.id in {o.id for o in d.options}
    assert elf.id not in {o.id for o in d.options}
    pick(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'
    assert s.state.cards[found.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_guild_feud_opponent_chooses_first_then_two_actual_arrivals_fight(cards):
    s = table(cards, ['Guild Feud', 'Runeclaw Bear'], ['Grizzly Bears'])
    put(s, 'Guild Feud', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    ours = put(s, 'Runeclaw Bear', 'library')
    theirs = put(s, 'Grizzly Bears', 'library', 'p2')
    d = s.state.rules.decision
    assert d is not None and 'p2' in {o.id for o in d.options}
    pick(s, ['p2'])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == 'p2'
    pick(s, [theirs.id])
    settle(s)
    assert s.state.cards[theirs.id].zone == 'p2:battlefield'
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1'
    pick(s, [ours.id])
    settle(s)
    assert s.state.cards[ours.id].zone == 'p1:graveyard'
    assert s.state.cards[theirs.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_kaboom_apnap_targets_use_successive_revealed_cards(cards):
    s = table(cards, ['Kaboom!', 'Sol Ring', 'Counterspell'])
    put(s, 'Counterspell', 'library')
    put(s, 'Sol Ring', 'library')
    cast(s, 'Kaboom!', ['p3', 'p2'])
    assert s.state.players['p2'].life == 39
    assert s.state.players['p3'].life == 38
    assert all(not s.state.cards[c].revealed_to for c in s.state.zones['p1:library'])
    roundtrip(s)


def test_kaboom_cold_order_within_player_planeswalker_group(cards, tmp_path):
    from tests.test_rules_reveal_outcomes import cold_answer

    s = table(cards, ['Kaboom!', 'Sarkhan the Mad', 'Sol Ring', 'Counterspell'])
    walker = cast(s, 'Sarkhan the Mad')
    put(s, 'Counterspell', 'library')
    put(s, 'Sol Ring', 'library')
    source = put(s, 'Kaboom!', 'hand')
    mana(s)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p1', walker.id], target_counts=[2], sources=[])
    for _ in range(12):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'reveal_target_order'
    s = cold_answer(s, cards, tmp_path, [walker.id, 'p1'])
    assert s.state.cards[walker.id].counters['loyalty'] == 6
    assert s.state.players['p1'].life == 38
    roundtrip(s)


def test_kaboom_zero_targets_resolves_without_revealing(cards):
    s = table(cards, ['Kaboom!', 'Counterspell'])
    found = put(s, 'Counterspell', 'library')
    cast(s, 'Kaboom!')
    assert s.state.zones['p1:library'][0] == found.id
    assert s.state.rules.decision is None
    assert s.state.players['p2'].life == 40
    assert not s.state.cards[found.id].revealed_to
    roundtrip(s)


@pytest.mark.parametrize('source_dies', [False, True])
def test_bronco_native_saddle_uses_original_designation_even_after_death(cards, source_dies):
    from app.rules.plan import Plan
    from tests.test_rules_bandmate_references import wait_priority

    s = table(cards, ['Caustic Bronco', 'Grizzly Bears', 'Llanowar Elves', 'Fervor', 'Counterspell'], ['Murder'])
    source = put(s, 'Caustic Bronco', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    found = put(s, 'Counterspell', 'library')
    index = next(a.index for a in Plan(s.state, 'p1', cards, None).ch(source).abilities if a.text.lower().startswith('saddle'))
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[bear.id, elf.id])
    settle(s)
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    if source_dies:
        murder = put(s, 'Murder', 'hand', 'p2')
        mana(s, 'p2')
        wait_priority(s, 'p2')
        act(s, 'p2', type='cast_spell', card_id=murder.id, targets=[source.id], sources=[])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    assert s.state.players['p1'].life == 40
    assert s.state.players['p2'].life == 38
    assert s.state.players['p3'].life == 38
    roundtrip(s)


def test_cold_matter_optional_permanent_entry_keeps_snapshot(cards, tmp_path):
    from tests.test_rules_reveal_outcomes import cold_answer

    s = table(cards, ['Matter Reshaper', 'Sol Ring'], ['Murder'])
    source = put(s, 'Matter Reshaper', 'battlefield')
    found = put(s, 'Sol Ring', 'library')
    cast(s, 'Murder', [source.id], 'p2')
    s = cold_answer(s, cards, tmp_path, [found.id])
    assert s.state.cards[found.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_guild_feud_declined_opponent_entry_does_not_fight_own_arrival(cards):
    s = table(cards, ['Guild Feud', 'Runeclaw Bear'], ['Grizzly Bears'])
    put(s, 'Guild Feud', 'battlefield')
    to_phase(s, 'upkeep', turn=4)
    ours = put(s, 'Runeclaw Bear', 'library')
    theirs = put(s, 'Grizzly Bears', 'library', 'p2')
    pick(s, ['p2'])
    settle(s)
    pick(s, [])
    settle(s)
    pick(s, [ours.id])
    settle(s)
    assert s.state.cards[theirs.id].zone == 'p2:graveyard'
    assert s.state.cards[ours.id].zone == 'p1:battlefield'
    assert s.state.cards[ours.id].damage == 0
    roundtrip(s)


def test_heirloom_time_lord_is_one_shared_creature_type(cards):
    s = table(cards, ['Heirloom Blade', 'The Tenth Doctor', 'The Master, Multiplied'], ['Murder'])
    blade = put(s, 'Heirloom Blade', 'battlefield')
    doctor = put(s, 'The Tenth Doctor', 'battlefield')
    found = put(s, 'The Master, Multiplied', 'library')
    mana(s)
    act(s, 'p1', type='activate_ability', card_id=blade.id, ability=2, targets=[doctor.id])
    settle(s)
    cast(s, 'Murder', [doctor.id], 'p2')
    pick(s, ['yes'])
    settle(s)
    assert s.state.cards[found.id].zone == 'p1:hand'
    roundtrip(s)
