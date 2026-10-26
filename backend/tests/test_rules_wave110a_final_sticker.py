"""Wave 110A final pass: Fight the _____ Fight (real Oracle text) on the CR123 name-sticker machinery.

* Ruling 2022-10-07: with no name sticker put on it as the enters ability resolves, the reflexive fight never triggers (603.12).
* Enchanted creature gets +0/+2 for each name sticker on the Aura with eight or more letters ("Minotaur" has eight, "Hot Dog" six).
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
from tests.wave100c_kit import to_phase
from tests.wave110a_kit import DATA as A110

FIGHT = "Fight the _____ Fight"


@pytest.fixture
def cards(settings):
    rows = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        rows[c["name"]] = card(c["name"], set_code="sf101", number=str(i), **{k: v for k, v in c.items() if k not in ("name", "set_code", "number", "collector_number")})
    for i, c in enumerate(A110):
        if c["name"] in (FIGHT, "Hill Giant"):
            rows[c["name"]] = card(c["name"], set_code="w110af", number=f"F{i:03d}", **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(rows.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), *((1, n) for n in (FIGHT, "Hill Giant"))])
    sheets = [s for name in ("Eldrazi Guacamole Tightrope", "Ancestral Hot Dog Minotaur") for s in SHEETS.values() if s["name"] == name]
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in sheets]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island"), (1, "Grizzly Bears")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng())), cards=cards)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


def fight(cards, text, target=True):
    """Cast it on Alice's Hill Giant (3/3) with Bob's Grizzly Bears (2/2) there; ``text``: the name sticker put on it (None: declined)."""
    s = setup(cards)
    giant = put(s, "Hill Giant", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield", "p2")
    aura = cast(s, FIGHT, targets=[giant.id])
    question(s)
    if text is None:
        pick(s, [])
    else:
        pick(s, [aura.id])
        pick(s, [sticker(s, "name", text=text)["id"]])
        pick(s, ["0"])
    for _ in range(20):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            pick(s, [bears.id] if bears.id in [o.id for o in d.options] and target else [d.options[0].id] if d.min_choices else [])
    return s, aura, giant, bears


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(FIGHT)).level == "FULL"


@pytest.mark.parametrize(("text", "toughness"), [("Minotaur", 5), ("Hot Dog", 3)])
def test_a_sticker_lets_the_enchanted_creature_fight_and_long_names_pump_toughness(cards, text, toughness):
    s, aura, giant, bears = fight(cards, text)
    view = Plan.view(s.state, "p1", s.cards)
    assert s.state.cards[bears.id].zone == "p2:graveyard"  # 3 damage from the Giant
    assert view.ch(s.state.cards[giant.id]).pt == (3, toughness)
    assert s.state.cards[giant.id].damage == 2  # the Bears' 2 damage in the fight
    check(s)


def test_no_sticker_means_no_fight_and_no_pump(cards):
    s, aura, giant, bears = fight(cards, None)
    assert s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[giant.id].damage == 0
    assert Plan.view(s.state, "p1", s.cards).ch(s.state.cards[giant.id]).pt == (3, 3)
    check(s)


def test_up_to_one_target_the_fight_may_have_no_target(cards):
    s, aura, giant, bears = fight(cards, "Hot Dog", target=False)
    assert s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[giant.id].damage == 0
    check(s)
