"""CR 702.22c-k: attacking bands, shared blocking, and damage assignment."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/banding_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Benalish Hero', 'Mesa Pegasus', 'Kjeldoran Warrior', 'Pikemen', 'Kjeldoran Skyknight', 'Shield Bearer', 'Kjeldoran Knight', 'Teremko Griffin', 'Wall of Shields', 'Benalish Infantry', 'Timber Wolves', 'War Elephant', 'Noble Elephant', 'Kjeldoran Escort', 'Kjeldoran Skycaptain', 'Knights of Thorn', 'Icatian Phalanx', 'Kjeldoran Phalanx', 'Nalathni Dragon', 'Volunteer Reserves'])
def test_banding_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def attack_step(s):
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.turn.number >= 4 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == 'declare_attackers' and s.state.turn.active_player == 'p1')


def attacks(s, pairs, bands=()):
    from tests.test_rules_conditionals import until

    attack_step(s)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': p} for c, p in pairs],
        bands=[[c.id for c in group] for group in bands])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_blockers')
    roundtrip(s)


def block(s, pairs):
    d = s.state.rules.decision
    assert d is not None and d.kind == 'declare_blockers'
    act(s, d.player, type='declare_blockers', blocks=[{'blocker_id': b.id, 'attacker_id': a.id} for b, a in pairs])
    roundtrip(s)


def damage_choice(s):
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'divide')
    roundtrip(s)
    return s.state.rules.decision


def divide(s, allocation):
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, amounts=[allocation.get(o.id, 0) for o in d.options])
    roundtrip(s)


@pytest.mark.parametrize('blocked_member', ['hero', 'bear'])
def test_one_blocker_blocks_every_member_and_the_attacker_divides_its_damage(cards, blocked_member):
    s = table(cards, ['Benalish Hero', 'Grizzly Bears'], ['Gigantosaurus'])
    hero = put(s, 'Benalish Hero', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    attacks(s, [(hero, 'p2'), (bear, 'p2')], [[hero, bear]])
    block(s, [(giant, hero if blocked_member == 'hero' else bear)])
    assert s.state.cards[giant.id].blocks(hero.id) and s.state.cards[giant.id].blocks(bear.id)
    assert {hero.id, bear.id} <= set(s.state.rules.blocked)
    d = damage_choice(s)
    assert d.player == 'p1' and {o.id for o in d.options} == {hero.id, bear.id}
    divide(s, {hero.id: 10})
    assert hero.id in s.state.zones['p1:graveyard'] and bear.id in s.state.zones['p1:battlefield']
    assert s.state.players['p2'].life == 40
    roundtrip(s)


def test_a_banding_blocker_lets_the_defender_divide_the_attackers_damage(cards):
    s = table(cards, ['Gigantosaurus'], ['Benalish Hero', 'Grizzly Bears'])
    giant = put(s, 'Gigantosaurus', 'battlefield')
    hero = put(s, 'Benalish Hero', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attacks(s, [(giant, 'p2')])
    block(s, [(hero, giant), (bear, giant)])
    d = damage_choice(s)
    assert d.player == 'p2'
    divide(s, {hero.id: 10})
    assert hero.id in s.state.zones['p2:graveyard'] and bear.id in s.state.zones['p2:battlefield']
    roundtrip(s)


def test_banding_does_not_share_flying_and_a_ground_member_exposes_a_flying_one(cards):
    s = table(cards, ['Mesa Pegasus', 'Grizzly Bears'], ['Gigantosaurus'])
    pegasus = put(s, 'Mesa Pegasus', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    attacks(s, [(pegasus, 'p2'), (bear, 'p2')], [[pegasus, bear]])
    d = s.state.rules.decision
    before = s.state.model_dump(mode='json')
    from app.game.errors import ActionError

    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': giant.id, 'attacker_id': pegasus.id}])
    assert s.state.model_dump(mode='json') == before and s.state.rules.decision.id == d.id
    block(s, [(giant, bear)])
    assert s.state.cards[giant.id].blocks(pegasus.id)
    assert damage_choice(s).player == 'p1'
    divide(s, {bear.id: 10})
    assert pegasus.id in s.state.zones['p1:battlefield']
    roundtrip(s)


@pytest.mark.parametrize('problem', ['two_without', 'no_bander', 'duplicate', 'multiple_bands', 'different_defenders', 'not_attacking', 'empty'])
def test_illegal_bands_are_rejected_without_changing_the_state(cards, problem):
    from app.game.errors import ActionError

    s = table(cards, ['Benalish Hero', 'Grizzly Bears', 'Runeclaw Bear'])
    hero = put(s, 'Benalish Hero', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Runeclaw Bear', 'battlefield')
    attack_step(s)
    pairs = [(hero, 'p2'), (bear, 'p2'), (other, 'p2')]
    groups = {'two_without': [[hero, bear, other]], 'no_bander': [[bear]], 'duplicate': [[hero, hero]],
              'multiple_bands': [[hero, bear], [hero, other]], 'different_defenders': [[hero, bear]],
              'not_attacking': [[hero, other]], 'empty': [[]]}[problem]
    if problem == 'different_defenders':
        pairs[1] = (bear, 'p3')
    if problem == 'not_attacking':
        pairs = pairs[:2]
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': p} for c, p in pairs],
            bands=[[c.id for c in group] for group in groups])
    assert s.state.model_dump(mode='json') == before
    roundtrip(s)


def test_multiple_bands_can_attack_different_defenders(cards):
    s = table(cards, ['Benalish Hero', 'Mesa Pegasus', 'Grizzly Bears', 'Runeclaw Bear'], ['Grizzly Bears'], ['Grizzly Bears'])
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield', 'p3')
    hero = put(s, 'Benalish Hero', 'battlefield')
    pegasus = put(s, 'Mesa Pegasus', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Runeclaw Bear', 'battlefield')
    attacks(s, [(hero, 'p2'), (bear, 'p2'), (pegasus, 'p3'), (other, 'p3')], [[hero, bear], [pegasus, other]])
    assert len(s.state.rules.attacking_bands) == 2
    roundtrip(s)


def declare_only(s, creatures, groups):
    attack_step(s)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in creatures],
        bands=[[c.id for c in group] for group in groups])
    roundtrip(s)


def until_block(s):
    from tests.test_rules_conditionals import until

    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_blockers')


def test_losing_banding_does_not_break_the_band_but_changes_damage_assignment_control(cards):
    s = table(cards, ['Benalish Hero', 'Grizzly Bears', 'Ovinize'], ['Gigantosaurus'])
    hero = put(s, 'Benalish Hero', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    declare_only(s, [hero, bear], [[hero, bear]])
    spell = put(s, 'Ovinize', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[hero.id])
    settle(s)
    until_block(s)
    block(s, [(giant, hero)])
    assert s.state.cards[giant.id].blocks(bear.id)
    assert damage_choice(s).player == 'p2'
    divide(s, {bear.id: 10})
    assert bear.id in s.state.zones['p1:graveyard'] and hero.id in s.state.zones['p1:battlefield']
    roundtrip(s)


def test_leaving_combat_removes_a_member_and_returning_is_a_new_unbanded_object(cards):
    from app.rules import banding

    s = table(cards, ['Benalish Hero', 'Mesa Pegasus', 'Grizzly Bears'], ['Gigantosaurus'])
    hero = put(s, 'Benalish Hero', 'battlefield')
    pegasus = put(s, 'Mesa Pegasus', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    declare_only(s, [hero, pegasus, bear], [[hero, pegasus, bear]])
    act(s, 'p1', type='move', card_ids=[hero.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, 'p1', type='move', card_ids=[hero.id], to={'player': 'p1', 'zone': 'battlefield'})
    assert banding.live_bands(s.state) == [[pegasus.id, bear.id]]
    assert s.state.cards[hero.id].attacking is None
    until_block(s)
    block(s, [(giant, bear)])
    assert s.state.cards[giant.id].blocks(pegasus.id) and not s.state.cards[giant.id].blocks(hero.id)
    assert damage_choice(s).player == 'p1'
    divide(s, {bear.id: 10})
    assert hero.id in s.state.zones['p1:battlefield'] and pegasus.id in s.state.zones['p1:battlefield']
    roundtrip(s)


def test_an_effect_blocking_one_band_member_blocks_the_entire_band(cards):
    from tests.test_rules_conditionals import until

    s = table(cards, ['Benalish Hero', 'Grizzly Bears', 'Curtain of Light'], ['Gigantosaurus'])
    hero = put(s, 'Benalish Hero', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Gigantosaurus', 'battlefield', 'p2')
    attacks(s, [(hero, 'p2'), (bear, 'p2')], [[hero, bear]])
    block(s, [])
    spell = put(s, 'Curtain of Light', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[hero.id])
    settle(s)
    assert {hero.id, bear.id} <= set(s.state.rules.blocked)
    roundtrip(s)
    until(s, lambda s: s.state.turn.phase == 'main2')
    assert s.state.players['p2'].life == 40 and not s.state.rules.attacking_bands
    assert s.view('p2')['rules']['attacking_bands'] == []
    roundtrip(s)


def test_blocking_a_band_member_can_block_a_member_with_menace_with_one_creature(cards):
    s = table(cards, ['Benalish Hero', 'Boggart Brute'], ['Gigantosaurus'])
    hero = put(s, 'Benalish Hero', 'battlefield')
    brute = put(s, 'Boggart Brute', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    attacks(s, [(hero, 'p2'), (brute, 'p2')], [[hero, brute]])
    block(s, [(giant, hero)])
    assert s.state.cards[giant.id].blocks(brute.id)
    assert damage_choice(s).player == 'p1'
    divide(s, {hero.id: 10})
    assert brute.id in s.state.zones['p1:battlefield']
    roundtrip(s)


def test_first_strike_is_not_shared_by_the_band(cards):
    s = table(cards, ['Pikemen', 'Grizzly Bears'], ['Gigantosaurus'])
    pike = put(s, 'Pikemen', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    attacks(s, [(pike, 'p2'), (bear, 'p2')], [[pike, bear]])
    block(s, [(giant, bear)])
    assert damage_choice(s).player == 'p1'
    assert s.state.cards[giant.id].damage == 1  # Pikemen dealt first-strike damage; the Bear hasn't.
    divide(s, {pike.id: 10})
    assert s.state.cards[giant.id].damage == 3
    assert pike.id in s.state.zones['p1:graveyard'] and bear.id in s.state.zones['p1:battlefield']
    roundtrip(s)


def test_defending_banding_controls_trample_assignment_and_still_requires_lethal_before_face_damage(cards):
    from app.game.errors import ActionError

    s = table(cards, ['War Elephant', 'Giant Growth'], ['Benalish Hero', 'Grizzly Bears'])
    elephant = put(s, 'War Elephant', 'battlefield')
    hero = put(s, 'Benalish Hero', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    declare_only(s, [elephant], [])
    growth = put(s, 'Giant Growth', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'G': 1})
    act(s, 'p1', type='cast_spell', card_id=growth.id, targets=[elephant.id])
    settle(s)
    until_block(s)
    block(s, [(hero, elephant), (bear, elephant)])
    d = damage_choice(s)
    assert d.player == 'p2' and 'p2' in {o.id for o in d.options}
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        divide(s, {'p2': 5})
    assert s.state.model_dump(mode='json') == before
    divide(s, {hero.id: 5})
    assert s.state.players['p2'].life == 40
    assert hero.id in s.state.zones['p2:graveyard'] and bear.id in s.state.zones['p2:battlefield']
    roundtrip(s)


def test_attacking_in_a_band_pays_each_creatures_attack_tax(cards):
    from tests.test_rules_conditionals import until

    s = table(cards, ['Benalish Hero', 'Grizzly Bears'], ['Ghostly Prison', 'Gigantosaurus'])
    hero = put(s, 'Benalish Hero', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Ghostly Prison', 'battlefield', 'p2')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    attack_step(s)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in [hero, bear]],
        bands=[[hero.id, bear.id]])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_blockers')
    assert sum(s.state.players['p1'].mana.values()) == 0
    assert len(s.state.rules.attacking_bands) == 1
    block(s, [(giant, bear)])
    assert damage_choice(s).player == 'p1'
    divide(s, {hero.id: 10})
    roundtrip(s)


@pytest.mark.parametrize('name', ['Baton of Morale', 'Helm of Chatzuk', 'Soraya the Falconer', 'Fortified Area',
                                 'Cooperation', 'Icatian Infantry', 'Errand of Duty', 'Dire Wolves', 'Beast Walkers', 'Formation'])
def test_banding_grant_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def has_banding(s, c):
    from app.rules.plan import Plan

    return 'banding' in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[c.id]).keywords


@pytest.mark.parametrize('name,target_name,ability,mana', [
    ('Baton of Morale', 'Grizzly Bears', 0, {'C': 2}),
    ('Helm of Chatzuk', 'Grizzly Bears', 0, {'C': 1}),
    ('Soraya the Falconer', 'Birds of Paradise', 1, {'C': 1, 'W': 1}),
    ('Icatian Infantry', 'Icatian Infantry', 1, {'C': 1}),
    ('Beast Walkers', 'Beast Walkers', 0, {'G': 1}),
])
def test_activated_banding_grants_change_the_derived_ability(cards, name, target_name, ability, mana):
    s = table(cards, list(dict.fromkeys([name, target_name])))
    source = put(s, name, 'battlefield')
    target = source if name == target_name else put(s, target_name, 'battlefield')
    assert not has_banding(s, target)
    act(s, 'p1', type='add_mana', player='p1', mana=mana)
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability,
        targets=[] if source.id == target.id else [target.id])
    settle(s)
    assert has_banding(s, target)
    if name == 'Helm of Chatzuk':
        assert s.state.cards[source.id].tapped
    roundtrip(s)


def test_static_banding_grants_follow_the_source_and_controller_filter(cards):
    s = table(cards, ['Fortified Area', 'Wall of Omens'], ['Wall of Omens'])
    source = put(s, 'Fortified Area', 'battlefield')
    wall = put(s, 'Wall of Omens', 'battlefield')
    other = put(s, 'Wall of Omens', 'battlefield', 'p2')
    assert has_banding(s, wall) and not has_banding(s, other)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert not has_banding(s, wall)
    roundtrip(s)


def test_cooperation_grants_banding_only_while_attached(cards):
    s = table(cards, ['Cooperation', 'Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    aura = put(s, 'Cooperation', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[bear.id])
    settle(s)
    assert has_banding(s, bear)
    act(s, 'p1', type='move', card_ids=[aura.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert not has_banding(s, bear)
    roundtrip(s)


def test_dire_wolves_banding_tracks_whether_its_controller_has_a_plains(cards):
    s = table(cards, ['Dire Wolves', 'Plains'])
    wolf = put(s, 'Dire Wolves', 'battlefield')
    assert not has_banding(s, wolf)
    plains = put(s, 'Plains', 'battlefield')
    assert has_banding(s, wolf)
    act(s, 'p1', type='move', card_ids=[plains.id], to={'player': 'p1', 'zone': 'graveyard'})
    assert not has_banding(s, wolf)
    roundtrip(s)


def test_errand_of_duty_creates_a_knight_with_banding(cards):
    from tests.test_rules_wave5j_token_copies import tokens

    s = table(cards, ['Errand of Duty'])
    spell = put(s, 'Errand of Duty', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[])
    settle(s)
    made = [c for c in tokens(s) if c.name == 'Knight']
    assert len(made) == 1 and has_banding(s, made[0])
    roundtrip(s)


def test_formation_grants_banding_this_turn_and_draws_at_the_next_upkeep(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Formation', 'Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, 'Formation', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'W': 1})
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    assert has_banding(s, bear)
    before = len(s.state.zones['p1:hand'])
    roundtrip(s)
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert len(s.state.zones['p1:hand']) == before + 1
    assert not has_banding(s, bear)
    roundtrip(s)


def test_multiple_blockers_of_a_band_each_block_every_member_and_keep_separate_damage_choices(cards):
    s = table(cards, ['Benalish Hero', 'Grizzly Bears'], ['Gigantosaurus', 'Grizzly Bears'])
    hero = put(s, 'Benalish Hero', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    other = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attacks(s, [(hero, 'p2'), (bear, 'p2')], [[hero, bear]])
    block(s, [(giant, hero), (other, bear)])
    for _ in range(4):
        d = damage_choice(s)
        assert d.player == 'p1'
        source = d.resume['creature']
        target = other.id if source in [hero.id, bear.id] else hero.id
        divide(s, {target: d.resume['total']})
    assert hero.id in s.state.zones['p1:graveyard'] and other.id in s.state.zones['p2:graveyard']
    assert bear.id in s.state.zones['p1:battlefield'] and giant.id in s.state.zones['p2:battlefield']
    roundtrip(s)


def test_one_declared_block_slot_can_cover_a_band_but_cannot_cover_a_second_band(cards):
    from app.game.errors import ActionError

    s = table(cards, ['Benalish Hero', 'Mesa Pegasus', 'Grizzly Bears', 'Runeclaw Bear'], ['Gigantosaurus'])
    hero = put(s, 'Benalish Hero', 'battlefield')
    pegasus = put(s, 'Mesa Pegasus', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    other = put(s, 'Runeclaw Bear', 'battlefield')
    giant = put(s, 'Gigantosaurus', 'battlefield', 'p2')
    attacks(s, [(c, 'p2') for c in [hero, pegasus, bear, other]], [[hero, bear], [pegasus, other]])
    before = s.state.model_dump(mode='json')
    with pytest.raises(ActionError):
        block(s, [(giant, hero), (giant, other)])
    assert s.state.model_dump(mode='json') == before
    block(s, [(giant, hero)])
    assert s.state.cards[giant.id].blocks(bear.id)
    assert not s.state.cards[giant.id].blocks(other.id) and not s.state.cards[giant.id].blocks(pegasus.id)
    roundtrip(s)


def test_banding_granted_after_blocks_changes_who_assigns_damage(cards):
    s = table(cards, ['Gigantosaurus'], ['Helm of Chatzuk', 'Grizzly Bears', 'Runeclaw Bear'])
    giant = put(s, 'Gigantosaurus', 'battlefield')
    helm = put(s, 'Helm of Chatzuk', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    other = put(s, 'Runeclaw Bear', 'battlefield', 'p2')
    attacks(s, [(giant, 'p2')])
    block(s, [(bear, giant), (other, giant)])
    act(s, 'p1', type='pass_priority')
    act(s, 'p2', type='add_mana', player='p2', mana={'C': 1})
    act(s, 'p2', type='activate_ability', card_id=helm.id, ability=0, targets=[bear.id])
    settle(s)
    assert damage_choice(s).player == 'p2'
    divide(s, {bear.id: 10})
    assert bear.id in s.state.zones['p2:graveyard'] and other.id in s.state.zones['p2:battlefield']
    roundtrip(s)
