from __future__ import annotations

import pytest

from app.decks.parser import DeckTextTooLarge, format_deck_text, parse_deck_text, parse_line


@pytest.mark.parametrize(
    ("line", "qty", "name", "set_code", "number"),
    [
        ("1 Sol Ring", 1, "Sol Ring", None, None),
        ("1x Sol Ring", 1, "Sol Ring", None, None),
        ("Sol Ring", 1, "Sol Ring", None, None),
        ("1 Sol Ring (CMM)", 1, "Sol Ring", "cmm", None),
        ("1 Sol Ring [CMM]", 1, "Sol Ring", "cmm", None),
        ("1 Sol Ring (CMM) 410", 1, "Sol Ring", "cmm", "410"),
        ("10 Island", 10, "Island", None, None),
        ("4 x Lightning Bolt", 4, "Lightning Bolt", None, None),
        ("Lightning Bolt x4", 4, "Lightning Bolt", None, None),
        ("1 Fire // Ice (MH2) 290", 1, "Fire // Ice", "mh2", "290"),
        ("1 Lightning Bolt (PLST) CLB-187", 1, "Lightning Bolt", "plst", "CLB-187"),
        ("1 Sol Ring (CMM) 410 *F*", 1, "Sol Ring", "cmm", "410"),
        ("1x Sol Ring (cmm) 410 [Ramp]", 1, "Sol Ring", "cmm", "410"),
        ("1x Sol Ring (cmm) 410 [Ramp,Artifact] ^Have,#37d67a^", 1, "Sol Ring", "cmm", "410"),
        ("1 Atraxa, Praetors' Voice", 1, "Atraxa, Praetors' Voice", None, None),
        ("  2   Llanowar Elves  ", 2, "Llanowar Elves", None, None),
    ],
)
def test_parse_line_variants(line, qty, name, set_code, number):
    entry = parse_line(line)
    assert entry is not None
    assert (entry.quantity, entry.name, entry.set_code, entry.collector_number) == (qty, name, set_code, number)


def test_parse_line_flags():
    assert parse_line("1 Sol Ring (CMM) 410 *F*").foil is True
    assert parse_line("1x Atraxa, Praetors' Voice (2x2) 190 [Commander{top}]").section == "commander"
    assert parse_line("1 Atraxa, Praetors' Voice *CMDR*").section == "commander"
    assert parse_line("1 Krenko, Mob Boss # !Commander").section == "commander"
    assert parse_line("SB: 2 Pyroblast").section == "sideboard"
    assert parse_line("1x Opt [Maybeboard]").section == "maybeboard"
    assert parse_line("") is None
    assert parse_line("12345") is None


def test_sections_moxfield_style():
    deck = parse_deck_text(
        """Commander
1 Krenko, Mob Boss

Deck
1 Sol Ring
1 Arcane Signet
1 Command Tower
10 Mountain

Sideboard
1 Lightning Bolt

Maybeboard
1 Counterspell
"""
    )
    assert deck.errors == []
    assert deck.count("commander") == 1
    assert deck.count("main") == 13
    assert deck.count("sideboard") == 1
    assert deck.count("maybeboard") == 1


def test_arena_format_with_about_block():
    deck = parse_deck_text(
        """About
Name Goblin Party

Commander
1 Krenko, Mob Boss (DDN) 13

Deck
1 Sol Ring (CMM) 410
"""
    )
    assert deck.name == "Goblin Party"
    assert deck.entries[0].section == "commander"
    assert deck.entries[0].set_code == "ddn"


def test_headers_with_colons_counts_and_comments():
    deck = parse_deck_text(
        """// My deck
# a comment
COMMANDER:
1 Atraxa, Praetors' Voice
Creatures (2)
1 Llanowar Elves
1 Krenko, Mob Boss
SIDEBOARD:
1 Counterspell
"""
    )
    assert [e.section for e in deck.entries] == ["commander", "main", "main", "sideboard"]


def test_mtggoldfish_blank_line_sideboard():
    main = "\n".join(["4 Lightning Bolt"] * 15)
    deck = parse_deck_text(main + "\n\n3 Pyroblast\n2 Smash to Smithereens\n")
    assert deck.count("main") == 60
    assert deck.count("sideboard") == 5
    assert deck.notes


def test_commander_detected_from_trailing_block():
    main = "\n".join(["1 Sol Ring"] * 99)
    deck = parse_deck_text(main + "\n\n1 Krenko, Mob Boss\n")
    assert deck.count("commander") == 1
    assert deck.entries[-1].name == "Krenko, Mob Boss"


def test_commander_detected_from_leading_block():
    deck = parse_deck_text("1 Krenko, Mob Boss\n\n" + "\n".join(["1 Sol Ring"] * 99))
    assert deck.entries[0].section == "commander"


def test_blank_lines_without_heuristic_match_stay_main():
    deck = parse_deck_text("1 Sol Ring\n\n1 Arcane Signet\n\n1 Command Tower\n")
    assert {e.section for e in deck.entries} == {"main"}


def test_unreadable_lines_are_reported():
    deck = parse_deck_text("1 Sol Ring\n???\n")
    assert len(deck.entries) == 1
    assert deck.errors and "Line 2" in deck.errors[0]


def test_size_limits():
    with pytest.raises(DeckTextTooLarge):
        parse_deck_text("x" * 300_000)
    with pytest.raises(DeckTextTooLarge):
        parse_deck_text("\n" * 5000)


def test_quantity_clamped():
    assert parse_line("5000 Island").quantity == 999


def test_export_round_trip():
    entries = [
        {"section": "commander", "quantity": 1, "name": "Krenko, Mob Boss", "set_code": "ddn", "collector_number": "13"},
        {"section": "main", "quantity": 10, "name": "Mountain", "set_code": None, "collector_number": None},
        {"section": "sideboard", "quantity": 1, "name": "Fire // Ice", "set_code": "mh2", "collector_number": "290"},
    ]
    text = format_deck_text(entries)
    parsed = parse_deck_text(text)
    assert [(e.section, e.quantity, e.name, e.set_code, e.collector_number) for e in parsed.entries] == [
        ("commander", 1, "Krenko, Mob Boss", "ddn", "13"),
        ("main", 10, "Mountain", None, None),
        ("sideboard", 1, "Fire // Ice", "mh2", "290"),
    ]
