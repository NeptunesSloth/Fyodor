"""Wave 110H session 4: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip).

* The Crowd Goes Wild: "Support X" on a sorcery is up to X target creatures (701.41a), then the trample line (611.2a).
* Crowd-Control Warden: the counters go on as it enters and again as it is turned face up, counting the other creatures then (614.1c, 708.11).
* Rain of Gore: a spell or ability gain of its own controller becomes a loss (614.1a, 119.10); another player's gain from it stays.
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, life, mana, put, to_hand

EXTRA = [
    real("The Crowd Goes Wild", "{X}{G}", 1, "Sorcery",
         "Assist (Another player can pay up to {X} of this spell's cost. You choose the value of X.)\nSupport X. (Put a +1/+1 counter on each of up to X "
         "target creatures.)\nEach creature with a +1/+1 counter on it gains trample until end of turn.", None, "G"),
    real("Rain of Gore", "{B}{B}", 2, "Enchantment",
         "If a spell or ability would cause its controller to gain life, that player loses that much life instead.", None, "B"),
    real("Tonic", "{W}", 1, "Instant", "Target player gains 3 life.", None, "W"),
    real("Crowd-Control Warden", "{3}{G}{W}", 5, "Creature \u2014 Centaur Soldier",
         "As this creature enters or is turned face up, put X +1/+1 counters on it, where X is the number of other creatures you control.\n"
         "Disguise {3}{G/W}{G/W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise "
         "cost.)", ("4", "4"), "GW"),
    real("Hill Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn, else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def _ch(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def test_crowd_goes_wild(cards):
    """X = 1: only the one target gets a counter, and only a creature with a counter gains trample."""
    s = build(cards, ["The Crowd Goes Wild", "Hill Giant", "Grizzly Bears"])
    giant, bears = put(s, "Hill Giant"), put(s, "Grizzly Bears")
    mana(s, G=1, C=1)
    cast(s, "The Crowd Goes Wild", [giant.id], x_value=1, target_counts=[1])
    answer(s)
    assert s.state.cards[giant.id].counters.get("+1/+1", 0) == 1 and not s.state.cards[bears.id].counters.get("+1/+1", 0)
    assert "trample" in _ch(s, giant).keywords and "trample" not in _ch(s, bears).keywords
    check(s)


@pytest.mark.parametrize("target,mine,theirs", [("p1", 37, 40), ("p2", 40, 43)])
def test_rain_of_gore(cards, target, mine, theirs):
    """Your own gain from your spell is a loss (the spell's controller is the gainer); an opponent gaining from your spell is not replaced."""
    s = build(cards, ["Rain of Gore", "Tonic"])
    put(s, "Rain of Gore")
    mana(s, W=1)
    cast(s, "Tonic", [target])
    answer(s)
    assert (life(s, "p1"), life(s, "p2")) == (mine, theirs)
    check(s)


def _warden_counters(s, w):
    return s.state.cards[w.id].counters.get("+1/+1", 0)


def test_crowd_control_warden_enters(cards):
    s = build(cards, ["Crowd-Control Warden", "Hill Giant", "Grizzly Bears"])
    put(s, "Hill Giant"), put(s, "Grizzly Bears")
    mana(s, G=1, W=1, C=3)
    w = cast(s, "Crowd-Control Warden")
    answer(s)
    assert s.state.cards[w.id].zone == "p1:battlefield" and _warden_counters(s, w) == 2
    check(s)


def test_crowd_control_warden_turned_face_up(cards):
    """Face down it has no abilities; the creatures it counts are those there when it is turned up, not when it was cast."""
    s = build(cards, ["Crowd-Control Warden", "Hill Giant", "Grizzly Bears"])
    w = to_hand(s, "Crowd-Control Warden")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=w.id, face_down=True)
    answer(s)
    assert s.state.cards[w.id].face_down and _warden_counters(s, w) == 0
    put(s, "Hill Giant"), put(s, "Grizzly Bears")
    mana(s, G=2, C=3)
    act(s, "p1", type="turn_face_up", card_id=w.id)
    answer(s)
    assert not s.state.cards[w.id].face_down and _warden_counters(s, w) == 2
    check(s)
