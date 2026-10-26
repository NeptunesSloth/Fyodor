"""Wave 110N: Shambling Swarm (601.2d divided counters, 603.7a the delayed removal counts what was really put on each creature)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

SWARM = "Shambling Swarm"
EXTRA = [real("Bull", "{3}{G}", 4, "Creature — Ox", "", ("4", "4"), "G"), real("Ox", "{3}{G}", 4, "Creature — Ox", "", ("4", "4"), "G"), real(SWARM, "{1}{B}", 2, "Creature — Insect Horror",
              "When this creature dies, distribute three -1/-1 counters among one, two, or three target creatures. For each -1/-1 counter you put on a creature this way, "
              "remove a -1/-1 counter from that creature at the beginning of the next end step.", ("1", "1"), "B")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([SWARM])


def kill_swarm(cards, victims, amounts):
    """Alice's Swarm dies (her own Murder); its trigger divides three counters among ``victims`` (Bob's creatures) by ``amounts``."""
    s = build(cards, [SWARM, "Murder"], victims)
    swarm = put(s, SWARM)
    targets = [put(s, n, "p2") for n in victims]
    mana(s, "p1", B=3)
    cast(s, "Murder", [swarm.id], pay=False)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[t.id for t in targets])
    if len(targets) > 1:
        act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[], amounts=amounts)
    answer(s)
    return s, targets


def test_the_counters_are_removed_again_at_the_next_end_step(cards):
    s, (a, b) = kill_swarm(cards, ["Ox", "Bull"], [2, 1])
    assert sorted((s.state.cards[c.id].counters.get("-1/-1", 0)) for c in (a, b)) == [1, 2]
    assert sorted(ch(s, c).pt for c in (a, b)) == [(2, 2), (3, 3)]
    stops(s)
    to_phase(s, "end")
    answer(s)
    assert all(s.state.cards[c.id].counters.get("-1/-1", 0) == 0 and ch(s, c).pt == (4, 4) for c in (a, b))
    check(s)


def test_a_single_target_gets_all_three(cards):
    s, (a,) = kill_swarm(cards, ["Ox"], [3])
    assert s.state.cards[a.id].counters.get("-1/-1") == 3 and ch(s, a).pt == (1, 1)
    stops(s)
    to_phase(s, "end")
    answer(s)
    assert s.state.cards[a.id].counters.get("-1/-1", 0) == 0 and ch(s, a).pt == (4, 4)
    check(s)


def test_a_creature_the_counters_killed_stays_dead(cards):
    s, (a, b) = kill_swarm(cards, ["Grizzly Bears", "Ox"], [2, 1])
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    stops(s)
    to_phase(s, "end")
    answer(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and s.state.cards[b.id].counters.get("-1/-1", 0) == 0
    check(s)
