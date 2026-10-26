"""Wave 110J: Park Bleater and Lineprancers (real Oracle text, tests/fixtures/wave110j_cards.json), on the CR123 sticker machinery.

* 123.1 / 509.1c: Lineprancers' "{3}{G}: Target creature you don't control blocks target creature you control with a power and toughness sticker on it
  other than Lineprancers this turn if able." targets only another creature with such a sticker and makes the opponent's creature block it.
* 123.1 / 123.2: Park Bleater's "{W}, {T}: You may put a sticker on a creature you own that entered this turn." offers only creatures you own that
  entered the battlefield this turn (history), may be declined, and the sticker stays on the creature.
"""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.sticker_sheets101 import SHEETS
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_sticker_effects101 import DATA, FixedSheetRng, cast, pick, place, question
from tests.wave9c_kit import check
from tests.wave100c_kit import settle, to_phase
from tests.wave110j_kit import DATA as J  # noqa: F401

BLEATER = "Park Bleater"


@pytest.fixture
def cards(settings):
    rows = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        rows[c["name"]] = card(c["name"], set_code="sf101", number=str(i), **{k: v for k, v in c.items() if k not in ("name", "set_code", "number", "collector_number")})
    for i, c in enumerate(J):
        if c["name"] in (BLEATER, "Lineprancers"):
            rows[c["name"]] = card(c["name"], set_code="w110js", number=f"S{i:03d}", **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(rows.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), *((1, n) for n in (BLEATER, "Lineprancers", "Grizzly Bears", "Hill Giant", "Llanowar Elves"))])
    sheets = [s for name in ("Eldrazi Guacamole Tightrope", "Ancestral Hot Dog Minotaur") for s in SHEETS.values() if s["name"] == name]
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in sheets]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island"), (1, "Grizzly Bears")])
    state = enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng()))
    s = GameSession(state, cards=cards)
    for pid in state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


def test_full(cards):
    for n in (BLEATER, "Lineprancers"):
        assert coverage.of_card_data(cards.resolve(n)).level == "FULL"


@pytest.mark.parametrize("take", [True, False])
def test_park_bleater_offers_only_creatures_that_entered_this_turn(cards, take):
    """123.1: only the creature that entered this turn is offered (not Bleater, not the one from an earlier turn)."""
    s = setup(cards)
    bleater = put(s, BLEATER, "battlefield")
    old = put(s, "Hill Giant", "battlefield")
    to_phase(s, "main1", 3)
    new = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="resource", key="ticket", delta=9)
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="activate_ability", card_id=bleater.id, ability=1)
    d = question(s)
    assert [o.id for o in d.options] == [new.id] and old.id not in [o.id for o in d.options]
    if take:
        place(s, new.id)
    else:
        pick(s, [])
    settle(s)
    assert bool(s.state.cards[new.id].stickers101) is take and not s.state.cards[old.id].stickers101
    check(s)


def _prance(s, on):
    """Cast Lineprancers (ETB: two tickets, then a power and toughness sticker on ``on``)."""
    cast(s, "Lineprancers")
    question(s)
    place(s, on.id, kind="pt")
    settle(s)


def _activate(s, mine, theirs):
    lp = next(c for c in s.state.cards.values() if c.name == "Lineprancers")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1, "C": 3})
    act(s, "p1", type="activate_ability", card_id=lp.id, ability=1, targets=[theirs.id, mine.id], target_counts=[1, 1])
    settle(s)
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[theirs.id]).imposed


def test_lineprancers_forces_a_block_of_the_stickered_creature(cards):
    s = setup(cards)
    giant = put(s, "Hill Giant", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield", "p2")
    _prance(s, giant)
    assert f"must_block_obj:{s.state.rules.object_id(giant.id)}" in _activate(s, giant, bears)
    check(s)


def test_lineprancers_needs_a_stickered_creature_other_than_itself(cards):
    s = setup(cards)
    giant = put(s, "Hill Giant", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield", "p2")
    _prance(s, next(c for c in s.state.cards.values() if c.name == "Lineprancers"))  # the sticker goes on Lineprancers itself
    lp = next(c for c in s.state.cards.values() if c.name == "Lineprancers")
    for bad in (lp, giant):  # itself (excluded), and a creature without a sticker
        act(s, "p1", type="add_mana", player="p1", mana={"G": 1, "C": 3})
        with pytest.raises(ActionError, match="target"):
            act(s, "p1", type="activate_ability", card_id=lp.id, ability=1, targets=[bears.id, bad.id], target_counts=[1, 1])
