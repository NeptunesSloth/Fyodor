"""Wave 110E session 6: planeswalker lines on real Oracle text; every scenario checks the replay and a save and a load.

* Rowan Kenrith +2: 508.1d the target player's creatures must attack during that player's next turn only.
* Rowan Kenrith -8: 114.1 the emblem; 603.2 / 707.10 it copies each non-mana ability its owner activates (a loyalty ability counts, 606.3).
* Garruk, Curse Breaker -4: 611.2a/500.4 until Garruk's controller's next turn, 603.2c one trigger per batch of creatures attacking an opponent
  of Garruk's controller: "those creatures" are that batch (they get +2/+2 and trample).
"""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db, keywords  # noqa: F401  (card_db is the fixture)
from tests.wave9c_kit import build, check, mana, put

ROWAN = real("Rowan Kenrith", "{2}{R}{R}", 4, "Legendary Planeswalker — Rowan",
             "+2: During target player's next turn, each creature that player controls attacks if able.\n"
             "−2: Rowan Kenrith deals 3 damage to each tapped creature target player controls.\n"
             "−8: Target player gets an emblem with \"Whenever you activate an ability that isn't a mana ability, copy it. You may choose new targets for the copy.\"\n"
             "Partner with Will Kenrith\nRowan Kenrith can be your commander.", None, "R")
GARRUK = real("Garruk, Curse Breaker", "{3}{G}{G}", 5, "Legendary Planeswalker — Garruk",
              "Whenever a creature you control with power 4 or greater enters, draw a card.\n"
              "+2: Untap up to two target lands.\n−3: Create a 4/4 green Beast creature token with trample.\n"
              "−4: Until your next turn, whenever one or more creatures attack one of your opponents, those creatures get +2/+2 and gain trample until end of turn.",
              None, "G")
ABSORB = real("Absorb Identity", "{2}{U}", 3, "Instant",
              "Return target creature to its owner's hand. You may have Shapeshifters you control become copies of that creature until end of turn.", None, "U")
SHIFTER = real("Test Shifter", "{1}", 1, "Creature — Shapeshifter", "", ("1", "1"), "")
COWARD = real("Coward", "{1}{R}", 2, "Instant",
              "Target creature can't block this turn and becomes a Coward in addition to its other types until end of turn.", None, "R")
KILLER = real("Killer", "{2}{R}", 3, "Instant",
              "Killer deals 3 damage to target creature and each other creature that shares a creature type with it.", None, "R")
FOLIAGE = real("Flash Foliage", "{2}{G}", 3, "Instant",
               "Cast this spell only during combat after blockers are declared.\n"
               "Create a 1/1 green Saproling creature token that's blocking target creature attacking you.\nDraw a card.", None, "G")
MIRROR = real("Mirror Match", "{4}{U}{U}", 6, "Instant",
              "Cast this spell only during the declare blockers step.\n"
              "For each creature attacking you or a planeswalker you control, create a token that's a copy of that creature and that's blocking that creature. "
              "Exile those tokens at end of combat.", None, "U")
base.EXTRA.extend([ROWAN, GARRUK, ABSORB, SHIFTER, COWARD, KILLER, FOLIAGE, MIRROR])
base.NAMES.extend(["Rowan Kenrith", "Garruk, Curse Breaker", "Absorb Identity", "Coward", "Killer", "Flash Foliage", "Mirror Match"])


def _walker(cards, name, extra=(), theirs=("Grizzly Bears",)):
    from tests.test_rules_wave30m_durations import to_phase

    s = build(cards, [name, "Grizzly Bears", *extra], list(theirs), forests=30, islands=30)
    mine = put(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    w = put(s, name)
    act(s, "p1", type="set_counter", card_id=w.id, kind="loyalty", value=8)
    return s, w, mine


def _activate(s, w, ability, **kw):
    act(s, "p1", type="activate_ability", card_id=w.id, ability=ability, **kw)
    answer(s)


def _until_attackers(s, turn, attack=()):
    """Pass until ``turn``'s declare-attackers question; earlier ones are answered (Alice declares nothing, Bob what ``attack`` says)."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            if s.state.turn.number == turn:
                return
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": c, "target": "p1"} for c in attack] if d.player == "p2" else [])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no attackers were asked for")


def test_rowan_plus_two_forces_the_attack_on_the_targets_next_turn(cards):
    s, rowan, _ = _walker(cards, "Rowan Kenrith")
    bears = put(s, "Grizzly Bears", "p2")
    _activate(s, rowan, 0, targets=["p2"], target_counts=[1])
    _until_attackers(s, 4)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    check(s)


def test_rowan_plus_two_ends_after_that_turn(cards):
    s, rowan, _ = _walker(cards, "Rowan Kenrith")
    bears = put(s, "Grizzly Bears", "p2")
    _activate(s, rowan, 0, targets=["p2"], target_counts=[1])
    _until_attackers(s, 6, attack=[bears.id])  # (turn 4: forced, attacks)
    act(s, "p2", type="declare_attackers", attackers=[])  # turn 6: free to stay home
    check(s)


@pytest.mark.parametrize("emblem", [True, False])
def test_rowan_minus_eight_emblem_copies_the_owners_activated_abilities(cards, emblem):
    s, rowan, _ = _walker(cards, "Rowan Kenrith", ["Shivan Dragon"])
    dragon = put(s, "Shivan Dragon")
    if emblem:
        _activate(s, rowan, 2, targets=["p1"])
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=dragon.id, ability=1)
    answer(s)
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[dragon.id]).pt[0] == (7 if emblem else 6)  # 5 + 1 (+1 for the copy)
    check(s)


def _settle(s):
    while s.state.zones.get("stack") and s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")


@pytest.mark.parametrize("target", ["p2", "p1"])
def test_garruk_minus_four_pumps_the_creatures_attacking_his_controllers_opponents(cards, target):
    from app.rules.plan import Plan

    s, garruk, bears = _walker(cards, "Garruk, Curse Breaker")
    theirs = put(s, "Grizzly Bears", "p2")
    _activate(s, garruk, 3)
    if target == "p2":
        _until_attackers(s, 3)  # (Alice's own declaration this turn)
    else:
        _until_attackers(s, 4)
    pt = lambda c: Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])  # noqa: E731
    if target == "p2":
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
        _settle(s)
        assert (pt(bears).pt[0], "trample" in {k.lower() for k in keywords(s, bears)}) == (4, True)
    else:
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": theirs.id, "target": "p1"}])
        _settle(s)
        assert (pt(theirs).pt[0], "trample" in {k.lower() for k in keywords(s, theirs)}) == (2, False)
    check(s)


def test_garruk_minus_four_ends_as_his_controllers_next_turn_begins(cards):
    from app.rules.plan import Plan

    s, garruk, bears = _walker(cards, "Garruk, Curse Breaker")
    _activate(s, garruk, 3)
    _until_attackers(s, 5)  # (turn 5 is Alice's next turn)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    _settle(s)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id]).pt[0] == 2
    check(s)


@pytest.mark.parametrize("name", ["Rowan Kenrith", "Garruk, Curse Breaker", "Absorb Identity", "Coward", "Killer", "Flash Foliage", "Mirror Match"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("accept", [True, False])
def test_absorb_identity_shapeshifters_copy_the_returned_creature_only_if_you_choose(cards, accept):
    from app.rules.plan import Plan
    from tests.wave9c_kit import to_hand  # noqa: F401

    s = build(cards, ["Absorb Identity", "Test Shifter"], ["Grizzly Bears", "Test Shifter"], forests=30, islands=30)
    mine, theirs = put(s, "Test Shifter"), put(s, "Test Shifter", "p2")
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, U=1, C=2)
    base.cast(s, "Absorb Identity", [bears.id])
    for _ in range(10):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0 if accept else -1].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    ch = lambda c: Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])  # noqa: E731
    assert s.state.cards[bears.id].zone == "p2:hand"
    assert (ch(mine).pt, ch(mine).name == "Grizzly Bears") == ((2, 2), True) if accept else ch(mine).pt == (1, 1)
    assert ch(theirs).pt == (1, 1)  # (only your own Shapeshifters)
    check(s)


def test_killer_damages_the_target_and_every_other_creature_sharing_a_type(cards):
    """205.3m: the target's creature types decide; 120.3 each is dealt 3 (a 2/2 Bear dies, the Shifter does not share a type, a 0/4 Wall survives)."""
    s = build(cards, ["Killer", "Grizzly Bears", "Test Shifter"], ["Grizzly Bears", "Wall of Test"], forests=30, islands=30)
    mine, shifter = put(s, "Grizzly Bears"), put(s, "Test Shifter")
    theirs = put(s, "Grizzly Bears", "p2")
    mana(s, R=1, C=2)
    base.cast(s, "Killer", [theirs.id])
    answer(s)
    assert [s.state.cards[c.id].zone for c in (theirs, mine, shifter)] == ["p2:graveyard", "p1:graveyard", "p1:battlefield"]
    check(s)


def test_killer_on_a_wall_leaves_the_others_alone(cards):
    s = build(cards, ["Killer", "Grizzly Bears"], ["Wall of Test"], forests=30, islands=30)
    bears, wall = put(s, "Grizzly Bears"), put(s, "Wall of Test", "p2")
    mana(s, R=1, C=2)
    base.cast(s, "Killer", [wall.id])
    answer(s)
    assert (s.state.cards[bears.id].zone, s.state.cards[wall.id].zone) == ("p1:battlefield", "p2:battlefield")  # 0/4 takes 3, no Bear shares Wall
    check(s)


def test_coward_adds_the_type_and_keeps_the_others(cards):
    from app.rules.plan import Plan

    s = build(cards, ["Coward"], ["Grizzly Bears"], forests=30, islands=30)
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, R=1, C=1)
    base.cast(s, "Coward", [bears.id])
    answer(s)
    assert {"Coward", "Bear"} <= set(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id]).subtypes)
    check(s)


@pytest.mark.parametrize("already_blocked", [False, True])
def test_flash_foliage_token_blocks_the_attacker_even_if_it_was_unblocked(cards, already_blocked):
    """509.4/509.3c: the token enters blocking the attacker (an unblocked one becomes blocked: no damage to the player); the spell also draws."""
    from tests.test_rules_group_unblocked import finish_combat
    from tests.wave53c_kit import combat_step, creature, in_play, pool, priority_to, settle, swing

    s = sandbox_with_foliage(cards)
    a = creature(s, "p1", "Aaa", "5/5")
    guard = creature(s, "p2", "Guard", "0/9")
    combat_step(s)
    swing(s, [a], [(guard, a)] if already_blocked else [], before=None)
    foliage = in_play(s, "Flash Foliage", "p2")
    act(s, "p2", type="move", card_ids=[foliage.id], to={"zone": "hand"})
    hand = len(s.state.zones["p2:hand"])
    pool(s, "p2", G=1, C=2)
    priority_to(s, "p2")
    act(s, "p2", type="cast_spell", card_id=foliage.id, targets=[a.id])
    settle(s)
    token = next(c for c in s.state.cards.values() if c.name == "Saproling" and c.zone == "p2:battlefield")
    assert token.blocking is not None and len(s.state.zones["p2:hand"]) == hand  # (the spell left the hand, one card drawn)
    finish_combat(s)
    assert s.state.players["p2"].life == 40  # a is blocked (509.1h): no damage to the player either way
    check(s)


def sandbox_with_foliage(cards, name="Flash Foliage"):
    from tests.wave53c_kit import sandbox

    return sandbox(cards, p2=(name,))


def test_mirror_match_copies_block_each_attacker_and_are_exiled_at_end_of_combat(cards):
    """509.4 + 707.2: one token copy per attacker, each blocking its original (so no damage to the player); 603.7 exiled at end of combat."""
    from tests.test_rules_group_unblocked import finish_combat
    from tests.wave53c_kit import combat_step, creature, in_play, pool, priority_to, settle, swing

    s = sandbox_with_foliage(cards, "Mirror Match")
    a, b = creature(s, "p1", "Aaa", "1/9"), creature(s, "p1", "Bbb", "2/9")
    creature(s, "p2", "Guard", "0/9")  # (so Bob is asked to declare blockers; he blocks nothing)
    combat_step(s)
    swing(s, [a, b], [], before=None)
    mm = in_play(s, "Mirror Match", "p2")
    act(s, "p2", type="move", card_ids=[mm.id], to={"zone": "hand"})
    pool(s, "p2", U=2, C=4)
    priority_to(s, "p2")
    act(s, "p2", type="cast_spell", card_id=mm.id)
    settle(s)
    copies = {c.name: c for c in s.state.cards.values() if c.controller == "p2" and c.zone == "p2:battlefield" and c.name in ("Aaa", "Bbb")}
    assert sorted(copies) == ["Aaa", "Bbb"] and all(c.blocking is not None for c in copies.values())
    finish_combat(s)
    assert s.state.players["p2"].life == 40 and not any(c.zone == "p2:battlefield" for c in copies.values() if c.id in s.state.cards)
    check(s)
