"""Wave 24D: "you may search your library" under Mindlock Orb (614.17b: a player can't choose to do what can't happen, so the
optional search is skipped whole and its "then shuffle" with it, unlike a mandatory tutor's shuffle); and Grafdigger's Cage vs manifest."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

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
