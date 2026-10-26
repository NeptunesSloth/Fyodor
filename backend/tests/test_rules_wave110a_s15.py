"""Wave 110A session 15: layer-6 timestamp order for the Zinnia offspring grant against a real static "loses all abilities" (Sludge Monster)."""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

from app.rules import wave110a_grants  # isort: skip


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _bears(s):
    return next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield" and not c.token)


def _run(cards, wipe_first):
    s = build(cards, ["Zinnia, Valley's Voice", "Grizzly Bears", "Sludge Monster"])
    put(s, "Zinnia, Valley's Voice")
    if wipe_first:
        put(s, "Sludge Monster")
    c = to_hand(s, "Grizzly Bears")
    fund(s, "{1}{G}{2}")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    answer(s)
    if not wipe_first:
        put(s, "Sludge Monster")
    check(s)
    bears = _bears(s)
    bears.counters["slime"] = 1  # Sludge Monster: "Non-Horror creatures with slime counters on them lose all abilities"
    s.state.seq += 1
    return s, bears


def test_wipe_earlier_than_the_grant_keeps_the_granted_offspring(cards):  # 613.7: the permanent's timestamp is later than Sludge Monster's, so the grant applies after the wipe
    s, bears = _run(cards, True)
    assert wave110a_grants.granted_offspring(ch(s, bears))


def test_wipe_later_than_the_grant_removes_the_granted_offspring(cards):  # 613.7: Sludge Monster entered after the creature, so its wipe applies after the grant
    s, bears = _run(cards, False)
    assert not wave110a_grants.granted_offspring(ch(s, bears))


def test_full(cards):
    from app.rules import coverage

    assert all(coverage.of_card_data(cards.resolve(n)).level == "FULL" for n in ("The Master, Multiplied", "Aboleth Spawn"))


def _unused_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve("The Master, Multiplied")).level == "FULL"


def _myriad(cards):
    from tests.test_rules_conditionals import until as until_
    from tests.test_rules_wave6e_statics import attack_with
    from tests.test_rules_wave15e_keywords import build3, next_own_turn

    s = build3(cards, "The Master, Multiplied", "Grizzly Bears")
    master = put(s, "The Master, Multiplied")
    next_own_turn(s)
    attack_with(s, master)
    until_(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one" and "token copy" in s.state.rules.decision.prompt)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    until_(s, lambda s: s.state.turn.phase == "main2")
    return s


def test_master_multiplied_keeps_its_myriad_tokens_at_end_of_combat(cards):  # 614.17: the delayed exile trigger can't exile the controller's creature tokens
    s = _myriad(cards)
    toks = [c for c in s.state.cards.values() if c.token and c.name == "The Master, Multiplied" and c.zone == "p1:battlefield"]
    assert len(toks) == 1
    check(s)


SPAWN = "Aboleth Spawn"


def _spawn(cards, creature, yes, targets=None):
    s = build(cards, [creature, "Grizzly Bears"], [SPAWN])
    put(s, SPAWN, pid="p2")
    hand = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    cast(s, creature)
    answer(s, *([] if targets is None else [targets]), "yes" if yes else "no")
    return s, hand


@pytest.mark.parametrize("yes", [True, False])
def test_aboleth_spawn_copies_an_opponents_enters_trigger(cards, yes):  # 603.2d, 707.10: p1's Elvish Visionary draws for p1; the copy (p2 controls it) draws for p2
    s, hand = _spawn(cards, "Elvish Visionary", yes)
    assert (len(s.state.zones["p1:hand"]) - hand["p1"], len(s.state.zones["p2:hand"]) - hand["p2"]) == (0, 1 if yes else 0)  # p1: -1 (cast) +1 (draw)
    check(s)


def test_aboleth_spawn_ignores_its_controllers_own_creatures(cards):
    s = build(cards, ["Elvish Visionary", SPAWN])
    put(s, SPAWN)
    n = len(s.state.zones["p1:hand"])
    cast(s, "Elvish Visionary")
    answer(s)
    assert len(s.state.zones["p1:hand"]) == n  # cast -1, draw +1, no copy
    check(s)
