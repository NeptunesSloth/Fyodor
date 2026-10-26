"""Wave 110F session 17, on real Oracle text. Every scenario checks the replay and a save and a load.

* 903.11, 608.2d: Extrapolate the Impossible: in Commander no card can be revealed from outside the game, so nothing is revealed, chosen or put into hand.
"""

from __future__ import annotations

from app.game.state import CollectionCard
from app.rules import coverage
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import answer, card_db, cast  # noqa: F401  (fixture DB with EXTRA)
from tests.wave9c_kit import build, check, mana

_BASE.append(real("Extrapolate the Impossible", "{1}{B}", 2, "Sorcery",
                  "You may reveal exactly two cards you own with different names from outside the game. An opponent chooses one of them. You put that card into your hand.",
                  None, "B"))


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Extrapolate the Impossible")).level == "FULL"


def test_extrapolate_the_impossible_imports_nothing_in_commander(cards):
    s = build(cards, ["Extrapolate the Impossible"])
    a, b = cards.resolve("Grizzly Bears"), cards.resolve("Llanowar Elves")
    s.state.collections["p1"] = [CollectionCard(printing_id=c["id"], oracle_id=c["oracle_id"], name=c["name"], quantity=1) for c in (a, b)]
    from app.game.session import GameSession

    s = GameSession(s.state, cards=s.cards)  # (the collections are part of the initial saved/replay state, as in a lobby-created game)
    before = dict(s.state.cards)
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", B=1, C=1)
    spell = cast(s, "Extrapolate the Impossible")
    answer(s)
    assert set(s.state.cards) == set(before) and s.state.cards[spell.id].zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand  # (the spell left the hand; nothing came in)
    assert [c.quantity for c in s.state.collections["p1"]] == [1, 1]
    check(s)
