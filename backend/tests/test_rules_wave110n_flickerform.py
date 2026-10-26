"""Wave 110N: Flickerform (701.13 exile, 603.7 the end step return, 303.4f the Auras come back attached to the creature)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

FORM, VEIL = "Flickerform", "Binding Veil"
EXTRA = [
    real(FORM, "{2}{W}{W}", 4, "Enchantment — Aura",
         "Enchant creature\n{2}{W}{W}: Exile enchanted creature and all Auras attached to it. At the beginning of the next end step, return that card to the battlefield under its owner's "
         "control. If you do, return the other cards exiled this way to the battlefield under their owners' control attached to that creature.", None, "W"),
    real(VEIL, "{2}{W}", 3, "Enchantment — Aura", "Enchant creature", None, "W"),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([FORM])


def attached_to(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].attached_to


def test_the_creature_and_all_its_auras_come_back_at_the_end_step_attached(cards):
    s = build(cards, [FORM, VEIL, "Grizzly Bears"], [VEIL])
    bears = put(s, "Grizzly Bears")
    auras = {}
    for name, pid in ((FORM, "p1"), (VEIL, "p1"), (VEIL, "p2")):
        a = put(s, name, pid)
        act(s, "p1", type="attach", card_ids=[a.id], to=bears.id)
        auras[(name, pid)] = a
    mana(s, "p1", W=2, C=2)
    act(s, "p1", type="activate_ability", card_id=auras[(FORM, "p1")].id, ability=1)
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:exile" and all(a.id and s.state.cards[a.id].zone.endswith(":exile") for a in auras.values())
    stops(s)
    to_phase(s, "end")
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"
    assert all(s.state.cards[a.id].zone.endswith(":battlefield") and s.state.cards[a.id].attached_to == bears.id for a in auras.values())
    assert s.state.cards[auras[(VEIL, "p2")].id].zone == "p2:battlefield"  # under its owner's control
    check(s)
