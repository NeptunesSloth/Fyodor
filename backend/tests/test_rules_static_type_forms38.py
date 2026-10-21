"""Canonical continuous type/color/ability changes with actual casting and native layers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/static_type_forms38_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="bd35", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [
        c["name"]
        for c in json.loads((Path(__file__).parent / "fixtures/static_type_forms38_cards.json").read_text())
    ]
    return table(cards, names, names, names)


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize(
    "aura,expected",
    [
        ("One with the Stars", {"Enchantment"}),
        ("Swift Reconfiguration", {"Artifact"}),
    ],
)
def test_actual_aura_sets_card_types_retains_ability_and_supertypes(cards, aura, expected):
    s = setup(cards)
    elf = put(s, "Llanowar Elves", "battlefield")
    start(s)
    cast(s, aura, [elf.id], target_counts=[1])
    current = ch(s, elf)
    assert (
        current.types == expected
        and current.colors == {"G"}
        and not current.subtypes - ({"Vehicle"} if aura == "Swift Reconfiguration" else set())
    )
    assert any("Add {G}" in a.text for a in current.abilities)
    assert current.pt is None
    roundtrip(s)


def test_swift_granted_real_crew_five_returns_creature_and_preserves_base_pt(cards):
    from tests.game_helpers import act

    s = setup(cards)
    elf = put(s, "Llanowar Elves", "battlefield")
    pilot = put(s, "Colossal Dreadmaw", "battlefield")
    start(s)
    cast(s, "Swift Reconfiguration", [elf.id], target_counts=[1])
    crew = next(a for a in ch(s, elf).abilities if a.text.startswith("Crew 5"))
    act(s, "p1", type="activate_ability", card_id=elf.id, ability=crew.index, crew=[pilot.id])
    settle(s)
    assert ch(s, elf).types == {"Artifact", "Creature"} and ch(s, elf).pt == (1, 1)
    assert s.state.cards[pilot.id].tapped
    roundtrip(s)


@pytest.mark.parametrize("aura", ["Siege Modification", "Aerial Modification"])
def test_vehicle_aura_native_dynamic_group_and_ordinary_creature(cards, aura):
    s = setup(cards)
    skiff = put(s, "Sky Skiff", "battlefield")
    start(s)
    cast(s, aura, [skiff.id], target_counts=[1])
    assert ch(s, skiff).types == {"Artifact", "Creature"} and ch(s, skiff).pt == (
        (5, 3) if aura == "Siege Modification" else (4, 5)
    )
    assert (
        "first strike" in ch(s, skiff).keywords
        if aura == "Siege Modification"
        else "flying" in ch(s, skiff).keywords
    )
    roundtrip(s)


@pytest.mark.parametrize("target", ["Sol Ring", "Humility"])
def test_puppet_crafting_native_union_target_retains_original_type(cards, target):
    s = setup(cards)
    host = put(s, target, "battlefield")
    start(s)
    cast(s, "Puppet Crafting", [host.id], target_counts=[1])
    current = ch(s, host)
    assert (
        "Creature" in current.types
        and ("Artifact" if target == "Sol Ring" else "Enchantment") in current.types
    )
    assert current.pt == (5, 5) and current.subtypes == {"Construct"}
    roundtrip(s)


def test_dralnu_global_goblin_type_and_black_color_set(cards):
    s = setup(cards)
    own = put(s, "Mogg Fanatic", "battlefield")
    other = put(s, "Goblin Arsonist", "battlefield", pid="p2")
    bear = put(s, "Grizzly Bears", "battlefield")
    start(s)
    cast(s, "Dralnu's Crusade")
    for goblin in [own, other]:
        current = ch(s, goblin)
        assert current.colors == {"B"} and {"Goblin", "Zombie"} <= current.subtypes and current.pt == (2, 2)
    assert ch(s, bear).colors == {"G"} and ch(s, bear).subtypes == {"Bear"}
    roundtrip(s)


def test_dune_changer_controlled_battlefield_vs_owned_offbattlefield(cards):
    from tests.game_helpers import act

    s = setup(cards)
    own = put(s, "Forest", "battlefield")
    owned_gy = put(s, "Mountain", "graveyard")
    enemy = put(s, "Island", "battlefield", pid="p2")
    start(s)
    cast(s, "Dune Chanter")
    assert ch(s, own).subtypes == {"Forest", "Desert"}
    assert ch(s, owned_gy).subtypes == {"Mountain", "Desert"}
    assert ch(s, enemy).subtypes == {"Island"}
    act(s, "p2", type="set_controller", card_ids=[enemy.id], player="p1")
    assert ch(s, enemy).subtypes == {"Island", "Desert"}
    act(s, "p1", type="set_controller", card_ids=[own.id], player="p2")
    assert ch(s, own).subtypes == {"Forest"}
    roundtrip(s)


def test_one_stars_noncreature_marwyn_mana_ability_uses_zero_power(cards):
    from tests.game_helpers import act, mana_pool

    s = setup(cards)
    marwyn = put(s, "Marwyn, the Nurturer", "battlefield")
    start(s)
    cast(s, "One with the Stars", [marwyn.id], target_counts=[1])
    act(s, "p1", type="clear_mana", player="p1")
    ability = next(a for a in ch(s, marwyn).abilities if "Add an amount" in a.text)
    act(s, "p1", type="activate_ability", card_id=marwyn.id, ability=ability.index)
    assert mana_pool(s, "p1") == {}
    assert s.state.cards[marwyn.id].tapped
    roundtrip(s)


def test_mephidross_grants_actual_damage_trigger_to_each_own_creature(cards):
    from tests.game_helpers import act

    s = setup(cards)
    goblin = put(s, "Mogg Fanatic", "battlefield")
    own = put(s, "Grizzly Bears", "battlefield")
    enemy = put(s, "Memnite", "battlefield", pid="p2")
    start(s)
    vampire = cast(s, "Mephidross Vampire")
    assert "Vampire" in ch(s, own).subtypes and "Vampire" not in ch(s, enemy).subtypes
    # Actual damage from a granted native activated ability; opponent spell damage
    # is deliberately not a qualifying source.
    from tests.test_rules_defender_relative36 import attack

    attack(s, own)
    from tests.test_rules_wave30m_durations import to_phase

    to_phase(s, "declare_blockers", turn=4)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": enemy.id, "attacker_id": own.id}])
    to_phase(s, "combat_damage", turn=4)
    settle(s)
    assert s.state.cards[own.id].zone == "p1:battlefield"
    assert s.state.cards[own.id].counters["+1/+1"] == 1 and ch(s, own).pt == (3, 3)
    assert not s.state.cards[goblin.id].counters
    assert "Vampire" in ch(s, vampire).subtypes
    roundtrip(s)


def test_captains_hook_actual_equip_pirate_menace_and_unattach_destroy(cards):
    from tests.game_helpers import act

    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    other = put(s, "Runeclaw Bear", "battlefield")
    start(s)
    hook = cast(s, "Captain's Hook")
    equip = next(a for a in ch(s, hook).abilities if a.text.startswith("Equip "))
    act(s, "p1", type="activate_ability", card_id=hook.id, ability=equip.index, targets=[bear.id])
    settle(s)
    assert ch(s, bear).subtypes == {"Bear", "Pirate"} and ch(s, bear).pt == (4, 2)
    assert "menace" in ch(s, bear).keywords
    act(s, "p1", type="activate_ability", card_id=hook.id, ability=equip.index, targets=[other.id])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    assert "Pirate" in ch(s, other).subtypes
    roundtrip(s)


def test_secret_arcade_actual_left_door_only_battlefield_and_permanent_spells(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    s = setup(cards)
    artifact = put(s, "Sol Ring", "battlefield")
    grave = put(s, "Memnite", "graveyard")
    land = put(s, "Forest", "battlefield")
    enemy = put(s, "Runeclaw Bear", "battlefield", pid="p2")
    start(s)
    room = cast(s, "Secret Arcade // Dusty Parlor", face=0)
    assert "Enchantment" in ch(s, artifact).types
    assert "Enchantment" not in ch(s, grave).types and "Enchantment" not in ch(s, land).types
    assert "Enchantment" not in ch(s, enemy).types
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="set_prefs", hold_priority=True, response="on")
    spell = put(s, "Grizzly Bears", "hand")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    assert s.state.cards[spell.id].zone == "stack" and "Enchantment" in ch(s, spell).types
    settle(s)
    assert s.state.cards[spell.id].zone == "p1:battlefield" and "Enchantment" in ch(s, spell).types
    assert room.id in s.state.cards
    roundtrip(s)


def test_bello_actual_turn_bound_animation_keywords_combat_draw_and_humility(cards):
    from tests.test_rules_defender_relative36 import attack
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    artifact = put(s, "Panharmonicon", "battlefield")
    small = put(s, "Sol Ring", "battlefield")
    enemy = put(s, "Doubling Season", "battlefield", pid="p2")
    start(s)
    bello = cast(s, "Bello, Bard of the Brambles")
    assert ch(s, artifact).types == {"Artifact", "Creature"} and ch(s, artifact).pt == (4, 4)
    assert {"indestructible", "haste"} <= ch(s, artifact).keywords
    assert ch(s, small).types == {"Artifact"} and ch(s, enemy).types == {"Enchantment"}
    before = len(s.state.zones["p1:hand"])
    attack(s, artifact)
    to_phase(s, "combat_damage", turn=4)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before + 1
    to_phase(s, "main1", turn=5)
    settle(s)
    assert ch(s, artifact).types == {"Artifact"}
    assert ch(s, bello).types == {"Creature"}
    roundtrip(s)


def test_actual_zendikar_defeat_casts_back_as_creature_land_with_mana(cards):
    from tests.game_helpers import act, mana_pool

    s = setup(cards)
    start(s)
    battle = cast(s, "Invasion of Zendikar // Awakened Skyclave")
    assert s.state.rules.decision
    pick(s, ["p2"])
    settle(s)
    # Native entry search chooses zero of its optional up-to-two basics.
    if s.state.rules.decision:
        pick(s, [])
        settle(s)
    cast(s, "Lightning Bolt", [battle.id], target_counts=[1])
    assert s.state.rules.decision and any(o.id == "yes@1" for o in s.state.rules.decision.options)
    pick(s, ["yes@1"])
    settle(s)
    current = ch(s, battle)
    assert (
        current.name == "Awakened Skyclave" and current.types == {"Creature", "Land"} and current.pt == (4, 4)
    )
    assert {"vigilance", "haste"} <= current.keywords
    act(s, "p1", type="clear_mana", player="p1")
    ability = next(a for a in current.abilities if "Add one mana" in a.text)
    act(s, "p1", type="activate_ability", card_id=battle.id, ability=ability.index, mana_choice="G")
    if s.state.rules.decision:
        pick(s, ["G"])
        settle(s)
    assert mana_pool(s, "p1") == {"G": 1}
    roundtrip(s)


def test_swift_vehicle_keeps_both_crews_and_underlying_printed_pt(cards):
    from tests.game_helpers import act

    s = setup(cards)
    skiff = put(s, "Sky Skiff", "battlefield")
    pilot = put(s, "Llanowar Elves", "battlefield")
    start(s)
    cast(s, "Swift Reconfiguration", [skiff.id], target_counts=[1])
    current = ch(s, skiff)
    assert current.pt is None and {
        a.text.split(" (")[0] for a in current.abilities if a.text.startswith("Crew")
    } == {"Crew 1", "Crew 5"}
    crew = next(a for a in current.abilities if a.text.startswith("Crew 1"))
    act(s, "p1", type="activate_ability", card_id=skiff.id, ability=crew.index, crew=[pilot.id])
    settle(s)
    assert ch(s, skiff).pt == (2, 3) and ch(s, skiff).types == {"Artifact", "Creature"}
    roundtrip(s)


def test_cr2083_preserves_offbattlefield_vehicle_printed_pt(cards):
    s = setup(cards)
    skiff = put(s, "Sky Skiff", "graveyard")
    assert ch(s, skiff).pt == (2, 3)
    start(s)
    cast(s, "One with the Stars", [put(s, "Grizzly Bears", "battlefield").id], target_counts=[1])
    assert ch(s, skiff).pt == (2, 3)
    roundtrip(s)


@pytest.mark.parametrize("humility_first", [True, False])
def test_bello_effect_continues_through_layer6_ability_loss(cards, humility_first):
    s = setup(cards)
    artifact = put(s, "Panharmonicon", "battlefield")
    start(s)
    if humility_first:
        humility = cast(s, "Humility")
    bello = cast(s, "Bello, Bard of the Brambles")
    if not humility_first:
        humility = cast(s, "Humility")
    assert ch(s, artifact).types == {"Artifact", "Creature"}
    assert ch(s, artifact).pt == ((4, 4) if humility_first else (1, 1))
    assert not ch(s, bello).abilities
    assert s.state.cards[humility.id].zone == "p1:battlefield"
    roundtrip(s)


def test_siege_aura_stops_animating_host_when_vehicle_type_is_lost(cards):
    s = setup(cards)
    skiff = put(s, "Sky Skiff", "battlefield")
    start(s)
    siege = cast(s, "Siege Modification", [skiff.id], target_counts=[1])
    assert "Creature" in ch(s, skiff).types
    cast(s, "One with the Stars", [skiff.id], target_counts=[1])
    assert ch(s, skiff).types == {"Enchantment"} and ch(s, skiff).pt is None
    assert s.state.cards[siege.id].zone == "p1:graveyard"
    roundtrip(s)


def test_vehicle_aura_source_leaving_removes_uncrewed_attacker_from_combat(cards):
    from tests.test_rules_defender_relative36 import attack

    s = setup(cards)
    skiff = put(s, "Sky Skiff", "battlefield")
    start(s)
    aura = cast(s, "Aerial Modification", [skiff.id], target_counts=[1])
    attack(s, skiff)
    assert s.state.cards[skiff.id].is_attacking
    cast(s, "Disenchant", [aura.id], target_counts=[1])
    assert ch(s, skiff).types == {"Artifact"} and not s.state.cards[skiff.id].is_attacking
    roundtrip(s)


def test_clone_copies_crewed_swift_host_without_external_vehicle_or_crew(cards):
    from tests.game_helpers import act

    s = setup(cards)
    elf = put(s, "Llanowar Elves", "battlefield")
    pilot = put(s, "Colossal Dreadmaw", "battlefield")
    start(s)
    cast(s, "Swift Reconfiguration", [elf.id], target_counts=[1])
    crew = next(a for a in ch(s, elf).abilities if a.text.startswith("Crew 5"))
    act(s, "p1", type="activate_ability", card_id=elf.id, ability=crew.index, crew=[pilot.id])
    settle(s)
    clone = cast(s, "Clone")
    pick(s, [elf.id])
    settle(s)
    current = ch(s, clone)
    assert current.name == "Llanowar Elves" and current.types == {"Creature"}
    assert current.subtypes == {"Elf", "Druid"} and current.pt == (1, 1)
    assert not any(a.text.startswith("Crew") for a in current.abilities)
    roundtrip(s)


def test_swift_retains_actual_animated_planeswalkers_loyalty_activation(cards):
    from tests.game_helpers import act
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    start(s)
    gideon = cast(s, "Gideon Jura")
    act(s, "p1", type="activate_ability", card_id=gideon.id, ability=2)
    settle(s)
    assert "Creature" in ch(s, gideon).types
    cast(s, "Swift Reconfiguration", [gideon.id], target_counts=[1])
    assert ch(s, gideon).types == {"Artifact"} and ch(s, gideon).supertypes == {"Legendary"}
    assert ch(s, gideon).pt is None
    to_phase(s, "main1", turn=7)
    settle(s)
    before = s.state.cards[gideon.id].counters["loyalty"]
    act(s, "p1", type="activate_ability", card_id=gideon.id, ability=0, targets=["p2"], target_counts=[1])
    settle(s)
    assert s.state.cards[gideon.id].counters["loyalty"] == before + 2
    assert ch(s, gideon).types == {"Artifact"}
    roundtrip(s)


def test_bello_equipment_also_non_aura_enchantment_qualifies_other_branch(cards):
    s = setup(cards)
    start(s)
    equipment = cast(s, "Sword of Kaldra")
    cast(s, "Bello, Bard of the Brambles")
    assert ch(s, equipment).types == {"Artifact"}
    cast(s, "Enchanted Evening")
    assert ch(s, equipment).types == {"Artifact", "Enchantment", "Creature"}
    assert ch(s, equipment).pt == (4, 4)
    roundtrip(s)


def test_secret_arcade_right_door_does_not_grant_left_until_actual_unlock(cards):
    from tests.game_helpers import act
    from tests.test_rules_bandmate_references import mana

    s = setup(cards)
    artifact = put(s, "Sol Ring", "battlefield")
    start(s)
    room = cast(s, "Secret Arcade // Dusty Parlor", face=1)
    assert ch(s, artifact).types == {"Artifact"}
    mana(s, W=1, C=6)
    act(s, "p1", type="unlock_door", card_id=room.id, door=1)
    settle(s)
    assert ch(s, artifact).types == {"Artifact", "Enchantment"}
    roundtrip(s)


def test_native_defeated_battle_saved_cast_back_resumes_cold_with_land_type(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    start(s)
    battle = cast(s, "Invasion of Zendikar // Awakened Skyclave")
    pick(s, ["p2"])
    settle(s)
    if s.state.rules.decision:
        pick(s, [])
        settle(s)
    cast(s, "Lightning Bolt", [battle.id], target_counts=[1])
    assert s.state.rules.decision and s.state.cards[battle.id].zone == "p1:exile"
    saved = tmp_path / "static38.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_designations import pick,settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
pick(s,['yes@1']);settle(s)
c=s.state.cards[sys.argv[3]]
assert c.zone=='p1:battlefield'
ch=Plan(s.state,'p1',repo,None).ch(c)
assert ch.types=={'Creature','Land'} and ch.name=='Awakened Skyclave' and ch.pt==(4,4)
roundtrip(s)
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), battle.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
