"""Wave 29C: "Draw three cards and reveal them" (Mad Wizard's Lair) reveals only the cards that were drawn without a replacement effect
(CR 121.6c, 614.11b: "If an effect would have a player both draw a card and perform an additional action on that card, and the draw is replaced,
the additional action is not performed on any cards that are drawn as a result of that replacement effect"; 121.5: cards put into a hand without
the word "draw" weren't drawn). Review 28B did this for a replacement that puts a card into the hand (Underrealm Lich); a replacement that draws
cards itself ("draw two cards instead": Phial of Galadriel, Blood Scrivener) still had them revealed. Review 29C: a replacement that changes the
number of cards the instruction draws (121.2a: Quantum Riddler, Alms Collector) is unsettled for "reveal them": the players resolve it.

Real Oracle text; every scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import find as dfind
from tests.test_rules_designations import resolve, table
from tests.test_rules_effects import mana
from tests.test_rules_review28b import MORE
from tests.test_rules_wave9b_exile_permission import roundtrip
from tests.test_rules_wave28b_replace import EXTRA


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    names = {c["name"] for c in fixture_cards()}
    build_database(fixture_cards() + [c for c in EXTRA + MORE if c["name"] not in names], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def lair(cards, replacer, *, empty_hand=True, theirs=()):
    """Alice has ventured to Deep Mines in the Dungeon of the Mad Mage, with ``replacer`` in play (or nothing; ``theirs``: Bob's permanents)
    and Lightning Bolt, Counterspell and Murder on top of her library (Bolt first); the next venture enters Mad Wizard's Lair. Returns the
    table and the free-cast decisions' offers."""
    s = table(cards, mine=("Secret Door",), theirs=theirs, hand=tuple(x for x in (replacer, "Lightning Bolt", "Counterspell", "Murder") if x))
    door = dfind(s, "Secret Door")

    def venture(*answers):
        mana(s, U=1, C=4)
        act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
        resolve(s, *answers)

    for answers in (("Dungeon of the Mad Mage",), ([],), ("Goblin Bazaar",), ([],), ("Muiral's Graveyard",), ([],)):
        venture(*answers)
    assert s.state.rules.dungeons["p1"].room == "Deep Mines"
    if replacer:
        act(s, "p1", type="move", card_ids=[dfind(s, replacer).id], to={"player": "p1", "zone": "battlefield"})
    if empty_hand:
        for cid in list(s.state.zones["p1:hand"]):
            act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "graveyard"})
    for name in ("Murder", "Counterspell", "Lightning Bolt"):
        act(s, "p1", type="move", card_ids=[dfind(s, name).id], to={"player": "p1", "zone": "library"}, position="top")
    return s, door


def enter_the_lair(s, door, manual=None):
    """(``manual``: collects the prompts of the decisions that leave a part to the players, with what Bob saw then)"""
    mana(s, U=1, C=4)
    act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
    offered: list[str] = []
    seen_by_bob: list[str] = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            cards_offered = [o.card_id for o in d.options if o.card_id]
            if d.kind == "manual_resolution" and manual is not None:
                manual.append(d.prompt)
                seen_by_bob.append(json.dumps(s.view("p2")))
            if cards_offered and d.min_choices == 0:  # (the free cast of one of the revealed cards: decline it)
                offered += cards_offered
                seen_by_bob.append(json.dumps(s.view("p2")))
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
            else:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.rules.completed_dungeons["p1"] == ["Dungeon of the Mad Mage"]
    return [s.state.cards[c].name for c in offered], "".join(seen_by_bob), json.dumps(s.view("p2"))


def test_an_old_turn_log_without_the_new_field_loads():
    from app.game.rules_state import TurnLog

    log = TurnLog.model_validate({"turn": 3, "drawn": {"p1": ["o1"]}})  # (a save from before wave 29C)
    assert log.drawn == {"p1": ["o1"]} and log.drawn_replaced == {}


def test_everything_it_drew_is_revealed_without_a_replacement(cards):
    s, door = lair(cards, None, empty_hand=False)
    offered, _, _ = enter_the_lair(s, door)
    assert set(offered) == {"Lightning Bolt", "Counterspell", "Murder"}, offered  # (the control: all three, 701.20a)
    roundtrip(s)


@pytest.mark.parametrize("replacer, hidden", [
    ("Phial of Galadriel", ["Lightning Bolt", "Counterspell"]),  # "draw two cards instead" replaces the first draw: those two aren't revealed
    ("Blood Scrivener", ["Lightning Bolt", "Counterspell"]),  # "instead you draw two cards and you lose 1 life" likewise
])
def test_cards_drawn_by_a_replacement_are_not_revealed(cards, replacer, hidden):
    s, door = lair(cards, replacer)
    offered, during, after = enter_the_lair(s, door)
    assert "Murder" in offered and not set(hidden) & set(offered), offered  # (the draws after it were not replaced)
    assert "Murder" in during and not any(name in during or name in after for name in hidden)  # 614.11b: Bob never saw them
    assert {s.state.cards[c].name for c in s.state.zones["p1:hand"]} >= set(hidden)  # (drawn all the same: they are in the hand)
    roundtrip(s)


@pytest.mark.parametrize("replacer, theirs, drawn", [
    ("Quantum Riddler", (), ["Lightning Bolt", "Counterspell", "Murder"]),  # "draw three cards" becomes "draw four cards"
    (None, ("Alms Collector",), ["Lightning Bolt"]),  # Bob's: "instead you and that player each draw a card"
])
def test_a_replacement_of_the_number_of_cards_drawn_leaves_the_reveal_to_the_players(cards, replacer, theirs, drawn):
    # (review 29C) 121.2a / 616.1g: a replacement that refers to the number of cards drawn changes the whole instruction before any card is
    # drawn (the Quantum Riddler and Alms Collector rulings). Whether "and reveal them. You may cast one of them" then reaches the cards is
    # unsettled: 614.11b / 121.6c read literally keep the additional action off every card drawn as a result of the replacement, 121.2a
    # speaks of the instruction itself being modified, and no ruling names the case. Neither guess is automated: the players resolve the
    # reveal and the cast by hand (nothing revealed, nothing offered for free), and the log says why
    s, door = lair(cards, replacer, theirs=theirs)
    manual: list[str] = []
    offered, during, after = enter_the_lair(s, door, manual)
    assert offered == [] and len(manual) == 1 and "121.2a" in manual[0] and "by hand" in manual[0], (offered, manual)
    assert not any(name in during or name in after for name in drawn)  # (nothing shown to Bob by the engine)
    assert set(drawn) <= {s.state.cards[c].name for c in s.state.zones["p1:hand"]}
    roundtrip(s)


def test_a_count_replacement_that_does_not_apply_changes_nothing(cards):
    # (review 29C) Quantum Riddler with two cards in hand: "as long as you have one or fewer cards in hand" doesn't hold, so all three
    # cards are drawn by the printed instruction and revealed (the control for the test above)
    s, door = lair(cards, "Quantum Riddler")
    forests = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:2]
    act(s, "p1", type="move", card_ids=forests, to={"player": "p1", "zone": "hand"})
    manual: list[str] = []
    offered, _, _ = enter_the_lair(s, door, manual)
    assert set(offered) == {"Lightning Bolt", "Counterspell", "Murder"} and manual == [], (offered, manual)
    roundtrip(s)


# -- "If you do" after a draw (CR 118.12: the player chose to draw, whatever replaced the draw) ------------------------------------------------
def riddlesmith_ring(cards, *extra):
    """Riddlesmith in play (a token with its Oracle text) and Sol Ring cast: "you may draw a card. If you do, discard a card." Returns the
    prompts asked while it resolved (every may answered yes, every other choice the first option)."""
    from tests.test_rules_conditionals import RIDDLESMITH, creature
    from tests.test_rules_wave9b_exile_permission import build, put

    s = build(cards, p1=("Sol Ring", *extra))
    for name in extra:
        put(s, name, "battlefield")
    creature(s, "p1", "Riddlesmith", "2/1", "Token Creature — Human Artificer", text=RIDDLESMITH)
    ring = put(s, "Sol Ring", "hand")
    mana(s, C=1)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=ring.id)
    prompts: list[str] = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            prompts.append(d.prompt)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if d.kind == "confirm" else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, prompts, hand


def test_if_you_do_holds_when_the_chosen_draw_was_replaced(cards):
    # (review 29C) 118.12: "[A player] may [do something]. If [that player] [does] …" — the draw is a cost paid as the ability resolves, and
    # "if you do" checks that the player chose to pay it, "regardless of what events actually occurred" (118.11; the CR's Dermoplasm example,
    # the Psychic Vortex ruling of 2008-04-01). Underrealm Lich replaces the draw (no card is drawn), and the discard still happens
    s, _, hand = riddlesmith_ring(cards, "Underrealm Lich")
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 1 - 1  # (Sol Ring left the hand, one card was put in, one discarded)
    assert len(s.state.zones["p1:graveyard"]) == 2 + 1  # (the two cards of the look that weren't chosen, and the discarded card)
    assert s.state.rules.turn_log.drew.get("p1", 0) == 0
    roundtrip(s)


def test_if_you_do_still_follows_a_draw_that_happened(cards):
    s, _, hand = riddlesmith_ring(cards)
    assert len(s.state.zones["p1:hand"]) == hand - 1 and len(s.state.zones["p1:graveyard"]) == 1  # (Sol Ring left; drew a card and discarded one)
    assert s.state.rules.turn_log.drew.get("p1", 0) == 1
    roundtrip(s)
