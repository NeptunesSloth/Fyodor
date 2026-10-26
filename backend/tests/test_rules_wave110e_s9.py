"""Wave 110E session 9: Oracle-text scenarios for cards promoted this session (each docstring names the rule)."""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.rules import coverage
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

BATTLE = real("Uphill Battle", "{3}{R}", 4, "Enchantment", "Creatures played by your opponents enter tapped.", None, "R")
BEAR = real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")
DJINN = real("Djinn Illuminatus", "{3}{U/R}{U/R}", 5, "Creature — Djinn",
             "({U/R} can be paid with either {U} or {R}.)\nFlying\nEach instant and sorcery spell you cast has replicate. The replicate cost is equal to its mana cost. "
             "(When you cast it, copy it for each time you paid its replicate cost. You may choose new targets for the copies.)", ("3", "5"), "UR")
SIP = real("Test Sip", "{U}", 1, "Instant", "You gain 1 life.", None, "U")
BOLT = real("Test Tonic", "{1}{G}", 2, "Sorcery", "You gain 1 life.", None, "G")
ARBORIA = real("Arboria", "{2}{G}", 3, "World Enchantment",
               "Creatures can't attack a player unless that player cast a spell or put a nontoken permanent onto the battlefield during their last turn.", None, "G")
DAWN = real("Celestial Dawn", "{1}{W}{W}", 3, "Enchantment",
            "Lands you control are Plains.\nNonland permanents you control are white. The same is true for spells you control and nonland cards you own that aren't on the battlefield.\n"
            "You may spend white mana as though it were mana of any color. You may spend other mana only as though it were colorless mana.", None, "W")
PETS = real("Exotic Pets", "{2}{U}", 3, "Sorcery",
            'Create two 1/1 blue Fish creature tokens with "This token can\'t be blocked." Then for each kind of counter among creatures you control, '
            "put a counter of that kind on either of those tokens.", None, "U")
base.EXTRA.extend([PETS, DAWN, ARBORIA, BATTLE, BEAR, DJINN, SIP, BOLT])


@pytest.mark.parametrize("name", [c["name"] for c in (BATTLE, DJINN, ARBORIA, DAWN, PETS)])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _cast_bear(cards, battle_owner):
    s = build(cards, ["Test Bear", *(["Uphill Battle"] if battle_owner == "p1" else [])], ["Uphill Battle"] if battle_owner == "p2" else [])
    from tests.game_helpers import act

    put(s, "Uphill Battle", battle_owner)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bear").id)
    answer(s)
    return s, card_named(s, "Test Bear")


def test_uphill_battle_opponents_cast_creature_enters_tapped(cards):
    """614.1d, 305.1: a creature an opponent of the controller casts enters tapped."""
    s, bear = _cast_bear(cards, "p2")
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].tapped
    check(s)


def test_uphill_battle_own_cast_and_non_cast_entries_untapped(cards):
    """Its controller's creatures are not "played by your opponents"; a creature put onto the battlefield (not cast) enters untapped."""
    s, bear = _cast_bear(cards, "p1")
    assert s.state.cards[bear.id].zone == "p1:battlefield" and not s.state.cards[bear.id].tapped
    s = build(cards, ["Test Bear"], ["Uphill Battle"])
    put(s, "Uphill Battle", "p2")
    bear = put(s, "Test Bear")
    assert not s.state.cards[bear.id].tapped
    check(s)


@pytest.mark.parametrize(("spell", "cost"), [("Test Sip", {"U": 3}), ("Test Tonic", {"G": 3, "C": 3})])
def test_djinn_illuminatus_gives_instants_and_sorceries_replicate(cards, spell, cost):
    """702.56a: the spell has replicate (cost = its mana cost); each time paid, one copy (two payments: 3 life in all)."""
    from tests.game_helpers import act
    from tests.wave9c_kit import life

    s = build(cards, ["Djinn Illuminatus", spell])
    put(s, "Djinn Illuminatus")
    mana(s, **cost)
    before = life(s, "p1")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, spell).id, kicker=2)
    answer(s)
    assert life(s, "p1") == before + 3
    check(s)


def test_djinn_illuminatus_gives_no_replicate_to_creature_spells(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act

    s = build(cards, ["Djinn Illuminatus", "Test Bear"])
    put(s, "Djinn Illuminatus")
    mana(s, G=3, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bear").id, kicker=1)


def _arboria_turn3(cards, p2_does):
    """Alice has Arboria and a creature; Bob's turn 2 is idle, plays a land, casts a spell or makes only a token; then Alice's turn 3 main phase."""
    from tests.game_helpers import act
    from tests.test_rules_conditionals import creature

    s = build(cards, ["Arboria", "Test Bear"], ["Test Sip"])
    put(s, "Arboria")
    bear = put(s, "Test Bear")
    for _ in range(300):
        if s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    if p2_does == "land":
        act(s, "p2", type="play_land", card_id=to_hand(s, "Island", "p2").id)
    elif p2_does == "spell":
        mana(s, "p2", U=1)
        act(s, "p2", type="cast_spell", card_id=to_hand(s, "Test Sip", "p2").id)
        answer(s)
    elif p2_does == "token":
        creature(s, "p2", "Bobbit", "1/1")
    for _ in range(300):
        if s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    return s, bear


@pytest.mark.parametrize(("p2_does", "may_attack"), [("nothing", False), ("token", False), ("land", True), ("spell", True)])
def test_arboria_attack_only_a_player_who_cast_or_put_a_nontoken_permanent_last_turn(cards, p2_does, may_attack):
    """508.1c: creatures can't attack a player unless that player cast a spell or put a nontoken permanent onto the battlefield (a land played counts, a token does not)."""
    from app.rules import combat
    from app.rules.plan import Plan

    s, bear = _arboria_turn3(cards, p2_does)
    plan = Plan(s.state, "p1", s.cards, None)
    assert combat.attack_forbidden(plan, plan.ch(s.state.cards[bear.id]), "p2") is (not may_attack)
    check(s)


def test_arboria_a_player_with_no_turn_yet_cannot_be_attacked(cards):
    """No last turn means no spell and no nontoken permanent: Bob has not taken a turn yet, so Alice's creatures can't attack him."""
    from app.rules import combat
    from app.rules.plan import Plan

    s = build(cards, ["Arboria", "Test Bear"])
    put(s, "Arboria")
    bear = put(s, "Test Bear")
    plan = Plan(s.state, "p1", s.cards, None)
    assert combat.attack_forbidden(plan, plan.ch(s.state.cards[bear.id]), "p2") is True


@pytest.mark.parametrize(
    ("text", "pool", "expected"),
    [
        ("{G}", {"W": 1}, True), ("{G}", {"G": 1}, False), ("{1}{G}", {"G": 1, "W": 1}, True), ("{1}{G}", {"G": 2}, False),
        ("{U}{B}", {"W": 2}, True), ("{U}{B}", {"W": 1, "U": 1}, False), ("{C}", {"G": 1}, True), ("{C}", {"W": 1}, False),
        ("{R/G}", {"W": 1}, True), ("{R/G}", {"R": 1}, False), ("{2/B}", {"U": 2}, True), ("{G}{G}", {"W": 1, "G": 1}, False),
    ],
)
def test_celestial_dawn_white_pays_any_color_and_other_mana_only_generic(text, pool, expected):
    """609.4b: white mana is spent as mana of any color; other mana only as colorless (it pays generic and {C}, never a colored symbol)."""
    from app.rules import mana as M

    try:
        M.solve(M.spend_as(M.parse_cost(text), "white_any"), pool, [])
    except M.ManaError:
        assert not expected
    else:
        assert expected


def test_celestial_dawn_in_a_real_cast_white_pays_green(cards):
    """Test Bear {1}{G} cast with W+W from the pool while Celestial Dawn is out (its lands are Plains, so only white is around)."""
    from tests.game_helpers import act

    s = build(cards, ["Celestial Dawn", "Test Bear"])
    put(s, "Celestial Dawn")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bear").id)
    answer(s)
    assert s.state.cards[card_named(s, "Test Bear").id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("picks", [(0, 1), (1, 1), (0, 0)])
def test_exotic_pets_puts_one_counter_of_each_kind_on_either_token(cards, picks):
    """122.1: kinds among your creatures are counted as the spell resolves (+1/+1 and flying here, two creatures with +1/+1 count once); each kind goes on a token you choose."""
    from tests.game_helpers import act
    from tests.test_rules_conditionals import creature

    s = build(cards, ["Exotic Pets"])
    for i in range(2):
        c = creature(s, "p1", f"Host{i}", "1/1")
        act(s, "p1", type="set_counter", card_id=c.id, kind="+1/+1", value=1)
    act(s, "p1", type="set_counter", card_id=c.id, kind="flying", value=1)
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Exotic Pets").id)
    asked, chosen = 0, []
    while s.state.zones.get("stack") or s.state.rules.decision is not None:
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        assert len(d.options) == 2
        chosen.append(d.options[picks[asked]].id)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[chosen[-1]])
        asked += 1
    fish = [c for c in s.state.cards.values() if c.name == "Fish" and c.zone == "p1:battlefield"]
    assert asked == 2 and len(fish) == 2
    assert s.state.cards[chosen[0]].counters.get("+1/+1") == 1 and s.state.cards[chosen[1]].counters.get("flying") == 1  # (sorted kinds: +1/+1 first)
    check(s)


def test_exotic_pets_without_counters_just_makes_the_tokens(cards):
    from tests.game_helpers import act

    s = build(cards, ["Exotic Pets"])
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Exotic Pets").id)
    answer(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Fish" and c.zone == "p1:battlefield") == 2
    check(s)
