"""Linked exile abilities grant native exact-object play permissions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_linked_aggregates import cast, ch
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = [
    c["name"]
    for c in json.loads((Path(__file__).parent / "fixtures/conditional_copy_sources_cards.json").read_text())[:16]
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/conditional_copy_sources_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="lor", number=str(i), **{k: v for k, v in c.items() if k not in ("name", "set_code")}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name):
    support = [
        "Grizzly Bears",
        "Counterspell",
        "Chatterfang, Squirrel General",
        "Peregrin Took",
        "Birthday Escape",
        "Mizzium Skin",
        "Llanowar Elves",
        "Holy Strength",
        "Liquimetal Torque",
        "March of the Machines",
        "Mycosynth Lattice",
        "Cackling Counterpart",
        "Parallel Lives",
        "Doubling Season",
        "Pithing Needle",
        "Murder",
        "Naturalize",
        "Memnite",
        "Clone",
        "Unsummon",
        "Cloudshift",
        "Lightning Bolt",
        "Siege Mastodon",
        "Forest",
        "Zuran Orb",
        "Regrowth",
        "Grist, the Hunger Tide",
        "Cremate",
        "Stifle",
        "Bottomless Pool // Locker Room",
        "Island",
        "Swamp",
        "Mountain",

    ]
    s = table(cards, [name, *support], support, support)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True)
    return s, put(s, name, "hand")



@pytest.mark.parametrize("name", NAMES)
def test_canonical_cards_are_full(cards, name):
    from app.rules import coverage
    result = coverage.of_card_data(cards.resolve(name))
    assert result.level == "FULL", [(f.label, f.supported) for f in result.features]


def tokens(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')]


def choose(s, ids):
    until(s, lambda s: s.state.rules.decision is not None, limit=20)
    d = s.state.rules.decision
    while d.kind in ('declare_attackers', 'declare_blockers'):
        act(s, d.player, type=d.kind, **({'attackers': []} if d.kind == 'declare_attackers' else {'blocks': []}))
        until(s, lambda s: s.state.rules.decision is not None, limit=20)
        d = s.state.rules.decision
    assert set(ids) <= {o.id for o in d.options}, (d.kind, d.resume, [(o.id, o.label) for o in d.options])
    act(s, d.player, type='choose', decision_id=d.id, option_ids=list(ids))


def test_cytoshape_resolution_original_choice_and_end_turn_restore(cards):
    s, spell = setup(cards, 'Cytoshape')
    target = put(s, 'Memnite', 'battlefield')
    original = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, spell, targets=[target.id])
    choose(s, [original.id])
    settle(s)
    assert ch(s, target).name == 'Grizzly Bears' and ch(s, target).pt == (2, 2)
    assert ch(s, target).types == frozenset({'Creature'})
    to_phase(s, 'upkeep', turn=2)
    assert ch(s, target).name == 'Memnite' and 'Artifact' in ch(s, target).types
    roundtrip(s)


@pytest.mark.parametrize('mode', [0, 1])
def test_masterful_both_native_modes_and_shared_frozen_original(cards, mode):
    s, spell = setup(cards, 'Masterful Replication')
    target = put(s, 'Memnite', 'battlefield')
    other = put(s, 'Liquimetal Torque', 'battlefield')
    cast(s, spell, modes=[mode], targets=[target.id] if mode else [])
    settle(s)
    if mode == 0:
        assert len(tokens(s)) == 2 and all(ch(s, c).pt == (3, 3) for c in tokens(s))
    else:
        assert ch(s, other).name == 'Memnite' and ch(s, other).pt == (1, 1)
        assert ch(s, target).name == 'Memnite'
        to_phase(s, 'upkeep', turn=2)
        assert ch(s, other).name == 'Liquimetal Torque'
    roundtrip(s)


def test_polymorphous_two_targets_strive_and_one_selected_recipe(cards):
    s, spell = setup(cards, 'Polymorphous Rush')
    a = put(s, 'Memnite', 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    original = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, spell, targets=[a.id, b.id], target_counts=[2])
    paid = s.state.rules.payments[s.state.rules.object_id(spell.id)]
    assert sum(paid.mana_spent.values()) == 5
    choose(s, [original.id])
    settle(s)
    assert ch(s, a).pt == ch(s, b).pt == (2, 2)
    assert ch(s, a).name == ch(s, b).name == 'Grizzly Bears'
    to_phase(s, 'upkeep', turn=2)
    assert ch(s, a).name == 'Memnite' and ch(s, b).name == 'Llanowar Elves'
    roundtrip(s)


def test_dane_native_sacrifice_lki_and_retained_activation(cards):
    s, source = setup(cards, "The Ever-Changing 'Dane")
    source = put(s, "The Ever-Changing 'Dane", 'battlefield')
    original = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    settle(s)
    assert original.zone == 'p1:graveyard'
    assert ch(s, source).name == 'Grizzly Bears' and ch(s, source).pt == (2, 2)
    ability = next(a.index for a in ch(s, source).abilities if 'Sacrifice another creature' in a.text)
    second = put(s, 'Memnite', 'battlefield')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability)
    settle(s)
    assert second.zone == 'p1:graveyard' and ch(s, source).name == 'Memnite'
    assert 'Artifact' in ch(s, source).types
    roundtrip(s)


def test_gogo_copies_name_then_both_exact_subjects_gain_bonus_haste_and_attack(cards):
    s, source = setup(cards, 'Gogo, Mysterious Mime')
    to_phase(s, 'main1', turn=4)
    source = put(s, 'Gogo, Mysterious Mime', 'battlefield')
    original = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Memnite', 'battlefield')
    to_phase(s, 'begin_combat', turn=4)
    choose(s, [original.id])
    choose(s, ['pay'])
    settle(s)
    assert ch(s, source).name == 'Gogo, Mysterious Mime'
    assert ch(s, source).pt == ch(s, original).pt == (4, 2)
    assert all('haste' in ch(s, c).keywords and 'must_attack' in ch(s, c).imposed for c in (source, original))
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in (source, original)])
    to_phase(s, 'upkeep', turn=5)
    assert ch(s, source).pt == ch(s, original).pt == (2, 2)
    assert 'haste' not in ch(s, original).keywords
    roundtrip(s)


def test_kimahri_copy_keeps_own_name_counter_vigilance_and_next_combat_ability(cards):
    s, source = setup(cards, 'Kimahri, Valiant Guardian')
    to_phase(s, 'main1', turn=4)
    source = put(s, 'Kimahri, Valiant Guardian', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Memnite', 'battlefield', 'p2')
    to_phase(s, 'begin_combat', turn=4)
    choose(s, [bear.id])
    choose(s, ['pay'])
    settle(s)
    assert bear.tapped
    assert ch(s, source).name == 'Kimahri, Valiant Guardian' and ch(s, source).pt == (3, 3)
    assert source.counters['+1/+1'] == 1 and 'vigilance' in ch(s, source).keywords
    assert any('beginning of combat' in a.text for a in ch(s, source).abilities)
    roundtrip(s)


def test_taskmaster_heterogeneous_graveyard_target_and_next_turn_duration(cards):
    s, source = setup(cards, 'Taskmaster, Mercenary Mimic')
    source = put(s, 'Taskmaster, Mercenary Mimic', 'battlefield')
    original = put(s, 'Memnite', 'graveyard')
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=4)
    choose(s, [original.id])
    settle(s)
    assert ch(s, source).name == 'Taskmaster, Mercenary Mimic' and ch(s, source).pt == (1, 1)
    assert ch(s, source).types == frozenset({'Creature'})
    assert ch(s, source).subtypes == frozenset({'Human', 'Mercenary', 'Villain'})
    assert 'Legendary' in ch(s, source).supertypes
    to_phase(s, 'upkeep', turn=5)
    assert ch(s, source).pt == (1, 1)
    to_phase(s, 'upkeep', turn=7)
    assert ch(s, source).pt == (3, 5)
    roundtrip(s)


def test_deepfathom_explores_before_optional_resolution_choice(cards):
    s, source = setup(cards, 'Deepfathom Echo')
    to_phase(s, 'main1', turn=4)
    source = put(s, 'Deepfathom Echo', 'battlefield')
    original = put(s, 'Memnite', 'battlefield')
    to_phase(s, 'main1', turn=4)
    top = next(s.state.cards[c] for c in s.state.zones['p1:library'] if s.state.cards[c].name == 'Forest')
    act(s, 'p1', type='move', card_ids=[top.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    to_phase(s, 'begin_combat', turn=4)
    choose(s, [original.id])
    settle(s)
    assert top.zone == 'p1:hand'
    assert ch(s, source).name == 'Memnite' and not source.counters
    to_phase(s, 'upkeep', turn=5)
    assert ch(s, source).name == 'Deepfathom Echo'
    roundtrip(s)


def test_flood_native_attack_changes_land_only_and_creature_only_branches(cards):
    s, source = setup(cards, 'The Flood of Mars')
    source = put(s, 'The Flood of Mars', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    choose(s, [target.id])
    settle(s)
    assert target.counters['flood'] == 1 and ch(s, target).name == 'The Flood of Mars'
    assert 'Land' not in ch(s, target).types and 'Island' not in ch(s, target).subtypes
    roundtrip(s)


def test_permeating_damage_recipient_becomes_copy_without_losing_damage(cards):
    s, source = setup(cards, 'Permeating Mass')
    source = put(s, 'Permeating Mass', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': target.id, 'attacker_id': source.id}])
    to_phase(s, 'end_combat', turn=4)
    settle(s)
    assert ch(s, target).name == 'Permeating Mass' and ch(s, target).pt == (1, 3)
    assert target.damage == 1 and source.damage == 2
    roundtrip(s)


def test_hall_timed_global_legend_exemption_survives_source_departure(cards):
    s, source = setup(cards, 'Hall of Echoes')
    source = put(s, 'Hall of Echoes', 'battlefield')
    original = put(s, 'Krenko, Mob Boss', 'battlefield')
    put(s, 'Memnite', 'battlefield')
    mana(s, C=5)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1, targets=[original.id])
    settle(s)
    assert ch(s, source).name == 'Krenko, Mob Boss' and original.zone == 'p1:battlefield'
    bounce = put(s, 'Unsummon', 'hand')
    cast(s, bounce, targets=[source.id])
    settle(s)
    assert source.zone == 'p1:hand'
    clone = put(s, 'Clone', 'hand')
    cast(s, clone)
    choose(s, [original.id])
    settle(s)
    assert original.zone == clone.zone == 'p1:battlefield'
    assert ch(s, clone).name == 'Krenko, Mob Boss'
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get('step') == 'legend_rule')
    choose(s, [original.id])
    settle(s)
    assert clone.zone == 'p1:graveyard'
    roundtrip(s)


def test_drifter_native_optional_reveal_copies_top_then_restores_end_turn(cards):
    s, source = setup(cards, 'Vesuvan Drifter')
    source = put(s, 'Vesuvan Drifter', 'battlefield')
    to_phase(s, 'main1', turn=4)
    original = put(s, 'Grizzly Bears', 'hand')
    act(s, 'p1', type='move', card_ids=[original.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    to_phase(s, 'begin_combat', turn=4)
    choose(s, ['pay'])
    settle(s)
    assert original.zone == 'p1:library'
    assert ch(s, source).name == 'Grizzly Bears' and 'flying' in ch(s, source).keywords
    assert not original.revealed_to
    to_phase(s, 'upkeep', turn=5)
    assert ch(s, source).name == 'Vesuvan Drifter'
    roundtrip(s)


def test_shadow_kin_all_players_actual_mill_pool_then_exact_exile_copy(cards):
    s, source = setup(cards, 'Shadow Kin')
    source = put(s, 'Shadow Kin', 'battlefield')
    to_phase(s, 'end', turn=3)
    a = put(s, 'Grizzly Bears', 'hand')
    b = put(s, 'Memnite', 'hand', 'p2')
    c = put(s, 'Llanowar Elves', 'hand', 'p3')
    for player, original in [('p1', a), ('p2', b), ('p3', c)]:
        act(s, player, type='move', card_ids=[original.id], to={'player': player, 'zone': 'library'}, index=0)
    to_phase(s, 'upkeep', turn=4)
    choose(s, [b.id])
    settle(s)
    assert a.zone == 'p1:graveyard' and c.zone == 'p3:graveyard' and b.zone == 'p2:exile'
    assert ch(s, source).name == 'Memnite' and ch(s, source).pt == (1, 1)
    assert any('each player mills three' in ability.text.lower() for ability in ch(s, source).abilities)
    roundtrip(s)


def test_nascent_target_opponent_reveal_copy_before_random_bottom_all(cards):
    s, source = setup(cards, 'Nascent Metamorph')
    source = put(s, 'Nascent Metamorph', 'battlefield')
    to_phase(s, 'main1', turn=4)
    bear = put(s, 'Grizzly Bears', 'hand', 'p2')
    forest = put(s, 'Forest', 'hand', 'p2')
    for original in [bear, forest]:
        act(s, 'p2', type='move', card_ids=[original.id], to={'player': 'p2', 'zone': 'library'}, index=0)
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    choose(s, ['p2'])
    settle(s)
    assert ch(s, source).name == 'Grizzly Bears' and ch(s, source).pt == (2, 2)
    assert set(s.state.zones['p2:library'][-2:]) == {bear.id, forest.id}
    assert not bear.revealed_to and not forest.revealed_to
    roundtrip(s)


def test_spirit_hidden_departure_cannot_be_chosen_then_public_exile_can(cards):
    s, source = setup(cards, 'Spirit of Resilience')
    source = put(s, 'Spirit of Resilience', 'battlefield')
    hidden = put(s, 'Memnite', 'graveyard')
    spell = put(s, 'Regrowth', 'hand')
    cast(s, spell, targets=[hidden.id])
    settle(s)
    assert hidden.zone == 'p1:hand' and source.counters['+1/+1'] == 1
    assert ch(s, source).name == 'Spirit of Resilience'
    original = put(s, 'Grizzly Bears', 'graveyard')
    cremation = put(s, 'Cremate', 'hand')
    cast(s, cremation, targets=[original.id])
    choose(s, [original.id])
    settle(s)
    assert original.zone == 'p1:exile' and source.counters['+1/+1'] == 2
    assert ch(s, source).name == 'Grizzly Bears' and ch(s, source).pt == (4, 4)
    to_phase(s, 'upkeep', turn=2)
    assert ch(s, source).name == 'Spirit of Resilience' and source.counters['+1/+1'] == 2
    roundtrip(s)


def test_lazav_native_attack_link_investigate_and_clue_sacrifice_copy(cards):
    s, source = setup(cards, 'Lazav, Wearer of Faces')
    source = put(s, 'Lazav, Wearer of Faces', 'battlefield')
    original = put(s, 'Grizzly Bears', 'graveyard')
    put(s, 'Memnite', 'graveyard', 'p2')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    choose(s, [original.id])
    settle(s)
    clue = next(c for c in tokens(s) if 'Clue' in ch(s, c).subtypes)
    assert original.zone == 'p1:exile'
    mana(s, C=2)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=clue.id, ability=0)
    choose(s, [original.id])
    settle(s)
    assert ch(s, source).name == 'Grizzly Bears'
    assert clue.id not in s.state.cards or not s.state.cards[clue.id].zone.endswith(':battlefield')
    to_phase(s, 'upkeep', turn=5)
    assert ch(s, source).name == 'Lazav, Wearer of Faces'
    roundtrip(s)


def test_cytoshape_nontarget_original_choice_resumes_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, spell = setup(cards, 'Cytoshape')
    target = put(s, 'Memnite', 'battlefield')
    original = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, spell, targets=[target.id])
    until(s, lambda s: s.state.rules.decision is not None)
    assert s.state.rules.decision.resume['step'] == 'select_copy_originals'
    s = cold_choose(s, cards, tmp_path, [original.id])
    settle(s)
    assert ch(s, target).name == 'Grizzly Bears'
    roundtrip(s)


def test_gogo_source_gone_cannot_pay_copy_cost_or_grant_target_bonus(cards):
    s, source = setup(cards, 'Gogo, Mysterious Mime')
    to_phase(s, 'main1', turn=4)
    source = put(s, 'Gogo, Mysterious Mime', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Memnite', 'battlefield')
    to_phase(s, 'begin_combat', turn=4)
    choose(s, [target.id])
    bounce = put(s, 'Unsummon', 'hand')
    cast(s, bounce, targets=[source.id])
    settle(s)
    assert source.zone == 'p1:hand'
    assert ch(s, target).pt == (2, 2) and 'haste' not in ch(s, target).keywords
    assert 'must_attack' not in ch(s, target).imposed
    roundtrip(s)


def test_dane_copies_sacrificed_clone_lki_even_after_new_card_exiled(cards):
    s, source = setup(cards, "The Ever-Changing 'Dane")
    source = put(s, "The Ever-Changing 'Dane", 'battlefield')
    original = put(s, 'Memnite', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    clone = put(s, 'Clone', 'hand')
    cast(s, clone)
    choose(s, [original.id])
    settle(s)
    mana(s, C=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    choose(s, [clone.id])
    assert clone.zone == 'p1:graveyard'
    cremation = put(s, 'Cremate', 'hand')
    cast(s, cremation, targets=[clone.id])
    settle(s)
    assert clone.zone == 'p1:exile'
    assert ch(s, source).name == 'Memnite' and ch(s, source).pt == (1, 1)
    assert 'Artifact' in ch(s, source).types
    roundtrip(s)


def test_flood_source_leaves_before_resolution_uses_its_exact_lki(cards):
    s, source = setup(cards, 'The Flood of Mars')
    source = put(s, 'The Flood of Mars', 'battlefield')
    target = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    choose(s, [target.id])
    bounce = put(s, 'Unsummon', 'hand')
    cast(s, bounce, targets=[source.id])
    settle(s)
    assert source.zone == 'p1:hand'
    assert ch(s, target).name == 'The Flood of Mars' and target.counters['flood'] == 1
    roundtrip(s)


def test_permeating_source_dies_simultaneously_and_survivor_uses_lki(cards):
    s, source = setup(cards, 'Permeating Mass')
    source = put(s, 'Permeating Mass', 'battlefield')
    target = put(s, 'Siege Mastodon', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == 'declare_blockers')
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': target.id, 'attacker_id': source.id}])
    to_phase(s, 'end_combat', turn=4)
    settle(s)
    assert source.zone == 'p1:graveyard'
    assert ch(s, target).name == 'Permeating Mass' and ch(s, target).pt == (1, 3)
    assert target.damage == 1
    roundtrip(s)


@pytest.mark.parametrize('accept', [True, False])
def test_drifter_noncreature_or_declined_reveal_has_no_copy_or_public_leak(cards, accept):
    s, source = setup(cards, 'Vesuvan Drifter')
    to_phase(s, 'main1', turn=4)
    source = put(s, 'Vesuvan Drifter', 'battlefield')
    top = next(s.state.cards[c] for c in s.state.zones['p1:library'] if s.state.cards[c].name == 'Forest')
    act(s, 'p1', type='move', card_ids=[top.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    to_phase(s, 'begin_combat', turn=4)
    choose(s, ['pay' if accept else 'decline'])
    settle(s)
    assert ch(s, source).name == 'Vesuvan Drifter'
    assert not top.revealed_to and top.zone == 'p1:library'
    roundtrip(s)


@pytest.mark.parametrize('name', ['Gogo, Mysterious Mime', "The Ever-Changing 'Dane", 'Shadow Kin'])
def test_optional_cost_and_mill_original_choices_resume_cold(cards, tmp_path, name):
    from tests.test_rules_linked_return_family import cold_choose
    s, source = setup(cards, name)
    if name == 'Shadow Kin':
        to_phase(s, 'end', turn=3)
        source = put(s, name, 'battlefield')
        original = put(s, 'Grizzly Bears', 'hand', 'p2')
        act(s, 'p2', type='move', card_ids=[original.id], to={'player': 'p2', 'zone': 'library'}, index=0)
        to_phase(s, 'upkeep', turn=4)
        until(s, lambda s: s.state.rules.decision is not None)
        s = cold_choose(s, cards, tmp_path, [original.id])
        settle(s)
        assert s.state.cards[original.id].zone == 'p2:exile'
        assert ch(s, source).name == 'Grizzly Bears'
    else:
        to_phase(s, 'main1', turn=4)
        source = put(s, name, 'battlefield')
        original = put(s, 'Grizzly Bears', 'battlefield')
        put(s, 'Memnite', 'battlefield')
        if name.startswith('Gogo'):
            to_phase(s, 'begin_combat', turn=4)
            choose(s, [original.id])
            until(s, lambda s: s.state.rules.decision is not None)
            s = cold_choose(s, cards, tmp_path, ['pay'])
            settle(s)
            assert ch(s, source).pt == ch(s, original).pt == (4, 2)
        else:
            mana(s, C=1)
            wait_priority(s, 'p1')
            act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
            until(s, lambda s: s.state.rules.decision is not None)
            assert s.state.cards[original.id].zone == 'p1:battlefield'
            s = cold_choose(s, cards, tmp_path, [original.id])
            settle(s)
            assert s.state.cards[original.id].zone == 'p1:graveyard'
            assert ch(s, source).name == 'Grizzly Bears'
    roundtrip(s)


def test_dane_countered_activation_keeps_paid_sacrifice_and_no_copy(cards):
    s, source = setup(cards, "The Ever-Changing 'Dane")
    source = put(s, "The Ever-Changing 'Dane", 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield')
    mana(s, C=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    assert victim.zone == 'p1:graveyard'
    ability = s.state.zones['stack'][-1]
    stifle = put(s, 'Stifle', 'hand', 'p2')
    mana(s, pid='p2', U=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=stifle.id, targets=[ability])
    settle(s)
    assert ch(s, source).name == "The Ever-Changing 'Dane"
    assert victim.zone == 'p1:graveyard' and ch(s, source).pt == (3, 3)
    roundtrip(s)


def test_cytoshape_original_is_nontarget_choice_even_with_opponent_hexproof(cards):
    s, spell = setup(cards, 'Cytoshape')
    target = put(s, 'Memnite', 'battlefield')
    original = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    skin = put(s, 'Mizzium Skin', 'hand', 'p2')
    mana(s, pid='p2', U=1)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=skin.id, targets=[original.id])
    settle(s)
    assert 'hexproof' in ch(s, original).keywords
    cast(s, spell, targets=[target.id])
    choose(s, [original.id])
    settle(s)
    assert ch(s, target).name == 'Grizzly Bears'
    assert 'hexproof' not in ch(s, target).keywords
    roundtrip(s)


def test_drifter_uses_genuine_outside_battlefield_grist_creature_eligibility(cards):
    s, source = setup(cards, 'Vesuvan Drifter')
    to_phase(s, 'main1', turn=4)
    source = put(s, 'Vesuvan Drifter', 'battlefield')
    original = put(s, 'Grist, the Hunger Tide', 'hand')
    act(s, 'p1', type='move', card_ids=[original.id], to={'player': 'p1', 'zone': 'library'}, index=0)
    assert 'Creature' in ch(s, original).types
    to_phase(s, 'begin_combat', turn=4)
    choose(s, ['pay'])
    settle(s)
    # The library card is a creature. The copy on the battlefield is a
    # planeswalker, receives no enters-with-loyalty counters, and dies at zero.
    assert source.zone == 'p1:graveyard'
    assert original.zone == 'p1:library' and not original.revealed_to
    roundtrip(s)
