"""Wave 110H session 4: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip).

* The Crowd Goes Wild: "Support X" on a sorcery is up to X target creatures (701.41a), then the trample line (611.2a).
* Crowd-Control Warden: the counters go on as it enters and again as it is turned face up, counting the other creatures then (614.1c, 708.11).
* Specter of Mortality: any number of graveyard creature cards (chosen as it resolves) are exiled; each other creature gets -X/-X (608.2d, 603.12).
* Time Reaper: only the damaged player's own face-up exiled card (not yours) goes to the bottom of their library; "if you do" gains 3 (608.2c, 406.3).
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
    real("Rabid Bite", "{1}{G}", 2, "Sorcery",
         "Target creature you control deals damage equal to its power to target creature you don't control.", None, "G"),
    real("Lifelinker", "{2}{W}", 3, "Creature \u2014 Vampire", "Lifelink", ("2", "2"), "W"),
    real("Tonic", "{W}", 1, "Instant", "Target player gains 3 life.", None, "W"),
    real("Crowd-Control Warden", "{3}{G}{W}", 5, "Creature \u2014 Centaur Soldier",
         "As this creature enters or is turned face up, put X +1/+1 counters on it, where X is the number of other creatures you control.\n"
         "Disguise {3}{G/W}{G/W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise "
         "cost.)", ("4", "4"), "GW"),
    real("Specter of Mortality", "{3}{B}{B}", 5, "Creature \u2014 Specter",
         "Flying\nWhen this creature enters, you may exile one or more creature cards from your graveyard. When you do, each other creature gets "
         "-X/-X until end of turn, where X is the number of cards exiled this way.", ("3", "3"), "B"),
    real("Runeclaw Bear", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G"),
    real("Elvish Visionary", "{1}{G}", 2, "Creature \u2014 Elf Shaman", "", ("1", "1"), "G"),
    real("Time Reaper", "{3}{B}{B}", 5, "Creature \u2014 Alien Horror",
         "Flying, haste\nConsume Anomaly \u2014 Whenever this creature deals combat damage to a player, put target face-up card they own in exile on the "
         "bottom of their library. If you do, you gain 3 life.", ("4", "4"), "B"),
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


def test_rain_of_gore_ignores_lifelink(cards):
    """702.15b: lifelink gain is a result of damage, not a spell or ability gain, so Rain of Gore leaves it alone while Tonic still turns to a loss."""
    s = build(cards, ["Rain of Gore", "Rabid Bite", "Lifelinker"], ["Hill Giant"])
    put(s, "Rain of Gore")
    ll, giant = put(s, "Lifelinker"), put(s, "Hill Giant", pid="p2")
    mana(s, G=1, C=1)
    cast(s, "Rabid Bite", [ll.id, giant.id], target_counts=[1, 1])
    answer(s)
    assert life(s, "p1") == 42
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


@pytest.mark.parametrize("n", [0, 1, 2])
def test_specter_of_mortality(cards, n):
    """X = the number exiled: the 1/1 dies for any n >= 1, the 3/3 shrinks by n, the Specter itself is untouched."""
    s = build(cards, ["Specter of Mortality", "Hill Giant", "Elvish Visionary", "Grizzly Bears", "Runeclaw Bear"])
    giant, elf = put(s, "Hill Giant"), put(s, "Elvish Visionary")
    dead = [to_hand(s, "Grizzly Bears"), to_hand(s, "Runeclaw Bear")]
    for c in dead:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=2, C=3)
    spec = cast(s, "Specter of Mortality")
    answer(s, [c.id for c in dead[:n]])  # the trigger resolves: the choice of the cards to exile
    zones = [s.state.cards[c.id].zone for c in dead]
    assert zones == ["p1:exile"] * n + ["p1:graveyard"] * (2 - n)
    assert (s.state.cards[elf.id].zone == "p1:battlefield") == (n == 0)
    assert _ch(s, giant).pt == (3 - n, 3 - n) and _ch(s, spec).pt == (3, 3)
    check(s)


@pytest.mark.parametrize("exiled", [True, False])
def test_time_reaper(cards, exiled):
    """Their exiled card goes to the bottom of their library and you gain 3; your own exiled card is never a target; with none, no life."""
    from tests.test_rules_conditionals import attack, until

    s = build(cards, ["Time Reaper", "Hill Giant"], ["Grizzly Bears"])
    reaper, mine = put(s, "Time Reaper"), to_hand(s, "Hill Giant")
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "exile"})
    theirs = to_hand(s, "Grizzly Bears", "p2")
    if exiled:
        act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "exile"})
    until(s, lambda s: s.state.turn.number == 3 and (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    attack(s, (s.state.cards[reaper.id], "p2"))
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None or not s.state.zones.get("stack") and s.state.turn.phase != "combat":
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert life(s, "p2") == 36
    assert s.state.cards[mine.id].zone == "p1:exile"
    assert (s.state.cards[theirs.id].zone, life(s, "p1")) == (("p2:library", 43) if exiled else ("p2:hand", 40))
    check(s)
