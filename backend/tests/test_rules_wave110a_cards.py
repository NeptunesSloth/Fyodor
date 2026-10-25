"""Wave 110A: promotions on real Oracle text (replay + save/load via tests/wave9c_kit.check).

* 601.2c, 608.2b: "Choose any number of target creatures with equal toughness. Destroy the chosen creatures." (V.A.T.S.).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import answer, card_db, cast  # noqa: F401  (fixture DB with EXTRA)
from tests.wave9c_kit import build, check, mana, put, zone_of

EXTRA = [
    real("V.A.T.S.", "{2}{B}{B}", 4, "Sorcery", "Choose any number of target creatures with equal toughness. Destroy the chosen creatures.", None, "B"),
    real("Test Two 110A", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Test Twin 110A", "{1}{G}", 2, "Creature — Cat", "", ("1", "2"), "G"),
    real("Test Three 110A", "{2}{G}", 3, "Creature — Ox", "", ("3", "3"), "G"),
]
GAMBIT = ("Remove all attacking creatures from combat and untap them. After this phase, there is an additional combat phase. Each of those creatures "
          "attacks that combat if able. They can't attack you or planeswalkers you control that combat.")
EXTRA.append(real("Illusionist's Gambit", "{1}{U}{U}", 3, "Instant",
                  "Cast this spell only during the declare blockers step on an opponent's turn.\n" + GAMBIT, None, "U"))
_BASE.extend(EXTRA)
NAMES = ["V.A.T.S."]
NAMES.append("Illusionist's Gambit")


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_vats_destroys_equal_toughness_only(cards):
    s = build(cards, ["V.A.T.S.", "Test Two 110A", "Test Twin 110A"], ["Test Three 110A"])
    a, b = put(s, "Test Two 110A"), put(s, "Test Twin 110A")
    put(s, "Test Three 110A", "p2")
    mana(s, B=2, C=2)
    cast(s, "V.A.T.S.", [a.id, b.id], target_counts=[2])
    answer(s)
    assert zone_of(s, "Test Two 110A") == "p1:graveyard" and zone_of(s, "Test Twin 110A") == "p1:graveyard"
    assert zone_of(s, "Test Three 110A", "p2") == "p2:battlefield"
    check(s)


def test_vats_refuses_unequal_toughness(cards):
    s = build(cards, ["V.A.T.S.", "Test Two 110A"], ["Test Three 110A"])
    a, c = put(s, "Test Two 110A"), put(s, "Test Three 110A", "p2")
    mana(s, B=2, C=2)
    with pytest.raises(ActionError, match="equal toughness"):
        cast(s, "V.A.T.S.", [a.id, c.id], target_counts=[2])


def test_gambit_attackers_untap_and_must_attack_someone_else(cards):
    """506.4, 701.26b, 500.8: removed, untapped, then forced into the extra combat, but never at the caster (3 players)."""
    from tests.wave53c_kit import creature, in_play, pool, sandbox, settle, until

    s = sandbox(cards, "Illusionist's Gambit", players=3)
    wolf = creature(s, "p2", "Wolf", "2/2")
    from tests.wave53c_kit import combat_step

    combat_step(s)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "declare_attackers", limit=200)
    from tests.game_helpers import act
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": wolf.id, "target": "p1"}])
    until(s, lambda s: s.state.turn.phase == "declare_blockers", limit=20)
    assert s.state.cards[wolf.id].is_attacking and s.state.cards[wolf.id].tapped
    g = in_play(s, "Illusionist's Gambit")
    act(s, "p1", type="move", card_ids=[g.id], to={"zone": "hand"})
    pool(s, "p1", U=2, C=1)
    while s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="cast_spell", card_id=g.id, targets=[])
    settle(s)
    assert not s.state.cards[wolf.id].is_attacking and not s.state.cards[wolf.id].tapped
    until(s, lambda s: s.state.turn.phase == "declare_attackers" and s.state.rules.decision is not None, limit=40)
    d = s.state.rules.decision
    assert d.kind == "declare_attackers" and d.player == "p2"
    with pytest.raises(ActionError):  # can't attack the caster
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": wolf.id, "target": "p1"}])
    with pytest.raises(ActionError):  # must attack if able
        act(s, "p2", type="declare_attackers", attackers=[])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": wolf.id, "target": "p3"}])
    assert s.state.cards[wolf.id].is_attacking
    check(s)
