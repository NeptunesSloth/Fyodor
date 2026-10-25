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
NAMES = ["_____ _____ Rocketship", "Ticketomaton"]


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


def test_whole_rocketship105(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[0])).level == "FULL"


def attack(s, source):
    bear = put(s, "Grizzly Bears", "battlefield")
    to_phase(s, "main1", 3)
    ability = next(a for a in chars(s, s.state.cards[source.id]).abilities if "Crew" in a.text)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability.index, crew=[bear.id])
    settle(s)
    to_phase(s, "declare_attackers", 3)
    before = chars(s, s.state.cards[source.id]).pt
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": source.id, "target": "p2"}])
    d = question(s)
    assert len(d.options) == 26 and d.options[0].id == "A" and d.options[-1].id == "Z"
    return before


@pytest.mark.parametrize(
    "names,letter,n",
    [(("Hot Dog", "Trendy"), "H", 1), (("Hot Dog", "Trendy"), "D", 0), (("Trendy", "Tightrope"), "T", 2)],
)
def test_real_crew_attack_choose_letter_counts_sticker_initials105(cards, names, letter, n):
    s = setup(cards)
    source = cast(s, NAMES[0])
    for name in names:
        question(s)
        place(s, source.id, "name", text=name)
    settle(s)
    before = attack(s, source)
    pick(s, [letter])
    settle(s)
    assert chars(s, s.state.cards[source.id]).pt == (before[0] + n, before[1] + n)
    check(s)


def test_genuine_cold_rocketship_letter_choice_keeps_name_markers105(cards, tmp_path):
    s = setup(cards)
    source = cast(s, NAMES[0])
    for name in ("Trendy", "Tightrope"):
        question(s)
        place(s, source.id, "name", text=name)
    settle(s)
    before = attack(s, source)
    cold(
        s,
        tmp_path,
        """answer(['T']);settle(s)
assert Plan.view(s.state,'p1',repo).ch(s.state.cards[m['source']]).pt==tuple(n+2 for n in m['pt'])
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
""",
        {"source": source.id, "pt": before},
    )
