"""Staged leaf-only canonical cast/play history and multiplayer optional draws."""

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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_placements import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/trigger_leaf51_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="tlf", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Jokulmorder", "Indentured Djinn", "Ichneumon Druid"])
def test_full_canonical(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    settle(s)


def djinn_setup(cards, extra=()):
    s = table(cards, ["Indentured Djinn", *extra], ["Lightning Bolt"], ["Opt"])
    source = put(s, "Indentured Djinn", "hand")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 2})
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    return s, source


@pytest.mark.parametrize("counts", [(0, 1), (1, 3), (3, 0)])
def test_djinn_each_player_chooses_before_draws_and_gets_own_count(cards, counts):
    s, source = djinn_setup(cards)
    before = {p: len(s.state.zones[p + ":hand"]) for p in ("p1", "p2", "p3")}
    for player, count in zip(("p2", "p3"), counts, strict=True):
        d = s.state.rules.decision
        assert d is not None and d.player == player and {o.id for o in d.options} == {"0", "1", "2", "3"}
        assert all(len(s.state.zones[p + ":hand"]) == before[p] for p in ("p1", "p2", "p3"))
        choose(s, [str(count)])
    assert s.state.cards[source.id].zone == "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == before["p1"]
    for player, count in zip(("p2", "p3"), counts, strict=True):
        assert len(s.state.zones[player + ":hand"]) == before[player] + count
    roundtrip(s)


def druid_setup(cards):
    names = [
        "Ichneumon Druid",
        "Lightning Bolt",
        "Opt",
        "Giant Growth",
        "Sol Ring",
        "Counterspell",
        "Grizzly Bears",
    ]
    s = table(cards, names, names, names)
    source = put(s, "Ichneumon Druid", "battlefield")
    to_phase(s, "main1", 2)
    return s, source


def cast_instant(s, name, player="p2"):
    source = put(s, name, "hand", player)
    wait_priority(s, player)
    amounts = {"Lightning Bolt": {"R": 1}, "Opt": {"U": 1}, "Giant Growth": {"G": 1}}
    act(s, player, type="add_mana", player=player, mana=amounts[name])
    act(s, player, type="cast_spell", card_id=source.id, targets=["p1"] if name == "Lightning Bolt" else [])
    settle(s)
    return source


def test_druid_counts_instant_casts_per_player_not_total_spells(cards):
    s, source = druid_setup(cards)
    ring = put(s, "Sol Ring", "hand", "p2")
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    act(s, "p2", type="cast_spell", card_id=ring.id)
    settle(s)
    cast_instant(s, "Lightning Bolt")
    assert s.state.players["p2"].life == 40
    cast_instant(s, "Opt", "p2")
    if s.state.rules.decision is not None:
        choose(s, [])
    assert s.state.players["p2"].life == 36
    cast_instant(s, "Lightning Bolt", "p3")
    assert s.state.players["p3"].life == 40
    cast_instant(s, "Lightning Bolt", "p2")
    assert s.state.players["p2"].life == 32
    cast_instant(s, "Lightning Bolt", "p1")
    assert s.state.players["p1"].life == 28  # four actual Bolts; own cast causes no Druid damage.
    roundtrip(s)


def jokul_setup(cards, pay=True):
    s = table(cards, ["Jokulmorder", "Island", "Breeding Pool"])
    source = put(s, "Jokulmorder", "hand")
    if pay:
        forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:5]
        act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 4, "U": 3})
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    return s, source


def pay_jokul(s):
    choose(s, ["pay"])
    d = s.state.rules.decision
    if d is not None:
        lands = [
            o.id
            for o in d.options
            if o.card_id in s.state.cards and s.state.cards[o.card_id].name == "Forest"
        ]
        assert len(lands) >= 5
        choose(s, lands[:5])
    assert sum(c.name == "Forest" and c.zone == "p1:graveyard" for c in s.state.cards.values()) == 5


def test_jokul_native_entry_five_land_cost_and_island_play(cards):
    s, source = jokul_setup(cards)
    assert s.state.cards[source.id].zone == "p1:battlefield" and s.state.cards[source.id].tapped
    pay_jokul(s)
    to_phase(s, "main1", 7)
    assert s.state.cards[source.id].tapped
    island = put(s, "Island", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="play_land", card_id=island.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    choose(s, ["yes"])
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


@pytest.mark.parametrize("accept", [False, True])
def test_jokul_play_is_optional_but_entering_island_is_not_playing(cards, accept):
    s, source = jokul_setup(cards)
    pay_jokul(s)
    island = put(s, "Island", "battlefield")
    settle(s)
    assert s.state.rules.decision is None and s.state.cards[source.id].tapped
    act(s, "p1", type="move", card_ids=[island.id], to={"player": "p1", "zone": "hand"})
    wait_priority(s, "p1")
    act(s, "p1", type="play_land", card_id=island.id)
    settle(s)
    choose(s, ["yes" if accept else "no"])
    assert s.state.cards[source.id].tapped == (not accept)
    roundtrip(s)


def test_jokul_declining_five_lands_sacrifices_it(cards):
    s, source = jokul_setup(cards)
    choose(s, ["decline"])
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def test_djinn_draw_replacement_keeps_original_draw_recipients_and_counts(cards):
    s, source = djinn_setup(cards, ["Notion Thief"])
    put(s, "Notion Thief", "battlefield")
    before = {p: len(s.state.zones[p + ":hand"]) for p in ("p1", "p2", "p3")}
    choose(s, ["1"])
    choose(s, ["3"])
    assert len(s.state.zones["p1:hand"]) == before["p1"] + 4
    assert all(len(s.state.zones[p + ":hand"]) == before[p] for p in ("p2", "p3"))
    roundtrip(s)


def test_djinn_draw_cap_prevents_impossible_multiple_draw_choice(cards):
    s, source = djinn_setup(cards, ["Spirit of the Labyrinth"])
    # The cap must already exist before the first numeric choice is emitted.
    # Start the actual entry trigger again with Narset now present.
    choose(s, ["0"])
    choose(s, ["0"])
    put(s, "Spirit of the Labyrinth", "battlefield")
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 2})
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {"0", "1"}
    choose(s, ["1"])
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {"0", "1"}
    choose(s, ["0"])
    roundtrip(s)


def test_djinn_departed_other_player_is_skipped_without_changing_earlier_choice(cards):
    s, source = djinn_setup(cards)
    before = len(s.state.zones["p2:hand"])
    act(s, "p3", type="concede")
    assert s.state.rules.decision is not None and s.state.rules.decision.player == "p2"
    choose(s, ["3"])
    assert s.state.rules.decision is None
    assert len(s.state.zones["p2:hand"]) == before + 3
    roundtrip(s)


@pytest.mark.parametrize("change", ["gone", "controller"])
def test_djinn_original_ability_controller_is_frozen(cards, change):
    s, source = djinn_setup(cards)
    before = {p: len(s.state.zones[p + ":hand"]) for p in ("p1", "p2", "p3")}
    if change == "gone":
        act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    else:
        act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    choose(s, ["1"])
    assert s.state.rules.decision.player == "p3"
    choose(s, ["3"])
    assert len(s.state.zones["p1:hand"]) == before["p1"]
    assert len(s.state.zones["p2:hand"]) == before["p2"] + 1
    assert len(s.state.zones["p3:hand"]) == before["p3"] + 3
    roundtrip(s)


def test_druid_late_entry_and_new_turn_use_complete_native_cast_history(cards):
    s, source = druid_setup(cards)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "hand"})
    cast_instant(s, "Lightning Bolt", "p2")
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "battlefield"})
    cast_instant(s, "Lightning Bolt", "p2")
    assert s.state.players["p2"].life == 36
    to_phase(s, "main1", 3)
    cast_instant(s, "Lightning Bolt", "p2")
    assert s.state.players["p2"].life == 36
    cast_instant(s, "Lightning Bolt", "p2")
    assert s.state.players["p2"].life == 32
    roundtrip(s)


def test_druid_original_cast_ordinal_survives_more_casts_and_source_departure(cards):
    s, source = druid_setup(cards)
    cast_instant(s, "Lightning Bolt", "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    for owner in ("p2", "p3"):
        bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == owner)
        act(s, "p2", type="move", card_ids=[bolt.id], to={"player": "p2", "zone": "hand"})
        wait_priority(s, "p2")
        act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    settle(s)
    assert s.state.players["p2"].life == 32
    roundtrip(s)


def test_djinn_cap_and_notion_thief_do_not_allow_optional_multiple_draws(cards):
    from app.rules import prohibitions
    from app.rules.plan import Plan

    s = table(cards, ["Indentured Djinn", "Notion Thief", "Narset, Parter of Veils"])
    source = put(s, "Indentured Djinn", "hand")
    narset = put(s, "Narset, Parter of Veils", "hand")
    put(s, "Notion Thief", "battlefield")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    for c in (narset, source):
        act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 2})
        act(s, "p1", type="cast_spell", card_id=c.id)
        settle(s)
    before = {p: len(s.state.zones[p + ":hand"]) for p in ("p1", "p2", "p3")}
    for p in ("p2", "p3"):
        d = s.state.rules.decision
        assert d is not None and d.player == p and {o.id for o in d.options} == {"0", "1"}
        choose(s, ["1"])
    assert len(s.state.zones["p1:hand"]) == before["p1"] + 2
    assert all(len(s.state.zones[p + ":hand"]) == before[p] for p in ("p2", "p3"))
    assert all(prohibitions.draw_left(Plan.view(s.state, "p1", cards), p)[0] == 1 for p in ("p2", "p3"))
    roundtrip(s)


def test_djinn_archive_modifies_draws_after_original_counts_chosen(cards):
    s, source = djinn_setup(cards, ["Alhammarret's Archive"])
    archive = put(s, "Alhammarret's Archive", "battlefield")
    act(s, "p1", type="set_controller", card_ids=[archive.id], player="p2")
    before = {p: len(s.state.zones[p + ":hand"]) for p in ("p1", "p2", "p3")}
    choose(s, ["2"])
    choose(s, ["1"])
    assert len(s.state.zones["p1:hand"]) == before["p1"]
    assert len(s.state.zones["p2:hand"]) == before["p2"] + 4
    assert len(s.state.zones["p3:hand"]) == before["p3"] + 1
    roundtrip(s)


def test_djinn_prompted_player_departure_resumes_remaining_recipient(cards):
    s, source = djinn_setup(cards)
    before = len(s.state.zones["p3:hand"])
    act(s, "p2", type="concede")
    d = s.state.rules.decision
    assert d is not None and d.player == "p3"
    choose(s, ["3"])
    assert s.state.rules.decision is None and len(s.state.zones["p3:hand"]) == before + 3
    roundtrip(s)


def test_druid_countered_first_instant_still_counts(cards):
    s, source = druid_setup(cards)
    bolt = put(s, "Lightning Bolt", "hand", "p2")
    counter = put(s, "Counterspell", "hand", "p1")
    wait_priority(s, "p2")
    act(s, "p2", type="set_prefs", hold_priority=True)
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 2})
    act(s, "p1", type="cast_spell", card_id=counter.id, targets=[bolt.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == "p2:graveyard" and s.state.players["p2"].life == 40
    cast_instant(s, "Lightning Bolt", "p2")
    assert s.state.players["p1"].life == 37 and s.state.players["p2"].life == 36
    roundtrip(s)


@pytest.mark.parametrize("landname,actor", [("Forest", "p1"), ("Island", "p2"), ("Breeding Pool", "p1")])
def test_jokul_exact_island_subtype_and_play_actor(cards, landname, actor):
    s, source = jokul_setup(cards)
    pay_jokul(s)
    if actor == "p2":
        to_phase(s, "main1", 5)
    land = put(s, landname, "hand", actor)
    wait_priority(s, actor)
    act(s, actor, type="play_land", card_id=land.id)
    settle(s)
    if landname == "Breeding Pool":
        d = s.state.rules.decision
        assert d is not None and d.resume["step"] == "shock"
        choose(s, ["tapped"])
        assert s.state.cards[land.id].tapped
        choose(s, ["yes"])
        assert not s.state.cards[source.id].tapped
        roundtrip(s)
    else:
        assert s.state.rules.decision is None and s.state.cards[source.id].tapped
        roundtrip(s)


def fresh(s, cards, path, actor, payload):
    import subprocess
    import sys

    from app.game.session import GameSession
    from app.game.state import GameState

    path.write_text(s.state.model_dump_json())
    code = """
import json,os,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
if os.environ.get('FYODOR_TRIGGERLEAF51_STAGE'):
 from fyodor_triggerleaf51_plugin import install
 install()
path=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(path.parent/'cold-images'))
s=GameSession(GameState.model_validate_json(path.read_text()),cards=repo)
s.perform(sys.argv[3],json.loads(sys.argv[4]))
for _ in range(80):
 if s.state.rules.decision or not s.state.zones.get('stack'):break
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
path.write_text(s.state.model_dump_json());repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), str(cards.db_path), actor, json.dumps(payload)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return GameSession(GameState.model_validate_json(path.read_text()), cards=cards)


def test_djinn_cold_between_recipients_keeps_original_counts(cards, tmp_path):
    s, source = djinn_setup(cards)
    before = {p: len(s.state.zones[p + ":hand"]) for p in ("p1", "p2", "p3")}
    choose(s, ["1"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p3"
    assert all(len(s.state.zones[p + ":hand"]) == before[p] for p in ("p1", "p2", "p3"))
    s = fresh(
        s,
        cards,
        tmp_path / "djinn.json",
        d.player,
        {"type": "choose", "decision_id": d.id, "option_ids": ["3"]},
    )
    assert len(s.state.zones["p1:hand"]) == before["p1"]
    assert len(s.state.zones["p2:hand"]) == before["p2"] + 1
    assert len(s.state.zones["p3:hand"]) == before["p3"] + 3
    roundtrip(s)


def test_jokul_cold_optional_untap_after_actual_island_play(cards, tmp_path):
    s, source = jokul_setup(cards)
    pay_jokul(s)
    island = put(s, "Island", "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="play_land", card_id=island.id)
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    s = fresh(
        s,
        cards,
        tmp_path / "jokul.json",
        d.player,
        {"type": "choose", "decision_id": d.id, "option_ids": ["yes"]},
    )
    assert not s.state.cards[source.id].tapped
    roundtrip(s)


def test_druid_cold_full_cast_history_still_excludes_only_first_instant(cards, tmp_path):
    s, source = druid_setup(cards)
    cast_instant(s, "Lightning Bolt", "p2")
    bolt = put(s, "Lightning Bolt", "hand", "p2")
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    s = fresh(
        s, cards, tmp_path / "druid.json", "p2", {"type": "cast_spell", "card_id": bolt.id, "targets": ["p1"]}
    )
    assert s.state.players["p2"].life == 36 and s.state.players["p1"].life == 34
    roundtrip(s)


def test_djinn_native_response_kills_source_before_trigger_resolves(cards):
    s = table(cards, ["Indentured Djinn"], ["Murder"])
    source = put(s, "Indentured Djinn", "hand")
    murder = put(s, "Murder", "hand", "p2")
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 2})
    act(s, "p1", type="cast_spell", card_id=source.id)
    for _ in range(20):
        if s.state.cards[source.id].zone == "p1:battlefield":
            break
        assert s.state.rules.decision is None
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[source.id].zone == "p1:battlefield"
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1, "B": 2})
    act(s, "p2", type="cast_spell", card_id=murder.id, targets=[source.id])
    settle(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    before = {p: len(s.state.zones[p + ":hand"]) for p in ("p1", "p2", "p3")}
    choose(s, ["1"])
    choose(s, ["3"])
    assert len(s.state.zones["p1:hand"]) == before["p1"]
    assert len(s.state.zones["p2:hand"]) == before["p2"] + 1
    assert len(s.state.zones["p3:hand"]) == before["p3"] + 3
    roundtrip(s)
