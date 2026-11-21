"""Canonical positive gameplay for reveal/exile packets and native continuations."""

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
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_ordered_tutor_continuations import cast
from tests.test_rules_qualified_attached_tutors import cold
from tests.test_rules_refused_look import stack_library
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase
from tests.conftest import claim_host

DATA = Path(__file__).parent / "fixtures/reveal_cast_packet_cards.json"
NAMES = [c["name"] for c in json.loads(DATA.read_text())][:16]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads(DATA.read_text())):
        base[c["name"]] = card(
            c["name"], set_code="rcp", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns = [c["name"] for c in json.loads(DATA.read_text())]
    s = table(cards, [*ns, "Forest", "Island", "Plains"], ns, ns)
    to_phase(s, "main1", turn=1)
    return s


def only_library(s, pid, names):
    ids = list(s.state.zones[pid + ":library"])
    if ids:
        act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "exile"})
    return stack_library(s, names, pid=pid)


@pytest.mark.parametrize("name", NAMES)
def test_canonical_full(cards, name):
    got = coverage.of_card_data(cards.resolve(name))
    assert got.level == "FULL", got


def test_reweave_actual_artifact_sacrifice_then_shared_permanent_entry(cards):
    s = setup(cards)
    target = put(s, "Sol Ring", "battlefield", "p2")
    top = stack_library(s, ["Forest", "Memnite"], pid="p2")
    cast(s, "Reweave", targets=[target.id])
    assert s.state.cards[target.id].zone == "p2:graveyard"
    assert s.state.cards[top[1]].zone == "p2:battlefield"
    roundtrip(s)


def test_blessed_actual_exile_then_owner_entry_and_rebound(cards):
    s = setup(cards)
    target = put(s, "Grizzly Bears", "battlefield", "p2")
    top = stack_library(s, ["Forest", "Shivan Dragon"], pid="p2")
    source = cast(s, "Blessed Reincarnation", targets=[target.id])
    assert s.state.cards[target.id].zone == "p2:exile"
    assert s.state.cards[top[1]].zone == "p2:battlefield"
    assert s.state.cards[source.id].zone == "p1:exile"
    roundtrip(s)


def test_collision_actual_all_owners_shuffle_then_atomic_entries(cards):
    s = setup(cards)
    put(s, "Grizzly Bears", "battlefield")
    put(s, "Memnite", "battlefield", "p2")
    only_library(s, "p1", ["Forest"])
    only_library(s, "p2", ["Island"])
    cast(s, "Collision of Realms")
    assert (
        len([c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield"])
        == 1
    )
    assert len([c for c in s.state.cards.values() if c.name == "Memnite" and c.zone == "p2:battlefield"]) == 1
    roundtrip(s)


def test_mirror_actual_source_shuffle_returns_named_body(cards):
    s = setup(cards)
    source = put(s, "Mirror-Mad Phantasm", "battlefield")
    only_library(s, "p1", ["Forest", "Island"])
    mana(s, C=1, U=1)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{1}"))
    settle(s)
    assert (
        len(
            [
                c
                for c in s.state.cards.values()
                if c.name == "Mirror-Mad Phantasm" and c.zone == "p1:battlefield"
            ]
        )
        == 1
    )
    roundtrip(s)


def test_spellshift_actual_uncast_found_shuffles_after_decline_cold(cards):
    s = setup(cards)
    target = put(s, "Lightning Bolt", "hand", "p2")
    source = put(s, "Spellshift", "hand")
    stack_library(s, ["Forest", "Counterspell"], pid="p2")
    mana(s, R=1)
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    act(s, "p2", type="set_prefs", hold_priority=True)
    while s.state.rules.priority != "p2":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=target.id, targets=["p1"])
    while s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    mana(s, C=2, U=2)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[target.id])
    settle(s)
    s = cold(s, cards)
    assert s.state.rules.decision.player == "p2"
    answer(s, [])
    assert s.state.cards[target.id].zone == "p2:graveyard"
    assert any(c.name == "Counterspell" and c.zone == "p2:library" for c in s.state.cards.values())
    roundtrip(s)


def test_creative_actual_optional_demonstrate_then_free_creature(cards):
    s = setup(cards)
    only_library(s, "p1", ["Forest", "Grizzly Bears"])
    cast(s, "Creative Technique")
    answer(s, ["no"])
    s = cold(s, cards)
    d = s.state.rules.decision
    assert d is not None
    chosen = next(o.id for o in d.options if o.card_id is not None)
    answer(s, [chosen])
    assert any(c.name == "Grizzly Bears" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    roundtrip(s)


def test_storm_actual_cast_hand_replaced_with_shared_type_creature(cards):
    s = setup(cards)
    put(s, "Possibility Storm", "battlefield")
    top = stack_library(s, ["Forest", "Shivan Dragon"])
    source = cast(s, "Grizzly Bears")
    assert s.state.cards[source.id].zone == "p1:exile"
    answer(s, [top[1]])
    assert s.state.cards[top[1]].zone == "p1:battlefield"
    assert not any(c.name == "Grizzly Bears" and c.zone == "p1:exile" for c in s.state.cards.values())
    roundtrip(s)


def test_loki_actual_first_qualifying_cast_difference_damage_and_offer(cards):
    s = setup(cards)
    put(s, "Lady Loki, Agent of Chaos", "battlefield")
    top = stack_library(s, ["Forest", "Shivan Dragon"])
    before = s.state.players["p2"].life
    cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.players["p2"].life == before - 5
    answer(s, [top[1]])
    assert s.state.cards[top[1]].zone == "p1:battlefield"
    roundtrip(s)


def test_guff_actual_each_controller_packet_casts_after_all_reveals(cards):
    s = setup(cards)
    a = put(s, "Memnite", "battlefield")
    b = put(s, "Grizzly Bears", "battlefield", "p2")
    c = put(s, "Sol Ring", "battlefield", "p3")
    only_library(s, "p1", ["Forest"])
    only_library(s, "p2", ["Island"])
    only_library(s, "p3", ["Plains"])
    cast(s, "Guff Rewrites History", targets=[a.id, b.id, c.id], target_counts=[1, 1, 1])
    s = cold(s, cards)
    for pid, _n in [("p1", "Memnite"), ("p2", "Grizzly Bears"), ("p3", "Sol Ring")]:
        d = s.state.rules.decision
        assert d.player == pid
        assert all(
            any(c.name == name and c.zone == owner + ":exile" for c in s.state.cards.values())
            for owner, name in [("p1", "Memnite"), ("p2", "Grizzly Bears"), ("p3", "Sol Ring")]
            if owner >= pid
        )
        answer(s, [next(o.id for o in d.options if o.card_id is not None)])
    assert all(
        any(c.name == n and c.zone == p + ":battlefield" for c in s.state.cards.values())
        for p, n in [("p1", "Memnite"), ("p2", "Grizzly Bears"), ("p3", "Sol Ring")]
    )
    roundtrip(s)


def test_pod_actual_exiles_stack_spell_cost_and_exact_mana_value(cards):
    s = setup(cards)
    pod = put(s, "Synthesis Pod", "battlefield")
    original = put(s, "Grizzly Bears", "hand")
    top = stack_library(s, ["Forest", "Nadir Kraken"], pid="p2")
    mana(s, C=10, G=1, U=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=original.id)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=pod.id,
        ability=ability(s, pod, "{1}"),
        targets=["p2"],
        life_symbols=[],
    )
    settle(s)
    if any(o.id == original.id for o in s.state.rules.decision.options):
        answer(s, [original.id])
    assert s.state.cards[original.id].zone == "p1:exile" and s.state.cards[pod.id].tapped
    answer(s, [top[1]])
    assert s.state.cards[top[1]].zone == "p1:battlefield" and s.state.cards[top[1]].owner == "p2"
    roundtrip(s)


def test_bruntar_actual_landfall_timed_normal_cost_source_independent(cards):
    s = setup(cards)
    source = put(s, "Territorial Bruntar", "battlefield")
    top = stack_library(s, ["Forest", "Memnite"])
    land = put(s, "Island", "hand")
    act(s, "p1", type="play_land", card_id=land.id)
    settle(s)
    assert s.state.cards[top[0]].zone == "p1:exile" and s.state.cards[top[1]].zone == "p1:exile"
    cast(s, "Murder", targets=[source.id])
    act(s, "p1", type="cast_spell", card_id=top[1])
    settle(s)
    assert s.state.cards[top[1]].zone == "p1:battlefield"
    roundtrip(s)


def test_bolas_actual_plus_two_foreign_card_free_timed_permission(cards):
    s = setup(cards)
    source = cast(s, "Nicol Bolas, God-Pharaoh")
    top = stack_library(s, ["Forest", "Memnite"], pid="p2")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "+2"), targets=["p2"])
    settle(s)
    assert s.state.cards[top[1]].zone == "p2:exile"
    s = cold(s, cards)
    act(s, "p1", type="cast_spell", card_id=top[1], free=True)
    settle(s)
    assert s.state.cards[top[1]].zone == "p1:battlefield"
    roundtrip(s)


def test_doctor_actual_all_four_natural_chapters_and_last_optional_instruction(cards):
    s = setup(cards)
    top = stack_library(s, ["Forest", "Lonis, Cryptozoologist"])
    source = cast(s, "The Day of the Doctor")
    assert s.state.cards[top[1]].zone == "p1:exile"
    mana(s, G=1, U=1)
    act(s, "p1", type="cast_spell", card_id=top[1])
    settle(s)
    assert s.state.cards[top[1]].zone == "p1:battlefield"
    for turn, n in [(4, "Krenko, Mob Boss"), (7, "Amareth, the Lustrous")]:
        top2 = stack_library(s, ["Island", "Plains", n])
        to_phase(s, "main1", turn=turn)
        settle(s)
        assert s.state.cards[top2[2]].zone == "p1:exile"
    protected = put(s, "Universal Automaton", "battlefield", "p2")
    noncreature = put(s, "Firdoch Core", "battlefield", "p3")
    before = s.state.players["p1"].life
    to_phase(s, "main1", turn=10)
    settle(s)
    s = cold(s, cards)
    assert s.state.rules.decision.resume["step"] == "return_choice"
    assert {protected.id, noncreature.id} <= {o.id for o in s.state.rules.decision.options}
    answer(s, [protected.id, noncreature.id])
    answer(s, ["pay"])
    assert s.state.players["p1"].life == before - 13
    assert s.state.cards[protected.id].zone == "p2:battlefield"
    assert s.state.cards[noncreature.id].zone == "p3:battlefield"
    assert s.state.cards[top[1]].zone == "p1:exile"
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def test_flamesage_actual_attack_power_capped_spell_exile_then_cast(cards):
    s = setup(cards)
    source = put(s, "Keldon Flamesage", "battlefield")
    put(s, "Fervor", "battlefield")
    top = stack_library(s, ["Lightning Bolt", "Forest"])
    to_phase(s, "declare_attackers", turn=1)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    settle(s)
    if s.state.rules.decision.resume["step"] != "pick_looked":
        answer(s, [])
    answer(s, [top[0]])
    answer(s, [top[0]])
    answer(s, ["p2"])
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_kiora_actual_hand_kraken_spell_event_less_than_mana_value(cards):
    s = setup(cards)
    put(s, "Kiora, Sovereign of the Deep", "battlefield")
    top = stack_library(s, ["Forest", "Memnite", "Shivan Dragon"])
    cast(s, "Nadir Kraken")
    assert {o.card_id for o in s.state.rules.decision.options if o.card_id is not None} == {top[1]}
    answer(s, [top[1]])
    assert s.state.cards[top[1]].zone == "p1:battlefield"
    roundtrip(s)


def test_discover_actual_private_face_down_noninstant_to_hand_cold(cards):
    s = setup(cards)
    top = stack_library(s, ["Forest", "Grizzly Bears", "Island", "Sol Ring", "Memnite"])
    cast(s, "Discover the Impossible")
    s = cold(s, cards)
    answer(s, [top[1]])
    assert s.state.rules.decision.resume["step"] == "free_cast_pick"
    assert not s.state.rules.decision.options
    answer(s, [])
    assert any(
        c.name == "Grizzly Bears" and c.zone == "p1:hand" and not c.face_down for c in s.state.cards.values()
    )
    assert all(c not in json.dumps(s.view("p2")["cards"]) for c in top)
    roundtrip(s)


@pytest.mark.parametrize("prefix", ["+1", "−4", "−12"])
def test_bolas_other_three_canonical_loyalty_effects(cards, prefix):
    s = setup(cards)
    put(s, "Doubling Season", "battlefield")
    source = cast(s, "Nicol Bolas, God-Pharaoh")
    assert s.state.cards[source.id].counters["loyalty"] == 14
    bear = put(s, "Grizzly Bears", "battlefield", "p2")
    ring = put(s, "Sol Ring", "battlefield", "p2")
    forest = put(s, "Forest", "battlefield", "p2")
    if prefix == "+1":
        for p in ["p2", "p3"]:
            put(s, "Island", "hand", p)
            put(s, "Plains", "hand", p)
        before = {p: len(s.state.zones[p + ":hand"]) for p in ["p2", "p3"]}
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, prefix),
        **({"targets": [bear.id]} if prefix == "−4" else {}),
    )
    settle(s)
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        answer(s, [o.id for o in d.options[: d.min_choices]])
    if prefix == "+1":
        assert all(len(s.state.zones[p + ":hand"]) == before[p] - 2 for p in before)
    elif prefix == "−4":
        assert s.state.cards[bear.id].zone == "p2:graveyard"
    else:
        assert s.state.cards[bear.id].zone == "p2:exile" and s.state.cards[ring.id].zone == "p2:exile"
        assert s.state.cards[forest.id].zone == "p2:battlefield"
    roundtrip(s)


def test_discover_actual_qualifying_adventure_spell_face_not_creature_front(cards):
    s = setup(cards)
    target = put(s, "Sol Ring", "battlefield", "p2")
    top = stack_library(s, ["Brazen Borrower // Petty Theft", "Forest", "Island", "Plains", "Memnite"])
    cast(s, "Discover the Impossible")
    answer(s, [top[0]])
    d = s.state.rules.decision
    assert len([o for o in d.options if o.card_id is not None]) == 1
    assert "Petty Theft" in next(o.label for o in d.options if o.card_id is not None)
    answer(s, [next(o.id for o in d.options if o.card_id is not None)])
    answer(s, [target.id])
    assert any(
        c.name == "Sol Ring" and c.owner == "p2" and c.zone == "p2:hand" for c in s.state.cards.values()
    )
    roundtrip(s)


def test_reweave_actual_splice_adds_effect_without_casting_splice_card(cards):
    s = setup(cards)
    target = put(s, "Memnite", "battlefield", "p2")
    spell = put(s, "Reach Through Mists", "hand")
    splice = put(s, "Reweave", "hand")
    top = stack_library(s, ["Forest", "Sol Ring"], pid="p2")
    mana(s, C=20, U=4, G=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, splice=[splice.id], targets=[target.id])
    settle(s)
    while s.state.rules.decision is not None:
        d = s.state.rules.decision
        answer(s, [o.id for o in d.options[: d.min_choices]])
    assert s.state.cards[splice.id].zone == "p1:hand"
    assert s.state.cards[target.id].zone == "p2:graveyard"
    assert s.state.cards[top[1]].zone == "p2:battlefield"
    roundtrip(s)


def test_collision_later_players_incoming_soul_warden_sees_first_players_entry(cards):
    s = setup(cards)
    put(s, "Memnite", "battlefield")
    put(s, "Soul Warden", "battlefield", "p2")
    only_library(s, "p1", ["Forest"])
    only_library(s, "p2", ["Island"])
    before = s.state.players["p2"].life
    cast(s, "Collision of Realms")
    assert s.state.players["p2"].life == before + 1
    roundtrip(s)


def test_blessed_large_library_no_match_public_reveal_is_native_bounded(cards):
    s = table(cards, ["Blessed Reincarnation", "Forest"], ["Grizzly Bears", *(["Forest"] * 110)], ["Island"])
    to_phase(s, "main1", turn=1)
    target = put(s, "Grizzly Bears", "battlefield", "p2")
    assert len(s.state.zones["p2:library"]) > 100
    cast(s, "Blessed Reincarnation", targets=[target.id])
    assert s.state.cards[target.id].zone == "p2:exile"
    assert not any(c.zone == "p2:battlefield" and c.name == "Forest" for c in s.state.cards.values())
    assert not any(c.revealed_to for c in s.state.cards.values() if c.zone == "p2:library")
    roundtrip(s)


def test_pod_actual_x_spell_pre_exile_mana_value_and_phyrexian_life_cold(cards):
    s = setup(cards)
    pod = put(s, "Synthesis Pod", "battlefield")
    original = put(s, "Stonecoil Serpent", "hand")
    top = stack_library(s, ["Forest", "Nadir Kraken"], pid="p2")
    mana(s, C=10)
    before = s.state.players["p1"].life
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=original.id, x_value=2)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=pod.id,
        ability=ability(s, pod, "{1}"),
        targets=["p2"],
        life_symbols=["U"],
    )
    settle(s)
    s = cold(s, cards)
    assert s.state.players["p1"].life == before - 2
    assert s.state.cards[original.id].zone == "p1:exile"
    assert {o.card_id for o in s.state.rules.decision.options if o.card_id is not None} == {top[1]}
    answer(s, [top[1]])
    assert s.state.cards[top[1]].zone == "p1:battlefield"
    roundtrip(s)


def test_mirror_actual_clone_does_not_seek_renamed_source_name(cards):
    s = setup(cards)
    source = put(s, "Mirror-Mad Phantasm", "battlefield")
    clone = cast(s, "Clone")
    answer(s, [source.id])
    cast(s, "Murder", targets=[source.id])
    only_library(s, "p1", ["Forest", "Island"])
    mana(s, C=1, U=1)
    act(
        s, "p1", type="activate_ability", card_id=clone.id, ability=ability(s, s.state.cards[clone.id], "{1}")
    )
    settle(s)
    assert not s.state.zones["p1:library"]
    assert any(c.name == "Clone" and c.zone == "p1:graveyard" for c in s.state.cards.values())
    roundtrip(s)


def test_storm_original_countered_by_actual_activated_ability_still_searches_types(cards):
    s = setup(cards)
    put(s, "Possibility Storm", "battlefield")
    glen = put(s, "Glen Elendra Archmage", "battlefield")
    source = put(s, "Lightning Bolt", "hand")
    top = stack_library(s, ["Forest", "Reach Through Mists"])
    mana(s, U=3, R=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=["p2"])
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=glen.id,
        ability=ability(s, glen, "{U}"),
        targets=[source.id],
    )
    settle(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert {o.card_id for o in s.state.rules.decision.options if o.card_id is not None} == {top[1]}
    s = cold(s, cards)
    answer(s, [])
    assert any(c.name == "Reach Through Mists" and c.zone == "p1:library" for c in s.state.cards.values())
    roundtrip(s)


def test_kiora_original_spell_countered_before_resolution_uses_cast_lki_cold(cards):
    s = setup(cards)
    put(s, "Kiora, Sovereign of the Deep", "battlefield")
    source = put(s, "Nadir Kraken", "hand")
    counter = put(s, "Counterspell", "hand")
    top = stack_library(s, ["Forest", "Memnite", "Shivan Dragon"])
    mana(s, C=3, U=5)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id)
    act(s, "p1", type="cast_spell", card_id=counter.id, targets=[source.id])
    settle(s)
    s = cold(s, cards)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert {o.card_id for o in s.state.rules.decision.options if o.card_id is not None} == {top[1]}
    answer(s, [top[1]])
    assert s.state.cards[top[1]].zone == "p1:battlefield"
    roundtrip(s)


def test_discover_private_look_face_down_offer_then_public_spell_rest_ws(cards, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    top = stack_library(s, ["Lightning Bolt", "Forest", "Island", "Plains", "Memnite"])
    cast(s, "Discover the Impossible")
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck = client.post(
            "/api/decks", json={"text": "Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest"}
        ).json()["id"]
        game = client.post(
            "/api/games",
            json={
                "mode": "lan",
                "players": [{"name": "Alice", "deck_id": deck}, {"name": "Bob", "deck_id": deck}],
            },
        ).json()
        gid = game["game"]["id"]
        token = client.post("/api/join", json={"code": game["game"]["code"], "spectate": True}).json()[
            "token"
        ]
        client.app.state.services.hub.get(gid).game = s
        for stage in range(3):
            if stage == 1:
                answer(s, [top[0]])
            elif stage == 2:
                answer(s, [next(o.id for o in s.state.rules.decision.options if o.card_id is not None)])
                answer(s, ["p2"])
            response = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": token})
            assert response.status_code == 200
            with client.websocket_connect(f"/ws/games/{gid}?token={token}") as ws:
                frame = ws.receive_json()
            for raw in [response.text, json.dumps(frame)]:
                assert ("Lightning Bolt" in raw) == (stage == 2)
                assert all(c not in raw for c in top[1:])
    assert s.state.players["p2"].life == 37
    roundtrip(s)


@pytest.mark.parametrize("replacement", ["Grafdigger's Cage", "Containment Priest"])
def test_reweave_native_entry_prohibition_or_redirection_keeps_shuffle_semantics(cards, replacement):
    s = setup(cards)
    target = put(s, "Sol Ring", "battlefield", "p2")
    put(s, replacement, "battlefield", "p3")
    stack_library(s, ["Forest", "Memnite"], pid="p2")
    cast(s, "Reweave", targets=[target.id])
    assert s.state.cards[target.id].zone == "p2:graveyard"
    assert any(
        c.name == "Memnite"
        and c.owner == "p2"
        and c.zone == ("p2:library" if replacement == "Grafdigger's Cage" else "p2:exile")
        for c in s.state.cards.values()
    )
    roundtrip(s)


def test_loki_first_qualifying_spell_ignores_prior_creature_and_second_instant(cards):
    s = setup(cards)
    put(s, "Lady Loki, Agent of Chaos", "battlefield")
    cast(s, "Memnite")
    top = stack_library(s, ["Forest", "Shivan Dragon"])
    before = s.state.players["p2"].life
    cast(s, "Lightning Bolt", targets=["p2"])
    assert s.state.players["p2"].life == before - 5
    answer(s, [])
    stack_library(s, ["Island"])
    cast(s, "Reach Through Mists")
    assert s.state.players["p2"].life == before - 5
    assert any(c.name == "Island" and c.owner == "p1" and c.zone == "p1:hand" for c in s.state.cards.values())
    assert s.state.cards[top[1]].zone == "p1:exile"
    roundtrip(s)


@pytest.mark.parametrize("kind", ["ability", "opponent_spell"])
def test_pod_cannot_exile_an_ability_or_opponents_spell_as_cost(cards, kind):
    from app.game.errors import ActionError

    s = setup(cards)
    pod = put(s, "Synthesis Pod", "battlefield")
    mana(s, C=5, U=2, R=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    if kind == "ability":
        librarian = put(s, "Orcish Librarian", "battlefield")
        s.state.rules.controlled_since[librarian.id].turn = 0
        act(s, "p1", type="activate_ability", card_id=librarian.id, ability=ability(s, librarian, "{R}"))
    else:
        spell = put(s, "Lightning Bolt", "hand", "p2")
        act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
        act(s, "p2", type="set_prefs", hold_priority=True)
        while s.state.rules.priority != "p2":
            act(s, s.state.rules.priority, type="pass_priority")
        act(s, "p2", type="cast_spell", card_id=spell.id, targets=["p1"])
        while s.state.rules.priority != "p1":
            act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=pod.id,
            ability=ability(s, pod, "{1}"),
            targets=["p2"],
            life_symbols=[],
        )
    assert not s.state.cards[pod.id].tapped
    roundtrip(s)
