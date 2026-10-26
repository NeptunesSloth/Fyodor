"""Wave 110D: Dack Fayden, real Oracle text. The -6 emblem: "Whenever you cast a spell that targets one or more permanents, gain control of those permanents."

* 114.1, 114.4: the emblem sits in the command zone and its trigger works there; 603.2: it triggers on casting.
* 115.9b: only the permanents still targeted are taken; a spell that targets only players does nothing. 611.2c: the control change is permanent.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import put
from tests.wave110d_kit import activate, build, card_db, cast_on, check, full, now, settle  # noqa: F401


def emblem(s):
    dack = put(s, "Dack Fayden")
    act(s, "p1", type="counter", card_ids=[dack.id], kind="loyalty", delta=6)
    activate(s, dack, "−6")


def test_full():
    assert full("Dack Fayden")


def test_a_spell_targeting_a_permanent_steals_it(cards):
    s = build(cards, ["Dack Fayden", "Giant Growth"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    emblem(s)
    cast_on(s, "Giant Growth", bear)
    settle(s)
    assert now(s, bear).controller == "p1"
    check(s)


def test_a_spell_targeting_only_a_player_takes_nothing(cards):
    s = build(cards, ["Dack Fayden", "Lightning Bolt"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    emblem(s)
    cast_on(s, "Lightning Bolt", "p2")
    settle(s)
    assert now(s, bear).controller == "p2"
    check(s)
