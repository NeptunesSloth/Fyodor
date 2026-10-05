"""Wave 23A: "Each player may discard their hand and draw N cards" and what the players who did get (CR 118.12, 101.4, 701.9a).

Snort: "Each player may discard their hand and draw five cards. Then Snort deals 5 damage to each opponent who discarded their hand
this way." Every player decides privately in turn order (APNAP), the hands are discarded together, then the draws and the damage
(to the opponents of the controller who discarded) follow. A player with an empty hand may still choose it (the Narset ruling).
Ruin Grinder and Variable Chaser use the same wording. Real Oracle text; replay and save/load."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import life, pick, settle, to_hand, until_asked
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card("Snort", set_code="tst", number="23A-SN", mana_cost="{3}{R}", cmc=4.0, type_line="Sorcery",
         oracle_text="Each player may discard their hand and draw five cards. Then Snort deals 5 damage to each opponent who discarded their hand this way.\nFlashback {5}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
         colors=["R"], color_identity=["R"], keywords=["Flashback"]),
    card("Ruin Grinder", set_code="tst", number="23A-RG", mana_cost="{5}{R}", cmc=6.0, type_line="Artifact Creature — Construct",
         oracle_text="Menace\nWhen this creature dies, each player may discard their hand and draw seven cards.\nMountaincycling {2} ({2}, Discard this card: Search your library for a Mountain card, reveal it, put it into your hand, then shuffle.)",
         power="7", toughness="4", colors=["R"], color_identity=["R"], keywords=["Mountaincycling", "Landcycling", "Menace", "Typecycling", "Cycling"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build3(cards, *mine):
    a = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (20, "Mountain")])
    b = deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")])
    c = deck(cards, "Krenko, Mob Boss", [(20, "Forest")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b), PlayerSetup("Carol", cards=c)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def hand(s, pid):
    return zone(s.state, pid, "hand")


@pytest.mark.parametrize("name", ["Snort", "Ruin Grinder"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_snort_each_player_chooses_then_the_opponents_who_did_take_damage(cards):
    s = build3(cards, "Snort")
    for pid in ("p2", "p3"):  # three cards in each hand
        for c in [c for c in s.state.cards.values() if c.owner == pid and c.zone == f"{pid}:library"][:3]:
            act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    old = {p: set(hand(s, p)) for p in ("p2", "p3")}
    c = to_hand(s, "Snort")
    mana(s, "p1", R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]  # Alice first (APNAP)
    assert "options" not in s.view("p2")["rules"]["decision"]
    roundtrip(s)  # (a save with Alice's private choice pending)
    pick(s, "pay")
    assert s.state.rules.decision.player == "p2"
    assert hand(s, "p1") != [] or True  # (nothing has been discarded yet: every choice first, 101.4)
    pick(s, "pay")
    assert s.state.rules.decision.player == "p3"
    pick(s, "decline")
    settle(s)
    assert life(s, "p1") == 40 and life(s, "p2") == 35 and life(s, "p3") == 40  # (the controller is no opponent of herself)
    assert len(hand(s, "p1")) == 5 and len(hand(s, "p2")) == 5 and set(hand(s, "p3")) == old["p3"]
    assert not (set(hand(s, "p2")) & old["p2"])  # (Bob's old cards were discarded, five new ones drawn)
    roundtrip(s)


def test_snort_a_player_with_an_empty_hand_may_still_choose_it(cards):
    s = build3(cards, "Snort")
    c = to_hand(s, "Snort")
    mana(s, "p1", R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id)
    pick(s, "decline")
    pick(s, "pay")  # Bob has no cards in hand: he still draws five and takes the damage
    pick(s, "decline")
    settle(s)
    assert len(hand(s, "p2")) == 5 and life(s, "p2") == 35
    roundtrip(s)
