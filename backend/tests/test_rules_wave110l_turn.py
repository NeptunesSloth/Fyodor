"""Wave 110L: this-turn history conditions, real Oracle text, replay and save/load checked.

* Oblivious Bookworm - the discard is skipped if a permanent entered face down under your control this turn (708.2) or you turned one face up (702.37e).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from app.rules.plan import Plan
from tests.wave110l_kit import *

BOOK, SUMMONS = "Oblivious Bookworm", "Soul Summons"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([BOOK, SUMMONS])


def hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def manifest_bears(s):
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "library"}, position="top")
    cast(s, SUMMONS)
    answer(s)


def end_step(s):
    before = hand_size(s)
    to_phase(s, "end")
    answer(s)
    return hand_size(s) - before


def test_bookworm_draws_then_discards_when_nothing_happened(cards):
    s = build(cards, [BOOK, SUMMONS, "Grizzly Bears"])
    put(s, BOOK)
    next_turn(s)
    stops(s)
    assert end_step(s) == 0  # drew one, discarded one
    assert zone_of(s, "Grizzly Bears") != "p1:battlefield"
    check(s)


def test_bookworm_keeps_the_card_when_a_permanent_entered_face_down(cards):
    s = build(cards, [BOOK, SUMMONS, "Grizzly Bears"])
    put(s, BOOK)
    next_turn(s)
    stops(s)
    manifest_bears(s)
    assert end_step(s) == 1
    check(s)


def test_bookworm_keeps_the_card_when_you_turned_a_permanent_face_up(cards):
    s = build(cards, [BOOK, SUMMONS, "Grizzly Bears"])
    put(s, BOOK)
    manifest_bears(s)  # on an earlier turn: it does not count now
    face_down = next(c for c in s.state.cards.values() if c.face_down and c.owner == "p1")
    next_turn(s)
    stops(s)
    fund(s, "{1}{G}")
    act(s, "p1", type="turn_face_up", card_id=face_down.id)
    answer(s)
    assert end_step(s) == 1
    check(s)



WAR = "The First Tyrannic War"
test_full_war = full_test([WAR])


def counters(s, name):
    return card_named(s, name).counters.get("+1/+1", 0)


@pytest.mark.parametrize(("creature", "expect"), [("Walking Ballista", 3), ("Grizzly Bears", 0)])
def test_first_tyrannic_war_counters_only_for_a_mana_cost_with_x(cards, creature, expect):
    s = build(cards, [WAR, creature], forests=9)
    for land in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]:  # three lands (the rest stay in the library)
        act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
    to_hand(s, creature)
    cast(s, WAR)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s, "Yes", creature)  # "you may", then the card
    assert zone_of(s, creature) == "p1:battlefield"
    assert counters(s, creature) == expect
    check(s)


MOON = "Day of the Moon"
test_full_moon = full_test([MOON])


def name_it(s, text):
    d = resolve_decision(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[], name=text)


def resolve_decision(s):
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    return s.state.rules.decision


def through_bobs_turn(s):
    """To Alice's next main phase; Bob's goaded creatures attack her as they must (701.15b), she blocks nothing."""
    turn = s.state.turn.number + (2 if s.state.turn.active_player == "p1" else 1)
    for _ in range(200):
        if s.state.turn.phase == "main1" and s.state.turn.number == turn:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and d.player == "p2":
            mine = [c.id for c in s.state.cards.values() if c.owner == "p2" and c.zone == "p2:battlefield"]
            act(s, "p2", type="declare_attackers", attackers=[{"card_id": c, "target": "p1"} for c in mine])
        elif d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached Alice's main phase")


def goaded(s, name, pid="p2"):
    from app.rules.keyword_actions import goaded_by

    c = card_named(s, name, pid)
    return bool(goaded_by(Plan(s.state, "p1", s.cards, None).ch(c)))


def test_day_of_the_moon_goads_every_name_chosen_so_far(cards):
    s = build(cards, [MOON], ["Grizzly Bears", "Young Wolf", "Mesa Pegasus"])
    for n in ("Grizzly Bears", "Young Wolf", "Mesa Pegasus"):
        put(s, n, "p2")
    cast(s, MOON)
    name_it(s, "Grizzly Bears")
    answer(s)
    assert goaded(s, "Grizzly Bears") and not goaded(s, "Young Wolf") and not goaded(s, "Mesa Pegasus")
    through_bobs_turn(s)  # chapter II: the goad of chapter I has ended (until your next turn), the name chosen then still counts
    name_it(s, "Young Wolf")
    answer(s)
    assert goaded(s, "Grizzly Bears") and goaded(s, "Young Wolf") and not goaded(s, "Mesa Pegasus")
    check(s)


AVATAR = "Avatar Destiny"
test_full_avatar = full_test([AVATAR])


def top_of_library(s, *names):
    for n in reversed(names):
        c = next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")


@pytest.mark.parametrize("take", ["Llanowar Elves", None])
def test_avatar_destiny_mills_its_power_returns_itself_and_may_reanimate_a_milled_creature(cards, take):
    s = build(cards, [AVATAR, "Grizzly Bears", "Llanowar Elves", "Young Wolf", "Murder"])
    bears = put(s, "Grizzly Bears")
    cast(s, AVATAR, [bears.id])
    answer(s)
    top_of_library(s, "Llanowar Elves", "Young Wolf", "Forest")
    cast(s, "Murder", [bears.id])
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s, "Yes" if take else "No", take)  # "you may", then which creature
    assert zone_of(s, AVATAR) == "p1:hand"
    assert zone_of(s, "Llanowar Elves") == ("p1:battlefield" if take else "p1:graveyard")
    assert zone_of(s, "Young Wolf") == "p1:graveyard"
    check(s)


LAUNDRY = "Lumbering Laundry"
test_full_laundry = full_test([LAUNDRY])


def test_lumbering_laundry_lets_its_controller_look_at_face_down_creatures_until_end_of_turn(cards):
    s = build(cards, [LAUNDRY], ["Grizzly Bears"])
    laundry = put(s, LAUNDRY)
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "battlefield"}, face_down=True, face_down_kind="manifest", x=10, y=10)
    assert s.view("p1")["cards"][bears.id]["hidden"]  # before: Alice can't tell what it is
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=laundry.id, ability=0)
    answer(s)
    mine, theirs = s.view("p1")["cards"][bears.id], s.view("p2")["cards"][bears.id]
    assert mine["name"] == "Grizzly Bears" and not mine.get("hidden")
    assert theirs["name"] == "Grizzly Bears"  # its own controller always knows
    to_phase(s, "main1", turn=3)
    assert s.view("p1")["cards"][bears.id]["hidden"]  # the look ended with the turn
    check(s)
