"""Actual canonical collateral coverage for fixed names in costs and tutors."""

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
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import answer, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase
from tests.conftest import claim_host


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / "fixtures/conditional_tutor_outcome_cards.json").read_text())
    for i, c in enumerate(data):
        base[c["name"]] = card(
            c["name"], set_code="sec", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = [
    c["name"]
    for c in json.loads((Path(__file__).parent / "fixtures/conditional_tutor_outcome_cards.json").read_text())
][:18]


@pytest.mark.parametrize("name", NAMES)
def test_canonical_full(cards, name):
    got = coverage.of_card_data(cards.resolve(name))
    assert got.level == "FULL", got


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/conditional_tutor_outcome_cards.json").read_text()
        )
    ]
    s = table(
        cards,
        [
            *names,
            "Plains",
            "Island",
            "Gingerbrute",
            "Grizzly Bears",
            "Grizzly Bears",
            "Shivan Dragon",
            "The First Doctor",
        ],
        names,
        names,
    )
    to_phase(s, "main1", turn=1)
    return s


def cast(s, name, **kw):
    source = put(s, name, "hand")
    mana(s, C=50, W=20, U=20, B=20, R=20, G=20)
    act(s, "p1", type="cast_spell", card_id=source.id, **kw)
    settle(s)
    return source


def choose_named(s, name):
    return next(o.id for o in s.state.rules.decision.options if s.state.cards[o.id].name == name)


def find(s, name):
    cid = choose_named(s, name)
    answer(s, [cid])
    return cid


def search_yes(s):
    if s.state.rules.decision.resume["step"] == "search_may":
        answer(s, ["yes"])


def finish_scry(s):
    while s.state.rules.decision:
        d = s.state.rules.decision
        if d.kind == "order":
            answer(s, [o.id for o in d.options])
        else:
            answer(s, [])


def current(s, c):
    return s.state.cards[c.id if hasattr(c, "id") else c]


def ch(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(current(s, c))


@pytest.mark.parametrize("kicked", [False, True])
def test_aang_kicked_query_actual_slots(cards, kicked):
    s = setup(cards)
    life = s.state.players["p1"].life
    cast(s, "Aang's Journey", kicker=int(kicked))
    cid = find(s, "Forest")
    if kicked:
        shrine = find(s, "Sanctum of Fruitful Harvest")
        assert current(s, shrine).zone == "p1:hand"
    assert current(s, cid).zone == "p1:hand"
    assert s.state.players["p1"].life == life + 2
    roundtrip(s)


@pytest.mark.parametrize("nissa", [False, True])
def test_nissa_triumph_actual_current_controlled_subtype_query(cards, nissa):
    s = setup(cards)
    if nissa:
        cast(s, "Nissa, Genesis Mage")
    cast(s, "Nissa's Triumph")
    d = s.state.rules.decision
    assert d.max_choices == (3 if nissa else 2)
    assert any(s.state.cards[o.id].name == "Temple Garden" for o in d.options) == nissa
    ids = [o.id for o in d.options][: 3 if nissa else 2]
    answer(s, ids)
    assert all(current(s, c).zone == "p1:hand" for c in ids)
    roundtrip(s)


@pytest.mark.parametrize("extra", [False, True])
def test_tithe_target_land_comparison_and_actual_hand(cards, extra):
    s = setup(cards)
    if extra:
        put(s, "Island", "battlefield", pid="p2")
    cast(s, "Tithe", targets=["p2"])
    d = s.state.rules.decision
    assert d.max_choices == (2 if extra else 1)
    ids = [o.id for o in d.options][: 2 if extra else 1]
    answer(s, ids)
    assert all(current(s, c).zone == "p1:hand" for c in ids)
    roundtrip(s)


@pytest.mark.parametrize("kicked", [False, True])
def test_five_doctors_native_zones_and_inherited_kicker_destination(cards, kicked):
    s = setup(cards)
    doctor = put(s, "The First Doctor", "graveyard")
    cast(s, "The Five Doctors", kicker=int(kicked))
    answer(s, ["graveyard"])
    answer(s, [doctor.id])
    assert current(s, doctor).zone == ("p1:battlefield" if kicked else "p1:hand")
    roundtrip(s)


@pytest.mark.parametrize("destination", ["hand", "graveyard"])
def test_dina_choose_actual_found_destination_before_shuffle(cards, destination):
    s = setup(cards)
    cast(s, "Dina's Guidance")
    cid = find(s, "Grizzly Bears")
    assert s.state.rules.decision.resume["step"] == "conditional_tutor_destination"
    answer(s, [destination])
    assert current(s, cid).zone == "p1:" + destination
    roundtrip(s)


@pytest.mark.parametrize("use_wastes", [False, True])
def test_ruin_in_wake_optional_tapped_entry_or_hand(cards, use_wastes):
    s = setup(cards)
    if use_wastes:
        put(s, "Wastes", "battlefield")
    cast(s, "Ruin in Their Wake")
    cid = find(s, "Forest")
    if use_wastes:
        answer(s, ["yes"])
    assert current(s, cid).zone == ("p1:battlefield" if use_wastes else "p1:hand")
    assert not use_wastes or current(s, cid).tapped
    roundtrip(s)


@pytest.mark.parametrize("take_entry", [False, True])
def test_caravan_morbid_optional_entry(cards, take_entry):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    cast(s, "Caravan Vigil")
    cid = find(s, "Forest")
    answer(s, ["yes" if take_entry else "no"])
    assert current(s, cid).zone == ("p1:battlefield" if take_entry else "p1:hand")
    roundtrip(s)


@pytest.mark.parametrize("x", [0, 4])
def test_vision_quest_entry_counters_and_haste_actual(cards, x):
    s = setup(cards)
    cast(s, "Vision Quest", x_value=x)
    answer(s, ["both"])
    cid = find(s, "Ornithopter")
    assert current(s, cid).zone == "p1:battlefield"
    assert current(s, cid).counters.get("+1/+1", 0) == x
    assert ("haste" in ch(s, cid).keywords) == (x >= 4)
    roundtrip(s)


@pytest.mark.parametrize("kicked", [False, True])
def test_hunting_wilds_exact_found_animation_and_untap(cards, kicked):
    s = setup(cards)
    unrelated = put(s, "Forest", "battlefield")
    cast(s, "Hunting Wilds", kicker=int(kicked))
    d = s.state.rules.decision
    ids = [o.id for o in d.options if s.state.cards[o.id].name == "Forest"][:2]
    answer(s, ids)
    for cid in ids:
        assert current(s, cid).zone == "p1:battlefield"
        assert current(s, cid).tapped == (not kicked)
        assert ch(s, cid).is_creature == kicked
        if kicked:
            assert ch(s, cid).pt[0] == 3 and "haste" in ch(s, cid).keywords
    assert not ch(s, unrelated).is_creature
    roundtrip(s)


def test_path_festival_domain_reads_just_entered_land(cards):
    s = setup(cards)
    put(s, "Temple Garden", "battlefield")
    cast(s, "Path to the Festival")
    cid = find(s, "Island")
    assert current(s, cid).zone == "p1:battlefield"
    assert s.state.rules.decision is not None
    finish_scry(s)
    roundtrip(s)


def test_slimefoot_search_then_domain_look_actual(cards):
    s = setup(cards)
    cast(s, "Slimefoot's Survey")
    ids = [choose_named(s, "Temple Garden"), choose_named(s, "Island")]
    answer(s, ids)
    assert all(current(s, cid).zone == "p1:battlefield" for cid in ids)
    d = s.state.rules.decision
    assert d.resume["step"] == "pick_looked" and len(d.options) == 3
    keep = d.options[0].id
    answer(s, [keep])
    assert s.state.zones["p1:library"][0] == keep
    roundtrip(s)


@pytest.mark.parametrize("found", [False, True])
def test_courier_food_only_if_card_not_put_into_hand(cards, found):
    s = setup(cards)
    cast(s, "Courier of Comestibles")
    search_yes(s)
    if found:
        cid = find(s, "Gingerbrute")
        assert current(s, cid).zone == "p1:hand"
    else:
        answer(s, [])
    assert sum(c.name == "Food" and c.zone == "p1:battlefield" for c in s.state.cards.values()) == int(
        not found
    )
    roundtrip(s)


def test_trench_gorger_exiled_count_sets_actual_base_pt(cards):
    s = setup(cards)
    source = cast(s, "Trench Gorger")
    search_yes(s)
    d = s.state.rules.decision
    ids = [o.id for o in d.options][:3]
    answer(s, ids)
    assert all(current(s, cid).zone == "p1:exile" for cid in ids)
    assert ch(s, source).pt == (3, 3)
    roundtrip(s)


def test_zirilan_actual_tutored_dragon_haste_and_delayed_exile(cards):
    s = setup(cards)
    source = put(s, "Zirilan of the Claw", "battlefield")
    to_phase(s, "main1", turn=4)
    mana(s, C=1, R=2)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{1}"))
    settle(s)
    cid = find(s, "Shivan Dragon")
    assert current(s, cid).zone == "p1:battlefield" and "haste" in ch(s, cid).keywords
    to_phase(s, "end", turn=4)
    settle(s)
    assert current(s, cid).zone == "p1:exile"
    roundtrip(s)


def test_nissa_worldwaker_ultimate_exact_lands_become_elementals(cards):
    s = setup(cards)
    source = cast(s, "Nissa, Worldwaker")
    act(s, "p1", type="set_counter", card_id=source.id, kind="loyalty", value=7)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "−7"))
    settle(s)
    d = s.state.rules.decision
    ids = [o.id for o in d.options][:2]
    answer(s, ids)
    assert all(
        current(s, cid).zone == "p1:battlefield"
        and ch(s, cid).pt[0] == 4
        and "trample" in ch(s, cid).keywords
        for cid in ids
    )
    roundtrip(s)


@pytest.mark.parametrize("paid", [False, True])
def test_analyze_evidence_changes_actual_query(cards, paid):
    s = setup(cards)
    source = put(s, "Analyze the Pollen", "hand")
    mana(s, G=1)
    if paid:
        a = put(s, "Mulldrifter", "graveyard")
        b = put(s, "Shivan Dragon", "graveyard")
        act(s, "p1", type="cast_spell", card_id=source.id, optional_costs=[source.id + ":evidence"])
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id, b.id])
        settle(s)
    else:
        act(s, "p1", type="cast_spell", card_id=source.id)
        settle(s)
    d = s.state.rules.decision
    assert any(s.state.cards[o.id].name == "Grizzly Bears" for o in d.options) == paid
    cid = find(s, "Grizzly Bears" if paid else "Forest")
    assert current(s, cid).zone == "p1:hand"
    roundtrip(s)


def test_unlucky_actual_food_sacrifice_then_search_bottoms_source(cards):
    s = setup(cards)
    source = cast(s, "Unlucky Cabbage Merchant")
    food = next(c for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=food.id, ability=ability(s, food, "{2}"))
    settle(s)
    search_yes(s)
    cid = find(s, "Forest")
    assert current(s, cid).zone == "p1:battlefield" and current(s, cid).tapped
    assert any(
        c.name == "Unlucky Cabbage Merchant" and c.zone == "p1:library" for c in s.state.cards.values()
    )
    assert source.id not in s.state.cards
    roundtrip(s)


@pytest.mark.parametrize("result", [1, 5, 12, 20])
def test_treasure_chest_native_actual_die_rows(cards, monkeypatch, result):
    from tests.test_rules_wave12a_counters_keywords import rolls

    s = setup(cards)
    source = put(s, "Treasure Chest", "battlefield")
    mana(s, C=4)
    life = s.state.players["p1"].life
    hand = len(s.state.zones["p1:hand"])
    rolls(monkeypatch, result)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{4}"))
    settle(s)
    if result == 20:
        cid = find(s, "Sol Ring")
        answer(s, ["battlefield"])
        assert current(s, cid).zone == "p1:battlefield"
    elif result == 1:
        assert s.state.players["p1"].life == life - 3
    elif result == 5:
        assert sum(c.name == "Treasure" and c.zone == "p1:battlefield" for c in s.state.cards.values()) == 5
    else:
        assert s.state.players["p1"].life == life + 3 and len(s.state.zones["p1:hand"]) == hand + 3
    assert current(s, source).zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize(
    "guard,expected",
    [("Doubling Season", 8), ("Solemnity", 0), ("Containment Priest", None), ("Grafdigger's Cage", None)],
)
def test_vision_native_entry_replacements(cards, guard, expected):
    s = setup(cards)
    put(s, guard, "battlefield", pid="p1" if guard in ("Doubling Season", "Solemnity") else "p2")
    cast(s, "Vision Quest", x_value=4)
    answer(s, ["both"])
    cid = find(s, "Ornithopter")
    if expected is None:
        assert not any(c.id == cid and c.zone == "p1:battlefield" for c in s.state.cards.values())
        assert not any(
            e.add_keywords and "haste" in e.add_keywords and cid in str(e.affected)
            for e in s.state.rules.effects
        )
    else:
        assert (
            current(s, cid).zone == "p1:battlefield" and current(s, cid).counters.get("+1/+1", 0) == expected
        )
    roundtrip(s)


def test_trench_zero_find_sets_zero_and_dies(cards):
    s = setup(cards)
    source = cast(s, "Trench Gorger")
    search_yes(s)
    answer(s, [])
    assert current(s, source).zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Courier of Comestibles", "Trench Gorger", "Unlucky Cabbage Merchant"])
def test_agent_diversion_not_original_tutor_result(cards, name):
    s = setup(cards)
    put(s, "Opposition Agent", "battlefield", pid="p2")
    source = cast(s, name)
    if name == "Unlucky Cabbage Merchant":
        food = next(c for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield")
        mana(s, C=2)
        act(s, "p1", type="activate_ability", card_id=food.id, ability=ability(s, food, "{2}"))
        settle(s)
    search_yes(s)
    d = s.state.rules.decision
    cid = choose_named(s, "Gingerbrute" if name == "Courier of Comestibles" else "Forest")
    assert d.decider == "p2"
    roundtrip(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[cid])
    settle(s)
    assert current(s, cid).zone == "p1:exile"
    assert any(p.card == cid and p.player == "p2" for p in s.state.rules.permissions)
    if name == "Courier of Comestibles":
        assert any(c.name == "Food" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    elif name == "Trench Gorger":
        assert current(s, source).zone == "p1:graveyard"
    else:
        assert any(c.name == name and c.zone == "p1:library" for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.parametrize("name", ["Courier of Comestibles", "Trench Gorger"])
def test_optional_search_forbidden_preserves_independent_fallback(cards, name):
    s = setup(cards)
    put(s, "Stranglehold", "battlefield", pid="p2")
    source = cast(s, name)
    assert s.state.rules.decision is None
    if name == "Courier of Comestibles":
        assert any(c.name == "Food" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    else:
        assert ch(s, source).pt == (6, 6)
    roundtrip(s)


@pytest.mark.parametrize("reentered", [False, True])
def test_zirilan_delayed_exact_object_and_source_independence(cards, reentered):
    s = setup(cards)
    source = put(s, "Zirilan of the Claw", "battlefield")
    to_phase(s, "main1", turn=4)
    mana(s, C=1, R=2)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{1}"))
    settle(s)
    cid = find(s, "Shivan Dragon")
    act(s, "p1", type="move", card_ids=[source.id], to={"zone": "graveyard"})
    if reentered:
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "graveyard"})
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "battlefield"})
    to_phase(s, "end", turn=4)
    settle(s)
    assert current(s, cid).zone == ("p1:battlefield" if reentered else "p1:exile")
    roundtrip(s)


def test_dina_destination_resumes_in_new_cold_session(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = setup(cards)
    cast(s, "Dina's Guidance")
    cid = find(s, "Grizzly Bears")
    cold = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    answer(cold, ["graveyard"])
    assert current(cold, cid).zone == "p1:graveyard"
    roundtrip(cold)


def test_evidence_cost_decision_is_copied_by_actual_twincast(cards):
    s = setup(cards)
    source = put(s, "Analyze the Pollen", "hand")
    copy = put(s, "Twincast", "hand")
    a = put(s, "Mulldrifter", "graveyard")
    b = put(s, "Shivan Dragon", "graveyard")
    mana(s, G=1, U=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id, optional_costs=[source.id + ":evidence"])
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id, b.id])
    act(s, "p1", type="cast_spell", card_id=copy.id, targets=[source.id])
    settle(s)
    for _ in range(2):
        d = s.state.rules.decision
        assert any(s.state.cards[o.id].name == "Grizzly Bears" for o in d.options)
        cid = find(s, "Grizzly Bears")
        assert current(s, cid).zone == "p1:hand"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Aang's Journey", "Hunting Wilds"])
def test_kicker_decision_is_copied_by_actual_twincast(cards, name):
    s = setup(cards)
    source = put(s, name, "hand")
    copy = put(s, "Twincast", "hand")
    mana(s, C=40, G=10, W=10, U=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id, kicker=1)
    act(s, "p1", type="cast_spell", card_id=copy.id, targets=[source.id])
    settle(s)
    for _ in range(2):
        cid = find(s, "Forest")
        if name == "Aang's Journey":
            answer(s, [])
            assert current(s, cid).zone == "p1:hand"
        else:
            assert (
                current(s, cid).zone == "p1:battlefield"
                and ch(s, cid).pt == (3, 3)
                and not current(s, cid).tapped
            )
    roundtrip(s)


def test_vision_entry_choice_pause_keeps_exact_post_entry_rider(cards):
    s = setup(cards)
    cast(s, "Vision Quest", x_value=4)
    answer(s, ["both"])
    cid = find(s, "Adaptive Automaton")
    d = s.state.rules.decision
    assert d.resume["step"] == "enter_choice"
    pick = next(o.id for o in d.options if o.label == "Elf")
    answer(s, [pick])
    assert current(s, cid).zone == "p1:battlefield"
    assert current(s, cid).counters.get("+1/+1", 0) == 4
    assert "haste" in ch(s, cid).keywords
    roundtrip(s)


def test_trench_actual_bounce_response_preserves_search_without_modifying_hand_card(cards):
    s = setup(cards)
    source = put(s, "Trench Gorger", "hand")
    mana(s, C=50, U=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id)
    for _ in range(20):
        if current(s, source).zone == "p1:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    bounce = put(s, "Unsummon", "hand")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=bounce.id, targets=[source.id])
    settle(s)
    assert current(s, source).zone == "p1:hand"
    search_yes(s)
    d = s.state.rules.decision
    ids = [o.id for o in d.options][:3]
    answer(s, ids)
    assert all(current(s, cid).zone == "p1:exile" for cid in ids)
    assert current(s, source).zone == "p1:hand" and ch(s, source).pt == (6, 6)
    roundtrip(s)


def test_merchant_trigger_uses_original_controller_after_control_change(cards):
    s = setup(cards)
    source = cast(s, "Unlucky Cabbage Merchant")
    food = next(c for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=food.id, ability=ability(s, food, "{2}"))
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    settle(s)
    assert s.state.rules.decision.player == "p1"
    search_yes(s)
    cid = find(s, "Forest")
    assert current(s, cid).zone == "p1:battlefield"
    assert any(
        c.name == "Unlucky Cabbage Merchant" and c.zone == "p1:library" for c in s.state.cards.values()
    )
    roundtrip(s)


def test_revealed_found_destination_rest_ws_hide_other_library_cards(cards, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    cast(s, "Dina's Guidance")
    found = choose_named(s, "Grizzly Bears")
    other = next(o.id for o in s.state.rules.decision.options if o.id != found)
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck_id = client.post(
            "/api/decks", json={"text": "Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest"}
        ).json()["id"]
        game = client.post(
            "/api/games",
            json={
                "mode": "lan",
                "players": [{"name": "Alice", "deck_id": deck_id}, {"name": "Bob", "deck_id": deck_id}],
            },
        ).json()
        gid = game["game"]["id"]
        bob = client.post("/api/join", json={"code": game["game"]["code"], "name": "Bob"}).json()["token"]
        spec = client.post("/api/join", json={"code": game["game"]["code"], "spectate": True}).json()["token"]
        client.app.state.services.hub.get(gid).game = s
        for stage in range(3):
            if stage == 1:
                answer(s, [found])
            elif stage == 2:
                answer(s, ["hand"])
            for token in [bob, spec]:
                response = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": token})
                assert response.status_code == 200
                with client.websocket_connect(f"/ws/games/{gid}?token={token}") as ws:
                    frame = ws.receive_json()
                for raw in [response.text, json.dumps(frame)]:
                    assert (found in raw) == (stage == 1)
                    assert other not in raw
    roundtrip(s)


def test_tithe_additional_card_is_one_library_search(cards):
    # Same CR701.23h rule as Firemind/Crescendo; extra qualifying card isn't an extra search event.
    s = setup(cards)
    put(s, "Archivist of Oghma", "battlefield", pid="p2")
    put(s, "Island", "battlefield", pid="p2")
    before = len(s.state.zones["p2:hand"])
    cast(s, "Tithe", targets=["p2"])
    d = s.state.rules.decision
    assert d.max_choices == 2
    ids = [o.id for o in d.options][:2]
    answer(s, ids)
    assert all(current(s, cid).zone == "p1:hand" for cid in ids)
    assert len(s.state.zones["p2:hand"]) == before + 1
    roundtrip(s)
