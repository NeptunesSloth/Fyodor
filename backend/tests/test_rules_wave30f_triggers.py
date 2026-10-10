"""Wave 30F: "from where" in trigger conditions about played lands, cast spells and entering permanents (CR 2026-09-25). Real Oracle text
(tests/fixtures/wave30f_triggers_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 701.18a: to play a land is to put it onto the battlefield from the zone it's in (usually the hand): "you play a land from exile" asks
  for that zone. 701.18b: to play a card is to play it as a land or cast it as a spell, whichever is appropriate: "you play a card from
  exile" (Prosper) is a land played from exile or a spell cast from exile, each its own event (603.2).
* 601.2a: a spell is cast from the zone it was in. 603.6a: "enters from anywhere other than your hand" (The Lost and the Damned) reads the
  zone the permanent came from (a token is created, it comes from no zone).
* 102.2: with no teams (Commander is free-for-all) "another player" is an opponent (Aerial Extortionist).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, events
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import to_turn
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30f_triggers_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w30f", number=f"F{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Prosper, Tome-Bound", "Klaw, Master of Sound", "Pia Nalaar, Consul of Revival", "Faldorn, Dread Wolf Herald",
        "Shadow of the Goblin", "The Lost and the Damned", "Aerial Extortionist"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, pick=None, limit=30):
    """Resolve the stack; a decision is answered with the option naming card ``pick``, else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            chosen = [o.id for o in d.options if pick and o.card_id == pick] or ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen[: max(1, d.max_choices or 1)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def exile_playable(s, name, pid="p1"):
    """Savvy Trader (Oracle: "exile target permanent card from your graveyard. You may play that card for as long as it remains exiled"):
    the named card is now in exile with a permission to play it."""
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    to_hand(s, "Savvy Trader", pid)
    mana(s, pid, G=4)
    act(s, pid, type="cast_spell", card_id=card_named(s, "Savvy Trader", pid).id)
    settle(s, pick=c.id)
    assert zone_of(s, name, pid) == f"{pid}:exile"
    return c


def treasures(s, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.controller == pid and c.zone.endswith(":battlefield"))


def tokens(s, name, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone.endswith(":battlefield"))


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_wordings_are_read():
    land = {"event": "land_played", "subject": "player", "player": "you", "aggregate": False, "entered_from": "exile"}
    assert events.parse_condition("you play a land from exile") == {**land, "obj": 'sel:{"types":["Land"]}'}
    both = events.parse_condition("you play a card from exile")
    assert both is not None and [x["event"] for x in both["conds"]] == ["land_played", "cast"]
    assert both["conds"][0]["entered_from"] == "exile" and both["conds"][1]["from"] == "exile"
    # (the one place of "play a land or cast a spell from …" is both halves')
    shadow = events.parse_condition("you play a land or cast a spell from anywhere other than your hand")
    assert shadow is not None and shadow["conds"][0]["entered_from"] == "not_hand" and shadow["conds"][1]["from"] == "not_hand"
    # (unread places and a subject that isn't one thing stay unread)
    assert events.parse_condition("you play a land from the top of your library") is None
    assert events.parse_condition("you play a card from anywhere") is None
    assert events.parse_condition("you play a land from exile or cast a spell") is not None  # (only the land is limited)


def test_prosper_triggers_on_a_land_or_a_spell_played_from_exile_not_from_hand(cards):
    """Prosper: "Pact Boon — Whenever you play a card from exile, create a Treasure token." (rulings: any card played from exile)"""
    s = build(cards, mine=("Prosper, Tome-Bound", "Savvy Trader", "Grizzly Bears"), forests=9)
    put(s, "Prosper, Tome-Bound")
    forest = exile_playable(s, "Forest")
    assert treasures(s) == 0  # (casting Savvy Trader from the hand is not casting from exile)
    check(s)
    act(s, "p1", type="play_land", card_id=forest.id)  # a land played from exile
    settle(s)
    assert zone_of(s, "Forest") == "p1:battlefield" and treasures(s) == 1
    check(s)
    # a spell cast from exile
    bears = exile_playable(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and treasures(s) == 2
    check(s)


def test_prosper_ignores_a_land_played_from_the_hand_and_an_opponent_playing_from_exile(cards):
    s = build(cards, mine=("Prosper, Tome-Bound",), theirs=("Savvy Trader",))
    put(s, "Prosper, Tome-Bound")
    hand_forest = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=hand_forest.id)
    settle(s)
    assert treasures(s) == 0
    to_turn(s, 2)  # Bob's turn: a card of his own played from exile is not "you play"
    bob_forest = exile_playable(s, "Island", "p2")
    assert bob_forest is not None
    act(s, "p2", type="play_land", card_id=bob_forest.id)
    settle(s)
    assert zone_of(s, "Island", "p2") == "p2:battlefield" and treasures(s) == 0 and treasures(s, "p2") == 0
    check(s)


def test_pia_nalaar_has_the_two_halves_each_its_own_event(cards):
    """Pia Nalaar: "Whenever you play a land from exile or cast a spell from exile, create a 1/1 colorless Thopter artifact creature token with
    flying." (603.2: each event triggers on its own)"""
    s = build(cards, mine=("Pia Nalaar, Consul of Revival", "Savvy Trader", "Grizzly Bears"), forests=9)
    put(s, "Pia Nalaar, Consul of Revival")
    forest = exile_playable(s, "Forest")
    assert tokens(s, "Thopter") == 0
    act(s, "p1", type="play_land", card_id=forest.id)
    settle(s)
    assert tokens(s, "Thopter") == 1
    bears = exile_playable(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert tokens(s, "Thopter") == 2
    check(s)


def test_shadow_of_the_goblin_counts_both_a_land_and_a_spell_from_anywhere_but_the_hand(cards):
    """Shadow of the Goblin: "Undying Vengeance — Whenever you play a land or cast a spell from anywhere other than your hand, this enchantment
    deals 1 damage to each opponent." (a land from the hand, a spell from the hand: no)"""
    s = build(cards, mine=("Shadow of the Goblin", "Savvy Trader", "Grizzly Bears"), forests=9)
    put(s, "Shadow of the Goblin")
    hand_forest = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=hand_forest.id)
    settle(s)
    assert life(s, "p2") == 40
    forest = exile_playable(s, "Forest")  # (Savvy Trader itself was cast from the hand: no damage yet)
    assert life(s, "p2") == 40
    check(s)
    # the land limit is 1 a turn: the next turn's land from exile
    to_turn(s, 3)
    act(s, "p1", type="play_land", card_id=forest.id)
    settle(s)
    assert life(s, "p2") == 39
    bears = exile_playable(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert life(s, "p2") == 38
    check(s)


def test_faldorn_reads_the_cast_and_the_entering_land_as_two_events(cards):
    """Faldorn: "Whenever you cast a spell from exile or a land you control enters from exile, create a 2/2 green Wolf creature token."
    (a land that enters from the hand, a spell cast from the hand: no)"""
    s = build(cards, mine=("Faldorn, Dread Wolf Herald", "Savvy Trader", "Grizzly Bears"), forests=9)
    put(s, "Faldorn, Dread Wolf Herald")
    hand_forest = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=hand_forest.id)
    settle(s)
    assert tokens(s, "Wolf") == 0
    bears = exile_playable(s, "Grizzly Bears")
    assert tokens(s, "Wolf") == 0  # (Savvy Trader itself was cast from the hand)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert tokens(s, "Wolf") == 1
    to_turn(s, 3)  # a land that enters from exile: the land play of a later turn
    forest = exile_playable(s, "Forest")
    act(s, "p1", type="play_land", card_id=forest.id)
    settle(s)
    assert tokens(s, "Wolf") == 2
    check(s)


def test_the_lost_and_the_damned_enters_from_anywhere_but_the_hand(cards):
    """The Lost and the Damned: "Whenever a land you control enters from anywhere other than your hand or you cast a spell from anywhere other
    than your hand, create a 3/3 red Spawn creature token." (a land and a spell from the hand: no; from exile: each its own)"""
    s = build(cards, mine=("The Lost and the Damned", "Savvy Trader", "Grizzly Bears"), forests=9)
    put(s, "The Lost and the Damned")
    hand_forest = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=hand_forest.id)
    settle(s)
    bears = exile_playable(s, "Grizzly Bears")
    assert tokens(s, "Spawn") == 0  # (a land from the hand, Savvy Trader from the hand)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert tokens(s, "Spawn") == 1
    to_turn(s, 3)
    forest = exile_playable(s, "Forest")
    act(s, "p1", type="play_land", card_id=forest.id)
    settle(s)
    assert tokens(s, "Spawn") == 2
    check(s)


def test_aerial_extortionist_is_about_another_player_not_you(cards):
    """Aerial Extortionist: "Whenever another player casts a spell from anywhere other than their hand, draw a card." (102.2: an opponent;
    its own controller casting from exile, or an opponent casting from the hand, draws nothing)"""
    s = build(cards, mine=("Aerial Extortionist", "Savvy Trader", "Grizzly Bears"), theirs=("Savvy Trader", "Grizzly Bears"))
    put(s, "Aerial Extortionist")
    mine = exile_playable(s, "Grizzly Bears")  # (Alice casts Savvy Trader from her hand, then her own Bears from exile)
    n = len(s.state.zones["p1:hand"])
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=mine.id)
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and len(s.state.zones["p1:hand"]) == n
    to_turn(s, 2)
    theirs = exile_playable(s, "Grizzly Bears", "p2")  # (Bob's Savvy Trader came from his hand: no draw)
    before = len(s.state.zones["p1:hand"])
    mana(s, "p2", G=2)
    act(s, "p2", type="cast_spell", card_id=theirs.id)
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield"
    assert len(s.state.zones["p1:hand"]) == before + 1
    check(s)
