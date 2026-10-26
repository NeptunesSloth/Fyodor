"""Wave 110C (last batch): Smuggler Captain (905.2: nothing was noted, the quality search finds nothing, 701.24 the library is still shuffled)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, real

SMUGGLER = ("Draft this card face up.\nAs you draft a card, you may reveal it, note its name, then turn this card face down.\n"
            "When this creature enters, you may search your library for a card with a name you noted for cards named Smuggler Captain, reveal it, put it into your hand, then shuffle.")
EXTRA = [real("Smuggler Captain", "{3}{B}", 4, "Creature — Human Pirate", SMUGGLER, ("2", "2"), "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Smuggler Captain", "Torrent Elemental"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_smuggler_captain_shuffles(cards):
    s = build(cards, ["Smuggler Captain"])
    before = list(s.state.zones["p1:library"])
    mana(s, B=4)
    cast(s, "Smuggler Captain")
    answer(s, "yes")
    after = list(s.state.zones["p1:library"])
    assert len(after) == len(before) - 1 and not set(after) & set(before)  # (the shuffle re-keyed every card, 701.24a)
    check(s)


def test_smuggler_captain_declined(cards):
    s = build(cards, ["Smuggler Captain"])
    mana(s, B=4)
    cast(s, "Smuggler Captain")
    lib = list(s.state.zones["p1:library"])
    answer(s, "no")
    assert s.state.zones["p1:library"] == lib
    check(s)


TORRENT = ("Flying\nWhenever this creature attacks, tap all creatures defending player controls.\n"
           "{3}{B/G}{B/G}: Put this card from exile onto the battlefield tapped. Activate only as a sorcery.")
EXTRA.append(real("Torrent Elemental", "{4}{U}", 5, "Creature — Elemental", TORRENT, ("3", "5"), "U"))


def test_torrent_elemental_from_exile(cards):
    """113.6m: the ability works only from exile (not the hand or graveyard); sorcery speed (602.5d); enters tapped."""
    from app.game.errors import ActionError
    from tests.wave110c_kit import card_named

    s = build(cards, ["Torrent Elemental"])
    c = card_named(s, "Torrent Elemental")
    mana(s, B=5)
    with pytest.raises(ActionError):  # (still in the library)
        act(s, "p1", type="activate_ability", card_id=c.id, ability=2)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    with pytest.raises(ActionError):  # (a graveyard is not exile)
        act(s, "p1", type="activate_ability", card_id=c.id, ability=2)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "exile"})
    act(s, "p1", type="activate_ability", card_id=c.id, ability=2)
    answer(s)
    assert s.state.cards[c.id].zone == "p1:battlefield" and s.state.cards[c.id].tapped
    check(s)
