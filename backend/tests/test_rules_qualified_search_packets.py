"""Actual canonical collateral coverage for fixed names in costs and tutors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import answer, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / "fixtures/qualified_search_packet_cards.json").read_text())
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
    for c in json.loads((Path(__file__).parent / "fixtures/qualified_search_packet_cards.json").read_text())
][:14]


@pytest.mark.parametrize("name", NAMES)
def test_canonical_full(cards, name):
    got = coverage.of_card_data(cards.resolve(name))
    assert got.level == "FULL", got


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/qualified_search_packet_cards.json").read_text()
        )
    ]
    s = table(
        cards,
        [
            *names,
            "Alpine Watchdog",
            "Igneous Cur",
            "Sol Ring",
            "Sol Ring",
            "Sol Ring",
            "Dryad Arbor",
            "Dryad Arbor",
            "Dryad Arbor",
            "Counterspell",
            "Plains",
            "Island",
            "Swamp",
            "Mountain",
            "Island",
            "Swamp",
            "Mountain",
        ],
        names,
        names,
    )
    to_phase(s, "main1", turn=1)
    return s


def cast(s, name, **kw):
    source = put(s, name, "hand")
    mana(s, C=40, W=20, U=20, B=20, R=20, G=20)
    act(s, "p1", type="cast_spell", card_id=source.id, **kw)
    settle(s)
    return source


def chosen(s, name):
    d = s.state.rules.decision
    return next(o.id for o in d.options if s.state.cards[o.id].name == name)


def accept(s):
    if s.state.rules.decision.resume["step"] == "search_may":
        answer(s, ["yes"])


def find(s, name):
    answer(s, [chosen(s, name)])


def count_shuffle(s):
    return sum(
        1
        for a in s.history.actions
        for step in (getattr(a, "r", None) or [])
        if isinstance(step, dict) and step.get("type") == "shuffle"
    )


@pytest.mark.parametrize(
    "name,picks,to",
    [
        ("Alpine Houndmaster", ["Alpine Watchdog", "Igneous Cur"], "hand"),
        ("Nissa's Encouragement", ["Forest", "Brambleweft Behemoth", "Nissa, Genesis Mage"], "hand"),
        ("Journey for the Elixir", ["Forest", "Jiang Yanggu"], "hand"),
        ("Firemind's Foresight", ["Disallow", "Counterspell", "Unsummon"], "hand"),
    ],
)
def test_fixed_slots_actual_gameplay(cards, name, picks, to):
    s = setup(cards)
    before = count_shuffle(s)
    cast(s, name)
    accept(s)
    found = []
    for pick in picks:
        d = s.state.rules.decision
        if name == "Firemind's Foresight" and pick == "Cultivate":
            # Actual instant MV3, not a sorcery sharing that mana value.
            assert not any(s.state.cards[o.id].name == "Cultivate" for o in d.options)
            answer(s, [])
            continue
        cid = chosen(s, pick)
        found.append(cid)
        answer(s, [cid])
    assert all(s.state.cards[c].zone == "p1:" + to for c in found)
    assert count_shuffle(s) == before + 1
    roundtrip(s)


@pytest.mark.parametrize(
    "name,first,second",
    [
        ("Nissa's Encouragement", "Brambleweft Behemoth", "Nissa, Genesis Mage"),
        ("Journey for the Elixir", "Jiang Yanggu", None),
    ],
)
def test_multizone_slots_use_each_own_selector_in_graveyard(cards, name, first, second):
    s = setup(cards)
    a = put(s, first, "graveyard")
    b = put(s, second, "graveyard") if second else None
    cast(s, name)
    d = s.state.rules.decision
    assert a.id not in {o.id for o in d.options}
    find(s, "Forest")
    assert a.id in {o.id for o in s.state.rules.decision.options}
    answer(s, [a.id])
    if b:
        assert b.id in {o.id for o in s.state.rules.decision.options}
        answer(s, [b.id])
    assert s.state.cards[a.id].zone == "p1:hand"
    roundtrip(s)


def test_agency_outfitter_multi_zone_packet_enters_together(cards):
    s = setup(cards)
    glass = put(s, "Magnifying Glass", "graveyard")
    cap = put(s, "Thinking Cap", "hand")
    before = count_shuffle(s)
    cast(s, "Agency Outfitter")
    assert s.state.rules.decision.resume["step"] == "search_zones"
    answer(s, ["graveyard+hand"])
    assert glass.id in {o.id for o in s.state.rules.decision.options}
    assert cap.id not in {o.id for o in s.state.rules.decision.options}
    answer(s, [glass.id])
    assert s.state.cards[glass.id].zone == "p1:graveyard"
    answer(s, [cap.id])
    assert s.state.cards[glass.id].zone == s.state.cards[cap.id].zone == "p1:battlefield"
    assert count_shuffle(s) == before
    roundtrip(s)


def test_secret_salvage_target_name_exile_and_many_hand(cards):
    s = setup(cards)
    source = put(s, "Forest", "graveyard")
    bad = put(s, "Sol Ring", "graveyard")
    cast(s, "Secret Salvage", targets=[bad.id])
    assert bad.zone == "p1:exile"
    d = s.state.rules.decision
    assert all(s.state.cards[o.id].name == "Sol Ring" for o in d.options)
    found = [o.id for o in d.options]
    assert d.min_choices == 0
    assert d.max_choices >= 2
    assert len(found) >= 2
    answer(s, found)
    assert all(s.state.cards[cid].zone == "p1:hand" for cid in found)
    assert source.zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("hellbent", [False, True])
def test_infernal_tutor_resolution_branch(cards, hellbent):
    s = setup(cards)
    for c in list(s.state.cards.values()):
        if c.zone == "p1:hand":
            act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    ref = put(s, "Sol Ring", "hand") if not hellbent else None
    cast(s, "Infernal Tutor")
    if ref:
        d = s.state.rules.decision
        assert d.resume["step"] == "qualified_search_prepare"
        answer(s, [ref.id])
        assert ref.zone == "p1:hand"
        assert all(s.state.cards[o.id].name == "Sol Ring" for o in s.state.rules.decision.options)
        cid = chosen(s, "Sol Ring")
        answer(s, [cid])
        assert s.state.cards[cid].zone == "p1:hand"
        assert not s.state.cards[ref.id].revealed_to
    else:
        assert any(s.state.cards[o.id].name == "Forest" for o in s.state.rules.decision.options)
        find(s, "Forest")
    roundtrip(s)


def test_assembly_hall_reveal_one_creature_not_whole_hand(cards):
    s = setup(cards)
    source = put(s, "Assembly Hall", "battlefield")
    creature = put(s, "Alpine Watchdog", "hand")
    ring = put(s, "Sol Ring", "hand")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{4}"))
    settle(s)
    d = s.state.rules.decision
    assert creature.id in {o.id for o in d.options} and ring.id not in {o.id for o in d.options}
    answer(s, [creature.id])
    assert s.state.cards[creature.id].revealed_to and not s.state.cards[ring.id].revealed_to
    assert all(s.state.cards[o.id].name == "Alpine Watchdog" for o in s.state.rules.decision.options)
    answer(s, [])
    assert not s.state.cards[creature.id].revealed_to
    roundtrip(s)


def test_mishra_event_spell_name_and_graveyard_only_search(cards):
    s = setup(cards)
    put(s, "Mishra, Artificer Prodigy", "battlefield")
    ring = put(s, "Sol Ring", "graveyard")
    # There is a second actual Sol Ring in p2 library; use a copied deck card owned by p1 for the cast.
    other = next(
        c for c in s.state.cards.values() if c.name == "Sol Ring" and c.owner == "p1" and c.id != ring.id
    )
    act(s, "p1", type="move", card_ids=[other.id], to={"zone": "hand"})
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=other.id)
    settle(s)
    answer(s, ["graveyard"])
    assert ring.id in {o.id for o in s.state.rules.decision.options}
    answer(s, [ring.id])
    assert s.state.cards[ring.id].zone == "p1:battlefield"
    roundtrip(s)


def test_doubling_chant_names_and_one_final_shuffle(cards):
    s = setup(cards)
    put(s, "Alpine Watchdog", "battlefield")
    put(s, "Igneous Cur", "battlefield")
    before = count_shuffle(s)
    cast(s, "Doubling Chant")
    accept(s)
    for name in ["Alpine Watchdog", "Igneous Cur"]:
        assert all(s.state.cards[o.id].name == name for o in s.state.rules.decision.options)
        answer(s, [])
    assert count_shuffle(s) == before + 1
    roundtrip(s)


def test_clarion_choose_then_private_slots(cards):
    s = setup(cards)
    land = put(s, "Forest", "battlefield")
    ring = put(s, "Sol Ring", "battlefield")
    before = count_shuffle(s)
    cast(s, "Clarion Ultimatum")
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {land.id, ring.id}
    answer(s, [land.id, ring.id])
    accept(s)
    find(s, "Forest")
    answer(s, [])
    assert sum(c.name == "Forest" and c.zone == "p1:battlefield" for c in s.state.cards.values()) == 2
    assert count_shuffle(s) == before + 1
    roundtrip(s)


def test_verdant_crescendo_first_enters_before_second_search(cards):
    s = setup(cards)
    before = count_shuffle(s)
    cast(s, "Verdant Crescendo")
    find(s, "Forest")
    assert any(c.name == "Forest" and c.zone == "p1:battlefield" and c.tapped for c in s.state.cards.values())
    assert count_shuffle(s) == before
    find(s, "Nissa, Nature's Artisan")
    assert count_shuffle(s) == before + 1
    roundtrip(s)


@pytest.mark.parametrize("find_cards", [False, True])
def test_gaea_balance_five_paid_lands_distinct_type_slots(cards, find_cards):
    s = setup(cards)
    lands = [put(s, n, "battlefield") for n in ["Plains", "Island", "Swamp", "Mountain", "Forest"]]
    source = put(s, "Gaea's Balance", "hand")
    mana(s, G=1, C=3)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=source.id,
        cost_choices=[{"component": 0, "cards": [c.id for c in lands]}],
    )
    settle(s)
    found = []
    for n in ["Plains", "Island", "Swamp", "Mountain", "Forest"]:
        d = s.state.rules.decision
        assert all(n in s.cards.resolve(s.state.cards[o.id].name)["type_line"] for o in d.options)
        ids = [chosen(s, n)] if find_cards else []
        found.extend(ids)
        answer(s, ids)
    assert all(s.state.cards[cid].zone == "p1:battlefield" for cid in found)
    assert all(c.zone == "p1:graveyard" for c in lands)
    roundtrip(s)


@pytest.mark.parametrize("pay", [False, True])
def test_canoptek_combat_payment_precedes_land_choice(cards, pay):
    s = setup(cards)
    source = put(s, "Canoptek Wraith", "battlefield")
    land = put(s, "Forest", "battlefield")
    to_phase(s, "main1", turn=4)
    mana(s, C=3)
    for _ in range(40):
        d = s.state.rules.decision
        if d and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    for _ in range(80):
        d = s.state.rules.decision
        if d and d.resume.get("step") == "pay_or_sacrifice":
            break
        if s.state.rules.stack:
            mana(s, C=3)
            settle(s)
            break
        if d and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d:
            raise AssertionError(d)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.decision.resume["step"] == "pay_or_sacrifice"
    before = count_shuffle(s)
    answer(s, ["pay" if pay else "decline"])
    if pay:
        assert s.state.cards[source.id].zone == "p1:graveyard"
        assert s.state.rules.decision.resume["step"] == "qualified_search_prepare"
        answer(s, [land.id])
        assert all(s.state.cards[o.id].name == "Forest" for o in s.state.rules.decision.options)
        ids = [o.id for o in s.state.rules.decision.options][:2]
        answer(s, ids)
        assert all(s.state.cards[c].zone == "p1:battlefield" and s.state.cards[c].tapped for c in ids)
        assert count_shuffle(s) == before + 1
    else:
        assert s.state.cards[source.id].zone == "p1:battlefield"
        assert s.state.rules.decision is None
        assert count_shuffle(s) == before
    roundtrip(s)


def test_one_search_agent_diverts_only_after_packet_selection(cards):
    s = setup(cards)
    put(s, "Opposition Agent", "battlefield", pid="p2")
    put(s, "Alpine Watchdog", "battlefield")
    put(s, "Igneous Cur", "battlefield")
    cast(s, "Doubling Chant")
    accept(s)
    d = s.state.rules.decision
    assert d.decider == "p2"
    cid = d.options[0].id
    roundtrip(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[cid])
    settle(s)
    assert s.state.cards[cid].zone == "p1:library"
    d = s.state.rules.decision
    assert d.decider == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.cards[cid].zone == "p1:exile"
    assert any(p.card == cid and p.player == "p2" for p in s.state.rules.permissions)
    roundtrip(s)


def test_repeated_search_forbidden_skips_each_optional_search(cards):
    s = setup(cards)
    put(s, "Stranglehold", "battlefield", pid="p2")
    put(s, "Alpine Watchdog", "battlefield")
    before = count_shuffle(s)
    cast(s, "Doubling Chant")
    assert s.state.rules.decision is None
    assert count_shuffle(s) == before + 1
    roundtrip(s)


def test_duplicate_creature_names_keep_separate_distinct_slots(cards):
    s = setup(cards)
    arbors = [c.id for c in s.state.cards.values() if c.name == "Dryad Arbor" and c.owner == "p1"]
    for cid in arbors[:2]:
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "battlefield"})
    cast(s, "Doubling Chant")
    selected = []
    accept(s)
    for _ in range(2):
        cid = chosen(s, "Dryad Arbor")
        assert cid not in selected
        selected.append(cid)
        answer(s, [cid])
        if len(selected) == 1:
            assert s.state.cards[cid].zone == "p1:library"
    assert all(s.state.cards[cid].zone == "p1:battlefield" for cid in selected)
    roundtrip(s)


def test_assembly_hall_reference_split_card_name_groups(cards):
    # Infernal Tutor can reveal a split card: either of its names matches.
    s = setup(cards)
    ref = put(s, "Fire // Ice", "hand")
    cast(s, "Infernal Tutor")
    answer(s, [ref.id])
    e = s.state.rules.decision.resume["e"]
    assert e["name_in"] == ["Fire", "Ice"]
    answer(s, [])
    roundtrip(s)


def test_assembly_hall_derived_hand_creature_includes_grist(cards):
    s = setup(cards)
    source = put(s, "Assembly Hall", "battlefield")
    grist = put(s, "Grist, the Hunger Tide", "hand")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{4}"))
    settle(s)
    assert grist.id in {o.id for o in s.state.rules.decision.options}
    answer(s, [grist.id])
    answer(s, [])
    roundtrip(s)


def test_search_public_graveyard_only_must_find_qualified_available_card(cards):
    s = setup(cards)
    put(s, "Mishra, Artificer Prodigy", "battlefield")
    ring = put(s, "Sol Ring", "graveyard")
    other = next(
        c for c in s.state.cards.values() if c.name == "Sol Ring" and c.owner == "p1" and c.id != ring.id
    )
    act(s, "p1", type="move", card_ids=[other.id], to={"zone": "hand"})
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=other.id)
    settle(s)
    answer(s, ["graveyard"])
    d = s.state.rules.decision
    assert d.min_choices == 1
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    assert s.state.model_dump(mode="json") == before
    answer(s, [ring.id])
    roundtrip(s)


@pytest.mark.parametrize("name", ["Alpine Houndmaster", "Nissa's Encouragement", "Journey for the Elixir"])
def test_native_mindcensor_applies_same_top_four_to_all_slots(cards, name):
    from tests.test_rules_refused_look import stack_library

    s = setup(cards)
    put(s, "Aven Mindcensor", "battlefield", pid="p2")
    top = stack_library(
        s,
        ["Forest", "Swamp", "Mountain", "Plains", "Alpine Watchdog", "Jiang Yanggu", "Brambleweft Behemoth"],
    )
    cast(s, name)
    accept(s)
    while s.state.rules.decision:
        assert all(o.id in top[:4] for o in s.state.rules.decision.options)
        answer(s, [])
    roundtrip(s)


def test_firemind_repeated_process_moves_each_before_next_without_shuffle(cards):
    s = setup(cards)
    before = count_shuffle(s)
    cast(s, "Firemind's Foresight")
    first = chosen(s, "Disallow")
    answer(s, [first])
    assert s.state.cards[first].zone == "p1:hand"
    assert count_shuffle(s) == before
    second = chosen(s, "Counterspell")
    answer(s, [second])
    assert s.state.cards[second].zone == "p1:hand"
    assert count_shuffle(s) == before
    find(s, "Unsummon")
    assert count_shuffle(s) == before + 1
    roundtrip(s)


def test_secret_salvage_illegal_target_fizzles_before_search(cards):
    s = setup(cards)
    ref = put(s, "Sol Ring", "graveyard")
    source = put(s, "Secret Salvage", "hand")
    mana(s, C=3, B=2)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[ref.id])
    act(s, "p1", type="move", card_ids=[ref.id], to={"zone": "exile"})
    before = count_shuffle(s)
    settle(s)
    assert s.state.rules.decision is None
    assert count_shuffle(s) == before
    roundtrip(s)


def test_assembly_source_departure_does_not_cancel_linked_reveal_search(cards):
    s = setup(cards)
    source = put(s, "Assembly Hall", "battlefield")
    ref = put(s, "Alpine Watchdog", "hand")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{4}"))
    act(s, "p1", type="move", card_ids=[source.id], to={"zone": "graveyard"})
    settle(s)
    answer(s, [ref.id])
    cid = chosen(s, "Alpine Watchdog")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:hand"
    assert not s.state.cards[ref.id].revealed_to
    roundtrip(s)


def test_packet_creatures_use_real_entry_replacement(cards):
    s = setup(cards)
    source = put(s, "Dryad Arbor", "battlefield")
    put(s, "Containment Priest", "battlefield", pid="p2")
    cast(s, "Doubling Chant")
    answer(s, ["yes"])
    cid = chosen(s, "Dryad Arbor")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:exile"
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_mishra_cold_session_resumes_exact_zone_and_controller(cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    s = setup(cards)
    source = put(s, "Mishra, Artificer Prodigy", "battlefield")
    ring = put(s, "Sol Ring", "graveyard")
    other = next(
        c for c in s.state.cards.values() if c.name == "Sol Ring" and c.owner == "p1" and c.id != ring.id
    )
    act(s, "p1", type="move", card_ids=[other.id], to={"zone": "hand"})
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=other.id)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    settle(s)
    cold = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    answer(cold, ["graveyard"])
    answer(cold, [ring.id])
    assert cold.state.cards[ring.id].zone == "p1:battlefield"
    assert cold.state.cards[source.id].controller == "p2"
    roundtrip(cold)


def test_reveal_choice_privacy_rest_and_websocket(cards, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    ref = put(s, "Fire // Ice", "hand")
    other = put(s, "Sol Ring", "hand")
    cast(s, "Infernal Tutor")
    with TestClient(create_app(settings)) as client:
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
                answer(s, [ref.id])
            elif stage == 2:
                answer(s, [])
            for token in [bob, spec]:
                response = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": token})
                assert response.status_code == 200
                with client.websocket_connect(f"/ws/games/{gid}?token={token}") as ws:
                    frame = ws.receive_json()
                for raw in [response.text, json.dumps(frame)]:
                    assert (ref.id in raw) == (stage == 1)
                    assert other.id not in raw
    roundtrip(s)


@pytest.mark.parametrize("name", ["Doubling Chant", "Clarion Ultimatum"])
def test_for_each_wording_is_one_actual_search_event(cards, name):
    s = setup(cards)
    put(s, "Archivist of Oghma", "battlefield", pid="p2")
    put(s, "Alpine Watchdog", "battlefield")
    put(s, "Igneous Cur", "battlefield")
    before = len(s.state.zones["p2:hand"])
    cast(s, name)
    if name == "Clarion Ultimatum":
        answer(s, [o.id for o in s.state.rules.decision.options])
    accept(s)
    answer(s, [])
    answer(s, [])
    assert len(s.state.zones["p2:hand"]) == before + 1
    roundtrip(s)


@pytest.mark.parametrize("answer_search", [False, True])
def test_doubling_zero_creatures_optional_search_mandatory_shuffle(cards, answer_search):
    s = setup(cards)
    put(s, "Archivist of Oghma", "battlefield", pid="p2")
    before = count_shuffle(s)
    hand = len(s.state.zones["p2:hand"])
    cast(s, "Doubling Chant")
    answer(s, ["yes" if answer_search else "no"])
    if answer_search:
        answer(s, [])
    assert count_shuffle(s) == before + 1
    assert len(s.state.zones["p2:hand"]) == hand + int(answer_search)
    roundtrip(s)


def test_clarion_found_nonpermanent_with_token_name_stays_in_library(cards):
    from tests.test_rules_conditionals import token_of

    s = setup(cards)
    illusion = token_of(s, "p1", "Illusion", "Token Creature — Illusion", "1/1")
    cast(s, "Clarion Ultimatum")
    answer(s, [illusion.id])
    accept(s)
    cid = chosen(s, "Illusion // Reality")
    answer(s, [cid])
    assert any(
        c.name == "Illusion // Reality" and c.owner == "p1" and c.zone == "p1:library"
        for c in s.state.cards.values()
    )
    assert not any(
        c.name == "Illusion // Reality" and c.zone == "p1:battlefield" for c in s.state.cards.values()
    )
    roundtrip(s)


@pytest.mark.parametrize("wrong", ["opponent", "land"])
def test_secret_salvage_cannot_target_wrong_owner_or_land(cards, wrong):
    s = setup(cards)
    target = put(
        s,
        "Magnifying Glass" if wrong == "opponent" else "Forest",
        "graveyard",
        pid="p2" if wrong == "opponent" else "p1",
    )
    source = put(s, "Secret Salvage", "hand")
    mana(s, C=3, B=2)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, targets=[target.id])
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


@pytest.mark.parametrize("name", ["Firemind's Foresight", "Verdant Crescendo"])
def test_multiple_search_instructions_before_one_shuffle_emit_one_search(cards, name):
    # CR701.23h: before a shuffle this is a single library search, despite the repeated wording.
    s = setup(cards)
    put(s, "Archivist of Oghma", "battlefield", pid="p2")
    before = len(s.state.zones["p2:hand"])
    cast(s, name)
    if name == "Verdant Crescendo":
        find(s, "Forest")
        find(s, "Nissa, Nature's Artisan")
    else:
        for card_name in ["Disallow", "Counterspell", "Unsummon"]:
            find(s, card_name)
    assert len(s.state.zones["p2:hand"]) == before + 1
    roundtrip(s)


@pytest.mark.parametrize("name", ["Firemind's Foresight", "Verdant Crescendo"])
def test_one_search_reuses_original_mindcensor_portion_after_first_card_moves(cards, name):
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.test_rules_refused_look import stack_library

    s = setup(cards)
    put(s, "Aven Mindcensor", "battlefield", pid="p2")
    put(s, "Archivist of Oghma", "battlefield", pid="p2")
    before = len(s.state.zones["p2:hand"])
    if name == "Firemind's Foresight":
        top = stack_library(s, ["Disallow", "Counterspell", "Sol Ring", "Plains", "Unsummon"])
        cast(s, name)
        answer(s, [top[0]])
        assert current_zone(s, top[0]) == "p1:hand"
    else:
        top = stack_library(s, ["Forest", "Sol Ring", "Counterspell", "Unsummon", "Nissa, Nature's Artisan"])
        cast(s, name)
        answer(s, [top[0]])
        assert current_zone(s, top[0]) == "p1:battlefield"
    cold = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)
    if name == "Firemind's Foresight":
        answer(cold, [top[1]])
    assert top[4] not in {o.id for o in cold.state.rules.decision.options}
    assert not cold.state.rules.decision.options
    answer(cold, [])
    assert len(cold.state.zones["p2:hand"]) == before + 1
    roundtrip(cold)


def current_zone(s, cid):
    return s.state.cards[cid].zone


@pytest.mark.parametrize("name", ["Firemind's Foresight", "Verdant Crescendo"])
def test_combined_search_retains_agent_chooser_and_original_portion(cards, name):
    from tests.test_rules_refused_look import stack_library

    s = setup(cards)
    put(s, "Opposition Agent", "battlefield", pid="p2")
    put(s, "Aven Mindcensor", "battlefield", pid="p2")
    if name == "Firemind's Foresight":
        top = stack_library(s, ["Disallow", "Counterspell", "Sol Ring", "Plains", "Unsummon"])
    else:
        top = stack_library(s, ["Forest", "Sol Ring", "Counterspell", "Unsummon", "Nissa, Nature's Artisan"])
    cast(s, name)
    d = s.state.rules.decision
    assert d.decider == "p2"
    roundtrip(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[top[0]])
    settle(s)
    assert current_zone(s, top[0]) == "p1:exile"
    if name == "Firemind's Foresight":
        d = s.state.rules.decision
        assert d.decider == "p2"
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[top[1]])
        settle(s)
    d = s.state.rules.decision
    assert d.decider == "p2"
    assert not d.options
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert any(p.card == top[0] and p.player == "p2" for p in s.state.rules.permissions)
    roundtrip(s)
