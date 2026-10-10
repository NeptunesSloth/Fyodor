"""Wave 24D: "you may search your library" under Mindlock Orb (614.17b: a player can't choose to do what can't happen, so the
optional search is skipped whole and its "then shuffle" with it, unlike a mandatory tutor's shuffle); and Grafdigger's Cage vs manifest."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana, put, to_hand

EXTRA = [
    real("Mindlock Orb", "{3}{U}", 4, "Artifact", "Players can't search libraries.", None, "U"),
    real("Path to Exile", "{W}", 1, "Instant", "Exile target creature. Its controller may search their library for a basic land card, put that card onto the battlefield tapped, then shuffle.", None, "W"),
    real("Probe Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def library(s, pid):
    return list(s.state.zones.get(f"{pid}:library", []))


@pytest.mark.parametrize("orb", [False, True])
def test_optional_search_under_mindlock_orb_does_not_shuffle(cards, orb):
    s = build(cards, ["Path to Exile", "Mindlock Orb"], ["Probe Bear"])
    if orb:
        put(s, "Mindlock Orb")
    bear = put(s, "Probe Bear", "p2")
    before = library(s, "p2")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Path to Exile").id, targets=[bear.id])
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if d.kind == "confirm" else d.options[0].id][:1]
                if d.kind == "confirm" else [d.options[0].id][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[bear.id].zone == "p2:exile"
    if orb:  # nothing asked, nothing found, and the library is untouched (not shuffled)
        assert library(s, "p2") == before
        assert not any(c.zone == "p2:battlefield" and c.name == "Island" for c in s.state.cards.values())
    else:
        assert library(s, "p2") != before  # the search happened and the library was shuffled
    check(s)


# -- Grafdigger's Cage vs manifest (701.40f, 614.17d) ------------------------------------------------------------------------
EXTRA += [
    real("Grafdigger's Cage", "{1}", 1, "Artifact", "Creature cards in graveyards and libraries can't enter the battlefield.\nPlayers can't cast spells from graveyards or libraries."),
    real("Soul Summons", "{W}", 1, "Sorcery", "Manifest the top card of your library.", None, "W"),
]


@pytest.mark.parametrize("cage", [False, True])
def test_cage_stops_a_manifest_from_the_library(cards, cage):
    s = build(cards, ["Soul Summons", "Grafdigger's Cage"], [])
    if cage:
        put(s, "Grafdigger's Cage")
    spell = to_hand(s, "Soul Summons")
    top = library(s, "p1")[0]
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    for _ in range(4):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    face_down = [c for c in s.state.cards.values() if c.face_down and c.zone == "p1:battlefield"]
    if cage:  # 701.40f: the face-down creature can't enter, so the card stays on top of the library
        assert not face_down and library(s, "p1")[0] == top and s.state.cards[top].zone == "p1:library"
    else:
        assert len(face_down) == 1
    check(s)
