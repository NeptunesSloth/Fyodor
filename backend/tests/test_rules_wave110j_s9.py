"""Wave 110J session 9: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 122.1, 406.3, 608.2d: Kianne // Imbraham exile cards and mark them with study counters; the Fractal counts different mana values.
* 701.17, 701.59, 603.12: Memory Vampire mills the chosen players, then may collect evidence 9 to cast a nonland card of the damaged player's graveyard free.
* 613.1b, 608.2d, 701.26: Turf War: the creature's controller gains control of one of the defending player's contested lands (their choice) and untaps it.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110b_kit import attack, top
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    activate,
    card_db,
    ch,
    check,
    fresh,
    grave_new,
    mana,
    move,
    now,
    put_new,
    settle,
)

KIANNE = "Kianne, Dean of Substance // Imbraham, Dean of Theory"


@pytest.mark.parametrize("name", ["Turf War", KIANNE])
def test_the_cards_are_full(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(("contested", "choice", "taken"), [(0, 0, None), (1, 0, 0), (2, 1, 1)])
def test_turf_war_takes_a_contested_land(cards, contested, choice, taken):
    """The creature's controller (not Turf War's) picks among the lands with contested counters and untaps the one it takes."""
    s = build(cards, ["Turf War", "Grizzly Bears"])
    put_new(s, "Turf War")
    bears = put_new(s, "Grizzly Bears")
    lands = [put_new(s, "Island", "p2") for _ in range(2)]
    for land in lands[:contested]:
        act(s, "p2", type="counter", card_ids=[land.id], kind="contested", delta=1)
    for land in lands:
        act(s, "p2", type="tap", card_ids=[land.id])
    attack(s, bears)
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            assert d.kind == "choose_cards" and d.player == "p1" and len(d.options) == 2
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[lands[choice].id])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    for i, land in enumerate(lands):
        mine = taken == i
        assert (now(s, land).controller == "p1") is mine and (not now(s, land).tapped) is mine
    check(s)


def _kianne(cards, extra=(), face=0):
    s = build(cards, [KIANNE, *extra])
    k = put_new(s, KIANNE)
    s.state.rules.controlled_since[k.id].turn = 0
    if face:
        act(s, "p1", type="set_face", card_id=k.id, face=1)
    return s, k


@pytest.mark.parametrize(("name", "zone", "counters"), [("Forest", "p1:hand", 0), ("Grizzly Bears", "p1:exile", 1)])
def test_kianne_exiles_the_top_card(cards, name, zone, counters):
    """A land goes to your hand; anything else stays exiled with a study counter."""
    s, k = _kianne(cards, ["Grizzly Bears"])
    top(s, name)
    top_card = next(c for c in s.state.cards.values() if c.zone == "p1:library" and c.name == name)
    activate(s, k, "{T}: Exile")
    assert now(s, top_card).zone == zone and now(s, top_card).counters.get("study", 0) == counters
    check(s)


def test_kianne_fractal_counts_different_mana_values(cards):
    """Two nonland cards of one mana value and one of another: two +1/+1 counters; a land with a study counter does not count."""
    s, k = _kianne(cards, ["Grizzly Bears", "Templar Knight", "Wall of Stone", "Forest"])
    seen = []
    for name in ("Grizzly Bears", "Templar Knight", "Wall of Stone"):
        c = fresh(s, name)
        move(s, c, "exile")
        act(s, "p1", type="counter", card_ids=[c.id], kind="study", delta=1)
        seen.append(c)
    mana(s, G=1, C=4)
    activate(s, k, "{4}{G}")
    token = next(c for c in s.state.cards.values() if c.name == "Fractal" and c.zone.endswith("battlefield"))
    assert len({ch(s, c).mana_value for c in seen}) == 2 and ch(s, token).pt == (2, 2)
    check(s)


@pytest.mark.parametrize("pick", [0, 1])
def test_imbraham_exiles_x_cards_and_may_take_one(cards, pick):
    """The top X cards get study counters, then you may put a card with one into your hand (the player's choice, up to one)."""
    s, k = _kianne(cards, ["Grizzly Bears", "Templar Knight"], face=1)
    top(s, "Templar Knight")
    top(s, "Grizzly Bears")
    mana(s, U=2, C=2)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=1, x_value=2)
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and len(d.options) == 2
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[pick].id] if pick == 0 else [])
    settle(s)
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile" and c.counters.get("study")]
    assert len(exiled) == (1 if pick == 0 else 2) and len([c for c in s.state.cards.values() if c.zone == "p1:hand" and c.name in ("Grizzly Bears", "Templar Knight")]) == (1 if pick == 0 else 0)
    check(s)


def _combat(s, answer):
    """Play combat on to the second main phase, ``answer(decision)`` giving the option ids of every decision but the blocks."""
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=answer(d))
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


@pytest.mark.parametrize(("pay", "free"), [(True, True), (False, False)])
def test_memory_vampire_mills_then_collects_evidence(cards, pay, free):
    """Mills the chosen player by the damage; paying evidence 9 (three Walls of Stone, mana value 3 each) casts a nonland card free; declining leaves it."""
    s = build(cards, ["Memory Vampire", "Wall of Stone", "Wall of Stone", "Wall of Stone"], ["Grizzly Bears"])
    v = put_new(s, "Memory Vampire")
    for _ in range(3):
        grave_new(s, "Wall of Stone")
    bears = fresh(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    library = len(s.state.zones["p2:library"])
    attack(s, v)

    def answer(d):
        ids = [o.id for o in d.options]
        if "pay" in ids:
            return ["pay" if pay else "decline"]
        if "p2" in ids:
            return ["p2"]
        return ids if "Collect evidence" in d.prompt else ids[:1]

    _combat(s, answer)
    assert len(s.state.zones["p2:library"]) == library - ch(s, v).pt[0]
    assert (now(s, bears).zone == "p1:battlefield") is free and (now(s, bears).controller == "p1" if free else True)
    assert len([c for c in s.state.cards.values() if c.name == "Wall of Stone" and c.zone == "p1:exile"]) == (3 if pay else 0)
    check(s)
