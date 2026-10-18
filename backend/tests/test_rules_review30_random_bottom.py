"""Review 30: cards put into a library together don't reveal their order (CR 2026-09-25), real Oracle text
(tests/fixtures/review30_random_bottom_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 401.4: "If an effect puts two or more cards in a specific position in a library at the same time, the owner of those cards may arrange
  them in any order. That library's owner doesn't reveal the order in which the cards go into the library."
* "… on the bottom of your library in a random order": nobody chooses and nobody learns the order, its controller included (the cards it
  looked at privately are named to it, never in the order they went in).
* The wave 29B fix (one batched move, `effects.bottom_at_random`) covered cascade and discover only; the look / reveal / exile forms
  (`rest_looked`, `rest_exiled`) and a chosen order (`resume_order_library`) logged one move per card, so the order was readable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.visibility import SPECTATOR
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "review30_random_bottom_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r30b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
VIEWERS = ("p1", "p2", SPECTATOR)
NONLANDS = ["Hill Giant", "Gray Ogre", "Craw Wurm"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def stack_top(s, names, pid="p1"):
    """Put these cards on top of the library, the first named on top."""
    for name in reversed(names):
        c = card_named(s, name, pid)
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")


def settle(s, prefer=(), limit=40):
    """Resolve everything; a choice is answered with ``prefer`` (the options it has, in that order) or its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o for o in prefer if o in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def bottom_lines(s, viewer):
    """The rendered log lines that put cards on the bottom of a library, as (names listed, hidden count)."""
    out = []
    for e in s.view(viewer)["log"]:
        if any(" put on the bottom of " in (p.get("t") or "") for p in e["parts"]):
            g = next(p for p in e["parts"] if "group" in p)
            out.append(([x["card"]["name"] for x in g["group"]], g["hidden"]))
    return out


def bottom_names(s, n, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:library"][-n:]]


def test_a_revealed_random_bottom_is_one_line_in_no_particular_order(cards):
    """Clifftop Lookout: "reveal cards from the top of your library until you reveal a land card. Put that card onto the battlefield tapped
    and the rest on the bottom of your library in a random order." The three revealed cards are public, so everyone sees their names, but in
    one line whose order is the same whatever order they went in."""
    orders, lines = set(), set()
    for _ in range(12):
        s = build(cards, ["Clifftop Lookout", *NONLANDS])
        stack_top(s, NONLANDS)
        to_hand(s, "Clifftop Lookout")
        mana(s, G=3)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Clifftop Lookout").id)
        settle(s)
        assert sorted(bottom_names(s, 3)) == sorted(NONLANDS)
        orders.add(tuple(bottom_names(s, 3)))
        for v in VIEWERS:
            got = bottom_lines(s, v)
            assert got == [(sorted(NONLANDS), 0)], (v, got)
            lines.add((v, json.dumps(got)))
        check(s)
    assert len(orders) > 1  # (it is random)
    assert len(lines) == len(VIEWERS)  # (and the log is the same every time)


def test_cards_looked_at_privately_go_to_the_bottom_unnamed_and_unordered(cards):
    """Monumental Henge: "Look at the top five cards of your library. You may reveal a historic card from among them and put it into your hand.
    Put the rest on the bottom of your library in a random order." Only its controller saw them: the opponent and a spectator see a count; the
    controller sees the names, never the order they went in."""
    five = ["Hill Giant", "Gray Ogre", "Craw Wurm", "Raging Goblin", "Goblin Ringleader"]
    orders = set()
    for _ in range(10):
        s = build(cards, ["Monumental Henge", *five])
        stack_top(s, five)
        henge = put(s, "Monumental Henge")
        mana(s, W=2, C=2)
        act(s, "p1", type="activate_ability", card_id=henge.id, ability=2)
        settle(s, prefer=("none", "no", "skip", "decline"))
        assert sorted(bottom_names(s, 5)) == sorted(five)
        orders.add(tuple(bottom_names(s, 5)))
        assert bottom_lines(s, "p1") == [(sorted(five), 0)]
        for v in ("p2", SPECTATOR):
            assert bottom_lines(s, v) == [([], 5)], v
        check(s)
    assert len(orders) > 1


def test_exiled_cards_not_cast_go_to_the_bottom_in_one_unordered_line(cards):
    """Herald of Amity: "exile the top eight cards of your library. You may cast an Aura spell from among them without paying its mana cost.
    Then put the rest on the bottom of your library in a random order." (`rest_exiled`)"""
    eight = ["Hill Giant", "Gray Ogre", "Craw Wurm", "Raging Goblin", "Goblin Ringleader", "Clifftop Lookout", "Mountain", "Monumental Henge"]
    orders = set()
    for _ in range(10):
        s = build(cards, ["Herald of Amity", *eight])
        stack_top(s, eight)
        to_hand(s, "Herald of Amity")
        mana(s, W=1, C=3)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Herald of Amity").id)
        settle(s)
        assert sorted(bottom_names(s, 8)) == sorted(eight) and not s.state.zones.get("p1:exile")
        orders.add(tuple(bottom_names(s, 8)))
        for v in VIEWERS:
            assert bottom_lines(s, v) == [(sorted(eight), 0)], v
        check(s)
    assert len(orders) > 1


def test_an_order_the_player_chooses_is_kept_but_not_shown(cards):
    """Goblin Ringleader: "reveal the top four cards of your library. Put all Goblin cards revealed this way into your hand and the rest on
    the bottom of your library in any order." The order is its owner's private choice (401.4): the library gets it, the log lists the
    revealed cards in one line in no particular order."""
    four = ["Raging Goblin", "Hill Giant", "Gray Ogre", "Craw Wurm"]
    s = build(cards, ["Goblin Ringleader", *four])
    stack_top(s, four)
    to_hand(s, "Goblin Ringleader")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Goblin Ringleader").id)
    chosen = ["Gray Ogre", "Craw Wurm", "Hill Giant"]  # (the first chosen ends at the very bottom)
    settle(s, prefer=[card_named(s, n).id for n in chosen])
    assert card_named(s, "Raging Goblin").zone == "p1:hand"
    assert bottom_names(s, 3) == list(reversed(chosen))
    for v in VIEWERS:
        assert bottom_lines(s, v) == [(sorted(chosen), 0)], v
    check(s)
