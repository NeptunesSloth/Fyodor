"""CR 702: remaining static, Aura, and resolved keyword grants."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/remaining_keyword_grants_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='sdc', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()



@pytest.mark.parametrize('name', ['Hunter Sliver', 'Lymph Sliver', 'Cavalry Master', "Teferi's Curse", 'Cloak of Invisibility', 'Shimmer', 'Riding the Dilu Horse', 'Barbed Foliage'])
def test_remaining_keyword_grant_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('copies', [1, 2])
@pytest.mark.parametrize('unpreventable', [False, True])
def test_absorb_each_instance_prevents_damage_and_respects_unpreventable_damage(cards, copies, unpreventable):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Lymph Sliver'] * copies, ['Lightning Bolt', 'Skullcrack'])
    lymph = []
    for _ in range(copies):
        remaining = next(c for c in s.state.cards.values() if c.name == 'Lymph Sliver' and c.id not in [c.id for c in lymph])
        act(s, 'p1', type='move', card_ids=[remaining.id], to={'player': 'p1', 'zone': 'battlefield'})
        lymph.append(remaining)
    wait_priority(s, 'p2')
    if unpreventable:
        crack = put(s, 'Skullcrack', 'hand', 'p2')
        mana(s, 'p2', C=1, R=1)
        act(s, 'p2', type='cast_spell', card_id=crack.id, targets=['p3'])
        settle(s)
        wait_priority(s, 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[lymph[0].id])
    settle(s)
    if unpreventable:
        assert s.state.cards[lymph[0].id].zone == 'p1:graveyard'
    else:
        assert s.state.cards[lymph[0].id].zone == 'p1:battlefield'
        assert s.state.cards[lymph[0].id].damage == 3 - copies
    roundtrip(s)


def test_absorb_applies_again_when_the_same_source_deals_damage_at_a_different_time(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Lymph Sliver'], ['Prodigal Pyromancer'])
    lymph = put(s, 'Lymph Sliver', 'battlefield')
    pyro = put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    for _ in range(2):
        wait_priority(s, 'p2')
        act(s, 'p2', type='activate_ability', card_id=pyro.id, ability=0, targets=[lymph.id])
        settle(s)
        assert s.state.cards[lymph.id].damage == 0
        roundtrip(s)
        act(s, 'p2', type='tap', card_ids=[pyro.id], tapped=False)


@pytest.mark.parametrize('master_present', [False, True])
def test_cavalry_master_grants_a_separate_flanking_instance(cards, master_present):
    from tests.test_rules_banding import attacks, block
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave6c_tokens_pumps import pt

    s = table(cards, ['Cavalry Master', 'Benalish Cavalry'], ['Grizzly Bears'])
    if master_present:
        put(s, 'Cavalry Master', 'battlefield')
    cavalry = put(s, 'Benalish Cavalry', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    attacks(s, [(cavalry, 'p2')], [])
    block(s, [(bear, cavalry)])
    settle(s)
    if master_present:
        assert s.state.cards[bear.id].zone == 'p2:graveyard'
    else:
        assert pt(s, bear) == (1, 1) and s.state.cards[bear.id].zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('accept', [False, True])
def test_hunter_sliver_grants_an_optional_provoke_trigger_to_another_sliver(cards, accept):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_banding import declare_only, until_block
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Hunter Sliver', 'Metallic Sliver'], ['Grizzly Bears'])
    put(s, 'Hunter Sliver', 'battlefield')
    sliver = put(s, 'Metallic Sliver', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, 'main1', turn=4)
    act(s, 'p2', type='tap', card_ids=[bear.id], tapped=True)
    declare_only(s, [sliver], [])
    d = s.state.rules.decision
    assert d and bear.id in {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d and {o.id for o in d.options} == {'yes', 'no'}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes' if accept else 'no'])
    settle(s)
    if accept:
        assert not s.state.cards[bear.id].tapped
        until_block(s)
        with pytest.raises(ActionError):
            act(s, 'p2', type='declare_blockers', blocks=[])
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': bear.id, 'attacker_id': sliver.id}])
    else:
        assert s.state.cards[bear.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('name', ["Teferi's Curse", 'Cloak of Invisibility'])
def test_aura_granted_phasing_phases_the_host_and_attached_aura_in_and_out_together(cards, name):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, [name], ['Grizzly Bears'])
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    aura = put(s, name, 'hand')
    mana(s, C=1 if name == "Teferi's Curse" else 0, U=1)
    act(s, 'p1', type='cast_spell', card_id=aura.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[aura.id].attached_to == bear.id
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert s.state.cards[bear.id].zone == 'p2:phased' and s.state.cards[aura.id].zone == 'p1:phased'
    roundtrip(s)
    to_phase(s, 'main1', turn=4)
    assert s.state.cards[aura.id].zone == 'p1:phased'
    to_phase(s, 'main1', turn=5)
    assert s.state.cards[bear.id].zone == 'p2:battlefield' and s.state.cards[aura.id].zone == 'p1:battlefield'
    assert s.state.cards[aura.id].attached_to == bear.id
    roundtrip(s)


@pytest.mark.parametrize('land_type', ['Forest', 'Desert', "Urza's"])
def test_shimmer_offers_all_land_types_and_phases_only_matching_lands(cards, land_type):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import keyword, mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Shimmer'], ['Desert', 'Forest', "Urza's Mine"])
    desert = put(s, 'Desert', 'battlefield', 'p2')
    forest = put(s, 'Forest', 'battlefield', 'p2')
    mine = put(s, "Urza's Mine", 'battlefield', 'p2')
    shimmer = put(s, 'Shimmer', 'hand')
    mana(s, C=2, U=2)
    act(s, 'p1', type='cast_spell', card_id=shimmer.id)
    settle(s)
    d = s.state.rules.decision
    assert d and len(d.options) == 17 and {'Desert', 'Forest', "Urza's"} <= {o.id for o in d.options}
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[land_type])
    settle(s)
    assert s.state.cards[shimmer.id].choices['Chosen land type'] == land_type
    assert keyword(s, desert, 'phasing') == (land_type == 'Desert')
    assert keyword(s, forest, 'phasing') == (land_type == 'Forest')
    assert keyword(s, mine, 'phasing') == (land_type == "Urza's")
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert s.state.cards[desert.id].zone == ('p2:phased' if land_type == 'Desert' else 'p2:battlefield')
    assert s.state.cards[forest.id].zone == ('p2:phased' if land_type == 'Forest' else 'p2:battlefield')
    assert s.state.cards[mine.id].zone == ('p2:phased' if land_type == "Urza's" else 'p2:battlefield')
    roundtrip(s)


def test_riding_the_dilu_horse_bonus_and_horsemanship_persist_across_turns_and_apply_in_combat(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_banding import attacks
    from tests.test_rules_bandmate_references import keyword, mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave6c_tokens_pumps import pt
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Riding the Dilu Horse', 'Grizzly Bears'], ['Grizzly Bears', 'Wu Elite Cavalry'])
    bear = put(s, 'Grizzly Bears', 'battlefield')
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    horse = put(s, 'Wu Elite Cavalry', 'battlefield', 'p2')
    spell = put(s, 'Riding the Dilu Horse', 'hand')
    mana(s, C=2, G=1)
    act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[bear.id])
    settle(s)
    assert pt(s, bear) == (4, 4) and keyword(s, bear, 'horsemanship')
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert pt(s, bear) == (4, 4) and keyword(s, bear, 'horsemanship')
    attacks(s, [(bear, 'p2')], [])
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': bear.id}])
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': horse.id, 'attacker_id': bear.id}])
    roundtrip(s)


def test_absorb_and_damage_doubling_offer_the_affected_player_a_replacement_order(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ['Lymph Sliver', 'Furnace of Rath'], ['Lightning Bolt'])
    lymph = put(s, 'Lymph Sliver', 'battlefield')
    put(s, 'Furnace of Rath', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=lymph.id, kind='+1/+1', value=5)
    wait_priority(s, 'p2')
    bolt = put(s, 'Lightning Bolt', 'hand', 'p2')
    mana(s, 'p2', R=1)
    act(s, 'p2', type='cast_spell', card_id=bolt.id, targets=[lymph.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == 'p1' and 'both apply' in d.prompt
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    assert s.state.cards[lymph.id].damage in (4, 5)
    roundtrip(s)


def test_a_lost_absorb_ability_no_longer_prevents_damage(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana, wait_priority
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Lymph Sliver'], ['Prodigal Pyromancer', 'Ovinize'])
    lymph = put(s, 'Lymph Sliver', 'battlefield')
    pyro = put(s, 'Prodigal Pyromancer', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    wait_priority(s, 'p2')
    spell = put(s, 'Ovinize', 'hand', 'p2')
    mana(s, 'p2', C=1, U=1)
    act(s, 'p2', type='cast_spell', card_id=spell.id, targets=[lymph.id])
    settle(s)
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=pyro.id, ability=0, targets=[lymph.id])
    settle(s)
    assert s.state.cards[lymph.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_absorb_granted_to_an_opponents_sliver_prevents_combat_damage_too(cards):
    from tests.game_helpers import act
    from tests.test_rules_banding import attacks, block
    from tests.test_rules_designations import put, roundtrip
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Metallic Sliver'], ['Lymph Sliver', 'Grizzly Bears'])
    sliver = put(s, 'Metallic Sliver', 'battlefield')
    put(s, 'Lymph Sliver', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    act(s, 'p1', type='set_counter', card_id=sliver.id, kind='+1/+1', value=1)
    attacks(s, [(sliver, 'p2')], [])
    block(s, [(bear, sliver)])
    to_phase(s, 'main2', turn=4)
    assert s.state.cards[sliver.id].zone == 'p1:battlefield' and s.state.cards[sliver.id].damage == 1
    assert s.state.cards[bear.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_cloaks_block_restriction_is_kept_alongside_its_phasing_grant(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act
    from tests.test_rules_banding import attacks
    from tests.test_rules_bandmate_references import mana
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ['Cloak of Invisibility', 'Grizzly Bears'], ['Grizzly Bears', 'Wall of Omens'])
    bearer = put(s, 'Grizzly Bears', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    wall = put(s, 'Wall of Omens', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    cloak = put(s, 'Cloak of Invisibility', 'hand')
    mana(s, U=1)
    act(s, 'p1', type='cast_spell', card_id=cloak.id, targets=[bearer.id])
    settle(s)
    attacks(s, [(bearer, 'p2')], [])
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': bear.id, 'attacker_id': bearer.id}])
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': wall.id, 'attacker_id': bearer.id}])
    roundtrip(s)


@pytest.mark.parametrize('late_grant', [False, True])
def test_barbed_foliage_removes_all_flanking_and_only_a_later_instance_can_trigger(cards, late_grant):
    from tests.game_helpers import act
    from tests.test_rules_banding import block, declare_only, until_block
    from tests.test_rules_designations import put, roundtrip, settle
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave6c_tokens_pumps import pt

    s = table(cards, ['Benalish Cavalry', 'Cavalry Master', 'Agility'], ['Barbed Foliage', 'Grizzly Bears'])
    cavalry = put(s, 'Benalish Cavalry', 'battlefield')
    put(s, 'Cavalry Master', 'battlefield')
    put(s, 'Barbed Foliage', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    declare_only(s, [cavalry], [])
    settle(s)
    assert s.state.cards[cavalry.id].damage == 1
    if late_grant:
        aura = put(s, 'Agility', 'battlefield')
        act(s, 'p1', type='attach', card_ids=[aura.id], to=cavalry.id)
    until_block(s)
    block(s, [(bear, cavalry)])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p2:battlefield'
    assert pt(s, bear) == ((1, 1) if late_grant else (2, 2))
    roundtrip(s)
