"""Wave 110G session 11: the sticker foundation on real Oracle text.

* Wicker Picker: 702.33h sticker kicker {1}; a kicked creature spell gets a ticket counter and may take a sticker, kept on the permanent (123.5).
* Done for the Day: 603.4 intervening if (any of three creature types); "you may get {TK} or create a Treasure" is up to one of two; sticker only with all three.
* Ambassador Blorpityblorpboop: 123.8a base P/T from the printed P/T of the stickers on permanents you control, with no duration (611.2a).
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
from app.rules.sticker_sheets101 import SHEETS
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_sticker_effects101 import FixedSheetRng, pick, question, sticker
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check
from tests.wave100c_kit import chars, move, one, settle, to_phase

EXTRA = [
    real("Wicker Picker", "{3}", 3, "Artifact Creature — Scarecrow Guest", "Creature spells you cast have sticker kicker {1}. (You may pay an additional {1} as you cast a creature spell. If you do, you get {TK}, then you may put a sticker on it.)", ("2", "3")),
    real("Done for the Day", "{2}{G}", 3, "Enchantment", "At the beginning of your end step, if you control an Employee, a Performer, or a Robot, you may get {TK} or create a Treasure token. If you control all three, you may put a sticker on a nonland permanent you own.", None, "G"),
    real("Ambassador Blorpityblorpboop", "{3}{G}{U}", 5, "Legendary Creature — Alien Advisor Guest", "When Ambassador Blorpityblorpboop enters, you get {TK}{TK}{TK}, then you may put a sticker on a nonland permanent you own.\nAt the beginning of each combat, you may have Ambassador Blorpityblorpboop's base power become equal to the total power of all stickers on permanents you control and its base toughness become equal to those stickers' total toughness.", ("3", "3"), "GU"),
    real("Test Employee", "{1}", 1, "Creature — Human Employee", "", ("1", "1")),
    real("Test Performer", "{1}", 1, "Creature — Human Performer", "", ("1", "1")),
    real("Test Robot", "{1}", 1, "Artifact Creature — Robot", "", ("1", "1")),
    real("Kicker Bear", "{1}{G}", 2, "Creature — Bear", "Kicker {1}", ("2", "2"), "G"),
]
NAMES = ["Wicker Picker", "Done for the Day", "Ambassador Blorpityblorpboop"]
LIST = [n["name"] for n in EXTRA] + ["Grizzly Bears", "Lightning Bolt"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    mine = deck(cards, "Krenko, Mob Boss", [(30, "Forest"), *((1, n) for n in LIST)])
    sheets = [s for n in ("Eldrazi Guacamole Tightrope", "Ancestral Hot Dog Minotaur", "Trendy Circus Pirate") for s in SHEETS.values() if s["name"] == n]
    sheets += [s for s in SHEETS.values() if s not in sheets][:7]
    mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in sheets]
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=mine), PlayerSetup("Bob", cards=other)], shuffle=False, rng=FixedSheetRng())), cards=cards)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


def cast(s, name, **kw):
    c = one(s, name)
    move(s, c, "hand")
    act(s, "p1", type="add_mana", player="p1", mana={m: 20 for m in ("C", "W", "U", "B", "R", "G")})
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    return c


def resolve(s):
    """Pass priority until the stack is empty or a question comes up."""
    for _ in range(20):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def tickets(s):
    return s.state.players["p1"].resources.get("ticket", 0)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_wicker_picker_kick_gives_ticket_and_sticker_that_stays(cards):
    """702.33h / 123.5: pay {1} more, get {TK}, put a sticker on the spell; it is still there on the permanent."""
    s = setup(cards)
    put(s, "Wicker Picker", "battlefield")
    bear = cast(s, "Grizzly Bears", kicker=1)
    d = question(s)
    assert tickets(s) == 1 and bear.id in [o.id for o in d.options]
    chosen = sticker(s, "art")
    pick(s, [bear.id])
    pick(s, [chosen["id"]])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].stickers101[-1].sticker.id == chosen["id"]
    check(s)


def test_wicker_picker_adds_nothing_to_a_creature_with_its_own_kicker(cards):
    """Documented ceiling: no second kicker is given (702.33b), so its own kicker is paid normally and no ticket comes."""
    s = setup(cards)
    put(s, "Wicker Picker", "battlefield")
    cast(s, "Kicker Bear", kicker=1)
    settle(s)
    assert tickets(s) == 0 and s.state.rules.decision is None


def test_wicker_picker_unkicked_or_without_picker_nothing(cards):
    s = setup(cards)
    cast(s, "Grizzly Bears")
    settle(s)
    assert tickets(s) == 0
    put(s, "Wicker Picker", "battlefield")
    cast(s, "Test Employee")
    settle(s)
    assert tickets(s) == 0 and s.state.rules.decision is None
    check(s)


def test_wicker_picker_gives_no_kicker_to_noncreature_spell(cards):
    s = setup(cards)
    put(s, "Wicker Picker", "battlefield")
    victim = put(s, "Grizzly Bears", "battlefield")
    with pytest.raises(ActionError):
        cast(s, "Lightning Bolt", kicker=1, targets=[victim.id])


def _end_step(s):
    to_phase(s, "end", 1)
    return question(s)


@pytest.mark.parametrize("have, shows", [([], False), (["Test Robot"], True), (["Test Employee", "Test Performer"], True)])
def test_done_for_the_day_needs_one_of_the_types(cards, have, shows):
    s = setup(cards)
    put(s, "Done for the Day", "battlefield")
    for n in have:
        put(s, n, "battlefield")
    if not shows:
        to_phase(s, "end", 1)
        settle(s)
        assert s.state.rules.decision is None and tickets(s) == 0
        return
    d = _end_step(s)
    assert len(d.options) == 3  # one of: get {TK}, Treasure, neither ("you may")
    check(s)


@pytest.mark.parametrize("opt, ticket, treasure", [(0, 1, 0), (1, 0, 1), (None, 0, 0)])
def test_done_for_the_day_modes(cards, opt, ticket, treasure):
    s = setup(cards)
    put(s, "Done for the Day", "battlefield")
    put(s, "Test Robot", "battlefield")
    d = _end_step(s)
    pick(s, [d.options[2 if opt is None else opt].id])
    resolve(s)
    assert tickets(s) == ticket
    assert sum(c.name == "Treasure" for c in s.state.cards.values() if c.zone == "p1:battlefield") == treasure
    assert s.state.rules.decision is None  # only two of the three types: no sticker offer
    check(s)


@pytest.mark.parametrize("first, ticket", [(0, 1), (1, 0), (2, 0)])
def test_done_for_the_day_all_three_offers_a_sticker(cards, first, ticket):
    s = setup(cards)
    put(s, "Done for the Day", "battlefield")
    robot = put(s, "Test Robot", "battlefield")
    for n in ("Test Employee", "Test Performer"):
        put(s, n, "battlefield")
    d = _end_step(s)
    pick(s, [d.options[first].id])
    resolve(s)
    d = s.state.rules.decision
    assert d is not None
    chosen = sticker(s, "art")
    pick(s, [robot.id])
    pick(s, [chosen["id"]])
    settle(s)
    assert tickets(s) == ticket and s.state.cards[robot.id].stickers101[-1].sticker.id == chosen["id"]
    check(s)


@pytest.mark.parametrize("accept", [True, False])
def test_ambassador_base_pt_from_sticker_totals(cards, accept):
    """123.8a: only the printed P/T of power-and-toughness stickers count (the Bears' 5/1 sticker); optional each combat."""
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    amb = cast(s, "Ambassador Blorpityblorpboop")
    question(s)
    assert tickets(s) == 3
    chosen = sticker(s, "pt", text="5/1", cost=2)
    pick(s, [bear.id])
    pick(s, [chosen["id"]])
    settle(s)
    assert chars(s, bear).pt == (5, 1) and chars(s, amb).pt == (3, 3)
    to_phase(s, "begin_combat", 1)
    d = question(s)
    assert d.kind == "confirm"
    pick(s, ["yes" if accept else "no"])
    settle(s)
    assert chars(s, amb).pt == ((5, 1) if accept else (3, 3))
    check(s)
