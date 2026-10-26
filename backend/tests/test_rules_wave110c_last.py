"""Wave 110C (last batch): Smuggler Captain (905.2: nothing was noted, the quality search finds nothing, 701.24 the library is still shuffled)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, real

SMUGGLER = ("Draft this card face up.\nAs you draft a card, you may reveal it, note its name, then turn this card face down.\n"
            "When this creature enters, you may search your library for a card with a name you noted for cards named Smuggler Captain, reveal it, put it into your hand, then shuffle.")
EXTRA = [real("Smuggler Captain", "{3}{B}", 4, "Creature — Human Pirate", SMUGGLER, ("2", "2"), "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Smuggler Captain", "Torrent Elemental", "Monument to Perfection"])
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


MONUMENT = ("{3}, {T}: Search your library for a basic, Sphere, or Locus land card, reveal it, put it into your hand, then shuffle.\n"
            "{3}: This artifact becomes a 9/9 Phyrexian Construct artifact creature, loses all abilities, and gains indestructible and toxic 9. "
            "Activate only if there are nine or more lands with different names among the basic, Sphere, and Locus lands you control.")
SNOW = [("Snow-Covered Plains", "Plains", "W"), ("Snow-Covered Island", "Island", "U"), ("Snow-Covered Swamp", "Swamp", "B"),
        ("Snow-Covered Mountain", "Mountain", "R"), ("Snow-Covered Forest", "Forest", "G")]
EXTRA += [real("Monument to Perfection", "{4}", 4, "Artifact", MONUMENT, None, ""),
          *(real(n, "", 0, f"Basic Snow Land — {t}", f"({{T}}: Add {{{c}}}.)", None, "") for n, t, c in SNOW),
          *(real(n, "", 0, f"Basic Land — {t}", f"({{T}}: Add {{{c}}}.)", None, "") for n, t, c in [("Plains", "Plains", "W"), ("Island", "Island", "U"), ("Swamp", "Swamp", "B"), ("Mountain", "Mountain", "R")]),
          real("Test Locus", "", 0, "Land — Locus", "{T}: Add {C}.", None, ""),
          real("Test Plain Land", "", 0, "Land", "{T}: Add {C}.", None, "")]
EXTRA_NAMES = [n for n, _, _ in SNOW] + ["Plains", "Island", "Swamp", "Mountain", "Test Locus"]


def animate(s, mon):
    act(s, "p1", type="activate_ability", card_id=mon.id, ability=1)
    answer(s)


@pytest.mark.parametrize("lands, ok", [(EXTRA_NAMES[:9], True), (EXTRA_NAMES[:8], False), ([*EXTRA_NAMES[:8], "Test Plain Land"], False)])
def test_monument_needs_nine_names(cards, lands, ok):
    """201.2 / 205.3i: nine differently named basic, Sphere or Locus lands; a nonbasic land of another name does not count. Then it is a 9/9 for good (611.2a)."""
    from app.game.errors import ActionError
    from tests.wave110c_kit import put

    s = build(cards, ["Monument to Perfection", *lands])
    mon = put(s, "Monument to Perfection")
    for n in lands:
        put(s, n)
    mana(s, C=3)
    if not ok:
        with pytest.raises(ActionError):
            animate(s, mon)
        return
    animate(s, mon)
    ch = Plan(s.state, "p1", cards, None).ch(s.state.cards[mon.id])
    assert ch.is_creature and ch.pt == (9, 9) and "indestructible" in ch.keywords and "Phyrexian" in ch.subtypes
    assert any("Toxic" in a.text for a in ch.abilities) and not any("Search your library" in a.text for a in ch.abilities)
    to_phase(s, "main1", 4)
    ch = Plan(s.state, "p1", cards, None).ch(s.state.cards[mon.id])
    assert ch.is_creature  # (lasts indefinitely)
    check(s)
