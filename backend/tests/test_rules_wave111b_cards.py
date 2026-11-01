"""Wave 111B: Star Trek "if you do" and "instead" clauses, on real Oracle text (Scryfall, 2026-10-30). Every scenario checks the replay and a
save and a load (tests/wave9c_kit.check).

* Creature types of the Star Trek sets (creature_types.py, wave 111E's block: 205.3a, 205.3m at its next update): Borg / Romulan / Officer tokens,
  "Target Klingon", "Klingons and Warriors you control".
* "you may pay / sacrifice …. If you do, …" (118.12): Antagonist Incorporator's granted trigger, In the Pale Moonlight III, Kor, The Promise of Kahless
  ("all other": not the card just sacrificed, 400.7j), U.S.S. Enterprise-C ("for each card discarded this way": the discarded cards, 701.9a).
* Cost sacrifice read as it last existed (608.2h, 112.7a): Gowron. Modes: "If you have no cards in hand, choose one or more instead." (Captain
  Kirk, 603.3c / 700.2a: judged as the ability goes on the stack); "If you control a commander as you cast this spell, you may choose both
  instead." (Collective Override, 601.2b).
* "instead" in a resolution (608.2c): Conquest Mission, Support Mission (the quest counter first, "that creature" the entering one).
* Replacement effects (614.1a, 616.1): counters (M'Benga, Geordi La Forge: only those you put, 122.6a; Optimization Annex: anyone's),
  tokens (Holo-Engineer, every token of yours), draws (Pavel Chekov: random order, 401.4), the graveyard permission's finality counter (Overflow
  Submatrix, 122.6, 702.? finality: exile instead of dying).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, on_field, sandbox, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
from tests.wave53c_kit import combat_step

EXTRA = [
    real("Antagonist Incorporator", "{1}{W}", 2, "Artifact Creature — Borg", "Artifact creatures you control have \"Whenever this creature deals combat damage to a player, you may pay {1}. If you do, create a 1/1 colorless Borg artifact creature token.\"", ("2", "3"), "W"),
    real("Gowron, Eager for Battle", "{2}{B}{R}", 4, "Legendary Creature — Klingon Warrior", "Whenever another creature dies, put a +1/+1 counter on Gowron.\nSacrifice another creature: Gowron gains trample until end of turn. If you sacrificed a Klingon this way, you draw a card and lose 1 life.", ("3", "3"), "BR"),
    real("In the Pale Moonlight", "{3}{B}{B}", 5, "Enchantment — Saga", "(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Each opponent sacrifices a nontoken creature of their choice.\nII — Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nIII — You may sacrifice an artifact or creature. If you do, create two 2/2 black Romulan creature tokens.", None, "B"),
    real("Join the Collective", "{5}{W}{W}", 7, "Sorcery", "Destroy all creatures. Create X 1/1 colorless Borg artifact creature tokens, where X is the number of nonartifact creatures destroyed this way.", None, "W"),
    real("Kor, Cause of Vengeance", "{1}{R}{W}{B}", 4, "Legendary Creature — Klingon Warrior Officer", "Whenever you attack, you may sacrifice another creature. If you do, draw a card, then Klingons and Warriors you control get +2/+2 until end of turn.", ("4", "4"), "BRW"),
    real("Overflow Submatrix", "{2}{B}", 3, "Artifact Creature — Borg", "Once during each of your turns, you may cast an artifact creature spell from your graveyard. If you cast a spell this way, that artifact creature enters with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)", ("3", "3"), "B"),
    real("Pavel Chekov, First Posting", "{2}{G}{U}", 4, "Legendary Creature — Human Pilot", "If you would draw a card, you may instead choose land or nonland and reveal cards from the top of your library until you reveal a card of the chosen kind. Put that card into your hand and put all other cards revealed this way on the bottom of your library in a random order.", ("1", "4"), "GU"),
    real("Test of Identity", "{1}{R}", 2, "Instant", "Choose one —\n• I Am Klingon — Target Klingon gets +1/+1 and gains double strike until end of turn.\n• I Am Starfleet — Discard a card. If you do, draw two cards.", None, "R"),
    real("The Promise of Kahless", "{4}{B}", 5, "Sorcery", "You may sacrifice a Klingon or Warrior. If you do, return all other Klingon and Warrior creature cards from your graveyard to the battlefield.", None, "B"),
    real("U.S.S. Enterprise-C, Time-Tossed", "{5}", 5, "Legendary Artifact — Spacecraft", "When U.S.S. Enterprise-C enters or dies, you may discard your hand. If you do, draw a card for each card discarded this way.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 3+.)\n3+ | Flying", ("6", "6"), ""),
    real("Captain James T. Kirk", "{2}{R}", 3, "Legendary Creature — Human Officer", "Whenever Captain Kirk enters or attacks, choose one. If you have no cards in hand, choose one or more instead.\n• Discard a card, then draw a card.\n• Create a 1/1 red Officer creature token.\n• Creatures you control get +1/+0 until end of turn.", ("2", "2"), "R"),
    real("Collective Override", "{2}{W}{U}", 4, "Instant", "Choose one. If you control a commander as you cast this spell, you may choose both instead.\n• Create a 1/1 colorless Borg artifact creature token for each attacking creature.\n• Draw a card for each attacking creature.", None, "UW"),
    real("Conquest Mission", "{2}{W}", 3, "Enchantment", "Whenever a nontoken artifact you control enters, put a quest counter on this enchantment. Create a 1/1 colorless Borg artifact creature token. If this enchantment has six or more quest counters on it, create two of those tokens instead.", None, "W"),
    real("Dr. Joseph M'Benga", "{2}{G}{G}", 4, "Legendary Creature — Human Doctor", "Other creatures you control with counters on them have hexproof.\nIf you would put one or more counters on a creature you control, put twice that many of each of those kinds of counters on that creature instead.", ("3", "3"), "G"),
    real("Holo-Engineer", "{2}{G}{G}", 4, "Creature — Human Artificer", "When this creature enters, create a 3/3 colorless Illusion artifact creature token.\nIf one or more tokens would be created under your control, that many 3/3 colorless Illusion artifact creature tokens are created instead.", ("3", "3"), "G"),
    real("Lt. Cmdr. Geordi La Forge", "{2}{U}", 3, "Legendary Creature — Human Artificer", "If you would put one or more charge counters on an artifact you control, put twice that many charge counters on that artifact instead.", ("3", "2"), "U"),
    real("Optimization Annex", "{1}{U}", 2, "Artifact Creature — Borg", "If one or more charge counters would be put on an artifact you control, that many plus one charge counters are put on it instead.", ("1", "3"), "U"),
    real("Support Mission", "{2}{G}", 3, "Enchantment", "Whenever a creature you control enters, put a quest counter on this enchantment. Put a +1/+1 counter on that creature. If this enchantment has five or more quest counters on it, instead put two +1/+1 counters on that creature.", None, "G"),
    real("B'Elanna Torres, Scrapper", "{1}{U}{R}", 3, "Legendary Creature — Klingon Human Artificer", "Vigilance, trample\n{2}, {T}: Surveil 2, then you may reveal the top card of your library. Draw a card if it's an artifact card. If you don't draw a card this way, put two +1/+1 counters on B'Elanna Torres.", ("2", "2"), "RU"),
    real("Guinan, Ancient Advisor", "{2}{W}", 3, "Legendary Creature — El-Aurian Advisor", "{1}, {T}: Put a +1/+1 counter on each creature you control that entered this turn. If you put two or more +1/+1 counters on creatures this way, draw a card.", ("1", "4"), "W"),
    real("Salt Vampire", "{1}{B}", 2, "Creature — Vampire Shapeshifter", "Lifelink\nWhen this creature enters, look at target opponent's hand. You may choose a nonland card from it. If you do, that player exiles that card, then draws a card.", ("2", "2"), "B"),
    real("Peace in Our Time", "{3}{W}", 4, "Enchantment", "At the beginning of combat on each player's turn, that player may draw a card. If they do, they can't attack this turn and you put a peace counter on this enchantment.\nAt the beginning of your upkeep, if this enchantment has twelve or more peace counters on it, you win the game.", None, "W"),
    real("Cmdr. Troi, Outgoing Empath", "{2}{U}{R}", 4, "Legendary Creature — Betazoid Human Advisor", "Vigilance\n{T}: Target opponent whose turn it is may cast a spell from their hand without paying its mana cost. If they do, you copy that spell. You may choose new targets for the copy. If they don't, you draw a card.", ("3", "3"), "RU"),
    real("Dr. McCoy, Surly Surgeon", "{2}{W}{W}", 4, "Legendary Creature — Human Doctor", "When Dr. McCoy enters, put a +1/+1 counter on another target creature you control.\nIf another creature you control with a +1/+1 counter on it would be destroyed, instead remove all +1/+1 counters from it and all damage already dealt to it is healed.", ("2", "2"), "W"),
    real("Dominion Saboteur", "{4}{U}", 5, "Creature — Shapeshifter", "You may have this creature enter as a copy of any artifact or creature on the battlefield, except it isn't legendary. If you do, it enters with additional counters on it equal to the same number and kinds of counters the copied permanent has on it.", ("3", "3"), "U"),
    real("Sarek, Federation Ambassador", "{1}{G}{W}{U}", 4, "Legendary Creature — Vulcan Advisor", "Federation — At the beginning of combat on your turn, draw a card for every five creature types among non-Borg creatures you control. If you draw three or more cards this way, put two +1/+1 counters on each creature you control.", ("0", "5"), "GUW"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [  # (helpers: plain cards of the types the scenarios need)
    real("Test Klingon 111B", "{1}{B}", 2, "Creature — Klingon Soldier", "", ("2", "2"), "B"),
    real("Test Warrior 111B", "{1}{B}", 2, "Creature — Human Warrior", "", ("2", "2"), "B"),
    real("Test Vulcan 111B", "{1}{B}", 2, "Creature — Vulcan Scientist", "", ("1", "1"), "B"),
    real("Test Drone 111B", "{2}", 2, "Artifact Creature — Drone", "", ("2", "2"), ""),
    real("Test Battery 111B", "{1}", 1, "Artifact", "{T}: Put a charge counter on this artifact.", None, ""),
    real("Test Charger 111B", "{U}", 1, "Instant", "Put two charge counters on target artifact.", None, "U"),
    real("Test Boost 111B", "{G}", 1, "Instant", "Put a +1/+1 counter on target creature.", None, "G"),
]


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


# -- helpers --------------------------------------------------------------------------------------------------------------------------------
def play(s, done=None, pick=None, limit=200):
    """Pass priority until ``done(s)`` (or, without it, until the stack is empty and nothing is asked); a decision is answered with
    ``pick(d)`` (option ids) when it returns some, else with its first options. Attackers and blockers: none."""
    for _ in range(limit):
        d = s.state.rules.decision
        if done is not None and done(s):
            return
        if done is None and d is None and not s.state.zones.get("stack"):
            return
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            got = pick(d) if pick is not None else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=got if got is not None else [o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never settled")


def attack(s, attackers, target="p2", pid="p1"):
    act(s, pid, type="declare_attackers", attackers=[{"card_id": c.id, "target": target} for c in attackers])


def opts(d):
    return [o.id for o in d.options]


def payer(pay):
    """Answers "you may pay …?" with yes or no; other decisions with their first options."""
    def pick(d):
        if "pay" in opts(d) and "decline" in opts(d):
            return ["pay" if pay else "decline"]
        return None
    return pick


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


def hand(s, pid="p1"):
    return list(s.state.zones.get(f"{pid}:hand", []))


def ptof(s, c):
    from app.rules import sba
    from app.rules.plan import Plan

    card = s.state.cards[c.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(card)
    return sba.power(card, ch), sba.toughness(card, ch)


def keywords(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords


# -- Antagonist Incorporator ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pay", [True, False])
def test_incorporator_artifact_creatures_dealing_combat_damage_may_pay_for_a_borg(cards, pay):
    s = sandbox(cards, "Antagonist Incorporator")
    inc = on_field(s, "Antagonist Incorporator")
    drone = creature(s, "p1", "Drone", "1/1", type_line="Token Artifact Creature — Drone")
    bear = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    combat_step(s)
    attack(s, [inc, drone, bear])
    play(s, lambda s: s.state.turn.phase == "combat_damage" and bool(s.state.zones.get("stack")))
    mana(s, C=2)  # (both triggers on the stack: {1} for each, 118.3 — the payment is offered only while it can be made)
    play(s, lambda s: s.state.turn.phase == "main2", pick=payer(pay))
    assert life(s, "p2") == 40 - 5
    borgs = tokens(s, "Borg")
    assert len(borgs) == (2 if pay else 0)  # the Incorporator's and the Drone's (an artifact creature), never the Bear's
    if pay:
        from app.rules.plan import Plan

        ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[borgs[0].id])
        assert ch.types >= {"Artifact", "Creature"} and ch.subtypes == {"Borg"} and not ch.colors
    check(s)


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def zone(s, c):
    return s.state.cards[c.id].zone


def picks(*rules):
    """A decision picker from (predicate on the option ids, answer) pairs: the first rule that applies answers."""
    def pick(d):
        for when, ids in rules:
            if when(opts(d)):
                return ids
        return None
    return pick


# -- In the Pale Moonlight -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pay", [True, False])
def test_pale_moonlight_three_sacrifice_for_two_romulans(cards, pay):
    s = build(cards, ["In the Pale Moonlight"])
    saga = put(s, "In the Pale Moonlight")
    play(s)
    act(s, "p1", type="set_counter", card_id=saga.id, kind="lore", value=2)  # (set by hand: chapter III next)
    bear = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    play(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack") and s.state.rules.decision is None,
         pick=picks((lambda o: "pay" in o, ["pay" if pay else "decline"]), (lambda o: bear.id in o, [bear.id])))
    romulans = tokens(s, "Romulan")
    assert len(romulans) == (2 if pay else 0) and (bear.id in s.state.cards and zone(s, bear) == "p1:battlefield") != pay
    if pay:
        assert ptof(s, romulans[0]) == (2, 2)
    assert zone(s, saga) == "p1:graveyard"  # (after III: 714.4)
    check(s)


# -- Join the Collective -------------------------------------------------------------------------------------------------------------------
def test_join_the_collective_counts_the_nonartifact_creatures_destroyed(cards):
    s = build(cards, ["Join the Collective"])
    creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    creature(s, "p2", "Wolf", "2/2", type_line="Token Creature — Wolf")
    creature(s, "p1", "Drone", "1/1", type_line="Token Artifact Creature — Drone")  # destroyed, but an artifact
    wall = creature(s, "p2", "Wall", "0/4", type_line="Token Creature — Wall", text="Indestructible")  # not destroyed
    mana(s, W=2, C=5)
    cast(s, "Join the Collective")
    play(s)
    assert len(tokens(s, "Borg")) == 2 and not tokens(s, "Borg", "p2")
    assert zone(s, wall) == "p2:battlefield" and not tokens(s, "Bear") and not tokens(s, "Drone")
    check(s)


# -- Kor, Cause of Vengeance ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pay", [True, False])
def test_kor_sacrifice_draws_then_pumps_klingons_and_warriors(cards, pay):
    s = sandbox(cards, "Kor, Cause of Vengeance")
    kor = on_field(s, "Kor, Cause of Vengeance")
    warrior = creature(s, "p1", "Grunt", "2/2", type_line="Token Creature — Human Warrior")
    vulcan = creature(s, "p1", "Tuvok", "1/1", type_line="Token Creature — Vulcan")
    bear = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    combat_step(s)
    held = len(hand(s))
    attack(s, [kor])
    play(s, pick=picks((lambda o: "pay" in o, ["pay" if pay else "decline"]), (lambda o: bear.id in o, [bear.id])))
    assert len(hand(s)) == held + pay and (bear.id in s.state.cards) != pay
    assert ptof(s, kor) == ((6, 6) if pay else (4, 4)) and ptof(s, warrior) == ((4, 4) if pay else (2, 2)) and ptof(s, vulcan) == (1, 1)
    check(s)


# -- Gowron, Eager for Battle --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("klingon", [True, False])
def test_gowron_draws_and_loses_life_only_for_a_sacrificed_klingon(cards, klingon):
    s = build(cards, ["Gowron, Eager for Battle"])
    gowron = put(s, "Gowron, Eager for Battle")
    play(s)
    fodder = creature(s, "p1", "Fodder", "1/1", type_line="Token Creature — " + ("Klingon" if klingon else "Bear"))
    held = len(hand(s))
    act(s, "p1", type="activate_ability", card_id=gowron.id, ability=1, cost_choices=[{"component": 0, "cards": [fodder.id]}])
    play(s)
    assert "trample" in keywords(s, gowron) and ptof(s, gowron) == (4, 4)  # (and its other ability: a creature died)
    assert len(hand(s)) == held + klingon and life(s) == 40 - klingon
    check(s)


# -- Test of Identity ----------------------------------------------------------------------------------------------------------------------
def test_identity_klingon_mode_pumps_a_klingon_only(cards):
    s = build(cards, ["Test of Identity"])
    worf = creature(s, "p1", "Worf", "2/2", type_line="Token Creature — Klingon Warrior")
    bear = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    mana(s, R=1, C=1)
    with pytest.raises(ActionError):
        cast(s, "Test of Identity", [bear.id], modes=[0])
    cast(s, "Test of Identity", [worf.id], modes=[0])
    play(s)
    assert ptof(s, worf) == (3, 3) and "double strike" in keywords(s, worf)
    check(s)


@pytest.mark.parametrize("discard", [True, False])
def test_identity_starfleet_mode_draws_two_only_after_a_discard(cards, discard):
    s = build(cards, ["Test of Identity", "Opt"])
    assert not hand(s)  # (the table starts with empty hands)
    if discard:
        to_hand(s, "Opt")
    mana(s, R=1, C=1)
    cast(s, "Test of Identity", modes=[1])
    play(s)
    assert len(hand(s)) == (2 if discard else 0)
    assert (zone(s, card_named(s, "Opt")) == "p1:graveyard") == discard
    check(s)


# -- The Promise of Kahless ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pay", [True, False])
def test_promise_of_kahless_returns_the_other_klingons_and_warriors(cards, pay):
    s = build(cards, ["The Promise of Kahless", "Test Klingon 111B", "Test Warrior 111B", "Test Vulcan 111B", "Gowron, Eager for Battle"])
    klingon = put(s, "Test Klingon 111B")
    play(s)
    gone = [card_named(s, n) for n in ("Test Warrior 111B", "Test Vulcan 111B", "Gowron, Eager for Battle")]
    act(s, "p1", type="move", card_ids=[c.id for c in gone], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1, C=4)
    cast(s, "The Promise of Kahless")
    play(s, pick=picks((lambda o: "pay" in o, ["pay" if pay else "decline"])))
    warrior, vulcan, gowron = gone
    assert zone(s, klingon) == ("p1:graveyard" if pay else "p1:battlefield")  # (sacrificed, then not returned: "all other")
    assert zone(s, warrior) == zone(s, gowron) == ("p1:battlefield" if pay else "p1:graveyard")
    assert zone(s, vulcan) == "p1:graveyard"
    check(s)


# -- U.S.S. Enterprise-C, Time-Tossed ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pay", [True, False])
def test_enterprise_c_discards_the_hand_and_draws_that_many(cards, pay):
    s = build(cards, ["U.S.S. Enterprise-C, Time-Tossed", "Opt", "Lightning Bolt", "Counterspell"])
    assert not hand(s)  # (the table starts with empty hands)
    kept = [to_hand(s, n) for n in ("Opt", "Lightning Bolt", "Counterspell")]
    mana(s, C=5)
    cast(s, "U.S.S. Enterprise-C, Time-Tossed")
    play(s, pick=picks((lambda o: "pay" in o, ["pay" if pay else "decline"])))
    assert len(hand(s)) == 3
    assert all(zone(s, c) == ("p1:graveyard" if pay else "p1:hand") for c in kept)
    check(s)


# -- Captain James T. Kirk -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("empty", [True, False])
def test_kirk_chooses_one_or_more_modes_with_no_cards_in_hand(cards, empty):
    s = build(cards, ["Captain James T. Kirk", "Opt"])
    if not empty:
        to_hand(s, "Opt")
    mana(s, R=1, C=2)
    kirk = cast(s, "Captain James T. Kirk")
    play(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_cards")
    d = s.state.rules.decision
    assert (d.min_choices, d.max_choices) == ((1, 3) if empty else (1, 1))  # (judged as the trigger is put on the stack: 603.3c)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=opts(d) if empty else [opts(d)[1]])
    play(s)
    officers = tokens(s, "Officer")
    assert len(officers) == 1 and ptof(s, officers[0]) == ((2, 1) if empty else (1, 1))  # (in printed order: the token, then +1/+0)
    assert ptof(s, kirk) == ((3, 2) if empty else (2, 2))
    assert len(hand(s)) == (1 if empty else 1)  # (no card to discard, then a card drawn; or the Opt kept)
    check(s)


# -- Collective Override -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("commander", [True, False])
def test_collective_override_both_modes_while_you_control_a_commander(cards, commander):
    from tests.wave53c_kit import priority_to

    s = sandbox(cards, "Collective Override")
    if commander:
        on_field(s, "Krenko, Mob Boss")
    a = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    b = creature(s, "p1", "Wolf", "2/2", type_line="Token Creature — Wolf")
    combat_step(s)
    attack(s, [a, b])
    priority_to(s, "p1")
    held = len(hand(s))
    mana(s, W=1, U=1, C=2)
    if not commander:
        with pytest.raises(ActionError):
            cast(s, "Collective Override", modes=[0, 1])
    cast(s, "Collective Override", modes=[0, 1] if commander else [0])
    play(s)
    assert len(tokens(s, "Borg")) == 2  # (one for each attacking creature)
    assert len(hand(s)) == held + (2 if commander else 0)  # (a card for each attacking creature)
    check(s)


# -- Conquest Mission / Support Mission ----------------------------------------------------------------------------------------------------
def test_conquest_mission_two_borgs_from_the_sixth_quest_counter(cards):
    s = build(cards, ["Conquest Mission", "Test Drone 111B", "Sol Ring"])
    mission = put(s, "Conquest Mission")
    play(s)
    mana(s, C=2)
    cast(s, "Test Drone 111B")
    play(s)
    assert s.state.cards[mission.id].counters.get("quest") == 1 and len(tokens(s, "Borg")) == 1  # (the Borg token is no nontoken artifact)
    act(s, "p1", type="set_counter", card_id=mission.id, kind="quest", value=5)
    mana(s, C=1)
    cast(s, "Sol Ring")
    play(s)
    assert s.state.cards[mission.id].counters.get("quest") == 6 and len(tokens(s, "Borg")) == 3
    check(s)


def test_support_mission_counter_on_the_entering_creature_two_from_the_fifth_quest_counter(cards):
    s = build(cards, ["Support Mission", "Grizzly Bears", "Test Klingon 111B"])
    mission = put(s, "Support Mission")
    play(s)
    mana(s, G=1, C=1)
    bears = cast(s, "Grizzly Bears")
    play(s)
    assert s.state.cards[mission.id].counters.get("quest") == 1 and s.state.cards[bears.id].counters.get("+1/+1") == 1
    assert not s.state.cards[mission.id].counters.get("+1/+1")
    act(s, "p1", type="set_counter", card_id=mission.id, kind="quest", value=4)
    mana(s, B=1, C=1)
    klingon = cast(s, "Test Klingon 111B")
    play(s)
    assert s.state.cards[mission.id].counters.get("quest") == 5 and s.state.cards[klingon.id].counters.get("+1/+1") == 2
    assert s.state.cards[bears.id].counters.get("+1/+1") == 1
    check(s)


# -- counter replacements ------------------------------------------------------------------------------------------------------------------
def to_bob(s):
    """Bob gets priority in Alice's main phase (Alice passes with an empty stack)."""
    act(s, "p2", type="set_stops", own=["main1"], others=["main1"], smart_pass=False)
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"


def test_mbenga_doubles_the_counters_you_put_on_your_creatures(cards):
    s = build(cards, ["Dr. Joseph M'Benga", "Test Boost 111B"], ["Grizzly Bears"])
    mbenga = put(s, "Dr. Joseph M'Benga")
    play(s)
    bear = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    wolf = creature(s, "p2", "Wolf", "2/2", type_line="Token Creature — Wolf")
    mana(s, G=1)
    cast(s, "Test Boost 111B", [bear.id])
    play(s)
    assert s.state.cards[bear.id].counters.get("+1/+1") == 2 and "hexproof" in keywords(s, bear) and "hexproof" not in keywords(s, mbenga)
    act(s, "p1", type="move", card_ids=[card_named(s, "Test Boost 111B").id], to={"player": "p1", "zone": "hand"})
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Test Boost 111B").id, targets=[wolf.id])
    play(s)
    assert s.state.cards[wolf.id].counters.get("+1/+1") == 1  # (not a creature you control)
    check(s)


@pytest.mark.parametrize("name, mine, theirs", [("Lt. Cmdr. Geordi La Forge", 2, 2), ("Optimization Annex", 2, 3)])
def test_charge_counter_replacements(cards, name, mine, theirs):
    """Geordi: only the charge counters you put are doubled (122.6a); Optimization Annex: one more on any put on your artifact."""
    s = build(cards, [name, "Test Battery 111B"], ["Test Charger 111B"])
    put(s, name)
    battery = put(s, "Test Battery 111B")
    play(s)
    act(s, "p1", type="activate_ability", card_id=battery.id, ability=0)
    play(s)
    assert s.state.cards[battery.id].counters.get("charge") == mine
    to_bob(s)
    mana(s, "p2", U=1)
    cast(s, "Test Charger 111B", [battery.id], pid="p2")
    play(s)
    assert s.state.cards[battery.id].counters.get("charge") == mine + theirs
    check(s)


# -- Holo-Engineer -------------------------------------------------------------------------------------------------------------------------
def test_holo_engineer_turns_every_token_of_yours_into_illusions(cards):
    s = build(cards, ["Holo-Engineer", "Raise the Alarm"], ["Raise the Alarm"])
    mana(s, G=2, C=2)
    cast(s, "Holo-Engineer")
    play(s)
    assert len(tokens(s, "Illusion")) == 1
    mana(s, W=1, C=1)
    cast(s, "Raise the Alarm")
    play(s)
    illusions = tokens(s, "Illusion")
    assert len(illusions) == 3 and not tokens(s, "Soldier") and all(ptof(s, c) == (3, 3) for c in illusions)
    to_bob(s)
    mana(s, "p2", W=1, C=1)
    cast(s, "Raise the Alarm", pid="p2")
    play(s)
    assert len(tokens(s, "Soldier", "p2")) == 2  # (only tokens created under your control)
    check(s)


# -- Pavel Chekov, First Posting -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("instead", [True, False])
def test_pavel_chekov_may_reveal_until_the_chosen_kind_instead_of_drawing(cards, instead):
    s = build(cards, ["Pavel Chekov, First Posting", "Opt", "Lightning Bolt"])
    put(s, "Pavel Chekov, First Posting")
    play(s)
    bolt = card_named(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "library"}, position="top")
    forests = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:2]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, U=1)
    cast(s, "Opt")
    seen = []

    def pick(d):
        seen.append((d.kind, opts(d)))
        if "nonland" in opts(d):
            return ["nonland"]
        if "decline" in opts(d) and "o0" in opts(d):  # (616.1: the replacement is optional, "you may instead")
            return ["o0" if instead else "decline"]
        return None
    play(s, pick=pick)
    lib = s.state.zones["p1:library"]
    if instead:
        assert zone(s, bolt) == "p1:hand" and set(lib[-2:]) == set(forests)  # (the revealed lands on the bottom)
    else:
        drawn = [s.state.cards[c].name for c in hand(s)]
        assert drawn == ["Forest"] and zone(s, bolt) == "p1:library"  # (a plain draw: the top card after the scry)
        assert not any(k == "choose_one" and "nonland" in o for k, o in seen)
    check(s)


# -- Overflow Submatrix --------------------------------------------------------------------------------------------------------------------
def test_overflow_submatrix_one_artifact_creature_from_the_graveyard_with_a_finality_counter(cards):
    s = build(cards, ["Overflow Submatrix", "Test Drone 111B", "Perilous Myr", "Grizzly Bears", "Murder"])
    put(s, "Overflow Submatrix")
    play(s)
    drone, myr, bears = (card_named(s, n) for n in ("Test Drone 111B", "Perilous Myr", "Grizzly Bears"))
    act(s, "p1", type="move", card_ids=[drone.id, myr.id, bears.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):  # (not an artifact creature spell)
        act(s, "p1", type="cast_spell", card_id=bears.id)
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=drone.id)
    play(s)
    assert zone(s, drone) == "p1:battlefield" and s.state.cards[drone.id].counters.get("finality") == 1
    mana(s, C=2)
    with pytest.raises(ActionError):  # (once during each of your turns)
        act(s, "p1", type="cast_spell", card_id=myr.id)
    mana(s, B=2, C=1)
    cast(s, "Murder", [drone.id])
    play(s)
    assert zone(s, drone) == "p1:exile"  # (a finality counter: exiled instead of dying)
    check(s)


# -- B'Elanna Torres, Scrapper -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("top, reveal, draws", [("Test Drone 111B", True, True), ("Test Drone 111B", False, False), ("Opt", True, False)])
def test_belanna_draws_a_revealed_artifact_card_else_two_counters(cards, top, reveal, draws):
    from tests.wave53c_kit import main_step

    s = sandbox(cards, "B'Elanna Torres, Scrapper", "Test Drone 111B", "Opt")
    belanna = on_field(s, "B'Elanna Torres, Scrapper")
    card = card_named(s, top)
    act(s, "p1", type="move", card_ids=[card.id], to={"player": "p1", "zone": "library"}, position="top")
    main_step(s)
    held = len(hand(s))
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=belanna.id, ability=1)
    def pick(d):
        if card.id in opts(d) and d.min_choices == 0:
            return []  # (surveil: both stay on top)
        if "yes" in opts(d) and "no" in opts(d):
            return ["yes" if reveal else "no"]
        return None
    play(s, pick=pick)
    assert (zone(s, card) == "p1:hand") == draws and len(hand(s)) == held + draws  # (surveil kept both on top: the card was the top one)
    assert s.state.cards[belanna.id].counters.get("+1/+1", 0) == (0 if draws else 2)
    check(s)


# -- Guinan, Ancient Advisor ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("entered, mbenga, draws", [(1, False, False), (2, False, True), (1, True, True)])
def test_guinan_draws_after_two_or_more_counters_put(cards, entered, mbenga, draws):
    """"two or more +1/+1 counters": the counters put, as M'Benga's replacement puts them (614.6), on the creatures that entered this turn."""
    s = sandbox(cards, "Guinan, Ancient Advisor", "Dr. Joseph M'Benga")
    guinan = on_field(s, "Guinan, Ancient Advisor")
    if mbenga:
        on_field(s, "Dr. Joseph M'Benga")
    old = creature(s, "p1", "Veteran", "2/2", type_line="Token Creature — Soldier")
    from tests.game_helpers import turn_on

    turn_on(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.priority == "p1" and not s.state.zones.get("stack"))
    fresh = [creature(s, "p1", f"Recruit {i}", "1/1", type_line="Token Creature — Soldier") for i in range(entered)]
    held = len(hand(s))
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=guinan.id, ability=0)
    play(s)
    assert [s.state.cards[c.id].counters.get("+1/+1", 0) for c in fresh] == [2 if mbenga else 1] * entered
    assert not s.state.cards[old.id].counters.get("+1/+1") and not s.state.cards[guinan.id].counters.get("+1/+1")  # (not this turn)
    assert len(hand(s)) == held + draws
    check(s)


# -- Salt Vampire --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("choose", [True, False])
def test_salt_vampire_the_opponent_exiles_the_chosen_card_then_draws(cards, choose):
    from tests.wave53c_kit import main_step

    s = sandbox(cards, "Salt Vampire", p2=("Opt",), players=3)
    opt = card_named(s, "Opt", "p2")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[opt.id, forest.id], to={"player": "p2", "zone": "hand"})
    main_step(s)
    bob, carol = len(hand(s, "p2")), len(hand(s, "p3"))
    mana(s, B=1, C=1)
    cast(s, "Salt Vampire")
    seen = []

    def pick(d):
        seen.append(opts(d))
        if "p2" in opts(d):
            return ["p2"]
        if opt.id in opts(d):
            assert forest.id not in opts(d)  # (a nonland card)
            return [opt.id] if choose else [o for o in opts(d) if o != opt.id][:1] or []
        return None
    play(s, pick=pick)
    assert zone(s, opt) == ("p2:exile" if choose else "p2:hand") and zone(s, forest) == "p2:hand"
    assert len(hand(s, "p2")) == bob - choose + choose and len(hand(s, "p3")) == carol
    check(s)


# -- Peace in Our Time ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("draw", [True, False])
def test_peace_in_our_time_a_draw_means_no_attack_and_a_peace_counter(cards, draw):
    s = sandbox(cards, "Peace in Our Time")
    peace = on_field(s, "Peace in Our Time")
    bear = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    held = len(hand(s))
    combat_step(s)

    def asked(s):
        d = s.state.rules.decision
        return (d is not None and d.kind == "declare_attackers") or (s.state.turn.phase != "begin_combat" and not s.state.zones.get("stack") and d is None)
    play(s, asked, pick=picks((lambda o: "pay" in o, ["pay" if draw else "decline"])))
    assert len(hand(s)) == held + draw and s.state.cards[peace.id].counters.get("peace", 0) == draw
    if draw:
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            with pytest.raises(ActionError):  # (they can't attack this turn)
                attack(s, [bear])
            attack(s, [])
        assert not s.state.cards[bear.id].is_attacking and s.state.turn.number == 1
    else:
        attack(s, [bear])
        assert s.state.cards[bear.id].is_attacking
    check(s)


def test_peace_in_our_time_on_an_opponents_turn_that_player_chooses_and_you_get_the_counter(cards):
    """Three players: on Bob's turn Bob is asked; he draws, his creatures can't attack, and Alice (the enchantment's controller) puts the counter."""
    s = sandbox(cards, "Peace in Our Time", players=3)
    peace = on_field(s, "Peace in Our Time")
    wolf = creature(s, "p2", "Wolf", "2/2", type_line="Token Creature \u2014 Wolf")
    carol = len(hand(s, "p3"))
    combat_step(s)
    asked = []

    def pick(d):
        if "pay" in opts(d):
            asked.append((s.state.turn.number, d.player))
            return ["pay"] if d.player == "p2" else ["decline"]
        return None
    play(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"), pick=pick)
    bob = len(hand(s, "p2"))
    play(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase not in ("main1", "begin_combat") and not s.state.zones.get("stack")
         and (s.state.rules.decision is None or s.state.rules.decision.kind == "declare_attackers"), pick=pick)
    assert asked == [(1, "p1"), (2, "p2")] and len(hand(s, "p2")) == bob + 1 and len(hand(s, "p3")) == carol
    assert s.state.cards[peace.id].counters.get("peace", 0) == 1 and s.state.cards[peace.id].controller == "p1"
    d = s.state.rules.decision
    if d is not None and d.kind == "declare_attackers":
        with pytest.raises(ActionError):  # (Bob can't attack this turn)
            act(s, "p2", type="declare_attackers", attackers=[{"card_id": wolf.id, "target": "p1"}])
    assert not s.state.cards[wolf.id].is_attacking
    check(s)


# -- Sarek, Federation Ambassador ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("more, draws", [(True, 3), (False, 1)])
def test_sarek_draws_per_five_creature_types_of_non_borg_creatures(cards, more, draws):
    s = sandbox(cards, "Sarek, Federation Ambassador")
    sarek = on_field(s, "Sarek, Federation Ambassador")  # Vulcan Advisor
    a = creature(s, "p1", "Crew", "1/1", type_line="Token Creature — Human Soldier Wizard Cleric Rogue Warrior")  # 2 + 6 = 8 types
    creature(s, "p1", "Drone", "1/1", type_line="Token Creature — Borg Elf Druid Shaman Knight Monk Pirate Ninja")  # a Borg: not counted
    if more:
        creature(s, "p1", "Away Team", "1/1", type_line="Token Creature — Elf Druid Shaman Knight Monk Pirate Ninja")  # 15 types
    held = len(hand(s))
    combat_step(s)
    play(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    assert len(hand(s)) == held + draws
    assert s.state.cards[sarek.id].counters.get("+1/+1", 0) == s.state.cards[a.id].counters.get("+1/+1", 0) == (2 if draws >= 3 else 0)
    check(s)


# -- Dominion Saboteur ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("copy", [True, False])
def test_dominion_saboteur_copies_a_nonlegendary_gowron_with_its_counters(cards, copy):
    s = build(cards, ["Dominion Saboteur"], ["Gowron, Eager for Battle"])
    gowron = put(s, "Gowron, Eager for Battle", "p2")
    play(s)
    act(s, "p2", type="counter", card_ids=[gowron.id], kind="+1/+1", delta=2)
    act(s, "p2", type="counter", card_ids=[gowron.id], kind="shield", delta=1)
    mana(s, U=1, C=4)
    sab = cast(s, "Dominion Saboteur")
    play(s, pick=picks((lambda o: gowron.id in o, [gowron.id] if copy else ["none"])))
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[sab.id])
    assert zone(s, sab) == "p1:battlefield" and zone(s, gowron) == "p2:battlefield"
    if copy:
        assert ch.name == "Gowron, Eager for Battle" and "Legendary" not in ch.supertypes  # (except it isn't legendary)
        assert s.state.cards[sab.id].counters == {"+1/+1": 2, "shield": 1} and ptof(s, sab) == (5, 5)
    else:
        assert ch.name == "Dominion Saboteur" and not s.state.cards[sab.id].counters and ptof(s, sab) == (3, 3)
    check(s)


# -- Dr. McCoy, Surly Surgeon --------------------------------------------------------------------------------------------------------------
def mccoy_table(cards):
    s = build(cards, ["Dr. McCoy, Surly Surgeon", "Murder", "Lightning Bolt"], ["Murder"])
    mccoy = put(s, "Dr. McCoy, Surly Surgeon")
    play(s)
    return s, mccoy


@pytest.mark.parametrize("who, counter, survives", [("p1", True, True), ("p1", False, False), ("p2", True, False)])
def test_mccoy_a_destroyed_creature_of_yours_with_a_counter_loses_its_counters_instead(cards, who, counter, survives):
    s, _ = mccoy_table(cards)
    bear = creature(s, who, "Bear", "2/2", type_line="Token Creature — Bear")
    if counter:
        act(s, who, type="counter", card_ids=[bear.id], kind="+1/+1", delta=2)
    mana(s, B=2, C=1)
    cast(s, "Murder", [bear.id])
    play(s)
    assert (bear.id in s.state.cards and zone(s, bear) == f"{who}:battlefield") == survives
    if survives:
        assert not s.state.cards[bear.id].counters.get("+1/+1") and ptof(s, bear) == (2, 2)
    check(s)


def test_mccoy_lethal_damage_is_healed_and_mccoy_himself_is_not_saved(cards):
    s, mccoy = mccoy_table(cards)
    bear = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    act(s, "p1", type="counter", card_ids=[bear.id, mccoy.id], kind="+1/+1", delta=1)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [bear.id])  # 3 damage to a 3/3: destroyed by 704.5g, replaced
    play(s)
    assert zone(s, bear) == "p1:battlefield" and s.state.cards[bear.id].damage == 0 and ptof(s, bear) == (2, 2)
    mana(s, B=2, C=1)
    cast(s, "Murder", [mccoy.id])  # (another creature: not McCoy himself)
    play(s)
    assert zone(s, mccoy) == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("use_mccoy", [True, False])
def test_mccoy_or_a_shield_counter_its_controller_chooses(cards, use_mccoy):
    """616.1: two replacements of the same destruction (a shield counter, 122.1c; McCoy's): the affected creature's controller picks one."""
    s, _ = mccoy_table(cards)
    bear = creature(s, "p1", "Bear", "2/2", type_line="Token Creature — Bear")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="shield", delta=1)
    mana(s, B=2, C=1)
    cast(s, "Murder", [bear.id])
    labels = []

    def pick(d):
        if any("heal it instead" in o.label for o in d.options):
            labels.extend(o.label for o in d.options)
            return [next(o.id for o in d.options if ("heal it instead" in o.label) == use_mccoy)]
        return None
    play(s, pick=pick)
    assert len(labels) == 2 and zone(s, bear) == "p1:battlefield"
    assert s.state.cards[bear.id].counters.get("+1/+1", 0) == (0 if use_mccoy else 1)
    assert s.state.cards[bear.id].counters.get("shield", 0) == (1 if use_mccoy else 0)
    check(s)


def test_mccoy_a_creature_left_at_zero_toughness_still_dies(cards):
    """704.5f: with its +1/+1 counters removed a 0/0 is put into the graveyard (not destroyed, so nothing replaces it)."""
    s, _ = mccoy_table(cards)
    blob = creature(s, "p1", "Blob", "0/0", type_line="Token Creature — Ooze")
    act(s, "p1", type="counter", card_ids=[blob.id], kind="+1/+1", delta=2)
    play(s)
    assert zone(s, blob) == "p1:battlefield"
    mana(s, B=2, C=1)
    cast(s, "Murder", [blob.id])
    play(s)
    assert blob.id not in s.state.cards or not zone(s, blob).endswith("battlefield")
    check(s)


# -- Cmdr. Troi, Outgoing Empath -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cast_it", [True, False])
def test_troi_the_active_opponent_may_cast_free_and_you_copy_it_else_you_draw(cards, cast_it):
    from tests.game_helpers import turn_on

    s = sandbox(cards, "Cmdr. Troi, Outgoing Empath", p2=("Grizzly Bears",), players=3)
    troi = on_field(s, "Cmdr. Troi, Outgoing Empath")
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "hand"})
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main 1
    with pytest.raises(ActionError):  # (no opponent whose turn it is)
        act(s, "p1", type="activate_ability", card_id=troi.id, ability=1, targets=["p2"])
    act(s, "p1", type="set_stops", own=[], others=["main1"], smart_pass=False)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.priority == "p1" and not s.state.zones.get("stack"))
    with pytest.raises(ActionError):  # (Carol: not the player whose turn it is)
        act(s, "p1", type="activate_ability", card_id=troi.id, ability=1, targets=["p3"])
    held = len(hand(s))
    act(s, "p1", type="activate_ability", card_id=troi.id, ability=1, targets=["p2"])
    asked = []

    def pick(d):
        if bears.id in opts(d):
            asked.append(d.player)
            return [bears.id] if cast_it else []
        return None
    play(s, pick=pick)
    assert asked == ["p2"]  # (Bob's own choice)
    copies = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield"]
    if cast_it:
        assert zone(s, bears) == "p2:battlefield" and len(copies) == 1 and copies[0].is_token and len(hand(s)) == held  # (707.10f: a copy of a permanent spell)
    else:
        assert zone(s, bears) == "p2:hand" and not copies and len(hand(s)) == held + 1
    check(s)


def test_troi_copies_a_targeted_spell_with_a_new_target(cards):
    """707.10c: Troi's controller controls the copy and may choose new targets for it; the copy resolves first."""
    from tests.game_helpers import turn_on

    s = sandbox(cards, "Cmdr. Troi, Outgoing Empath", p2=("Lightning Bolt",), players=3)
    troi = on_field(s, "Cmdr. Troi, Outgoing Empath")
    bolt = card_named(s, "Lightning Bolt", "p2")
    act(s, "p2", type="move", card_ids=[bolt.id], to={"player": "p2", "zone": "hand"})
    turn_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="set_stops", own=[], others=["main1"], smart_pass=False)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.priority == "p1" and not s.state.zones.get("stack"))
    act(s, "p1", type="activate_ability", card_id=troi.id, ability=1, targets=["p2"])
    seen = []

    def pick(d):
        seen.append((d.player, d.kind, opts(d)))
        if bolt.id in opts(d):
            return [bolt.id]
        if d.player == "p2" and "p1" in opts(d):
            return ["p1"]  # Bob's Bolt at Alice
        if d.player == "p1" and "p2" in opts(d):
            return ["p2"]  # Alice's copy at Bob
        return None
    play(s, pick=pick)
    assert life(s, "p1") == 37 and life(s, "p2") == 37 and life(s, "p3") == 40, seen
    check(s)
