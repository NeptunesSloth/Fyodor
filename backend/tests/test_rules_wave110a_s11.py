"""Wave 110A session 11: real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Displaced Dinosaurs - 614.12 / 205.1b / 613.4b: a historic permanent you control becomes a 7/7 Dinosaur creature in addition as it enters.
* Zariel, Archduke of Avernus - -6 emblem: 511.2 / 500.8 untap a creature and get an additional combat phase after the first combat only.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

DINO = "Displaced Dinosaurs"
ZARIEL = "Zariel, Archduke of Avernus"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([DINO, ZARIEL])


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


def _combats(s, bears, stop=60):
    """Attack with the bears in every combat of the turn until the end step; the number of declare attackers decisions seen."""
    seen = 0
    for _ in range(stop):
        d = s.state.rules.decision
        if d is None:
            if s.state.turn.phase == "end":
                return seen
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            seen += 1
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}] if not s.state.cards[bears.id].tapped else [])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never settled")


def test_zariel_emblem_untaps_a_creature_and_adds_one_combat_phase_only(cards):
    s = build(cards, [ZARIEL, "Grizzly Bears"])
    z = put(s, ZARIEL)
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[z.id], kind="loyalty", delta=6)
    next_turn(s)
    stops(s)
    act(s, "p1", type="activate_ability", card_id=z.id, ability=2)
    answer(s)
    assert any(c.zone == "p1:command" for c in s.state.cards.values())
    to_phase(s, "declare_attackers")
    assert _combats(s, bears) == 2  # the first combat, then exactly one more: the added phase is not a "first combat phase"
    assert s.state.cards[bears.id].tapped  # it attacked in the second combat after the emblem untapped it
    check(s)
