# ruff: noqa: F811  (the imported fixtures are used as test arguments)
"""Wave 110B final pass: Clandestine Chameleon with a really placed sticker (123.2, 613.1f): Pin Collection's ability sticker (on a permanent its owner owns) reaches the Chameleon."""
from __future__ import annotations

from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.sticker_sheets101 import SHEETS
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import find, put
from tests.test_rules_sticker_effects101 import FixedSheetRng, cast, pick, question
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110i_s11b import EXTRA, _settle, cards  # noqa: F401
from tests.wave9c_kit import check
from tests.wave100c_kit import to_phase

CHAM = "Clandestine Chameleon has all abilities of ability stickers on other permanents you own and cards in your graveyard."
if all(c["name"] != "Clandestine Chameleon" for c in EXTRA):
    EXTRA.append(real("Clandestine Chameleon", "{2}{U}", 3, "Creature — Lizard Guest", CHAM, ("2", "2"), "U"))


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Clandestine Chameleon")).level == "FULL"


def test_chameleon_has_pin_collection_sticker_ability(cards):
    """The Pin Collection's Deathtouch sticker gives the Chameleon Deathtouch while the Equipment is on the battlefield; it is gone when the Equipment leaves (613.1f)."""
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), (1, "Pin Collection"), (1, "Clandestine Chameleon")])
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in list(SHEETS.values())[:10]]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng())), cards=cards)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    cham = put(s, "Clandestine Chameleon", "battlefield")
    assert "deathtouch" not in Plan(s.state, "p1", s.cards, None).ch(cham).keywords
    cast(s, "Pin Collection", x_value=2)
    pin = find(s, "Pin Collection")
    question(s)
    pick(s, [pin.id])
    from app.rules import stickers101

    mine_stickers = {v["id"]: v for v in stickers101.available(Plan.view(s.state, "p1", s.cards), "p1", "ability")}
    pick(s, [next(v["id"] for v in mine_stickers.values() if v["text"] == "Deathtouch")])
    _settle(s, first=False)
    assert "deathtouch" in Plan(s.state, "p1", s.cards, None).ch(cham).keywords
    check(s)
    act(s, "p1", type="move", card_ids=[pin.id], to={"player": "p1", "zone": "graveyard"})  # a card in the graveyard still counts
    assert "deathtouch" in Plan(s.state, "p1", s.cards, None).ch(cham).keywords
    act(s, "p1", type="move", card_ids=[pin.id], to={"zone": "exile"})
    assert "deathtouch" not in Plan(s.state, "p1", s.cards, None).ch(cham).keywords
    check(s)
