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
    "Goblin Airbrusher",
    "Wee Champion",
    "Tusk and Whiskers",
    "Unlawful Entry",
    "A Good Day to Pie",
    "Ticketomaton",
    "Prize Wall",
    "Sol Ring",
    "Lightning Bolt",
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


@pytest.mark.parametrize("name", NAMES[:5])
def test_whole_placement_trigger_cards103(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("art", [True, False])
def test_real_placement_dispatches_airbrusher_and_wee103(cards, art):
    s = setup(cards)
    put(s, "Goblin Airbrusher", "battlefield")
    wee = put(s, "Wee Champion", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    p = chars(s, wee).pt[0]
    cast(s, "Ticketomaton")
    question(s)
    place(s, bear.id, "art" if art else "name", text=None if art else "Minotaur")
    settle(s)
    assert len(
        [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone.endswith(":battlefield")]
    ) == (2 if art else 1)
    assert chars(s, s.state.cards[wee.id]).pt[0] == p + 1
    assert s.state.cards[wee.id].counters.get("+1/+1", 0) == int(art)
    check(s)


@pytest.mark.parametrize(
    "name,kind,text", [("Unlawful Entry", "art", None), ("A Good Day to Pie", "name", "Minotaur")]
)
def test_real_creature_placement_returns_graveyard_card103(cards, name, kind, text):
    s = setup(cards)
    gy = put(s, name, "graveyard")
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Ticketomaton")
    question(s)
    place(s, bear.id, kind, text=text)
    d = question(s)
    assert d.kind == "confirm"
    pick(s, ["yes"])
    settle(s)
    assert s.state.cards[gy.id].zone == "p1:hand"
    check(s)


def test_tusk_actual_tap_ticket_activation_and_ability_sticker103(cards):
    s = setup(cards)
    tusk = put(s, "Tusk and Whiskers", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    # Ticketomaton grants two tickets while its optional sticker is declined.
    cast(s, "Ticketomaton")
    question(s)
    pick(s, [])
    settle(s)
    to_phase(s, "main1", 3)
    act(s, "p1", type="add_mana", player="p1", mana={"G": 20, "W": 20, "C": 20})
    ability = next(a for a in chars(s, tusk).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=tusk.id, ability=ability.index, sources=[])
    question(s)
    place(s, bear.id, "ability", text="Haste")
    settle(s)
    assert s.state.cards[bear.id].counters.get("+1/+1") == 1
    assert s.state.cards[tusk.id].tapped
    assert s.state.players["p1"].resources["ticket"] == 0
    check(s)


@pytest.mark.parametrize(
    "target,kind,text", [("Sol Ring", "art", None), ("Grizzly Bears", "name", "Minotaur")]
)
def test_art_creature_graveyard_trigger_rejects_wrong_kind_and_noncreature103(cards, target, kind, text):
    s = setup(cards)
    gy = put(s, "Unlawful Entry", "graveyard")
    card = put(s, target, "battlefield")
    cast(s, "Ticketomaton")
    question(s)
    place(s, card.id, kind, text=text)
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[gy.id].zone == "p1:graveyard"
    check(s)


def test_declining_placement_does_not_trigger_or_return103(cards):
    s = setup(cards)
    put(s, "Goblin Airbrusher", "battlefield")
    put(s, "Wee Champion", "battlefield")
    gy = put(s, "Unlawful Entry", "graveyard")
    cast(s, "Ticketomaton")
    question(s)
    pick(s, [])
    settle(s)
    assert not any(c.name == "Treasure" for c in s.state.cards.values())
    assert s.state.cards[gy.id].zone == "p1:graveyard"
    check(s)


def test_genuine_cold_placement_receipt_then_graveyard_optional_return103(cards, tmp_path):
    s = setup(cards)
    gy = put(s, "Unlawful Entry", "graveyard")
    bear = put(s, "Grizzly Bears", "battlefield")
    cast(s, "Ticketomaton")
    question(s)
    place(s, bear.id)
    question(s)
    cold(
        s,
        tmp_path,
        """answer(['yes']);settle(s)
assert s.state.cards[m['gy']].zone=='p1:hand'
assert s.history.rebuild().model_dump(mode='json')==s.state.model_dump(mode='json')
""",
        {"gy": gy.id},
    )


@pytest.mark.parametrize("watcher", ["Goblin Airbrusher", "Wee Champion"])
def test_opponents_watcher_does_not_trigger_for_your_placement103(cards, watcher):
    s = setup(cards)
    source = put(s, watcher, "battlefield")
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    bear = put(s, "Grizzly Bears", "battlefield")
    original = chars(s, s.state.cards[source.id]).pt[0]
    cast(s, "Ticketomaton")
    question(s)
    place(s, bear.id)
    settle(s)
    assert not any(c.name == "Treasure" for c in s.state.cards.values())
    assert not s.state.cards[source.id].counters
    assert chars(s, s.state.cards[source.id]).pt[0] == original
    check(s)
