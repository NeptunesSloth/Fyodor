"""Wave 110D: Gollum, Scheming Guide, real Oracle text (tests/fixtures/wave110d_cards.json).

* 701.20 / 608.2d: look at the top two and reorder; the controller chooses land or nonland; an opponent guesses without seeing the card.
* 701.20a: the top card is revealed after the guess. Right: Gollum is removed from combat (506.4). Wrong: draw a card, Gollum can't be blocked (509.1b).
"""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave110d_kit import build, card_db, check, full, hand_new, now, put_new, to_phase  # noqa: F401

NAME = "Gollum, Scheming Guide"


def test_full():
    assert full(NAME)


def _attack(cards, top, kind, guess, guess_wrong=False):
    """Gollum attacks; the top card of Alice's library is ``top`` ("Lightning Bolt" or "Forest"); Alice chooses ``kind``, Bob guesses ``guess`` ("yes"/"no")."""
    s = build(cards, [NAME, "Lightning Bolt", "Lightning Bolt"], ["Grizzly Bears"])
    gollum = put_new(s, NAME)
    bears = put_new(s, "Grizzly Bears", "p2")
    to_phase(s, "declare_attackers", turn=3)
    deck_top = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == top and c.zone == "p1:library")
    other = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:library" and c.id != deck_top.id)
    for c in (other, deck_top):  # (the second, then the first: ends on top)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": gollum.id, "target": "p2"}])
    seen = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            break
        if "land or nonland" in d.prompt:
            ids = [kind]
        elif d.player == "p2" and "top card" in d.prompt:
            seen.append((d.prompt, json.dumps(s.view("p2"), default=str)))
            ids = [guess]
        elif d.kind == "declare_blockers":
            blocks = [{"blocker_id": bears.id, "attacker_id": gollum.id}]
            if guess_wrong:  # 509.1b: it can't be blocked
                with pytest.raises(ActionError):
                    act(s, "p2", type="declare_blockers", blocks=blocks)
            act(s, "p2", type="declare_blockers", blocks=[])
            continue
        else:
            ids = [o.id for o in d.options][: max(1, d.min_choices)]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    return s, gollum, bears, hand, seen


@pytest.mark.parametrize(("top", "kind", "guess", "right"), [("Lightning Bolt", "land", "no", True), ("Lightning Bolt", "land", "yes", False),
                                                           ("Forest", "land", "yes", True), ("Forest", "nonland", "yes", False),
                                                           ("Forest", "nonland", "no", True)])
def test_guess(cards, top, kind, guess, right):
    s, gollum, bears, hand, seen = _attack(cards, top, kind, guess, not right)
    drawn = len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) - hand
    assert drawn == (0 if right else 1)
    assert s.state.players["p2"].life == (40 if right else 38)  # right: removed from combat, no damage; wrong: unblocked 2 damage (Bears stayed home)
    assert now(s, bears).damage == 0
    check(s)


def test_the_guesser_does_not_see_the_card(cards):
    s, gollum, bears, hand, seen = _attack(cards, "Lightning Bolt", "land", "no")
    assert seen and all("Lightning Bolt" not in prompt and '"Lightning Bolt"' not in view for prompt, view in seen)
    assert "Lightning Bolt" in json.dumps(s.view("p2"), default=str)  # revealed afterwards (701.20a), in the log
