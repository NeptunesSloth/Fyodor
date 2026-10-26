"""Wave 110F final pass, on real Oracle text. Every scenario checks the replay and a save and a load.

* 701.55a-b, 608.2c, 603.5: The Master, Gallifrey's End: "you may exile it. If you do, ..." the opponent with the most life faces a villainous choice.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, card_named, check, life, mana, put

_MASTER = ("Make Them Pay — Whenever a nontoken artifact creature you control dies, you may exile it. If you do, choose an opponent with the most life among your "
           "opponents. That player faces a villainous choice — They lose 4 life, or you create a token that's a copy of that card.")
EXTRA = [
    real("The Master, Gallifrey's End", "{3}{B}{B}", 5, "Legendary Creature — Time Lord Rogue", _MASTER, ("4", "4"), "B"),
    real("Test Smite 110FF", "{B}", 1, "Instant", "Destroy target creature.", None, "B"),
    real("Test Golem 110FF", "{2}", 2, "Artifact Creature — Golem", "", ("2", "2"), ""),
]
_BASE.extend(EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("The Master, Gallifrey's End")).level == "FULL"


def _setup(cards):
    s = build(cards, ["The Master, Gallifrey's End", "Test Golem 110FF", "Test Smite 110FF"])
    put(s, "The Master, Gallifrey's End")
    golem = put(s, "Test Golem 110FF")
    mana(s, "p1", B=1)
    cast(s, "Test Smite 110FF", [golem.id])
    return s, golem


def _step(s, pick=None):
    """Pass priority until a decision shows; return it (None: settled)."""
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            return d
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")


def _answer(s, d, opt):
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[opt])


def _tokens(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Test Golem 110FF" and c.zone == "p1:battlefield"]


@pytest.mark.parametrize("choice,lost,tokens", [("a", 4, 0), ("b", 0, 1)])
def test_villainous_choice(cards, choice, lost, tokens):
    """701.55a: the opponent with the most life picks; the chosen option is carried out."""
    s, golem = _setup(cards)
    _answer(s, _step(s), "yes")
    d = _step(s)
    assert d.player == "p2"
    _answer(s, d, choice)
    assert _step(s) is None
    assert s.state.cards[golem.id].zone == "p1:exile"
    assert life(s, "p2") == 40 - lost and len(_tokens(s)) == tokens
    check(s)


def test_declined_keeps_the_card(cards):
    """603.5: "you may exile it": declined means no "if you do" part."""
    s, golem = _setup(cards)
    _answer(s, _step(s), "no")
    assert _step(s) is None
    assert s.state.cards[golem.id].zone == "p1:graveyard" and life(s, "p2") == 40
    check(s)


_ANIMATE = "Enchant artifact\nAs long as enchanted artifact isn't a creature, it's an artifact creature with power and toughness each equal to its mana value."
EXTRA2 = [
    real("Animate Artifact", "{3}{U}", 4, "Enchantment — Aura", _ANIMATE, None, "U"),
    real("Test Rock 110FF", "{3}", 3, "Artifact", "", None, ""),
    real("Test Big Golem 110FF", "{5}", 5, "Artifact Creature — Golem", "", ("2", "3"), ""),
]
_BASE.extend(EXTRA2)


def test_animate_full(cards):
    assert coverage.of_card_data(cards.resolve("Animate Artifact")).level == "FULL"


def _stats(s, c):
    from app.rules import sba
    from app.rules.plan import Plan

    card = s.state.cards[c.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(card)
    return ch.is_creature, sba.power(card, ch), sba.toughness(card, ch)


@pytest.mark.parametrize("host,expect", [("Test Rock 110FF", (True, 3, 3)), ("Test Big Golem 110FF", (True, 2, 3))])
def test_animate_artifact(cards, host, expect):
    """613.1d, 613.4b: a noncreature artifact becomes an artifact creature with P/T = its mana value; one that already is a creature keeps its own P/T (2008-08-01 ruling)."""
    s = build(cards, ["Animate Artifact", host])
    rock = put(s, host)
    mana(s, "p1", U=1, C=3)
    cast(s, "Animate Artifact", [rock.id])
    answer(s)
    assert _stats(s, rock) == expect
    check(s)


def test_animate_artifact_leaves(cards):
    s = build(cards, ["Animate Artifact", "Test Rock 110FF", "Test Smite 110FF"])
    rock = put(s, "Test Rock 110FF")
    mana(s, "p1", U=1, C=3)
    cast(s, "Animate Artifact", [rock.id])
    answer(s)
    aura = card_named(s, "Animate Artifact")
    act(s, "p1", type="move", card_ids=[aura.id], to={"player": "p1", "zone": "graveyard"})
    assert _stats(s, rock)[0] is False
    check(s)
