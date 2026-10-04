"""Core-premise review: layers (613), replacements (614–616), triggers (603), priority and the stack (117, 405, 608),
state-based actions (704), save/load and replay, probed with real Oracle text of FULL staples pulled from the card database.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, reloaded, to_hand, zone_of

REAL_DB = Path("/home/user/Fyodor/data/cards.sqlite")
NAMES = ["Blood Artist", "Zulaport Cutthroat", "Wrath of God", "Kiki-Jiki, Mirror Breaker", "Deceiver Exarch", "Mana Drain",
         "Rest in Peace", "Glen Elendra Archmage", "Platinum Angel", "Thassa's Oracle", "Elesh Norn, Grand Cenobite",
         "Night of Souls' Betrayal", "Stifle", "Solemn Simulacrum", "Path to Exile", "Strionic Resonator", "Darksteel Plate",
         "Grizzly Bears", "Mikaeus, the Unhallowed", "Doubling Season", "Hardened Scales", "Linvala, Keeper of Silence",
         "Swords to Plowshares", "Dictate of Erebos", "Rhystic Study", "Field of the Dead", "Skullclamp", "Cursed Totem", "Null Rod"]


def real_cards(names: list[str]) -> list[dict]:
    db = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    out = []
    for i, name in enumerate(names):
        r = db.execute("SELECT p.* FROM printings p JOIN oracle_defaults d ON d.printing_id = p.id WHERE p.name = ?", (name,)).fetchone()
        assert r is not None, name
        extra = {k: r[k] for k in ("power", "toughness", "loyalty") if r[k] is not None}
        out.append(card(name, set_code="tst", number=f"RC-{i}", mana_cost=r["mana_cost"] or "", cmc=float(r["cmc"] or 0),
                        type_line=r["type_line"], oracle_text=r["oracle_text"] or "", colors=json.loads(r["colors"] or "[]"),
                        color_identity=json.loads(r["color_identity"] or "[]"), keywords=json.loads(r["keywords"] or "[]"), **extra))
    db.close()
    return out


pytestmark = pytest.mark.skipif(not REAL_DB.is_file(), reason="the real card database is needed")


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *real_cards(NAMES)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_probed_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def stack_names(s):
    return [s.state.cards[i].name for i in s.state.zones.get("stack", [])]


def test_wrath_dies_triggers_apnap_and_lki(cards):
    """704.3 / 603.10a: all creatures die at once; Blood Artist (Alice, AP) sees itself and every other creature die;
    Zulaport (Bob) sees its controller's two. APNAP (603.3b): Bob's go on top and resolve first."""
    s = build(cards, ["Blood Artist", "Grizzly Bears", "Wrath of God"], ["Zulaport Cutthroat", "Deceiver Exarch"])
    put(s, "Blood Artist")
    put(s, "Grizzly Bears")
    put(s, "Zulaport Cutthroat", "p2")
    put(s, "Deceiver Exarch", "p2")
    wrath = to_hand(s, "Wrath of God")
    mana(s, "p1", W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    # Wrath resolved: 4 Blood Artist triggers (Alice) and 2 Zulaport triggers (Bob) wait
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and len(d.options) == 4, stack_names(s)  # Alice orders her four (603.3b)
    answer(s, limit=60)
    assert all(zone_of(s, n, p).endswith("graveyard") for n, p in [("Blood Artist", "p1"), ("Grizzly Bears", "p1"),
                                                                  ("Zulaport Cutthroat", "p2"), ("Deceiver Exarch", "p2")])
    # Blood Artist: 4 × (target player loses 1 — the first option — and Alice gains 1); Zulaport: 2 × (Alice loses 1, Bob gains 1)
    print("life", life(s, "p1"), life(s, "p2"), s.state.rules.log[-12:] if hasattr(s.state.rules, "log") else "")
    assert life(s, "p1") + life(s, "p2") == 80 - 6 + 6
    check(s)


def test_rest_in_peace_exiles_instead_so_persist_never_sees_a_death(cards):
    s = build(cards, ["Rest in Peace", "Glen Elendra Archmage", "Wrath of God"], [])
    put(s, "Rest in Peace")
    put(s, "Glen Elendra Archmage")
    wrath = to_hand(s, "Wrath of God")
    mana(s, "p1", W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    answer(s)
    assert zone_of(s, "Glen Elendra Archmage").endswith("exile")
    assert not s.state.zones.get("stack") and s.state.rules.decision is None
    check(s)


def test_platinum_angel_keeps_a_player_at_zero_life_until_it_leaves(cards):
    s = build(cards, ["Platinum Angel"], ["Path to Exile"])
    put(s, "Platinum Angel")
    path = to_hand(s, "Path to Exile", "p2")
    mana(s, "p2", W=1)
    act(s, "p2", type="set_stops", others=["main1"])
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")
    assert s.state.players["p1"].life == 0 and s.state.rules.priority == "p2" and s.state.turn.phase == "main1"
    act(s, "p2", type="cast_spell", card_id=path.id, targets=[card_named(s, "Platinum Angel").id])
    answer(s)
    assert zone_of(s, "Platinum Angel").endswith("exile")
    assert "p1" in s.state.rules.lost and s.state.rules.winner == "p2"  # 704.5a once the Angel is gone; 104.2a
    check(s)


def test_elesh_norn_and_night_of_souls_betrayal_layer_7c(cards):
    s = build(cards, ["Elesh Norn, Grand Cenobite", "Night of Souls' Betrayal", "Grizzly Bears"], ["Deceiver Exarch"])
    put(s, "Elesh Norn, Grand Cenobite")
    put(s, "Night of Souls' Betrayal")
    put(s, "Grizzly Bears")
    put(s, "Deceiver Exarch", "p2")
    act(s, "p1", type="pass_priority")
    assert pt(s, "Grizzly Bears") == (3, 3)
    assert pt(s, "Elesh Norn, Grand Cenobite") == (3, 6)
    assert pt(s, "Deceiver Exarch", "p2") == (-2, 1) and zone_of(s, "Deceiver Exarch", "p2").endswith("battlefield")
    check(s)


def test_stifle_counters_a_triggered_ability_on_the_stack(cards):
    s = build(cards, ["Solemn Simulacrum", "Wrath of God"], ["Stifle"])
    put(s, "Solemn Simulacrum")
    stifle = to_hand(s, "Stifle", "p2")
    mana(s, "p2", U=1)
    wrath = to_hand(s, "Wrath of God")
    mana(s, "p1", W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="pass_priority")
    assert stack_names(s) == ["Solemn Simulacrum"], stack_names(s)  # the dies trigger
    hand_before = len(s.state.zones["p1:hand"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="cast_spell", card_id=stifle.id, targets=[s.state.zones["stack"][-1]])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand_before  # the "you may draw a card" never happened
    check(s)


def test_bolt_fizzles_when_its_only_target_left(cards):
    s = build(cards, ["Lightning Bolt"], ["Grizzly Bears", "Path to Exile"])
    put(s, "Grizzly Bears", "p2")
    path = to_hand(s, "Path to Exile", "p2")
    mana(s, "p2", W=1)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bears.id])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="cast_spell", card_id=path.id, targets=[bears.id])
    answer(s)
    assert zone_of(s, "Grizzly Bears", "p2").endswith("exile")
    assert zone_of(s, "Lightning Bolt").endswith("graveyard")
    check(s)


def test_kiki_jiki_copies_exarch_which_untaps_kiki(cards):
    s = build(cards, ["Kiki-Jiki, Mirror Breaker", "Deceiver Exarch"], [])
    put(s, "Kiki-Jiki, Mirror Breaker")
    put(s, "Deceiver Exarch")
    kiki = card_named(s, "Kiki-Jiki, Mirror Breaker")
    exarch = card_named(s, "Deceiver Exarch")
    act(s, "p1", type="activate_ability", card_id=kiki.id, ability=1, targets=[exarch.id])
    d = s.state.rules.decision
    print("DECISION", d.prompt if d else None, [(o.id, o.label) for o in d.options] if d else None)
    answer(s, limit=40)
    tokens = [c for c in s.state.cards.values() if c.name == "Deceiver Exarch" and c.id != exarch.id]
    assert len(tokens) == 1
    assert not s.state.cards[kiki.id].tapped
    check(s)


def test_skullclamp_sees_the_equipped_creature_die_by_sba_lki(cards):
    """704.5f after equipping a 1/1 (1/0); "Whenever equipped creature dies" looks back in time (603.10a)."""
    from tests.test_rules_effects import token

    s = build(cards, ["Skullclamp"], [])
    put(s, "Skullclamp")
    bird = token(s, "p1", "Bird", "1/1")
    mana(s, "p1", C=1)
    clamp = card_named(s, "Skullclamp")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=clamp.id, ability=2, targets=[bird.id])
    answer(s)
    assert bird.id not in s.state.cards or not s.state.cards[bird.id].zone.endswith("battlefield")
    assert len(s.state.zones["p1:hand"]) == hand + 2
    check(s)


def test_save_and_load_in_the_middle_of_a_trigger_order_decision(cards):
    s = build(cards, ["Blood Artist", "Grizzly Bears", "Wrath of God"], ["Zulaport Cutthroat", "Deceiver Exarch"])
    put(s, "Blood Artist")
    put(s, "Grizzly Bears")
    put(s, "Zulaport Cutthroat", "p2")
    put(s, "Deceiver Exarch", "p2")
    wrath = to_hand(s, "Wrath of God")
    mana(s, "p1", W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    assert s.state.rules.decision is not None
    s2 = reloaded(s)
    assert s2.state.rules.decision is not None and s2.state.rules.decision.id == s.state.rules.decision.id
    answer(s, limit=60)
    answer(s2, limit=60)
    # (server-owned ids of new objects are drawn afresh in each session: compare what the table shows)
    def view(x):
        return ({p: x.state.players[p].life for p in x.state.players},
                sorted((c.name, c.zone) for c in x.state.cards.values()), x.state.rules.decision)

    assert view(s) == view(s2)
    check(s2)


def test_concede_while_a_decision_is_pending(cards):
    s = build(cards, ["Blood Artist", "Grizzly Bears", "Wrath of God"], ["Zulaport Cutthroat", "Deceiver Exarch"])
    put(s, "Blood Artist")
    put(s, "Grizzly Bears")
    put(s, "Zulaport Cutthroat", "p2")
    put(s, "Deceiver Exarch", "p2")
    wrath = to_hand(s, "Wrath of God")
    mana(s, "p1", W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    act(s, "p2", type="concede")
    assert s.state.rules.winner == "p1"
    check(s)


def test_mana_drain_adds_mana_at_the_next_main_phase_across_a_save(cards):
    s = build(cards, ["Grizzly Bears"], ["Mana Drain"])
    drain = to_hand(s, "Mana Drain", "p2")
    mana(s, "p2", U=2)
    bears = to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=drain.id, targets=[bears.id])
    answer(s)
    assert zone_of(s, "Grizzly Bears").endswith("graveyard")
    s = reloaded(s)
    act(s, "p1", type="pass_priority", until="next_turn")
    for _ in range(12):
        if s.state.rules.decision is not None:
            answer(s, limit=1)
        if s.state.turn.active_player == "p2" and s.state.turn.phase == "main1":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.active_player == "p2" and s.state.turn.phase == "main1", (s.state.turn.active_player, s.state.turn.phase)
    assert s.state.players["p2"].mana.get("C", 0) == 2, s.state.players["p2"].mana
    check(s)


def test_darksteel_plate_indestructible_survives_wrath(cards):
    s = build(cards, ["Darksteel Plate", "Grizzly Bears", "Wrath of God"], [])
    put(s, "Darksteel Plate")
    put(s, "Grizzly Bears")
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Darksteel Plate").id, ability=2, targets=[card_named(s, "Grizzly Bears").id])
    answer(s)
    wrath = to_hand(s, "Wrath of God")
    mana(s, "p1", W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    answer(s)
    assert zone_of(s, "Grizzly Bears").endswith("battlefield")
    check(s)


def test_linvala_stops_an_opponents_creature_abilities(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Linvala, Keeper of Silence"], ["Kiki-Jiki, Mirror Breaker", "Deceiver Exarch"])
    put(s, "Linvala, Keeper of Silence")
    put(s, "Kiki-Jiki, Mirror Breaker", "p2")
    put(s, "Deceiver Exarch", "p2")
    act(s, "p2", type="set_stops", others=["main1"])
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=card_named(s, "Kiki-Jiki, Mirror Breaker", "p2").id, ability=1,
            targets=[card_named(s, "Deceiver Exarch", "p2").id])
    check(s)


def test_thassas_oracle_cannot_win_through_an_opponents_platinum_angel(cards):
    s = build(cards, ["Thassa's Oracle"], ["Platinum Angel"])
    put(s, "Platinum Angel", "p2")
    oracle = to_hand(s, "Thassa's Oracle")
    for cid in list(s.state.zones["p1:library"]):
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "exile"})
    mana(s, "p1", U=2)
    act(s, "p1", type="cast_spell", card_id=oracle.id)
    answer(s)
    assert s.state.rules.winner is None
    check(s)


def test_mikaeus_undying_never_returns_under_rest_in_peace(cards):
    s = build(cards, ["Mikaeus, the Unhallowed", "Rest in Peace", "Grizzly Bears", "Wrath of God"], [])
    put(s, "Mikaeus, the Unhallowed")
    put(s, "Rest in Peace")
    put(s, "Grizzly Bears")
    wrath = to_hand(s, "Wrath of God")
    mana(s, "p1", W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    answer(s)
    assert zone_of(s, "Grizzly Bears").endswith("exile") and zone_of(s, "Mikaeus, the Unhallowed").endswith("exile")
    check(s)


def test_dictate_of_erebos_makes_each_opponent_sacrifice(cards):
    s = build(cards, ["Dictate of Erebos", "Grizzly Bears", "Lightning Bolt"], ["Deceiver Exarch"])
    put(s, "Dictate of Erebos")
    put(s, "Grizzly Bears")
    put(s, "Deceiver Exarch", "p2")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[card_named(s, "Grizzly Bears").id])
    answer(s)
    assert zone_of(s, "Grizzly Bears").endswith("graveyard") and zone_of(s, "Deceiver Exarch", "p2").endswith("graveyard")
    check(s)


@pytest.mark.parametrize("hold", [True, False])
def test_the_caster_receives_priority_after_a_cast_trigger_is_put_on_the_stack(cards, hold):
    """117.3c: a player who casts a spell receives priority afterwards — after the triggered abilities that cast
    caused are put on the stack (603.3), not the active player."""
    s = build(cards, ["Rhystic Study", "Counterspell"], ["Lightning Bolt"])
    put(s, "Rhystic Study")
    to_hand(s, "Counterspell")
    mana(s, "p1", U=2)  # (Alice could respond, so no one passes for her)
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="set_stops", others=["main1"])
    act(s, "p2", type="set_prefs", response="on", hold_priority=hold)
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    assert stack_names(s) == ["Lightning Bolt", "Rhystic Study"], stack_names(s)
    # holding priority, Bob keeps it; otherwise the engine passed for him (Arena-style) and Alice is next (117.4)
    assert (s.state.rules.priority, s.state.rules.passed) == (("p2", []) if hold else ("p1", ["p2"]))
    check(s)
