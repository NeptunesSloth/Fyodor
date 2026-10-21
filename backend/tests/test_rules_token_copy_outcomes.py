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
    for c in json.loads((Path(__file__).parent / "fixtures/token_copy_outcomes_cards.json").read_text())[:17]
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/token_copy_outcomes_cards.json").read_text())
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
    s = table(cards, [name, *support, *NAMES, "Bonesplitter", "Changeling Outcast", "Ornithopter", "Reanimate", "Think Twice", "Rest in Peace", "Darksteel Ingot"], [*support, "Bonesplitter", "Changeling Outcast", "Ornithopter", "Reanimate", "Think Twice", "Rest in Peace", "Darksteel Ingot"], support)
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



def activate(s, source, ability=0, **kwargs):
    from tests.test_rules_linked_aggregates import activate as native
    native(s, source, ability=ability, **kwargs)


def top(s, name, pid='p1'):
    c = put(s, name, 'library', pid)
    act(s, pid, type='move', card_ids=[c.id], to={'player': pid, 'zone': 'library'}, index=0)
    return c


def test_hour_copies_each_exiled_creature_and_preserves_artifact_type(cards):
    s, spell = setup(cards, 'Hour of Eternity')
    a = put(s, 'Memnite', 'graveyard')
    b = put(s, 'Grizzly Bears', 'graveyard')
    cast(s, spell, x_value=2, targets=[a.id, b.id], target_counts=[2])
    settle(s)
    assert a.zone == b.zone == 'p1:exile'
    assert len(tokens(s)) == 2
    assert all(ch(s, c).pt == (4, 4) and ch(s, c).colors == frozenset({'B'}) and 'Zombie' in ch(s, c).subtypes for c in tokens(s))
    assert 'Artifact' in ch(s, next(c for c in tokens(s) if c.name == 'Memnite')).types
    roundtrip(s)


@pytest.mark.parametrize('x', [0, 1])
def test_hour_exact_x_including_zero(cards, x):
    s, spell = setup(cards, 'Hour of Eternity')
    a = put(s, 'Grizzly Bears', 'graveyard')
    cast(s, spell, x_value=x, targets=[a.id] if x else [], target_counts=[x])
    settle(s)
    assert len(tokens(s)) == x
    roundtrip(s)


@pytest.mark.parametrize('overloaded', [False, True])
def test_march_actual_normal_and_overload(cards, overloaded):
    s, spell = setup(cards, 'March of Progress')
    a = put(s, 'Memnite', 'battlefield')
    put(s, 'Ornithopter', 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    cast(s, spell, targets=[] if overloaded else [a.id], **({'alt_cost': f'{spell.id}:1'} if overloaded else {}))
    settle(s)
    assert len(tokens(s)) == (2 if overloaded else 1)
    assert all(ch(s, c).name in ('Memnite', 'Ornithopter') for c in tokens(s))
    roundtrip(s)


def test_red_sun_copies_destroyed_lki_and_cleans_up(cards):
    s, spell = setup(cards, "Red Sun's Twilight")
    a = put(s, 'Memnite', 'battlefield', 'p2')
    b = put(s, 'Liquimetal Torque', 'battlefield', 'p3')
    cast(s, spell, x_value=5, targets=[a.id, b.id], target_counts=[2])
    settle(s)
    assert a.zone == 'p2:graveyard' and b.zone == 'p3:graveyard'
    assert len(tokens(s)) == 2
    assert all('haste' in ch(s, c).keywords for c in tokens(s))
    made = [c.id for c in tokens(s)]
    to_phase(s, 'end')
    settle(s)
    assert all(c not in s.state.cards or s.state.cards[c].zone.endswith(':exile') for c in made)
    roundtrip(s)


def test_haunting_public_library_originals_stay_and_hidden_after(cards):
    s, spell = setup(cards, 'Haunting Imitation')
    original = top(s, 'Grizzly Bears')
    top(s, 'Forest', 'p2')
    top(s, 'Memnite', 'p3')
    cast(s, spell)
    settle(s)
    assert len(tokens(s)) == 2
    assert original.zone == 'p1:library' and not original.revealed_to
    assert all(ch(s, c).pt == (1, 1) and 'Spirit' in ch(s, c).subtypes and 'flying' in ch(s, c).keywords for c in tokens(s))
    assert spell.zone == 'p1:graveyard'
    roundtrip(s)


def test_haunting_no_creatures_returns_spell(cards):
    s, spell = setup(cards, 'Haunting Imitation')
    for p in ('p1', 'p2', 'p3'):
        top(s, 'Forest', p)
    cast(s, spell)
    settle(s)
    assert not tokens(s) and spell.zone == 'p1:hand'
    roundtrip(s)


def test_osgood_cast_token_is_not_legendary_and_original_resolves(cards):
    s, spell = setup(cards, 'Osgood, Operation Double')
    cast(s, spell)
    settle(s)
    assert len(tokens(s)) == 1
    token = tokens(s)[0]
    assert ch(s, token).name == 'Osgood, Operation Double' and 'Legendary' not in ch(s, token).supertypes
    assert spell.zone == 'p1:battlefield'
    roundtrip(s)


def test_ultron_noncreature_and_creature_copy_outputs(cards):
    s, source = setup(cards, 'Ultron, Artificial Malevolence')
    put(s, 'Ultron, Artificial Malevolence', 'battlefield')
    artifact = put(s, 'Liquimetal Torque', 'hand')
    cast(s, artifact)
    choose(s, ['pay'])
    settle(s)
    assert len(tokens(s)) == 1
    token = tokens(s)[0]
    assert ch(s, token).pt == (2, 2) and {'Robot', 'Villain'} <= ch(s, token).subtypes
    assert {'Artifact', 'Creature'} <= ch(s, token).types
    other = put(s, 'Memnite', 'hand')
    cast(s, other)
    choose(s, ['pay'])
    settle(s)
    assert ch(s, next(c for c in tokens(s) if c.name == 'Memnite')).pt == (1, 1)
    roundtrip(s)


def test_firion_equipment_copy_reduces_only_own_equip_and_next_upkeep(cards):
    s, source = setup(cards, 'Firion, Wild Rose Warrior')
    put(s, 'Firion, Wild Rose Warrior', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    equipment = put(s, 'Bonesplitter', 'hand')
    cast(s, equipment)
    settle(s)
    token = next(c for c in tokens(s) if c.name == 'Bonesplitter')
    mana(s, C=0)
    activate(s, token, ability=1, targets=[bear.id])
    settle(s)
    assert token.attached_to == bear.id and 'haste' in ch(s, bear).keywords
    made = token.id
    to_phase(s, 'upkeep', turn=2)
    settle(s)
    assert made not in s.state.cards or not s.state.cards[made].zone.endswith(':battlefield')
    roundtrip(s)


def test_duplicator_self_sacrifice_uses_last_known_and_next_end(cards):
    s, source = setup(cards, 'Esoteric Duplicator')
    source = put(s, 'Esoteric Duplicator', 'battlefield')
    activate(s, source, ability=1)
    choose(s, ['pay'])
    settle(s)
    assert source.zone == 'p1:graveyard' and not tokens(s)
    to_phase(s, 'end')
    settle(s)
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Esoteric Duplicator'
    roundtrip(s)


def test_artisan_target_player_private_exile_creates_for_them_and_late_cleanup(cards):
    s, source = setup(cards, 'Arcane Artisan')
    source = put(s, 'Arcane Artisan', 'battlefield')
    to_phase(s, 'main1', turn=4)
    original = put(s, 'Grizzly Bears', 'hand', 'p2')
    activate(s, source, targets=['p2'])
    # Its leave trigger resolves BEFORE the activated ability creates a token.
    removal = put(s, 'Unsummon', 'hand')
    cast(s, removal, targets=[source.id])
    until(s, lambda s: s.state.rules.decision is not None)
    choose(s, [original.id])
    settle(s)
    assert original.zone == 'p2:exile'
    made = tokens(s)
    assert len(made) == 1 and made[0].controller == 'p2'
    to_phase(s, 'end')
    settle(s)
    assert made[0].id not in s.state.cards or s.state.cards[made[0].id].zone == 'p2:exile'
    roundtrip(s)


def test_espers_cast_has_no_targets_then_reflexive_targets_exact_exiled_pool(cards):
    s, spell = setup(cards, 'Espers to Magicite')
    original = put(s, 'Memnite', 'graveyard', 'p2')
    put(s, 'Forest', 'graveyard', 'p3')
    cast(s, spell)
    choose(s, [original.id])
    settle(s)
    assert original.zone == 'p2:exile'
    assert spell.zone == 'p1:graveyard'
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).types == frozenset({'Artifact'})
    roundtrip(s)


def test_nahiri_loyalty_bound_copy_haste_and_next_end(cards):
    s, source = setup(cards, 'Nahiri, the Unforgiving')
    cast(s, source)
    settle(s)
    assert source.counters['loyalty'] == 5
    original = put(s, 'Memnite', 'graveyard')
    activate(s, source, ability=3, targets=[original.id])
    settle(s)
    assert original.zone == 'p1:exile'
    assert len(tokens(s)) == 1 and 'haste' in ch(s, tokens(s)[0]).keywords
    made = tokens(s)[0]
    to_phase(s, 'end')
    settle(s)
    assert made.id not in s.state.cards or s.state.cards[made.id].zone == 'p1:exile'
    roundtrip(s)


def test_echoing_one_trigger_per_attacked_player_fixed_recipient(cards):
    s, source = setup(cards, 'Echoing Assault')
    put(s, 'Echoing Assault', 'battlefield')
    a = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': a.id, 'target': 'p2'}])
    choose(s, [a.id])
    settle(s)
    assert len(tokens(s)) == 1
    token = tokens(s)[0]
    assert ch(s, token).pt == (1, 1) and token.attacking.id == 'p2'
    assert 'menace' in ch(s, token).keywords and token.tapped
    to_phase(s, 'end')
    settle(s)
    assert token.id not in s.state.cards or not s.state.cards[token.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_shredder_other_opponents_fixed_attack_and_half_life(cards):
    s, source = setup(cards, 'Shredder, Shadow Master')
    source = put(s, 'Shredder, Shadow Master', 'battlefield')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    assert len(tokens(s)) == 1
    token = tokens(s)[0]
    assert token.attacking.id == 'p3' and token.tapped and 'Legendary' not in ch(s, token).supertypes
    to_phase(s, 'end_combat')
    settle(s)
    assert s.state.players['p2'].life == 17 and s.state.players['p3'].life == 17
    assert token.id not in s.state.cards or not s.state.cards[token.id].zone.endswith(':battlefield')
    roundtrip(s)


def test_altair_memory_target_then_owner_exile_copies_choose_defender(cards):
    s, source = setup(cards, "Altaïr Ibn-La'Ahad")
    source = put(s, "Altaïr Ibn-La'Ahad", 'battlefield')
    original = put(s, 'Changeling Outcast', 'graveyard')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    choose(s, [original.id])
    choose(s, ['p3'])
    settle(s)
    assert original.zone == 'p1:exile' and original.counters['memory'] == 1
    assert len(tokens(s)) == 1 and tokens(s)[0].attacking.id == 'p3'
    made = tokens(s)[0]
    to_phase(s, 'end_combat')
    settle(s)
    assert made.id not in s.state.cards or s.state.cards[made.id].zone == 'p1:exile'
    roundtrip(s)


def test_bretagard_all_chapters_and_different_names_native_choice(cards):
    s, spell = setup(cards, 'Battle for Bretagard')
    cast(s, spell)
    settle(s)
    assert len(tokens(s)) == 1 and 'Human' in ch(s, tokens(s)[0]).subtypes
    to_phase(s, 'main1', turn=4)
    settle(s)
    assert len(tokens(s)) == 2 and any('Elf' in ch(s, c).subtypes for c in tokens(s))
    originals = [c.id for c in tokens(s)]
    to_phase(s, 'main1', turn=7)
    choose(s, originals)
    settle(s)
    assert len(tokens(s)) == 4 and spell.zone == 'p1:graveyard'
    roundtrip(s)


def test_mog_all_chapters_and_repeated_noncreature_cast_watch(cards):
    s, spell = setup(cards, 'Summon: Good King Mog XII')
    cast(s, spell)
    settle(s)
    assert len(tokens(s)) == 2 and all(ch(s, c).pt == (1, 2) and 'lifelink' in ch(s, c).keywords for c in tokens(s))
    assert {'flying', 'lifelink'} <= ch(s, spell).keywords
    to_phase(s, 'main1', turn=4)
    settle(s)
    original = tokens(s)[0]
    for _ in range(2):
        removal = put(s, 'Unsummon', 'hand')
        target = put(s, 'Memnite', 'battlefield', 'p2')
        cast(s, removal, targets=[target.id])
        choose(s, [original.id])
        settle(s)
    assert len(tokens(s)) == 4
    to_phase(s, 'main1', turn=7)
    settle(s)
    target = put(s, 'Memnite', 'battlefield', 'p2')
    removal = put(s, 'Unsummon', 'hand')
    cast(s, removal, targets=[target.id])
    choose(s, [original.id])
    settle(s)
    assert len(tokens(s)) == 5
    to_phase(s, 'main1', turn=10)
    settle(s)
    assert all(c.counters.get('+1/+1') == 2 for c in tokens(s))
    assert spell.zone == 'p1:graveyard'
    roundtrip(s)


def test_grist_back_plus_mill_black_counter_and_minus_six(cards):
    s, source = setup(cards, 'Grist, Voracious Larva // Grist, the Plague Swarm')
    source = put(s, 'Grist, Voracious Larva // Grist, the Plague Swarm', 'battlefield')
    act(s, 'p1', type='set_face', card_id=source.id, face=1)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=7)
    top(s, 'Forest')
    top(s, 'Changeling Outcast')
    activate(s, source, ability=0)
    settle(s)
    insect = tokens(s)[0]
    assert insect.counters.get('deathtouch') == 1 and ch(s, insect).colors == frozenset({'B', 'G'})
    to_phase(s, 'main1', turn=4)
    original = put(s, 'Memnite', 'graveyard')
    activate(s, source, ability=2)
    settle(s)
    assert any(c.name == 'Memnite' and ch(s, c).pt == (1, 1) and 'Artifact' in ch(s, c).types for c in tokens(s))
    assert original.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('change', ['counters', 'bounce', 'blink'])
def test_nahiri_target_rechecks_exact_source_loyalty_not_new_incarnation(cards, change):
    s, source = setup(cards, 'Nahiri, the Unforgiving')
    cast(s, source)
    settle(s)
    original = put(s, 'Grizzly Bears', 'graveyard')
    activate(s, source, ability=3, targets=[original.id])
    if change == 'counters':
        act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=2)
    else:
        if change == 'bounce':
            # Native table move preserves the source's exact last-known counters.
            act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'hand'})
        else:
            act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'exile'})
            act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'battlefield'})
            act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=1)
    settle(s)
    assert len(tokens(s)) == (0 if change == 'counters' else 1)
    assert s.state.cards[original.id].zone == ('p1:graveyard' if change == 'counters' else 'p1:exile')
    roundtrip(s)


def test_nahiri_attack_requirement_is_player_only_and_expires(cards):
    from app.game.errors import ActionError
    s, source = setup(cards, 'Nahiri, the Unforgiving')
    cast(s, source)
    settle(s)
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=4)
    activate(s, source, ability=1, targets=[bear.id], target_counts=[1])
    settle(s)
    assert 'attack_player_any' in ch(s, bear).imposed
    to_phase(s, 'declare_attackers', turn=4)
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[])
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    to_phase(s, 'main1', turn=7)
    assert 'attack_player_any' not in ch(s, bear).imposed
    # The independent discard/draw loyalty ability remains native.
    discard = put(s, 'Forest', 'hand')
    activate(s, source, ability=2)
    choose(s, [discard.id])
    settle(s)
    assert s.state.cards[discard.id].zone == 'p1:graveyard'
    roundtrip(s)


def test_firion_exact_zero_equip_cost_and_other_equipment_cost_unchanged(cards):
    s, source = setup(cards, 'Firion, Wild Rose Warrior')
    put(s, 'Firion, Wild Rose Warrior', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    equipment = put(s, 'Bonesplitter', 'hand')
    cast(s, equipment)
    settle(s)
    token = next(c for c in tokens(s) if c.name == 'Bonesplitter')
    act(s, 'p1', type='clear_mana', player='p1')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=token.id, ability=1, targets=[bear.id])
    paid = s.state.rules.payments[s.state.rules.object_id(s.state.zones['stack'][-1])]
    assert sum(paid.mana_spent.values()) == 0
    settle(s)
    mana(s, C=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=equipment.id, ability=1, targets=[bear.id])
    paid = s.state.rules.payments[s.state.rules.object_id(s.state.zones['stack'][-1])]
    assert sum(paid.mana_spent.values()) == 1
    settle(s)
    roundtrip(s)


def test_espers_reflexive_target_selection_resumes_fresh_process(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, spell = setup(cards, 'Espers to Magicite')
    original = put(s, 'Memnite', 'graveyard', 'p2')
    cast(s, spell)
    until(s, lambda s: s.state.rules.decision is not None)
    s = cold_choose(s, cards, tmp_path, [original.id])
    settle(s)
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).types == frozenset({'Artifact'})


def test_artisan_private_hand_choice_resumes_fresh_process(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, source = setup(cards, 'Arcane Artisan')
    source = put(s, 'Arcane Artisan', 'battlefield')
    to_phase(s, 'main1', turn=4)
    original = put(s, 'Grizzly Bears', 'hand', 'p2')
    activate(s, source, targets=['p2'])
    until(s, lambda s: s.state.rules.decision is not None)
    assert s.state.rules.decision.player == 'p2'
    s = cold_choose(s, cards, tmp_path, [original.id])
    settle(s)
    assert len(tokens(s)) == 1 and tokens(s)[0].controller == 'p2'


def test_haunting_replacement_batch_and_public_library_binding_resume_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose
    s, spell = setup(cards, 'Haunting Imitation')
    put(s, 'Parallel Lives', 'battlefield')
    put(s, 'Peregrin Took', 'battlefield')
    top(s, 'Grizzly Bears')
    top(s, 'Forest', 'p2')
    top(s, 'Forest', 'p3')
    cast(s, spell)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume['step'] == 'replace_order'
    s = cold_choose(s, cards, tmp_path, [d.options[0].id])
    settle(s)
    assert len(tokens(s)) in (3, 4)
    assert sum(ch(s, c).name == 'Grizzly Bears' for c in tokens(s)) == 2
    assert not any(c.revealed_to for c in s.state.cards.values() if c.zone.endswith(':library'))


def test_grist_actual_graveyard_front_entry_transforms_then_back_minus_two(cards):
    s, source = setup(cards, 'Grist, Voracious Larva // Grist, the Plague Swarm')
    source = put(s, 'Grist, Voracious Larva // Grist, the Plague Swarm', 'graveyard')
    spell = put(s, 'Reanimate', 'hand')
    cast(s, spell, targets=[source.id])
    choose(s, ['pay'])
    settle(s)
    assert s.state.cards[source.id].face == 1 and s.state.cards[source.id].counters['loyalty'] == 3
    victim = put(s, 'Liquimetal Torque', 'battlefield', 'p2')
    activate(s, source, ability=1, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == 'p2:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('black', [False, True])
def test_grist_mill_public_exile_replacement_and_no_black(cards, black):
    s, source = setup(cards, 'Grist, Voracious Larva // Grist, the Plague Swarm')
    source = put(s, 'Grist, Voracious Larva // Grist, the Plague Swarm', 'battlefield')
    act(s, 'p1', type='set_face', card_id=source.id, face=1)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='loyalty', value=3)
    put(s, 'Rest in Peace', 'battlefield')
    top(s, 'Forest')
    original = top(s, 'Changeling Outcast' if black else 'Island')
    activate(s, source, ability=0)
    settle(s)
    assert s.state.cards[original.id].zone == 'p1:exile'
    assert len(tokens(s)) == 1
    assert tokens(s)[0].counters.get('deathtouch', 0) == int(black)
    roundtrip(s)


def test_nahiri_native_compleated_life_payment_reduces_starting_loyalty(cards):
    s, source = setup(cards, 'Nahiri, the Unforgiving')
    mana(s, C=1, R=1, W=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=source.id)
    if s.state.rules.decision is not None:
        choose(s, ['life'])
    settle(s)
    assert s.state.players['p1'].life == 38
    assert s.state.cards[source.id].counters['loyalty'] == 3
    roundtrip(s)


def test_osgood_artifact_restricted_mana_and_nonhand_paradox(cards):
    s, source = setup(cards, 'Osgood, Operation Double')
    source = put(s, 'Osgood, Operation Double', 'battlefield')
    to_phase(s, 'main1', turn=4)
    act(s, 'p1', type='clear_mana', player='p1')
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=1)
    artifact = put(s, 'Bonesplitter', 'hand')
    act(s, 'p1', type='cast_spell', card_id=artifact.id)
    settle(s)
    assert s.state.cards[artifact.id].zone == 'p1:battlefield'
    spell = put(s, 'Think Twice', 'graveyard')
    cast(s, spell)
    settle(s)
    assert any('Clue' in ch(s, c).subtypes for c in tokens(s))
    roundtrip(s)


def test_red_sun_indestructible_survivor_is_not_copied(cards):
    s, spell = setup(cards, "Red Sun's Twilight")
    survivor = put(s, 'Darksteel Ingot', 'battlefield', 'p2')
    destroyed = put(s, 'Memnite', 'battlefield', 'p3')
    cast(s, spell, x_value=5, targets=[survivor.id, destroyed.id], target_counts=[2])
    settle(s)
    assert s.state.cards[survivor.id].zone == 'p2:battlefield'
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Memnite'
    roundtrip(s)
