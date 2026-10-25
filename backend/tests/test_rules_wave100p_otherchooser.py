"""Wave 100P: choices made by a player other than the controller, votes and piles (app/rules/otherchooser100p.py, voting.py,
trigger_upkeep_comparison75.py), real Oracle text (tests/fixtures/wave100p_otherchooser_cards.json; CR 2026-09-25). Every scenario checks the replay
and a save and a load.

* 701.38a: Will of the Planeswalkers — each player votes in turn order; 701.31a / 311.7: a Commander game is no Planechase game, so neither
  "planeswalk" nor "chaos ensues" does anything.
* Oath of Druids / Oath of Lieges: the player whose upkeep it is chooses the target (an opponent with more creatures / lands, rechecked on
  resolution: rulings 2009-10-01) and puts the card onto the battlefield under their own control (ruling 2004-10-04).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import check
from tests.wave100c_kit import cast, move, named, one, put_on, settle, three, to_phase, zone

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100p_otherchooser_cards.json").read_text("utf-8"))
PROMOTED = ["Path of the Animist", "Path of the Enigma", "Path of the Ghosthunter", "Path of the Pyromancer", "Path of the Schemer", "Oath of Druids",
            "Oath of Lieges"]


@pytest.fixture()
def cards(settings):
    known = {c["name"] for c in fixture_cards()}
    settings.ensure_dirs()
    build_database([*fixture_cards(), *(card(c["name"], set_code="w100p", number=f"P{i:03d}", **{k: v for k, v in c.items() if k != "name"})
                                        for i, c in enumerate(DATA) if c["name"] not in known)], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def hand(s, pid):
    return list(s.state.zones.get(f"{pid}:hand", []))


def log_text(s):
    return " ".join(str(e.model_dump()) for e in s.state.log)


# -- Will of the Planeswalkers -------------------------------------------------------------------------------------------------------------------
def test_path_of_the_enigma_draws_then_everyone_votes_and_nothing_planeswalks(cards):
    s = three(cards, ["Path of the Enigma"])
    before = len(hand(s, "p2"))
    voters = []
    c = one(s, "Path of the Enigma")
    move(s, c, "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1, "C": 4})
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            assert d.kind == "choose_one" and {o.id for o in d.options} == {"planeswalk", "chaos"}
            voters.append(d.player)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["planeswalk"])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert voters == ["p1", "p2", "p3"]  # 701.38a: starting with the caster, in turn order
    assert len(hand(s, "p2")) == before + 4
    assert "Not a Planechase game" in log_text(s) and zone(s, c) == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("held", [2, 0])
def test_path_of_the_pyromancer_adds_red_for_each_discard_and_draws_one_more(cards, held):
    s = three(cards, ["Path of the Pyromancer"])
    for cid in hand(s, "p1"):
        move(s, s.state.cards[cid], "library")
    for c in [x for x in s.state.cards.values() if x.owner == "p1" and x.name == "Forest"][:held]:
        move(s, c, "hand")
    cast(s, "Path of the Pyromancer", R=1, C=4)
    assert len([x for x in s.state.cards.values() if x.zone == "p1:graveyard" and x.name == "Forest"]) == held
    p1 = s.state.players["p1"]
    assert p1.mana.get("R", 0) + sum(u.sym == "R" for u in p1.mana_units) == held  # (ruling: an empty hand adds nothing, still draws one)
    assert len(hand(s, "p1")) == held + 1
    check(s)


# -- Oaths -----------------------------------------------------------------------------------------------------------------------------------------
def test_oath_of_druids_upkeep_player_targets_and_gets_the_creature(cards):
    s = three(cards, ["Oath of Druids"], ["Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    put_on(s, "Oath of Druids")
    put_on(s, "Grizzly Bears", "p3")
    elves = one(s, "Llanowar Elves", "p2")
    move(s, elves, "library", position="top")
    island = next(x for x in s.state.cards.values() if x.owner == "p2" and x.zone == "p2:library" and x.name == "Island")
    move(s, island, "library", position="top")  # Island on top, then Llanowar Elves
    to_phase(s, "upkeep", turn=2)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and {o.id for o in d.options} == {"p3"}  # Bob chooses; only Carol has more creatures than he does
    settle(s, ["p3", "yes"])
    assert zone(s, elves) == "p2:battlefield" and s.state.cards[elves.id].controller == "p2"
    assert zone(s, island) == "p2:graveyard"
    check(s)


def test_oath_of_lieges_has_no_target_when_nobody_controls_more_lands(cards):
    s = three(cards, ["Oath of Lieges"], [], [])
    put_on(s, "Oath of Lieges")
    put_on(s, "Island", "p2")
    put_on(s, "Island", "p3")  # Alice has none: Bob's only opponent with more lands is nobody (Carol has as many)
    to_phase(s, "main1", turn=2)
    assert "Oath of Lieges’s ability" not in log_text(s)
    check(s)


def test_oath_of_lieges_bob_searches_his_own_library(cards):
    s = three(cards, ["Oath of Lieges"], [], [])
    put_on(s, "Oath of Lieges")
    put_on(s, "Island", "p3")
    to_phase(s, "upkeep", turn=2)
    settle(s, ["p3", "yes", "Island"])
    lands = [x for x in s.state.cards.values() if x.zone == "p2:battlefield" and x.name == "Island"]
    assert len(lands) == 1 and lands[0].controller == "p2" and lands[0].owner == "p2"
    assert not named(s, "Island", "p1")
    check(s)


# -- Council's dilemma -----------------------------------------------------------------------------------------------------------------------------
PROMOTED += ["Travel Through Caradhras", "Fateful Tempest", "Selvala's Stampede", "Expropriate"]


def vote_cast(s, name, ballots, prefer=(), **pool):
    """Cast ``name`` for Alice; the votes are answered from ``ballots`` in order (asked of each player in turn order), every other decision
    from ``prefer``; then everything resolves."""
    c = one(s, name)
    move(s, c, "hand")
    act(s, "p1", type="add_mana", player="p1", mana=pool)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[])
    ballots, order = list(ballots), ["p1", "p2", "p3"]
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.prompt.startswith("Vote"):
            assert d.player == order.pop(0)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[ballots.pop(0)])
        elif d is not None:
            want = [o.id for p in prefer for o in d.options if p in (o.id, o.label, s.state.cards[o.card_id].name if o.card_id in s.state.cards else None)]
            need = max(1, d.min_choices)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want[: d.max_choices] if len(want) >= need else [o.id for o in d.options][:need])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert not ballots
    return s.state.cards[c.id]


def stack_top(s, pid, names):
    """Put the named cards (each the first of that name the player owns still in their library) on top of their library, in that order."""
    for name in reversed(names):
        c = next(x for x in s.state.cards.values() if x.owner == pid and x.name == name and x.zone == f"{pid}:library")
        move(s, c, "library", position="top")


def shuffles(s, who):
    return sum(1 for e in s.state.log if [p.get("t") for p in e.model_dump()["parts"]][:2] == [who, " shuffled their library"])


def test_travel_through_caradhras_searches_once_per_vote_and_shuffles_once(cards):
    s = three(cards, ["Travel Through Caradhras", "Grizzly Bears"])
    bears = one(s, "Grizzly Bears")
    move(s, bears, "graveyard")
    before = shuffles(s, "Alice")
    spell = vote_cast(s, "Travel Through Caradhras", ["redhorn pass", "redhorn pass", "mines of moria"], ["Forest", "Grizzly Bears"], G=1, C=5)
    lands = [x for x in s.state.cards.values() if x.zone == "p1:battlefield" and x.name == "Forest"]
    assert len(lands) == 2 and all(x.tapped for x in lands)
    assert zone(s, bears) == "p1:hand" and zone(s, spell) == "p1:exile"
    assert shuffles(s, "Alice") == before + 1
    check(s)


def test_travel_through_caradhras_without_redhorn_votes_does_not_shuffle(cards):
    s = three(cards, ["Travel Through Caradhras", "Grizzly Bears"])
    move(s, one(s, "Grizzly Bears"), "graveyard")
    before = shuffles(s, "Alice")
    vote_cast(s, "Travel Through Caradhras", ["mines of moria"] * 3, ["Grizzly Bears"], G=1, C=5)
    assert shuffles(s, "Alice") == before and zone(s, one(s, "Grizzly Bears")) == "p1:hand"  # (two returns find nothing more)
    check(s)


def test_fateful_tempest_mills_for_past_and_exiles_for_present(cards):
    s = three(cards, ["Fateful Tempest", "Grizzly Bears", "Llanowar Elves"])
    stack_top(s, "p1", ["Grizzly Bears", "Llanowar Elves", "Forest"])
    vote_cast(s, "Fateful Tempest", ["past", "present", "past"], R=1, C=2)
    assert zone(s, one(s, "Grizzly Bears")) == "p1:graveyard" and zone(s, one(s, "Llanowar Elves")) == "p1:graveyard"
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [40, 37, 37]  # 2 + 1 to each opponent
    assert len([x for x in s.state.cards.values() if x.zone == "p1:exile" and x.name == "Forest"]) == 1
    check(s)


def test_fateful_tempest_without_past_votes_deals_no_damage(cards):
    s = three(cards, ["Fateful Tempest"])
    vote_cast(s, "Fateful Tempest", ["present"] * 3, R=1, C=2)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [40, 40, 40]
    assert len([x for x in s.state.cards.values() if x.zone == "p1:exile"]) == 3
    check(s)


def test_selvalas_stampede_reveals_creatures_for_wild_then_puts_from_hand_for_free(cards):
    s = three(cards, ["Selvala's Stampede", "Grizzly Bears", "Llanowar Elves", "Soul Warden"])
    stack_top(s, "p1", ["Forest", "Grizzly Bears", "Forest", "Llanowar Elves"])
    warden = one(s, "Soul Warden")
    move(s, warden, "hand")
    vote_cast(s, "Selvala's Stampede", ["wild", "free", "wild"], ["Soul Warden"], G=2, C=4)
    assert zone(s, one(s, "Grizzly Bears")) == "p1:battlefield" and zone(s, one(s, "Llanowar Elves")) == "p1:battlefield"
    assert zone(s, warden) == "p1:battlefield"
    assert not [x for x in s.state.cards.values() if x.owner == "p1" and x.zone != "p1:library" and x.name == "Forest"]  # the revealed Forests went back
    check(s)


def test_expropriate_extra_turn_for_time_and_steals_for_each_money_vote(cards):
    s = three(cards, ["Expropriate"], ["Grizzly Bears"], ["Llanowar Elves"])
    bears, elves = put_on(s, "Grizzly Bears", "p2"), put_on(s, "Llanowar Elves", "p3")
    spell = vote_cast(s, "Expropriate", ["time", "money", "money"], ["Grizzly Bears", "Llanowar Elves"], U=2, C=7)
    assert s.state.cards[bears.id].controller == "p1" and s.state.cards[elves.id].controller == "p1"
    assert len(s.state.rules.extra_turns) == 1 and zone(s, spell) == "p1:exile"
    check(s)
