"""Wave 53A: another player's library searched, and "that player" of a trigger (CR 2026-09-25), real Oracle text (tests/fixtures/wave53a_cards.json, from data/cards.sqlite). Every
scenario checks the replay and a save and a load.

* 701.23a, 701.24a, 406.3: "Search target opponent's library for a card and exile it face down. Then that player shuffles. You may play that card for as long as it remains exiled."
  (Praetor's Grasp) - the controller searches it and picks; the card is exiled face down (only she may look); the opponent's library is shuffled; she may play it.
* 603.2, 608.2k: "Whenever this creature deals combat damage to a player, search that player's library for an artifact card and exile it. Then that player shuffles. Until end of turn, you may
  play that card." (Thada Adel, Acquisitor); "you may pay {2}. If you do, search that player's library for a card and exile it, then the player shuffles." (Rootwater Thief).
* 601.2c, 702.33: "Search target player's library for up to three cards, exile them, then that player shuffles. If this spell was kicked, instead search that player's library for up to
  fifteen cards" (Sadistic Sacrament).
* 401.5, 701.20 (look), 508.5: "you may look at the top card of target opponent's library. If you do, you may put that card on the bottom of that player's library." (Precognition),
  "look at the top card of defending player's library. You may put that card on the bottom of that player's library." (Coral Fighters) - only the looker sees the card.
"""

from __future__ import annotations

import pytest

from app.game.visibility import SPECTATOR
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave34b_activated import attack, stops, to_phase
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave53a_kit import alice_next, open_repo, table, unseen_by, until_asked

BEARS, GIANT, GRAIL = "Grizzly Bears", "Hill Giant", "Sol Grail"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", ["Praetor's Grasp", "Thada Adel, Acquisitor", "Rootwater Thief", "Sadistic Sacrament", "Precognition", "Coral Fighters", "Thieving Amalgam", "Orochi Soul-Reaver"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def lib_names(s, pid):
    return sorted(s.state.cards[c].name for c in s.state.zones[f"{pid}:library"])


def pick(s, d, name):
    return [o.id for o in d.options if s.state.cards[o.id].name == name][:1]


# -- Praetor's Grasp ----------------------------------------------------------------------------------------------------------------------
def test_praetors_grasp_exiles_a_card_of_the_opponents_library_face_down_and_you_may_play_it(cards):
    s = table(cards, ["Praetor's Grasp"], [BEARS, GIANT], [BEARS])
    to_hand(s, "Praetor's Grasp")
    mana(s, "p1", B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Praetor's Grasp").id, targets=["p2"])
    d = until_asked(s)
    assert d.player == "p1" and {s.state.cards[o.id].owner for o in d.options} == {"p2"}  # Bob's library, Alice picks
    for viewer in ("p2", "p3", SPECTATOR):  # the question and its options reach nobody else
        assert "options" not in s.view(viewer)["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=pick(s, d, BEARS))
    settle(s)
    bears = next(c for c in s.state.cards.values() if c.name == BEARS and c.owner == "p2" and c.zone == "p2:exile")
    assert bears.face_down
    assert unseen_by(s, bears, "p2", "p3", SPECTATOR) and not unseen_by(s, bears, "p1")  # Bob doesn't see his own card either: only the player who exiled it looks (406.3)
    # she may play it (a creature spell, for its mana cost, at sorcery speed) for as long as it remains exiled
    mana(s, "p1", G=1, C=1)
    assert bears.id in s.view("p1")["rules"]["hints"]["castable"]
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and not s.state.cards[bears.id].face_down  # Alice's now, face up
    check(s)


def test_praetors_grasp_the_library_is_shuffled(cards):
    s = table(cards, ["Praetor's Grasp"], [BEARS, GIANT], [])
    to_hand(s, "Praetor's Grasp")
    mana(s, "p1", B=2, C=1)
    ids_before = list(s.state.zones["p2:library"])
    before = [s.state.cards[c].name for c in ids_before]
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Praetor's Grasp").id, targets=["p2"])
    d = until_asked(s)
    giant_id = pick(s, d, GIANT)[0]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[giant_id])
    settle(s)
    ids_after = list(s.state.zones["p2:library"])
    after = [s.state.cards[c].name for c in ids_after]
    assert sorted(after) == sorted(before[:1] + before[2:])  # one Giant fewer, the rest the same cards
    assert ids_after != [i for i in ids_before if i != giant_id]  # shuffled (compare ids: a shuffle can leave the names in order)
    check(s)


# -- Thada Adel, Acquisitor ------------------------------------------------------------------------------------------------------------
def test_thada_adel_exiles_an_artifact_from_that_players_library_and_you_may_play_it_this_turn(cards):
    s = table(cards, ["Thada Adel, Acquisitor"], [BEARS, GRAIL], [BEARS, GRAIL])  # (Bob and Carol each draw the first card on their turn)
    stops(s)
    thada = put(s, "Thada Adel, Acquisitor")
    alice_next(s)
    attack(s, thada)  # islandwalk: Bob has Islands, so she is unblockable
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and all(s.state.cards[o.id].zone == "p2:library" for o in d.options):
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and {s.state.cards[o.id].name for o in d.options} == {GRAIL}  # Bob's artifact cards only
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    settle(s)
    grail = next(c for c in s.state.cards.values() if c.name == GRAIL and c.owner == "p2" and c.zone == "p2:exile")
    assert not grail.face_down and next(c for c in s.state.cards.values() if c.name == GRAIL and c.owner == "p3").zone == "p3:library"  # Carol's library isn't searched
    to_phase(s, "main2")
    mana(s, "p1", C=3)
    assert grail.id in s.view("p1")["rules"]["hints"]["castable"]
    act(s, "p1", type="cast_spell", card_id=grail.id)
    settle(s)
    assert s.state.cards[grail.id].zone == "p1:battlefield"
    check(s)


# -- Rootwater Thief ---------------------------------------------------------------------------------------------------------------------
def thief_hits(cards, pay):
    s = table(cards, ["Rootwater Thief"], [BEARS, GIANT], [])
    stops(s)
    thief = put(s, "Rootwater Thief")
    alice_next(s)
    attack(s, thief)
    paid = False
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack") and s.state.turn.phase == "combat_damage" and not paid:
                mana(s, "p1", C=2)  # the trigger is on the stack: the mana is there to pay with when it resolves
                paid = True
            elif not s.state.zones.get("stack") and s.state.turn.phase in ("end_combat", "main2"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif {"pay", "decline"} <= {o.id for o in d.options}:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    return s


def test_rootwater_thief_paying_two_searches_that_players_library(cards):
    s = thief_hits(cards, True)
    assert sorted(s.state.cards[c].name for c in s.state.zones["p2:exile"]) in ([BEARS], [GIANT]) and len(s.state.zones["p2:exile"]) == 1
    check(s)


def test_rootwater_thief_not_paying_searches_nothing(cards):
    s = thief_hits(cards, False)
    assert s.state.zones.get("p2:exile", []) == []
    check(s)


# -- Sadistic Sacrament ------------------------------------------------------------------------------------------------------------------
def test_sadistic_sacrament_exiles_up_to_three_cards(cards):
    s = table(cards, ["Sadistic Sacrament"], [BEARS, GIANT, GRAIL], [])
    to_hand(s, "Sadistic Sacrament")
    mana(s, "p1", B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sadistic Sacrament").id, targets=["p2"])
    d = until_asked(s)
    assert d.player == "p1" and d.max_choices == 3
    act(s, "p1", type="choose", decision_id=d.id, option_ids=pick(s, d, BEARS) + pick(s, d, GIANT))
    settle(s)
    assert sorted(s.state.cards[c].name for c in s.state.zones["p2:exile"]) == [BEARS, GIANT]
    check(s)


def test_sadistic_sacrament_kicked_searches_for_up_to_fifteen(cards):
    s = table(cards, ["Sadistic Sacrament"], [BEARS, GIANT, GRAIL], [])
    to_hand(s, "Sadistic Sacrament")
    mana(s, "p1", B=3, C=7)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sadistic Sacrament").id, targets=["p2"], kicker=1)
    d = until_asked(s)
    in_library = len(s.state.zones["p2:library"])
    assert d.max_choices == min(15, in_library) and in_library == 13  # three named cards and ten Islands: fewer than fifteen to find
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:15])
    settle(s)
    assert len(s.state.zones["p2:exile"]) == in_library and s.state.zones["p2:library"] == []
    check(s)


# -- Precognition / Coral Fighters ------------------------------------------------------------------------------------------------------
def ask(s, kind=None, limit=60):
    """Pass priority (no attackers, no blockers) until a decision of this kind is open."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers") and kind != d.kind:
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            return d
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


def test_precognition_you_look_at_the_top_card_and_may_put_it_on_the_bottom(cards):
    """The target opponent's top card is seen by Alice alone; if she puts it on the bottom it is the bottom of Bob's library (not shuffled, not Carol's)."""
    s = table(cards, ["Precognition"], [BEARS, GIANT, "Serra Angel"], [GIANT])
    put(s, "Precognition")
    d = ask(s)  # (Alice's next upkeep: Bob has drawn since)
    assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}  # target opponent
    top = s.state.zones["p2:library"][0]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    d = ask(s)
    assert d.kind == "confirm" and d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = ask(s)
    assert d.player == "p1" and top in {o.id for o in d.options}  # the card she saw
    assert not unseen_by(s, s.state.cards[top], "p1") and unseen_by(s, s.state.cards[top], "p2", "p3", SPECTATOR)  # nobody else sees it
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[top])
    settle(s)
    assert s.state.zones["p2:library"][-1] == top and s.state.zones["p2:library"][0] != top
    check(s)


def test_precognition_the_player_may_decline_to_look(cards):
    s = table(cards, ["Precognition"], [BEARS, GIANT], [GIANT])
    put(s, "Precognition")
    d = ask(s)
    before = list(s.state.zones["p2:library"])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    settle(s)
    assert list(s.state.zones["p2:library"]) == before
    check(s)


def test_coral_fighters_look_at_the_defending_players_top_card_only(cards):
    """508.5: the player the Fighters attack (Bob, not Carol); the card goes to the bottom of his library when she says so."""
    s = table(cards, ["Coral Fighters"], [BEARS, GIANT], [GIANT])
    stops(s)
    fighters = put(s, "Coral Fighters")
    alice_next(s)
    top, ctop = s.state.zones["p2:library"][0], s.state.zones["p3:library"][0]
    attack(s, fighters)
    d = None
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and d.kind not in ("declare_attackers", "declare_blockers"):
            break
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[]) if d.kind == "declare_blockers" else act(
                s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and top in {o.id for o in d.options}, d
    assert unseen_by(s, s.state.cards[top], "p2", "p3", SPECTATOR)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[top])
    settle(s)
    assert s.state.zones["p2:library"][-1] == top and s.state.zones["p3:library"][0] == ctop
    check(s)


# -- Thieving Amalgam / Orochi Soul-Reaver ----------------------------------------------------------------------------------------------
def test_thieving_amalgam_manifests_the_top_card_of_each_opponents_library_at_their_upkeep(cards):
    """701.40a: the top card of that player's library goes onto the battlefield face down under your control as a 2/2 (it is still their card, 108.3); nobody but its controller can look at it."""
    s = table(cards, ["Thieving Amalgam"], [BEARS, GIANT, "Serra Angel"], [GIANT])
    put(s, "Thieving Amalgam")
    top, carols_top = s.state.zones["p2:library"][0], s.state.zones["p3:library"][0]
    top_name = s.state.cards[top].name
    for _ in range(40):
        if s.state.turn.number == 2 and s.state.turn.phase == "main1":  # (past Bob's upkeep)
            break
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    c = next(x for x in s.state.cards.values() if x.face_down)  # (a new object: 400.7)
    assert c.name == top_name and c.zone == "p1:battlefield" and c.controller == "p1" and c.owner == "p2"
    assert s.state.cards[carols_top].zone == "p3:library"  # only the opponent whose upkeep it is
    assert not unseen_by(s, c, "p1")  # Alice looks at her face-down creature
    assert unseen_by(s, c, "p2", "p3", SPECTATOR)
    check(s)


def test_orochi_soul_reaver_combat_damage_to_a_player_makes_a_treasure_and_manifests_their_top_card(cards):
    s = table(cards, ["Orochi Soul-Reaver", BEARS], [BEARS, GIANT, "Serra Angel"], [GIANT])
    stops(s)
    snake = put(s, "Orochi Soul-Reaver")
    alice_next(s)
    top_name = s.state.cards[s.state.zones["p2:library"][0]].name
    attack(s, snake)
    for _ in range(40):
        d = s.state.rules.decision
        if any(c.name == "Treasure" for c in s.state.cards.values()) or s.state.turn.phase in ("main2", "end"):
            break
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    c = next(x for x in s.state.cards.values() if x.face_down)
    assert c.name == top_name and c.zone == "p1:battlefield" and c.controller == "p1" and c.owner == "p2"  # Bob's card, the player dealt damage
    assert unseen_by(s, c, "p2", "p3", SPECTATOR)
    assert any(x.name == "Treasure" and x.controller == "p1" for x in s.state.cards.values())
    check(s)
