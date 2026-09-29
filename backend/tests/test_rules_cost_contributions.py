"""Convoke, improvise and delve pay parts of a spell's total cost; they never produce mana.

CR 702.51a (convoke): "For each colored mana in this spell's total cost, you may tap an untapped
creature of that color you control rather than pay that mana. For each generic mana in this
spell's total cost, you may tap an untapped creature you control rather than pay that mana."
CR 702.126a (improvise) and 702.66a (delve): the same, for generic mana only, tapping an artifact
/ exiling a card from your graveyard. 702.51b / 702.126b / 702.66b: they apply after the total
cost is determined (601.2f). 601.2h: the total cost is paid all at once — no partial payments.
106.3 / 106.12a: mana is produced only by effects that add it; "tapped for mana" means a mana
ability. 107.4e: a hybrid symbol is each of its colors.

Players tap their own mana (payment "self"): clicking a creature / artifact / graveyard card
commits it to pay one symbol; nothing is tapped or exiled until the whole cost is paid.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import mana as M
from app.rules import payment as P
from tests.game_helpers import act, deck, enable, zone


def build(cards, spell, *, creatures=(), artifacts=0, graveyard=0, pool=None):
    alice = deck(cards, "Krenko, Mob Boss", [(1, spell), (12, "Island")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False))
    for prefs in state.rules.prefs.values():
        prefs.payment = "self"  # the table default: players tap their own mana
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"  # (so a spell waits on the stack)
    card = next(c for c in s.state.cards.values() if c.name == spell)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "hand"})
    made = []
    for i, colors in enumerate(creatures):
        act(s, "p1", type="create_token", player="p1", token={
            "name": f"Helper{i}", "type_line": "Token Creature — Test", "power": "1", "toughness": "1", "colors": colors})
        made.append(next(c.id for c in s.state.cards.values() if c.name == f"Helper{i}"))
    arts = []
    for i in range(artifacts):
        act(s, "p1", type="create_token", player="p1", token={
            "name": f"Gizmo{i}", "type_line": "Token Artifact — Treasure",
            "text": "{T}, Sacrifice this artifact: Add one mana of any color."})
        arts.append(next(c.id for c in s.state.cards.values() if c.name == f"Gizmo{i}"))
    islands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.zone == "p1:library"]
    grave = islands[:graveyard]
    if grave:
        act(s, "p1", type="move", card_ids=grave, to={"zone": "graveyard"})
    if pool:
        act(s, "p1", type="add_mana", player="p1", mana=pool)
    return s, card, made, arts, grave


def cast(s, card, **extra):
    act(s, "p1", type="cast_spell", card_id=card.id, **extra)
    return s.state.rules.decision


def commit(s, cid, kind):
    act(s, "p1", type="activate_ability", card_id=cid, ability=0, **{kind: True})


def record(s, card):
    r = s.state.rules
    return next(v for v in r.payments.values() if v.card == card.id)


# -- the payment model ---------------------------------------------------------------------
def test_requirement_matching():
    red, gold, grey = P.Helper("convoke", "a", frozenset("R")), P.Helper("convoke", "b", frozenset("WU")), \
        P.Helper("convoke", "c")
    art, grave = P.Helper("improvise", "d"), P.Helper("delve", "e")
    assert P.pays(red, "R") and P.pays(red, "1") and not P.pays(red, "G") and not P.pays(red, "C")
    assert P.pays(red, "R/G") and P.pays(red, "2/R") and P.pays(red, "R/P") and not P.pays(red, "W/U")
    assert P.pays(gold, "W") and P.pays(gold, "U") and not P.pays(gold, "B")
    assert P.pays(grey, "1") and not P.pays(grey, "C") and not P.pays(grey, "R")
    for h in (art, grave):
        assert P.pays(h, "1") and not any(P.pays(h, s) for s in ("C", "U", "W/U", "2/U", "U/P"))


def test_assignment_prefers_what_the_pool_cannot_pay():
    cost = M.parse_cost("{1}{G}")
    green = P.Helper("convoke", "a", frozenset("G"))
    assert P.assign(cost, [green], P.pool_pays({"C": 1})) == ["G"]  # {C} in the pool pays the generic
    assert P.assign(cost, [green], P.pool_pays({"G": 1})) in (["G"], ["1"])
    assert P.assign(M.parse_cost("{C}"), [P.Helper("convoke", "x")]) is None
    assert P.remaining(M.parse_cost("{3}{G}{G}"), ["G", "1", "1"]).text() == "{1}{G}"


# 1-3: none of them can pay {C}
@pytest.mark.parametrize(("spell", "kind"), [("Test Colorless Convoke", "convoke"),
                                             ("Test Colorless Improvise", "improvise"),
                                             ("Test Colorless Delve", "delve")])
def test_cannot_pay_specific_colorless(cards, spell, kind):
    s, card, made, arts, grave = build(cards, spell, creatures=[[], []], artifacts=2, graveyard=2)
    helpers = {"convoke": made, "improvise": arts, "delve": grave}[kind]
    d = cast(s, card)
    assert d.display["kind"] == "tap_mana" and d.display["cost"] == "{1}{C}"
    commit(s, helpers[0], kind)  # pays the {1}
    with pytest.raises(ActionError, match=r"never \{C\}"):
        commit(s, helpers[1], kind)  # nothing but {C} is left
    d = s.state.rules.decision
    assert [p["pays"] for p in d.display["paid"]] == ["1"] and d.display["remaining"] == "{C}"
    assert s.state.players["p1"].mana == {}
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})  # real colorless mana pays {C}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    assert s.state.cards[card.id].zone == "stack"
    rec = record(s, card)
    assert rec.mana_spent == {"C": 1} and [(c.kind, c.pays) for c in rec.contributions] == [(kind, "1")]


# 4: improvise pays only generic
def test_improvise_pays_only_generic(cards):
    s, card, _, arts, _ = build(cards, "Reverse Engineer", artifacts=4)  # {3}{U}{U}
    cast(s, card)
    for a in arts[:3]:
        commit(s, a, "improvise")
    with pytest.raises(ActionError, match="improvise pays only generic"):
        commit(s, arts[3], "improvise")
    d = s.state.rules.decision
    assert d.display["remaining"] == "{U}{U}" and not any(s.state.cards[a].tapped for a in arts)


# 5: delve pays only generic, and no more cards than the generic part
def test_delve_pays_only_generic_and_no_more(cards):
    s, card, _, _, grave = build(cards, "Treasure Cruise", graveyard=9)  # {7}{U}
    cast(s, card)
    for g in grave[:7]:
        commit(s, g, "delve")
    with pytest.raises(ActionError, match="delve pays only generic"):
        commit(s, grave[7], "delve")
    d = s.state.rules.decision
    assert d.display["remaining"] == "{U}" and len(zone(s.state, "p1", "graveyard")) == 9  # nothing exiled yet
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1})
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    assert set(grave[:7]) <= set(zone(s.state, "p1", "exile")) and len(zone(s.state, "p1", "graveyard")) == 2
    rec = record(s, card)
    assert rec.mana_spent == {"U": 1} and [c.pays for c in rec.contributions] == ["1"] * 7


# 6: a colored creature pays a matching colored symbol
def test_colored_creature_pays_its_color(cards):
    s, card, made, _, _ = build(cards, "Stoke the Flames", creatures=[["R"], ["R"], [], ["G"]])  # {2}{R}{R}
    cast(s, card, targets=["p2"])
    for c in made:
        commit(s, c, "convoke")
    assert s.state.cards[card.id].zone == "stack" and all(s.state.cards[c].tapped for c in made)
    pays = {c.card: c.pays for c in record(s, card).contributions}
    assert pays[made[0]] == "R" and pays[made[1]] == "R" and pays[made[2]] == "1" and pays[made[3]] == "1"
    assert record(s, card).mana_spent == {}


# 7: a wrong-color creature can't pay a different colored symbol
def test_wrong_color_creature_cannot_pay_colored(cards):
    s, card, made, _, _ = build(cards, "Stoke the Flames", creatures=[["G"], ["G"], ["G"]])
    cast(s, card, targets=["p2"])
    commit(s, made[0], "convoke")
    commit(s, made[1], "convoke")  # the two generic
    with pytest.raises(ActionError, match="convoke pays only generic mana or mana of its color"):
        commit(s, made[2], "convoke")
    assert s.state.rules.decision.display["remaining"] == "{R}{R}"


# 8: a multicolored creature chooses one of its colors
def test_multicolored_creature_pays_either_color(cards):
    s, card, made, _, _ = build(cards, "Test Azorius Convoke", creatures=[["W", "U"], ["W", "U"]])  # {W}{U}
    cast(s, card)
    commit(s, made[0], "convoke")
    commit(s, made[1], "convoke")
    assert s.state.cards[card.id].zone == "stack"
    assert sorted(c.pays for c in record(s, card).contributions) == ["U", "W"]


def test_multicolored_creature_fills_the_color_the_pool_lacks(cards):
    s, card, made, _, _ = build(cards, "Test Azorius Convoke", creatures=[["W", "U"]], pool={"W": 1})
    cast(s, card)
    commit(s, made[0], "convoke")
    assert s.state.cards[card.id].zone == "stack"
    rec = record(s, card)
    assert [c.pays for c in rec.contributions] == ["U"] and rec.mana_spent == {"W": 1}


# 9-11: no mana is produced — the pool never grows, nothing is left over, nothing "adds mana"
def test_contributions_never_touch_the_mana_pool(cards):
    s, card, made, _, _ = build(cards, "Stoke the Flames", creatures=[["R"], ["R"], [], []])
    cast(s, card, targets=["p2"])
    for c in made[:3]:
        commit(s, c, "convoke")
        assert s.state.players["p1"].mana == {}
        assert s.state.rules.decision.display["pool"] == {}
    commit(s, made[3], "convoke")
    assert s.state.players["p1"].mana == {}  # no excess: nothing was ever added
    events = s.state.rules.events
    assert not [e for e in events if e.kind == "mana_added"]
    assert {e.card for e in events if e.kind == "tapped"} >= set(made)


def test_real_mana_is_seen_as_mana_contributions_are_not(cards):
    s, card, made, _, _ = build(cards, "Test Azorius Convoke", creatures=[["W"]])
    island = zone(s.state, "p1", "library")[0]
    act(s, "p1", type="move", card_ids=[island], to={"zone": "battlefield"})
    cast(s, card)
    act(s, "p1", type="activate_ability", card_id=island, ability=0)  # a mana ability: {U} is added
    assert [e.card for e in s.state.rules.events if e.kind == "mana_added"] == [island]
    before = max(e.batch for e in s.state.rules.events)
    commit(s, made[0], "convoke")
    assert s.state.cards[card.id].zone == "stack"
    assert not [e for e in s.state.rules.events if e.kind == "mana_added" and e.batch > before]  # (convoking adds none)
    rec = record(s, card)
    assert rec.mana_spent == {"U": 1} and [(c.card, c.pays) for c in rec.contributions] == [(made[0], "W")]


# 12: provenance keeps actual mana and contributions apart
def test_payment_provenance(cards):
    s, card, made, _, _ = build(cards, "Stoke the Flames", creatures=[["R"], []], pool={"R": 1, "C": 1})
    cast(s, card, targets=["p2"])
    commit(s, made[0], "convoke")
    commit(s, made[1], "convoke")
    rec = record(s, card)
    assert rec.total_cost == "{2}{R}{R}" and rec.mana_spent == {"R": 1, "C": 1}
    assert sum(rec.mana_spent.values()) == 2  # mana spent to cast it: 2, not 4
    assert [(c.kind, c.card, c.name, c.pays) for c in rec.contributions] == [
        ("convoke", made[0], "Helper0", "R"), ("convoke", made[1], "Helper1", "1")]
    assert rec.alternative is None and rec.additional == [] and rec.life == 0


def test_the_permanent_remembers_how_it_was_paid(cards):
    s, card, made, _, _ = build(cards, "Test Azorius Convoke", creatures=[["W"], ["U"]])
    cast(s, card)
    commit(s, made[0], "convoke")
    commit(s, made[1], "convoke")
    oid = s.state.rules.object_id(card.id)
    assert oid in s.state.rules.payments  # keyed by the spell on the stack


# 13: undo / redo reproduce the exact payment
def test_undo_redo_reproduce_the_payment(cards):
    s, card, made, _, grave = build(cards, "Treasure Cruise", graveyard=3, pool={"U": 1, "C": 4})
    cast(s, card)
    for g in grave:
        commit(s, g, "delve")
    paid = s.state.model_dump(mode="json")
    rec = record(s, card).model_dump()
    s.undo("p1")  # the last delve click (it completed the payment)
    assert s.state.cards[card.id].zone == "p1:hand" and all(g in zone(s.state, "p1", "graveyard") for g in grave)
    assert s.state.players["p1"].mana == {"U": 1, "C": 4}
    s.redo("p1")
    assert record(s, card).model_dump() == rec
    assert s.state.model_dump(mode="json")["zones"] == paid["zones"]


# 14: save / load (and reconnect) keep the payment, and a half-committed prompt
def test_save_load_keeps_payment_metadata(cards):
    s, card, made, arts, _ = build(cards, "Reverse Engineer", artifacts=3, pool={"U": 2})
    cast(s, card)
    commit(s, arts[0], "improvise")
    commit(s, arts[1], "improvise")
    saved = s.state.model_dump_json()
    s2 = GameSession(GameState.model_validate_json(saved), cards=cards)  # a save, loaded (or a restart)
    d = s2.state.rules.decision
    assert d.display["remaining"] == "{1}" and set(d.display["committed"]) == {arts[0], arts[1]}
    commit(s2, arts[2], "improvise")
    rec = record(s2, card)
    s3 = GameSession(GameState.model_validate_json(s2.state.model_dump_json()), cards=cards)
    assert record(s3, card) == rec and [c.kind for c in rec.contributions] == ["improvise"] * 3
    assert rec.mana_spent == {"U": 2}
    view = s3.view("p1")  # the client never sees the record (nothing hidden could leak through it)
    assert "payments" not in (view.get("rules") or {})


# 15: cancelling restores everything: no partial payment
def test_cancel_restores_everything(cards):
    s, card, made, arts, grave = build(cards, "Stoke the Flames", creatures=[["R"], []], graveyard=2)
    cast(s, card, targets=["p2"])
    commit(s, made[0], "convoke")
    commit(s, made[1], "convoke")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["cancel"])
    assert s.state.cards[card.id].zone == "p1:hand"
    assert not any(s.state.cards[c].tapped for c in made) and s.state.players["p1"].mana == {}
    assert not s.state.rules.payments


def test_cancel_after_delve_puts_nothing_in_exile(cards):
    s, card, _, _, grave = build(cards, "Treasure Cruise", graveyard=4)
    cast(s, card)
    for g in grave:
        commit(s, g, "delve")
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["cancel"])
    assert zone(s.state, "p1", "graveyard") == grave and not zone(s.state, "p1", "exile")


def test_click_again_takes_it_back(cards):
    s, card, made, _, _ = build(cards, "Stoke the Flames", creatures=[["R"], ["R"]])
    cast(s, card, targets=["p2"])
    commit(s, made[0], "convoke")
    assert s.state.rules.decision.display["committed"] == [made[0]]
    commit(s, made[0], "convoke")
    assert s.state.rules.decision.display["committed"] == [] and not s.state.cards[made[0]].tapped


def test_committed_card_cannot_also_tap_for_mana(cards):
    s, card, _, arts, _ = build(cards, "Reverse Engineer", artifacts=2)
    cast(s, card)
    commit(s, arts[0], "improvise")
    with pytest.raises(ActionError, match="already paying part of the cost"):
        act(s, "p1", type="activate_ability", card_id=arts[0], ability=0, mana_choice="U")


def test_forged_contributions_are_validated(cards):
    """A client may send contributions with the cast: every one is checked."""
    s, card, made, arts, grave = build(cards, "Stoke the Flames", creatures=[["R"]], artifacts=1, graveyard=1)
    for bad in ([{"kind": "improvise", "card": arts[0]}],  # Stoke has convoke, not improvise
                [{"kind": "convoke", "card": arts[0]}],  # not a creature
                [{"kind": "convoke", "card": made[0]}, {"kind": "convoke", "card": made[0]}]):
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=card.id, targets=["p2"], contributions=bad)
    act(s, "p1", type="tap", card_ids=[made[0]], tapped=True)
    with pytest.raises(ActionError, match="untapped creature"):
        act(s, "p1", type="cast_spell", card_id=card.id, targets=["p2"], contributions=[{"kind": "convoke", "card": made[0]}])


# Never for other payments: ward, "counter unless its controller pays", activated abilities
def test_not_offered_for_activated_abilities(cards):
    s, card, made, arts, _ = build(cards, "Stoke the Flames", creatures=[["R"]], artifacts=1)
    act(s, "p1", type="create_token", player="p1", token={
        "name": "Pumper", "type_line": "Token Creature — Test", "power": "1", "toughness": "1",
        "text": "{2}: This creature gets +1/+1 until end of turn."})
    pumper = next(c for c in s.state.cards.values() if c.name == "Pumper")
    act(s, "p1", type="activate_ability", card_id=pumper.id, ability=0)
    d = s.state.rules.decision
    assert d.display["kind"] == "tap_mana" and not d.display["convoke"] and not d.display["improvise"]
    with pytest.raises(ActionError, match="Only a spell with convoke"):
        commit(s, made[0], "convoke")
    with pytest.raises(ActionError, match="Only a spell with improvise"):
        commit(s, arts[0], "improvise")


def test_not_usable_without_a_payment(cards):
    s, card, made, _, _ = build(cards, "Stoke the Flames", creatures=[["R"]])
    with pytest.raises(ActionError, match="only pay for the spell you're casting"):
        commit(s, made[0], "convoke")


def test_not_usable_for_counter_unless_or_ward(cards):
    """Ward (702.21a) and "counter … unless its controller pays" open a pay-or-not choice that
    isn't a spell's total cost: convoke can't help pay it."""
    from app.rules.plan import Plan, decide

    s, card, made, _, _ = build(cards, "Stoke the Flames", creatures=[["R"]])
    plan = Plan(s.state, "p1", cards, None)
    decide(plan, player="p1", kind="choose_one", prompt="Pay {1} or it's countered?",
           options=[], resume={"step": "pay_or_sacrifice", "counter": "x", "ctx": {}, "cost": "{1}"})
    s.state.rules.decision = plan.rules.decision
    with pytest.raises(ActionError, match="Only a spell with convoke"):
        commit(s, made[0], "convoke")
