"""Wave 110D: Niko, Light of Hope, real Oracle text (tests/fixtures/wave110d_cards.json).

* 707.9 / 608.2h: the Shards become copies of the exiled creature (as it last existed) until the next end step begins (611.2a).
* 603.7: the creature returns under its owner's control at the beginning of that end step.
"""

from __future__ import annotations

from tests.wave110d_kit import (  # noqa: F401
    activate,
    build,
    card_db,
    cast_on,
    ch,
    check,
    full,
    hand_new,
    mana,
    now,
    put_new,
    refused,
    settle,
    to_phase,
)

NAME = "Niko, Light of Hope"


def test_full():
    assert full(NAME)


def _board(cards):
    s = build(cards, [NAME, "Hill Giant"], ["Grizzly Bears"])
    giant = put_new(s, "Hill Giant")
    niko = cast_on(s, NAME)
    to_phase(s, "main1", turn=3)
    return s, niko, giant


def _shards(s):
    return [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]


def test_shards_copy_it_until_the_end_step_and_it_comes_back(cards):
    s, niko, giant = _board(cards)
    assert len(_shards(s)) == 2 and all(ch(s, c).name == "Shard" for c in _shards(s))
    mana(s, C=2)
    activate(s, niko, "{2}, {T}", targets=[giant.id])
    assert now(s, giant).zone == "p1:exile"
    assert [ch(s, c).name for c in _shards(s)] == ["Hill Giant", "Hill Giant"]  # the Shards are 3/3 Giants now
    to_phase(s, "end", turn=3)
    assert all(ch(s, c).name == "Shard" for c in _shards(s))  # the copy ended as the end step began
    settle(s)
    assert [c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Hill Giant" and not c.is_token]  # and the Giant is back
    check(s)


def test_a_legendary_creature_is_no_target(cards):
    s, niko, giant = _board(cards)
    mana(s, C=2)
    refused(s, "legal target", niko, "{2}, {T}", targets=[niko.id])
