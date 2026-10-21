"""Native own discounts count the physical qualifying cards in the printed zones."""

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditional_prevention import cast, choose
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game

HEARTH = "Hearth Elemental // Stoke Genius"
BANE = "Sailors' Bane"
ADVENTURE = "Bramble Familiar // Fetch Quest"
NAMES = [
    HEARTH,
    BANE,
    ADVENTURE,
    "Fire // Ice",
    "Lightning Bolt",
    "Murder",
    "Conduit of Worlds",
    "Inspired Ultimatum",
]


def setup(cards):
    return game(cards, NAMES)


def paid(s, card):
    records = [r for r in s.state.rules.payments.values() if r.card == card.id]
    assert len(records) == 1
    return records[0]


@pytest.mark.parametrize("name", [HEARTH, BANE])
def test_full_actual_cards(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name,generic,color", [(HEARTH, 2, "R"), (BANE, 4, "U")])
def test_actual_three_qualifying_physical_cards_reduce_only_generic(cards, name, generic, color):
    s = setup(cards)
    for n in ["Lightning Bolt", "Murder", ADVENTURE]:
        put(s, n, "graveyard")
    source = put(s, name, "hand")
    mana(s, C=generic, **{color: 1 if name == HEARTH else 2})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and not s.state.players["p1"].mana
    assert paid(s, source).total_cost == f"{{{generic}}}" + f"{{{color}}}" * (1 if name == HEARTH else 2)
    roundtrip(s)


@pytest.mark.parametrize("name,generic", [(HEARTH, 5), (BANE, 5)])
def test_exile_counts_only_for_bane_and_opponents_cards_never_count(cards, name, generic):
    s = setup(cards)
    put(s, "Lightning Bolt", "exile")
    put(s, ADVENTURE, "exile")
    put(s, "Murder", "graveyard", "p2")
    put(s, "Fire // Ice", "exile", "p3")
    source = put(s, name, "hand")
    mana(s, C=generic, R=1 if name == HEARTH else 0, U=2 if name == BANE else 0)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and not s.state.players["p1"].mana
    roundtrip(s)


def test_split_card_is_one_qualifying_card_not_two_spells(cards):
    s = setup(cards)
    put(s, "Fire // Ice", "graveyard")
    source = put(s, HEARTH, "hand")
    mana(s, C=4, R=1)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert not s.state.players["p1"].mana and paid(s, source).total_cost == "{4}{R}"
    roundtrip(s)


def test_cast_as_adventure_does_not_get_permanent_face_discount(cards):
    s = setup(cards)
    for n in ["Lightning Bolt", "Murder", ADVENTURE]:
        put(s, n, "graveyard")
    source = put(s, HEARTH, "hand")
    mana(s, R=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, face=1, sources=[])
    assert s.state.model_dump_json() == before
    mana(s, C=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id, face=1, sources=[])
    assert source.zone == "stack" and paid(s, source).total_cost == "{1}{R}"
    settle(s)
    assert source.zone == "p1:exile"
    roundtrip(s)


def test_hearth_adventure_then_cast_permanent_from_exile_uses_current_graveyard(cards):
    s = setup(cards)
    for n in ["Lightning Bolt", "Murder", ADVENTURE]:
        put(s, n, "graveyard")
    source = put(s, HEARTH, "hand")
    mana(s, C=1, R=1)
    act(s, "p1", type="cast_spell", card_id=source.id, face=1, sources=[])
    settle(s)
    assert source.zone == "p1:exile"
    mana(s, C=2, R=1)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and not s.state.players["p1"].mana
    roundtrip(s)


def test_actual_bane_ward_counters_opponents_spell_when_declined(cards):
    s = setup(cards)
    source = cast(s, BANE)
    murder = cast(s, "Murder", [source.id], pid="p2")
    d = s.state.rules.decision
    assert d and any(o.id == "decline" for o in d.options)
    choose(s, ["decline"])
    assert source.zone == "p1:battlefield" and murder.zone == "p2:graveyard"
    roundtrip(s)


def test_hearth_cast_from_graveyard_does_not_count_itself(cards):
    s = game(cards, [*NAMES, "Muldrotha, the Gravetide"])
    put(s, "Muldrotha, the Gravetide", "battlefield")
    source = put(s, HEARTH, "graveyard")
    mana(s, C=4, R=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    assert s.state.model_dump_json() == before
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and paid(s, source).total_cost == "{5}{R}"
    roundtrip(s)


@pytest.mark.parametrize("name,color", [(BANE, "U"), (HEARTH, "R")])
def test_true_cold_saved_game_computes_exile_and_graveyard_union_before_payment(cards, tmp_path, name, color):
    import subprocess
    import sys

    s = setup(cards)
    put(s, "Lightning Bolt", "graveyard")
    put(s, "Murder", "exile")
    put(s, ADVENTURE, "exile")
    source = put(s, name, "hand")
    saved = tmp_path / "adventure-count48.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mana(s,C=4,**({sys.argv[4]:2 if sys.argv[4]=='U' else 1}))
act(s,'p1',type='cast_spell',card_id=sys.argv[3],sources=[])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:battlefield'
assert not s.state.players['p1'].mana
roundtrip(s)
"""
    p = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, color],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize("name,color", [(BANE, "U"), (HEARTH, "R")])
def test_discount_never_reduces_colored_requirement(cards, name, color):
    s = setup(cards)
    qualifying = ["Lightning Bolt", "Murder", "Healing Salve", "Fire // Ice", ADVENTURE]
    if name == BANE:
        qualifying += [HEARTH, "Inspired Ultimatum"]
    for n in qualifying:
        put(s, n, "graveyard")
    source = put(s, name, "hand")
    mana(s, C=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    assert s.state.model_dump_json() == before
    mana(s, **{color: 2 if name == BANE else 1})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and s.state.players["p1"].mana == {"C": 1}
    roundtrip(s)


def test_face_down_exile_has_no_qualifying_characteristics(cards):
    s = setup(cards)
    hidden = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="move", card_ids=[hidden.id], to={"zone": "exile"}, face_down=True)
    put(s, "Murder", "graveyard")
    source = put(s, BANE, "hand")
    mana(s, C=6, U=2)
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert source.zone == "p1:battlefield" and not s.state.players["p1"].mana
    roundtrip(s)
