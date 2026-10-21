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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_linked_aggregates import cast, ch
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = [
    c["name"]
    for c in json.loads((Path(__file__).parent / "fixtures/token_copy_continuations_cards.json").read_text())[:15]
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/token_copy_continuations_cards.json").read_text())
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
        "Bottomless Pool // Locker Room",
        "Island",
        "Swamp",
        "Mountain",

    ]
    s = table(cards, [name, *support, *NAMES, "Bonesplitter", "Changeling Outcast", "Ornithopter", "Reanimate", "Think Twice", "Rest in Peace", "Darksteel Ingot", "Hour of Eternity", "Solemnity", "Spark Double", "Black Knight", "Masterwork of Ingenuity", "Timecrafting", "Contentious Plan", "Magnetic Theft", "Renegade Krasis", "Rite of the Raging Storm", "Hardened Scales", "Diregraf Ghoul", "Divine Visitation", "Army of the Damned", "Brood Keeper", "Triskelavus"], [*support, "Bonesplitter", "Changeling Outcast", "Ornithopter", "Reanimate", "Think Twice", "Rest in Peace", "Darksteel Ingot", "Hour of Eternity", "Grub's Command"], support)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True)
    return s, put(s, name, "hand")




def choose(s, ids):
    until(s, lambda s: s.state.rules.decision is not None, limit=20)
    d = s.state.rules.decision
    assert set(ids) <= {o.id for o in d.options}, (d.kind, d.resume, [(o.id, o.label) for o in d.options])
    act(s, d.player, type='choose', decision_id=d.id, option_ids=list(ids))


def tokens(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')]


def activate(s, src, ability=0, **kw):
    from tests.test_rules_linked_aggregates import activate as native
    return native(s, src, ability=ability, **kw)


def test_vizier_actual_embalm_offers_copy_before_entry(cards):
    s, source = setup(cards, 'Vizier of Many Faces')
    source = put(s, 'Vizier of Many Faces', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    activate(s, source, ability=1)
    until(s, lambda s: s.state.rules.decision is not None, limit=20)
    d = s.state.rules.decision
    assert bear.id in {o.id for o in d.options}, (d.kind, d.resume)
    choose(s, [bear.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and ch(s, made[0]).name == 'Grizzly Bears'
    assert ch(s, made[0]).colors == frozenset({'W'}) and 'Zombie' in ch(s, made[0]).subtypes
    assert ch(s, made[0]).mana_cost == '' and ch(s, made[0]).mana_value == 0
    roundtrip(s)


def test_generic_clone_token_entry_chooses_own_copy(cards):
    s, source = setup(cards, 'Hour of Eternity')
    original = put(s, 'Clone', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, source, x_value=1, targets=[original.id], target_counts=[1])
    until(s, lambda s: s.state.rules.decision is not None, limit=20)
    d = s.state.rules.decision
    assert bear.id in {o.id for o in d.options}, (d.kind, d.resume)
    choose(s, [bear.id])
    settle(s)
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Grizzly Bears'
    assert ch(s, tokens(s)[0]).pt == (2, 2)
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_canonical_cards_are_full(cards, name):
    from app.rules import coverage
    r = coverage.of_card_data(cards.resolve(name))
    assert r.level == 'FULL', [(f.label, f.supported) for f in r.features]


def test_radstag_actual_evolve_creates_copy_but_manual_counter_does_not(cards):
    s, source = setup(cards, 'Watchful Radstag')
    source = put(s, source.name, 'battlefield')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=1)
    settle(s)
    assert not tokens(s)
    bear = put(s, 'Siege Mastodon', 'hand')
    cast(s, bear)
    settle(s)
    assert source.counters.get('+1/+1') == 2
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Watchful Radstag'
    roundtrip(s)


def test_daretti_copies_foreign_graveyard_artifact_three_times(cards):
    s, source = setup(cards, 'Daretti, Ingenious Iconoclast')
    source = put(s, source.name, 'battlefield')
    artifact = put(s, 'Darksteel Ingot', 'graveyard', 'p2')
    act(s, 'p1', type='counter', card_ids=[source.id], kind='loyalty', delta=6)
    activate(s, source, ability=2, targets=[artifact.id])
    settle(s)
    assert len(tokens(s)) == 3 and all(ch(s, c).name == 'Darksteel Ingot' for c in tokens(s))
    assert artifact.zone == 'p2:graveyard'
    roundtrip(s)


def test_jace_actual_kicked_entry_and_zero_draw(cards):
    from tests.test_rules_token_copy_outcomes import top
    s, source = setup(cards, 'Jace, Mirror Mage')
    drawn = top(s, 'Grizzly Bears')
    cast(s, source, kicker=True)
    settle(s)
    assert len(tokens(s)) == 1 and tokens(s)[0].counters.get('loyalty') == 1
    assert 'Legendary' not in ch(s, tokens(s)[0]).supertypes
    activate(s, source, ability=3)
    settle(s)
    assert drawn.zone == 'p1:hand' and source.counters.get('loyalty') == 2
    roundtrip(s)


def test_hofri_actual_dies_exiles_copies_and_returns_exact_card(cards):
    s, source = setup(cards, 'Hofri Ghostforge')
    source = put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    spell = put(s, 'Murder', 'hand')
    cast(s, spell, targets=[bear.id])
    settle(s)
    assert bear.zone == 'p1:exile'
    made = tokens(s)
    assert len(made) == 1 and 'Spirit' in ch(s, made[0]).subtypes and ch(s, made[0]).pt == (3, 3)
    bounce = put(s, 'Unsummon', 'hand')
    cast(s, bounce, targets=[made[0].id])
    settle(s)
    assert bear.zone == 'p1:graveyard'
    roundtrip(s)


def test_leonardo_real_discard_exile_copy_and_hand_size_animation(cards):
    s, source = setup(cards, 'Leonardo da Vinci')
    source = put(s, source.name, 'battlefield')
    artifact = put(s, 'Darksteel Ingot', 'hand')
    to_phase(s, 'main1', turn=4)
    activate(s, source, ability=1)
    choose(s, [artifact.id])
    settle(s)
    assert artifact.zone == 'p1:exile'
    made = tokens(s)[0]
    assert ch(s, made).pt == (0, 2) and {'Artifact', 'Creature'} <= ch(s, made).types
    assert 'Thopter' in ch(s, made).subtypes and 'flying' in ch(s, made).keywords
    activate(s, source, ability=0)
    settle(s)
    n = len(s.state.zones['p1:hand'])
    assert ch(s, made).pt == (n, n)
    roundtrip(s)


def test_arna_copies_equipment_attached_and_doubles_actual_counters(cards):
    s, source = setup(cards, 'Arna Kennerüd, Skycaptain')
    source = put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    equipment = put(s, 'Bonesplitter', 'battlefield')
    activate(s, equipment, ability=1, targets=[bear.id])
    settle(s)
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=1)
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    settle(s)
    assert bear.counters.get('+1/+1') == 2
    assert len(tokens(s)) == 1 and tokens(s)[0].attached_to == bear.id
    assert ch(s, bear).pt == (8, 4)
    roundtrip(s)


def test_three_dog_pays_sacrifices_and_copies_aura_to_other_attacker(cards):
    s, source = setup(cards, 'Three Dog, Galaxy News DJ')
    source = put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    aura = put(s, 'Holy Strength', 'hand')
    cast(s, aura, targets=[source.id])
    settle(s)
    to_phase(s, 'declare_attackers', turn=4)
    mana(s, 'p1', C=2)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}, {'card_id': bear.id, 'target': 'p3'}])
    choose(s, ['pay'])
    settle(s)
    assert aura.zone == 'p1:graveyard'
    assert len(tokens(s)) == 1 and tokens(s)[0].attached_to == bear.id
    assert ch(s, bear).pt == (3, 4)
    roundtrip(s)


def test_living_laser_native_discard_attack_and_end_cleanup(cards):
    s, source = setup(cards, 'Living Laser')
    source = put(s, source.name, 'battlefield')
    discarded = put(s, 'Grizzly Bears', 'hand')
    leonardo = put(s, 'Leonardo da Vinci', 'battlefield')
    to_phase(s, 'main1', turn=4)
    activate(s, leonardo, ability=1)
    choose(s, [discarded.id])
    settle(s)
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    choose(s, ['p3'])
    settle(s)
    made = tokens(s)[0]
    assert made.tapped and made.attacking.id == 'p3' and 'Legendary' not in ch(s, made).supertypes
    to_phase(s, 'end')
    settle(s)
    assert made.id not in s.state.cards or not s.state.cards[made.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_calamity_native_saddle_two_sequential_copies_and_cleanup(cards):
    s, source = setup(cards, 'Calamity, Galloping Inferno')
    source = put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    activate(s, source, ability=2, crew=[bear.id])
    settle(s)
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    choose(s, ['p2'])
    choose(s, ['p3'])
    settle(s)
    assert len(tokens(s)) == 2 and all(ch(s, c).name == 'Grizzly Bears' for c in tokens(s))
    to_phase(s, 'end')
    settle(s)
    assert not tokens(s)
    roundtrip(s)


def test_mirage_pair_grants_two_combat_copies_without_soulbond(cards):
    s, source = setup(cards, 'Mirage Phalanx')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, source)
    choose(s, ['yes'])
    settle(s)
    assert s.state.rules.pairs
    to_phase(s, 'begin_combat')
    settle(s)
    assert len(tokens(s)) == 2
    assert all('haste' in ch(s, c).keywords and 'soulbond' not in ch(s, c).keywords for c in tokens(s))
    to_phase(s, 'end_combat')
    settle(s)
    assert not tokens(s)
    assert bear.zone.endswith(':battlefield')
    roundtrip(s)


def test_runo_reveals_six_mana_creature_transforms_and_krothuss_attacks(cards):
    s, source = setup(cards, 'Runo Stromkirk // Krothuss, Lord of the Deep')
    # The actual ETB puts the chosen six-mana creature on top for the upkeep reveal.
    original = put(s, 'Mirage Phalanx', 'graveyard')
    cast(s, source, targets=[original.id], target_counts=[1])
    settle(s)
    to_phase(s, 'upkeep', turn=4)
    choose(s, ['pay'])
    settle(s)
    assert ch(s, source).name == 'Krothuss, Lord of the Deep'
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'declare_attackers', turn=7)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}, {'card_id': bear.id, 'target': 'p2'}])
    choose(s, [bear.id])
    choose(s, ['p3'])
    settle(s)
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Grizzly Bears'
    assert tokens(s)[0].attacking.id == 'p3'
    roundtrip(s)


def test_terra_front_mills_trance_and_saga_copy_choice(cards):
    s, source = setup(cards, 'Terra, Magical Adept // Esper Terra')
    source = put(s, source.name, 'battlefield')
    aura = put(s, 'Holy Strength', 'hand')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, aura, targets=[bear.id])
    settle(s)
    to_phase(s, 'main1', turn=4)
    activate(s, source, ability=1)
    choose(s, [aura.id])
    choose(s, [bear.id])
    settle(s)
    assert ch(s, source).name == 'Esper Terra'
    assert len(tokens(s)) == 1 and tokens(s)[0].attached_to == bear.id
    assert 'haste' in ch(s, tokens(s)[0]).keywords
    roundtrip(s)


def test_grub_command_mills_goblins_and_copies_real_goblin(cards):
    from tests.test_rules_token_copy_outcomes import top
    s, spell = setup(cards, "Grub's Command")
    goblin = put(s, 'Changeling Outcast', 'battlefield')
    milled = top(s, "Grub's Command", 'p2')
    cast(s, spell, modes=[0, 3], targets=[goblin.id, 'p2'], target_counts=[1, 1])
    settle(s)
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Changeling Outcast'
    assert milled.zone == 'p2:hand'
    roundtrip(s)


def test_grub_native_main_phase_transform_and_blight_copy(cards):
    s, source = setup(cards, 'Grub, Storied Matriarch // Grub, Notorious Auntie')
    source = put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=4)
    mana(s, R=1)
    choose(s, ['pay'])
    settle(s)
    assert ch(s, source).name == 'Grub, Notorious Auntie'
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    choose(s, ['pay'])
    choose(s, [bear.id])
    choose(s, ['p3'])
    settle(s)
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Grizzly Bears'
    assert bear.counters.get('-1/-1') == 1 and ch(s, tokens(s)[0]).pt == (2, 2)
    to_phase(s, 'end')
    settle(s)
    assert not tokens(s)
    roundtrip(s)


def test_vizier_embalm_cold_copy_choice_and_copiable_provenance_boundary(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, source = setup(cards, 'Vizier of Many Faces')
    source = put(s, source.name, 'graveyard')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    activate(s, source, ability=1)
    until(s, lambda s: s.state.rules.decision is not None)
    s = cold_choose(s, cards, tmp_path, [bear.id])
    settle(s)
    made = tokens(s)[0]
    assert made.embalmed
    spell = put(s, 'Cackling Counterpart', 'hand')
    cast(s, spell, targets=[made.id])
    settle(s)
    copies = tokens(s)
    assert len(copies) == 2
    assert sum(c.embalmed for c in copies) == 1
    assert all(ch(s, c).colors == frozenset({'W'}) and 'Zombie' in ch(s, c).subtypes for c in copies)


def test_arna_fixed_host_and_replacement_extra_nonattachment_resume_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, source = setup(cards, 'Arna Kennerüd, Skycaptain')
    put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    equipment = put(s, 'Bonesplitter', 'battlefield')
    activate(s, equipment, ability=1, targets=[bear.id])
    settle(s)
    put(s, 'Parallel Lives', 'battlefield')
    put(s, 'Peregrin Took', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume['step'] == 'replace_order'
    s = cold_choose(s, cards, tmp_path, [d.options[0].id])
    settle(s)
    equipment_tokens = [c for c in tokens(s) if 'Equipment' in ch(s, c).subtypes]
    assert len(equipment_tokens) == 2 and all(c.attached_to == bear.id for c in equipment_tokens)
    assert all(c.attached_to is None for c in tokens(s) if 'Equipment' not in ch(s, c).subtypes)


def test_hofri_independent_copy_of_spirit_has_no_exiled_card_link(cards):
    s, source = setup(cards, 'Hofri Ghostforge')
    put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, put(s, 'Murder', 'hand'), targets=[bear.id])
    settle(s)
    original = tokens(s)[0]
    cast(s, put(s, 'Cackling Counterpart', 'hand'), targets=[original.id])
    settle(s)
    independent = next(c for c in tokens(s) if c.id != original.id)
    cast(s, put(s, 'Unsummon', 'hand'), targets=[independent.id])
    settle(s)
    assert bear.zone == 'p1:exile'
    cast(s, put(s, 'Unsummon', 'hand'), targets=[original.id])
    settle(s)
    assert bear.zone == 'p1:graveyard'
    roundtrip(s)


def test_hofri_extra_squirrel_has_no_link_and_actual_spirit_keeps_it(cards):
    s, source = setup(cards, 'Hofri Ghostforge')
    put(s, source.name, 'battlefield')
    put(s, 'Chatterfang, Squirrel General', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, put(s, 'Murder', 'hand'), targets=[bear.id])
    settle(s)
    assert len(tokens(s)) == 2
    squirrel = next(c for c in tokens(s) if 'Spirit' not in ch(s, c).subtypes)
    cast(s, put(s, 'Unsummon', 'hand'), targets=[squirrel.id])
    settle(s)
    assert bear.zone == 'p1:exile'
    spirit = tokens(s)[0]
    cast(s, put(s, 'Unsummon', 'hand'), targets=[spirit.id])
    settle(s)
    assert bear.zone == 'p1:graveyard'
    roundtrip(s)


def test_daretti_construct_and_real_sacrifice_destroy(cards):
    s, source = setup(cards, 'Daretti, Ingenious Iconoclast')
    cast(s, source)
    settle(s)
    activate(s, source, ability=0)
    settle(s)
    construct = tokens(s)[0]
    assert ch(s, construct).pt == (1, 1) and 'defender' in ch(s, construct).keywords
    to_phase(s, 'main1', turn=4)
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    activate(s, source, ability=1, targets=[victim.id])
    choose(s, ['pay'])
    settle(s)
    assert victim.zone == 'p2:graveyard'
    assert construct.id not in s.state.cards or not s.state.cards[construct.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_hofri_cold_pending_return_uses_exact_spirit_link(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, source = setup(cards, 'Hofri Ghostforge')
    put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Parallel Lives', 'battlefield')
    put(s, 'Peregrin Took', 'battlefield')
    cast(s, put(s, 'Murder', 'hand'), targets=[bear.id])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume['step'] == 'replace_order'
    s = cold_choose(s, cards, tmp_path, [d.options[0].id])
    settle(s)
    spirits = [c for c in tokens(s) if 'Spirit' in ch(s, c).subtypes]
    assert len(spirits) == 2
    cast(s, put(s, 'Unsummon', 'hand'), targets=[spirits[0].id])
    settle(s)
    assert s.state.cards[bear.id].zone == 'p1:graveyard'


def test_grub_command_other_two_modes_destroy_and_pump(cards):
    s, source = setup(cards, "Grub's Command")
    bear = put(s, 'Grizzly Bears', 'battlefield')
    victim = put(s, 'Darksteel Ingot', 'battlefield', 'p2')
    # Use a destructible creature rather than the indestructible artifact.
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, source, modes=[1, 2], targets=['p1', victim.id], target_counts=[1, 1])
    settle(s)
    assert victim.zone == 'p2:graveyard'
    assert ch(s, bear).pt == (3, 3) and 'haste' in ch(s, bear).keywords
    roundtrip(s)


@pytest.mark.parametrize('prevent', [False, True])
def test_radstag_evolves_only_when_native_counter_is_actually_put(cards, prevent):
    s, source = setup(cards, 'Watchful Radstag')
    source = put(s, source.name, 'battlefield')
    if prevent:
        put(s, 'Solemnity', 'battlefield')
    else:
        put(s, 'Doubling Season', 'battlefield')
    cast(s, put(s, 'Siege Mastodon', 'hand'))
    settle(s)
    assert source.counters.get('+1/+1', 0) == (0 if prevent else 2)
    assert len(tokens(s)) == (0 if prevent else 2)
    roundtrip(s)


def test_clone_token_preserves_additional_copy_entry_counter_rider(cards):
    s, spell = setup(cards, 'Hour of Eternity')
    original = put(s, 'Spark Double', 'graveyard')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, spell, x_value=1, targets=[original.id], target_counts=[1])
    choose(s, [bear.id])
    settle(s)
    made = tokens(s)[0]
    assert made.counters.get('+1/+1') == 1 and ch(s, made).pt == (3, 3)
    roundtrip(s)


def test_terra_actual_front_entry_and_fourth_chapter_returns_front(cards):
    s, source = setup(cards, 'Terra, Magical Adept // Esper Terra')
    cast(s, source)
    settle(s)
    assert len(s.state.zones['p1:graveyard']) >= 5
    to_phase(s, 'main1', turn=4)
    activate(s, source, ability=1)
    settle(s)
    assert ch(s, source).name == 'Esper Terra'
    act(s, 'p1', type='counter', card_ids=[source.id], kind='lore', delta=2)
    cast(s, put(s, 'Contentious Plan', 'hand'))
    act(s, 'p1', type='clear_mana', player='p1')
    choose(s, [source.id])
    settle(s)
    assert ch(s, source).name == 'Terra, Magical Adept'
    from app.rules.mana_units import visible_pool
    assert visible_pool(s.state, 'p1') == {color: 2 for color in ('W', 'U', 'B', 'R', 'G')}
    roundtrip(s)


def test_three_dog_does_not_create_aura_that_cannot_enchant_fixed_host(cards):
    s, source = setup(cards, 'Three Dog, Galaxy News DJ')
    source = put(s, source.name, 'battlefield')
    knight = put(s, 'Black Knight', 'battlefield')
    aura = put(s, 'Holy Strength', 'hand')
    cast(s, aura, targets=[source.id])
    settle(s)
    to_phase(s, 'declare_attackers', turn=4)
    mana(s, C=2)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}, {'card_id': knight.id, 'target': 'p3'}])
    choose(s, ['pay'])
    settle(s)
    assert aura.zone == 'p1:graveyard'
    assert not tokens(s)
    roundtrip(s)


def test_arna_fixed_host_survives_per_token_copy_entry_cold_choice(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, source = setup(cards, 'Arna Kennerüd, Skycaptain')
    put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    equipment = put(s, 'Masterwork of Ingenuity', 'battlefield')
    original = put(s, 'Bonesplitter', 'battlefield')
    cast(s, put(s, 'Magnetic Theft', 'hand'), targets=[equipment.id, bear.id], target_counts=[1, 1])
    settle(s)
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume['step'] == 'replace_order'
    assert original.id in {o.id for o in d.options}
    s = cold_choose(s, cards, tmp_path, [original.id])
    settle(s)
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Bonesplitter'
    assert tokens(s)[0].attached_to == bear.id


def test_collateral_renegade_krasis_actual_evolve_and_manual_negative(cards):
    s, source = setup(cards, 'Renegade Krasis')
    source = put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=1)
    act(s, 'p1', type='counter', card_ids=[source.id], kind='+1/+1', delta=1)
    settle(s)
    assert bear.counters.get('+1/+1') == 1
    cast(s, put(s, 'Siege Mastodon', 'hand'))
    settle(s)
    assert source.counters.get('+1/+1') == 2 and bear.counters.get('+1/+1') == 2
    roundtrip(s)


def test_collateral_renegade_native_counter_replacement_resumes_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, source = setup(cards, 'Renegade Krasis')
    source = put(s, source.name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    act(s, 'p1', type='counter', card_ids=[bear.id], kind='+1/+1', delta=1)
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Hardened Scales', 'battlefield')
    cast(s, put(s, 'Siege Mastodon', 'hand'))
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume['step'] == 'replace_order'
    s = cold_choose(s, cards, tmp_path, [d.options[0].id])
    settle(s)
    assert s.state.cards[source.id].counters.get('+1/+1') in (3, 4)
    assert s.state.cards[bear.id].counters.get('+1/+1') in (4, 5)


def test_collateral_rite_actual_recipient_attack_restriction_and_end_sacrifice(cards):
    from app.game.errors import ActionError
    s, spell = setup(cards, 'Rite of the Raging Storm')
    cast(s, spell)
    settle(s)
    to_phase(s, 'declare_attackers', turn=2)
    made = tokens(s)[0]
    assert made.controller == made.owner == 'p2'
    assert ch(s, made).pt == (5, 1) and {'haste', 'trample'} <= ch(s, made).keywords
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': made.id, 'target': 'p1'}])
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': made.id, 'target': 'p3'}])
    to_phase(s, 'end', turn=2)
    settle(s)
    assert not tokens(s)
    assert s.state.players['p3'].life == 35
    roundtrip(s)


def test_collateral_rite_native_creation_and_granted_end_trigger_resume_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, spell = setup(cards, 'Rite of the Raging Storm')
    cast(s, spell)
    settle(s)
    put(s, 'Parallel Lives', 'battlefield', 'p2')
    put(s, 'Peregrin Took', 'battlefield', 'p2')
    to_phase(s, 'upkeep', turn=2)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == 'p2' and d.resume['step'] == 'replace_order'
    s = cold_choose(s, cards, tmp_path, [d.options[0].id])
    settle(s)
    ragers = [c for c in tokens(s) if ch(s, c).name == 'Lightning Rager']
    assert len(ragers) == 2 and all(c.controller == 'p2' for c in ragers)
    to_phase(s, 'end', turn=2)
    settle(s)
    assert not any(ch(s, c).name == 'Lightning Rager' for c in tokens(s))
    assert any('Food' in ch(s, c).subtypes for c in tokens(s))


def test_collateral_rite_all_players_upkeep_and_independent_copy_after_source_leaves(cards):
    s, source = setup(cards, 'Rite of the Raging Storm')
    cast(s, source)
    settle(s)
    for turn, pid in [(2, 'p2'), (3, 'p3'), (4, 'p1')]:
        to_phase(s, 'upkeep', turn=turn)
        settle(s)
        assert len(tokens(s)) == 1 and tokens(s)[0].controller == pid
    original = tokens(s)[0]
    cast(s, put(s, 'Naturalize', 'hand'), targets=[source.id])
    settle(s)
    assert source.zone == 'p1:graveyard'
    cast(s, put(s, 'Cackling Counterpart', 'hand'), targets=[original.id])
    settle(s)
    assert len(tokens(s)) == 2
    assert all({'trample', 'haste'} <= ch(s, c).keywords for c in tokens(s))
    to_phase(s, 'end', turn=4)
    settle(s)
    assert not tokens(s)
    roundtrip(s)


def test_vizier_embalm_chosen_copy_obeys_its_intrinsic_enters_tapped(cards):
    s, source = setup(cards, 'Vizier of Many Faces')
    source = put(s, source.name, 'graveyard')
    original = put(s, 'Diregraf Ghoul', 'battlefield')
    activate(s, source, ability=1)
    choose(s, [original.id])
    settle(s)
    assert len(tokens(s)) == 1 and tokens(s)[0].tapped
    roundtrip(s)


@pytest.mark.parametrize('explicit', [False, True])
def test_creation_replacement_keeps_explicit_tap_but_not_replaced_intrinsic_tap(cards, explicit):
    s, spell = setup(cards, 'Army of the Damned' if explicit else 'Cackling Counterpart')
    original = put(s, 'Diregraf Ghoul', 'battlefield')
    put(s, 'Divine Visitation', 'battlefield')
    cast(s, spell, **({} if explicit else {'targets': [original.id]}))
    settle(s)
    assert len(tokens(s)) == (13 if explicit else 1)
    assert all(ch(s, c).name == 'Angel' and c.tapped == explicit for c in tokens(s))
    roundtrip(s)


def test_brood_keeper_intrinsic_flying_and_firebreathing_survive_independent_copy(cards):
    s, source = setup(cards, 'Brood Keeper')
    source = put(s, source.name, 'battlefield')
    cast(s, put(s, 'Holy Strength', 'hand'), targets=[source.id])
    settle(s)
    original = tokens(s)[0]
    assert ch(s, original).pt == (2, 2) and 'flying' in ch(s, original).keywords
    activate(s, original, ability=1)
    settle(s)
    assert ch(s, original).pt == (3, 2)
    cast(s, put(s, 'Cackling Counterpart', 'hand'), targets=[original.id])
    settle(s)
    independent = next(c for c in tokens(s) if c.id != original.id)
    assert ch(s, independent).pt == (2, 2) and 'flying' in ch(s, independent).keywords
    activate(s, independent, ability=1)
    settle(s)
    assert ch(s, independent).pt == (3, 2)
    roundtrip(s)


def test_triskelavus_intrinsic_flying_and_actual_sacrifice_damage_both_retained(cards):
    s, source = setup(cards, 'Triskelavus')
    cast(s, source)
    settle(s)
    assert source.counters.get('+1/+1') == 3
    activate(s, source, ability=2)
    settle(s)
    made = tokens(s)[0]
    assert ch(s, made).pt == (1, 1) and 'flying' in ch(s, made).keywords
    activate(s, made, ability=1, targets=['p2'])
    settle(s)
    assert s.state.players['p2'].life == 39
    assert not tokens(s)
    roundtrip(s)
