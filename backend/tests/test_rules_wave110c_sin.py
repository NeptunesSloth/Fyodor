"""Wave 110C: Sin, Unending Cataclysm: "As Sin enters, remove all counters from any number of artifacts, creatures, and enchantments" (122.1; any player's permanents,
chosen as it enters like devour's sacrifices, 702.82a): it enters with twice as many +1/+1 counters as were really removed; when it dies its counters go to a creature."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110c_kit import answer, check, make_db, mana, put, real, to_hand

SIN = ("Flying, trample\nAs Sin enters, remove all counters from any number of artifacts, creatures, and enchantments. Sin enters with X +1/+1 counters on it, where X "
       "is twice the number of counters removed this way.\nWhen Sin dies, put its counters on target creature you control, then shuffle this card into its owner's library.")
EXTRA = [real("Sin, Unending Cataclysm", "{5}{G}{U}", 7, "Legendary Creature — Leviathan Avatar", SIN, ("5", "5"), "GU"),
         real("Plain Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
         real("Charged Rock", "{1}", 1, "Artifact", "", None, ""),
         real("Doom Blade", "{1}{B}", 2, "Instant", "Destroy target creature.", None, "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Sin, Unending Cataclysm")).level == "FULL"


def counters(s, c):
    return dict(s.state.cards[c.id].counters)


def table(cards):
    s = build(cards, ["Sin, Unending Cataclysm", "Plain Bear", "Doom Blade"], ["Charged Rock"])
    bear, rock = put(s, "Plain Bear"), put(s, "Charged Rock", "p2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=2)
    act(s, "p1", type="counter", card_ids=[rock.id], kind="charge", delta=1)
    return s, bear, rock


def enter_sin(s, picks):
    c = to_hand(s, "Sin, Unending Cataclysm")
    mana(s, G=1, U=1, C=5)
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s, *picks)
    return c


@pytest.mark.parametrize("which,removed", [(("bear", "rock"), 3), (("bear",), 2), (("rock",), 1), ((), 0)])
def test_removes_all_counters_from_the_chosen(cards, which, removed):
    s, bear, rock = table(cards)
    ids = {"bear": bear.id, "rock": rock.id}
    sin = enter_sin(s, [*(ids[w] for w in which), "done"])
    assert s.state.cards[sin.id].zone == "p1:battlefield" and counters(s, sin).get("+1/+1", 0) == 2 * removed
    assert counters(s, bear).get("+1/+1", 0) == (0 if "bear" in which else 2) and counters(s, rock).get("charge", 0) == (0 if "rock" in which else 1)
    check(s)


def test_dies_gives_its_counters_to_a_creature_and_shuffles_in(cards):
    s, bear, rock = table(cards)
    sin = enter_sin(s, [bear.id, rock.id, "done"])
    blade = to_hand(s, "Doom Blade")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=blade.id, targets=[sin.id])
    answer(s, bear.id)
    assert counters(s, bear).get("+1/+1") == 6 and s.state.cards[sin.id].zone == "p1:library"
    check(s)
