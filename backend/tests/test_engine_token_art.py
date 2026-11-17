"""-- engine token art -- a token the rules engine describes ("create a 3/3 colorless Robot artifact creature token") is pictured by a
matching token printing of the card database (``TokenDef.art_id``), the source card's Scryfall related tokens first, while its
characteristics stay the engine's (app/cards/token_match.py, app/game/resolve.py). Real Oracle text (Mr. House, President and CEO)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards import token_match
from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_random_consequences import faces
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold
from tests.wave9c_kit import check

HOUSE = "Mr. House, President and CEO"
TREASURE_TEXT = "{T}, Sacrifice this token: Add one mana of any color."


def token(name: str, number: str, type_line: str, *, released: str = "2020-01-01", **extra: object) -> dict[str, object]:
    return card(name, set_code="tok", number=number, set_type="token", type_line=type_line, released_at=released,
                **{"layout": "token", **extra})


ROBOT_PIP = token("Robot", "R1", "Token Artifact Creature — Robot", released="2024-03-08", power="3", toughness="3")
ROBOT_NEWER = token("Robot", "R2", "Token Artifact Creature — Robot", released="2025-06-01", power="3", toughness="3")  # (not House's)
ROBOT_SMALL = token("Robot", "R3", "Token Artifact Creature — Robot", released="2026-01-01", power="1", toughness="1")
ROBOT_FLYING = token("Robot", "R4", "Token Artifact Creature — Robot", released="2026-02-01", power="3", toughness="3", colors=["U"])
TREASURE_PIP = token("Treasure", "T9", "Token Artifact — Treasure", released="2024-03-08", oracle_text=TREASURE_TEXT)
# a double-faced token printing (a Commander insert): its back face is a 3/3 Robot
INSERT = token("Soldier // Robot", "D1", "Token Creature — Soldier // Token Artifact Creature — Robot", released="2026-05-01",
               layout="double_faced_token", image_uris=None, card_faces=[
                   {"name": "Soldier", "type_line": "Token Creature — Soldier", "power": "1", "toughness": "1", "colors": ["W"],
                    "oracle_text": "", "image_uris": {"normal": "https://img.example/d1a.jpg"}},
                   {"name": "Robot", "type_line": "Token Artifact Creature — Robot", "power": "3", "toughness": "3", "colors": [],
                    "oracle_text": "", "image_uris": {"normal": "https://img.example/d1b.jpg"}}])


# real Oracle text (Scryfall): a token copy, and "becomes a copy"
COPIERS = [
    card("Cackling Counterpart", set_code="tst", number="CC1", mana_cost="{1}{U}{U}", cmc=3.0, type_line="Instant", colors=["U"],
         color_identity=["U"], oracle_text="Create a token that's a copy of target creature you control.\nFlashback {5}{U}{U} (You may cast "
                                           "this card from your graveyard for its flashback cost. Then exile it.)"),
    card("Mirrorweave", set_code="tst", number="MW1", mana_cost="{2}{W/U}{W/U}", cmc=4.0, type_line="Instant", colors=["U", "W"],
         color_identity=["U", "W"], oracle_text="Each other creature becomes a copy of target nonlegendary creature until end of turn."),
]


def _house() -> dict[str, object]:
    data = json.loads((Path(__file__).parent / "fixtures/random_receipt_consumers_cards.json").read_text(encoding="utf-8"))
    raw = next(c for c in data if c["name"] == HOUSE)
    parts = [{"object": "related_card", "id": t["id"], "component": "token", "name": t["name"], "type_line": t["type_line"]}
             for t in (ROBOT_PIP, TREASURE_PIP)]
    return card(HOUSE, set_code="pip", number="H1", all_parts=parts, **{k: v for k, v in raw.items() if k not in ("name", "set_code")})


@pytest.fixture()
def cards(settings):
    from tests.test_rules_wave24b_dice import EXTRA

    existing = {c["name"]: c for c in [*fixture_cards(), *EXTRA]}
    existing[HOUSE] = _house()
    settings.ensure_dirs()
    build_database([*existing.values(), *COPIERS, ROBOT_PIP, ROBOT_NEWER, ROBOT_SMALL, ROBOT_FLYING, TREASURE_PIP, INSERT], settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def _picture(repo: CardRepository, printing: dict[str, object], face: int = 0) -> None:
    path = repo.images.path_for(str(printing["id"]), face=face, size="normal", is_token=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8\xff\xe0art")


def _house_rolls(cards, monkeypatch, roll: int, extra=()):
    s = three(cards, [HOUSE, "Sol Ring", "Lightning Bolt", *extra], ["Sol Ring"], ["Sol Ring"])
    hold(s)
    from tests.test_rules_wave30m_durations import to_phase

    house = put(s, HOUSE, "battlefield")
    to_phase(s, "main1", turn=4)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 4})
    priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=house.id, ability=1, sources=[])
    faces(monkeypatch, [roll])
    settle(s)
    return s


def _made(s, name):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == "p1:battlefield"]


def test_mr_house_robot_and_treasure_are_pictured_by_his_related_tokens(cards, monkeypatch):
    s = _house_rolls(cards, monkeypatch, 6)
    [robot], [treasure] = _made(s, "Robot"), _made(s, "Treasure")
    # the engine's token, unchanged: no printing, the engine's characteristics; the picture is House's own related tokens'
    assert robot.card_id is None and treasure.card_id is None
    assert (robot.token.name, robot.token.power, robot.token.toughness, robot.token.colors, robot.token.type_line) == \
        ("Robot", "3", "3", [], "Token Artifact Creature — Robot")
    assert treasure.token.type_line == "Token Artifact — Treasure" and treasure.token.text.startswith("{T}, Sacrifice")
    assert (robot.token.art_id, robot.token.art_face) == (ROBOT_PIP["id"], 0)
    assert (treasure.token.art_id, treasure.token.art_face) == (TREASURE_PIP["id"], 0)
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", cards, None).ch(robot).pt == (3, 3)
    # every seat sees the picture with the token
    for viewer in ("p1", "p2", "p3"):
        assert s.view(viewer)["cards"][robot.id]["token"]["art_id"] == ROBOT_PIP["id"]
        assert s.view(viewer)["cards"][robot.id]["card_id"] is None
    # recorded with the action: replays, a save and a load keep it
    check(s)
    from app.game.state import GameState

    again = GameState.model_validate_json(s.state.model_dump_json())
    assert again.cards[robot.id].token.art_id == ROBOT_PIP["id"]


def test_a_token_with_no_related_printing_takes_any_matching_one_with_a_picture_here_first(cards):
    s = three(cards, ["Sol Ring"], ["Sol Ring"], ["Sol Ring"])
    spec = {"name": "Robot", "power": "3", "toughness": "3", "colors": [], "type_line": "Token Artifact Creature — Robot"}
    act(s, "p1", type="create_token", token=spec)
    [first] = _made(s, "Robot")
    # no picture here at all: the newest single-faced 3/3 colourless Robot (not the 1/1, not the blue one, not the insert)
    assert first.token.art_id == ROBOT_NEWER["id"]
    _picture(cards, ROBOT_PIP)
    cards._token_art.clear()  # (remembered per database: a picture arriving later counts from the next database open)
    act(s, "p1", type="create_token", token=spec)
    second = next(c for c in _made(s, "Robot") if c.id != first.id)
    assert second.token.art_id == ROBOT_PIP["id"]
    assert first.token.art_id == ROBOT_NEWER["id"]  # (the first keeps the picture it was made with)
    check(s)


def test_a_double_faced_token_printing_pictures_the_face_that_matches(cards):
    want = token_match.wanted("Robot", "Token Artifact Creature — Robot", "3", "3", [])
    assert token_match.match_face(cards.rules_card(INSERT["id"]), want) == 1
    assert token_match.match_face(cards.rules_card(ROBOT_SMALL["id"]), want) is None
    assert token_match.match_face(cards.rules_card(ROBOT_FLYING["id"]), want) is None
    _picture(cards, INSERT, face=1)
    assert cards.token_art(None, "Robot", "Token Artifact Creature — Robot", "3", "3", []) == (INSERT["id"], 1)


def test_unmatched_and_printed_tokens_are_left_alone(cards):
    s = three(cards, ["Sol Ring"], ["Sol Ring"], ["Sol Ring"])
    act(s, "p1", type="create_token", token={"name": "Gizmo", "power": "2", "toughness": "2", "type_line": "Token Creature — Gizmo"})
    [gizmo] = _made(s, "Gizmo")
    assert gizmo.token.art_id is None and gizmo.card_id is None
    # a database token chosen by hand keeps its printing (characteristics and picture), no art_id
    act(s, "p1", type="create_token", token={"card_id": TREASURE_PIP["id"]})
    [treasure] = _made(s, "Treasure")
    assert treasure.card_id == TREASURE_PIP["id"] and treasure.token.art_id is None
    check(s)


def test_no_card_database_means_no_picture():
    from app.game.actions import TokenSpec
    from app.game.resolve import NoCardInfo, _token_def

    t = _token_def(TokenSpec(name="Robot", power="3", toughness="3", type_line="Token Artifact Creature — Robot"), NoCardInfo())
    assert t.art_id is None and t.name == "Robot"


# -- copies of engine tokens: the copy is pictured as what it copies (TokenDef.art_id goes with the copiable values, 707.2) ---------------------
def _cast(s, name, targets, **pool):
    from tests.wave9c_kit import card_named

    act(s, "p1", type="add_mana", player="p1", mana=pool)
    priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=card_named(s, name, "p1").id, targets=targets)
    settle(s)


def test_a_token_copy_of_a_pictured_engine_token_has_its_picture(cards, monkeypatch):
    s = _house_rolls(cards, monkeypatch, 4, ["Cackling Counterpart"])
    [robot] = _made(s, "Robot")
    assert robot.token.art_id == ROBOT_PIP["id"]
    act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Cackling Counterpart")], to={"zone": "hand"})
    _cast(s, "Cackling Counterpart", [robot.id], U=2, C=1)
    copy = next(c for c in _made(s, "Robot") if c.id != robot.id)
    # (looked up afresh it would be the newest matching printing, ROBOT_NEWER: Counterpart has no related Robot)
    assert copy.card_id is None and (copy.token.art_id, copy.token.art_face) == (ROBOT_PIP["id"], 0)
    for viewer in ("p1", "p2"):
        seen = s.view(viewer)["cards"][copy.id]
        assert seen["card_id"] is None and seen["token"]["art_id"] == ROBOT_PIP["id"]
    check(s)


def test_a_client_cant_pass_a_picture_on(cards):
    s = three(cards, ["Sol Ring"], ["Sol Ring"], ["Sol Ring"])
    act(s, "p1", type="create_token", token={"name": "Gizmo", "power": "2", "toughness": "2", "type_line": "Token Creature — Gizmo",
                                              "art_id": ROBOT_PIP["id"], "art_face": 1})
    [gizmo] = _made(s, "Gizmo")
    assert gizmo.token.art_id is None and gizmo.token.art_face == 0  # (resolve clears it: only the engine's token copies pass one on)
    check(s)


def test_becoming_a_copy_of_another_token_shows_that_tokens_picture(cards, monkeypatch):
    s = _house_rolls(cards, monkeypatch, 4, ["Mirrorweave"])
    [robot] = _made(s, "Robot")
    act(s, "p1", type="create_token", token={"name": "Soldier", "power": "1", "toughness": "1", "colors": ["W"],
                                              "type_line": "Token Creature — Soldier"})
    [soldier] = _made(s, "Soldier")
    assert (soldier.token.art_id, soldier.token.art_face) == (INSERT["id"], 0)  # (the insert's Soldier face)
    act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Mirrorweave")], to={"zone": "hand"})
    _cast(s, "Mirrorweave", [soldier.id], W=2, C=2)
    for viewer in ("p1", "p2"):
        seen = s.view(viewer)["cards"][robot.id]
        assert seen["name"] == "Soldier" and seen["token"]["name"] == "Soldier" and seen["copy_of"]["source_name"] == "Soldier"
        assert (seen["token"]["art_id"], seen["token"]["art_face"]) == (INSERT["id"], 0)  # (not the Robot picture it had as itself)
    assert s.state.cards[robot.id].token.art_id == ROBOT_PIP["id"]  # (the object's own token is unchanged: the copy is a view of layer 1)
    check(s)
