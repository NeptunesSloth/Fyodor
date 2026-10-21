"""Linked exile abilities grant native exact-object play permissions."""

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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = [
    "Ethereal Forager",
    "Nyla, Shirshu Sleuth",
    "Underworld Sentinel",
    "Wall of Mourning",
    "Purgatory",
    "Bag of Devouring",
    "Endless Horizons",
    "Bottled Cloister",
    "Asmodeus the Archfiend",
    "Ghost Vacuum",
    "Pinnacle Starcage",
]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/linked_return_family_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="lor", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name, *, hand=False):
    support = [
        "Grizzly Bears",
        "Lightning Bolt",
        "Llanowar Elves",
        "Counterspell",
        "Naturalize",
        "Murder",
        "Clone",
        "Memnite",
        "Plains",
        "Plains",
        "Voltaic Key",
        "Word of Seizing",
        "Rest in Peace",
        "Pull from Eternity",
        "Underworld Breach",
        "Tormod's Crypt",
        "Dominate",
    ]
    s = table(cards, [name, *support], support, support)
    for p in ["p1", "p2", "p3"]:
        act(s, p, type="set_prefs", hold_priority=True)
    return s, put(s, name, "hand" if hand else "battlefield")


def choose(s, ids):
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    while d.kind in ("declare_attackers", "declare_blockers"):
        act(
            s,
            d.player,
            type=d.kind,
            **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}),
        )
        until(s, lambda s: s.state.rules.decision is not None)
        d = s.state.rules.decision
    if d.resume.get("step") == "may":
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        until(s, lambda s: s.state.rules.decision is not None)
        d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def activate(s, src, n, **kw):
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=src.id, ability=n, **kw)


def kill(s, c):
    murder = put(s, "Murder", "hand")
    mana(s, C=1, B=2)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[c.id])
    settle(s)


@pytest.mark.parametrize("name", NAMES)
def test_canonical_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_ethereal_native_printed_delve_then_attack_returns_only_instant_or_sorcery(cards):
    s, src = setup(cards, "Ethereal Forager", hand=True)
    paid = [put(s, n, "graveyard") for n in ["Lightning Bolt", "Counterspell", "Grizzly Bears", "Naturalize"]]
    mana(s, U=2)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=src.id,
        contributions=[{"kind": "delve", "card": c.id} for c in paid],
    )
    settle(s)
    assert len(s.state.rules.exiled_with[s.state.rules.object_id(src.id)]) == 4
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": src.id, "target": "p2"}])
    choose(s, [paid[0].id])
    settle(s)
    assert s.state.cards[paid[0].id].zone == "p1:hand"
    assert s.state.cards[paid[2].id].zone == "p1:exile"
    roundtrip(s)


def test_nyla_native_clues_then_targeted_linked_return(cards):
    s, src = setup(cards, "Nyla, Shirshu Sleuth", hand=True)
    bear = put(s, "Grizzly Bears", "graveyard")
    mana(s, C=10, G=10, B=10)
    act(s, "p1", type="cast_spell", card_id=src.id)
    choose(s, [bear.id])
    settle(s)
    clues = [c for c in s.state.cards.values() if c.is_token and c.name == "Clue"]
    assert len(clues) == 2 and s.state.players["p1"].life == 38
    for clue in clues:
        mana(s, C=2)
        activate(s, clue, 0)
        settle(s)
    to_phase(s, "end", turn=1)
    choose(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:hand"
    roundtrip(s)


@pytest.mark.parametrize("stolen", [False, True])
def test_underworld_native_attack_exile_then_death_returns_instructed_player_battlefield(cards, stolen):
    s, src = setup(cards, "Underworld Sentinel")
    bear = put(s, "Grizzly Bears", "graveyard")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": src.id, "target": "p2"}])
    choose(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:exile"
    if stolen:
        steal = put(s, "Dominate", "hand", pid="p2")
        mana(s, "p2", C=6, U=2)
        wait_priority(s, "p2")
        act(s, "p2", type="cast_spell", card_id=steal.id, x_value=5, targets=[src.id])
        settle(s)
        assert s.state.cards[src.id].controller == "p2"
    kill(s, src)
    assert s.state.cards[bear.id].zone == ("p2:battlefield" if stolen else "p1:battlefield")
    assert s.state.cards[bear.id].owner == "p1"
    roundtrip(s)


def test_wall_native_blind_exile_then_coven_hand_choice(cards):
    from tests.test_rules_linked_exile_look import assert_look

    s, src = setup(cards, "Wall of Mourning", hand=True)
    mana(s, C=10, W=10)
    act(s, "p1", type="cast_spell", card_id=src.id)
    settle(s)
    assert len(s.state.zones["p1:exile"]) == 2
    for cid in s.state.zones["p1:exile"]:
        assert_look(s, cid, set())
    for name, owner in [("Grizzly Bears", "p2"), ("Llanowar Elves", "p3")]:
        support = next(c for c in s.state.cards.values() if c.owner == owner and c.name == name)
        act(s, "p1", type="move", card_ids=[support.id], to={"player": "p1", "zone": "battlefield"})
    cid = s.state.zones["p1:exile"][0]
    to_phase(s, "end", turn=1)
    choose(s, [cid])
    settle(s)
    assert s.state.cards[cid].zone == "p1:hand"
    assert len(s.state.zones["p1:exile"]) == 1
    roundtrip(s)


def test_purgatory_native_death_exile_optional_payment_return(cards):
    s, src = setup(cards, "Purgatory")
    bear = put(s, "Grizzly Bears", "battlefield")
    kill(s, bear)
    assert s.state.cards[bear.id].zone == "p1:exile"
    to_phase(s, "upkeep", turn=4)
    mana(s, C=4)
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.players["p1"].life == 38
    roundtrip(s)


@pytest.mark.parametrize("take", [False, True])
def test_bag_native_sacrifice_exile_roll_and_up_to_return(cards, take):
    s, src = setup(cards, "Bag of Devouring")
    bear = put(s, "Grizzly Bears", "battlefield")
    mana(s, C=2)
    activate(s, src, 1, cost_choices=[{"component": 2, "cards": [bear.id]}])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:exile"
    to_phase(s, "main1", turn=4)
    mana(s, C=3)
    activate(s, src, 2)
    choose(s, [bear.id] if take else [])
    settle(s)
    assert s.state.cards[bear.id].zone == ("p1:hand" if take else "p1:exile")
    assert s.state.cards[src.id].zone == "p1:graveyard"
    roundtrip(s)


def test_endless_native_plains_search_and_own_linked_choice(cards):
    s, src = setup(cards, "Endless Horizons", hand=True)
    mana(s, C=3, W=1)
    act(s, "p1", type="cast_spell", card_id=src.id)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    ids = [o.id for o in d.options if o.card_id and s.state.cards[o.card_id].name == "Plains"]
    assert len(ids) == 2
    act(s, "p1", type="choose", decision_id=d.id, option_ids=ids)
    settle(s)
    to_phase(s, "upkeep", turn=4)
    choose(s, [ids[0]])
    settle(s)
    assert s.state.cards[ids[0]].zone == "p1:hand" and s.state.cards[ids[1]].zone == "p1:exile"
    roundtrip(s)


def test_bottled_native_opponent_upkeep_blind_hand_then_own_return_and_draw(cards):
    from collections import Counter

    from tests.test_rules_linked_exile_look import assert_look

    s, src = setup(cards, "Bottled Cloister")
    put(s, "Grizzly Bears", "hand")
    put(s, "Lightning Bolt", "hand")
    original = Counter(s.state.cards[c].card_id for c in s.state.zones["p1:hand"])
    to_phase(s, "main1", turn=2)
    assert not s.state.zones["p1:hand"]
    for cid in s.state.zones["p1:exile"]:
        assert_look(s, cid, set())
    to_phase(s, "upkeep", turn=4)
    settle(s)
    assert not s.state.zones["p1:exile"]
    assert Counter(s.state.cards[c].card_id for c in s.state.zones["p1:hand"]) >= original
    assert len(s.state.zones["p1:hand"]) == sum(original.values()) + 1
    roundtrip(s)


def test_asmodeus_native_draw_replacement_linked_blind_return_actual_life_count(cards):
    from tests.test_rules_linked_exile_look import assert_look

    s, src = setup(cards, "Asmodeus the Archfiend")
    mana(s, B=3)
    activate(s, src, 1)
    settle(s)
    assert len(s.state.zones["p1:exile"]) == 7
    for cid in s.state.zones["p1:exile"]:
        assert_look(s, cid, set())
    before = len(s.state.zones["p1:hand"])
    mana(s, B=1)
    activate(s, src, 2)
    settle(s)
    assert not s.state.zones["p1:exile"] and len(s.state.zones["p1:hand"]) == before + 7
    assert s.state.players["p1"].life == 33
    roundtrip(s)


def test_ghost_native_foreign_creature_return_flying_counter_spirit_base_pt(cards):
    from app.rules.plan import Plan

    s, src = setup(cards, "Ghost Vacuum")
    bear = put(s, "Grizzly Bears", "graveyard", pid="p2")
    bolt = put(s, "Lightning Bolt", "graveyard")
    activate(s, src, 0, targets=[bear.id])
    settle(s)
    key = put(s, "Voltaic Key", "battlefield")
    mana(s, C=1)
    activate(s, key, 0, targets=[src.id])
    settle(s)
    activate(s, src, 0, targets=[bolt.id])
    settle(s)
    to_phase(s, "main1", turn=4)
    mana(s, C=6)
    activate(s, src, 1)
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].owner == "p2"
    assert s.state.cards[bolt.id].zone == "p1:exile"
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id])
    assert ch.pt == (1, 1) and {"Bear", "Spirit"} <= ch.subtypes and "flying" in ch.keywords
    assert s.state.cards[bear.id].counters.get("flying") == 1
    roundtrip(s)


@pytest.mark.parametrize("rip", [False, True])
def test_pinnacle_native_linked_graveyard_arrivals_count_robots(cards, rip):
    s, src = setup(cards, "Pinnacle Starcage", hand=True)
    bear = put(s, "Grizzly Bears", "battlefield", pid="p2")
    mem = put(s, "Memnite", "battlefield")
    mana(s, C=10, W=10)
    act(s, "p1", type="cast_spell", card_id=src.id)
    settle(s)
    assert s.state.cards[bear.id].zone == "p2:exile" and s.state.cards[mem.id].zone == "p1:exile"
    if rip:
        put(s, "Rest in Peace", "battlefield")
    mana(s, C=6, W=2)
    activate(s, src, 1)
    settle(s)
    robots = [
        c for c in s.state.cards.values() if c.is_token and c.name == "Robot" and c.zone == "p1:battlefield"
    ]
    assert len(robots) == (0 if rip else 2)
    if not rip:
        assert s.state.cards[bear.id].zone == "p2:graveyard" and s.state.cards[mem.id].zone == "p1:graveyard"
    roundtrip(s)


def test_delve_original_exile_oid_does_not_follow_leave_and_reexile(cards):
    s, src = setup(cards, "Ethereal Forager", hand=True)
    paid = [put(s, n, "graveyard") for n in ["Lightning Bolt", "Counterspell", "Grizzly Bears", "Naturalize"]]
    mana(s, U=2)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=src.id,
        contributions=[{"kind": "delve", "card": c.id} for c in paid],
    )
    original = s.state.rules.object_id(paid[0].id)
    pull = put(s, "Pull from Eternity", "hand", pid="p2")
    mana(s, "p2", W=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=pull.id, targets=[paid[0].id])
    until(s, lambda s: s.state.cards[paid[0].id].zone == "p1:graveyard")
    crypt = put(s, "Tormod's Crypt", "battlefield", pid="p2")
    wait_priority(s, "p2")
    act(s, "p2", type="activate_ability", card_id=crypt.id, ability=0, targets=["p1"])
    until(s, lambda s: s.state.cards[paid[0].id].zone == "p1:exile")
    assert s.state.rules.object_id(paid[0].id) != original
    settle(s)
    linked = s.state.rules.exiled_with[s.state.rules.object_id(src.id)]
    assert len(linked) == 3 and s.state.rules.object_id(paid[0].id) not in linked
    roundtrip(s)


def test_delve_legacy_missing_new_exile_snapshot_does_not_guess(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s, src = setup(cards, "Ethereal Forager", hand=True)
    paid = [put(s, n, "graveyard") for n in ["Lightning Bolt", "Counterspell", "Grizzly Bears", "Naturalize"]]
    mana(s, U=2)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=src.id,
        contributions=[{"kind": "delve", "card": c.id} for c in paid],
    )
    data = s.state.model_dump(mode="json")
    for record in data["rules"]["payments"].values():
        for part in record["contributions"]:
            part.pop("exiled_object_id", None)
    s = GameSession(GameState.model_validate(data), cards=cards)
    settle(s)
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(src.id))
    roundtrip(s)


def cold_choose(s, cards, tmp_path, ids):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    original = tmp_path / "original.json"
    restored = tmp_path / "restored.json"
    original.write_text(s.state.model_dump_json())
    code = """
import sys,json
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[1]),ImageStore(Path(sys.argv[2])))
s=GameSession(GameState.model_validate_json(Path(sys.argv[3]).read_text()),cards=repo)
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':json.loads(sys.argv[5])})
Path(sys.argv[4]).write_text(s.state.model_dump_json())
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(cards.db_path),
            str(tmp_path / "images"),
            str(original),
            str(restored),
            json.dumps(ids),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return GameSession(GameState.model_validate_json(restored.read_text()), cards=cards)


def test_ghost_cold_native_clone_entry_choice_retains_flying_and_spirit_recipe(cards, tmp_path):
    from app.rules.plan import Plan

    s, src = setup(cards, "Ghost Vacuum")
    clone = put(s, "Clone", "graveyard", pid="p2")
    bear = put(s, "Grizzly Bears", "battlefield", pid="p2")
    activate(s, src, 0, targets=[clone.id])
    settle(s)
    to_phase(s, "main1", turn=4)
    mana(s, C=6)
    activate(s, src, 1)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    option = next(o.id for o in d.options if o.card_id == bear.id or o.id == bear.id)
    s = cold_choose(s, cards, tmp_path, [option])
    settle(s)
    returned = s.state.cards[clone.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(returned)
    assert returned.zone == "p1:battlefield" and returned.owner == "p2"
    assert ch.pt == (1, 1) and {"Bear", "Spirit"} <= ch.subtypes and returned.counters.get("flying") == 1
    roundtrip(s)


def test_bag_cold_recorded_roll_pending_up_to_choice(cards, tmp_path):
    s, src = setup(cards, "Bag of Devouring")
    bear = put(s, "Grizzly Bears", "battlefield")
    mana(s, C=2)
    activate(s, src, 1, cost_choices=[{"component": 2, "cards": [bear.id]}])
    settle(s)
    to_phase(s, "main1", turn=4)
    mana(s, C=3)
    activate(s, src, 2)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.min_choices == 0 and d.max_choices == 1
    assert d.resume["ctx"].get("dice") or d.resume["ctx"].get("roll") or "die" in str(d.resume)
    s = cold_choose(s, cards, tmp_path, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:hand"
    roundtrip(s)


def test_breach_escaped_clone_copying_forager_does_not_link_foreign_escape_cost(cards):
    s, forager = setup(cards, "Ethereal Forager")
    put(s, "Underworld Breach", "battlefield")
    clone = put(s, "Clone", "graveyard")
    paid = [put(s, n, "graveyard") for n in ["Lightning Bolt", "Counterspell", "Naturalize"]]
    mana(s, C=3, U=1)
    act(s, "p1", type="cast_spell", card_id=clone.id)
    choose(s, [forager.id])
    settle(s)
    assert all(s.state.cards[c.id].zone == "p1:exile" for c in paid)
    assert not s.state.rules.exiled_with.get(s.state.rules.object_id(clone.id))
    roundtrip(s)


def test_delve_link_follows_source_control_but_return_follows_card_owner(cards):
    s, src = setup(cards, "Ethereal Forager", hand=True)
    paid = [put(s, n, "graveyard") for n in ["Lightning Bolt", "Counterspell", "Grizzly Bears", "Naturalize"]]
    mana(s, U=2)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=src.id,
        contributions=[{"kind": "delve", "card": c.id} for c in paid],
    )
    settle(s)
    steal = put(s, "Dominate", "hand", pid="p2")
    mana(s, "p2", C=7, U=2)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=steal.id, x_value=6, targets=[src.id])
    settle(s)
    assert s.state.cards[src.id].controller == "p2"
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": src.id, "target": "p3"}])
    choose(s, [paid[0].id])
    settle(s)
    assert s.state.cards[paid[0].id].zone == "p1:hand"
    roundtrip(s)
