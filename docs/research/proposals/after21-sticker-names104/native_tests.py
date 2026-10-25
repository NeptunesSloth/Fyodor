"""Newly placed name receipts: six unique vowels, not the whole name or old stickers."""

from __future__ import annotations

import pytest

from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.sticker_sheets101 import SHEETS
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_sticker_effects101 import FixedSheetRng, cast, cold, pick, place, question
from tests.test_rules_sticker_effects101 import cards as _cards
from tests.wave9c_kit import check
from tests.wave100c_kit import chars, settle, to_phase

cards = _cards
NAMES = [
    "_____ _____ _____ Trespasser",
    "_____ Balls of Fire",
    "Make a _____ Splash",
    "Ticketomaton",
    "Disenchant",
]


def setup(cards, sheets=True):
    mine = deck(
        cards,
        "Krenko, Mob Boss",
        [
            (30, "Forest"),
            *((1, n) for n in [*NAMES, "Cloudshift", "Grizzly Bears", "Vorinclex, Monstrous Raider"]),
        ],
    )
    other = deck(cards, "Atraxa, Praetors' Voice", [(30, "Island")])
    if sheets:
        wanted = ["Eldrazi Guacamole Tightrope", "Ancestral Hot Dog Minotaur", "Trendy Circus Pirate"]
        selected = [s for n in wanted for s in SHEETS.values() if s["name"] == n]
        selected += [s for s in SHEETS.values() if s not in selected][:7]
        mine += [DeckCard("stickers", 1, s["name"], s["printing_id"]) for s in selected]
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
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    to_phase(s, "main1", 1)
    return s


@pytest.mark.parametrize("name", NAMES[:3])
def test_whole_name_marker_cards104(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("put_name", [True, False])
def test_actual_trespasser_counts_stickers_not_words_and_unblockable_without_stickers104(cards, put_name):
    s = setup(cards)
    source = cast(s, NAMES[0])
    question(s)
    if put_name:
        place(s, source.id, "name", text="Hot Dog")
    else:
        pick(s, [])
    settle(s)
    before = chars(s, s.state.cards[source.id]).pt[0]
    ability = next(a for a in chars(s, s.state.cards[source.id]).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability.index, sources=[])
    settle(s)
    assert chars(s, s.state.cards[source.id]).pt[0] == before + int(put_name)
    assert "cant_be_blocked" in chars(s, s.state.cards[source.id]).imposed
    check(s)


@pytest.mark.parametrize("text,n", [("Hot Dog", 2), ("Guacamole", 1)])
def test_balls_real_placement_counts_each_o_and_targets_player104(cards, text, n):
    s = setup(cards)
    source = cast(s, NAMES[1])
    question(s)
    place(s, source.id, "name", text=text)
    d = question(s)
    assert "p2" in [o.id for o in d.options]
    before = s.state.players["p2"].life
    pick(s, ["p2"])
    settle(s)
    assert s.state.players["p2"].life == before - n
    check(s)


@pytest.mark.parametrize("text,n", [("Minotaur", 1), ("Tightrope", 0)])
def test_splash_real_placement_uses_letter_count_as_target_cap104(cards, text, n):
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    source = cast(s, NAMES[2])
    question(s)
    place(s, source.id, "name", text=text)
    if n:
        d = question(s)
        assert d.max_choices == 1
        pick(s, [bear.id])
    settle(s)
    assert s.state.cards[bear.id].tapped == bool(n)
    check(s)


def test_balls_genuine_cold_source_leaves_uses_its_original_name_markers104(cards, tmp_path):
    s = setup(cards)
    source = cast(s, NAMES[1])
    question(s)
    place(s, source.id, "name", text="Hot Dog")
    question(s)
    pick(s, ["p2"])
    # Destroying its source cannot erase the announced trigger or its name-sticker LKI.
    cast(s, "Disenchant", targets=[source.id])
    # Stop with Disenchant above the trigger, then finish both in a fresh process.
    cold(
        s,
        tmp_path,
        """settle(s)
assert s.state.cards[m['source']].zone=='p1:graveyard'
assert s.state.players['p2'].life==m['life']-2
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
""",
        {"source": source.id, "life": s.state.players["p2"].life},
    )


def test_balls_later_art_placement_triggers_and_counts_existing_name_letters104(cards):
    s = setup(cards)
    source = cast(s, NAMES[1])
    question(s)
    place(s, source.id, "name", text="Hot Dog")
    question(s)
    pick(s, ["p2"])
    settle(s)
    before = s.state.players["p2"].life
    cast(s, "Ticketomaton")
    question(s)
    place(s, source.id, "art")
    question(s)
    pick(s, ["p2"])
    settle(s)
    assert s.state.players["p2"].life == before - 2
    check(s)


def test_borrowed_balls_does_not_trigger_for_owner_sticker_placement104(cards):
    s = setup(cards)
    source = cast(s, NAMES[1])
    question(s)
    pick(s, [])
    settle(s)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    before = s.state.players["p2"].life
    cast(s, "Ticketomaton")
    question(s)
    place(s, source.id, "art")
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players["p2"].life == before
    check(s)
