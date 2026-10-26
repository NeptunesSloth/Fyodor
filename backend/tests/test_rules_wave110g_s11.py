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
    real("Mist of Stagnation", "{2}{U}{U}", 4, "Enchantment", "Permanents don't untap during their controllers' untap steps.\nAt the beginning of each player's upkeep, that player chooses a permanent for each card in their graveyard, then untaps those permanents.", None, "U"),
    real("J\u00f6tun Grunt", "{1}{W}", 2, "Creature \u2014 Giant Soldier", "Cumulative upkeep\u2014Put two cards from a single graveyard on the bottom of their owner's library. (At the beginning of your upkeep, put an age counter on this permanent, then sacrifice it unless you pay its upkeep cost for each age counter on it.)", ("4", "4"), "W"),
    real("Kicker Bear", "{1}{G}", 2, "Creature — Bear", "Kicker {1}", ("2", "2"), "G"),
]
NAMES = ["Wicker Picker", "Done for the Day", "Ambassador Blorpityblorpboop", "Mist of Stagnation", "J\u00f6tun Grunt"]
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
    """702.33c: two kicker abilities are not modelled: its own kicker is paid normally, no ticket comes, and the log hands the second kicker to manual play."""
    s = setup(cards)
    put(s, "Wicker Picker", "battlefield")
    cast(s, "Kicker Bear", kicker=1)
    settle(s)
    assert tickets(s) == 0 and s.state.rules.decision is None
    assert any("sticker kicker is manual play" in "".join(p.t or "" for p in x.parts) for x in s.state.log)


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


def _choose(s, which):
    """"You may get {TK} or create a Treasure token": which = 0 (ticket), 1 (Treasure) or None (neither); never both."""
    for i in range(2):
        if which is not None and which > i:
            pick(s, ["decline"])
        elif which == i:
            pick(s, ["pay"])
            return
        else:
            pick(s, ["decline"])


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
    assert [o.id for o in d.options] == ["pay", "decline"] and "{TK}" in d.prompt  # "you may A or B": ask A, then B; no invented "neither" mode
    check(s)


@pytest.mark.parametrize("opt, ticket, treasure", [(0, 1, 0), (1, 0, 1), (None, 0, 0)])
def test_done_for_the_day_modes(cards, opt, ticket, treasure):
    s = setup(cards)
    put(s, "Done for the Day", "battlefield")
    put(s, "Test Robot", "battlefield")
    d = _end_step(s)
    _choose(s, opt)
    resolve(s)
    assert tickets(s) == ticket
    assert sum(c.name == "Treasure" for c in s.state.cards.values() if c.zone == "p1:battlefield") == treasure
    assert s.state.rules.decision is None  # only two of the three types: no sticker offer
    check(s)


@pytest.mark.parametrize("first, ticket", [(0, 1), (1, 0), (None, 0)])
def test_done_for_the_day_all_three_offers_a_sticker(cards, first, ticket):
    s = setup(cards)
    put(s, "Done for the Day", "battlefield")
    robot = put(s, "Test Robot", "battlefield")
    for n in ("Test Employee", "Test Performer"):
        put(s, n, "battlefield")
    d = _end_step(s)
    _choose(s, first)
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


@pytest.mark.parametrize("dead", [0, 2])
def test_mist_of_stagnation_untaps_one_permanent_per_graveyard_card(cards, dead):
    """Permanents stay tapped (no untap step); at the owner's upkeep they untap as many chosen permanents as they have cards in their graveyard."""
    s = setup(cards)
    put(s, "Mist of Stagnation", "battlefield")
    bears = [put(s, "Grizzly Bears", "battlefield") for _ in range(1)] + [put(s, "Test Employee", "battlefield"), put(s, "Test Robot", "battlefield")]
    act(s, "p1", type="tap", card_ids=[b.id for b in bears])
    gy = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:dead]
    if gy:
        act(s, "p1", type="move", card_ids=[c.id for c in gy], to={"player": "p1", "zone": "graveyard"})
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None or (s.state.turn.number == 3 and s.state.turn.phase == "main1"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    if not dead:
        assert d is None and all(s.state.cards[b.id].tapped for b in bears)
        return
    assert d.player == "p1" and d.max_choices == 2 and "untap" in d.prompt
    pick(s, [bears[0].id, bears[2].id])
    settle(s)
    assert [s.state.cards[b.id].tapped for b in bears] == [False, True, False]
    check(s)


def _grunt_upkeep(s, mine, theirs, age=0):
    """Grunt on the battlefield with ``mine`` / ``theirs`` Forest/Island cards in the graveyards, on to Alice's turn-3 upkeep decision."""
    grunt = put(s, "J\u00f6tun Grunt", "battlefield")
    if age:
        act(s, "p1", type="counter", card_ids=[grunt.id], kind="age", delta=age)
    for pid, n, name in (("p1", mine, "Forest"), ("p2", theirs, "Island")):
        ids = [c.id for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:library"][:n]
        if ids:
            act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "graveyard"})
    for _ in range(40):
        if s.state.rules.decision is not None or (s.state.turn.number == 3 and s.state.turn.phase == "main1"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return grunt


def _answer(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def test_jotun_grunt_pays_two_cards_from_one_graveyard_to_the_bottom(cards):
    """702.24a: pay the cost for the age counter: two cards of a single graveyard (their owner's) go to the bottom of that library."""
    s = setup(cards)
    grunt = _grunt_upkeep(s, 3, 2)
    d = s.state.rules.decision
    assert d.player == "p1" and "put two cards" in d.prompt
    _answer(s, ["pay"])
    d = s.state.rules.decision
    assert sorted(o.id for o in d.options) == ["p1", "p2"]  # both graveyards hold two or more cards
    _answer(s, ["p2"])
    gy = list(s.state.zones["p2:graveyard"])
    _answer(s, gy)
    d = s.state.rules.decision
    assert d.kind == "order" and d.player == "p2"  # 401.4: the cards' owner arranges them, not the payer
    _answer(s, [gy[1], gy[0]])
    settle(s)
    assert s.state.zones["p2:graveyard"] == [] and s.state.zones["p2:library"][-2:] == [gy[0], gy[1]]  # first chosen is the very bottom
    assert s.state.cards[grunt.id].zone == "p1:battlefield" and s.state.cards[grunt.id].counters["age"] == 1
    check(s)


def test_jotun_grunt_declined_is_sacrificed(cards):
    s = setup(cards)
    grunt = _grunt_upkeep(s, 2, 0)
    _answer(s, ["decline"])
    settle(s)
    assert s.state.cards[grunt.id].zone == "p1:graveyard" and len(s.state.zones["p1:graveyard"]) == 3
    check(s)


@pytest.mark.parametrize("mine, theirs, age, paid", [(0, 0, 0, False), (1, 1, 0, False), (3, 0, 1, False), (4, 0, 1, True)])
def test_jotun_grunt_all_or_nothing(cards, mine, theirs, age, paid):
    """118.3: no partial payment: with 2 age counters (one is added at upkeep) it needs two separate pairs (one graveyard may supply both); cards that cannot pay mean sacrifice with no question."""
    s = setup(cards)
    grunt = _grunt_upkeep(s, mine, theirs, age)
    if not paid:
        assert s.state.rules.decision is None or "put two cards" not in s.state.rules.decision.prompt
        assert s.state.cards[grunt.id].zone == "p1:graveyard"
        return
    _answer(s, ["pay"])
    for _ in range(2):  # one graveyard only: no graveyard question
        d = s.state.rules.decision
        assert d.max_choices == 2
        _answer(s, [o.id for o in d.options][:2])
        d = s.state.rules.decision
        assert d.kind == "order"
        _answer(s, [o.id for o in d.options])
    settle(s)
    assert s.state.cards[grunt.id].zone == "p1:battlefield" and s.state.zones["p1:graveyard"] == []
    check(s)
