"""Native optional placement, true ticket costs and distinct owner/controller authorities."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, stickers101
from app.rules.plan import Plan
from app.rules.sticker_sheets101 import SHEETS
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.wave9c_kit import check
from tests.wave100c_kit import chars, move, one, settle, to_phase, zone

DATA = json.loads((Path(__file__).parent / "fixtures/sticker_effects101_cards.json").read_text())
NAMES = [
    "Command Performance",
    "Ticketomaton",
    "Finishing Move",
    "Chicken Troupe",
    "Prize Wall",
    "Stiltstrider",
    "Glitterflitter",
    "Bioluminary",
    "Baaallerina",
    "Minotaur de Force",
    "Aerialephant",
    "Carnival Carnivore",
    "Robo-Piñata",
    "Sword-Swallowing Seraph",
    "Proficient Pyrodancer",
    "Roxi, Publicist to the Stars",
    "Costume Shop",
]
ETB = [
    "Ticketomaton",
    "Chicken Troupe",
    "Stiltstrider",
    "Glitterflitter",
    "Minotaur de Force",
    "Aerialephant",
    "Carnival Carnivore",
]


@pytest.fixture
def cards(settings):
    rows = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        fields = {k: v for k, v in c.items() if k not in ("name", "set_code", "number", "collector_number")}
        rows[c["name"]] = card(
            c["name"],
            set_code=c.get("set_code", "sf101") if "Attraction" in c.get("type_line", "") else "sf101",
            number=str(c.get("collector_number", i)) if "Attraction" in c.get("type_line", "") else str(i),
            **fields,
        )
    settings.ensure_dirs()
    build_database(rows.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


class FixedSheetRng:
    def shuffle(self, values):
        pass


def setup(cards, sheets=True, third=False, attractions=False):
    names = [n for n in NAMES if n != "Costume Shop"] + [
        "Grizzly Bears",
        "Sol Ring",
        "Hill Giant",
        "Llanowar Elves",
        "Control Magic",
        "Unsummon",
        "Disenchant",
        "Lightning Bolt",
        "Solemnity",
        "Vorinclex, Monstrous Raider",
    ]
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), *((1, n) for n in names)])
    if attractions:
        extra = [
            "Balloon Stand",
            "Bumper Cars",
            "Clown Extruder",
            "Concession Stand",
            "Foam Weapons Kiosk",
            "Fortune Teller",
            "Hall of Mirrors",
            "Haunted House",
            "Information Booth",
            "Costume Shop",
        ]
        mine += [DeckCard("attractions", 1, (c := cards.resolve(name))["name"], c["id"]) for name in extra]
    other = deck(
        cards,
        "Atraxa, Praetors' Voice",
        [(30, "Island"), (1, "Grizzly Bears"), (1, "Hill Giant"), (1, "Control Magic")],
    )
    if sheets:
        wanted = ["Eldrazi Guacamole Tightrope", "Ancestral Hot Dog Minotaur", "Trendy Circus Pirate"]
        selected = [s for name in wanted for s in SHEETS.values() if s["name"] == name]
        selected += [s for s in SHEETS.values() if s not in selected][:7]
        mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in selected]
    players = [PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)]
    if third:
        players.append(PlayerSetup("Carol", cards=other))
    state = enable(new_game(players, shuffle=False, rng=FixedSheetRng()))
    s = GameSession(state, cards=cards)
    for pid in state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


def question(s):
    for _ in range(40):
        if s.state.rules.decision:
            return s.state.rules.decision
        assert s.state.zones.get("stack")
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("No question")


def pick(s, ids):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def cast(s, name, **kw):
    c = one(s, name)
    move(s, c, "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={c: 20 for c in ("C", "W", "U", "B", "R", "G")})
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    return c


def sticker(s, kind="art", text=None, cost=None):
    return next(
        v
        for v in stickers101.available(Plan.view(s.state, "p1", s.cards), "p1", kind)
        if (text is None or v["text"] == text) and (cost is None or v["cost"] == cost)
    )


def place(s, cid, kind="art", text=None, cost=None, position=0):
    d = question(s)
    assert d.min_choices == 0 and cid in [o.id for o in d.options]
    chosen = sticker(s, kind, text, cost)
    pick(s, [cid])
    assert chosen["id"] in [o.id for o in s.state.rules.decision.options]
    pick(s, [chosen["id"]])
    if kind == "name":
        pick(s, [str(position)])
    return chosen


@pytest.mark.parametrize("name", NAMES)
def test_whole_canonical_candidates101(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", ETB)
def test_actual_etb_tickets_then_optional_non_target_art_placement101(cards, name):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    source = cast(s, name)
    choice = question(s)
    assert source.id in [o.id for o in choice.options]
    expected = cards.resolve(name)["oracle_text"].split("then you may")[0].count("{TK}")
    assert s.state.players["p1"].resources["ticket"] == expected
    chosen = place(s, bear.id)
    settle(s)
    assert s.state.cards[bear.id].stickers101[-1].sticker.id == chosen["id"]
    assert s.state.players["p1"].resources["ticket"] == expected
    check(s)


def test_decline_and_no_sheet_preserve_actual_ticket_grant101(cards):
    for sheets in (False, True):
        s = setup(cards, sheets=sheets)
        cast(s, "Aerialephant")
        if sheets:
            question(s)
            pick(s, [])
        settle(s)
        assert s.state.players["p1"].resources["ticket"] == 1
        assert all(not c.stickers101 for c in s.state.cards.values())
        check(s)


def test_paid_power_sticker_changes_finishing_move_damage_before_damage_resolves101(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    victim = put(s, "Hill Giant", "battlefield", "p2")
    cast(s, "Finishing Move", targets=[bear.id, victim.id], target_counts=[1, 1])
    chosen = place(s, bear.id, kind="pt", text="5/1", cost=2)
    settle(s)
    assert s.state.cards[bear.id].stickers101[-1].sticker.id == chosen["id"]
    assert chars(s, bear).pt == (5, 1) and zone(s, victim) == "p2:graveyard"
    assert s.state.players["p1"].resources["ticket"] == 0
    check(s)


def test_optional_sticker_filters_unaffordable_and_other_owner_objects101(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    foreign = put(s, "Grizzly Bears", "battlefield", "p2")
    cast(s, "Ticketomaton")
    d = question(s)
    assert foreign.id not in [o.id for o in d.options]
    pick(s, [bear.id])
    offered = {o.id for o in s.state.rules.decision.options}
    assert sticker(s, "ability", text="Haste")["id"] not in offered
    assert sticker(s, "name")["id"] in offered
    pick(s, ["decline"])
    settle(s)
    assert not s.state.cards[bear.id].stickers101 and s.state.players["p1"].resources["ticket"] == 1
    check(s)


def test_actual_command_ticket_and_sticker_modes_share_one_resolution101(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Command Performance", modes=[2, 3])
    chosen = place(s, bear.id, kind="ability", text="Haste", cost=2)
    settle(s)
    assert chosen["id"] == s.state.cards[bear.id].stickers101[-1].sticker.id
    assert "haste" in chars(s, bear).keywords and s.state.players["p1"].resources["ticket"] == 0
    check(s)


def test_actual_roxi_distributes_two_art_stickers_and_cda_counts_both_objects101(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    roxi = cast(s, "Roxi, Publicist to the Stars")
    first = place(s, bear.id)
    second = place(s, roxi.id)
    settle(s)
    assert first["id"] != second["id"] and chars(s, roxi).pt == (2, 4)
    assert len(s.state.cards[bear.id].stickers101) == len(s.state.cards[roxi.id].stickers101) == 1
    check(s)


@pytest.mark.parametrize(
    "name,kind",
    [("Baaallerina", "name"), ("Sword-Swallowing Seraph", "name"), ("Proficient Pyrodancer", "art")],
)
def test_actual_kind_restricted_etb_and_native_activated_sticker_target101(cards, name, kind):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    source = cast(s, name)
    chosen = place(s, bear.id, kind=kind)
    settle(s)
    assert s.state.cards[bear.id].stickers101[-1].sticker.id == chosen["id"]
    if name == "Sword-Swallowing Seraph":
        to_phase(s, "main1", 3)
    ability = next(a for a in chars(s, source).abilities if a.cost and a.kind == "activated")
    act(s, "p1", type="add_mana", player="p1", mana={c: 20 for c in ("C", "W", "U", "B", "R", "G")})
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability.index,
        targets=[bear.id],
        sources=[],
    )
    settle(s)
    if name == "Baaallerina":
        assert "flying" in chars(s, bear).keywords
    elif name == "Sword-Swallowing Seraph":
        assert bear.counters["+1/+1"] == 1 and source.tapped
    else:
        assert chars(s, bear).pt == (4, 2) and "menace" in chars(s, bear).keywords
    check(s)


def test_actual_prize_wall_sorcery_activation_and_discrete_sticker_use101(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    wall = cast(s, "Prize Wall")
    settle(s)
    to_phase(s, "main1", 3)
    ability = next(
        a for a in chars(s, wall).abilities if a.cost and a.kind == "activated" and "sticker" in a.text
    )
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1, "C": 4})
    act(s, "p1", type="activate_ability", card_id=wall.id, ability=ability.index, sources=[])
    selected = place(s, bear.id, kind="name")
    settle(s)
    assert wall.tapped and selected["id"] not in {
        v["id"] for v in stickers101.available(Plan.view(s.state, "p1", s.cards), "p1")
    }
    assert s.state.cards[bear.id].stickers101[-1].sticker.kind == "name"
    check(s)


def test_actual_bioluminary_combat_grants_two_tickets_before_choice101(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    creature = cast(s, "Bioluminary")
    settle(s)
    to_phase(s, "declare_attackers", 3)
    power = chars(s, creature).pt[0]
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": creature.id, "target": "p2"}])
    for _ in range(80):
        d = s.state.rules.decision
        if d and d.resume.get("step") == "put_sticker101":
            break
        if d and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == 40 - power and s.state.players["p1"].resources["ticket"] == 2
    place(s, bear.id, "ability", text="Haste")
    settle(s)
    assert "haste" in chars(s, bear).keywords and s.state.players["p1"].resources["ticket"] == 0
    check(s)


@pytest.mark.parametrize("mode", ["0", "1"])
def test_actual_robo_pinata_death_modal_ticket_or_sticker101(cards, mode):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    robot = cast(s, "Robo-Piñata")
    settle(s)
    cast(s, "Lightning Bolt", targets=[robot.id])
    d = question(s)
    assert d.resume.get("step") == "trigger_modes" and len(d.options) == 2
    pick(s, [next(o.id for o in d.options if o.id.split(":", 1)[0] == mode)])
    if mode == "1":
        place(s, bear.id)
        settle(s)
    else:
        settle(s)
    assert zone(s, robot) == "p1:graveyard"
    assert len(s.state.cards[bear.id].stickers101) == int(mode == "1")
    assert s.state.players["p1"].resources.get("ticket", 0) == 2 * int(mode == "0")
    check(s)


def borrowed_choice(cards):
    s = setup(cards, third=True)
    bear = put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "main1", 2)
    aura = one(s, "Control Magic", "p2")
    move(s, aura, "hand")
    act(s, "p2", type="add_mana", player="p2", mana={"U": 2, "C": 2})
    act(s, "p2", type="cast_spell", card_id=aura.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].controller == "p2"
    to_phase(s, "main1", 4)
    cast(s, "Baaallerina")
    question(s)
    pick(s, [bear.id])
    pick(s, [sticker(s, "name", text="Hot Dog")["id"]])
    assert s.state.rules.decision.player == "p2"
    return s, bear


def test_owner_chooses_sticker_borrowed_current_controller_chooses_name_position101(cards):
    s, bear = borrowed_choice(cards)
    pick(s, ["2"])
    settle(s)
    assert chars(s, bear).name == "Grizzly Bears Hot Dog"
    assert s.state.cards[bear.id].owner == "p1" and s.state.cards[bear.id].controller == "p2"
    assert s.state.cards[bear.id].stickers101[-1].owner == "p1"
    check(s)


def test_borrower_concedes_during_name_choice_reoffers_current_controller_same_object101(cards):
    s, bear = borrowed_choice(cards)
    oid = s.state.rules.object_id(bear.id)
    act(s, "p2", type="concede")
    assert s.state.rules.object_id(bear.id) == oid and s.state.cards[bear.id].controller == "p1"
    assert s.state.rules.decision and s.state.rules.decision.player == "p1"
    pick(s, ["0"])
    settle(s)
    assert chars(s, bear).name == "Hot Dog Grizzly Bears" and len(s.state.cards[bear.id].stickers101) == 1
    check(s)


def cold(s, tmp_path, body, metadata):
    import subprocess
    import sys

    import app

    saved = tmp_path / "sticker-effect101.json"
    saved.write_text(s.state.model_dump_json())
    code = (
        """import json,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.wave100c_kit import settle
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
m=json.loads(sys.argv[3])
def answer(ids):
 d=s.state.rules.decision;act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
"""
        + body
        + "\nrepo.close()\n"
    )
    p = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(s.cards.db_path), json.dumps(metadata)],
        cwd=Path(app.__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=100,
    )
    assert p.returncode == 0, p.stdout + p.stderr


def test_genuine_cold_ticket_grant_card_then_paid_ability_sticker101(cards, tmp_path):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Command Performance", modes=[2, 3])
    question(s)
    selected = sticker(s, "ability", text="Haste")
    cold(
        s,
        tmp_path,
        """assert s.state.players['p1'].resources['ticket']==2
answer([m['bear']]);answer([m['sticker']]);settle(s)
c=s.state.cards[m['bear']]
assert c.stickers101[-1].sticker.id==m['sticker'] and 'haste' in Plan.view(s.state,'p1',repo).ch(c).keywords
assert s.state.players['p1'].resources['ticket']==0
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
""",
        {"bear": bear.id, "sticker": selected["id"]},
    )


def test_genuine_cold_borrowed_name_position_reassigns_after_controller_concedes101(cards, tmp_path):
    s, bear = borrowed_choice(cards)
    cold(
        s,
        tmp_path,
        """oid=s.state.rules.object_id(m['bear'])
assert s.state.rules.decision.player=='p2'
act(s,'p2',type='concede')
assert s.state.rules.object_id(m['bear'])==oid and s.state.rules.decision.player=='p1'
answer(['0']);settle(s)
c=s.state.cards[m['bear']]
assert Plan.view(s.state,'p1',repo).ch(c).name=='Hot Dog Grizzly Bears'
assert c.stickers101[-1].owner=='p1' and c.controller=='p1'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
""",
        {"bear": bear.id},
    )


def test_actual_open_then_roll_to_visit_costume_shop_offers_sticker101(cards, monkeypatch):
    from tests.test_rules_wave12a_counters_keywords import rolls

    s = setup(cards, attractions=True)
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Command Performance", modes=[0, 2])
    settle(s)
    attraction = one(s, "Costume Shop")
    assert zone(s, attraction) == "p1:battlefield"
    assert s.state.players["p1"].resources["ticket"] == 2
    rolls(monkeypatch, 6)
    cast(s, "Command Performance", modes=[1, 2])
    question(s)
    assert s.state.players["p1"].resources["ticket"] == 4
    chosen = place(s, bear.id)
    settle(s)
    assert s.state.cards[bear.id].stickers101[-1].sticker.id == chosen["id"]
    check(s)


@pytest.mark.parametrize("source,expected", [("Solemnity", 0), ("Vorinclex, Monstrous Raider", 2)])
def test_ticket_grant_uses_native_counter_prevention_and_multiplication101(cards, source, expected):
    s = setup(cards)
    put(s, source, "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Ticketomaton")
    question(s)
    assert s.state.players["p1"].resources.get("ticket", 0) == expected
    place(s, bear.id, kind="name")
    settle(s)
    assert chars(s, bear).name.endswith("Grizzly Bears")
    assert s.state.players["p1"].resources.get("ticket", 0) == expected
    check(s)
