"""Wave 110F session 9: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 601.2b: "As an additional cost to cast this spell, choose a number between 0 and 5." (Liquid Fire): the number picks the damage split, announced with the targets.
* 700.2e: "An opponent chooses one" (Fatal Lore, Misfortune): the opponent picks the mode (with several, the caster picks which opponent); "that player" is that opponent.
* 609.7c, 702.16e: "Black and/or red permanents and spells are colorless sources of damage." (Ghostly Flame): protection from red no longer stops red damage.
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, life, mana, put

EXTRA = [
    real('Liquid Fire', '{2}{R}{R}', 4, 'Instant',
         "As an additional cost to cast this spell, choose a number between 0 and 5.\nLiquid Fire deals X damage to target creature and 5 minus X damage to that creature's controller, where X is the chosen number.", None, 'R'),
    real('Ghostly Flame', '{B/R}', 1, 'Enchantment', 'Black and/or red permanents and spells are colorless sources of damage.', None, 'B'),
    real('Test Pro-Red 110F', '{1}{W}', 2, 'Creature — Knight', 'Protection from red', ('2', '2'), 'W'),
    real('Test Sweep 110F', '{1}{R}', 2, 'Sorcery', 'Test Sweep 110F deals 2 damage to each creature.', None, 'R'),
    real('Fatal Lore', '{4}{B}{B}', 6, 'Sorcery',
         "An opponent chooses one \u2014\n\u2022 You draw three cards.\n\u2022 You destroy up to two target creatures that player controls. They can't be regenerated. That player draws up to three cards.", None, 'B'),
    real('Misfortune', '{2}{R}{R}', 4, 'Sorcery',
         "An opponent chooses one \u2014\n\u2022 You put a +1/+1 counter on each creature you control and gain 4 life.\n\u2022 You put a -1/-1 counter on each creature that player controls and Misfortune deals 4 damage to that player.", None, 'R'),
    real('Test Sweep Blue 110F', '{1}{U}', 2, 'Sorcery', 'Test Sweep Blue 110F deals 2 damage to each creature.', None, 'U'),
]
_BASE.extend(EXTRA)


@pytest.mark.parametrize("name", ["Liquid Fire", "Ghostly Flame", "Fatal Lore", "Misfortune"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("n", [0, 1, 2, 5])
def test_liquid_fire_splits_five_damage(cards, n):
    """601.2b: the chosen number X is damage to the creature, 5 - X to its controller (each of the six numbers is its own mode)."""
    s = build(cards, ["Liquid Fire"], ["Grizzly Bears"], forests=20, islands=20)
    bear = put(s, "Grizzly Bears", pid="p2")
    mana(s, "p1", R=4)
    cast(s, "Liquid Fire", [bear.id], modes=[n])
    answer(s)
    assert (s.state.cards[bear.id].zone, life(s, "p2")) == (("p2:graveyard" if n >= 2 else "p2:battlefield"), 40 - (5 - n))
    check(s)


@pytest.mark.parametrize("flame,spell,dies", [(False, "Test Sweep 110F", False), (True, "Test Sweep 110F", True), (True, "Test Sweep Blue 110F", False)])
def test_ghostly_flame_makes_red_damage_colorless(cards, flame, spell, dies):
    """Protection from red stops red damage (702.16e) until Ghostly Flame makes the source colorless; blue damage was never stopped."""
    s = build(cards, ["Test Sweep 110F", "Test Sweep Blue 110F", "Ghostly Flame"], ["Test Pro-Red 110F"], forests=20, islands=20)
    knight = put(s, "Test Pro-Red 110F", pid="p2")
    if flame:
        put(s, "Ghostly Flame")
    mana(s, "p1", R=2, U=2)
    cast(s, spell)
    answer(s)
    assert (s.state.cards[knight.id].zone == "p2:graveyard") == (dies or spell == "Test Sweep Blue 110F")
    check(s)


def table(cards, mine, bob=(), carol=()):
    """Alice (p1), Bob (p2) and, with ``carol``, Carol (p3); creatures are moved onto the battlefield by the tests."""
    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (20, "Forest")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")]))]
    if carol is not None:
        setups.append(PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in carol), (20, "Forest")])))
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def bears(s, pid):
    out = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == pid]
    for c in out:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return out


def test_fatal_lore_draw_mode_is_chosen_by_the_opponent(cards):
    """700.2e: Bob (the only opponent) picks the mode; Alice, not Bob, draws the three cards."""
    s = table(cards, ["Fatal Lore"], carol=None)
    before = len(s.state.zones["p1:hand"])
    mana(s, "p1", B=2, C=4)
    cast(s, "Fatal Lore")
    d = s.state.rules.decision
    assert d.player == "p2" and len(d.options) == 2
    answer(s, "0:0")
    assert len(s.state.zones["p1:hand"]) == before + 3
    check(s)


@pytest.mark.parametrize("bob_draws", [0, 2])
def test_fatal_lore_destroy_mode_hits_the_choosing_opponent_and_lets_them_draw(cards, bob_draws):
    """700.2e: Bob chooses the destroy mode; Alice's two targets are creatures Bob controls ("that player"), they can't regenerate; Bob draws up to three (his choice)."""
    s = table(cards, ["Fatal Lore"], ["Grizzly Bears", "Grizzly Bears"], carol=None)
    b1, b2 = bears(s, "p2")
    before = len(s.state.zones["p2:hand"])
    mana(s, "p1", B=2, C=4)
    cast(s, "Fatal Lore")
    answer(s, "1:0", [b1.id, b2.id], str(bob_draws))
    assert {s.state.cards[b.id].zone for b in (b1, b2)} == {"p2:graveyard"}
    assert len(s.state.zones["p2:hand"]) == before + bob_draws
    check(s)


def test_fatal_lore_with_two_opponents_the_caster_picks_who_chooses(cards):
    """700.2e: with Bob and Carol the caster decides which of them chooses; only that opponent's creatures can be targeted ("that player")."""
    s = table(cards, ["Fatal Lore"], ["Grizzly Bears"], ["Grizzly Bears"])
    (bob_bear,), (carol_bear,) = bears(s, "p2"), bears(s, "p3")
    mana(s, "p1", B=2, C=4)
    cast(s, "Fatal Lore")
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    assert s.state.rules.decision.player == "p3"
    answer(s, "1:0", [carol_bear.id], "0")
    assert s.state.cards[carol_bear.id].zone == "p3:graveyard" and s.state.cards[bob_bear.id].zone == "p2:battlefield"
    check(s)


@pytest.mark.parametrize("mode", [0, 1])
def test_misfortune_modes(cards, mode):
    """700.2e: Bob chooses: +1/+1 counters on Alice's creatures and 4 life for her, or -1/-1 counters on Bob's creatures and 4 damage to Bob."""
    s = table(cards, ["Misfortune", "Grizzly Bears"], ["Grizzly Bears"], carol=None)
    (mine,), (his,) = bears(s, "p1"), bears(s, "p2")
    mana(s, "p1", R=2, C=2)
    cast(s, "Misfortune")
    answer(s, f"{mode}:0")
    assert (life(s, "p1"), life(s, "p2")) == ((44, 40) if mode == 0 else (40, 36))
    assert (s.state.cards[mine.id].counters.get("+1/+1", 0), s.state.cards[his.id].counters.get("-1/-1", 0)) == ((1, 0) if mode == 0 else (0, 1))
    check(s)


def test_the_caster_cannot_choose_the_opponents_mode(cards):
    """700.2e: modes (and the chooser) named in the cast action are ignored: the opponent is still asked."""
    s = table(cards, ["Misfortune"], carol=None)
    mana(s, "p1", R=2, C=2)
    cast(s, "Misfortune", modes=[0], chooser110f="p2")
    assert s.state.rules.decision.player == "p2"
