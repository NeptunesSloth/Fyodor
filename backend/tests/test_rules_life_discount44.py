"""Canonical Game Over costs, destruction, and saved payment."""


import pytest

from tests.game_helpers import act
from tests.test_rules_conditional_prevention import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_life_sequences44 import cards as cards


def custom_start(cards, starting):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from app.game.state import GameSettings
    from tests.game_helpers import deck, enable

    names = ["Game Over", "Grizzly Bears", "Llanowar Elves", "Sphere of Resistance"]
    setups = [
        PlayerSetup(n, cards=deck(cards, "Krenko, Mob Boss", [(1, k) for k in names] + [(20, "Forest")]))
        for n in ["A", "B", "C"]
    ]
    s = GameSession(
        enable(new_game(setups, settings=GameSettings(starting_life=starting), shuffle=False)), cards=cards
    )
    for p in s.state.players:
        act(s, p, type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")
    start(s)
    return s


@pytest.mark.parametrize(
    "payer,life,starting,tax",
    [
        ("p1", 20, 40, False),
        ("p2", 20, 40, False),
        ("p3", 21, 40, False),
        ("p1", 21, 41, False),
        ("p2", 20, 41, False),
        ("p3", 20, 40, True),
    ],
)
def test_actual_native_cost_boundary_and_destroy(cards, payer, life, starting, tax):
    from app.rules.plan import Plan

    s = custom_start(cards, starting)
    a = put(s, "Grizzly Bears", "battlefield", "p1")
    b = put(s, "Llanowar Elves", "battlefield", "p2")
    if tax:
        put(s, "Sphere of Resistance", "battlefield")
    act(s, "p1", type="set_life", player=payer, value=life)
    discounted = 2 * life <= starting
    generic = (1 if discounted else 3) + int(tax)
    source = put(s, "Game Over", "hand")
    mana(s, C=generic, B=2)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[], sources=[])
    assert source.zone == "stack" and Plan(s.state, "p1", cards, None).ch(source).mana_value == 5
    record = s.state.rules.payments[Plan(s.state, "p1", cards, None).oid(source)]
    assert sum(record.mana_spent.values()) == generic + 2
    settle(s)
    assert a.zone == "p1:graveyard" and b.zone == "p2:graveyard" and source.zone == "p1:graveyard"
    roundtrip(s)


def test_no_discount_insufficient_mana_refuses_without_partial_payment(cards):
    from app.game.errors import ActionError

    s = custom_start(cards, 40)
    source = put(s, "Game Over", "hand")
    mana(s, C=1, B=2)
    wait_priority(s, "p1")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, targets=[], sources=[])
    assert s.state.model_dump_json() == before


def test_actual_canonical_full(cards):
    from app.rules import coverage

    result = coverage.of_card_data(cards.resolve("Game Over"))
    assert result.level == "FULL", result.manual_parts


def test_actual_paid_spell_stack_cold_no_adapter(cards, tmp_path):
    import subprocess
    import sys

    s = custom_start(cards, 41)
    victim = put(s, "Grizzly Bears", "battlefield", "p2")
    act(s, "p1", type="set_life", player="p2", value=20)
    source = put(s, "Game Over", "hand")
    mana(s, C=1, B=2)
    wait_priority(s, "p1")
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[], sources=[])
    saved = tmp_path / "pending.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source,victim=sys.argv[3:]
record=next(r for r in s.state.rules.payments.values() if r.card==source)
assert sum(record.mana_spent.values())==3
settle(s)
assert s.state.cards[source].zone=='p1:graveyard' and s.state.cards[victim].zone=='p2:graveyard'
assert not s.state.rules.decision
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, victim.id],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
