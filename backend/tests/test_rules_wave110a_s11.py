"""Wave 110A session 11: real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Displaced Dinosaurs - 614.12 / 205.1b / 613.4b: a historic permanent you control becomes a 7/7 Dinosaur creature in addition as it enters.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

DINO = "Displaced Dinosaurs"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([DINO])


def test_historic_artifact_enters_as_a_7_7_dinosaur_creature(cards):
    s = build(cards, [DINO, "Sol Ring"])
    put(s, DINO)
    ring = cast(s, "Sol Ring")
    answer(s)
    c = ch(s, ring)
    assert {"Artifact", "Creature"} <= set(c.types) and "Dinosaur" in c.subtypes and c.pt == (7, 7)
    check(s)


def test_non_historic_permanent_is_unchanged(cards):
    s = build(cards, [DINO, "Grizzly Bears"])
    put(s, DINO)
    bears = cast(s, "Grizzly Bears")
    answer(s)
    assert ch(s, bears).pt == (2, 2) and "Dinosaur" not in ch(s, bears).subtypes  # 700.6: not historic
    check(s)


def test_opponents_historic_permanent_is_unchanged(cards):
    s = build(cards, ["Sol Ring"], [DINO])
    put(s, DINO, "p2")
    ring = cast(s, "Sol Ring")
    answer(s)
    assert "Creature" not in ch(s, ring).types  # "you control": the Dinosaurs' controller only
    check(s)
