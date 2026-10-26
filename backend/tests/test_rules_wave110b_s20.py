"""Wave 110B session 20: single cards (real Oracle text in tests/fixtures/wave110b_cards.json).

* The Raven's Warning: 903.11 no card from outside the game comes into a Commander game, so chapter III offers nothing and the Saga is sacrificed (714.4).
* Summon: Brynhildr: 122.1, 611.2a the exiled card stays playable in every turn its controller puts a lore counter on the Saga (it enters with one, 714.3a), not in others.
* Temporal Extortion ruling check: tests/test_rules_wave110b_s19.py.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import build, card_named, check, drive, life, mana, repository, to_hand, zone_of


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["The Raven's Warning", "Summon: Brynhildr"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_ravens_warning_chapter_three_offers_nothing_from_outside_the_game(cards):
    """903.11: the optional import is impossible, so nothing is asked (608.2d); the Saga is sacrificed after III (714.4)."""
    s = build(cards, ["The Raven's Warning"], [], forests=30, islands=40)
    mana(s, W=1, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "The Raven's Warning").id)
    drive(s)
    assert life(s, "p1") == 42  # chapter I: the Bird and 2 life
    saga = card_named(s, "The Raven's Warning")
    library = len(s.state.zones["p1:library"])
    to_phase(s, "main1", turn=5)
    drive(s)  # chapters II and III: no decision is left open
    assert s.state.rules.decision is None and zone_of(s, "The Raven's Warning") == "p1:graveyard"
    assert saga.id in s.state.zones["p1:graveyard"] and len(s.state.zones["p1:library"]) <= library
    check(s)


@pytest.mark.parametrize(("turn", "playable"), [(1, True), (3, True), (7, False)])
def test_brynhildr_card_is_playable_in_turns_a_lore_counter_is_put(cards, turn, playable):
    """122.1, 611.2a: playable on the turn the Saga enters (its lore counter) and on later turns with a lore counter put; not once the Saga is gone (turn 7, III was turn 5)."""
    s = build(cards, ["Summon: Brynhildr"], [], forests=30, islands=40)
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Summon: Brynhildr").id)
    drive(s)
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile" and c.name == "Forest"]
    assert len(exiled) == 1
    if turn > 1:
        to_phase(s, "main1", turn=turn)
        drive(s)
    if playable:
        act(s, "p1", type="play_land", card_id=exiled[0].id)
        assert s.state.cards[exiled[0].id].zone == "p1:battlefield"
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="play_land", card_id=exiled[0].id)
    check(s)
