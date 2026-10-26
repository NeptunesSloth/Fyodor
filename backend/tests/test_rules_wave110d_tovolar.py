"""Wave 110D: Tovolar, Dire Overlord // Tovolar, the Midnight Scourge, real Oracle text (tests/fixtures/wave110d_cards.json).

* 603.4: "if you control three or more Wolves and/or Werewolves" is an intervening if, checked as it triggers and as it resolves.
* 731.1: it becomes night; 701.28: "transform any number of Human Werewolves you control" is a choice on resolution (no target, 601.2c).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave110d_kit import build, card_db, cast_on, check, full, now, put_new, settle, to_phase  # noqa: F401

NAME = "Tovolar, Dire Overlord // Tovolar, the Midnight Scourge"
VILLAGERS = "Villagers of Estwald // Howlpack of Estwald"


def test_full():
    assert full(NAME)


def _upkeep(cards, wolves, take=True):
    s = build(cards, [NAME, VILLAGERS, "Young Wolf", "Young Wolf", "Lightning Bolt"], ["Lightning Bolt"])
    tov = put_new(s, NAME)
    vil = put_new(s, VILLAGERS)
    for _ in range(wolves):
        put_new(s, "Young Wolf")
    cast_on(s, "Lightning Bolt", "p2")  # (a spell each turn keeps it day (731.2) and Villagers' own trigger, which needs none or two, off)
    to_phase(s, "main1", turn=2)
    cast_on(s, "Lightning Bolt", "p1", pid="p2")
    if not wolves:
        to_phase(s, "main1", turn=3)
        return s, tov, vil
    for _ in range(60):  # (to the choice of Human Werewolves, in turn 3's upkeep)
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        act(s, s.state.rules.priority, type="pass_priority") if d is None else act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options] if take else [])
    settle(s)
    return s, tov, vil


def test_three_creatures_make_night_and_transform_the_chosen(cards):
    s, tov, vil = _upkeep(cards, 2, take=False)
    assert now(s, tov).face == 1 and now(s, vil).face == 0  # (night: the daybound Tovolar transformed; none chosen)
    check(s)


def test_choose_the_human_werewolf(cards):
    s, tov, vil = _upkeep(cards, 2)
    assert now(s, vil).face == 1
    check(s)


def test_two_creatures_do_nothing(cards):
    s, tov, vil = _upkeep(cards, 0)
    assert now(s, tov).face == 0 and now(s, vil).face == 0
    check(s)
