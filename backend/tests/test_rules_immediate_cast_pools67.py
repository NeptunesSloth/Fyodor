"""Native whole-card immediate casting pools, frozen targets and dynamic limits."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_refused_look import stack_library

NAMES = [
    "Aetherflux Conduit",
    "Chandra Ablaze",
    "Ashiok, Nightmare Muse",
    "Counterlash",
    "Brain in a Jar",
    "Tetsuo, Imperial Champion",
]
SUPPORT = [
    "Shock",
    "Blaze",
    "Fling",
    "Doubling Season",
    "Sol Ring",
    "Lightning Bolt",
    "Llanowar Elves",
    "Divination",
    "Giant Growth",
    "Forest",
    "Jace Beleren",
    "Healing Salve",
    "Murder",
    "Darksteel Myr",
    "Disperse",
    "Hermetic Study",
    "Centaur Courser",
    "Brazen Borrower // Petty Theft",
    "Into the Roil",
    "Bonesplitter",
    "Last Word",
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for filename in [
        "exile_outcomes42_cards.json",
        "exile_cast_outcomes45_cards.json",
        "fight_exile_receipts65_cards.json",
        "immediate_cast_pools67_cards.json",
    ]:
        for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / filename).read_text())):
            base[c["name"]] = card(
                c["name"],
                set_code="ic67",
                number=str(i),
                **{k: v for k, v in c.items() if k not in {"name", "set_code"}},
            )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *NAMES, *SUPPORT)


def pick(s, name):
    d = s.state.rules.decision
    assert d and d.resume["step"] == "free_cast_pick"
    option = next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == name)
    answer(s, [option])


def stop(s):
    d = s.state.rules.decision
    if d:
        assert d.resume["step"] == "free_cast_pick"
        answer(s, [])
    settle(s)


@pytest.mark.parametrize("name", NAMES)
def test_whole_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_brain_adds_counter_then_freecasts_equal_instant(cards):
    s = setup(cards)
    source = cast(s, "Brain in a Jar")
    bolt = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0)
    settle(s)
    assert s.state.cards[source.id].counters["charge"] == 1
    pick(s, "Lightning Bolt")
    answer(s, ["p2"])
    settle(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    roundtrip(s)


def test_brain_matching_cost_is_exact_not_lower(cards):
    s = setup(cards)
    source = cast(s, "Brain in a Jar")
    act(s, "p1", type="counter", card_ids=[source.id], kind="charge", delta=1)
    bolt = put(s, "Lightning Bolt", "hand")
    bear = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0)
    settle(s)
    d = s.state.rules.decision
    assert not d or all(o.card_id not in [bolt.id, bear.id] for o in d.options)
    stop(s)
    roundtrip(s)


def test_chandra_ultimate_only_own_red_instants_sorceries(cards):
    s = setup(cards)
    cast(s, "Doubling Season")
    source = cast(s, "Chandra Ablaze")
    bolt = put(s, "Lightning Bolt", "graveyard")
    foreign = put(s, "Shock", "graveyard", "p2")
    green = put(s, "Giant Growth", "graveyard")
    creature = put(s, "Centaur Courser", "graveyard")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=2)
    settle(s)
    d = s.state.rules.decision
    assert d and bolt.id in [o.card_id for o in d.options]
    assert not {foreign.id, green.id, creature.id} & {o.card_id for o in d.options}
    pick(s, "Lightning Bolt")
    answer(s, ["p2"])
    stop(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    roundtrip(s)


def test_ashiok_casts_unlinked_opponent_faceup_cards_only(cards):
    s = setup(cards)
    cast(s, "Doubling Season")
    source = cast(s, "Ashiok, Nightmare Muse")
    foreign = put(s, "Lightning Bolt", "exile", "p2")
    own = put(s, "Shock", "exile")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=2)
    settle(s)
    d = s.state.rules.decision
    assert d and foreign.id in [o.card_id for o in d.options] and own.id not in [o.card_id for o in d.options]
    pick(s, "Lightning Bolt")
    answer(s, ["p2"])
    stop(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[foreign.id].zone == "p2:graveyard"
    roundtrip(s)


def test_aetherflux_pays_fifty_draws_seven_and_offers_newly_drawn_cards(cards):
    s = setup(cards)
    source = cast(s, "Aetherflux Conduit")
    act(s, "p1", type="resource", player="p1", key="energy", delta=50)
    stack_library(
        s, ["Lightning Bolt", "Shock", "Blaze", "Forest", "Sol Ring", "Llanowar Elves", "Divination"]
    )
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1)
    settle(s)
    assert s.state.players["p1"].resources["energy"] == 0
    assert len(s.state.zones["p1:hand"]) == before + 7
    pick(s, "Lightning Bolt")
    answer(s, ["p2"])
    stop(s)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_aetherflux_insufficient_energy_cannot_activate(cards):
    s = setup(cards)
    source = cast(s, "Aetherflux Conduit")
    act(s, "p1", type="resource", player="p1", key="energy", delta=49)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=1)
    assert s.state.model_dump(mode="json") == before


def test_counterlash_uses_original_adventure_stack_face_after_counter(cards):
    from tests.test_rules_bandmate_references import mana

    s = setup(cards)
    adventure = put(s, "Brazen Borrower // Petty Theft", "hand")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    bolt = put(s, "Lightning Bolt", "hand")
    creature = put(s, "Llanowar Elves", "hand")
    mana(s, C=50, U=20)
    act(s, "p1", type="cast_spell", card_id=adventure.id, face=1, targets=[bear.id])
    cast(s, "Counterlash", targets=[adventure.id])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "free_cast_pick"
    assert bolt.id in [o.card_id for o in d.options] and creature.id not in [o.card_id for o in d.options]
    assert s.state.cards[adventure.id].zone == "p1:graveyard"
    pick(s, "Lightning Bolt")
    answer(s, ["p2"])
    settle(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[bear.id].zone == "p2:battlefield"
    roundtrip(s)


def test_brain_departed_source_uses_original_counter_lki(cards):
    s = setup(cards)
    source = cast(s, "Brain in a Jar")
    act(s, "p1", type="counter", card_ids=[source.id], kind="charge", delta=2)
    shock = put(s, "Into the Roil", "hand")
    divination = put(s, "Divination", "hand")
    put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0)
    cast(s, "Disperse", targets=[source.id])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "free_cast_pick"
    assert shock.id in [o.card_id for o in d.options] and divination.id not in [
        o.card_id for o in d.options
    ], (d.resume, {k: v.model_dump() for k, v in s.state.rules.lki.items() if k.startswith(source.id)})
    assert s.state.cards[source.id].zone == "p1:hand"
    stop(s)
    assert s.state.cards[shock.id].zone == "p1:hand"
    roundtrip(s)


def test_ashiok_returned_card_can_be_exiled_by_target_controller(cards):
    s = setup(cards)
    source = cast(s, "Ashiok, Nightmare Muse")
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    put(s, "Llanowar Elves", "hand", "p2")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p2" and bear.id in [o.id for o in d.options]
    answer(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == "p2:exile"
    assert s.state.cards[source.id].counters["loyalty"] == 2
    roundtrip(s)


def test_target_type_metadata_cannot_bypass_missing_spell_target_guard():
    from app.rules import scripts

    e = {"do": "free_cast", "zone": "hand", "shares_type": "target"}
    assert not scripts._event_refs_ok({"kind": "spell", "effects": [e], "target": None})
    assert not scripts._event_refs_ok({"kind": "spell", "effects": [e], "target": {"what": "creature"}})
    assert not scripts._event_refs_ok({"kind": "triggered", "effects": [e], "target": {"what": "spell"}})
    assert scripts._event_refs_ok({"kind": "spell", "effects": [e], "target": {"what": "spell"}})


def test_ashiok_bounced_owner_exiles_own_hand_not_former_controllers_hand(cards):
    s = setup(cards)
    source = cast(s, "Ashiok, Nightmare Muse")
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="set_controller", card_ids=[bear.id], player="p2")
    elf = put(s, "Llanowar Elves", "hand", "p2")
    foreign = put(s, "Shock", "hand", "p2")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, targets=[bear.id])
    settle(s)
    d = s.state.rules.decision
    if d:
        assert d.player == "p1" and bear.id in [o.id for o in d.options]
        answer(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:exile"
    assert s.state.cards[foreign.id].zone == "p2:hand"
    assert s.state.cards[elf.id].zone == "p2:hand"
    roundtrip(s)


def equipped_attacker(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = cast(s, "Tetsuo, Imperial Champion")
    equipment = cast(s, "Bonesplitter")
    act(s, "p1", type="activate_ability", card_id=equipment.id, ability=1, targets=[source.id])
    settle(s)
    assert s.state.cards[equipment.id].attached_to == source.id
    put(s, "Lightning Bolt", "hand")
    put(s, "Divination", "hand")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    settle(s)
    return s, source, equipment


def test_tetsuo_attack_native_mode_damage_uses_max_equipment_value(cards):
    s, source, equipment = equipped_attacker(cards)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "trigger_modes"
    answer(s, ["0:0"])
    answer(s, ["p2"])
    settle(s)
    assert s.state.players["p2"].life == 39
    roundtrip(s)


def test_tetsuo_attack_native_cast_mode_limits_to_equipment_value(cards):
    s, source, equipment = equipped_attacker(cards)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "trigger_modes"
    answer(s, ["1:0"])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "free_cast_pick"
    for o in d.options:
        if o.card_id:
            assert s.state.cards[o.card_id].name in {
                "Shock",
                "Blaze",
                "Lightning Bolt",
                "Healing Salve",
                "Giant Growth",
            }
    stop(s)
    roundtrip(s)


def test_chandra_plus_red_discard_damages(cards):
    s = setup(cards)
    source = cast(s, "Chandra Ablaze")
    red = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, targets=["p2"])
    settle(s)
    if s.state.rules.decision:
        answer(s, [red.id])
    assert s.state.cards[red.id].zone == "p1:graveyard"
    assert s.state.players["p2"].life == 36
    roundtrip(s)


def test_chandra_minus_two_each_player_discards_then_draws_three(cards):
    s = setup(cards)
    source = cast(s, "Chandra Ablaze")
    old = [put(s, "Lightning Bolt", "hand", pid).id for pid in ["p1", "p2", "p3"]]
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1)
    settle(s)
    assert all(s.state.cards[c].zone.endswith(":graveyard") for c in old)
    assert all(len(s.state.zones[p + ":hand"]) == 3 for p in ["p1", "p2", "p3"])
    roundtrip(s)


def test_aetherflux_trigger_counts_actual_paid_mana(cards):
    s = setup(cards)
    cast(s, "Aetherflux Conduit")
    cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.players["p1"].resources["energy"] == 1
    roundtrip(s)


def test_ashiok_nightmare_attack_exiles_two_from_each_opponent(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s = setup(cards)
    source = cast(s, "Ashiok, Nightmare Muse")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0)
    settle(s)
    token = next(c for c in s.state.cards.values() if c.is_token and c.name == "Nightmare")
    before = {p: len(s.state.zones[p + ":library"]) for p in ["p2", "p3"]}
    to_phase(s, "declare_attackers", turn=4)
    # Opponents each drew once before this attack.
    before = {p: len(s.state.zones[p + ":library"]) for p in ["p2", "p3"]}
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": token.id, "target": "p2"}])
    settle(s)
    assert all(len(s.state.zones[p + ":library"]) == before[p] - 2 for p in before)
    assert all(len(s.state.zones[p + ":exile"]) == 2 for p in before)
    roundtrip(s)


def test_brain_second_ability_removes_announced_x_counters_for_scry(cards):
    s = setup(cards)
    source = cast(s, "Brain in a Jar")
    act(s, "p1", type="counter", card_ids=[source.id], kind="charge", delta=2)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=1, x_value=2)
    settle(s)
    assert s.state.cards[source.id].counters.get("charge", 0) == 0
    d = s.state.rules.decision
    assert d and d.resume["step"] == "look"
    answer(s, [])
    settle(s)
    roundtrip(s)


def test_tetsuo_loses_equipment_before_resolution_neither_mode_happens(cards):
    s, source, equipment = equipped_attacker(cards)
    answer(s, ["0:0"])
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
    cast(s, "Disperse", targets=[equipment.id])
    settle(s)
    assert s.state.players["p2"].life == 40
    assert s.state.cards[equipment.id].zone == "p1:hand"
    roundtrip(s)


@pytest.mark.parametrize("name", NAMES)
def test_genuine_cold_immediate_cast_pool_choice(cards, tmp_path, name):
    import os
    import subprocess
    import sys

    from tests.test_rules_bandmate_references import mana

    s = setup(cards)
    if name == "Tetsuo, Imperial Champion":
        s, source, equipment = equipped_attacker(cards)
        answer(s, ["1:0"])
    elif name in ["Chandra Ablaze", "Ashiok, Nightmare Muse"]:
        cast(s, "Doubling Season")
        source = cast(s, name)
        put(
            s,
            "Lightning Bolt",
            "graveyard" if name == "Chandra Ablaze" else "exile",
            "p1" if name == "Chandra Ablaze" else "p2",
        )
        act(s, "p1", type="activate_ability", card_id=source.id, ability=2)
        settle(s)
    elif name == "Brain in a Jar":
        source = cast(s, name)
        put(s, "Lightning Bolt", "hand")
        act(s, "p1", type="activate_ability", card_id=source.id, ability=0)
        settle(s)
    elif name == "Aetherflux Conduit":
        source = cast(s, name)
        act(s, "p1", type="resource", player="p1", key="energy", delta=50)
        stack_library(
            s, ["Lightning Bolt", "Shock", "Blaze", "Forest", "Sol Ring", "Llanowar Elves", "Divination"]
        )
        act(s, "p1", type="activate_ability", card_id=source.id, ability=1)
        settle(s)
    else:
        original = put(s, "Brazen Borrower // Petty Theft", "hand")
        bear = put(s, "Grizzly Bears", "battlefield", "p2")
        put(s, "Lightning Bolt", "hand")
        mana(s, C=50, U=20)
        act(s, "p1", type="cast_spell", card_id=original.id, face=1, targets=[bear.id])
        cast(s, name, targets=[original.id])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "free_cast_pick"
    assert any(o.card_id and s.state.cards[o.card_id].name == "Lightning Bolt" for o in d.options)
    saved = tmp_path / "saved.json"
    saved.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision
option=next(o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name=='Lightning Bolt')
act(s,d.player,type='choose',decision_id=d.id,option_ids=[option]);settle(s)
d=s.state.rules.decision
assert d and 'p2' in [o.id for o in d.options]
act(s,d.player,type='choose',decision_id=d.id,option_ids=['p2']);settle(s)
d=s.state.rules.decision
if d and d.resume['step']=='free_cast_pick':
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[]);settle(s)
assert s.state.players['p2'].life==37
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path)],
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ashiok_caps_three_sequential_casts_while_original_spells_wait(cards):
    s = setup(cards)
    cast(s, "Doubling Season")
    source = cast(s, "Ashiok, Nightmare Muse")
    for name, pid in [("Lightning Bolt", "p2"), ("Shock", "p3"), ("Blaze", "p2"), ("Divination", "p3")]:
        put(s, name, "exile", pid)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=2)
    settle(s)
    pick(s, "Lightning Bolt")
    answer(s, ["p2"])
    assert s.state.players["p2"].life == 40
    pick(s, "Shock")
    answer(s, ["p2"])
    assert s.state.players["p2"].life == 40
    pick(s, "Blaze")
    answer(s, ["p2"])
    settle(s)
    assert s.state.players["p2"].life == 35
    assert s.state.rules.decision is None
    assert (
        next(c for c in s.state.cards.values() if c.name == "Divination" and c.owner == "p3").zone
        == "p3:exile"
    )
    roundtrip(s)


def test_ashiok_foreign_free_spell_requires_casters_mandatory_sacrifice(cards):
    s = setup(cards)
    cast(s, "Doubling Season")
    source = cast(s, "Ashiok, Nightmare Muse")
    bear = put(s, "Grizzly Bears", "battlefield")
    foreign = put(s, "Fling", "exile", "p2")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=2)
    settle(s)
    pick(s, "Fling")
    answer(s, ["p2"])
    d = s.state.rules.decision
    if d and d.resume["step"] != "free_cast_pick":
        answer(s, [bear.id])
    stop(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    assert s.state.cards[foreign.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_counterlash_uncounterable_valid_spell_still_grants_matching_cast(cards):
    from tests.test_rules_bandmate_references import mana

    s = setup(cards)
    original = put(s, "Shock", "hand")
    uncounterable = put(s, "Last Word", "hand")
    bolt = put(s, "Lightning Bolt", "hand")
    creature = put(s, "Llanowar Elves", "hand")
    mana(s, C=50, U=20, R=20)
    act(s, "p1", type="cast_spell", card_id=original.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=uncounterable.id, targets=[original.id])
    cast(s, "Counterlash", targets=[uncounterable.id])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "free_cast_pick"
    assert bolt.id in [o.card_id for o in d.options] and creature.id not in [o.card_id for o in d.options]
    assert s.state.cards[uncounterable.id].zone == "stack"
    pick(s, "Lightning Bolt")
    answer(s, ["p2"])
    settle(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[original.id].zone == "p1:graveyard"
    assert s.state.cards[uncounterable.id].zone == "p1:graveyard"
    roundtrip(s)
