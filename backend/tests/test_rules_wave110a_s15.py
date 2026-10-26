"""Wave 110A session 15: layer-6 timestamp order for the Zinnia offspring grant against a real static "loses all abilities" (Sludge Monster)."""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

from app.rules import wave110a_grants  # isort: skip


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _bears(s):
    return next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield" and not c.token)


def _run(cards, wipe_first):
    s = build(cards, ["Zinnia, Valley's Voice", "Grizzly Bears", "Sludge Monster"])
    put(s, "Zinnia, Valley's Voice")
    if wipe_first:
        put(s, "Sludge Monster")
    c = to_hand(s, "Grizzly Bears")
    fund(s, "{1}{G}{2}")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1)
    answer(s)
    if not wipe_first:
        put(s, "Sludge Monster")
    check(s)
    bears = _bears(s)
    bears.counters["slime"] = 1  # Sludge Monster: "Non-Horror creatures with slime counters on them lose all abilities"
    s.state.seq += 1
    return s, bears


def test_wipe_earlier_than_the_grant_keeps_the_granted_offspring(cards):  # 613.7: the permanent's timestamp is later than Sludge Monster's, so the grant applies after the wipe
    s, bears = _run(cards, True)
    assert wave110a_grants.granted_offspring(ch(s, bears))


def test_wipe_later_than_the_grant_removes_the_granted_offspring(cards):  # 613.7: Sludge Monster entered after the creature, so its wipe applies after the grant
    s, bears = _run(cards, False)
    assert not wave110a_grants.granted_offspring(ch(s, bears))
