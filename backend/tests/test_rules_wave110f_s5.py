"""Wave 110F session 5: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 701.24, 701.16a, 108.3: "Choose target creature. Its owner shuffles it into their library, then investigates." (Blink chapters I, III).
* 701.13a, 603.10, 110.2: "exile another target nonland permanent. If you controlled it, return it to the battlefield tapped. Otherwise, its controller creates a ... Detective" (Unyielding Gatekeeper).
* 205.1b, 611.2a: token "Whenever an opponent casts a creature spell, this token isn't a creature until end of turn." (Blink chapters II, IV).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100f_attached import to_phase
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, mana, put, to_hand

EXTRA = [
    real('Blink', '{2}{U}{B}', 4, 'Enchantment — Saga',
         '(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, III — Choose target creature. Its owner shuffles it into their library, then investigates. (They create a Clue token.)\nII, IV — Create a 2/2 black Alien Angel artifact creature token with first strike, vigilance, and "Whenever an opponent casts a creature spell, this token isn\'t a creature until end of turn."', None, 'BU'),
    real('Unyielding Gatekeeper', '{1}{W}', 2, 'Creature — Elephant Cleric',
         'Disguise {1}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, exile another target nonland permanent. If you controlled it, return it to the battlefield tapped. Otherwise, its controller creates a 2/2 white and blue Detective creature token.', ('3', '2'), 'W'),
    real('Test Flash Bear 110F', '{1}{U}', 2, 'Creature — Bear', 'Flash', ('2', '2'), 'U'),
]
_BASE.extend(EXTRA)
NAMES = ["Blink", "Unyielding Gatekeeper"]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _resolve(s, pick=None):
    for _ in range(14):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick or d.options[0].id])


def test_blink_chapter_one_shuffles_target_and_its_owner_investigates(cards):
    """701.24, 701.16a: the owner (p2) shuffles the creature away, then p2 (not the Saga's controller) gets the Clue."""
    s = build(cards, ["Blink", "Grizzly Bears"], ["Grizzly Bears"], forests=20, islands=20)
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, U=1, B=1, C=2)
    cast(s, "Blink")
    _resolve(s, bear.id)
    assert s.state.cards[bear.id].zone == "p2:library"
    clues = [c for c in s.state.cards.values() if c.name == "Clue"]
    assert [c.controller for c in clues] == ["p2"]
    check(s)


def test_blink_chapter_two_token_stops_being_a_creature_when_opponent_casts_a_creature(cards):
    """205.1b, 611.2a: the Alien Angel (2/2, first strike, vigilance) is no creature until end of turn once an opponent casts a creature spell."""
    from tests.test_rules_wave100f_control import ch

    s = build(cards, ["Blink", "Grizzly Bears"], ["Grizzly Bears", "Test Flash Bear 110F"], forests=20, islands=20)
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, U=1, B=1, C=2)
    cast(s, "Blink")
    _resolve(s, bear.id)
    act(s, "p2", type="set_stops", others=["end"], smart_pass=False)
    to_phase(s, "main1", turn=3)
    _resolve(s)
    angel = next(c for c in s.state.cards.values() if c.name == "Alien Angel")
    got = ch(s, angel)
    assert "Creature" in got.types and got.pt == (2, 2) and {"first strike", "vigilance"} <= set(got.keywords)
    to_phase(s, "end", turn=3)
    mana(s, U=1, C=1, pid="p2")
    cast(s, "Test Flash Bear 110F", pid="p2")
    _resolve(s)
    assert "Creature" not in ch(s, angel).types and "Artifact" in ch(s, angel).types
    check(s)


@pytest.mark.parametrize("mine", [True, False])
def test_gatekeeper_returns_your_permanent_tapped_or_gives_its_controller_a_detective(cards, mine):
    """Exiling your own permanent returns it tapped (no Detective); exiling an opponent's gives that opponent the 2/2 Detective."""
    s = build(cards, ["Unyielding Gatekeeper", "Grizzly Bears"], ["Grizzly Bears"])
    mana(s, C=3)
    gate = to_hand(s, "Unyielding Gatekeeper")
    act(s, "p1", type="cast_spell", card_id=gate.id, face_down=True)
    _resolve(s)
    bear = put(s, "Grizzly Bears", "p1" if mine else "p2")
    mana(s, W=1, C=1)
    act(s, "p1", type="turn_face_up", card_id=gate.id, method="disguise")
    _resolve(s, bear.id)
    detectives = [c for c in s.state.cards.values() if c.name == "Detective"]
    if mine:
        assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].tapped and not detectives
    else:
        assert s.state.cards[bear.id].zone == "p2:exile" and [c.controller for c in detectives] == ["p2"]
    check(s)
