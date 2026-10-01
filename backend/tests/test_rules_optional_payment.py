"""Optional costs paid on resolution (app/rules/optional_payment.py): "You may [cost]. If you do,
…" and "[effect] unless [player] pays [cost]" (CR 118.12, 118.12a). The cost is paid when the
ability resolves; "If you do" checks whether the payer chose to pay (118.12). PAY is offered only
while the whole cost is payable (118.3, 608.2d); paying is all or nothing (601.2h); the choice
(and the objects for each part, e.g. a discard from the hand) is private to the payer; every
scenario checks that replaying the recorded history reproduces the table — also while a payment
prompt is pending."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.rules import optional_payment
from app.rules.scripts import parse_effects
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, named, token
from tests.test_rules_costs_components import artifact, choose, decision, life, mana, use
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def hand(s, pid="p1"):
    return zone(s.state, pid, "hand")


def pay_prompt(s, pid="p1"):
    d = decision(s)
    assert d is not None and d.player == pid and d.kind == "choose_one"
    assert [o.id for o in d.options] == ["pay", "decline"]
    return d


def dump(s):
    """The table (cards, zones, players) without the resolving ability itself (it leaves the
    stack once it has resolved, whatever was paid)."""
    out = s.state.model_dump(mode="json")
    stack = set(out["zones"].get("stack") or [])
    return {"cards": {k: v for k, v in out["cards"].items() if k not in stack},
            "zones": {k: v for k, v in out["zones"].items() if k != "stack"}, "players": out["players"]}


# -- parsing ------------------------------------------------------------------------------------
PAY0 = {"do": "optional_payment", "who": "you", "cost": "{2}", "bind": "pay0"}
IF_DO = {"do": "only_if", "cond": {"succeeded": "pay0"}, "skip": 1}
UNLESS = {"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": 1}
DRAW = {"do": "draw", "who": "you", "n": 1}


@pytest.mark.parametrize(("text", "it", "effects", "target"), [
    ("You may pay {2}. If you do, draw a card.", None, [PAY0, IF_DO, DRAW], None),
    ("You may pay {2}. If you don't, draw a card.", None, [PAY0, UNLESS, DRAW], None),
    ("You may discard a card. If you do, draw a card.", None, [{**PAY0, "cost": "Discard a card"}, IF_DO, DRAW], None),
    ("You may pay 2 life. If you do, draw a card.", None, [{**PAY0, "cost": "Pay 2 life"}, IF_DO, DRAW], None),
    ("You may sacrifice it. If you do, draw a card.", "self", [{**PAY0, "cost": "Sacrifice it"}, IF_DO, DRAW], None),
    ("You may pay {1} and discard a card. If you do, draw a card.", None,
     [{**PAY0, "cost": "{1}, Discard a card"}, IF_DO, DRAW], None),
    ("You may sacrifice another creature. If you do, ~ gets +2/+2 until end of turn.", "self",
     [{**PAY0, "cost": "Sacrifice another creature"}, IF_DO, {"do": "pump", "who": "self", "p": 2, "t": 2}], None),
    ("Target player loses 3 life unless that player pays {2}.", None,
     [{**PAY0, "who": "target"}, UNLESS, {"do": "lose_life", "who": "target", "n": 3}], "player"),
    ("Destroy target creature unless its controller pays 2 life.", None,
     [{**PAY0, "who": "target", "cost": "Pay 2 life"}, UNLESS, {"do": "destroy", "who": "target"}], "creature"),
    ("Return ~ to its owner's hand unless you pay {1}.", None,
     [{**PAY0, "cost": "{1}"}, UNLESS, {"do": "bounce", "who": "self"}], None),
])
def test_parse(text, it, effects, target):
    assert parse_effects(text, it) == (effects, target, False)


def test_two_payments_bind_separately():
    parsed = parse_effects("You may pay {1}. If you do, draw a card. You may pay 2 life. If you do, you gain 3 life.")
    assert parsed is not None
    effects = parsed[0]
    assert [e["do"] for e in effects] == ["optional_payment", "only_if", "draw", "optional_payment", "only_if", "gain_life"]
    assert effects[0]["bind"] == "pay0" and effects[3]["bind"] == "pay1"
    assert effects[1]["cond"] == {"succeeded": "pay0"} and effects[4]["cond"] == {"succeeded": "pay1"}


@pytest.mark.parametrize("text", [
    "You may pay {2}. When you do, it deals 1 damage to any target.",  # (603.12, wave 3R1: "it" names nothing there)
    "You may pay {X}. If you do, draw a card.",
    "You may sacrifice it. If you do, draw a card.",  # "it" isn't this object (the antecedent is unknown)
    "You may tap two untapped creatures you control that share a color. If you do, draw a card.",
    "Draw a card. If you do, draw a card.",  # nothing optional to refer to
    "Each opponent loses 3 life unless they pay {2}.",  # several payers
    "~ deals 3 damage to any target unless its controller pays {2}.",  # "any target" may be a player
    "You may pay {2}. If you do, you may draw a card.",
])
def test_refused(text):
    assert parse_effects(text) is None


def test_cost_text():
    assert optional_payment.cost_text("pay {1}{G}") == "{1}{G}"
    assert optional_payment.cost_text("pay 3 life") == "Pay 3 life"
    assert optional_payment.cost_text("exile a creature card from your graveyard") == "Exile a creature card from your graveyard"
    assert optional_payment.cost_text("remove a +1/+1 counter from ~") == "Remove a +1/+1 counter from ~"
    assert optional_payment.cost_text("pay {1} and 3 life") == "{1}, Pay 3 life"  # (Ripples of Undeath)
    assert optional_payment.cost_text("pay {X}") is None
    assert optional_payment.cost_text("have it fight another creature") is None


# -- pay / decline / can't ------------------------------------------------------------------------
def test_pay_then_the_effect_happens(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may pay {2}. If you do, draw a card.")
    mana(s, C=2)
    before = len(hand(s))
    use(s, relic)
    d = pay_prompt(s)
    assert d.options[0].label == "Pay {2}" and d.source_id == relic.id
    assert "options" not in s.view("p2")["rules"]["decision"]  # (the decision is the payer's)
    assert s.view("p1")["rules"]["decision"]["options"][0]["id"] == "pay"
    choose(s, ["pay"])
    assert len(hand(s)) == before + 1 and s.state.players["p1"].mana == {}
    assert decision(s) is None and s.state.rules.priority == "p1"
    replay_matches(s)


def test_decline_and_nothing_happens(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may pay {2}. If you do, draw a card.")
    mana(s, C=2)
    before = len(hand(s))
    use(s, relic)
    pay_prompt(s)
    choose(s, ["decline"])
    assert len(hand(s)) == before and s.state.players["p1"].mana == {"C": 2}
    assert "didn't pay {2}" in json.dumps(s.view("p2")["log"])
    replay_matches(s)


def test_unpayable_cost_is_not_offered(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may pay {2}. If you do, draw a card.")
    mana(s, C=1)
    before = len(hand(s))
    use(s, relic)  # 118.3 / 608.2d: {2} can't be paid with {C}: no question, the ability just finishes
    assert decision(s) is None and len(hand(s)) == before and s.state.players["p1"].mana == {"C": 1}
    assert "can't pay {2}" in json.dumps(s.view("p2")["log"])
    replay_matches(s)


def test_payment_impossible_when_answered_pays_nothing(cards):
    """The payer chose PAY, but used the artifact to be sacrificed for mana while the prompt was
    open: the cost can't be paid in full any more, so nothing is paid and "if you do" doesn't
    happen (118.3, 601.2h). The table is as it was, apart from the log."""
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may sacrifice another artifact. If you do, draw two cards.")
    trinket = artifact(s, "Trinket", "{T}, Sacrifice this artifact: Add {C}.")
    before = len(hand(s))
    use(s, relic)
    pay_prompt(s)
    act(s, "p1", type="activate_ability", card_id=trinket.id, ability=0)  # (a mana ability, while paying)
    assert trinket.id not in s.state.cards and s.state.players["p1"].mana == {"C": 1}
    table = dump(s)
    choose(s, ["pay"])
    assert dump(s) == table and len(hand(s)) == before and decision(s) is None
    assert "couldn't pay" in json.dumps(s.view("p2")["log"])
    replay_matches(s)


def test_self_tapping_player_taps_mana_while_the_prompt_is_open(cards):
    s = build(cards)
    s.state.rules.prefs_for("p1").payment = "self"
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    relic = artifact(s, "Relic", "{T}: You may pay {G}. If you do, draw a card.")
    before = len(hand(s))
    use(s, relic)
    d = pay_prompt(s)
    assert "tap your mana first" in d.prompt and d.display["pool"] == {}
    with pytest.raises(ActionError, match="Tap your mana first"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    assert decision(s).display["pool"] == {"G": 1}
    choose(s, ["pay"])
    assert len(hand(s)) == before + 1 and s.state.players["p1"].mana == {} and s.state.cards[forest.id].tapped
    replay_matches(s)


# -- each kind of cost -----------------------------------------------------------------------------
def test_pay_life(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may pay 2 life. If you do, draw a card.")
    before = len(hand(s))
    use(s, relic)
    choose(s, ["pay"])
    assert life(s) == 38 and len(hand(s)) == before + 1
    act(s, "p1", type="life", player="p1", delta=-37)  # 119.4: 1 life can't pay 2
    act(s, "p1", type="tap", card_ids=[relic.id], tapped=False)
    use(s, relic)
    assert decision(s) is None and life(s) == 1 and len(hand(s)) == before + 1
    replay_matches(s)


def test_discard_is_chosen_privately(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may discard a card. If you do, draw two cards.")
    while len(hand(s)) < 3:
        act(s, "p1", type="draw", player="p1", count=1)
    before = list(hand(s))
    use(s, relic)
    choose(s, ["pay"])
    d = decision(s)
    assert d.player == "p1" and d.kind == "choose_cards" and {o.id for o in d.options} == set(before)
    assert d.min_choices == d.max_choices == 1
    assert "options" not in s.view("p2")["rules"]["decision"]  # the payer's hand is theirs alone
    assert before[0] not in json.dumps(s.view("p2"))
    replay_matches(s)  # (pending: the choice is part of the table)
    choose(s, [before[0]])
    assert s.state.cards[before[0]].zone == "p1:graveyard" and len(hand(s)) == len(before) - 1 + 2
    replay_matches(s)


def test_sacrifice_with_a_choice(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may sacrifice a creature. If you do, you gain 5 life.")
    bear, wolf = token(s, "p1", "Bear"), token(s, "p1", "Wolf")
    use(s, relic)
    choose(s, ["pay"])
    d = decision(s)
    assert d.kind == "choose_cards" and {o.id for o in d.options} == {bear.id, wolf.id}
    choose(s, [wolf.id])
    assert wolf.id not in s.state.cards and bear.id in s.state.cards and life(s) == 45
    replay_matches(s)


def test_sacrifice_itself(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may sacrifice this artifact. If you do, draw a card.")
    before = len(hand(s))
    use(s, relic)
    pay_prompt(s)
    choose(s, ["pay"])
    assert relic.id not in s.state.cards and len(hand(s)) == before + 1
    replay_matches(s)


def test_tap_an_untapped_creature(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may tap an untapped creature you control. If you do, draw a card.")
    bear, wolf = token(s, "p1", "Bear"), token(s, "p1", "Wolf")
    before = len(hand(s))
    use(s, relic)
    choose(s, ["pay"])
    choose(s, [bear.id])
    assert s.state.cards[bear.id].tapped and not s.state.cards[wolf.id].tapped and len(hand(s)) == before + 1
    replay_matches(s)


def test_remove_counters_from_itself(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may remove a charge counter from this artifact. If you do, draw a card.")
    before = len(hand(s))
    use(s, relic)  # no counter: the option isn't offered
    assert decision(s) is None and len(hand(s)) == before
    act(s, "p1", type="tap", card_ids=[relic.id], tapped=False)
    act(s, "p1", type="counter", card_ids=[relic.id], kind="charge", delta=2)
    use(s, relic)
    choose(s, ["pay"])
    assert s.state.cards[relic.id].counters == {"charge": 1} and len(hand(s)) == before + 1
    replay_matches(s)


def test_exile_from_graveyard(cards):
    s = build(cards, "Grizzly Bears")
    bears = named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    relic = artifact(s, "Relic", "{T}: You may exile a creature card from your graveyard. If you do, you gain 3 life.")
    use(s, relic)
    choose(s, ["pay"])  # (one candidate: no choice to make)
    assert s.state.cards[bears.id].zone == "p1:exile" and life(s) == 43
    replay_matches(s)


def test_mana_and_discard_together(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may pay {1} and discard a card. If you do, draw two cards.")
    while len(hand(s)) < 2:
        act(s, "p1", type="draw", player="p1", count=1)
    use(s, relic)
    assert decision(s) is None  # no mana: not offered (118.3: the whole cost)
    act(s, "p1", type="tap", card_ids=[relic.id], tapped=False)
    mana(s, C=1)
    before = list(hand(s))
    use(s, relic)
    choose(s, ["pay"])
    choose(s, [before[1]])
    assert s.state.players["p1"].mana == {} and s.state.cards[before[1]].zone == "p1:graveyard"
    assert len(hand(s)) == len(before) - 1 + 2
    replay_matches(s)


# -- two payments in one ability; triggers -----------------------------------------------------------
def test_two_payments_in_one_ability(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may pay {1}. If you do, draw a card. You may pay 2 life. If you do, you gain 5 life.")
    mana(s, C=1)
    before = len(hand(s))
    use(s, relic)
    d = pay_prompt(s)
    assert "{1}" in d.prompt
    choose(s, ["decline"])
    d = pay_prompt(s)
    assert "2 life" in d.prompt
    choose(s, ["pay"])
    assert len(hand(s)) == before and life(s) == 43 and s.state.players["p1"].mana == {"C": 1}
    replay_matches(s)


def test_trigger_offers_the_payment(cards):
    s = build(cards)
    while len(hand(s)) < 3:
        act(s, "p1", type="draw", player="p1", count=1)
    before = list(hand(s))
    token(s, "p1", "Watcher", text="Whenever a creature you control enters, you may discard a card. If you do, draw a card.")
    muster = token(s, "p1", "Muster", text="{1}: Create a 1/1 white Soldier creature token.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=muster.id, ability=0)
    pass_until_stack_empty(s)
    pass_until_stack_empty(s)
    pay_prompt(s)
    choose(s, ["pay"])
    choose(s, [before[2]])
    assert s.state.cards[before[2]].zone == "p1:graveyard" and len(hand(s)) == len(before)
    replay_matches(s)


# -- "unless that player pays": the other player decides -------------------------------------------
def test_unless_that_player_pays_the_opponent_decides(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: Target player loses 3 life unless that player pays {2}.")
    mana(s, "p2", C=2)
    use(s, relic, targets=["p2"])
    d = decision(s)
    assert d.player == "p2" and [o.id for o in d.options] == ["pay", "decline"]
    assert "options" not in s.view("p1")["rules"]["decision"]
    replay_matches(s)
    choose(s, ["pay"], pid="p2")
    assert life(s, "p2") == 40 and s.state.players["p2"].mana == {}
    act(s, "p1", type="tap", card_ids=[relic.id], tapped=False)
    mana(s, "p2", C=2)
    use(s, relic, targets=["p2"])
    choose(s, ["decline"], pid="p2")
    assert life(s, "p2") == 37 and s.state.players["p2"].mana == {"C": 2}
    act(s, "p2", type="add_mana", player="p2", mana={"C": -2})
    act(s, "p1", type="tap", card_ids=[relic.id], tapped=False)
    use(s, relic, targets=["p2"])  # p2 can't pay: no question, they lose the life
    assert decision(s) is None and life(s, "p2") == 34
    replay_matches(s)


def test_unless_its_controller_pays(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: Destroy target creature unless its controller pays {1}.")
    ogre = token(s, "p2", "Ogre")
    mana(s, "p2", C=1)
    use(s, relic, targets=[ogre.id])
    d = decision(s)
    assert d.player == "p2"
    choose(s, ["decline"], pid="p2")
    assert ogre.id not in s.state.cards and s.state.players["p2"].mana == {"C": 1}
    replay_matches(s)


def test_history_rebuild_while_pending(cards):
    s = build(cards)
    relic = artifact(s, "Relic", "{T}: You may sacrifice a creature. If you do, draw a card.")
    token(s, "p1", "Bear"), token(s, "p1", "Wolf")
    use(s, relic)
    pay_prompt(s)
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    choose(s, ["pay"])
    assert decision(s).kind == "choose_cards"
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
