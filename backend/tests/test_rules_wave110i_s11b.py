# ruff: noqa: F811  (the imported fixtures are used as test arguments)
"""Wave 110I session 11: Wee Champion and Goblin Airbrusher (123.2 stickers, 608.2c "instead"): a sticker of any kind placed on any card by you triggers them; an
art sticker gives the other mode."""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.sticker_sheets101 import SHEETS
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_sticker_effects101 import DATA, FixedSheetRng, cast, pick, place
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check
from tests.wave100c_kit import to_phase

WEE = "Whenever you place a sticker, this creature gets +1/+1 until end of turn. If it's an art sticker, instead put a +1/+1 counter on this creature."
AIR = ("Whenever you place a sticker, create a Treasure token. If it's an art sticker, instead create two Treasure tokens. "
       "(They're artifacts with \"{T}, Sacrifice this token: Add one mana of any color.\")")
EXTRA = [real("Wee Champion", "{1}{R}", 2, "Creature — Goblin Warrior", WEE, ("2", "2"), "R"),
         real("Goblin Airbrusher", "{1}{R}", 2, "Creature — Goblin Artificer", AIR, ("2", "2"), "R")]


@pytest.fixture()
def cards(settings):
    rows = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        fields = {k: v for k, v in c.items() if k not in ("name", "set_code", "number", "collector_number")}
        rows[c["name"]] = card(c["name"], set_code=c.get("set_code", "sf101") if "Attraction" in c.get("type_line", "") else "sf101",
                               number=str(c.get("collector_number", i)) if "Attraction" in c.get("type_line", "") else str(i), **fields)
    for c in EXTRA:
        rows[c["name"]] = c
    settings.ensure_dirs()
    build_database(rows.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def start(cards):
    names = ["Grizzly Bears", "Ticketomaton", "Wee Champion", "Goblin Airbrusher"]
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), *((1, n) for n in names)])
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in list(SHEETS.values())[:10]]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island"), (1, "Grizzly Bears")])
    state = enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng()))
    s = GameSession(state, cards=cards)
    for pid in state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


@pytest.mark.parametrize("name", ["Wee Champion", "Goblin Airbrusher"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("kind", ["art", "name"])
def test_wee_champion_and_goblin_airbrusher(cards, kind):
    """Ticketomaton's sticker goes on a Bear (a non-Champion): art, Wee gets a +1/+1 counter and Airbrusher makes two Treasures; otherwise Wee gets +1/+1 until end of turn and
    Airbrusher makes one."""
    s = start(cards)
    put(s, "Goblin Airbrusher", "battlefield")
    wee, bear = put(s, "Wee Champion", "battlefield"), put(s, "Grizzly Bears", "battlefield")
    cast(s, "Ticketomaton")
    place(s, bear.id, kind=kind)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            pick(s, [o.id for o in d.options][: max(1, d.min_choices)])
    w = s.state.cards[wee.id]
    treasures = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Treasure"]
    assert (w.counters.get("+1/+1", 0), len(treasures)) == ((1, 2) if kind == "art" else (0, 1))
    oid = s.state.rules.object_id(wee.id)
    assert any(oid in e.affected and e.power == 1 for e in s.state.rules.effects) == (kind != "art")  # (+1/+1 until end of turn only for a non-art sticker)
    check(s)
