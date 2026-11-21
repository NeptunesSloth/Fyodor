"""Canonical relative tutor qualifiers and ordered Aura/Equipment entry proofs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.conftest import claim_host
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
    data = json.loads((Path(__file__).parent / "fixtures/qualified_attached_tutor_cards.json").read_text())
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
    for c in json.loads((Path(__file__).parent / "fixtures/qualified_attached_tutor_cards.json").read_text())
][:15]


@pytest.mark.parametrize("name", NAMES)
def test_canonical_full(cards, name):
    got = coverage.of_card_data(cards.resolve(name))
    assert got.level == "FULL", got


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/qualified_attached_tutor_cards.json").read_text()
        )
    ]
    assert all(cards.resolve(n) is not None for n in names), [n for n in names if cards.resolve(n) is None]
    s = table(
        cards,
        [
            *names,
            "Plains",
            "Island",
            "Grizzly Bears",
            "Grizzly Bears",
            "Shivan Dragon",
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


@pytest.mark.parametrize(
    "source,found,destination",
    [
        ("Phantom Carriage", "Faithless Looting", "graveyard"),
        ("Mwonvuli Beast Tracker", "Ghalta, Primal Hunger", "library"),
        ("Auratouched Mage", "Pacifism", "battlefield"),
    ],
)
def test_actual_etb_found(cards, source, found, destination):
    s = setup(cards)
    c = cast(s, source)
    search_yes(s)
    cid = choose_named(s, found)
    answer(s, [cid])
    if destination == "library":
        assert s.state.cards[s.state.zones["p1:library"][0]].name == found
    else:
        assert s.state.cards[cid].zone == "p1:" + destination
    if source == "Auratouched Mage":
        assert s.state.cards[cid].attached_to == c.id
    roundtrip(s)


@pytest.mark.parametrize("name", ["Stonehewer Giant", "Quest for the Holy Relic"])
def test_equipment_choose_after_entry(cards, name):
    s = setup(cards)
    host = put(s, "Grizzly Bears", "battlefield")
    source = put(s, name, "battlefield")
    s.state.rules.controlled_since[source.id].turn = 0
    if name.startswith("Quest"):
        source.counters["quest"] = 5
    mana(s, C=10, W=10)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{1}{W}" if name.startswith("Stone") else "Remove five"),
    )
    settle(s)
    cid = choose_named(s, "Shadowspear")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    assert s.state.rules.decision.resume["step"] == "relative_tutor_attach"
    answer(s, [host.id])
    assert s.state.cards[cid].attached_to == host.id
    roundtrip(s)


def test_wild_pair_actual_hand_cast(cards):
    s = setup(cards)
    put(s, "Wild Pair", "battlefield")
    cast(s, "Grizzly Bears")
    search_yes(s)
    cid = choose_named(s, "Grizzly Bears")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    roundtrip(s)


def test_light_paws_actual_cast_aura(cards):
    s = setup(cards)
    source = put(s, "Light-Paws, Emperor's Voice", "battlefield")
    cast(s, "Rancor", targets=[source.id])
    search_yes(s)
    cid = choose_named(s, "Aqueous Form")
    assert all(s.state.cards[o.id].name != "Rancor" for o in s.state.rules.decision.options)
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    assert s.state.cards[cid].attached_to == source.id
    roundtrip(s)


def test_tallowisp_exact_enchant_creature(cards):
    s = setup(cards)
    put(s, "Tallowisp", "battlefield")
    cast(s, "Will-o'-the-Wisp")
    search_yes(s)
    names = {s.state.cards[o.id].name for o in s.state.rules.decision.options}
    assert "Pacifism" in names and "Threads of Disloyalty" not in names
    cid = choose_named(s, "Pacifism")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:hand"
    roundtrip(s)


def test_vivien_delayed_lesser_creature(cards):
    s = setup(cards)
    source = cast(s, "Vivien, Monsters' Advocate")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "−2"))
    settle(s)
    cast(s, "Shivan Dragon")
    cid = choose_named(s, "Grizzly Bears")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    roundtrip(s)


def test_disciple_discard_binding(cards):
    s = setup(cards)
    source = put(s, "Disciple of Deceit", "battlefield")
    put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="tap", card_ids=[source.id])
    to_phase(s, "upkeep", turn=4)
    settle(s)
    answer(s, ["pay"])
    cid = choose_named(s, "Grizzly Bears")
    answer(s, [cid])
    found = choose_named(s, "Grizzly Bears")
    answer(s, [found])
    assert s.state.cards[cid].zone == "p1:graveyard"
    assert s.state.cards[found].zone == "p1:hand"
    roundtrip(s)


def test_forging_saga_named_or_equipment(cards):
    s = setup(cards)
    cast(s, "Forging the Tyrite Sword")
    to_phase(s, "main1", turn=7)
    settle(s)
    cid = choose_named(s, "Shadowspear")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:hand"
    roundtrip(s)


def test_curse_attaches_to_enchanted_player(cards):
    s = setup(cards)
    source = cast(s, "Curse of Misfortunes", targets=["p2"])
    assert s.state.cards[source.id].attached_player == "p2", (
        s.state.cards[source.id].zone,
        s.state.rules.decision,
        s.state.zones.get("stack"),
    )
    to_phase(s, "upkeep", turn=4)
    settle(s)
    search_yes(s)
    cid = choose_named(s, "Curse of Opulence")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    assert s.state.cards[cid].attached_player == "p2"
    roundtrip(s)


def attack_one(s, source):
    s.state.rules.controlled_since[source.id].turn = 0
    for _ in range(40):
        d = s.state.rules.decision
        if d and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    settle(s)


def test_sovereigns_actual_attack_attaches(cards):
    s = setup(cards)
    put(s, "Sovereigns of Lost Alara", "battlefield")
    attacker = put(s, "Grizzly Bears", "battlefield")
    attack_one(s, attacker)
    search_yes(s)
    cid = choose_named(s, "Rancor")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    assert s.state.cards[cid].attached_to == attacker.id
    roundtrip(s)


def test_hiveheart_current_land_type_exclusion(cards):
    s = setup(cards)
    source = put(s, "Hiveheart Shaman", "battlefield")
    put(s, "Forest", "battlefield")
    attack_one(s, source)
    search_yes(s)
    assert all(s.state.cards[o.id].name != "Forest" for o in s.state.rules.decision.options)
    cid = choose_named(s, "Plains")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    roundtrip(s)


def test_evolving_door_cost_colors_paid_cast(cards):
    s = setup(cards)
    source = put(s, "Evolving Door", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    mana(s, C=10, U=10, B=10)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{1}"))
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    cid = choose_named(s, "Disciple of Deceit")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:exile"
    d = s.state.rules.decision
    assert d.resume["step"] == "free_cast_pick"
    from tests.game_helpers import mana_pool

    before = sum(mana_pool(s).values())
    answer(s, [next(o.id for o in d.options if o.card_id == cid)])
    assert sum(mana_pool(s).values()) == before - 2
    assert s.state.cards[cid].zone == "p1:battlefield"
    roundtrip(s)


def cold(s, cards):
    from app.game.session import GameSession
    from app.game.state import GameState

    return GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=cards)


def test_equipment_entry_then_attachment_cold_living_weapon(cards):
    s = setup(cards)
    host = put(s, "Grizzly Bears", "battlefield")
    source = put(s, "Quest for the Holy Relic", "battlefield")
    source.counters["quest"] = 5
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "Remove five"))
    settle(s)
    cid = choose_named(s, "Batterskull")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    assert not any(
        c.name == "Phyrexian Germ" and c.zone.endswith(":battlefield") for c in s.state.cards.values()
    )
    s = cold(s, cards)
    assert s.state.rules.decision.resume["step"] == "relative_tutor_attach"
    answer(s, [host.id])
    assert any("Germ" in c.name and c.zone.endswith(":battlefield") for c in s.state.cards.values())
    roundtrip(s)


def test_equipment_no_host_stays_unattached(cards):
    s = setup(cards)
    source = put(s, "Quest for the Holy Relic", "battlefield")
    source.counters["quest"] = 5
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "Remove five"))
    settle(s)
    cid = choose_named(s, "Shadowspear")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield" and s.state.cards[cid].attached_to is None
    assert s.state.rules.decision is None
    roundtrip(s)


def test_auratouched_bounced_uses_lki_finds_to_hand_cold(cards):
    s = setup(cards)
    source = put(s, "Auratouched Mage", "hand")
    mana(s, C=20, W=10, U=10)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id)
    for _ in range(20):
        if s.state.cards[source.id].zone == "p1:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    bounce = put(s, "Unsummon", "hand")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=bounce.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == "p1:hand"
    cid = choose_named(s, "Pacifism")
    s = cold(s, cards)
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:hand"
    assert s.state.cards[source.id].zone == "p1:hand"
    roundtrip(s)


def test_wild_pair_cage_blocks_selected_entry(cards):
    s = setup(cards)
    put(s, "Grafdigger's Cage", "battlefield")
    put(s, "Wild Pair", "battlefield")
    cast(s, "Grizzly Bears")
    search_yes(s)
    cid = choose_named(s, "Grizzly Bears")
    answer(s, [cid])
    assert not any(c.id == cid and c.zone == "p1:battlefield" for c in s.state.cards.values())
    assert sum(c.name == "Grizzly Bears" and c.zone == "p1:battlefield" for c in s.state.cards.values()) == 1
    roundtrip(s)


def test_light_paws_uncast_aura_does_not_trigger(cards):
    s = setup(cards)
    source = put(s, "Light-Paws, Emperor's Voice", "battlefield")
    aura = put(s, "Pacifism", "battlefield")
    act(s, "p1", type="attach", card_ids=[aura.id], to=source.id)
    settle(s)
    assert s.state.rules.decision is None
    roundtrip(s)


def test_native_mindcensor_only_original_top_four(cards):
    from tests.test_rules_land_or_cast import thin_library
    from tests.test_rules_refused_look import stack_library

    s = setup(cards)
    put(s, "Aven Mindcensor", "battlefield", "p2")
    thin_library(s, ["Forest", "Island", "Plains", "Memnite", "Pacifism"])
    stack_library(s, ["Forest", "Island", "Plains", "Memnite", "Pacifism"])
    cast(s, "Auratouched Mage")
    if s.state.rules.decision is not None:
        assert not s.state.rules.decision.options
        answer(s, [])
    assert not any(c.name == "Pacifism" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    roundtrip(s)


def test_wild_pair_uses_current_counter_modified_pt(cards):
    s = setup(cards)
    put(s, "Wild Pair", "battlefield")
    source = cast(s, "Triskelion")
    assert s.state.cards[source.id].counters.get("+1/+1") == 3
    search_yes(s)
    names = {s.state.cards[o.id].name for o in s.state.rules.decision.options}
    assert "Phantom Carriage" in names and "Grizzly Bears" not in names
    cid = choose_named(s, "Phantom Carriage")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    if s.state.rules.decision:
        answer(s, ["no"])
    roundtrip(s)


def test_aura_could_enchant_protection_excludes_white(cards):
    s = setup(cards)
    put(s, "Sovereigns of Lost Alara", "battlefield")
    attacker = put(s, "Black Knight", "battlefield")
    attack_one(s, attacker)
    search_yes(s)
    names = {s.state.cards[o.id].name for o in s.state.rules.decision.options}
    assert "Pacifism" not in names and "Rancor" in names
    cid = choose_named(s, "Rancor")
    answer(s, [cid])
    assert s.state.cards[cid].attached_to == attacker.id
    roundtrip(s)


def test_auratouched_last_battlefield_artifact_legality(cards):
    from app.rules.plan import Plan

    s = setup(cards)
    coating = put(s, "Liquimetal Coating", "battlefield")
    source = put(s, "Auratouched Mage", "hand")
    mana(s, C=20, W=10, U=10)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id)
    for _ in range(20):
        if s.state.cards[source.id].zone == "p1:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=coating.id,
        ability=ability(s, coating, "{T}"),
        targets=[source.id],
    )
    for _ in range(20):
        if "Artifact" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[source.id]).types:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert "Artifact" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[source.id]).types
    bounce = put(s, "Unsummon", "hand")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=bounce.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == "p1:hand"
    cid = choose_named(s, "Ensoul Artifact")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:hand"
    roundtrip(s)


def test_agent_native_authority_diverts_qualified_find(cards):
    s = setup(cards)
    put(s, "Opposition Agent", "battlefield", "p2")
    cast(s, "Mwonvuli Beast Tracker")
    d = s.state.rules.decision
    assert d.decider == "p2"
    cid = choose_named(s, "Ghalta, Primal Hunger")
    assert cid not in json.dumps(s.view("p3")["rules"]["decision"])
    s = cold(s, cards)
    act(s, "p2", type="choose", decision_id=s.state.rules.decision.id, option_ids=[cid])
    settle(s)
    assert s.state.cards[cid].zone == "p1:exile"
    assert any(g.player == "p2" and g.card == cid for g in s.state.rules.permissions)
    roundtrip(s)


def test_tallowisp_native_search_privacy_rest_ws(cards, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    put(s, "Tallowisp", "battlefield")
    cast(s, "Reach Through Mists")
    search_yes(s)
    found = choose_named(s, "Pacifism")
    hidden = [o.id for o in s.state.rules.decision.options]
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
        for stage in range(2):
            if stage:
                answer(s, [found])
                assert s.state.cards[found].zone == "p1:hand"
            for token in (bob, spec):
                response = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": token})
                assert response.status_code == 200
                with client.websocket_connect(f"/ws/games/{gid}?token={token}") as ws:
                    frame = ws.receive_json()
                for raw in (response.text, json.dumps(frame)):
                    assert all(cid not in raw for cid in hidden)
    roundtrip(s)


def test_auratouched_reentered_source_original_trigger_goes_hand(cards):
    s = setup(cards)
    source = put(s, "Auratouched Mage", "hand")
    mana(s, C=20, W=10)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id)
    for _ in range(20):
        if s.state.cards[source.id].zone == "p1:battlefield":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    blink = put(s, "Cloudshift", "hand")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=blink.id, targets=[source.id])
    settle(s)
    first = choose_named(s, "Pacifism")
    answer(s, [first])
    assert s.state.cards[first].zone == "p1:battlefield"
    assert s.state.cards[first].attached_to == source.id
    second = choose_named(s, "Rancor")
    answer(s, [second])
    assert s.state.cards[second].zone == "p1:hand"
    roundtrip(s)


def test_sovereigns_blinked_attacker_is_new_object(cards):
    s = setup(cards)
    put(s, "Sovereigns of Lost Alara", "battlefield")
    attacker = put(s, "Grizzly Bears", "battlefield")
    s.state.rules.controlled_since[attacker.id].turn = 0
    act(s, "p1", type="set_prefs", hold_priority=True)
    for _ in range(40):
        d = s.state.rules.decision
        if d and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])
    while s.state.rules.decision and s.state.rules.decision.kind == "order":
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    blink = put(s, "Cloudshift", "hand")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=blink.id, targets=[attacker.id])
    settle(s)
    search_yes(s)
    assert not s.state.rules.decision.options
    answer(s, [])
    assert not any(c.attached_to == attacker.id for c in s.state.cards.values())
    roundtrip(s)


def test_wild_pair_library_cda_grist_is_one_one(cards):
    s=setup(cards)
    put(s,'Wild Pair','battlefield')
    cast(s,'Memnite')
    search_yes(s)
    cid=choose_named(s,'Grist, the Hunger Tide')
    answer(s,[cid])
    assert s.state.cards[cid].zone == 'p1:battlefield'
    assert s.state.cards[cid].counters.get('loyalty') == 3
    roundtrip(s)
