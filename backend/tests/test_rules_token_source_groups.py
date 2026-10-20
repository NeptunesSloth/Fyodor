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
    for c in json.loads((Path(__file__).parent / "fixtures/token_source_groups_cards.json").read_text())[:10]
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/token_source_groups_cards.json").read_text())
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


@pytest.mark.parametrize('x', [0, 1, 2])
def test_doppelgang_announced_x_targets_and_token_count(cards, x):
    s, spell = setup(cards, 'Doppelgang')
    a = put(s, 'Memnite', 'battlefield')
    b = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, spell, x_value=x, targets=[a.id, b.id][:x], target_counts=[x])
    settle(s)
    assert len(tokens(s)) == x * x
    assert all(c.controller == 'p1' for c in tokens(s))
    roundtrip(s)


def test_fractured_identity_copies_last_known_clone_for_other_controllers(cards):
    s, spell = setup(cards, 'Fractured Identity')
    original = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Memnite', 'battlefield')
    to_phase(s, 'main1', turn=2)
    clone = put(s, 'Clone', 'hand', 'p2')
    mana(s, U=1, C=3, pid='p2')
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=clone.id)
    choose(s, [original.id])
    settle(s)
    to_phase(s, 'main1', turn=4)
    cast(s, spell, targets=[clone.id])
    settle(s)
    assert clone.zone == 'p2:exile'
    made = tokens(s)
    assert {c.controller for c in made} == {'p1', 'p3'}
    assert all(ch(s, c).name == 'Grizzly Bears' for c in made)
    roundtrip(s)


def test_jelly_death_five_counters_creates_delayed_two_not_copiable(cards):
    s, source = setup(cards, 'Ochre Jelly')
    cast(s, source, x_value=5)
    settle(s)
    assert source.counters['+1/+1'] == 5
    murder = put(s, 'Murder', 'hand')
    cast(s, murder, targets=[source.id])
    settle(s)
    assert not tokens(s)
    to_phase(s, 'end')
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and made[0].counters['+1/+1'] == 2
    assert ch(s, made[0]).base_pt == (0, 0)
    roundtrip(s)


def test_joo_dee_native_surveil_copy_then_new_token_can_pay_sacrifice(cards):
    s, source = setup(cards, 'Joo Dee, One of Many')
    source = put(s, 'Joo Dee, One of Many', 'battlefield')
    to_phase(s, 'main1', turn=4)
    mana(s, B=1)
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume['step'] == 'look'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    until(s, lambda s: s.state.rules.decision is not None)
    made = tokens(s)
    assert len(made) == 1
    choose(s, [made[0].id])
    settle(s)
    assert source.zone == 'p1:battlefield' and source.tapped
    assert not tokens(s)
    roundtrip(s)


def test_benthic_native_nontarget_choices_and_combined_stats(cards):
    s, spell = setup(cards, 'Benthic Anomaly')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Llanowar Elves', 'battlefield', 'p3')
    other = put(s, 'Memnite', 'battlefield', 'p2')
    cast(s, spell)
    choose(s, [bear.id])
    choose(s, [bear.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1
    assert ch(s, made[0]).pt == (3, 3)
    assert ch(s, made[0]).types == frozenset({'Creature'})
    assert ch(s, made[0]).subtypes == frozenset({'Eldrazi'})
    assert ch(s, made[0]).colors == frozenset()
    assert other.zone == 'p2:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('monarch', [True, False])
def test_court_resolves_current_monarch_and_keeps_only_upkeep_ability(cards, monarch):
    s, source = setup(cards, 'Court of Vantress')
    target = put(s, 'Liquimetal Torque', 'battlefield')
    cast(s, source)
    settle(s)
    assert s.state.table.monarch == 'p1'
    to_phase(s, 'upkeep', turn=4)
    choose(s, [target.id])
    act(s, 'p1', type='set_monarch', player='p1' if monarch else 'p2')
    choose(s, ['pay'])
    settle(s)
    if monarch:
        assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Liquimetal Torque'
        assert ch(s, source).name == 'Court of Vantress'
    else:
        assert not tokens(s) and ch(s, source).name == 'Liquimetal Torque'
        assert any('beginning of your upkeep' in a.text.lower() for a in ch(s, source).abilities)
        assert not any('become the monarch' in a.text.lower() for a in ch(s, source).abilities)
    roundtrip(s)


def test_calix_native_self_damage_optional_copy_and_once_each_turn(cards):
    s, source = setup(cards, 'Calix, Guided by Fate')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    cast(s, source)
    choose(s, [bear.id])
    settle(s)
    aura = put(s, 'Holy Strength', 'hand')
    cast(s, aura, targets=[bear.id])
    choose(s, [bear.id])
    settle(s)
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}, {'card_id': bear.id, 'target': 'p3'}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind not in ('declare_attackers','declare_blockers'))
    choose(s, [aura.id])
    choose(s, [source.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and ch(s, made[0]).name == 'Holy Strength'
    assert made[0].attached_to == source.id
    roundtrip(s)


def test_redoubled_only_this_turn_token_entries_and_next_end_sacrifice(cards):
    s, source = setup(cards, 'Redoubled Stormsinger')
    source = put(s, 'Redoubled Stormsinger', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=4)
    copy_spell = put(s, 'Cackling Counterpart', 'hand')
    cast(s, copy_spell, targets=[bear.id])
    settle(s)
    old = tokens(s)[0]
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    settle(s)
    made = [c for c in tokens(s) if c.id != old.id]
    assert len(made) == 1 and made[0].tapped and made[0].attacking
    to_phase(s, 'end', turn=4)
    settle(s)
    assert [c.id for c in tokens(s)] == [old.id]
    roundtrip(s)


def test_mirror_master_backup_grants_real_attack_ability_and_end_combat_cleanup(cards):
    s, source = setup(cards, 'Mirror-Style Master')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    to_phase(s, 'main1', turn=4)
    cast(s, source)
    choose(s, [bear.id])
    settle(s)
    assert bear.counters.get('+1/+1') == 1
    assert any('modified creature' in a.text for a in ch(s, bear).abilities)
    # The backed-up creature may attack this turn only after gaining haste;
    # it was already on the battlefield before this turn's start.
    to_phase(s, 'declare_attackers')
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': bear.id, 'target': 'p2'}])
    settle(s)
    assert len(tokens(s)) == 1 and ch(s, tokens(s)[0]).name == 'Grizzly Bears'
    assert not tokens(s)[0].counters
    to_phase(s, 'end_combat')
    settle(s)
    assert not tokens(s)
    to_phase(s, 'main1', turn=7)
    assert not any('modified creature' in a.text for a in ch(s, bear).abilities)
    roundtrip(s)


@pytest.mark.parametrize('before,copy_expected', [(5, False), (6, True)])
def test_scouring_swarm_counts_actual_land_arrival_before_sacrifice_trigger(cards, before, copy_expected):
    s, source = setup(cards, 'Scouring Swarm')
    put(s, 'Scouring Swarm', 'battlefield')
    orb = put(s, 'Zuran Orb', 'battlefield')
    lands = [c for c in s.state.cards.values() if c.owner == 'p1' and c.name == 'Forest']
    act(s, 'p1', type='move', card_ids=[c.id for c in lands[:before]], to={'player': 'p1', 'zone': 'graveyard'})
    land = lands[before]
    act(s, 'p1', type='move', card_ids=[land.id], to={'player': 'p1', 'zone': 'battlefield'})
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=orb.id, ability=0)
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and made[0].tapped
    assert ch(s, made[0]).name == ('Scouring Swarm' if copy_expected else 'Insect')
    assert land.zone == 'p1:graveyard'
    roundtrip(s)


def test_identity_room_lki_tokens_both_doors_locked_then_native_unlock(cards):
    s, spell = setup(cards, 'Fractured Identity')
    room = put(s, 'Bottomless Pool // Locker Room', 'battlefield', 'p2')
    to_phase(s, 'main1', turn=2)
    mana(s, pid='p2', U=1, C=4)
    wait_priority(s, 'p2')
    act(s, 'p2', type='unlock_door', card_id=room.id, door=2)
    assert s.state.rules.unlocked[s.state.rules.object_id(room.id)] == [2]
    to_phase(s, 'main1', turn=4)
    cast(s, spell, targets=[room.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 2
    assert {c.controller for c in made} == {'p1', 'p3'}
    for token in made:
        assert 'Room' in ch(s, token).subtypes
        assert not s.state.rules.unlocked.get(s.state.rules.object_id(token.id))
        from app.rules import scripts
        assert not scripts.definitions(ch(s, token))
    own = next(c for c in made if c.controller == 'p1')
    mana(s, U=1, C=4)
    wait_priority(s, 'p1')
    act(s, 'p1', type='unlock_door', card_id=own.id, door=2)
    assert s.state.rules.unlocked[s.state.rules.object_id(own.id)] == [2]
    assert any('combat damage' in a.text for a in ch(s, own).abilities)
    roundtrip(s)


def test_identity_stolen_aura_uses_departure_controller_and_native_hosts_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, spell = setup(cards, 'Fractured Identity')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p3')
    aura = put(s, 'Holy Strength', 'hand')
    cast(s, aura, targets=[bear.id])
    settle(s)
    cast(s, spell, targets=[aura.id])
    act(s, 'p1', type='set_controller', card_ids=[aura.id], player='p2')
    until(s, lambda s: s.state.rules.decision is not None)
    while 'Aura token' not in s.state.rules.decision.prompt:
        d = s.state.rules.decision
        s = cold_choose(s, cards, tmp_path, [d.options[0].id])
        until(s, lambda s: s.state.rules.decision is not None, limit=20)
    s = cold_choose(s, cards, tmp_path, [bear.id])
    assert s.state.rules.decision is not None
    s = cold_choose(s, cards, tmp_path, [elf.id])
    settle(s)
    made = tokens(s)
    assert {c.controller for c in made} == {'p1', 'p3'}
    assert {c.attached_to for c in made} == {bear.id, elf.id}
    assert aura.zone == 'p1:exile'
    roundtrip(s)


def test_benthic_choices_resume_cold_and_explicit_creature_drops_artifact(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, spell = setup(cards, 'Benthic Anomaly')
    memnite = put(s, 'Memnite', 'battlefield', 'p2')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    elf = put(s, 'Llanowar Elves', 'battlefield', 'p3')
    cast(s, spell)
    until(s, lambda s: s.state.rules.decision is not None)
    s = cold_choose(s, cards, tmp_path, [memnite.id])
    assert s.state.rules.decision.resume['step'] == 'select_copy_originals'
    s = cold_choose(s, cards, tmp_path, [memnite.id])
    settle(s)
    made = tokens(s)
    assert len(made) == 1 and ch(s, made[0]).pt == (2, 2)
    assert ch(s, made[0]).types == frozenset({'Creature'})
    assert ch(s, made[0]).subtypes == frozenset({'Eldrazi'})
    assert bear.zone == 'p2:battlefield' and elf.zone == 'p3:battlefield'
    roundtrip(s)


def test_doppelgang_illegal_target_preserves_announced_x_and_other_copies(cards):
    s, spell = setup(cards, 'Doppelgang')
    a = put(s, 'Memnite', 'battlefield')
    b = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    cast(s, spell, x_value=2, targets=[a.id, b.id], target_counts=[2])
    bounce = put(s, 'Unsummon', 'hand')
    cast(s, bounce, targets=[a.id])
    settle(s)
    assert a.zone == 'p1:hand'
    assert len(tokens(s)) == 2 and all(ch(s, c).name == 'Grizzly Bears' for c in tokens(s))
    roundtrip(s)


@pytest.mark.parametrize('n,expected', [(1, 0), (2, 1), (5, 2)])
def test_jelly_split_threshold_floor_and_original_departure(cards, n, expected):
    s, source = setup(cards, 'Ochre Jelly')
    cast(s, source, x_value=n)
    settle(s)
    murder = put(s, 'Murder', 'hand')
    cast(s, murder, targets=[source.id])
    # Resolve the death and leave the delayed Split waiting for the end step.
    settle(s)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    to_phase(s, 'end')
    settle(s)
    assert len(tokens(s)) == bool(expected)
    if expected:
        assert tokens(s)[0].counters['+1/+1'] == expected
    roundtrip(s)


def test_jelly_entry_counters_are_replaced_after_immutable_death_count_halved(cards):
    s, source = setup(cards, 'Ochre Jelly')
    put(s, 'Doubling Season', 'battlefield')
    cast(s, source, x_value=5)
    settle(s)
    assert source.counters['+1/+1'] == 10
    murder = put(s, 'Murder', 'hand')
    cast(s, murder, targets=[source.id])
    settle(s)
    to_phase(s, 'end')
    settle(s)
    assert len(tokens(s)) == 2
    assert all(c.counters['+1/+1'] == 10 for c in tokens(s))
    roundtrip(s)


def test_jelly_created_token_split_uses_its_own_counters_next_end_step(cards):
    s, source = setup(cards, 'Ochre Jelly')
    cast(s, source, x_value=5)
    settle(s)
    murder = put(s, 'Murder', 'hand')
    cast(s, murder, targets=[source.id])
    settle(s)
    to_phase(s, 'end')
    settle(s)
    first = tokens(s)[0]
    assert first.counters['+1/+1'] == 2
    murder = put(s, 'Murder', 'hand')
    cast(s, murder, targets=[first.id])
    settle(s)
    assert not tokens(s)
    to_phase(s, 'end', turn=2)
    settle(s)
    assert len(tokens(s)) == 1 and tokens(s)[0].counters['+1/+1'] == 1
    assert tokens(s)[0].id != first.id
    roundtrip(s)


def test_benthic_native_token_replacement_order_resumes_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, spell = setup(cards, 'Benthic Anomaly')
    bear = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Llanowar Elves', 'battlefield', 'p3')
    put(s, 'Parallel Lives', 'battlefield')
    put(s, 'Peregrin Took', 'battlefield')
    cast(s, spell)
    choose(s, [bear.id])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume['step'] == 'replace_order'
    s = cold_choose(s, cards, tmp_path, [d.options[0].id])
    settle(s)
    made = [c for c in tokens(s) if ch(s, c).name == 'Grizzly Bears']
    assert len(made) == 2 and all(ch(s, c).pt == (3, 3) for c in made)
    assert all(ch(s, c).subtypes == frozenset({'Eldrazi'}) for c in made)
    assert len(tokens(s)) in (3, 4)
