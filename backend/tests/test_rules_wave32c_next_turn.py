"""Wave 32C: "until the end of your next turn" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave32c_next_turn_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 611.2a / 514.2: the duration ends in the cleanup step of the stated player's next turn. When the effect began in one of their own turns the
  next one is the *following* turn of theirs (the one it began in is not "next"); when it began in an opponent's, it is the first of theirs.
  Unlike "until your next turn" (500.4: ends as that turn begins) the player gets the whole turn, end step included.
* Three kinds of effect carry the duration: a continuous effect (Treasure Nabber's control change: ``ContinuousEffect.duration``
  "end_of_next_turn", app/rules/delayed.py), a casting limit (Single Combat: app/rules/cast_limits.py) and a permission to play the exiled
  cards (``Permission.until``, which already knew it: the parser now reads "cards exiled this way", "mana of any type" riders after it, and
  "each player's library").
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.casting import castable
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave32c_next_turn_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w32c", number=f"N{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def settle(s, prefer=(), limit=60):
    """Resolve everything; a decision is answered with the first of ``prefer`` it offers (card names or option ids), else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for p in prefer for o in d.options if p in (o.id, o.label, s.state.cards[o.card_id].name if o.card_id in s.state.cards else None)]
            pick = want[: max(1, d.min_choices)] if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_phase(s, phase, turn=None, limit=300):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn} (at {s.state.turn.phase} of turn {s.state.turn.number})")


def stops(s, *steps):
    """Alice is given priority in these steps of every turn (hers and the others')."""
    act(s, "p1", type="set_stops", own=list(steps), others=list(steps), smart_pass=False)


def to_zone(s, cid, zone, pid="p1", position=None):
    payload = {"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": zone}}
    if position:
        payload["position"] = position
    act(s, pid, **payload)


def library_top(s, names, pid="p1"):
    """These cards (the first named on top), each a different card of the library, put on top of it in this order."""
    for name in reversed(names):
        cid = next(c.id for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library")
        to_zone(s, cid, "library", pid, "top")


def named(s, name, zone, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:{zone}")


def can_cast(s, pid, c):
    return castable(s.state, pid, s.state.cards[c.id], s.cards, check_priority=False)


# --- a continuous effect: Treasure Nabber -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("first", [1, 2])
def test_treasure_nabber_keeps_the_artifact_through_the_whole_of_your_next_turn(cards, first):
    """Treasure Nabber: "Whenever an opponent taps an artifact for mana, gain control of that artifact until the end of your next turn."
    Tapped in Alice's own turn 1 or in Bob's turn 2, the next turn of Alice's is turn 3: she still has it all through turn 1 / 2 and through
    turn 3 up to its cleanup step, and Bob has it back when turn 4 begins. (Her own turn 1 is not "next", 611.2a.)"""
    s = build(cards, ["Treasure Nabber"], ["Sol Ring"])
    put(s, "Treasure Nabber")
    ring = put(s, "Sol Ring", "p2")
    stops(s, "end")
    if first == 2:
        to_phase(s, "main1", turn=2)
    else:
        act(s, "p2", type="set_stops", own=[], others=["main1"], smart_pass=False)
        act(s, "p1", type="pass_priority")  # (Bob gets priority in Alice's main phase)
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="activate_ability", card_id=ring.id, ability=0)
    settle(s)
    assert s.state.cards[ring.id].controller == "p1"
    check(s)
    s = reloaded(s)  # (saved and loaded in the middle of the duration: the game goes on from the loaded table)
    to_phase(s, "end", turn=first)
    assert s.state.cards[ring.id].controller == "p1"  # (not an "until end of turn" effect)
    to_phase(s, "main1", turn=3)
    assert s.state.cards[ring.id].controller == "p1"  # (not "until your next turn", which would have ended as turn 3 began)
    check(s)
    to_phase(s, "end", turn=3)
    assert s.state.cards[ring.id].controller == "p1"
    check(s)
    to_phase(s, "main1", turn=4)
    assert s.state.cards[ring.id].controller == "p2"
    check(s)


# --- a casting limit: Single Combat ------------------------------------------------------------------------------------------------


def test_single_combat_limit_lasts_until_the_end_of_alices_next_turn(cards):
    """Single Combat: "Each player chooses a creature or planeswalker they control, then sacrifices the rest. Players can't cast creature or
    planeswalker spells until the end of your next turn." Cast in Alice's turn 1: nobody can cast a creature spell in Bob's turn 2 or in
    Alice's turn 3 (end step included); noncreature spells are not limited; in Bob's turn 4 the limit is over."""
    s = build(cards, ["Single Combat", "Grizzly Bears", "Grizzly Bears", "Llanowar Elves"],
              ["Grizzly Bears", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt"])
    for pid in ("p1", "p2"):
        put(s, "Grizzly Bears", pid)
        put(s, "Llanowar Elves", pid)
    to_hand(s, "Single Combat")
    mana(s, W=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Single Combat").id)
    settle(s)
    for pid in ("p1", "p2"):  # (each player kept one creature, the first offered, and sacrificed the other)
        assert len([c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and c.name in ("Grizzly Bears", "Llanowar Elves")]) == 1
    check(s)
    s = reloaded(s)  # (saved and loaded in the middle of the duration: the limit is part of the saved rules state)
    bears_a = named(s, "Grizzly Bears", "library")
    to_zone(s, bears_a.id, "hand")
    bears_b = named(s, "Grizzly Bears", "library", "p2")
    to_zone(s, bears_b.id, "hand", "p2")
    bolt = named(s, "Lightning Bolt", "library", "p2")
    to_zone(s, bolt.id, "hand", "p2")
    stops(s, "end")
    mana(s, G=2)
    assert not can_cast(s, "p1", bears_a)  # (the rest of Alice's turn 1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears_a.id)
    to_phase(s, "main1", turn=2)
    mana(s, "p2", G=2, R=1)
    assert not can_cast(s, "p2", bears_b) and can_cast(s, "p2", bolt)
    check(s)
    to_phase(s, "main1", turn=3)
    mana(s, G=2)
    assert not can_cast(s, "p1", bears_a)
    to_phase(s, "end", turn=3)
    assert not can_cast(s, "p1", bears_a)
    check(s)
    to_phase(s, "main1", turn=4)
    mana(s, "p2", G=2)
    assert can_cast(s, "p2", bears_b)
    check(s)


# --- permissions: the exiled cards stay playable through your next turn ---------------------------------------------------------------


def test_escape_to_the_wilds_cards_are_playable_this_turn_and_all_of_the_next_then_gone(cards):
    """Escape to the Wilds: "Exile the top five cards of your library. You may play cards exiled this way until the end of your next turn. You
    may play an additional land this turn." Cast in Alice's turn 1 (an own turn): the cards are playable then, in turn 3 up to its end step, and
    stay in exile for good once turn 3's cleanup step has ended it."""
    s = build(cards, ["Escape to the Wilds", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Sol Ring"], [])
    library_top(s, ["Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Sol Ring", "Forest"])
    to_hand(s, "Escape to the Wilds")
    mana(s, R=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Escape to the Wilds").id)
    settle(s)
    exiled = [s.state.cards[c].name for c in s.state.zones["p1:exile"]]
    assert sorted(exiled) == sorted(["Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Sol Ring", "Forest"])
    forest, bears = named(s, "Forest", "exile"), named(s, "Grizzly Bears", "exile")
    check(s)
    act(s, "p1", type="play_land", card_id=forest.id)  # (a land play from exile; the extra land play is the spell's other sentence)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)
    stops(s, "end", "upkeep")
    to_phase(s, "main1", turn=3)
    elves, ring = named(s, "Llanowar Elves", "exile"), named(s, "Sol Ring", "exile")
    mana(s, G=1)
    assert can_cast(s, "p1", elves)
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:battlefield"
    check(s)
    to_phase(s, "end", turn=3)
    bolt = named(s, "Lightning Bolt", "exile")
    mana(s, R=1)
    assert can_cast(s, "p1", bolt)  # (an instant: still playable in the end step of turn 3)
    to_phase(s, "upkeep", turn=4)
    mana(s, R=1, G=1)
    assert not can_cast(s, "p1", bolt) and not can_cast(s, "p1", elves)
    assert s.state.cards[bolt.id].zone == "p1:exile" and s.state.cards[elves.id].zone == "p1:exile"
    check(s)


def test_ignite_the_future_plays_for_free_only_when_cast_from_a_graveyard(cards):
    """Ignite the Future: "Exile the top three cards of your library. Until the end of your next turn, you may play those cards. If this spell was
    cast from a graveyard, you may play cards this way without paying their mana costs." Cast from the hand, a card must be paid for; cast
    with flashback ({7}{R}) from the graveyard, the exiled cards are free; both stay playable through Alice's next turn."""
    s = build(cards, ["Ignite the Future", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Sol Ring"], [])
    library_top(s, ["Grizzly Bears", "Llanowar Elves", "Lightning Bolt"])
    to_hand(s, "Ignite the Future")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Ignite the Future").id)
    settle(s)
    bears = named(s, "Grizzly Bears", "exile")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id, free=True)  # (cast from the hand: no free play)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)
    ignite = named(s, "Ignite the Future", "graveyard")
    library_top(s, ["Sol Ring", "Forest", "Forest"])
    mana(s, R=1, C=7)
    act(s, "p1", type="cast_spell", card_id=ignite.id)
    settle(s)
    ring = named(s, "Sol Ring", "exile")
    act(s, "p1", type="cast_spell", card_id=ring.id, free=True)  # (118.9: no mana, from the flashback cast)
    settle(s)
    assert s.state.cards[ring.id].zone == "p1:battlefield"
    check(s)
    to_phase(s, "main1", turn=3)
    elves = named(s, "Llanowar Elves", "exile")  # (the first cast's cards: still there through turn 3)
    mana(s, G=1)
    assert can_cast(s, "p1", elves)
    check(s)


def test_lidless_gaze_plays_every_players_exiled_card_with_any_mana_through_alices_next_turn(cards):
    """Lidless Gaze: "Exile the top card of each player's library. Until the end of your next turn, you may play those cards, and mana of any
    type can be spent to cast those spells." Bob's Grizzly Bears ({1}{G}) is cast with red mana in Alice's turn 3; Alice's own exiled card
    stays playable too; it is all over when turn 3 has ended."""
    s = build(cards, ["Lidless Gaze", "Llanowar Elves"], ["Grizzly Bears"])
    library_top(s, ["Llanowar Elves"])
    library_top(s, ["Grizzly Bears"], "p2")
    to_hand(s, "Lidless Gaze")
    mana(s, B=1, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lidless Gaze").id)
    settle(s)
    bears = named(s, "Grizzly Bears", "exile", "p2")
    elves = named(s, "Llanowar Elves", "exile")
    check(s)
    stops(s, "upkeep")
    to_phase(s, "main1", turn=3)
    mana(s, R=2)
    assert can_cast(s, "p1", bears)  # (red mana pays the {G}: mana of any type)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].controller == "p1"
    check(s)
    to_phase(s, "upkeep", turn=5)
    mana(s, G=1)
    assert not can_cast(s, "p1", elves) and s.state.cards[elves.id].zone == "p1:exile"
    check(s)


def test_bloodsoaked_insight_plays_the_opponents_exiled_cards_with_any_mana(cards):
    """Bloodsoaked Insight: "Target opponent exiles the top three cards of their library. Until the end of your next turn, you may play those
    cards. If you cast a spell this way, mana of any type can be spent to cast it." Cast in Alice's turn 1; a card of Bob's is cast with red mana in
    turn 3 and the others stay exiled once turn 3 is over."""
    s = build(cards, ["Bloodsoaked Insight // Sanguine Morass"], ["Grizzly Bears", "Llanowar Elves", "Lightning Bolt"])
    library_top(s, ["Grizzly Bears", "Llanowar Elves", "Lightning Bolt"], "p2")
    to_hand(s, "Bloodsoaked Insight // Sanguine Morass")
    mana(s, R=2, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Bloodsoaked Insight // Sanguine Morass").id, targets=["p2"])
    settle(s)
    bears, elves = named(s, "Grizzly Bears", "exile", "p2"), named(s, "Llanowar Elves", "exile", "p2")
    check(s)
    stops(s, "upkeep")
    to_phase(s, "main1", turn=3)
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)
    to_phase(s, "upkeep", turn=5)
    mana(s, G=1)
    assert not can_cast(s, "p1", elves) and s.state.cards[elves.id].zone == "p2:exile"
    check(s)


def moloch_table(cards):
    """Alice casts Rooting Moloch with a Lonely Sandbar (cycling) and a Grizzly Bears in her graveyard: the Sandbar is the only legal target."""
    s = build(cards, ["Rooting Moloch", "Lonely Sandbar", "Grizzly Bears"], [])
    to_zone(s, named(s, "Lonely Sandbar", "library").id, "graveyard")
    to_zone(s, named(s, "Grizzly Bears", "library").id, "graveyard")
    to_hand(s, "Rooting Moloch")
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Rooting Moloch").id)
    settle(s)
    assert named(s, "Grizzly Bears", "graveyard")  # (no cycling ability: not a target, 702.29f)
    return s, named(s, "Lonely Sandbar", "exile")


def test_rooting_moloch_card_is_playable_in_alices_next_turn(cards):
    """Rooting Moloch: "When this creature enters, exile target card with a cycling ability from your graveyard. Until the end of your next
    turn, you may play that card." Cast in Alice's own turn 1 the card is still hers to play in turn 3, not just in turn 1."""
    s, sandbar = moloch_table(cards)
    check(s)
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="play_land", card_id=sandbar.id)
    assert s.state.cards[sandbar.id].zone == "p1:battlefield"
    check(s)


def test_rooting_moloch_card_is_gone_once_alices_next_turn_has_ended(cards):
    s, sandbar = moloch_table(cards)
    stops(s, "end", "upkeep")
    to_phase(s, "end", turn=3)
    assert any(p.card == sandbar.id for p in s.state.rules.permissions)  # (still in force in turn 3's end step)
    to_phase(s, "main1", turn=5)
    assert not any(p.card == sandbar.id for p in s.state.rules.permissions)
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=sandbar.id)
    assert s.state.cards[sandbar.id].zone == "p1:exile"
    check(s)
