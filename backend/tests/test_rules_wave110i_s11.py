"""Wave 110I session 11: Arcum's Whistle (118.12a optional payment, 508.1d forced attack, 603.4/603.7 end-step destroy; Nettling Imp's machinery)."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import EXTRA as BASE
from tests.test_rules_wave110e_cards import (
    _bobs_beginning_of_combat,
    _imp_table,
    _to_phase_stop,
)
from tests.wave9c_kit import check, mana

WHISTLE = ("{3}, {T}: Choose target non-Wall creature the active player has controlled continuously since the beginning of the turn. That player may pay {X}, where X is "
           "that creature's mana value. If they don't pay, the creature attacks this turn if able, and at the beginning of the next end step, destroy it if it didn't attack "
           "this turn. Activate only before attackers are declared.")
EXTRA = [*BASE, real("Arcum's Whistle", "{3}", 3, "Artifact", WHISTLE)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Arcum's Whistle")).level == "FULL"


@pytest.mark.parametrize("pays", [True, False])
@pytest.mark.parametrize("attacks", [True, False])
def test_arcum_whistle(cards, pays, attacks):
    """Bob (the active player) may pay {2} (the Bears' mana value); paid, nothing happens. Unpaid, the Bears must attack and are destroyed at the end step unless they did."""
    from tests.test_rules_conditionals import settle

    s, whistle, bears, wall = _imp_table(cards, "Arcum's Whistle")
    _bobs_beginning_of_combat(s)
    mana(s, C=3)
    mana(s, "p2", C=2)  # (his pool survives until the step ends)
    act(s, "p1", type="activate_ability", card_id=whistle.id, ability=0, targets=[bears.id])
    d = None
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if (o.label.lower().startswith("pay") == pays))])
    settle(s)
    if pays:
        assert s.state.players["p2"].mana_units == []
    if not pays and not attacks:
        act(s, "p2", type="tap", card_ids=[bears.id])  # (a tapped creature can't attack: the requirement is unmet only "if able")
    else:
        _to_phase_stop(s, "declare_attackers", 4)
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}] if attacks else [])
    _to_phase_stop(s, "end", 4)
    settle(s)
    assert (s.state.cards[bears.id].zone == "p2:battlefield") == (pays or attacks)
    check(s)
