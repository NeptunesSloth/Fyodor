"""Wave 110J: Last Voyage of the _____ (real Oracle text, tests/fixtures/wave110j_cards.json), on the CR123 name-sticker machinery.

* 205.1 / 303.4: it becomes an Aura with enchant creature whether or not a name sticker was put on it; the creature card returned from the graveyard is enchanted by it.
* Enchanted creature gets +2/+0 for each name sticker on it with seven or fewer letters ("Hot Dog" has six, "Minotaur" eight).
* 603.10a: when the Aura leaves the battlefield, the enchanted creature's controller sacrifices it.
"""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.sticker_sheets101 import SHEETS
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_sticker_effects101 import DATA, FixedSheetRng, cast, pick, question, sticker
from tests.wave9c_kit import check
from tests.wave100c_kit import settle, to_phase
from tests.wave110j_kit import DATA as J  # noqa: F401

VOYAGE = "Last Voyage of the _____"


@pytest.fixture
def cards(settings):
    rows = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        rows[c["name"]] = card(c["name"], set_code="sf101", number=str(i), **{k: v for k, v in c.items() if k not in ("name", "set_code", "number", "collector_number")})
    for i, c in enumerate(J):
        if c["name"] in (VOYAGE, "Naturalize"):
            rows[c["name"]] = card(c["name"], set_code="w110jv", number=f"V{i:03d}", **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(rows.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), *((1, n) for n in (VOYAGE, "Grizzly Bears", "Naturalize"))])
    sheets = [s for name in ("Eldrazi Guacamole Tightrope", "Ancestral Hot Dog Minotaur") for s in SHEETS.values() if s["name"] == name]
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in sheets]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng())), cards=cards)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


def voyage(cards, text):
    """Cast it with a Grizzly Bears in the graveyard; ``text``: the name sticker put on it (None: declined). Returns (game, Voyage, Bears)."""
    s = setup(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    v = cast(s, VOYAGE)
    question(s)
    if text is None:
        pick(s, [])
    else:
        pick(s, [v.id])
        pick(s, [sticker(s, "name", text=text)["id"]])
        pick(s, ["0"])
    for _ in range(20):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            pick(s, [bears.id] if bears.id in [o.id for o in d.options] else [d.options[0].id])
    return s, v, bears


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(VOYAGE)).level == "FULL"


@pytest.mark.parametrize("text,power", [("Hot Dog", 4), ("Minotaur", 2), (None, 2)])
def test_returns_the_creature_enchanted_and_pumped_by_short_stickers(cards, text, power):
    s, v, bears = voyage(cards, text)
    now_v, now_b = s.state.cards[v.id], s.state.cards[bears.id]
    assert now_b.zone == "p1:battlefield" and now_v.attached_to == bears.id
    ch = Plan.view(s.state, "p1", s.cards).ch(now_b)
    assert ch.pt[0] == power
    assert "Aura" in Plan.view(s.state, "p1", s.cards).ch(now_v).subtypes
    check(s)


def test_the_enchanted_creature_is_sacrificed_when_the_aura_leaves(cards):
    s, v, bears = voyage(cards, "Hot Dog")
    cast(s, "Naturalize", targets=[v.id])
    settle(s)
    assert s.state.cards[bears.id].zone.endswith(":graveyard")
    check(s)
