"""Wave 110C: Midnight Arsonist (605.1a an artifact with a mana ability isn't a legal target; X counts the Vampires, 608.2h)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real

EXTRA = [real("Midnight Arsonist", "{2}{R}{R}", 4, "Creature — Vampire Warlock",
              "When this creature enters, destroy up to X target artifacts without mana abilities, where X is the number of Vampires you control.",
              ("4", "3"), "R"),
         real("Mana Rock", "{2}", 2, "Artifact", "{T}: Add {C}.", None, ""),
         real("Plain Relic", "{2}", 2, "Artifact", "", None, ""),
         real("Other Relic", "{2}", 2, "Artifact", "", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Midnight Arsonist")).level == "FULL"


def test_destroys_only_artifacts_without_mana_abilities_up_to_vampire_count(cards):
    s = build(cards, ["Midnight Arsonist"], ["Mana Rock", "Plain Relic", "Other Relic"])
    rock, relic, other = (put(s, n, "p2") for n in ("Mana Rock", "Plain Relic", "Other Relic"))
    mana(s, "p1", R=2, C=2)
    cast(s, "Midnight Arsonist")
    d = s.state.rules.decision
    assert d is not None and rock.id not in {o.id for o in d.options} and relic.id in {o.id for o in d.options}
    answer(s, [relic.id])
    assert s.state.cards[relic.id].zone == "p2:graveyard"
    assert s.state.cards[rock.id].zone == "p2:battlefield" and s.state.cards[other.id].zone == "p2:battlefield"  # X = 1 Vampire: one target, no mana rock
    check(s)
