"""Canonical discard outcomes use native payments, simultaneous choices and immutable scalars."""

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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_hidden_card_facts import cast_cost, choose
from tests.test_rules_mana_delayed_effects import answer, cast, drawn
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = Path(__file__).parent / "fixtures/discard_outcomes_cards.json"
NAMES = [c["name"] for c in json.loads(DATA.read_text())][:18]
POOL = {c: 20 for c in "WUBRGC"}


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c["name"]] = card(
            c["name"], set_code="dco35", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    r = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield r
    r.close()


def game(cards):
    names = [c["name"] for c in json.loads(DATA.read_text())]
    s = table(cards, names, names, names)
    for p in ["p1", "p2", "p3"]:
        act(s, p, type="set_prefs", hold_priority=True)
    to_phase(s, "main1", 4)
    return s


def clear_hand(s, p="p1"):
    for cid in list(s.state.zones[p + ":hand"]):
        act(s, p, type="move", card_ids=[cid], to={"player": p, "zone": "library"})


def activate(s, source, targets=(), **kw):
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana=POOL)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[source.id])
    index = next(a.index for a in ch.abilities if a.kind in ["activated", "loyalty"])
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=index,
        targets=list(targets),
        sources=[],
        **kw,
    )


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_forget_actual_discard_count(cards):
    s = game(cards)
    clear_hand(s, "p2")
    c = put(s, "Forest", "hand", "p2")
    before = drawn(s, "p2")
    cast(s, "Forget", POOL, ["p2"])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone == "p2:graveyard" and drawn(s, "p2") == before + 1


def test_dream_and_shadow_read_exact_native_discard_history(cards):
    s = game(cards)
    c = put(s, "Trained Armodon", "hand")
    cast_cost(s, "Nahiri's Wrath", [c], [], x_value=1, target_counts=[0])
    answer(s)
    before = drawn(s, "p2")
    cast(s, "Dream Salvage", POOL, ["p1"], pid="p2")
    answer(s)
    assert drawn(s, "p2") == before + 1
    cast(s, "Shadow of the Grave", POOL)
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone == "p1:hand"


@pytest.mark.parametrize("name", ["Fa'adiyah Seer", "Sindbad"])
@pytest.mark.parametrize("land", [False, True])
def test_seer_exact_original_draw_reveal(cards, name, land):
    s = game(cards)
    source = put(s, name, "battlefield")
    to_phase(s, "main1", 7)
    found = put(s, "Forest" if land else "Sol Ring", "library")
    act(s, "p1", type="move", card_ids=[found.id], to={"player": "p1", "zone": "library"}, position="top")
    activate(s, source)
    answer(s)
    roundtrip(s)
    assert s.state.cards[found.id].zone == ("p1:hand" if land else "p1:graveyard")
    if land:
        assert s.state.cards[found.id].revealed_to


@pytest.mark.parametrize("shared", [False, True])
def test_rowdy_random_discards_share_type_once(cards, shared):
    s = game(cards)
    clear_hand(s)
    for n in (
        ["Sol Ring", "Ornithopter", "Darksteel Myr"] if shared else ["Forest", "Storm Crow", "Lightning Bolt"]
    ):
        c = put(s, n, "library")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    source = cast(s, "Rowdy Crew", POOL)
    answer(s)
    roundtrip(s)
    assert s.state.cards[source.id].counters.get("+1/+1", 0) == (2 if shared else 0)


def test_lumengrid_target_artifact_discard_untaps(cards):
    s = game(cards)
    source = put(s, "Lumengrid Augur", "battlefield")
    to_phase(s, "main1", 7)
    clear_hand(s, "p2")
    c = put(s, "Sol Ring", "hand", "p2")
    activate(s, source, ["p2"])
    settle(s)
    choose(s, [c.id])
    answer(s)
    roundtrip(s)
    assert not s.state.cards[source.id].tapped
    assert s.state.cards[c.id].zone == "p2:graveyard"


@pytest.mark.parametrize("land,discard", [("Urza's Cave", False), ("Command Tower", True), ("Forest", True)])
def test_wonderscape_uses_original_land_subtype_not_nonbasic_supertype(cards, land, discard):
    s = game(cards)
    source = put(s, "Wonderscape Sage", "battlefield")
    to_phase(s, "main1", 7)
    paid = put(s, land, "battlefield")
    before = drawn(s)
    activate(s, source, cost_choices=[{"component": 1, "cards": [paid.id]}])
    settle(s)
    if discard:
        assert s.state.rules.decision and s.state.rules.decision.player == "p1"
        choose(s, [paid.id])
        settle(s)
        assert s.state.cards[paid.id].zone == "p1:graveyard"
    else:
        assert s.state.rules.decision is None and s.state.cards[paid.id].zone == "p1:hand"
    assert drawn(s) == before + 1
    roundtrip(s)


def test_knollspine_uses_damage_not_net_life_loss(cards):
    s = game(cards)
    cast(s, "Lightning Bolt", POOL, ["p2"])
    answer(s)
    act(s, "p1", type="life", player="p2", delta=6)
    before = drawn(s)
    cast(s, "Knollspine Dragon", POOL)
    settle(s)
    choose(s, ["p2"])
    answer(s)
    roundtrip(s)
    assert s.state.players["p2"].life == 43 and drawn(s) == before + 3


def test_aether_rift_all_decline_reanimates_actual_random_card(cards):
    s = game(cards)
    put(s, "Aether Rift", "battlefield")
    to_phase(s, "upkeep", 7)
    clear_hand(s)
    c = put(s, "Grizzly Bears", "hand")
    answer(s, optional=False)
    roundtrip(s)
    assert s.state.cards[c.id].zone == "p1:battlefield"


def test_mog_optional_discards_each_trait_only_once(cards):
    s = game(cards)
    put(s, "Mog, Moogle Warrior", "battlefield")
    for p in ["p1", "p2", "p3"]:
        clear_hand(s, p)
    a = put(s, "Grizzly Bears", "hand")
    b = put(s, "Sol Ring", "hand", "p2")
    c = put(s, "Forest", "hand", "p3")
    to_phase(s, "end", 4)
    settle(s)
    for obj in [a, b, c]:
        assert s.state.rules.decision and s.state.rules.decision.player == obj.owner
        choose(s, [obj.id])
        settle(s)
    answer(s)
    roundtrip(s)
    p = Plan(s.state, "p1", s.cards, None)
    moogles = [
        c for c in s.state.cards.values() if c.zone == "p1:battlefield" and "Moogle" in p.ch(c).subtypes
    ]
    assert len(moogles) == 2
    assert all(c.counters.get("+1/+1") == 1 for c in moogles)


def test_ill_timed_reflexive_actual_maximum(cards):
    s = game(cards)
    big = put(s, "Trained Armodon", "hand")
    small = put(s, "Sol Ring", "hand")
    victim = put(s, "Darksteel Colossus", "battlefield", "p2")
    cast(s, "Ill-Timed Explosion", POOL)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and any(o.id == "pay" for o in d.options)
    choose(s, ["pay"])
    settle(s)
    choose(s, [big.id, small.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[victim.id].damage == 3


def test_hollow_each_target_threshold_independent(cards):
    s = game(cards)
    for p in ["p2", "p3"]:
        clear_hand(s, p)
    high = put(s, "Stormscale Anarch", "hand", "p2")
    low = put(s, "Forest", "hand", "p3")
    before = drawn(s)
    cast(s, "Hollow Marauder", POOL)
    settle(s)
    choose(s, ["p2", "p3"])
    answer(s)
    roundtrip(s)
    assert s.state.cards[high.id].zone == "p2:graveyard" and s.state.cards[low.id].zone == "p3:graveyard"
    assert drawn(s) == before + 1


def test_cait_actual_attack_draw_discard_tie_qualifies(cards):
    s = game(cards)
    source = put(s, "Cait, Cage Brawler", "battlefield")
    to_phase(s, "declare_attackers", 7)
    clear_hand(s)
    clear_hand(s, "p2")
    a = put(s, "Sol Ring", "hand")
    b = put(s, "Sol Ring", "hand", "p2")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    settle(s)
    choose(s, [a.id])
    settle(s)
    choose(s, [b.id])
    settle(s)
    roundtrip(s)
    assert s.state.cards[source.id].counters.get("+1/+1") == 2


def test_manticore_reflexive_target_after_discard_card_types(cards):
    s = game(cards)
    put(s, "Mount Velus Manticore", "battlefield")
    paid = put(s, "Ornithopter", "hand")
    to_phase(s, "begin_combat", 4)
    settle(s)
    d = s.state.rules.decision
    if any(o.id == "yes" for o in d.options):
        choose(s, ["yes"])
        settle(s)
    choose(s, [paid.id])
    settle(s)
    d = s.state.rules.decision
    assert d and "p2" in {o.id for o in d.options}
    choose(s, ["p2"])
    answer(s)
    roundtrip(s)
    assert s.state.players["p2"].life == 38


def test_argentum_discards_before_reflexive_target_selection(cards):
    s = game(cards)
    source = put(s, "Argentum Masticore", "battlefield")
    victim = put(s, "Sol Ring", "battlefield", "p2")
    to_phase(s, "upkeep", 7)
    paid = put(s, "Trained Armodon", "hand")
    settle(s)
    d = s.state.rules.decision
    assert d and any(o.id == "pay" for o in d.options)
    choose(s, ["pay"])
    settle(s)
    choose(s, [paid.id])
    settle(s)
    assert s.state.cards[paid.id].zone == "p1:graveyard"
    d = s.state.rules.decision
    assert d and victim.id in {o.id for o in d.options}
    choose(s, [victim.id])
    answer(s)
    roundtrip(s)
    assert (
        s.state.cards[victim.id].zone == "p2:graveyard" and s.state.cards[source.id].zone == "p1:battlefield"
    )


def test_skullknocker_actual_combat_discard_draw(cards):
    s = game(cards)
    source = put(s, "Skullknocker Ogre", "battlefield")
    to_phase(s, "declare_attackers", 7)
    clear_hand(s, "p2")
    c = put(s, "Forest", "hand", "p2")
    before = drawn(s, "p2")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    to_phase(s, "main2", 7)
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone == "p2:graveyard" and drawn(s, "p2") == before + 1


@pytest.mark.parametrize("pw_attack", [False, True])
def test_mila_opponent_attack_multiple_planeswalkers_triggers_once(cards, pw_attack):
    s = game(cards)
    put(s, "Mila, Crafty Companion // Lukka, Wayward Bonder", "battlefield")
    one = cast(s, "Teferi, Hero of Dominaria", POOL)
    answer(s)
    two = cast(s, "Jace, the Mind Sculptor", POOL)
    answer(s)
    a = put(s, "Grizzly Bears", "battlefield", "p2")
    b = put(s, "Storm Crow", "battlefield", "p2")
    to_phase(s, "declare_attackers", 5)
    before = [s.state.cards[c.id].counters.get("loyalty", 0) for c in [one, two]]
    act(
        s,
        "p2",
        type="declare_attackers",
        attackers=[
            {"card_id": a.id, "target": one.id if pw_attack else "p1"},
            {"card_id": b.id, "target": two.id if pw_attack else "p1"},
        ],
    )
    settle(s)
    roundtrip(s)
    assert [s.state.cards[c.id].counters.get("loyalty", 0) for c in [one, two]] == [
        n + int(pw_attack) for n in before
    ]


def test_lukka_actual_back_face_creature_discard_draws_two(cards):
    s = game(cards)
    source = cast(s, "Mila, Crafty Companion // Lukka, Wayward Bonder", POOL, face=1)
    answer(s)
    c = put(s, "Grizzly Bears", "hand")
    before = drawn(s)
    activate(s, source)
    settle(s)
    choose(s, [c.id])
    answer(s)
    roundtrip(s)
    assert drawn(s) == before + 2


@pytest.mark.parametrize("name", ["Fa'adiyah Seer", "Sindbad"])
@pytest.mark.parametrize(
    "replacement", ["Enduring Renewal", "Notion Thief", "Alhammarret's Archive", "Quantum Riddler"]
)
def test_seer_replaced_draw_never_discards_replacement_cards(cards, name, replacement):
    s = game(cards)
    source = put(s, name, "battlefield")
    to_phase(s, "main1", 7)
    put(s, replacement, "battlefield", "p2" if replacement == "Notion Thief" else "p1")
    answer(s)
    clear_hand(s)
    ring = put(s, "Sol Ring", "library")
    land = put(s, "Forest", "library")
    for c in [land, ring]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    if replacement == "Notion Thief":
        other = put(s, "Storm Crow", "library", "p2")
        act(s, "p2", type="move", card_ids=[other.id], to={"player": "p2", "zone": "library"}, position="top")
    activate(s, source)
    answer(s)
    roundtrip(s)
    if replacement == "Notion Thief":
        assert s.state.cards[ring.id].zone == "p1:library" and s.state.cards[other.id].zone == "p2:hand"
    else:
        assert s.state.cards[ring.id].zone == "p1:hand"
    if replacement in ["Alhammarret's Archive", "Quantum Riddler"]:
        assert s.state.cards[land.id].zone == "p1:hand"


def test_shadow_follows_declined_madness_but_not_cast_card(cards):
    s = game(cards)
    c = put(s, "Basking Rootwalla", "hand")
    cast_cost(s, "Nahiri's Wrath", [c], [], x_value=1, target_counts=[0])
    settle(s)
    d = s.state.rules.decision
    assert d and "Madness" in d.prompt
    choose(s, ["no"])
    settle(s)
    cast(s, "Shadow of the Grave", POOL)
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone == "p1:hand"


def test_argentum_no_target_still_accepts_discard(cards):
    s = game(cards)
    source = put(s, "Argentum Masticore", "battlefield")
    to_phase(s, "upkeep", 7)
    c = put(s, "Forest", "hand")
    settle(s)
    choose(s, ["pay"])
    settle(s)
    choose(s, [c.id])
    answer(s)
    roundtrip(s)
    assert s.state.cards[c.id].zone == "p1:graveyard" and s.state.cards[source.id].zone == "p1:battlefield"


def test_hollow_empty_handed_target_still_draws_for_that_player(cards):
    s = game(cards)
    for p in ["p2", "p3"]:
        clear_hand(s, p)
    high = put(s, "Stormscale Anarch", "hand", "p2")
    before = drawn(s)
    cast(s, "Hollow Marauder", POOL)
    settle(s)
    choose(s, ["p2", "p3"])
    answer(s)
    roundtrip(s)
    assert s.state.cards[high.id].zone == "p2:graveyard" and drawn(s) == before + 1


def test_aether_rift_any_player_life_payment_prevents_return(cards):
    s = game(cards)
    put(s, "Aether Rift", "battlefield")
    to_phase(s, "upkeep", 7)
    clear_hand(s)
    c = put(s, "Grizzly Bears", "hand")
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p1"
    choose(s, ["decline"])
    settle(s)
    d = s.state.rules.decision
    assert d and d.player == "p2"
    choose(s, ["pay"])
    answer(s, optional=False)
    roundtrip(s)
    assert s.state.players["p2"].life == 35 and s.state.cards[c.id].zone == "p1:graveyard"


def cold_run(s, cards, tmp_path, body, *args):
    import subprocess
    import sys

    saved = tmp_path / "state.json"
    saved.write_text(s.state.model_dump_json())
    code = (
        """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle
from tests.test_rules_mana_delayed_effects import answer,drawn
save,db,*args=sys.argv[1:]
r=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(save).read_text()),cards=r)
"""
        + body
        + """
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
r.close()
"""
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), *args],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=100,
    )
    assert result.returncode == 0, result.stderr


def test_manticore_pending_reflexive_target_cold_resume(cards, tmp_path):
    s = game(cards)
    put(s, "Mount Velus Manticore", "battlefield")
    c = put(s, "Ornithopter", "hand")
    to_phase(s, "begin_combat", 4)
    settle(s)
    d = s.state.rules.decision
    if any(o.id == "yes" for o in d.options):
        choose(s, ["yes"])
        settle(s)
    choose(s, [c.id])
    settle(s)
    assert "p2" in {o.id for o in s.state.rules.decision.options}
    cold_run(
        s,
        cards,
        tmp_path,
        """
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['p2'])
answer(s)
assert s.state.players['p2'].life==38
""",
    )


def test_returned_land_battlefield_receipt_cold_resume(cards, tmp_path):
    s = game(cards)
    source = put(s, "Wonderscape Sage", "battlefield")
    to_phase(s, "main1", 7)
    land = put(s, "Command Tower", "battlefield")
    activate(s, source, cost_choices=[{"component": 1, "cards": [land.id]}])
    roundtrip(s)
    cold_run(
        s,
        cards,
        tmp_path,
        """
land=args[0]
settle(s)
d=s.state.rules.decision
assert d is not None and d.kind=='choose_cards'
act(s,d.player,type='choose',decision_id=d.id,option_ids=[land])
settle(s)
assert s.state.cards[land].zone=='p1:graveyard'
""",
        land.id,
    )


def test_original_draw_replacement_order_cold_resume(cards, tmp_path):
    s = game(cards)
    source = put(s, "Sindbad", "battlefield")
    to_phase(s, "main1", 7)
    put(s, "Alhammarret's Archive", "battlefield")
    put(s, "Notion Thief", "battlefield", "p2")
    top = put(s, "Sol Ring", "library")
    act(s, "p1", type="move", card_ids=[top.id], to={"player": "p1", "zone": "library"}, position="top")
    activate(s, source)
    settle(s)
    assert s.state.rules.decision is not None
    cold_run(
        s,
        cards,
        tmp_path,
        """
answer(s)
assert s.state.cards[args[0]].zone=='p1:library'
""",
        top.id,
    )


def test_shadow_exact_discard_result_cold_resume(cards, tmp_path):
    s = game(cards)
    c = put(s, "Trained Armodon", "hand")
    cast_cost(s, "Nahiri's Wrath", [c], [], x_value=1, target_counts=[0])
    answer(s)
    cast(s, "Shadow of the Grave", POOL)
    roundtrip(s)
    cold_run(
        s,
        cards,
        tmp_path,
        """
answer(s)
assert s.state.cards[args[0]].zone=='p1:hand'
""",
        c.id,
    )
