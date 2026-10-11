"""Wave 31B: "each player / opponent may [do it]" for an action that is no cost, asked of every player in turn order (CR 2026-09-25), real
Oracle text (tests/fixtures/wave31b_per_player_cards.json, from data/cards.sqlite). Every scenario has three players, answers that differ,
a replay and a save and a load.

* 101.4: the players decide in APNAP order, each in turn; the answers are private decisions (nothing but the player's own prompt shows them).
* 608.2d: a player who may do something decides as the effect is applied; one who says yes does it (they are "you" for it: their library,
  their tokens), one who says no does nothing.
* "Each player who drew a card this way gains 1 life" (Kwain), "For each opponent who does, you create a Treasure token." (Tempting Contract),
  "Then each player who searched their library this way shuffles." (Noble Benefactor, 701.19): what the answers give.
* "Each opponent chooses a creature they control. You gain control of those creatures." (Riches): every opponent's choice, then the control change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana
from tests.wave9c_kit import check

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave31b_per_player_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w31b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build3(cards, mine=(), bob=(), carol=()):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (20, "Mountain")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")]),
             deck(cards, "Krenko, Mob Boss", [*((1, n) for n in carol), (20, "Forest")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_hand(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def on_field(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def on_top(s, name, pid):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def library(s, pid):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:library"]]


def zone_names(s, pid, z):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:{z}"]]


def answer(s, pid, *ids):
    """The pending decision is ``pid``'s: answer it."""
    d = s.state.rules.decision
    assert d is not None and d.player == pid, (d and (d.player, d.prompt))
    act(s, pid, type="choose", decision_id=d.id, option_ids=list(ids))


def until_asked(s, limit=60):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            return d
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("still resolving")


def finish(s, limit=60):
    """Resolve what is left; any other question is answered with its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_alices_turn(s, limit=200):
    """Pass until the next time Alice's upkeep trigger asks (turn 4 of three players)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "confirm":
            return d
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def to_main(s, number, limit=200):
    for _ in range(limit):
        if s.state.turn.number == number and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def treasures(s, pid):
    return sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.controller == pid and c.zone.endswith(":battlefield"))


@pytest.mark.parametrize("name", ["Eager Construct", "Myr Custodian", "Kaya, Intangible Slayer", "Jungle Wayfinder", "Noble Benefactor",
                                  "Tempting Contract", "Kwain, Itinerant Meddler", "Rags // Riches", "Sadistic Shell Game", "Druid of Purification",
                                  "The Horus Heresy", "The Legend of Yangchen // Avatar Yangchen", "Turtles in Time", "Step Between Worlds",
                                  "Weird Harvest"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_eager_construct_each_player_decides_in_turn_order_then_scries(cards):
    """Eager Construct: "When this creature enters, each player may scry 1." Alice yes, Bob no, Carol yes."""
    s = build3(cards, mine=["Eager Construct", "Giant Growth"], bob=["Lightning Bolt"], carol=["Sol Ring"])
    on_top(s, "Giant Growth", "p1")
    on_top(s, "Lightning Bolt", "p2")
    on_top(s, "Sol Ring", "p3")
    c = to_hand(s, "Eager Construct")
    mana(s, "p1", C=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["yes", "no"]  # Alice first (101.4)
    assert "options" not in s.view("p2")["rules"]["decision"]  # (the question is hers)
    check(s)  # (a save with Alice's answer pending)
    answer(s, "p1", "yes")
    answer(s, "p2", "no")  # Bob is asked before anything is scried
    answer(s, "p3", "yes")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.kind == "choose_cards" and "Scry 1" in d.prompt  # the scries follow, Alice's own
    answer(s, "p1", d.options[0].id)  # Giant Growth to the bottom
    d = s.state.rules.decision
    assert d is not None and d.player == "p3" and "Scry 1" in d.prompt
    answer(s, "p3")  # Carol keeps hers on top
    finish(s)
    assert library(s, "p1")[-1] == "Giant Growth" and library(s, "p1")[0] != "Giant Growth"
    assert library(s, "p2")[0] == "Lightning Bolt"  # (Bob said no: his top card stayed)
    assert library(s, "p3")[0] == "Sol Ring"
    check(s)


def test_myr_custodian_only_the_opponents_are_asked(cards):
    """Myr Custodian: "scry 2. Then each opponent may scry 1." Alice scries by the first sentence; Bob yes, Carol no."""
    s = build3(cards, mine=["Myr Custodian", "Giant Growth", "Sol Ring"], bob=["Lightning Bolt"])
    on_top(s, "Giant Growth", "p1")
    on_top(s, "Lightning Bolt", "p2")
    c = to_hand(s, "Myr Custodian")
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "choose_cards" and "Scry 2" in d.prompt
    answer(s, "p1")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.kind == "order"  # (the order of her two cards on top)
    answer(s, "p1", *[o.id for o in d.options])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.kind == "confirm"  # Alice is no opponent of herself: Bob is the first asked
    answer(s, "p2", "yes")
    answer(s, "p3", "no")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and "Scry 1" in d.prompt
    answer(s, "p2", d.options[0].id)
    finish(s)
    assert library(s, "p2")[-1] == "Lightning Bolt" and library(s, "p3")[0] != "Lightning Bolt"
    check(s)


def test_tempting_contract_you_get_one_treasure_per_opponent_who_did(cards):
    """Tempting Contract: "At the beginning of your upkeep, each opponent may create a Treasure token. For each opponent who does, you
    create a Treasure token." Run twice: only Bob says yes (1 + 1), then both (1 + 1 + 1 + 2 for Alice)."""
    for answers, expected in ((("yes", "no"), (1, 1, 0)), (("yes", "yes"), (2, 1, 1)), (("no", "no"), (0, 0, 0))):
        s = build3(cards, mine=["Tempting Contract"])
        on_field(s, "Tempting Contract")
        d = to_alices_turn(s)
        assert d.player == "p2" and s.state.turn.active_player == "p1"  # Alice is no opponent: Bob first, then Carol
        answer(s, "p2", answers[0])
        answer(s, "p3", answers[1])
        finish(s)
        assert tuple(treasures(s, p) for p in ("p1", "p2", "p3")) == expected, answers
        check(s)


def test_kwain_each_player_who_drew_gains_life(cards):
    """Kwain: "{T}: Each player may draw a card, then each player who drew a card this way gains 1 life." Alice yes, Bob no, Carol yes."""
    s = build3(cards, mine=["Kwain, Itinerant Meddler"])
    kwain = on_field(s, "Kwain, Itinerant Meddler")
    to_main(s, 4)  # (Alice's next turn: no longer summoning sick, 302.6)
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2", "p3")}
    life = {p: s.state.players[p].life for p in ("p1", "p2", "p3")}
    act(s, "p1", type="activate_ability", card_id=kwain.id, ability=0)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "confirm"
    answer(s, "p1", "yes")
    answer(s, "p2", "no")
    answer(s, "p3", "yes")
    finish(s)
    assert {p: len(s.state.zones[f"{p}:hand"]) - hands[p] for p in hands} == {"p1": 1, "p2": 0, "p3": 1}
    assert {p: s.state.players[p].life - life[p] for p in life} == {"p1": 1, "p2": 0, "p3": 1}
    check(s)


def test_noble_benefactor_each_player_searches_privately_and_only_searchers_shuffle(cards):
    """Noble Benefactor: "When this creature dies, each player may search their library for a card and put that card into their hand. Then
    each player who searched their library this way shuffles." Alice no, Bob yes (takes Lightning Bolt), Carol no."""
    s = build3(cards, mine=["Noble Benefactor"], bob=["Lightning Bolt", "Giant Growth"])
    nb = on_field(s, "Noble Benefactor")
    act(s, "p1", type="set_damage", card_ids=[nb.id], delta=20)  # (lethal damage: it dies, 704.5g)
    act(s, "p1", type="pass_priority")
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "confirm"
    answer(s, "p1", "no")
    answer(s, "p2", "yes")
    answer(s, "p3", "no")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.kind == "choose_cards"
    assert "options" not in s.view("p1")["rules"]["decision"] and "options" not in s.view("p3")["rules"]["decision"]  # (Bob's library is his)
    bolt = next(o.id for o in d.options if o.label == "Lightning Bolt")
    answer(s, "p2", bolt)
    finish(s)
    assert "Lightning Bolt" in zone_names(s, "p2", "hand") and "Lightning Bolt" not in library(s, "p2")
    assert "Lightning Bolt" not in zone_names(s, "p1", "hand") + zone_names(s, "p3", "hand")
    for viewer in ("p1", "p3"):  # what Bob took stays his: nobody else's log names it
        assert "Lightning Bolt" not in json.dumps(s.view(viewer)["log"]), viewer
    check(s)


def test_riches_every_opponent_chooses_then_you_gain_control_of_those_creatures(cards):
    """Rags // Riches (Riches, aftermath): "Each opponent chooses a creature they control. You gain control of those creatures." Bob has two
    creatures and chooses one; Carol has one; Alice's own is not hers to give."""
    s = build3(cards, mine=["Rags // Riches", "Llanowar Elves"], bob=["Grizzly Bears", "Llanowar Elves"], carol=["Llanowar Elves"])
    mine = on_field(s, "Llanowar Elves")
    bear = on_field(s, "Grizzly Bears", "p2")
    delver = on_field(s, "Llanowar Elves", "p2")
    elf3 = on_field(s, "Llanowar Elves", "p3")
    fc = named(s, "Rags // Riches")
    act(s, "p1", type="move", card_ids=[fc.id], to={"zone": "graveyard"})
    mana(s, "p1", C=5, U=2)
    act(s, "p1", type="cast_spell", card_id=fc.id, face=1)  # the aftermath half, from the graveyard
    d = until_asked(s)
    assert d is not None and d.player == "p2" and d.kind == "choose_cards"  # Bob chooses (Carol's single creature needs no choice)
    answer(s, "p2", bear.id)
    finish(s)
    ctl = {c.id: s.state.cards[c.id].controller for c in (mine, bear, delver, elf3)}
    assert ctl == {mine.id: "p1", bear.id: "p1", delver.id: "p2", elf3.id: "p1"}
    check(s)


def test_sadistic_shell_game_each_player_chooses_in_turn_order_from_the_next_opponent_then_all_chosen_are_destroyed(cards):
    """Sadistic Shell Game: "Starting with the next opponent in turn order, each player chooses a creature you don't control. Destroy the chosen
    creatures." Bob, Carol, then Alice choose (101.4); two may choose the same creature (it is destroyed once); Alice's own are not offered."""
    s = build3(cards, mine=["Sadistic Shell Game", "Llanowar Elves"], bob=["Grizzly Bears", "Llanowar Elves"], carol=["Llanowar Elves"])
    mine = on_field(s, "Llanowar Elves")
    bear = on_field(s, "Grizzly Bears", "p2")
    elf2 = on_field(s, "Llanowar Elves", "p2")
    elf3 = on_field(s, "Llanowar Elves", "p3")
    c = to_hand(s, "Sadistic Shell Game")
    mana(s, "p1", C=4, B=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = until_asked(s)
    assert d is not None and d.player == "p2" and d.kind == "choose_cards"  # the next opponent in turn order, not Alice
    assert {o.card_id for o in d.options} == {bear.id, elf2.id, elf3.id}  # (a creature Alice doesn't control)
    check(s)  # (a save with Bob's choice pending)
    answer(s, "p2", bear.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p3" and "already chosen" in d.prompt  # (101.4b: Carol knows Bob's choice)
    answer(s, "p3", bear.id)  # the same creature again
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"  # Alice chooses last
    answer(s, "p1", elf3.id)
    finish(s)
    gone = {x.id: s.state.cards[x.id].zone.endswith(":graveyard") for x in (mine, bear, elf2, elf3)}
    assert gone == {mine.id: False, bear.id: True, elf2.id: False, elf3.id: True}
    check(s)


def test_druid_of_purification_a_player_may_choose_none(cards):
    """Druid of Purification: "When this creature enters, starting with you, each player may choose an artifact or enchantment you don't
    control. Destroy each permanent chosen this way." Alice and Carol choose Bob's Sol Ring, Bob chooses nothing (always asked, 'may')."""
    s = build3(cards, mine=["Druid of Purification"], bob=["Sol Ring"], carol=["Sol Ring"])
    ring2 = on_field(s, "Sol Ring", "p2")
    ring3 = on_field(s, "Sol Ring", "p3")
    c = to_hand(s, "Druid of Purification")
    mana(s, "p1", C=3, G=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.min_choices == 0 and {o.card_id for o in d.options} == {ring2.id, ring3.id}
    answer(s, "p1", ring2.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.min_choices == 0  # (asked though only one thing could be chosen, 'may')
    answer(s, "p2")
    answer(s, "p3", ring2.id)
    finish(s)
    assert s.state.cards[ring2.id].zone == "p2:graveyard" and s.state.cards[ring3.id].zone == "p3:battlefield"
    check(s)


def test_weird_harvest_x_is_every_players_limit(cards):
    """Weird Harvest: "Each player may search their library for up to X creature cards, reveal those cards, put them into their hand, then
    shuffle." X = 1 (cast for {1}{G}{G}): Alice no, Bob yes (takes one of his two creatures, no more), Carol no."""
    s = build3(cards, mine=["Weird Harvest"], bob=["Grizzly Bears", "Llanowar Elves"])
    c = to_hand(s, "Weird Harvest")
    mana(s, "p1", C=1, G=2)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=1)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "confirm"
    answer(s, "p1", "no")
    answer(s, "p2", "yes")
    answer(s, "p3", "no")
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.max_choices == 1  # (up to X, here 1)
    answer(s, "p2", d.options[0].id)
    finish(s)
    assert zone_names(s, "p2", "hand") == ["Grizzly Bears"] and zone_names(s, "p1", "hand") == [] == zone_names(s, "p3", "hand")  # (one card: X = 1)
    check(s)


def test_turtles_in_time_the_players_who_shuffled_draw_seven(cards):
    """Turtles in Time: "Return all creatures to their owners' hands. Each player may shuffle their hand and graveyard into their library,
    then each player who does draws seven cards." Alice yes, Bob no (keeps his hand and graveyard), Carol yes; the draws wait for every shuffle."""
    s = build3(cards, mine=["Turtles in Time", "Giant Growth"], bob=["Lightning Bolt", "Grizzly Bears"], carol=["Sol Ring"])
    bear = on_field(s, "Grizzly Bears", "p2")
    for name, pid in (("Giant Growth", "p1"), ("Lightning Bolt", "p2"), ("Sol Ring", "p3")):
        act(s, pid, type="move", card_ids=[named(s, name, pid).id], to={"zone": "graveyard"})
    c = to_hand(s, "Turtles in Time")
    mana(s, "p1", C=5, U=2)
    bob_hand = len(s.state.zones["p2:hand"]) + 1  # (the Bear comes back to it)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "confirm" and s.state.cards[bear.id].zone == "p2:hand"  # (returned first)
    answer(s, "p1", "yes")
    answer(s, "p2", "no")
    answer(s, "p3", "yes")
    finish(s)
    assert len(s.state.zones["p1:hand"]) == 7 and len(s.state.zones["p3:hand"]) == 7
    assert zone_names(s, "p1", "graveyard") == [] and zone_names(s, "p3", "graveyard") == []
    assert len(s.state.zones["p2:hand"]) == bob_hand and zone_names(s, "p2", "graveyard") == ["Lightning Bolt"]
    check(s)
