"""Native discrete sticker sheets, costs, current layers and public/hidden transitions (CR123)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, stickers101
from app.rules.plan import Plan
from app.rules.sticker_sheets101 import SHEETS
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase

NAMES = {
    "Croakid Amphibonaut": "flying",
    "Grabby Tabby": "vigilance",
    "Scared Stiff": "menace",
    "Big Winner": "trample",
    "Sanguine Sipper": "lifelink",
}


@pytest.fixture
def cards(settings):
    rows = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/stickers101_cards.json").read_text())
    ):
        extra = {k: v for k, v in c.items() if k not in ("name", "set_code", "number")}
        rows[c["name"]] = card(c["name"], set_code="st101", number=str(i), **extra)
    settings.ensure_dirs()
    build_database(rows.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


class FixedSheetRng:
    def shuffle(self, values):
        pass


def setup(cards, *, preferred=None):
    wanted = preferred or [
        "Eldrazi Guacamole Tightrope",
        "Ancestral Hot Dog Minotaur",
        "Trendy Circus Pirate",
    ]
    choices = [s for name in wanted for s in SHEETS.values() if s["name"] == name]
    choices += [s for s in SHEETS.values() if s not in choices][:7]
    mine = deck(
        cards,
        "Krenko, Mob Boss",
        [
            (30, "Forest"),
            *(
                (1, n)
                for n in [
                    "Grizzly Bears",
                    "Sol Ring",
                    "Dress Down",
                    "Witness Protection",
                    "Disenchant",
                    "Giant Growth",
                    "Clone",
                    "Gemrazer",
                    "Murder",
                    "Dismember",
                    "Karmic Justice",
                    "Song of the Dryads",
                    *NAMES,
                ]
            ),
        ],
    )
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in choices]
    other = deck(
        cards, "Atraxa, Praetors' Voice", [(30, "Island"), (1, "Grizzly Bears"), (1, "Beast Within")]
    )
    s = GameSession(
        enable(
            new_game(
                [PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)],
                shuffle=False,
                rng=FixedSheetRng(),
            )
        ),
        cards=cards,
    )
    to_phase(s, "main1", 1)
    return s


def view(s, cid):
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[cid])


def select(s, kind, *, text=None):
    return next(
        v
        for v in stickers101.available(Plan.view(s.state, "p1", s.cards), "p1", kind)
        if text is None or v["text"] == text
    )


def attach(s, cid, kind, *, text=None, position=0):
    chosen = select(s, kind, text=text)
    s.perform(
        "p1",
        {"type": "rules_sticker101", "card_id": cid, "sticker_id": chosen["id"], "position": position},
        trusted=True,
    )
    return chosen


def test_constructed_sheets_are_three_distinct_public_and_offline(cards):
    s = setup(cards)
    p = s.state.players["p1"]
    assert len(p.sticker_sheets101) == 3
    assert len(p.sticker_pool101) == 10 and len({s["id"] for s in p.sticker_pool101}) == 10
    assert all(len(sheet.stickers) == 10 for sheet in p.sticker_sheets101)
    names = [
        x.text
        for sh in p.sticker_sheets101
        if sh.name == "Ancestral Hot Dog Minotaur"
        for x in sh.stickers
        if x.kind == "name"
    ]
    assert names == ["Ancestral", "Hot Dog", "Minotaur"]
    assert len(s.view("p2")["players"][0]["sticker_sheets101"]) == 3
    assert not any(c.name in {sh.name for sh in p.sticker_sheets101} for c in s.state.cards.values())
    roundtrip(s)


def test_cost_and_discrete_availability_are_atomic_and_replayable(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    haste = select(s, "ability", text="Haste")
    with pytest.raises(ActionError, match="tickets"):
        s.perform(
            "p1", {"type": "rules_sticker101", "card_id": bear.id, "sticker_id": haste["id"]}, trusted=True
        )
    act(s, "p1", type="resource", key="ticket", delta=haste["cost"])
    attach(s, bear.id, "ability", text="Haste")
    assert s.state.players["p1"].resources["ticket"] == 0
    assert "haste" in view(s, bear.id).keywords
    assert haste["id"] not in {x["id"] for x in stickers101.available(Plan.view(s.state, "p1", cards), "p1")}
    with pytest.raises(ActionError, match="already"):
        s.perform(
            "p1", {"type": "rules_sticker101", "card_id": bear.id, "sticker_id": haste["id"]}, trusted=True
        )
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_public_exile_graveyard_retains_then_hidden_hand_returns_to_sheet(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    sticker = attach(s, bear.id, "name", text="Hot Dog", position=1)
    assert view(s, bear.id).name == "Grizzly Hot Dog Bears"
    for zone in ["exile", "graveyard", "battlefield"]:
        act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": zone})
        assert view(s, bear.id).name == "Grizzly Hot Dog Bears"
        assert s.state.cards[bear.id].stickers101
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "hand"})
    assert not s.state.cards[bear.id].stickers101
    assert sticker["id"] in {x["id"] for x in stickers101.available(Plan.view(s.state, "p1", cards), "p1")}
    assert view(s, bear.id).name == "Grizzly Bears"
    roundtrip(s)


def test_owner_not_controller_can_put_on_stolen_permanent(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="set_controller", card_ids=[bear.id], player="p2")
    attach(s, bear.id, "art")
    assert s.state.cards[bear.id].stickers101
    foreign = put(s, "Grizzly Bears", "battlefield", "p2")
    sticker = select(s, "art")
    with pytest.raises(ActionError, match="own"):
        s.perform(
            "p1",
            {"type": "rules_sticker101", "card_id": foreign.id, "sticker_id": sticker["id"]},
            trusted=True,
        )
    roundtrip(s)


@pytest.mark.parametrize("name,keyword", NAMES.items())
def test_current_sticker_condition_follows_native_control_and_hidden_return(cards, name, keyword):
    s = setup(cards)
    source = put(s, name, "battlefield")
    rock = put(s, "Sol Ring", "battlefield")
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
    assert keyword not in view(s, source.id).keywords
    attach(s, rock.id, "art")
    assert keyword in view(s, source.id).keywords
    act(s, "p1", type="set_controller", card_ids=[rock.id], player="p2")
    assert keyword not in view(s, source.id).keywords
    act(s, "p1", type="set_controller", card_ids=[rock.id], player="p1")
    assert keyword in view(s, source.id).keywords
    act(s, "p1", type="move", card_ids=[rock.id], to={"player": "p1", "zone": "hand"})
    assert keyword not in view(s, source.id).keywords
    roundtrip(s)


def cast(s, name, targets=()):
    source = put(s, name, "hand")
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 40, "W": 20, "U": 20, "B": 20, "R": 20, "G": 20})
    act(s, "p1", type="cast_spell", card_id=source.id, targets=list(targets))
    settle(s)
    if s.state.rules.decision and s.state.rules.decision.resume.get("step") == "phyrexian":
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        settle(s)
    return source


def test_pt_sticker_is_not_an_ability_and_interleaves_base_pt_and_counters(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    pt = select(s, "pt")
    act(s, "p1", type="resource", key="ticket", delta=20)
    attach(s, bear.id, "pt")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=2)
    assert view(s, bear.id).pt == (pt["power"] + 2, pt["toughness"] + 2)
    cast(s, "Dress Down")
    assert view(s, bear.id).pt == (pt["power"] + 2, pt["toughness"] + 2)
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_later_ability_sticker_follows_real_ability_loss_and_copy_does_not_inherit(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="resource", key="ticket", delta=20)
    attach(s, bear.id, "ability", text="Haste")
    assert "haste" in view(s, bear.id).keywords
    dress = cast(s, "Dress Down")
    assert "haste" not in view(s, bear.id).keywords
    attach(s, bear.id, "ability", text="Flying")
    assert "flying" in view(s, bear.id).keywords
    cast(s, "Disenchant", [dress.id])
    clone = cast(s, "Clone")
    d = s.state.rules.decision
    assert d and any(o.id == bear.id for o in d.options)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
    settle(s)
    assert not s.state.cards[clone.id].stickers101
    assert "haste" not in view(s, clone.id).keywords and "flying" not in view(s, clone.id).keywords
    roundtrip(s)


def test_name_sticker_timestamp_with_actual_name_setting_aura(cards):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    attach(s, bear.id, "name", text="Hot Dog", position=1)
    aura = cast(s, "Witness Protection", [bear.id])
    assert view(s, bear.id).name == "Legitimate Businessperson"
    attach(s, bear.id, "name", text="Ancestral", position=0)
    assert view(s, bear.id).name == "Ancestral Legitimate Businessperson"
    cast(s, "Disenchant", [aura.id])
    assert view(s, bear.id).name == "Ancestral Grizzly Hot Dog Bears"
    roundtrip(s)


def test_genuine_cold_ability_name_and_pt_markers_keep_public_and_clear_hidden(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="resource", key="ticket", delta=20)
    attach(s, bear.id, "name", text="Hot Dog", position=1)
    attach(s, bear.id, "ability", text="Haste")
    chosen = attach(s, bear.id, "pt")
    saved = tmp_path / "stickers101.json"
    saved.write_text(s.state.model_dump_json())
    code = """import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
cid=sys.argv[3]
def ch():return Plan.view(s.state,'p1',repo).ch(s.state.cards[cid])
assert ch().name=='Grizzly Hot Dog Bears' and 'haste' in ch().keywords
assert ch().pt==tuple(map(int,sys.argv[4:6]))
act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'graveyard'})
assert ch().name=='Grizzly Hot Dog Bears' and 'haste' in ch().keywords
act(s,'p1',type='move',card_ids=[cid],to={'player':'p1','zone':'library'})
assert not s.state.cards[cid].stickers101
assert ch().name=='Grizzly Bears' and 'haste' not in ch().keywords
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(saved),
            str(cards.db_path),
            bear.id,
            str(chosen["power"]),
            str(chosen["toughness"]),
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def merged(s):
    from tests.test_rules_wave18d_merged import mutate

    bear = put(s, "Grizzly Bears", "battlefield")
    attach(s, bear.id, "name", text="Hot Dog", position=1)
    mutate(s, "Gemrazer", bear, G=3)
    assert s.state.cards[bear.id].merged
    assert view(s, bear.id).name == "Gemrazer Hot Dog"
    return bear


def test_actual_destroy_merged_owner_chooses_one_sticker_recipient_before_move(cards):
    s = setup(cards)
    host = merged(s)
    cast(s, "Murder", [host.id])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "sticker_split101" and d.player == "p1"
    assert s.state.cards[host.id].zone == "p1:battlefield"
    selected = next(o.id for o in d.options if o.label == "Grizzly Bears")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[selected])
    settle(s)
    retained = [c for c in s.state.cards.values() if c.stickers101]
    assert len(retained) == 1 and retained[0].name == "Grizzly Bears" and retained[0].zone == "p1:graveyard"
    assert view(s, retained[0].id).name == "Grizzly Hot Dog Bears"
    assert not s.state.rules.sticker_splits101
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_actual_sba_merged_sticker_recipient_choice_is_retained_after_cold(cards, tmp_path):
    import subprocess
    import sys

    s = setup(cards)
    host = merged(s)
    cast(s, "Dismember", [host.id])
    d = s.state.rules.decision
    assert d and d.resume["step"] == "sticker_split101" and d.resume["ctx"] is None
    assert s.state.cards[host.id].zone == "p1:battlefield"
    selected = next(o.id for o in d.options if o.label == "Grizzly Bears")
    saved = tmp_path / "sticker-sba.json"
    saved.write_text(s.state.model_dump_json())
    code = """import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
d=s.state.rules.decision
act(s,'p1',type='choose',decision_id=d.id,option_ids=[sys.argv[3]])
retained=[c for c in s.state.cards.values() if c.stickers101]
assert len(retained)==1 and retained[0].name=='Grizzly Bears' and retained[0].zone=='p1:graveyard'
assert Plan.view(s.state,'p1',repo).ch(retained[0]).name=='Grizzly Hot Dog Bears'
assert not s.state.rules.sticker_splits101
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
repo.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), selected],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sticker_static_ability_uses_its_timestamp_through_real_dress_down(cards):
    s = setup(
        cards, preferred=["Vampire Champion Fury", "Trained Blessed Mind", "Eldrazi Guacamole Tightrope"]
    )
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="resource", key="ticket", delta=20)
    put(s, "Forest", "hand")
    hellbent = next(
        x
        for x in stickers101.available(Plan.view(s.state, "p1", cards), "p1", "ability")
        if x["text"].startswith("Hellbent")
    )
    s.perform(
        "p1", {"type": "rules_sticker101", "card_id": bear.id, "sticker_id": hellbent["id"]}, trusted=True
    )
    assert view(s, bear.id).pt == (2, 2)
    hand = list(s.state.zones["p1:hand"])
    act(s, "p1", type="move", card_ids=hand, to={"player": "p1", "zone": "graveyard"})
    assert view(s, bear.id).pt == (5, 5)
    cast(s, "Dress Down")
    assert view(s, bear.id).pt == (2, 2)
    missing = 7 - len(s.state.zones["p1:graveyard"])
    if missing > 0:
        forests = [cid for cid in s.state.zones["p1:library"] if s.state.cards[cid].name == "Forest"][
            :missing
        ]
        act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "graveyard"})
    threshold = next(
        x
        for x in stickers101.available(Plan.view(s.state, "p1", cards), "p1", "ability")
        if x["text"].startswith("Threshold")
    )
    s.perform(
        "p1", {"type": "rules_sticker101", "card_id": bear.id, "sticker_id": threshold["id"]}, trusted=True
    )
    assert view(s, bear.id).pt == (6, 2) and "trample" in view(s, bear.id).keywords
    roundtrip(s)


def test_native_placement_receipt_freezes_actor_original_object_and_actual_types(cards):
    s = setup(cards)
    rock = put(s, "Sol Ring", "battlefield")
    oid = s.state.rules.object_id(rock.id)
    chosen = attach(s, rock.id, "art")
    event = next(
        e for e in reversed(s.state.rules.events) if e.kind == "designation" and e.counter == "sticker101:art"
    )
    assert event.card == rock.id and event.object_id == oid and event.actor == "p1" and event.player == "p1"
    assert event.types == ["Artifact"]
    assert event.sticker101["id"] == chosen["id"] and event.sticker101["kind"] == "art"
    assert event.sticker101["owner"] == "p1"
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def test_sheet_import_section_and_permissive_manual_table_do_not_invent_authority():
    from app.decks.parser import parse_deck_text
    from app.game.factory import DeckCard, PlayerSetup, new_game

    parsed = parse_deck_text("Sticker Sheets\n1 Eldrazi Guacamole Tightrope\n1 Ancestral Hot Dog Minotaur")
    assert len(parsed.entries) == 2 and all(e.section == "stickers" for e in parsed.entries)
    known = SHEETS["1"]
    game = new_game(
        [
            PlayerSetup(
                "Alice",
                cards=[
                    DeckCard("stickers", 1, known["name"], known["printing_id"]),
                    DeckCard("stickers", 1, known["name"], known["printing_id"]),
                    DeckCard("stickers", 1, "Unknown sheet", None),
                ],
            )
        ],
        rng=FixedSheetRng(),
    )
    assert [s.id for s in game.players["p1"].sticker_sheets101] == ["1"]
    assert not game.cards


def test_opponent_destroy_retains_original_destroyer_after_owner_sticker_choice(cards):
    s = setup(cards)
    host = merged(s)
    put(s, "Karmic Justice", "battlefield")
    cast(s, "Song of the Dryads", [host.id])
    assert "Creature" not in view(s, host.id).types
    put(s, "Island", "battlefield", "p2")
    spell = put(s, "Beast Within", "hand", "p2")
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"G": 3})
    act(s, "p2", type="cast_spell", card_id=spell.id, targets=[host.id])
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "sticker_split101" and d.player == "p1"
    chosen = next(o.id for o in d.options if o.label == "Grizzly Bears")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[chosen])
    assert any(entry.name == "Karmic Justice" for entry in s.state.rules.stack.values()) or (
        s.state.rules.decision and "Karmic Justice" in s.state.rules.decision.prompt
    )
    roundtrip(s)
