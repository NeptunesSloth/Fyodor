"""Wave 110J session 6: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 122.1, 115.1: Simic Guildmage moves a +1/+1 counter between two creatures that have the same controller (Bioshift-style "that player").
* 303.4, 701.3b: Simic Guildmage moves an Aura attached to a permanent to another permanent controlled by the controller of its current host;
  an Aura that can't enchant the new permanent stays where it is.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    ability,
    activate,
    card_db,
    cast_on,
    check,
    full,
    mana,
    now,
    put_new,
    settle,
    to_hand,
)

GUILD = "Simic Guildmage"


@pytest.mark.parametrize("name", [GUILD, "Jester's Mask"])
def test_the_cards_are_full(name):
    assert full(name)


def _guild(cards, theirs=("Grizzly Bears", "Grizzly Bears")):
    s = build(cards, [GUILD, "Grizzly Bears", "Ray of Frost", "Kudzu", "Forest"], list(theirs))
    return s, put_new(s, GUILD)


def test_guildmage_moves_a_counter_to_a_creature_with_the_same_controller(cards):
    s, g = _guild(cards)
    a, b = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Grizzly Bears", "p2")
    act(s, "p1", type="counter", card_ids=[a.id], kind="+1/+1", delta=2)
    mana(s, G=1, C=1)
    activate(s, g, "{1}{G}", targets=[a.id, b.id], target_counts=[1, 1])
    assert now(s, a).counters == {"+1/+1": 1} and now(s, b).counters == {"+1/+1": 1}
    check(s)


def test_guildmage_counter_refuses_creatures_of_two_players(cards):
    s, g = _guild(cards, theirs=("Grizzly Bears",))
    a, c = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Grizzly Bears", "p1")
    act(s, "p1", type="counter", card_ids=[a.id], kind="+1/+1", delta=1)
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=g.id, ability=ability(s, g, "{1}{G}"), targets=[a.id, c.id], target_counts=[1, 1])


def test_guildmage_moves_an_aura_to_another_permanent_of_its_hosts_controller(cards):
    s, g = _guild(cards)
    a, b = put_new(s, "Grizzly Bears", "p2"), put_new(s, "Grizzly Bears", "p2")
    ray = cast_on(s, "Ray of Frost", a)
    assert ray.attached_to == a.id
    mana(s, U=1, C=1)
    activate(s, g, "{1}{U}", targets=[ray.id, b.id], target_counts=[1, 1])
    assert now(s, ray).attached_to == b.id
    check(s)


@pytest.mark.parametrize("pick", ["same", "mine"])
def test_guildmage_aura_refuses_the_same_host_and_another_controllers_permanent(cards, pick):
    s, g = _guild(cards)
    a = put_new(s, "Grizzly Bears", "p2")
    mine = put_new(s, "Grizzly Bears", "p1")
    ray = cast_on(s, "Ray of Frost", a)
    mana(s, U=1, C=1)
    target = a if pick == "same" else mine
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=g.id, ability=ability(s, g, "{1}{U}"), targets=[ray.id, target.id], target_counts=[1, 1])


def test_guildmage_aura_that_cant_enchant_the_new_permanent_stays_put(cards):
    s, g = _guild(cards)
    land = put_new(s, "Forest", "p1")
    bears = put_new(s, "Grizzly Bears", "p1")
    kudzu = cast_on(s, "Kudzu", land)
    assert kudzu.attached_to == land.id
    mana(s, U=1, C=1)
    activate(s, g, "{1}{U}", targets=[kudzu.id, bears.id], target_counts=[1, 1])
    assert now(s, kudzu).attached_to == land.id  # 303.4i / 701.3b: Kudzu enchants lands only
    check(s)


def test_jesters_mask_lets_the_activator_pick_any_cards_to_replace_the_hand(cards):
    """701.23a, 701.24: the opponent's hand goes on top of their library, the activator searches it for that many cards, they go to the hand, then a shuffle."""
    from app.game.state import zone_key

    s = build(cards, ["Jester's Mask"], ["Llanowar Elves", "Grizzly Bears", "Forest", "Island", "Forest"])
    mask = put_new(s, "Jester's Mask")
    hand = [to_hand(s, n, "p2") for n in ("Llanowar Elves", "Grizzly Bears")]
    lib = list(s.state.zones[zone_key("p2", "library")])
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=mask.id, ability=ability(s, mask, "{1}"), targets=["p2"])
    for _ in range(5):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"  # the activator searches (701.23a)
    wanted = [c for c in lib if s.state.cards[c].name == "Island"][:1] + [c for c in lib if s.state.cards[c].name == "Forest"][:1]
    settle(s, answers=[wanted])
    assert sorted(s.state.zones[zone_key("p2", "hand")]) == sorted(wanted)
    assert now(s, mask).zone.endswith(":graveyard")
    assert len(s.state.zones[zone_key("p2", "library")]) == len(lib) + len(hand) - 2
    check(s)


def test_jesters_mask_with_an_empty_hand_searches_for_nothing(cards):
    from app.game.state import zone_key

    s = build(cards, ["Jester's Mask"], ["Forest", "Island"])
    mask = put_new(s, "Jester's Mask")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=mask.id, ability=ability(s, mask, "{1}"), targets=["p2"])
    for _ in range(5):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0  # a search for 0 cards is still a search (701.23b)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    assert s.state.zones[zone_key("p2", "hand")] == []
    check(s)


TOWASHI, CATHAR = "Corruption of Towashi", "Brutal Cathar // Moonrage Brute"


def _draws(s):
    from app.game.state import zone_key

    return len(s.state.zones[zone_key("p1", "hand")])


def _flip_night(s):
    act(s, "p1", type="set_day_night", value="night")


def test_towashi_is_full():
    assert full(TOWASHI)


def _towashi_world(cards):
    s = build(cards, [TOWASHI, CATHAR, "Grizzly Bears", "Forest", "Forest", "Forest"], ["Grizzly Bears"])
    return s


def test_towashi_draws_when_a_permanent_you_control_transforms(cards):
    """701.28: the Incubator token turning into a Phyrexian creature is a permanent of yours transforming; the draw is optional."""
    s = _towashi_world(cards)
    cast_on(s, TOWASHI)
    token = next(c for c in s.state.cards.values() if c.name == "Incubator" and c.zone == "p1:battlefield")
    before = _draws(s)
    mana(s, C=2)
    activate(s, token, "{2}")
    assert token.id and s.state.cards[token.id].face == 1
    assert _draws(s) == before + 1
    check(s)


def test_towashi_draws_when_a_permanent_enters_transformed(cards):
    """702.145b, 712.14a: a daybound permanent cast at night enters transformed (no transformation happens), which Towashi sees."""
    s = _towashi_world(cards)
    put_new(s, TOWASHI)
    _flip_night(s)
    c = to_hand(s, CATHAR)
    before = _draws(s)
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert now(s, c).face == 1 and _draws(s) == before - 1 + 1  # cast (-1 hand), then the draw (+1)
    check(s)


def test_towashi_ignores_a_permanent_that_enters_front_face_up(cards):
    s = _towashi_world(cards)
    put_new(s, TOWASHI)
    c = to_hand(s, CATHAR)
    before = _draws(s)
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert now(s, c).face == 0 and _draws(s) == before - 1
    check(s)


MDFC = "Twin Test // Twin Test Giant"
EXTRA.append(card(MDFC, set_code="w110j", number="D990", layout="modal_dfc", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf // Creature — Giant",
                  colors=["G"], color_identity=["G"],
                  card_faces=[{"object": "card_face", "name": "Twin Test", "mana_cost": "{G}", "type_line": "Creature — Elf", "oracle_text": "", "power": "1", "toughness": "1"},
                              {"object": "card_face", "name": "Twin Test Giant", "mana_cost": "{G}", "type_line": "Creature — Giant", "oracle_text": "", "power": "4", "toughness": "4"}]))


def test_towashi_ignores_a_modal_dfc_cast_back_face_up(cards):
    """712.14a, 701.28: only transforming DFCs transform; a modal DFC's back face entering (712.4) is not "entering transformed"."""
    s = build(cards, [TOWASHI, MDFC, "Forest", "Forest", "Forest"], ["Grizzly Bears"])
    put_new(s, TOWASHI)
    c = to_hand(s, MDFC)
    before = _draws(s)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=c.id, face=1)
    settle(s)
    assert now(s, c).face == 1 and now(s, c).zone == "p1:battlefield" and _draws(s) == before - 1
    check(s)


def test_towashi_draws_only_once_each_turn(cards):
    """603.2h: "Do this only once each turn": the second event of the same turn draws nothing."""
    s = _towashi_world(cards)
    cast_on(s, TOWASHI)
    token = next(c for c in s.state.cards.values() if c.name == "Incubator" and c.zone == "p1:battlefield")
    _flip_night(s)
    c = to_hand(s, CATHAR)
    start = _draws(s)
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    after_first = _draws(s)
    assert after_first == start  # cast (-1), first draw (+1)
    mana(s, C=2)
    activate(s, token, "{2}")
    assert s.state.cards[token.id].face == 1 and _draws(s) == after_first
    check(s)


EVE = "All Hallow's Eve"


def test_all_hallows_eve_ticks_down_on_its_owners_upkeeps_then_returns_every_creature(cards):
    """608.2n, 603.4: the spell exiles itself with two scream counters; at each of its owner's upkeeps it loses one; with none left it goes to the
    graveyard and every player's creature cards return from their graveyard to the battlefield."""
    from tests.wave110j_kit import grave_new, to_phase

    assert full(EVE)
    s = build(cards, [EVE, "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    mine, theirs = grave_new(s, "Grizzly Bears", "p1"), grave_new(s, "Grizzly Bears", "p2")
    eve = cast_on(s, EVE)
    assert eve.zone == "p1:exile" and eve.counters == {"scream": 2}
    to_phase(s, "main1", turn=3)  # p1's next turn: one counter off (turn 2 was p2's upkeep: no tick)
    assert now(s, eve).zone == "p1:exile" and now(s, eve).counters == {"scream": 1}
    assert now(s, mine).zone.endswith(":graveyard")
    to_phase(s, "main1", turn=5)
    assert now(s, eve).zone == "p1:graveyard" and not now(s, eve).counters
    assert now(s, mine).zone == "p1:battlefield" and now(s, theirs).zone == "p2:battlefield"  # each under its owner's control (400.3)
    check(s)


RES = "Churning Reservoir"


def _goblins(s):
    return sum(1 for c in s.state.cards.values() if c.name == "Phyrexian Goblin" and c.zone == "p1:battlefield")


@pytest.mark.parametrize(("what", "ok"), [
    ("nothing", False),
    ("mine_removed", True),
    ("theirs_removed", False),  # "a permanent you controlled"
    ("theirs_died", True),  # any permanent with an oil counter put into a graveyard
    ("mine_died", True),
])
def test_churning_reservoir_activates_only_after_oil_was_removed_or_a_permanent_with_oil_died(cards, what, ok):
    """122.1, 603.10a: the history is this turn's: a counter removed from your permanent, or a permanent that had an oil counter going to a graveyard."""
    s = build(cards, [RES, "Grizzly Bears"], ["Grizzly Bears"])
    res = put_new(s, RES)
    s.state.rules.controlled_since[res.id].turn = 0
    mine, theirs = put_new(s, "Grizzly Bears", "p1"), put_new(s, "Grizzly Bears", "p2")
    for c in (mine, theirs):
        act(s, "p1", type="counter", card_ids=[c.id], kind="oil", delta=1)
    if what == "mine_removed":
        act(s, "p1", type="counter", card_ids=[mine.id], kind="oil", delta=-1)
    elif what == "theirs_removed":
        act(s, "p1", type="counter", card_ids=[theirs.id], kind="oil", delta=-1)
    elif what in ("theirs_died", "mine_died"):
        c = theirs if what == "theirs_died" else mine
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    mana(s, C=2)
    if ok:
        activate(s, res, "{2}, {T}")
        assert _goblins(s) == 1
        check(s)
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", card_id=res.id, ability=ability(s, res, "{2}, {T}"))


def test_churning_reservoir_ignores_a_permanent_without_an_oil_counter_dying(cards):
    s = build(cards, [RES, "Grizzly Bears"])
    res = put_new(s, RES)
    s.state.rules.controlled_since[res.id].turn = 0
    bears = put_new(s, "Grizzly Bears", "p1")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    mana(s, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=res.id, ability=ability(s, res, "{2}, {T}"))


LIVIO = "Livio, Oathsworn Sentinel"


def _aegis(s, target, yes):
    """Livio's first ability on ``target``: the creature's controller gets the question (608.2d)."""
    livio = next(c for c in s.state.cards.values() if c.name == LIVIO)
    mana(s, W=1, C=1)
    act(s, "p1", type="activate_ability", card_id=livio.id, ability=ability(s, livio, "{1}{W}"), targets=[target.id])
    for _ in range(5):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == s.state.cards[target.id].controller
    pick = next(o.id for o in d.options if o.id == ("yes" if yes else "no") or o.label.lower().startswith("yes" if yes else "no"))
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    settle(s)


@pytest.mark.parametrize("yes", [True, False])
def test_livio_lets_the_creatures_controller_choose_to_exile_it_with_an_aegis_counter(cards, yes):
    assert full(LIVIO)
    s = build(cards, [LIVIO, "Grizzly Bears"], ["Grizzly Bears"])
    put_new(s, LIVIO)
    theirs = put_new(s, "Grizzly Bears", "p2")
    _aegis(s, theirs, yes)
    if yes:
        assert now(s, theirs).zone == "p2:exile" and now(s, theirs).counters == {"aegis": 1}
    else:
        assert now(s, theirs).zone == "p2:battlefield" and not now(s, theirs).counters
    check(s)


def test_livio_returns_every_exiled_card_with_an_aegis_counter_under_its_owners_control(cards):
    s = build(cards, [LIVIO, "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    livio = put_new(s, LIVIO)
    s.state.rules.controlled_since[livio.id].turn = 0
    mine, theirs, plain = put_new(s, "Grizzly Bears", "p1"), put_new(s, "Grizzly Bears", "p2"), put_new(s, "Llanowar Elves", "p1")
    _aegis(s, mine, True)
    _aegis(s, theirs, True)
    act(s, "p1", type="move", card_ids=[plain.id], to={"zone": "exile"})  # exiled, but with no aegis counter
    mana(s, W=1, C=2)
    activate(s, livio, "{2}{W}, {T}")
    assert now(s, mine).zone == "p1:battlefield" and now(s, theirs).zone == "p2:battlefield" and now(s, plain).zone == "p1:exile"
    assert not now(s, mine).counters and not now(s, theirs).counters
    check(s)
