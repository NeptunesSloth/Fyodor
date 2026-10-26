"""Wave 110M: attack triggers on real Oracle text. Every scenario checks the replay and a save and a load.

* 508.3a: "Whenever you attack a player or planeswalker with one or more creatures with power 1 or less, draw a card." (Rigo, Streetwise Mentor): once for
  each player or planeswalker attacked, counting only the creatures attacking it.
* 603.2c, 121.4, 104.2b: "When one or more of your opponents are dealt combat damage during your turn, draw two cards. If your library has no cards in it,
  you win the game. Fblthp's owner shuffles him into their library." (Fblthp, Impossibly Lost): once for the batch, the win checked after the draw.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.test_rules_wave36a_trigger_words import loyal
from tests.wave36a_kit import ready, to_turn_of
from tests.wave110m_kit import *

RIGO, FBLTHP = "Rigo, Streetwise Mentor", "Fblthp, Impossibly Lost"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([RIGO, FBLTHP])


def hand(s):
    return len(s.state.zones["p1:hand"])


# attackers (power) -> where each attacks: "p2" the player, "pw" Gideon; expected cards drawn
@pytest.mark.parametrize("who,draws", [
    ((("elf", "p2"),), 1),
    ((("bear", "p2"),), 0),                         # power 2: not enough
    ((("elf", "p2"), ("elf2", "p2")), 1),           # one or more at the same player: once
    ((("elf", "p2"), ("elf2", "pw")), 2),           # the player and the planeswalker are each attacked
    ((("bear", "p2"), ("elf", "pw")), 1),           # only the planeswalker's attacker has power 1 or less
    ((("elf", "p2"), ("bear", "pw")), 1),
    ((("bear", "pw"),), 0),
    ((("elf", "pw"), ("elf2", "pw")), 1),           # two creatures at one planeswalker: once
])
def test_rigo_draws_once_for_each_player_or_planeswalker_attacked_by_a_small_creature(cards, who, draws):
    s = build(cards, [RIGO, "Llanowar Elves", "Birds of Paradise", "Grizzly Bears"], ["Gideon Jura"], forests=20)
    put(s, RIGO)
    gideon = loyal(s, "Gideon Jura", "p2")
    elf, elf2, bear = put(s, "Llanowar Elves"), put(s, "Birds of Paradise"), put(s, "Grizzly Bears")
    by = {"elf": elf, "elf2": elf2, "bear": bear}
    next_turn(s)
    before = hand(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers",
        attackers=[{"card_id": by[n].id, "target": gideon.id if t == "pw" else t} for n, t in who])
    answer(s)
    assert hand(s) - before == draws
    check(s)


def library(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:library"]


def trim_library(s, keep):
    """Everything but ``keep`` cards of Alice's library into her graveyard (not drawn, so not a loss, 704.5b)."""
    extra = library(s)[keep:]
    act(s, "p1", type="move", card_ids=[c.id for c in extra], to={"player": "p1", "zone": "graveyard"})
    assert len(library(s)) == keep


@pytest.mark.parametrize("attackers,keep,win", [
    (("Grizzly Bears",), 5, False),                          # draws two, the library keeps three, Fblthp is shuffled in
    (("Grizzly Bears", "Llanowar Elves"), 5, False),         # two creatures deal damage at once: still one trigger
    (("Grizzly Bears",), 3, False),                          # four cards in the library after Fblthp joins... the library had 3: draws 2 and keeps 1
    (("Grizzly Bears",), 2, True),                           # the last cards are drawn: the library is empty, Alice wins
    (("Grizzly Bears",), 1, True),                           # drawing from the empty library does not lose first (121.4 / 704.5b vs 104.2b)
])
def test_fblthp_draws_two_wins_on_an_empty_library_and_shuffles_himself_in(cards, attackers, keep, win):
    s = build(cards, [FBLTHP, "Llanowar Elves", "Grizzly Bears"], forests=20)
    fblthp = put(s, FBLTHP)
    for n in attackers:
        put(s, n)
    next_turn(s)
    trim_library(s, keep)
    before = hand(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, n).id, "target": "p2"} for n in attackers])
    until(s, lambda s: s.state.turn.phase == "main2" or s.state.rules.winner is not None)
    answer(s)
    if win:
        assert s.state.rules.winner == "p1"
    else:
        assert s.state.rules.winner is None
        assert hand(s) - before == 2 and s.state.cards[fblthp.id].zone == "p1:library" and len(library(s)) == keep - 2 + 1
    check(s)


def test_fblthp_does_nothing_when_you_are_the_one_dealt_damage(cards):
    s = build(cards, [FBLTHP], ["Grizzly Bears"], forests=20)
    fblthp = put(s, FBLTHP)
    bear = put(s, "Grizzly Bears", "p2")
    ready(s, "Grizzly Bears", pid="p2")
    to_turn_of(s, "p2")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    before = hand(s)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p1"}])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s) == 38 and hand(s) == before and s.state.cards[fblthp.id].zone == "p1:battlefield"
    check(s)
