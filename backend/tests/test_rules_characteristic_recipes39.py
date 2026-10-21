"""Canonical continuous type/color/ability changes with actual casting and native layers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import cast, start
from tests.test_rules_designations import pick, put, roundtrip, settle
from tests.test_rules_shared_damage_choices import table


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/characteristic_recipes39_cards.json").read_text())
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
        for c in json.loads(
            (Path(__file__).parent / "fixtures/characteristic_recipes39_cards.json").read_text()
        )
    ]
    return table(cards, names, names, names)


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


NAMES = [
    "Coercive Recruiter",
    "Crawling Barrens",
    "Vronos, Masked Inquisitor",
    "Werewolf Pack Leader",
    "Traitor's Clutch",
    "Defiling Tears",
    "Phantasmal Form",
    "Jump Scare",
    "Fendeep Summoner",
    "Anthousa, Setessan Hero",
    "Restless Spire",
    "Genju of the Fields",
    "Nightcreep",
    "Flayer of Loyalties",
    "Ageless Sentinels",
    "Haunted Plate Mail",
    "Dancing Sword",
    "Kaito, Bane of Nightmares",
    "Warden of the Wall",
]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(
    "spell,pt,colors,keyword",
    [
        ("Traitor's Clutch", (3, 2), {"B"}, "shadow"),
        ("Defiling Tears", (3, 1), {"B"}, None),
        ("Jump Scare", (4, 4), {"G"}, "flying"),
        ("Phantasmal Form", (3, 3), {"G", "U"}, "flying"),
    ],
)
def test_actual_targeted_recipes(cards, spell, pt, colors, keyword):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    start(s)
    cast(s, spell, [bear.id], target_counts=[1])
    current = ch(s, bear)
    assert current.pt == pt and current.colors == colors
    if keyword:
        assert keyword in current.keywords
    if spell == "Jump Scare":
        assert current.types == {"Creature", "Enchantment"} and {"Bear", "Horror"} <= current.subtypes
    if spell == "Phantasmal Form":
        assert {"Bear", "Illusion"} <= current.subtypes
    if spell == "Defiling Tears":
        assert any("Regenerate" in a.text for a in current.abilities)
    roundtrip(s)


def activate(s, c, text, **kw):
    a = next(a for a in ch(s, c).abilities if text in a.text)
    mana(s, W=10, U=10, B=10, R=10, G=10, C=20)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=a.index, **kw)
    settle(s)


def test_werewolf_removes_only_human_and_respects_counters(cards):
    s = setup(cards)
    wolf = put(s, "Werewolf Pack Leader", "battlefield")
    start(s)
    activate(s, wolf, "base power")
    assert (
        ch(s, wolf).pt == (5, 3)
        and "Human" not in ch(s, wolf).subtypes
        and "Werewolf" in ch(s, wolf).subtypes
        and "trample" in ch(s, wolf).keywords
    )
    roundtrip(s)


def test_haunted_plate_mail_retains_artifact_removes_equipment(cards):
    s = setup(cards)
    mail = put(s, "Haunted Plate Mail", "battlefield")
    start(s)
    activate(s, mail, "no longer an Equipment")
    assert (
        ch(s, mail).pt == (4, 4)
        and ch(s, mail).types == {"Artifact", "Creature"}
        and ch(s, mail).subtypes == {"Spirit"}
    )
    roundtrip(s)


def test_kaito_safe_own_turn_form_from_actual_cast(cards):
    s = setup(cards)
    start(s)
    kaito = cast(s, "Kaito, Bane of Nightmares")
    assert (
        ch(s, kaito).types == {"Creature"}
        and ch(s, kaito).pt == (3, 4)
        and ch(s, kaito).subtypes == {"Ninja"}
        and "hexproof" in ch(s, kaito).keywords
    )
    roundtrip(s)


@pytest.mark.parametrize("accept", [False, True])
def test_crawling_barrens_counters_before_independent_optional_animation(cards, accept):
    s = setup(cards)
    land = put(s, "Crawling Barrens", "battlefield")
    start(s)
    activate(s, land, "Put two")
    assert s.state.cards[land.id].counters.get("+1/+1") == 2
    d = s.state.rules.decision
    assert d
    pick(s, [next(o.id for o in d.options if ("Yes" in o.label) == accept)])
    settle(s)
    assert ("Creature" in ch(s, land).types) == accept
    if accept:
        assert ch(s, land).pt == (2, 2) and "Land" in ch(s, land).types
    roundtrip(s)


def test_fendeep_animates_two_swamps_retains_mana(cards):
    s = setup(cards)
    source = put(s, "Fendeep Summoner", "battlefield")
    a = put(s, "Swamp", "battlefield")
    b = put(s, "Swamp", "battlefield", pid="p2")
    start(s)
    activate(s, source, "Up to two", targets=[a.id, b.id], target_counts=[2])
    for land in [a, b]:
        assert (
            ch(s, land).pt == (3, 5)
            and {"Land", "Creature"} <= ch(s, land).types
            and {"Swamp", "Treefolk", "Warrior"} <= ch(s, land).subtypes
        )
        assert any("Add {B}" in x.text for x in ch(s, land).abilities)
    roundtrip(s)


def test_restless_spire_animates_with_controller_relative_first_strike(cards):
    s = setup(cards)
    land = put(s, "Restless Spire", "battlefield")
    start(s)
    activate(s, land, "Elemental creature")
    assert (
        ch(s, land).pt == (2, 1)
        and ch(s, land).colors == {"U", "R"}
        and "Land" in ch(s, land).types
        and "first strike" in ch(s, land).keywords
    )
    roundtrip(s)


def test_nightcreep_locks_current_sets_and_land_rules_text(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    tower = put(s, "Command Tower", "battlefield")
    start(s)
    cast(s, "Nightcreep")
    assert ch(s, bear).colors == {"B"} and ch(s, tower).subtypes == {"Swamp"}
    assert any("Add {B}" in a.text for a in ch(s, tower).abilities)
    new = put(s, "Forest", "battlefield")
    assert ch(s, new).subtypes == {"Forest"}
    roundtrip(s)


def test_coercive_recruiter_native_enter_target_control_and_pirate(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    cast(s, "Coercive Recruiter")
    d = s.state.rules.decision
    assert d and any(o.id == bear.id for o in d.options)
    pick(s, [bear.id])
    settle(s)
    assert (
        s.state.cards[bear.id].controller == "p1"
        and "Pirate" in ch(s, bear).subtypes
        and "haste" in ch(s, bear).keywords
    )
    roundtrip(s)


def test_genju_actual_aura_activation_targets_host_not_source(cards):
    s = setup(cards)
    land = put(s, "Plains", "battlefield")
    start(s)
    aura = cast(s, "Genju of the Fields", [land.id], target_counts=[1])
    activate(s, aura, "2/5 white Spirit")
    assert (
        ch(s, land).pt == (2, 5)
        and ch(s, land).colors == {"W"}
        and {"Land", "Creature"} <= ch(s, land).types
        and "Spirit" in ch(s, land).subtypes
    )
    assert "Creature" not in ch(s, aura).types
    assert any(
        "gains that much life" in a.text or "gain that much life" in a.text for a in ch(s, land).abilities
    ), [a.text for a in ch(s, land).abilities]
    roundtrip(s)


def test_warden_of_wall_current_turn_static(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    warden = put(s, "Warden of the Wall", "battlefield")
    start(s)
    assert ch(s, warden).types == {"Artifact"} and ch(s, warden).pt is None
    to_phase(s, "main1", turn=5)
    assert (
        ch(s, warden).types == {"Artifact", "Creature"}
        and ch(s, warden).pt == (2, 3)
        and "flying" in ch(s, warden).keywords
    )
    roundtrip(s)


def test_vronos_permanent_construct_native_loyalty_activation(cards):
    s = setup(cards)
    ring = put(s, "Sol Ring", "battlefield")
    start(s)
    vr = cast(s, "Vronos, Masked Inquisitor")
    act(s, "p1", type="counter", card_ids=[vr.id], kind="loyalty", delta=2)
    activate(s, vr, "9/9 Construct", targets=[ring.id], target_counts=[1])
    assert (
        ch(s, ring).pt == (9, 9)
        and {"Artifact", "Creature"} <= ch(s, ring).types
        and {"vigilance", "indestructible"} <= ch(s, ring).keywords
    )
    assert any("can't be blocked" in a.text for a in ch(s, ring).abilities)
    roundtrip(s)


def test_flayer_cast_trigger_actual_target(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield", pid="p2")
    start(s)
    cast(s, "Flayer of Loyalties")
    pick(s, [bear.id])
    settle(s)
    assert (
        s.state.cards[bear.id].controller == "p1"
        and ch(s, bear).pt == (10, 10)
        and {"trample", "haste", "annihilator"} <= ch(s, bear).keywords
    )
    roundtrip(s)


def test_anthousa_heroic_native_up_to_three_land_binding(cards):
    s = setup(cards)
    hero = put(s, "Anthousa, Setessan Hero", "battlefield")
    land = put(s, "Forest", "battlefield")
    start(s)
    cast(s, "Giant Growth", [hero.id], target_counts=[1])
    pick(s, [land.id])
    settle(s)
    assert (
        ch(s, land).pt == (2, 2)
        and {"Land", "Creature"} <= ch(s, land).types
        and "Warrior" in ch(s, land).subtypes
    )
    roundtrip(s)


@pytest.mark.parametrize("accept", [False, True])
def test_dancing_sword_actual_equipped_creature_dies(cards, accept):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    sword = put(s, "Dancing Sword", "battlefield")
    start(s)
    activate(s, sword, "Equip {1}", targets=[bear.id], target_counts=[1])
    cast(s, "Murder", [bear.id], target_counts=[1])
    d = s.state.rules.decision
    assert d
    pick(s, [next(o.id for o in d.options if ("Yes" in o.label) == accept)])
    settle(s)
    assert ("Creature" in ch(s, sword).types) == accept
    if accept:
        assert (
            ch(s, sword).pt == (2, 1)
            and ch(s, sword).subtypes == {"Construct"}
            and "flying" in ch(s, sword).keywords
        )
    else:
        assert "Equipment" in ch(s, sword).subtypes
    roundtrip(s)


def test_ageless_sentinels_block_trigger_permanently_loses_defender(cards):
    from tests.test_rules_wave30m_durations import to_phase
    from tests.test_rules_wave30p_combat import attack

    s = setup(cards)
    sentinel = put(s, "Ageless Sentinels", "battlefield", pid="p2")
    bear = put(s, "Grizzly Bears", "battlefield")
    start(s)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (bear, "p2"), pid="p1")
    to_phase(s, "declare_blockers", turn=4)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": sentinel.id, "attacker_id": bear.id}])
    settle(s)
    assert (
        ch(s, sentinel).subtypes == {"Bird", "Giant"}
        and "defender" not in ch(s, sentinel).keywords
        and "flying" in ch(s, sentinel).keywords
    )
    roundtrip(s)


def test_phantasmal_form_zero_targets_still_draws(cards):
    s = setup(cards)
    start(s)
    before = len(s.state.zones.get("p1:hand", []))
    cast(s, "Phantasmal Form", [], target_counts=[0])
    assert len(s.state.zones.get("p1:hand", [])) == before + 1
    roundtrip(s)


def test_crawling_barrens_saved_optional_choice_cold(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    land = put(s, "Crawling Barrens", "battlefield")
    start(s)
    activate(s, land, "Put two")
    saved = tmp_path / "recipes39.json"
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
d=s.state.rules.decision
pick(s,[next(o.id for o in d.options if 'Yes' in o.label)]);settle(s)
c=s.state.cards[sys.argv[3]]
ch=Plan(s.state,'p1',repo,None).ch(c)
assert ch.pt==(2,2) and {'Creature','Land'}<=ch.types and c.counters['+1/+1']==2
roundtrip(s);repo.close()
"""
    r = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), land.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("wipe_first", [False, True])
def test_spire_resolved_quoted_static_obeys_ability_wipe_timestamp(cards, wipe_first):
    s = setup(cards)
    land = put(s, "Restless Spire", "battlefield")
    start(s)
    if wipe_first:
        cast(s, "Humility")
    activate(s, land, "Elemental creature")
    if not wipe_first:
        cast(s, "Humility")
    assert ("first strike" in ch(s, land).keywords) == wipe_first
    roundtrip(s)


def test_vronos_quoted_unblockable_is_real_rule_and_later_wipe_removes_it(cards):
    s = setup(cards)
    ring = put(s, "Sol Ring", "battlefield")
    start(s)
    vr = cast(s, "Vronos, Masked Inquisitor")
    act(s, "p1", type="counter", card_ids=[vr.id], kind="loyalty", delta=2)
    activate(s, vr, "9/9 Construct", targets=[ring.id], target_counts=[1])
    assert "cant_be_blocked" in ch(s, ring).imposed
    cast(s, "Humility")
    assert "cant_be_blocked" not in ch(s, ring).imposed and ch(s, ring).pt == (1, 1)
    roundtrip(s)


def genju_damage_pending(s):
    from tests.test_rules_wave30m_durations import stops, to_phase
    from tests.test_rules_wave30p_combat import attack

    land = put(s, "Plains", "battlefield")
    start(s)
    aura = cast(s, "Genju of the Fields", [land.id], target_counts=[1])
    activate(s, aura, "2/5 white Spirit")
    stops(s, "declare_attackers", "declare_blockers", "combat_damage")
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (land, "p2"), pid="p1")
    to_phase(s, "declare_blockers", turn=4)
    if s.state.rules.decision and s.state.rules.decision.kind == "declare_blockers":
        act(s, "p2", type="declare_blockers", blocks=[])
    to_phase(s, "combat_damage", turn=4)
    assert s.state.zones.get("stack") and s.state.players["p2"].life == 38
    return land


@pytest.mark.parametrize("response", ["control", "blink", "counter"])
def test_genju_trigger_counterable_and_beneficiary_current_or_last_controller(cards, response):
    s = setup(cards)
    land = genju_damage_pending(s)
    if response == "control":
        cast(s, "Act of Aggression", [land.id], pid="p2", target_counts=[1], life_symbols=[])
        assert s.state.cards[land.id].controller == "p2", (
            s.state.turn,
            [(e.layer, e.new_controller, e.duration) for e in s.state.rules.effects],
            s.state.players["p1"].life,
            s.state.players["p2"].life,
        )
        assert s.state.players["p1"].life == 40 and s.state.players["p2"].life == 40
    elif response == "blink":
        cast(s, "Cloudshift", [land.id], target_counts=[1])
        assert s.state.players["p1"].life == 42 and ch(s, land).types == {"Land"}
    else:
        trigger = s.state.zones["stack"][-1]
        cast(s, "Stifle", [trigger], target_counts=[1])
        assert s.state.players["p1"].life == 40
    roundtrip(s)


def test_flayer_granted_annihilator_uses_native_attack_trigger(cards):
    from tests.test_rules_wave30m_durations import to_phase
    from tests.test_rules_wave30p_combat import attack

    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield", pid="p2")
    put(s, "Sol Ring", "battlefield", pid="p2")
    put(s, "Island", "battlefield", pid="p2")
    put(s, "Forest", "battlefield", pid="p2")
    start(s)
    cast(s, "Flayer of Loyalties")
    pick(s, [bear.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=4)
    attack(s, (bear, "p2"), pid="p1")
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.min_choices == 2
    pick(s, [o.id for o in d.options][:2])
    settle(s)
    assert len(s.state.zones.get("p2:graveyard", [])) >= 2
    roundtrip(s)


def test_dancing_sword_granted_ward_uses_native_opponent_target_trigger(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    sword = put(s, "Dancing Sword", "battlefield")
    start(s)
    activate(s, sword, "Equip {1}", targets=[bear.id], target_counts=[1])
    cast(s, "Murder", [bear.id], target_counts=[1])
    d = s.state.rules.decision
    pick(s, [next(o.id for o in d.options if "Yes" in o.label)])
    settle(s)
    cast(s, "Giant Growth", [sword.id], pid="p2", target_counts=[1])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and any(o.id == "decline" for o in d.options)
    pick(s, ["decline"])
    settle(s)
    assert ch(s, sword).pt == (2, 1)
    roundtrip(s)


@pytest.mark.parametrize("kaito_first", [False, True])
def test_kaito_type_animation_continues_after_humility_removes_ability(cards, kaito_first):
    s = setup(cards)
    start(s)
    if not kaito_first:
        cast(s, "Humility")
    kaito = cast(s, "Kaito, Bane of Nightmares")
    if kaito_first:
        cast(s, "Humility")
    current = ch(s, kaito)
    assert current.types == {"Creature"} and current.subtypes == {"Ninja"}
    assert current.pt == ((1, 1) if kaito_first else (3, 4))
    assert ("hexproof" in current.keywords) == (not kaito_first)
    roundtrip(s)


def test_kaito_prospective_creature_form_respects_native_entry_replacement(cards):
    s = setup(cards)
    put(s, "Authority of the Consuls", "battlefield", pid="p2")
    start(s)
    kaito = cast(s, "Kaito, Bane of Nightmares")
    assert "Creature" in ch(s, kaito).types
    assert s.state.cards[kaito.id].tapped and s.state.players["p2"].life == 41
    roundtrip(s)


@pytest.mark.parametrize("warden_first", [False, True])
def test_warden_animation_continues_through_humility_when_turn_changes(cards, warden_first):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    start(s)
    if not warden_first:
        cast(s, "Humility")
    warden = cast(s, "Warden of the Wall")
    if warden_first:
        cast(s, "Humility")
    assert ch(s, warden).types == {"Artifact"}
    to_phase(s, "main1", turn=5)
    current = ch(s, warden)
    assert current.types == {"Artifact", "Creature"} and current.subtypes == {"Gargoyle"}
    assert current.pt == ((1, 1) if warden_first else (2, 3))
    assert ("flying" in current.keywords) == (not warden_first)
    roundtrip(s)


def test_native_zero_counter_prohibition_preview_does_not_commit_or_invent_counters(cards):
    s = setup(cards)
    put(s, "Solemnity", "battlefield", pid="p2")
    put(s, "Authority of the Consuls", "battlefield", pid="p2")
    start(s)
    serpent = cast(s, "Stonecoil Serpent", x_value=3)
    assert s.state.cards[serpent.id].zone == "p1:graveyard"
    assert not s.state.cards[serpent.id].counters
    assert s.state.players["p2"].life == 41
    roundtrip(s)


@pytest.mark.parametrize("double_first", [False, True])
def test_kaito_initial_counter_replacement_order_qualifies_entry_without_double_commit(cards, double_first):
    s = setup(cards)
    put(s, "Authority of the Consuls", "battlefield", pid="p2")
    put(s, "Doubling Season", "battlefield")
    put(s, "Lae'zel, Vlaakith's Champion", "battlefield")
    start(s)
    kaito = cast(s, "Kaito, Bane of Nightmares")
    d = s.state.rules.decision
    assert d
    want = "Doubling Season" if double_first else "Lae'zel"
    pick(s, [next(o.id for o in d.options if want in o.label)])
    settle(s)
    assert s.state.cards[kaito.id].counters["loyalty"] == (9 if double_first else 10)
    assert s.state.cards[kaito.id].tapped and ch(s, kaito).types == {"Creature"}
    assert s.state.players["p2"].life == 41
    roundtrip(s)


def test_kaito_turn_and_last_loyalty_boundaries_are_current_not_cast_frozen(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    start(s)
    kaito = cast(s, "Kaito, Bane of Nightmares")
    cast(s, "Lightning Bolt", [kaito.id], target_counts=[1])
    assert s.state.cards[kaito.id].counters["loyalty"] == 4 and s.state.cards[kaito.id].damage == 3
    to_phase(s, "main1", turn=5)
    assert (
        ch(s, kaito).types == {"Planeswalker"}
        and ch(s, kaito).pt is None
        and "hexproof" not in ch(s, kaito).keywords
    )
    to_phase(s, "main1", turn=7)
    assert ch(s, kaito).types == {"Creature"} and ch(s, kaito).pt == (3, 4)
    act(s, "p1", type="counter", card_ids=[kaito.id], kind="loyalty", delta=-4)
    assert ch(s,kaito).types == {"Planeswalker"}
    act(s,s.state.rules.priority,type="pass_priority")
    assert s.state.cards[kaito.id].zone == "p1:graveyard"
    roundtrip(s)
