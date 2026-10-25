"""Wave 110C: Foggy Swamp Visions (701.59-ish waterbend X, 707.2 copy, 111.7): exiled cards become token copies that are sacrificed at the caster's next end step."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import STEPS, answer, build, cast, check, make_db, mana, put, real  # noqa: F401

TEXT = ("As an additional cost to cast this spell, waterbend {X}. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)\n"
        "Exile X target creature cards from graveyards. For each creature card exiled this way, create a token that's a copy of it. At the beginning of your next end step, sacrifice those tokens.")
EXTRA = [real("Foggy Swamp Visions", "{1}{B}{B}", 3, "Sorcery", TEXT, None, "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Foggy Swamp Visions")).level == "FULL"


def test_exiled_creature_cards_return_as_token_copies_then_are_sacrificed(cards):
    s = build(cards, ["Foggy Swamp Visions", "Grizzly Bears"], ["Courser of Kruphix"])
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    giant = next(c for c in s.state.cards.values() if c.name == "Courser of Kruphix")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[giant.id], to={"player": "p2", "zone": "graveyard"})
    mana(s, B=2, C=3)
    cast(s, "Foggy Swamp Visions", [bears.id, giant.id], x_value=2, target_counts=[2])
    answer(s)
    toks = [c for c in s.state.cards.values() if c.token is not None and c.zone == "p1:battlefield"]
    assert sorted(t.name for t in toks) == ["Courser of Kruphix", "Grizzly Bears"]
    assert s.state.cards[bears.id].zone.endswith("exile") and s.state.cards[giant.id].zone.endswith("exile")
    check(s)
    to_phase(s, "main1", 3)
    assert not [c for c in s.state.cards.values() if c.token is not None and c.zone == "p1:battlefield"]
    check(s)
