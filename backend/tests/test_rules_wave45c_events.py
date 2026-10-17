"""Wave 45C: coin flip events (CR 2026-09-25, real Oracle text, tests/fixtures/wave45c_cards.json from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 705.2, 705.3: "Whenever you win a coin flip" (Tavern Scoundrel, Chance Encounter, Setzer, Zndrsplt, Okaun): only the player who flipped wins or loses the
  flip; an effect that reads heads or tails (Odds // Ends) has no winner or loser. "Flip a coin until you lose a flip" flips one coin at a time.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, until
from tests.test_rules_wave38a_trailing_ifs import hand, table
from tests.wave9c_kit import card_named, cast, check, mana, put, to_hand
from tests.wave36a_kit import attack_as, ready, resolve_stack, to_turn_of
from tests.wave45c_kit import ability, hold, make_repo, pt_of, treasures

COMMANDERS = ["Setzer, Wandering Gambler", "Zndrsplt, Eye of Wisdom", "Okaun, Eye of Chaos"]


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [*COMMANDERS, "Tavern Scoundrel", "Chance Encounter"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def flips(monkeypatch, *results):
    """The coins come up as listed (1: the call matches, the flip is won), then tails; the result is recorded on the step: a replay doesn't flip again."""
    left = list(results)
    monkeypatch.setattr("app.game.resolve._rng_int", lambda rng, lo, hi: left.pop(0) if left else 0)


@pytest.mark.parametrize("win", [True, False])
def test_tavern_scoundrel_makes_two_treasures_when_you_win_a_flip(cards, monkeypatch, win):
    flips(monkeypatch, int(win))
    s = table(cards, ["Tavern Scoundrel"])
    scoundrel = put(s, "Tavern Scoundrel")
    put(s, "Forest")
    mana(s, G=1)
    s.state.rules.controlled_since[scoundrel.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=scoundrel.id, ability=ability(s, scoundrel, "Flip a coin"))
    resolve_stack(s)
    assert treasures(s) == (2 if win else 0)
    check(s)


@pytest.mark.parametrize("win", [True, False])
def test_chance_encounter_gets_a_luck_counter_for_each_flip_you_win(cards, monkeypatch, win):
    flips(monkeypatch, int(win))
    s = table(cards, ["Chance Encounter", "The Gold Saucer"])
    encounter, saucer = put(s, "Chance Encounter"), put(s, "The Gold Saucer")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=saucer.id, ability=ability(s, saucer, "Flip a coin"))
    resolve_stack(s)
    assert s.state.cards[encounter.id].counters.get("luck", 0) == int(win)
    check(s)


def test_the_flipper_alone_wins_an_opponents_flip_is_not_yours(cards, monkeypatch):
    """Chance Encounter ruling: "Your opponent losing a flip does not count as you winning one." Bob wins one: Alice's Scoundrel makes no Treasure."""
    flips(monkeypatch, 1)
    s = table(cards, ["Tavern Scoundrel"], ["The Gold Saucer"])
    put(s, "Tavern Scoundrel")
    saucer = put(s, "The Gold Saucer", "p2")
    to_turn_of(s, "p2")
    mana(s, "p2", C=2)
    act(s, "p2", type="activate_ability", card_id=saucer.id, ability=ability(s, saucer, "Flip a coin"))
    resolve_stack(s)
    assert treasures(s, "p2") == 1 and treasures(s, "p1") == 0
    check(s)


def test_odds_ends_reads_heads_or_tails_so_nobody_wins_the_flip(cards, monkeypatch):
    """Odds // Ends: "If it comes up heads, …" (705.2: no winner or loser): Tavern Scoundrel doesn't see a win."""
    flips(monkeypatch, 1)
    s = table(cards, ["Tavern Scoundrel", "Odds // Ends", "Lightning Bolt"])
    put(s, "Tavern Scoundrel")
    bolt, odds = (card_named(s, n) for n in ("Lightning Bolt", "Odds // Ends"))
    act(s, "p1", type="move", card_ids=[bolt.id, odds.id], to={"zone": "hand"})
    hold(s)
    mana(s, R=2, U=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=odds.id, face=0, targets=[bolt.id])
    settle(s)
    assert s.state.players["p2"].life == 40 and treasures(s) == 0  # (heads: the Bolt is countered)
    check(s)


@pytest.mark.parametrize("win", [True, False])
def test_setzers_vehicle_flips_when_it_connects_and_a_win_makes_two_tapped_treasures(cards, monkeypatch, win):
    flips(monkeypatch, int(win))
    s = table(cards, ["Setzer, Wandering Gambler"])
    setzer = to_hand(s, "Setzer, Wandering Gambler")
    mana(s, B=1, R=1, G=1)
    cast(s, "Setzer, Wandering Gambler")
    resolve_stack(s)  # (its enter trigger: The Blackjack)
    jack = card_named(s, "The Blackjack")
    ready(s, "Setzer, Wandering Gambler", "The Blackjack")
    act(s, "p1", type="activate_ability", card_id=jack.id, ability=ability(s, jack, "Crew"), crew=[setzer.id])
    resolve_stack(s)
    attack_as(s, "p1", [jack], "p2")
    until(s, lambda s: s.state.turn.phase == "end_combat")
    assert s.state.players["p2"].life == 37
    made = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    assert len(made) == (2 if win else 0) and all(c.tapped for c in made)
    check(s)


def test_zndrsplt_and_okaun_flip_until_a_loss_and_see_every_win(cards, monkeypatch):
    """Two wins then a loss at the beginning of combat: Zndrsplt draws twice (a player's win), Okaun doubles its power and toughness twice."""
    flips(monkeypatch, 1, 1, 0)
    s = table(cards, ["Zndrsplt, Eye of Wisdom", "Okaun, Eye of Chaos"])
    for n in ("Zndrsplt, Eye of Wisdom", "Okaun, Eye of Chaos"):
        put(s, n)
    before, base = hand(s), pt_of(s, "Okaun, Eye of Chaos")
    until(s, lambda s: s.state.turn.phase == "declare_attackers")  # (the trigger resolved on the way)
    assert hand(s) == before + 2
    assert pt_of(s, "Okaun, Eye of Chaos") == (base[0] * 4, base[1] * 4)
    check(s)
