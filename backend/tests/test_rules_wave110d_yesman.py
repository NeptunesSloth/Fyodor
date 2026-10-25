"""Wave 110D: Yes Man, Personal Securitron, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 603.12, 701.15: "{T}: Target opponent gains control of Yes Man. When they do, you draw two cards and put a quest counter on Yes Man." — the opponent
  takes it, then the activator draws two and the counter goes on.
* 603.10a, 608.2h: "Wild Card — When Yes Man leaves the battlefield, its owner creates a tapped 1/1 white Soldier creature token for each quest counter on it."
  — the owner (not the controller) gets one tapped Soldier per counter it last had.
"""

from __future__ import annotations

from tests.wave9c_kit import build
from tests.wave110d_kit import activate, card_db, cast_on, check, full, now, put_new, to_phase  # noqa: F401

YES = "Yes Man, Personal Securitron"


def hand(s, pid):
    return len(s.state.zones[f"{pid}:hand"])


def soldiers(s, pid):
    return [c for c in s.state.cards.values() if c.name == "Soldier" and c.controller == pid and c.zone.endswith(":battlefield")]


def test_yes_man_is_full():
    assert full(YES)


def test_gives_away_draws_two_and_owner_gets_tokens(cards):
    s = build(cards, [YES], ["Murder"])
    yes = put_new(s, YES)
    to_phase(s, "main1", turn=3)
    h1 = hand(s, "p1")
    activate(s, yes, "{T}:")
    assert now(s, yes).controller == "p2" and now(s, yes).counters.get("quest") == 1 and hand(s, "p1") == h1 + 2
    to_phase(s, "main1", turn=4)
    cast_on(s, "Murder", yes, pid="p2")
    assert now(s, yes).zone.endswith(":graveyard")
    assert len(soldiers(s, "p1")) == 1 and not soldiers(s, "p2") and all(c.tapped for c in soldiers(s, "p1"))
    check(s)

