"""Wave 110I (session 8): real Oracle text; scenarios check replay and save/load.

* Arcee: "that many" counters = the cast spell's targets that are creatures or Vehicles you control (115.9b, 603.2).
* Shifty Doppelganger: the creature put onto the battlefield is sacrificed at the next end step; if it was, this card returns from exile (118.12).
* Evershrike: returns from the graveyard; an Aura (mana value X or less) from hand enters attached to it (303.4f), else it is exiled (118.12).
* Raiding Party: each player (turn order, 101.4) taps white creatures and chooses up to two Plains per creature; unchosen Plains are destroyed.
* Arsenal Thresher: reveals other artifact cards from hand as it enters (701.20a), a +1/+1 counter for each (614.12); the cards stay in hand.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import activate
from tests.wave9c_kit import build, card_named, mana, pt, put, to_hand
from tests.wave110a_kit import answer
from tests.wave110c_kit import check, make_db

THRESHER = ("As this creature enters, you may reveal any number of other artifact cards from your hand. "
            "This creature enters with a +1/+1 counter on it for each card revealed this way.")
ARCEE = ("Whenever you cast a spell that targets one or more creatures or Vehicles you control, put that many +1/+1 counters on Arcee. Convert Arcee.")
SHIFTY = ("{3}{U}, Exile this creature: You may put a creature card from your hand onto the battlefield. If you do, that creature gains haste until end of turn. "
          "At the beginning of the next end step, sacrifice that creature. If you do, return this card to the battlefield.")
EVER = ("Flying\nThis creature gets +2/+2 for each Aura attached to it.\n{X}{W/B}{W/B}: Return this card from your graveyard to the battlefield. "
        "You may put an Aura card with mana value X or less from your hand onto the battlefield attached to it. If you don't, exile this creature.")
PARTY = ("This enchantment can't be the target of white spells or abilities from white sources.\n"
         "Sacrifice an Orc: Each player may tap any number of untapped white creatures they control. For each creature tapped this way, that player chooses up to two Plains. "
         "Then destroy all Plains that weren't chosen this way by any player.")
EXTRA = [real("Plains", "", 0, "Basic Land \u2014 Plains", "({T}: Add {W}.)", None, ""),
         real("Raiding Party", "{2}{R}", 3, "Enchantment", PARTY, None, "R"),
         real("Probe Orc", "{1}{R}", 2, "Creature \u2014 Orc", "", ("2", "2"), "R"),
         real("Probe Knight", "{1}{W}", 2, "Creature \u2014 Human Knight", "", ("2", "2"), "W"),
         real("Evershrike", "{3}{W/B}{W/B}", 5, "Creature \u2014 Elemental Spirit", EVER, ("2", "2"), "WB"),
         real("Probe Aura", "{1}{W}", 2, "Enchantment \u2014 Aura", "Enchant creature", None, "W"),
         real("Probe Landaura", "{W}", 1, "Enchantment \u2014 Aura", "Enchant land", None, "W"),
         real("Shifty Doppelganger", "{2}{U}", 3, "Creature \u2014 Shapeshifter", SHIFTY, ("1", "1"), "U"),
         real("Arcee", "{1}{R}{W}", 3, "Legendary Artifact Creature \u2014 Robot", ARCEE, ("2", "2"), "RW"),
         real("Probe Pair", "{R}", 1, "Instant", "Two target creatures each get +1/+1 until end of turn.", None, "R"),
         real("Probe Bears", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G"),
         real("Probe Ride", "{2}", 2, "Artifact \u2014 Vehicle", "Crew 1", None, ""),
         real("Probe Pump", "{R}", 1, "Instant", "Target creature gets +1/+1 until end of turn.", None, "R"),
         real("Probe Untap", "{R}", 1, "Instant", "Untap target artifact.", None, "R"),
         real("Arsenal Thresher", "{2}{W/B}{U}", 4, "Artifact Creature — Construct", THRESHER, ("2", "2"), "BUW"),
         real("Probe Gem1", "{1}", 1, "Artifact", "", None, ""), real("Probe Gem2", "{2}", 2, "Artifact", "", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Arsenal Thresher", "Arcee", "Probe Pair", "Shifty Doppelganger", "Evershrike", "Raiding Party"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("reveal", [2, 1, 0])
def test_thresher_counters_per_revealed_artifact(cards, reveal):
    s = build(cards, ["Arsenal Thresher", "Probe Gem1", "Probe Gem2", "Forest"])
    gems = [to_hand(s, "Probe Gem1"), to_hand(s, "Probe Gem2")]
    forest = to_hand(s, "Forest")
    mana(s, W=1, U=1, C=2)
    t = to_hand(s, "Arsenal Thresher")
    act(s, "p1", type="cast_spell", card_id=t.id)
    d = None
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and {o.card_id for o in d.options} >= {g.id for g in gems} and forest.id not in {o.card_id for o in d.options}
    for g in gems[:reveal]:
        act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[next(o.id for o in s.state.rules.decision.options if o.card_id == g.id)])
    if reveal < 2:
        act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["done"])
    answer(s)
    got = s.state.cards[t.id]
    assert got.zone == "p1:battlefield" and got.counters.get("+1/+1", 0) == reveal
    assert all(s.state.cards[g.id].zone == "p1:hand" for g in gems)
    check(s)


def _arcee(cards, spell, targets_of, mine=(), theirs=()):
    s = build(cards, ["Arcee", "Probe Pair", "Probe Bears", "Probe Ride", "Probe Untap", "Probe Pump"], ["Probe Bears"])
    arcee = put(s, "Arcee")
    ours = {n: put(s, n) for n in mine}
    opp = put(s, "Probe Bears", "p2")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, spell).id, targets=(t := targets_of(arcee, ours, opp)), target_counts=[len(t)])
    answer(s)
    return s, arcee


@pytest.mark.parametrize(("spell", "pick", "n"), [
    ("Probe Pair", lambda a, o, p: [a.id, p.id], 1),          # one of mine, one opponent's: only mine counts
    ("Probe Pair", lambda a, o, p: [a.id, o["Probe Bears"].id], 2),
    ("Probe Untap", lambda a, o, p: [o["Probe Ride"].id], 1),  # a Vehicle I control
])
def test_arcee_counts_matching_targets(cards, spell, pick, n):
    s, arcee = _arcee(cards, spell, pick, mine=("Probe Bears", "Probe Ride"))
    assert s.state.cards[arcee.id].counters.get("+1/+1", 0) == n
    check(s)


def test_arcee_ignores_spell_targeting_only_opponents(cards):
    s, arcee = _arcee(cards, "Probe Pump", lambda a, o, p: [p.id], mine=())
    assert s.state.cards[arcee.id].counters.get("+1/+1", 0) == 0


@pytest.mark.parametrize("case", ["sacrificed", "no creature", "creature gone first"])
def test_shifty_swaps_and_returns_after_sacrifice(cards, case):
    s = build(cards, ["Shifty Doppelganger", "Probe Bears"])
    shifty = put(s, "Shifty Doppelganger")
    bears = to_hand(s, "Probe Bears") if case != "no creature" else None
    mana(s, U=1, C=3)
    activate(s, "p1", shifty, "Exile")
    answer(s, bears.id if bears else None)
    assert s.state.cards[shifty.id].zone == "p1:exile"
    if case == "creature gone first":  # nothing left to sacrifice: no "if you do"
        act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "hand"})
    for _ in range(60):  # (the empty end step gives no priority: play on to the next turn)
        d = s.state.rules.decision
        if s.state.turn.number > 1:
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type=d.kind, attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[shifty.id].zone == ("p1:battlefield" if case == "sacrificed" else "p1:exile")
    if case == "sacrificed":
        assert s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize(("aura", "x", "attached"), [("Probe Aura", 2, True), ("Probe Aura", 3, True), ("Probe Aura", 1, False),
                                                      ("Probe Landaura", 1, False), (None, 0, False)])
def test_evershrike_returns_with_an_aura_or_is_exiled(cards, aura, x, attached):
    s = build(cards, ["Evershrike", "Probe Aura", "Probe Landaura"])
    ever = card_named(s, "Evershrike")
    act(s, "p1", type="move", card_ids=[ever.id], to={"zone": "graveyard"})
    a = to_hand(s, aura) if aura else None
    mana(s, W=2 + x)
    activate(s, "p1", ever, "Return", x_value=x)
    answer(s, *([a.id] if a is not None and a.name != "Probe Aura" or x >= 2 else []))  # (no card of mana value X or less: nothing to choose)
    if attached:
        assert s.state.cards[ever.id].zone == "p1:battlefield" and s.state.cards[a.id].attached_to == ever.id
        assert pt(s, "Evershrike") == (4, 4)  # +2/+2 for the Aura attached to it
    else:
        assert s.state.cards[ever.id].zone == "p1:exile"
        assert a is None or s.state.cards[a.id].zone == "p1:hand"
    check(s)



def _put_new(s, name, pid):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library")
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def _party(cards, mine, theirs, picks):
    s = build(cards, ["Raiding Party", "Probe Orc", *["Probe Knight"] * 2, *["Plains"] * 3], ["Probe Knight", "Plains", "Plains"])
    party = put(s, "Raiding Party")
    orc = put(s, "Probe Orc")
    ids = {}
    for who, names in (("p1", mine), ("p2", theirs)):
        for tag, name in names:
            ids[tag] = _put_new(s, name, who)
    activate(s, "p1", party, "Sacrifice")
    for pick in picks:
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[ids[t].id for t in pick])
    answer(s)
    return s, ids, orc, party


def test_raiding_party_destroys_unchosen_plains(cards):
    s, ids, orc, party = _party(cards, [("k1", "Probe Knight"), ("k2", "Probe Knight"), ("a", "Plains"), ("b", "Plains"), ("c", "Plains")],
                                [("k3", "Probe Knight"), ("d", "Plains"), ("e", "Plains")],
                                [["k1"], ["a", "b"], ["k3"], ["e"]])  # p1 taps one Knight, keeps two Plains; p2 taps its Knight, keeps one
    zone = {t: s.state.cards[c.id].zone for t, c in ids.items()}
    assert s.state.cards[orc.id].zone == "p1:graveyard"
    assert zone["a"] == zone["b"] == "p1:battlefield" and zone["e"] == "p2:battlefield"
    assert zone["c"] == "p1:graveyard" and zone["d"] == "p2:graveyard"
    assert s.state.cards[ids["k1"].id].tapped and s.state.cards[ids["k3"].id].tapped and not s.state.cards[ids["k2"].id].tapped
    check(s)


def test_raiding_party_nobody_taps_destroys_every_plains(cards):
    s, ids, orc, party = _party(cards, [("k1", "Probe Knight"), ("a", "Plains")], [("d", "Plains")], [[]])  # (the opponent has no white creature: asked nothing)
    assert s.state.cards[ids["a"].id].zone == "p1:graveyard" and s.state.cards[ids["d"].id].zone == "p2:graveyard"
    assert not s.state.cards[ids["k1"].id].tapped
    check(s)
