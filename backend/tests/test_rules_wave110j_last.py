"""Wave 110J last cards (official Scryfall rulings, scratchpad rul/final11.json).

* Quicksilver Elemental: the activated abilities of the target are collected when the ability resolves (611.2c; rulings 2004-10-04: several
  activations collect from several creatures, each copy of a once-each-turn ability is activated once each turn), only activated abilities
  (ruling 2004-12-01), written for "this permanent"; its own abilities may be paid with blue mana as though any color (609.4b).
* Grell Philosopher: the Oracle text is a triggered ability (enters, and your upkeep): each Horror you control gains the activated abilities
  the target artifact has at resolution, payable with blue mana as though any color (rulings 2022-06-10).
"""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave110e_cards import cast as cast_card
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put

QUICK = real("Quicksilver Elemental", "{3}{U}{U}", 5, "Creature — Elemental",
             "{U}: This creature gains all activated abilities of target creature until end of turn. (If any of the abilities use that creature's name, use this creature's name instead.)\n"
             "You may spend blue mana as though it were mana of any color to pay the activation costs of this creature's abilities.", ("3", "4"), "U")
GRELL = real("Grell Philosopher", "{2}{U}", 3, "Creature — Horror Wizard",
             "Aberrant Tinkering — When this creature enters and at the beginning of your upkeep, each Horror you control gains all activated abilities of target artifact an opponent controls until end of turn. "
             "You may spend blue mana as though it were mana of any color to activate those abilities.", ("1", "4"), "U")
SORC = real("Prodigal Sorcerer", "{2}{U}", 3, "Creature — Human Wizard Sorcerer", "{T}: This creature deals 1 damage to any target.", ("1", "1"), "U")
SHIVAN = real("Shivan Dragon", "{4}{R}{R}", 6, "Creature — Dragon", "Flying\n{R}: This creature gets +1/+0 until end of turn.", ("5", "5"), "R")
WALLA = real("Basking Rootwalla", "{G}", 1, "Creature — Lizard",
             "{1}{G}: This creature gets +2/+2 until end of turn. Activate only once each turn.\n"
             "Madness {0} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.)", ("1", "1"), "G")
SPELLBOMB = real("Pyrite Spellbomb", "{1}", 1, "Artifact", "{R}, Sacrifice this artifact: It deals 2 damage to any target.\n{1}, Sacrifice this artifact: Draw a card.", None)
HORROR = real("Test Horror", "{1}{B}", 2, "Creature — Horror", "", ("2", "2"), "B")
base.EXTRA.extend([QUICK, GRELL, SORC, SHIVAN, WALLA, SPELLBOMB, HORROR])


@pytest.mark.parametrize("name", ["Quicksilver Elemental", "Grell Philosopher"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _plan(s):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None)


def _abilities(s, card, needle):
    return [a.index for a in _plan(s).ch(s.state.cards[card.id]).abilities if a.kind == "activated" and needle in a.text]


def _activated(s, card, needle):
    return _abilities(s, card, needle)[0]


def _borrow(s, q, lender):
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=q.id, ability=_activated(s, q, "gains all activated"), targets=[lender.id])
    answer(s)


def _quick(cards, *others):
    s = build(cards, ["Quicksilver Elemental"], list(others))
    q = put(s, "Quicksilver Elemental")
    s.state.rules.controlled_since[q.id].turn = 0
    return s, q


def test_quicksilver_gains_the_activated_abilities_of_the_target_and_pays_with_blue(cards):
    s, q = _quick(cards, "Prodigal Sorcerer", "Shivan Dragon")
    sorc, dragon = put(s, "Prodigal Sorcerer", "p2"), put(s, "Shivan Dragon", "p2")
    _borrow(s, q, sorc)
    act(s, "p1", type="activate_ability", card_id=q.id, ability=_activated(s, q, "deals 1 damage"), targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39 and s.state.cards[q.id].tapped  # "This creature" is Quicksilver Elemental (ruling 2004-12-01)
    _borrow(s, q, dragon)
    pump = _activated(s, q, "gets +1/+0")
    mana(s, G=1)
    with pytest.raises(ActionError):  # green mana is not blue mana
        act(s, "p1", type="activate_ability", card_id=q.id, ability=pump)
    mana(s, U=1)  # blue mana pays {R}
    act(s, "p1", type="activate_ability", card_id=q.id, ability=pump)
    answer(s)
    assert pt(s, "Quicksilver Elemental")[0] == 4
    check(s)


def test_quicksilver_collects_from_several_creatures_activated_only_and_keeps_them_after_the_lender_leaves(cards):
    s, q = _quick(cards, "Prodigal Sorcerer", "Shivan Dragon")
    sorc, dragon = put(s, "Prodigal Sorcerer", "p2"), put(s, "Shivan Dragon", "p2")
    _borrow(s, q, sorc)
    _borrow(s, q, dragon)
    assert _abilities(s, q, "deals 1 damage") and _abilities(s, q, "gets +1/+0")  # both collected (ruling 2004-10-04)
    assert "flying" not in _plan(s).ch(s.state.cards[q.id]).keywords  # activated abilities only (ruling 2004-12-01)
    _gy(s, sorc)  # the lender leaves the battlefield
    assert _abilities(s, q, "deals 1 damage")  # fixed at resolution (611.2c)
    check(s)


def test_quicksilver_two_copies_of_a_once_each_turn_ability_are_each_activated_once(cards):
    s, q = _quick(cards, "Basking Rootwalla")
    walla = put(s, "Basking Rootwalla", "p2")
    _borrow(s, q, walla)
    _borrow(s, q, walla)
    pumps = _abilities(s, q, "+2/+2")
    assert len(pumps) == 2
    for ab in pumps:
        mana(s, U=2)
        act(s, "p1", type="activate_ability", card_id=q.id, ability=ab)
        answer(s)
    assert pt(s, "Quicksilver Elemental") == (7, 8)
    mana(s, U=2)
    with pytest.raises(ActionError):  # each copy only once each turn (ruling 2004-10-04)
        act(s, "p1", type="activate_ability", card_id=q.id, ability=pumps[0])
    check(s)


def _gy(s, card):
    act(s, card.owner, type="move", card_ids=[card.id], to={"player": card.owner, "zone": "graveyard"})


def _grell(cards, horror):
    s = build(cards, ["Grell Philosopher", "Test Horror", "Shivan Dragon"], ["Pyrite Spellbomb"])
    bomb = put(s, "Pyrite Spellbomb", "p2")
    other = put(s, "Test Horror") if horror else None
    mana(s, U=1, C=2)
    grell = cast_card(s, "Grell Philosopher")
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next((o.id for o in d.options if o.card_id == bomb.id), d.options[0].id)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, grell, bomb, other


def test_grell_gives_horrors_the_abilities_of_an_opponents_artifact_payable_with_blue(cards):
    s, grell, bomb, other = _grell(cards, True)
    assert _abilities(s, other, "deals 2 damage")  # every Horror you control
    ab = _activated(s, grell, "deals 2 damage")
    mana(s, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=grell.id, ability=ab, targets=["p2"])
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=grell.id, ability=ab, targets=["p2"])  # {R} paid with blue mana
    answer(s)
    assert life(s, "p2") == 38 and s.state.cards[grell.id].zone.endswith(":graveyard")  # it sacrificed itself ("this permanent")
    assert s.state.cards[bomb.id].zone.endswith(":battlefield")
    check(s)


def test_grell_abilities_stay_after_the_artifact_leaves_and_only_horrors_gain_them(cards):
    s, grell, bomb, _ = _grell(cards, False)
    shivan = put(s, "Shivan Dragon")
    _gy(s, bomb)
    assert _abilities(s, grell, "Draw a card") and not _abilities(s, shivan, "Draw a card")  # fixed at resolution (611.2c); a Dragon is no Horror
    check(s)


def test_grell_upkeep_trigger_lends_again_and_the_grant_ends_with_the_turn(cards):
    from tests.test_rules_wave100g_zones import to_step

    s = build(cards, ["Grell Philosopher"], ["Pyrite Spellbomb"])
    grell, bomb = put(s, "Grell Philosopher"), put(s, "Pyrite Spellbomb", "p2")
    assert not _abilities(s, grell, "Draw a card")
    to_step(s, "upkeep", 1 + len(s.state.players), pick=lambda d: [o.id for o in d.options if o.card_id == bomb.id] or None)
    assert s.state.turn.active_player == "p1" and _abilities(s, grell, "Draw a card")  # your upkeep
    to_step(s, "upkeep", 2 + len(s.state.players))
    assert not _abilities(s, grell, "Draw a card")  # until end of turn (514.2)
    check(s)


# -- Contractual Safeguard --
SAFEGUARD = real("Contractual Safeguard", "{2}{W}", 3, "Instant",
                 "Addendum — If you cast this spell during your main phase, put a shield counter on a creature you control. (If it would be dealt damage or destroyed, remove a shield counter from it instead.)\n"
                 "Choose a kind of counter on a creature you control. Put a counter of that kind on each other creature you control.", None, "W")
BEARS = [real(f"Bear{n}", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G") for n in "ABC"]
base.EXTRA.extend([SAFEGUARD, *BEARS])


def test_safeguard_full(cards):
    assert coverage.of_card_data(cards.resolve("Contractual Safeguard")).level == "FULL"


def _bears(cards):
    s = build(cards, ["Contractual Safeguard", "BearA", "BearB", "BearC"])
    return s, [put(s, f"Bear{n}") for n in "ABC"]


def test_safeguard_main_phase_shield_may_be_the_chosen_kind(cards):
    s, (a, b, c) = _bears(cards)
    mana(s, W=1, C=2)
    cast_card(s, "Contractual Safeguard")
    answer(s, a.id, f"{a.id}|shield")  # the addendum's shield counter on A, then that shield counter is chosen (ruling 2022-04-29)
    assert [s.state.cards[x.id].counters.get("shield", 0) for x in (a, b, c)] == [1, 1, 1]
    check(s)


def test_safeguard_outside_a_main_phase_no_shield_and_other_than_the_chosen_creature(cards):
    from tests.wave110a_kit import goto

    s, (a, b, c) = _bears(cards)
    act(s, "p1", type="set_counter", card_id=a.id, kind="+1/+1", value=2)
    act(s, "p1", type="set_counter", card_id=b.id, kind="+1/+1", value=1)
    goto(s, "begin_combat")
    mana(s, W=1, C=2)
    cast_card(s, "Contractual Safeguard")
    d = None
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and {o.id for o in d.options} == {f"{a.id}|+1/+1", f"{b.id}|+1/+1"}  # no shield counter was put (not a main phase)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[f"{b.id}|+1/+1"])
    answer(s)
    assert [s.state.cards[x.id].counters.get("+1/+1", 0) for x in (a, b, c)] == [3, 1, 1]  # each other creature than B
    assert not any(s.state.cards[x.id].counters.get("shield") for x in (a, b, c))
    check(s)


def test_safeguard_without_counters_does_nothing(cards):
    from tests.wave110a_kit import goto

    s, bears = _bears(cards)
    goto(s, "begin_combat")
    mana(s, W=1, C=2)
    cast_card(s, "Contractual Safeguard")
    answer(s)
    assert not any(s.state.cards[x.id].counters for x in bears) and s.state.rules.decision is None
    check(s)


# -- Reed Richards, Smartest Man --
REED = real("Reed Richards, Smartest Man", "{5}{U}", 6, "Legendary Creature — Human Scientist Hero",
            "Reach\nYou have no maximum hand size.\n"
            "The first time you would draw a card each turn except the first card you draw during each of your draw steps, you draw four cards instead.", ("2", "4"), "U")
CANTRIP = real("Test Cantrip", "{U}", 1, "Instant", "Draw a card.", None, "U")
base.EXTRA.extend([REED, CANTRIP])


def test_reed_full(cards):
    assert coverage.of_card_data(cards.resolve("Reed Richards, Smartest Man")).level == "FULL"


def _hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def _cantrip(s):
    from tests.wave9c_kit import to_hand

    c = to_hand(s, "Test Cantrip")
    mana(s, U=1)
    before = _hand(s) - 1
    if s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    return _hand(s) - before


def test_reed_your_turn_the_draw_step_draw_stays_one_and_the_next_draw_is_four(cards):
    from tests.test_rules_wave100g_zones import to_step
    from tests.wave110a_kit import goto

    s = build(cards, ["Reed Richards, Smartest Man", "Test Cantrip", "Test Cantrip"])
    put(s, "Reed Richards, Smartest Man")
    to_step(s, "main1", 2)
    before = _hand(s)
    to_step(s, "main1", 3)
    goto(s, "main1")
    assert s.state.turn.active_player == "p1" and _hand(s) == before + 1  # the draw step's first card is excluded (504.1)
    assert _cantrip(s) == 4  # the first other draw this turn
    assert _cantrip(s) == 1  # only the first time
    check(s)


def test_reed_opponents_turn_the_first_draw_is_four(cards):
    from tests.test_rules_wave100g_zones import to_step
    from tests.wave110a_kit import goto

    s = build(cards, ["Reed Richards, Smartest Man", "Test Cantrip", "Test Cantrip"])
    put(s, "Reed Richards, Smartest Man")
    opp = _hand(s, "p2")
    to_step(s, "main1", 2)
    goto(s, "main1", "p1")
    assert s.state.turn.active_player == "p2" and _hand(s, "p2") == opp + 1  # only "you"
    assert _cantrip(s) == 4
    assert _cantrip(s) == 1
    check(s)


# -- Captain America, First Avenger --
CAP = real("Captain America, First Avenger", "{R}{W}{U}", 3, "Legendary Creature — Human Soldier Hero",
           "Throw ... — {3}, Unattach an Equipment from Captain America: He deals damage equal to that Equipment's mana value divided as you choose among one, two, or three targets.\n"
           "... Catch — At the beginning of combat on your turn, attach up to one target Equipment you control to Captain America.", ("4", "4"), "RWU")
HAMMER = real("Loxodon Warhammer", "{3}", 3, "Artifact — Equipment", "Equipped creature gets +3/+0 and has trample and lifelink.\nEquip {3}", None)
SPLITTER = real("Bonesplitter", "{1}", 1, "Artifact — Equipment", "Equipped creature gets +2/+0.\nEquip {1}", None)
MANTLE = real("Paradise Mantle", "{0}", 0, "Artifact — Equipment", "Equipped creature has \"{T}: Add one mana of any color.\"\nEquip {1}", None)
base.EXTRA.extend([CAP, HAMMER, SPLITTER, MANTLE])


def test_captain_full(cards):
    assert coverage.of_card_data(cards.resolve("Captain America, First Avenger")).level == "FULL"


def _captain(cards, *equipment):
    s = build(cards, ["Captain America, First Avenger", *equipment, "Grizzly Bears"], ["Grizzly Bears", "Shivan Dragon"])
    cap = put(s, "Captain America, First Avenger")
    gear = [put(s, e) for e in equipment]
    for g in gear:
        act(s, "p1", type="attach", card_ids=[g.id], to=cap.id)
    return s, cap, gear


def _throw(s, cap, targets, division=(), **kw):
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=cap.id, ability=0, targets=targets, division=list(division), **kw)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_captain_divides_the_equipment_mana_value_among_one_two_or_three_targets(cards, n):
    s, cap, (hammer,) = _captain(cards, "Loxodon Warhammer")
    bears, dragon = put(s, "Grizzly Bears", "p2"), put(s, "Shivan Dragon", "p2")
    targets, division = {1: (["p2"], []), 2: (["p2", dragon.id], [1, 2]), 3: (["p2", dragon.id, bears.id], [1, 1, 1])}[n]
    _throw(s, cap, targets, division)
    answer(s)
    assert s.state.cards[hammer.id].attached_to is None and s.state.cards[hammer.id].zone == "p1:battlefield"  # unattached, stays (701.3d)
    assert life(s, "p2") == {1: 37, 2: 39, 3: 39}[n]
    assert s.state.cards[dragon.id].damage == {1: 0, 2: 2, 3: 1}[n]
    check(s)


def test_captain_division_must_match_the_equipment_and_give_each_target_one(cards):
    s, cap, _ = _captain(cards, "Loxodon Warhammer")
    dragon = put(s, "Shivan Dragon", "p2")
    with pytest.raises(ActionError):
        _throw(s, cap, ["p2", dragon.id], [2, 2])  # 4 is not the Warhammer's mana value
    with pytest.raises((ActionError, ValueError)):  # (the intent schema already refuses a 0)
        _throw(s, cap, ["p2", dragon.id], [3, 0])  # 601.2d: at least 1 each
    check(s)


def test_captain_chooses_the_equipment_first_when_mana_values_differ(cards):
    s, cap, (hammer, splitter) = _captain(cards, "Loxodon Warhammer", "Bonesplitter")
    dragon = put(s, "Shivan Dragon", "p2")
    _throw(s, cap, [])
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {hammer.id, splitter.id}  # 601.2b: before the targets
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[splitter.id])
    answer(s, dragon.id)
    assert s.state.cards[dragon.id].damage == 1 and s.state.cards[splitter.id].attached_to is None and s.state.cards[hammer.id].attached_to == cap.id
    check(s)


def test_captain_cost_choice_given_and_illegal_target_at_resolution(cards):
    s, cap, (hammer, splitter) = _captain(cards, "Loxodon Warhammer", "Bonesplitter")
    bears = put(s, "Grizzly Bears", "p2")
    _throw(s, cap, ["p2", bears.id], [2, 1], cost_choices=[{"component": 1, "cards": [hammer.id]}])
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "graveyard"})  # the Bears become an illegal target
    answer(s)
    assert life(s, "p2") == 38  # the original division still applies; the Bears' 1 isn't dealt (608.2b)
    assert s.state.cards[hammer.id].attached_to is None and s.state.cards[splitter.id].attached_to == cap.id
    check(s)


def test_captain_needs_equipment_with_mana_value(cards):
    s, cap, _ = _captain(cards)
    with pytest.raises(ActionError):
        _throw(s, cap, ["p2"])
    s, cap, _ = _captain(cards, "Paradise Mantle")
    with pytest.raises(ActionError):
        _throw(s, cap, ["p2"])  # 601.2d: nothing to give one, two, or three targets
    check(s)


# -- Fabrication Foundry --
FOUNDRY = real("Fabrication Foundry", "{1}{W}", 2, "Artifact",
               "{T}: Add {W}. Spend this mana only to cast an artifact spell or activate an ability of an artifact source.\n"
               "{2}{W}, {T}, Exile one or more other artifacts you control with total mana value X: Return target artifact card with mana value X or less from your graveyard to the battlefield. "
               "Activate only as a sorcery.", None, "W")
ARTS = [real(f"Gizmo{n}{k}", f"{{{n}}}", n, "Artifact", "", None) for n in (1, 2, 3, 4) for k in "ab"]
base.EXTRA.extend([FOUNDRY, *ARTS])


def test_foundry_full(cards):
    assert coverage.of_card_data(cards.resolve("Fabrication Foundry")).level == "FULL"


def _foundry(cards, mine, yard):
    s = build(cards, ["Fabrication Foundry", *mine, *yard])
    foundry = put(s, "Fabrication Foundry")  # (a noncreature artifact: {T} needs no wait, 302.6)
    arts = [put(s, n) for n in mine]
    for n in yard:
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == n)], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, C=2)
    return s, foundry, arts


def _gy_card(s, name):
    return next(c for c in s.state.cards.values() if c.name == name)


@pytest.mark.parametrize("given", [True, False])
def test_foundry_x_then_target_then_exact_total(cards, given):
    s, foundry, (a1, a2, a3) = _foundry(cards, ["Gizmo1a", "Gizmo2a", "Gizmo4a"], ["Gizmo3a"])
    target = _gy_card(s, "Gizmo3a")
    kw = {"cost_choices": [{"component": 2, "cards": [a1.id, a2.id]}]} if given else {}
    act(s, "p1", type="activate_ability", card_id=foundry.id, ability=1, x_value=3, targets=[target.id], **kw)
    if not given:
        d = s.state.rules.decision
        assert d is not None and {o.id for o in d.options} == {a1.id, a2.id, a3.id}  # other artifacts you control (not the Foundry)
        with pytest.raises(ActionError):  # 4 is not exactly 3
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[a3.id])
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[a1.id, a2.id])
    answer(s)
    assert s.state.cards[target.id].zone == "p1:battlefield"
    assert [s.state.cards[a.id].zone for a in (a1, a2, a3)] == ["p1:exile", "p1:exile", "p1:battlefield"]
    check(s)


def test_foundry_target_mana_value_above_x_is_refused(cards):
    s, foundry, (a1, a2) = _foundry(cards, ["Gizmo1a", "Gizmo2a"], ["Gizmo4b"])
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=foundry.id, ability=1, x_value=3, targets=[_gy_card(s, "Gizmo4b").id])
    check(s)


def test_foundry_refused_when_no_exact_total_exists(cards):
    s, foundry, (a, b) = _foundry(cards, ["Gizmo2a", "Gizmo2b"], ["Gizmo3a"])
    with pytest.raises(ActionError):  # 2 and 2 make 2 or 4, never 3 (601.2h: an unpayable cost)
        act(s, "p1", type="activate_ability", card_id=foundry.id, ability=1, x_value=3, targets=[_gy_card(s, "Gizmo3a").id])
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=foundry.id, ability=1, x_value=3, targets=[_gy_card(s, "Gizmo3a").id],
            cost_choices=[{"component": 2, "cards": [a.id]}])
    assert all(s.state.cards[c.id].zone == "p1:battlefield" for c in (foundry, a, b)) and s.state.cards[foundry.id].tapped is False
    check(s)


# -- Parnesse, the Subtle Brush --
PARNESSE = real("Parnesse, the Subtle Brush", "{2}{U}{B}{R}", 5, "Legendary Creature — Vampire Wizard",
                "Whenever you or a permanent you control becomes the target of a spell or ability an opponent controls, counter that spell or ability unless that player pays 4 life.\n"
                "Whenever you copy a spell, up to one target opponent may also copy that spell. They may choose new targets for that copy.", ("4", "4"), "UBR")
SHOCK = real("Shock", "{R}", 1, "Instant", "Shock deals 2 damage to any target.", None, "R")
TWINCAST = real("Twincast", "{U}{U}", 2, "Instant", "Copy target instant or sorcery spell. You may choose new targets for the copy.", None, "U")
base.EXTRA.extend([PARNESSE, SHOCK, TWINCAST])


@pytest.mark.parametrize("name", ["Parnesse, the Subtle Brush"])
def test_parnesse_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _drive(s, pick, limit=60):
    """Resolve everything; ``pick(d)`` answers a decision (a list of option ids), or None for its first options."""
    seen = []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            seen.append((d.player, d.prompt, [(o.id, o.label) for o in d.options]))
            got = pick(d)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=got if got is not None else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return seen
    raise AssertionError(seen)


def _parnesse(cards):
    s = build(cards, ["Parnesse, the Subtle Brush", "Shock", "Twincast"], ["Grizzly Bears", "Shock"])
    put(s, "Parnesse, the Subtle Brush")
    bears = put(s, "Grizzly Bears", "p2")
    for p in ("p1", "p2"):
        act(s, p, type="set_prefs", hold_priority=True)
    return s, bears


def _copy_own_shock(s, pick):
    mana(s, R=1, U=2)
    shock = cast_card(s, "Shock", ["p2"])
    cast_card(s, "Twincast", [shock.id])
    return _drive(s, pick)


@pytest.mark.parametrize("choice", ["yes", "no", "no_target"])
def test_parnesse_opponent_may_copy_the_copied_spell_with_new_targets(cards, choice):
    s, bears = _parnesse(cards)

    def pick(d):
        if "target for Parnesse" in d.prompt:
            return [] if choice == "no_target" else ["p2"]
        if d.prompt.startswith("Parnesse: copy"):
            return [choice]
        if d.player == "p2" and "keep its target" in d.prompt:
            return [bears.id]  # 707.10c: a new target for the opponent's copy
        return None
    seen = _copy_own_shock(s, pick)
    asked = [p for p, prompt, _ in seen if prompt.startswith("Parnesse: copy")]
    assert asked == ([] if choice == "no_target" else ["p2"])
    assert life(s, "p2") == 36  # the Shock and your copy
    assert s.state.cards[bears.id].zone == ("p2:graveyard" if choice == "yes" else "p2:battlefield")
    check(s)


def test_parnesse_copies_the_spell_as_it_last_was_after_it_left_the_stack(cards):
    s, bears = _parnesse(cards)
    left = []

    def pick(d):
        if left and d.prompt.startswith("Parnesse: copy"):
            shock = left.pop()
            assert s.state.cards[shock.id].zone == "p1:graveyard"
            return ["yes"]
        if "target for Parnesse" in d.prompt:
            return ["p2"]
        if d.player == "p2" and "keep its target" in d.prompt:
            return [bears.id]
        return None
    mana(s, R=1, U=2)
    shock = cast_card(s, "Shock", ["p2"])
    cast_card(s, "Twincast", [shock.id])
    for _ in range(30):  # Twincast resolves: the copy and Parnesse's trigger go on the stack
        d = s.state.rules.decision
        if d is not None and "target for Parnesse" in d.prompt:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="move", card_ids=[shock.id], to={"player": "p1", "zone": "graveyard"})  # the copied Shock leaves the stack
    left.append(shock)
    _drive(s, pick)
    assert not left and s.state.cards[bears.id].zone == "p2:graveyard"  # copied as it last existed (608.2h, 707.10)
    assert life(s, "p2") == 38  # only your copy hit Bob (the original left)
    check(s)


@pytest.mark.parametrize("pays", [True, False])
def test_parnesse_counters_an_opponents_targeting_spell_unless_they_pay_4_life(cards, pays):
    from tests.test_rules_wave100g_zones import to_step

    s, _ = _parnesse(cards)
    parnesse = card_named(s, "Parnesse, the Subtle Brush")
    to_step(s, "main1", 2)
    mana(s, "p2", R=1)
    shock = cast_card(s, "Shock", [parnesse.id], pid="p2")
    seen = _drive(s, lambda d: ["pay" if pays else "decline"] if d.prompt.endswith("pay 4 life?") else None)
    assert [p for p, prompt, _ in seen] == ["p2"]
    assert life(s, "p2") == (36 if pays else 40) and s.state.cards[parnesse.id].damage == (2 if pays else 0)
    assert s.state.cards[shock.id].zone == "p2:graveyard"  # resolved, or countered
    check(s)


# -- Magar of the Magic Strings --
MAGAR = real("Magar of the Magic Strings", "{1}{B}{R}", 3, "Legendary Creature — Minotaur Performer",
             "{1}{B}{R}: Note the name of target instant or sorcery card in your graveyard and put it onto the battlefield face down. It's a 3/3 creature with "
             "\"Whenever this creature deals combat damage to a player, you may create a copy of the card with the noted name. You may cast the copy without paying its mana cost\" "
             "and \"If this creature would leave the battlefield, exile it instead of putting it anywhere else.\"", ("3", "3"), "BR")
MURDER = real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B")
CLOUDSHIFT = real("Cloudshift", "{W}", 1, "Instant", "Exile target creature you control, then return that card to the battlefield under your control.", None, "W")
CLONE = real("Clone", "{3}{U}", 4, "Creature — Shapeshifter", "You may have this creature enter as a copy of any creature on the battlefield.", ("0", "0"), "U")
IXIDOR = real("Ixidor, Reality Sculptor", "{3}{U}{U}", 5, "Legendary Creature — Human Wizard", "Face-down creatures get +1/+1.\n{2}{U}: Turn target face-down creature face up.", ("3", "4"), "U")
base.EXTRA.extend([MAGAR, MURDER, CLOUDSHIFT, CLONE, IXIDOR])


def test_magar_full(cards):
    assert coverage.of_card_data(cards.resolve("Magar of the Magic Strings")).level == "FULL"


def _magar(cards, *more):
    s = build(cards, ["Magar of the Magic Strings", "Shock", *more])
    magar = put(s, "Magar of the Magic Strings")
    shock = card_named(s, "Shock")
    act(s, "p1", type="move", card_ids=[shock.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1, R=1, C=1)
    act(s, "p1", type="activate_ability", card_id=magar.id, ability=0, targets=[shock.id])
    answer(s)
    return s, magar, shock


def _attack(s, attacker, pick):
    from tests.wave110j_kit import to_phase

    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])
    return _drive(s, pick)


def test_magar_puts_the_card_face_down_as_a_3_3_with_the_noted_name(cards):
    s, magar, shock = _magar(cards)
    c = s.state.cards[shock.id]
    ch = _plan(s).ch(c)
    assert c.zone == "p1:battlefield" and c.face_down and ch.name == "" and (ch.power, ch.toughness) == ("3", "3") and not ch.colors and ch.mana_value == 0
    assert c.choices == {"Noted name": "Shock"}
    check(s)


@pytest.mark.parametrize("cast_it", [True, False])
def test_magar_combat_damage_casts_a_copy_of_the_noted_card_for_free(cards, cast_it):
    s, magar, shock = _magar(cards)

    def pick(d):
        if d.prompt.startswith("Choose a spell to cast"):
            return [d.options[0].id] if cast_it else []
        if d.prompt == "Choose a target for Shock":
            return ["p2"]
        return None
    seen = _attack(s, s.state.cards[shock.id], pick)
    assert any(prompt.startswith("Choose a spell to cast") for _, prompt, _ in seen)
    assert life(s, "p2") == (35 if cast_it else 37)  # 3 combat damage, then the copy's 2 (no mana paid)
    assert s.state.cards[shock.id].zone == "p1:battlefield" and s.state.cards[shock.id].face_down
    assert not any(c.name == "Shock" and c.id != shock.id and c.zone != "p1:library" for c in s.state.cards.values() if c.owner == "p1")  # the copy ceased to exist
    check(s)


def test_magar_copy_of_the_face_down_creature_has_no_noted_name(cards):
    s, magar, shock = _magar(cards, "Clone")
    mana(s, U=1, C=3)
    clone = cast_card(s, "Clone")
    _drive(s, lambda d: [shock.id] if "choose a creature to copy" in d.prompt else None)
    ch = _plan(s).ch(s.state.cards[clone.id])
    assert (ch.power, ch.toughness) == ("3", "3") and len(ch.abilities) == 2 and not s.state.cards[clone.id].choices
    seen = _attack(s, s.state.cards[clone.id], lambda d: None)
    assert life(s, "p2") == 37 and not any(prompt.startswith("Choose a spell to cast") for _, prompt, _ in seen)  # nothing is copied
    check(s)


@pytest.mark.parametrize("how", ["Murder", "Cloudshift"])
def test_magar_face_down_card_leaving_is_exiled_and_stays_there(cards, how):
    s, magar, shock = _magar(cards, how)
    mana(s, B=2, C=1, W=1)
    cast_card(s, how, [shock.id])
    answer(s)
    assert s.state.cards[shock.id].zone == "p1:exile"  # exiled instead; a blinked instant card stays in exile
    check(s)


def test_magar_turning_it_face_up_only_reveals_it(cards):
    s, magar, shock = _magar(cards, "Ixidor, Reality Sculptor")
    ixidor = put(s, "Ixidor, Reality Sculptor")
    s.state.rules.controlled_since[ixidor.id].turn = 0
    mana(s, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=ixidor.id, ability=1, targets=[shock.id])
    answer(s)
    c = s.state.cards[shock.id]
    assert c.zone == "p1:battlefield" and c.face_down  # revealed, stays face down (ruling 2022-10-07)
    check(s)


def test_clone_copies_a_face_down_creature_as_a_nameless_2_2(cards):
    """707.2 (its example: Clone copying a face-down Grinning Demon), 708.2a: nothing of the hidden card is copied."""
    s = build(cards, ["Clone", "Shivan Dragon"])
    dragon = put(s, "Shivan Dragon")
    act(s, "p1", type="face_down", card_ids=[dragon.id], face_down=True)
    mana(s, U=1, C=3)
    clone = cast_card(s, "Clone")
    _drive(s, lambda d: [dragon.id] if "choose a creature to copy" in d.prompt else None)
    ch = _plan(s).ch(s.state.cards[clone.id])
    assert not s.state.cards[clone.id].face_down and ch.name == "" and (ch.power, ch.toughness) == ("2", "2") and not ch.abilities and not ch.colors
    check(s)


# -- Ertai's Meddling --
MEDDLING = real("Ertai's Meddling", "{X}{U}", 1, "Instant",
                "X can't be 0.\nTarget spell's controller exiles it with X delay counters on it.\n"
                "At the beginning of each of that player's upkeeps, if that card is exiled, remove a delay counter from it. If the card has no delay counters on it, "
                "the player puts it onto the stack as a copy of the original spell.", None, "U")
PYROMANCER = real("Young Pyromancer", "{1}{R}", 2, "Creature — Human Shaman", "Whenever you cast an instant or sorcery spell, create a 1/1 red Elemental creature token.", ("2", "1"), "R")
THINK = real("Think Twice", "{1}{U}", 2, "Instant", "Draw a card.\nFlashback {2}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)", None, "U")
MIGHT = real("Kodama's Might", "{G}", 1, "Instant — Arcane", "Target creature gets +2/+2 until end of turn.\nSplice onto Arcane {G} (As you cast an Arcane spell, you may reveal this card "
             "from your hand and pay its splice cost. If you do, add this card's effects to that spell.)", None, "G")
RAY = real("Glacial Ray", "{1}{R}", 2, "Instant — Arcane", "Glacial Ray deals 2 damage to any target.\nSplice onto Arcane {1}{R} (As you cast an Arcane spell, you may reveal this card "
           "from your hand and pay its splice cost. If you do, add this card's effects to that spell.)", None, "R")
ANGEL = real("Exalted Angel", "{4}{W}{W}", 6, "Creature — Angel", "Flying\nWhenever this creature deals damage, you gain that much life.\n"
             "Morph {2}{W}{W} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)", ("4", "5"), "W")
base.EXTRA.extend([MEDDLING, PYROMANCER, THINK, MIGHT, RAY, ANGEL])


def test_meddling_full(cards):
    assert coverage.of_card_data(cards.resolve("Ertai's Meddling")).level == "FULL"


def _meddle_setup(cards, *more):
    s = build(cards, ["Ertai's Meddling", *more], ["Grizzly Bears"])
    for p in ("p1", "p2"):
        act(s, p, type="set_prefs", hold_priority=True)
    return s


def _meddle(s, spell, x):
    mana(s, U=1, C=x)
    m = to_hand_(s, "Ertai's Meddling")
    if s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="cast_spell", card_id=m.id, targets=[spell.id], x_value=x)
    answer(s)


def to_hand_(s, name):
    from tests.wave9c_kit import to_hand

    return to_hand(s, name)


def _tokens(s):
    return len([c for c in s.state.cards.values() if c.is_token and c.zone.endswith(":battlefield")])


def _meddle_ticks(s):
    return [t for t in s.state.rules.delayed if t.effects and t.effects[0].get("do") == "meddle_tick110j"]


@pytest.mark.parametrize("x", [1, 2])
def test_meddling_delays_the_spell_and_puts_the_card_back_uncast(cards, x):
    from tests.test_rules_wave100g_zones import to_step

    s = _meddle_setup(cards, "Shock", "Young Pyromancer")
    put(s, "Young Pyromancer")
    mana(s, R=1)
    shock = cast_card(s, "Shock", ["p2"])
    _meddle(s, shock, x)
    assert s.state.cards[shock.id].zone == "p1:exile" and s.state.cards[shock.id].counters == {"delay": x} and life(s, "p2") == 40
    tokens = _tokens(s)
    to_step(s, "main1", 2)  # Bob's upkeep: not that player's
    assert s.state.cards[shock.id].counters == {"delay": x}
    to_step(s, "main1", 3)
    if x == 2:
        assert s.state.cards[shock.id].zone == "p1:exile" and s.state.cards[shock.id].counters == {"delay": 1} and life(s, "p2") == 40
        to_step(s, "main1", 5)
    assert life(s, "p2") == 38 and s.state.cards[shock.id].zone == "p1:graveyard"  # the original target (707.10)
    assert _tokens(s) == tokens  # put onto the stack, not cast: no cast trigger (ruling 2013-04-15)
    assert not _meddle_ticks(s) and not s.state.rules.meddled110j
    check(s)


def test_meddling_an_opponents_spell_returns_at_their_upkeep(cards):
    from tests.test_rules_wave100g_zones import to_step

    s = build(cards, ["Ertai's Meddling"], ["Shock"])
    for p in ("p1", "p2"):
        act(s, p, type="set_prefs", hold_priority=True)
    to_step(s, "main1", 2)
    mana(s, "p2", R=1)
    _no_auto_pass(s)
    shock = cast_card(s, "Shock", ["p1"], pid="p2")
    _meddle(s, shock, 1)
    assert s.state.cards[shock.id].zone == "p2:exile" and life(s, "p1") == 40
    to_step(s, "main1", 3)
    assert s.state.cards[shock.id].zone == "p2:exile"  # your upkeep: nothing
    to_step(s, "main1", 4)
    assert life(s, "p1") == 38 and s.state.cards[shock.id].zone == "p2:graveyard"
    check(s)


def _no_auto_pass(s):
    from tests.wave110a_kit import STEPS

    for p in ("p1", "p2"):
        act(s, p, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)


def test_meddling_a_copy_of_a_spell_makes_it_cease_to_exist(cards):
    from tests.wave110a_kit import STEPS

    s = _meddle_setup(cards, "Shock", "Twincast")
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, R=1, U=2)
    shock = cast_card(s, "Shock", ["p2"])
    cast_card(s, "Twincast", [shock.id])
    for _ in range(6):  # Twincast resolves; the copy waits on the stack
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
            continue
        copy = next((c for c in s.state.cards.values() if c.zone == "stack" and c.is_token), None)
        if copy is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    _meddle(s, copy, 1)
    assert copy.id not in s.state.cards or not s.state.cards[copy.id].zone.endswith("exile")  # it ceased to exist (707.10a)
    assert not _meddle_ticks(s) and not s.state.rules.meddled110j and life(s, "p2") == 38  # only the original Shock dealt damage
    check(s)


def test_meddling_flashback_spell_is_exiled_after_it_resolves_again(cards):
    from tests.test_rules_wave100g_zones import to_step

    s = _meddle_setup(cards, "Think Twice")
    think = card_named(s, "Think Twice")
    act(s, "p1", type="move", card_ids=[think.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=think.id)
    assert s.state.cards[think.id].zone == "stack"
    _meddle(s, think, 1)
    to_step(s, "main1", 2)
    hand = len(s.state.zones["p1:hand"])
    to_step(s, "main1", 3)
    assert s.state.cards[think.id].zone == "p1:exile"  # it remembers flashback (ruling 2011-01-22)
    assert len(s.state.zones["p1:hand"]) == hand + 2  # the draw step's card and Think Twice's
    check(s)


def test_meddling_keeps_the_spliced_effects(cards):
    from tests.test_rules_wave100g_zones import to_step

    s = _meddle_setup(cards, "Kodama's Might", "Glacial Ray")
    bears = put(s, "Grizzly Bears", "p2")
    might, ray = to_hand_(s, "Kodama's Might"), to_hand_(s, "Glacial Ray")
    mana(s, G=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=might.id, splice=[ray.id], targets=[bears.id, "p2"], target_counts=[1, 1])
    _meddle(s, might, 1)
    assert life(s, "p2") == 40 and pt(s, "Grizzly Bears", "p2") == (2, 2)
    to_step(s, "main1", 3)  # it comes back in this turn's upkeep: the pump lasts until end of turn
    assert life(s, "p2") == 38 and pt(s, "Grizzly Bears", "p2") == (4, 4)  # both effects (ruling 2013-04-15)
    check(s)


def test_meddling_face_down_spell_returns_as_a_face_up_nameless_2_2(cards):
    from tests.test_rules_wave100g_zones import to_step

    s = _meddle_setup(cards, "Exalted Angel")
    angel = to_hand_(s, "Exalted Angel")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=angel.id, face_down=True)
    _meddle(s, angel, 1)
    assert s.state.cards[angel.id].zone == "p1:exile"
    to_step(s, "main1", 3)
    c = s.state.cards[angel.id]
    ch = _plan(s).ch(c)
    assert c.zone == "p1:battlefield" and not c.face_down
    assert ch.name == "" and (ch.power, ch.toughness) == ("2", "2") and not ch.colors and not ch.abilities  # ruling 2004-10-04
    check(s)


def test_meddling_x_cant_be_0_and_a_card_that_left_exile_stays_gone(cards):
    from tests.test_rules_wave100g_zones import to_step

    s = _meddle_setup(cards, "Shock")
    mana(s, R=1)
    shock = cast_card(s, "Shock", ["p2"])
    with pytest.raises(ActionError):
        _meddle(s, shock, 0)
    _meddle(s, shock, 1)
    act(s, "p1", type="move", card_ids=[shock.id], to={"player": "p1", "zone": "graveyard"})  # it leaves exile
    to_step(s, "main1", 3)
    assert s.state.cards[shock.id].zone == "p1:graveyard" and life(s, "p2") == 40  # 603.4: "if that card is exiled"
    check(s)
