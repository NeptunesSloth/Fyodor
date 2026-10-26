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
EXTRA.append(real("Wheel of Potential", "{2}{R}", 3, "Sorcery",
                  "You get {E}{E}{E} (three energy counters), then you may pay any amount of {E}.\nEach player may exile their hand and draw a number of cards equal "
                  "to the amount of {E} paid this way. If seven or more {E} was paid this way, you may play cards you own exiled this way until the end of "
                  "your next turn.", None, "R"))
EXTRA.append(real("Officious Interrogation", "{W}{U}", 2, "Sorcery",
                  "This spell costs {W}{U} more to cast for each target beyond the first.\nChoose any number of target players. Investigate X times, where X is the "
                  "total number of creatures those players control.", None, "WU"))
EXTRA.append(real("Hulking Metamorph", "{9}", 9, "Artifact Creature — Shapeshifter",
                  "Prototype {2}{U}{U} — 3/3 (You may cast this spell with different mana cost, color, and size. It keeps its abilities and types.)\nYou may have this "
                  "creature enter as a copy of an artifact or creature you control, except it's an artifact creature in addition to its other types, and its "
                  "power and toughness are equal to this creature's power and toughness.", ("9", "9"), ""))
_BASE.extend(EXTRA)
NAMES = ["V.A.T.S.", "Wheel of Potential", "Officious Interrogation", "Hulking Metamorph"]
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


@pytest.mark.parametrize("paid,p2_yes", [(3, False), (3, True), (7, True)])
def test_wheel_of_potential(cards, paid, p2_yes):
    """107.14 pay any amount of {E}; each player may exile their hand and draw that many; seven or more: play your exiled cards (next turn too)."""
    from tests.game_helpers import act
    from tests.wave9c_kit import to_hand

    s = build(cards, ["Wheel of Potential", "Test Two 110A", "Test Three 110A"], ["Test Two 110A", "Test Three 110A"])
    if paid > 3:
        act(s, "p1", type="set_resource", player="p1", key="energy", value=paid - 3)
    to_hand(s, "Test Two 110A", "p2")
    to_hand(s, "Test Two 110A")
    to_hand(s, "Test Three 110A")
    theirs = len(s.state.zones["p2:hand"])
    mana(s, R=1, C=2)
    cast(s, "Wheel of Potential")
    answer(s, str(paid), "yes", "yes" if p2_yes else "no")
    assert s.state.players["p1"].resources.get("energy", 0) == 3 + (paid - 3) - paid
    assert len(s.state.zones["p1:hand"]) == paid  # the whole hand went, `paid` cards came
    assert len(s.state.zones["p2:hand"]) == (paid if p2_yes else theirs)
    assert len(s.state.zones.get("p1:exile", [])) == 2 and len(s.state.zones.get("p2:exile", [])) == (theirs if p2_yes else 0)
    granted = {p.card for p in s.state.rules.permissions if p.player == "p1"}
    exiled = set(s.state.zones.get("p1:exile", []))
    assert (granted == exiled) if paid >= 7 else not granted  # 7 or more: both exiled cards may be played (until the end of your next turn)
    check(s)


@pytest.mark.parametrize("targets,clues", [([], 0), (["p2"], 2), (["p1", "p2"], 3)])
def test_officious_interrogation(cards, targets, clues):
    """601.2c any number of targets, 601.2f {W}{U} per target beyond the first, 608.2b X = total creatures the chosen players control."""
    s = build(cards, ["Officious Interrogation", "Test Two 110A"], ["Test Two 110A", "Test Three 110A"])
    put(s, "Test Two 110A")
    put(s, "Test Two 110A", "p2")
    put(s, "Test Three 110A", "p2")
    mana(s, W=3, U=3)
    cast(s, "Officious Interrogation", targets, target_counts=[len(targets)])
    answer(s)
    assert sum(c.name == "Clue" for c in s.state.cards.values() if c.zone == "p1:battlefield") == clues
    check(s)


def test_officious_interrogation_second_target_costs_more(cards):
    s = build(cards, ["Officious Interrogation"])
    mana(s, W=1, U=1)
    with pytest.raises(ActionError):
        cast(s, "Officious Interrogation", ["p1", "p2"], target_counts=[2])


@pytest.mark.parametrize("prototype,pt", [(True, (3, 3)), (False, (9, 9))])
def test_hulking_metamorph_copy_keeps_own_power_and_toughness(cards, prototype, pt):
    """707.9b: copy of a creature, an artifact creature too, with this creature's own P/T (prototyped 3/3 per 718.3b, else 9/9)."""
    from tests.test_rules_attachments import ch

    s = build(cards, ["Hulking Metamorph", "Test Three 110A"])
    bear = put(s, "Test Three 110A")
    mana(s, U=2, C=9 if not prototype else 2)
    meta = cast(s, "Hulking Metamorph", prototype=prototype)
    answer(s, [bear.id])
    got = ch(s, s.state.cards[meta.id])
    assert got.name == "Test Three 110A" and got.pt == pt and {"Artifact", "Creature"} <= set(got.types)
    check(s)


def test_vats_destroys_a_single_target(cards):  # ruling 2024-03-08: one target is destroyed whatever its toughness (the equal-toughness check is on the group at resolution too, targets.relation_ok; split second leaves no window to test a change)
    s = build(cards, ["V.A.T.S.", "Test Three 110A"])
    a = put(s, "Test Three 110A")
    mana(s, B=2, C=2)
    cast(s, "V.A.T.S.", [a.id], target_counts=[1])
    answer(s)
    assert zone_of(s, "Test Three 110A") == "p1:graveyard"
    check(s)
