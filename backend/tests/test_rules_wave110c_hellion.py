"""Wave 110C: Volcano Hellion: a damage amount of the controller's choice, 107.1; echo {X} with X the controller's life total, 702.30a."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, check, life, make_db, mana, put, real, to_hand

HELLION = ("This creature has echo {X}, where X is your life total. (At the beginning of your upkeep, if this came under your control since the beginning of your "
           "last upkeep, sacrifice it unless you pay its echo cost.)\nWhen this creature enters, it deals an amount of damage of your choice to you and target "
           "creature. The damage can't be prevented.")
DEAD = ("Menace\nWhen this creature dies, you may pay {B}. If you do, return it to its owner's hand.\nWhen this creature dies, you may pay {X}. If you do, return another "
        "target Zombie creature card with mana value X from your graveyard to the battlefield.")
EXTRA = [real("Volcano Hellion", "{2}{R}{R}", 4, "Creature — Hellion", HELLION, ("5", "4"), "R"),
         real("Relentless Dead", "{B}{B}", 2, "Creature — Zombie", DEAD, ("2", "2"), "B"),
         real("Two Zombie", "{1}{B}", 2, "Creature — Zombie", "", ("2", "2"), "B"),
         real("Three Zombie", "{2}{B}", 3, "Creature — Zombie", "", ("3", "3"), "B"),
         real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Volcano Hellion", "Relentless Dead"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("n", [0, 3, 6])
def test_enter_damage_of_your_choice(cards, n):
    s = build(cards, ["Volcano Hellion", "Grizzly Bears"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, R=2, C=2)
    h = to_hand(s, "Volcano Hellion")
    act(s, "p1", type="cast_spell", card_id=h.id)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            typed = d.options[0].id == "__number__"
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[] if typed else [bear.id], **({"name": str(n)} if typed else {}))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p1") == 40 - n
    assert (s.state.cards[bear.id].zone == "p2:graveyard") == (n >= 2)  # 2 toughness
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_echo_costs_the_life_total(cards, pay):
    s = build(cards, ["Volcano Hellion"])
    h = put(s, "Volcano Hellion")
    act(s, "p1", type="set_life", player="p1", value=3)
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.resume["step"] == "pay_or_sacrifice" and d.resume["cost"] == "{3}"
    if pay:
        mana(s, C=3)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay" if pay else "sacrifice"])
    answer(s)
    assert s.state.cards[h.id].zone == ("p1:battlefield" if pay else "p1:graveyard")


@pytest.mark.parametrize(("x", "target", "back"), [(2, "Two Zombie", True), (2, "Three Zombie", False), (3, "Three Zombie", True), (None, "Two Zombie", False)])
def test_relentless_dead_returns_the_zombie_with_mana_value_x(cards, x, target, back):
    """107.3f: the target is chosen as the ability goes on the stack, X as it resolves; a card of another mana value stays."""
    s = build(cards, ["Relentless Dead", "Two Zombie", "Three Zombie", "Murder"])
    dead = put(s, "Relentless Dead")
    z = {n: to_hand(s, n) for n in ("Two Zombie", "Three Zombie")}
    act(s, "p1", type="move", card_ids=[c.id for c in z.values()], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=2, C=4)
    murder = to_hand(s, "Murder")
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[dead.id])
    for _ in range(60):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        if d.kind == "order":
            pick = ids
        elif z[target].id in ids:
            pick = [z[target].id]
        elif x is not None and f"x:{x}" in ids:
            pick = [f"x:{x}"]
        else:
            pick = [next(i for i in ids if "decline" in i.lower() or i == ids[-1])]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    assert (s.state.cards[z[target].id].zone == "p1:battlefield") == back
    assert s.state.cards[z["Two Zombie" if target == "Three Zombie" else "Three Zombie"].id].zone == "p1:graveyard"
    check(s)
