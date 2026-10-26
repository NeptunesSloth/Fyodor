"""Wave 110D: Jin-Gitaxias // The Great Synthesis, real Oracle text (tests/fixtures/wave110d_cards.json).

* 714.2c, 714.3b: chapters trigger as lore counters are added (precombat main phase, and as the Saga enters).
* I: draw cards equal to the cards in hand; 402.2 + 611.2b: no maximum hand size for as long as you control that Saga (it ends when the
  Saga leaves; delayed.expire).
* III: cast any number of spells from hand free (601.2); 400.7: exile the Saga, return it as a new object, front face up (712.14a).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import ability, card_db, check, full, hand_new, mana, now, put_new, settle, to_phase  # noqa: F401

NAME = "Jin-Gitaxias // The Great Synthesis"


def _saga(cards, extra=()):
    s = build(cards, [NAME, "Grizzly Bears", "Ambush Viper", *extra, *["Forest"] * 30])
    jin = put_new(s, NAME)
    for _ in range(7):
        hand_new(s, "Forest")
    to_phase(s, "main1", turn=3)
    mana(s, "p1", U=1, C=3)
    s.before = len(_hand(s))
    act(s, "p1", type="activate_ability", card_id=jin.id, ability=ability(s, jin, "{3}{U}"), sources=[])
    settle(s)
    return s, jin


def _hand(s):
    return [c for c in s.state.cards.values() if c.zone == "p1:hand"]


def test_jin_is_full():
    assert full(NAME)


def test_chapter_one_draws_and_lifts_the_limit(cards):
    s, jin = _saga(cards)
    assert now(s, jin).face == 1 and len(_hand(s)) == 2 * s.before >= 14  # as many drawn as in hand when chapter I resolved
    to_phase(s, "main1", turn=5)  # cleanup of turn 3 passed: no discard down to seven
    assert len(_hand(s)) >= 2 * s.before and now(s, jin).zone == "p1:battlefield"
    assert any(e.hand_limit for e in s.state.rules.effects)
    check(s)


def test_chapter_three_casts_free_and_returns_front_face(cards):
    s, jin = _saga(cards, ["Grizzly Bears"] * 3)
    bears = to_hand(s, "Grizzly Bears")
    to_phase(s, "main1", turn=5)  # chapter II: no non-Phyrexian creature but the Saga's controller's Bears are in hand only
    to_phase(s, "main1", turn=7)  # chapter III
    settle(s, answers=[])
    assert now(s, bears).zone == "p1:battlefield"  # cast without paying its mana cost
    new = now(s, jin)
    assert new.zone == "p1:battlefield" and new.face == 0
    assert not any(e.hand_limit for e in s.state.rules.effects)  # 611.2b: it no longer controls that Saga
    check(s)
