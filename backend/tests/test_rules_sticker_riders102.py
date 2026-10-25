"""Newly placed name receipts: six unique vowels, not the whole name or old stickers."""

from __future__ import annotations

import pytest

from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.sticker_sheets101 import SHEETS
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_sticker_effects101 import FixedSheetRng, cast, cold, pick, question, sticker
from tests.test_rules_sticker_effects101 import cards as _cards
from tests.wave9c_kit import check
from tests.wave100c_kit import settle, to_phase

cards = _cards
NAMES = ["_____ Goblin", "_____-o-saurus", "Wizards of the _____", "_____ Bird Gets the Worm"]


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


def red(s):
    p = s.state.players["p1"]
    return p.mana.get("R", 0) + sum(u.sym == "R" for u in p.mana_units)


def name_self(s, source, text):
    d = question(s)
    assert [o.id for o in d.options] == [source.id]
    selected = sticker(s, "name", text=text)
    pick(s, [source.id])
    pick(s, [selected["id"]])
    pick(s, ["0"])
    return selected


@pytest.mark.parametrize("name", NAMES)
def test_whole_name_receipt_cards102(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(
    "name,text,n",
    [
        ("_____ Goblin", "Trendy", 2),
        ("_____-o-saurus", "Hot Dog", 1),
        ("_____ Bird Gets the Worm", "Minotaur", 4),
    ],
)
def test_actual_new_name_receipt_reward_counts_unique_vowels_y_and_two_word_sticker102(cards, name, text, n):
    s = setup(cards)
    source = cast(s, name)
    question(s)
    before_red = red(s)
    before_life = s.state.players["p1"].life
    name_self(s, source, text)
    settle(s)
    assert len(s.state.cards[source.id].stickers101) == 1
    if name == "_____ Goblin":
        assert red(s) == before_red + n
    elif name == "_____-o-saurus":
        assert source.counters["+1/+1"] == n
    else:
        assert s.state.players["p1"].life == before_life + n
    check(s)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("sheets", [False, True])
def test_no_new_sticker_no_reward_even_when_optional_placement_declined102(cards, name, sheets):
    s = setup(cards, sheets=sheets)
    source = cast(s, name)
    before_red = red(s)
    before_life = s.state.players["p1"].life
    hand = len(s.state.zones["p1:hand"])
    if sheets:
        question(s)
        pick(s, [])
    settle(s)
    assert not source.stickers101 and not source.counters
    assert (
        s.state.players["p1"].life == before_life
        and red(s) == before_red
        and len(s.state.zones["p1:hand"]) == hand
    )
    check(s)


def test_wizards_looks_receipt_count_puts_one_in_hand_orders_rest_then_declining_on_blink_ignores_old_name102(
    cards,
):
    s = setup(cards)
    source = cast(s, "Wizards of the _____")
    name_self(s, source, "Minotaur")
    d = s.state.rules.decision
    assert d and len(d.options) == 4
    selected = d.options[-1].id
    pick(s, [selected])
    settle(s)
    assert s.state.cards[selected].zone == "p1:hand"
    cast(s, "Cloudshift", targets=[source.id])
    question(s)
    hand = len(s.state.zones["p1:hand"])
    pick(s, [])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand and len(s.state.cards[source.id].stickers101) == 1
    check(s)


def test_vowel_counters_use_native_replacement_after_count102(cards):
    s = setup(cards)
    put(s, "Vorinclex, Monstrous Raider", "battlefield")
    source = cast(s, "_____-o-saurus")
    name_self(s, source, "Hot Dog")
    settle(s)
    assert source.counters["+1/+1"] == 2
    check(s)


def test_genuine_cold_goblin_saved_name_position_keeps_new_sticker_receipt_and_mana102(cards, tmp_path):
    s = setup(cards)
    source = cast(s, "_____ Goblin")
    question(s)
    selected = sticker(s, "name", text="Trendy")
    pick(s, [source.id])
    pick(s, [selected["id"]])
    before = red(s)
    cold(
        s,
        tmp_path,
        """answer(['0']);settle(s)
p=s.state.players['p1']
assert p.mana.get('R',0)+sum(u.sym=='R' for u in p.mana_units)==m['before']+2
assert s.state.cards[m['source']].stickers101[-1].sticker.text=='Trendy'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
""",
        {"source": source.id, "before": before},
    )
