"""Wave 110C: optional graveyard replacements (614.1a, 616.1, 701.9).

* Library of Leng: an effect's discard may put the card on top of its owner's library instead; declining discards as usual.
* Nephalia Academy: the same, only for a spell or ability an opponent controls (its owner's own Mind Rot is not replaced).
* Pulmonic Sliver: every Sliver may go on top of its owner's library instead of a graveyard.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import build, cast, mana, put, real, to_hand

LENG = ("You have no maximum hand size.\nIf an effect causes you to discard a card, discard it, but you may put it on top of your library instead of into your "
        "graveyard.")
ACADEMY = ("If a spell or ability an opponent controls causes you to discard a card, you may reveal that card and put it on top of your library instead of putting it "
           "anywhere else.\n{T}: Add {C}.")
SLIVER = "All Sliver creatures have flying.\nAll Slivers have \"If this permanent would be put into a graveyard, you may put it on top of its owner's library instead.\""
EXTRA = [real("Library of Leng", "{1}", 1, "Artifact", LENG, None, ""),
         real("Nephalia Academy", "", 0, "Land", ACADEMY, None, ""),
         real("Pulmonic Sliver", "{3}{W}{W}", 5, "Creature — Sliver", SLIVER, ("3", "3"), "W"),
         real("Mind Rot", "{2}{B}", 3, "Sorcery", "Target player discards two cards.", None, "B"),
         real("Doom Blade", "{1}{B}", 2, "Instant", "Destroy target nonblack creature.", None, "B")]


@pytest.fixture()
def card_db(settings):
    from tests.wave110c_kit import make_db

    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Library of Leng", "Nephalia Academy", "Pulmonic Sliver"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _settle(s, take):
    """Resolve everything; each 616.1 question picks the option labelled with 'library' when ``take`` else 'Decline'."""
    asked = 0
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None:
            if d.kind == "choose_cards":
                ids = [o.id for o in d.options][: d.max_choices]
            else:
                asked += 1
                ids = [next(o.id for o in d.options if ("library" in o.label) == take or (not take and "Decline" in o.label))]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


@pytest.mark.parametrize("take", [True, False])
def test_library_of_leng_may_put_a_discarded_card_on_top(cards, take):
    s = build(cards, ["Library of Leng", "Mind Rot", "Grizzly Bears", "Forest", "Forest"])
    put(s, "Library of Leng")
    for n in ("Grizzly Bears", "Forest"):
        to_hand(s, n)
    mana(s, B=1, C=2)
    cast(s, "Mind Rot", ["p1"])
    asked = _settle(s, take)
    top = s.state.zones["p1:library"]
    gy = [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]]
    assert asked == 2 and gy.count("Mind Rot") == 1
    assert (len(gy) == 1 and len([c for c in top if s.state.cards[c].name in ("Grizzly Bears", "Forest")]) >= 2) if take else sorted(gy) == ["Forest", "Grizzly Bears", "Mind Rot"]


def test_nephalia_academy_only_for_an_opponents_effect(cards):
    s = build(cards, ["Nephalia Academy", "Mind Rot", "Grizzly Bears", "Forest"], ["Mind Rot", "Grizzly Bears", "Forest"])
    put(s, "Nephalia Academy")
    for n in ("Grizzly Bears", "Forest"):
        to_hand(s, n)
    mana(s, B=1, C=2)
    cast(s, "Mind Rot", ["p1"])  # its own owner's spell: no replacement, no question
    assert _settle(s, True) == 0
    assert sorted(s.state.cards[c].name for c in s.state.zones["p1:graveyard"]) == ["Forest", "Grizzly Bears", "Mind Rot"]


@pytest.mark.parametrize("take", [True, False])
def test_nephalia_academy_opponent_spell(cards, take):
    s = build(cards, ["Mind Rot", "Forest"], ["Nephalia Academy", "Grizzly Bears", "Forest"])
    put(s, "Nephalia Academy", "p2")
    for n in ("Grizzly Bears", "Forest"):
        to_hand(s, n, "p2")
    mana(s, B=1, C=2)
    cast(s, "Mind Rot", ["p2"])
    assert _settle(s, take) == 2
    assert len(s.state.zones["p2:graveyard"]) == (0 if take else 2)
    assert len(s.state.zones["p2:hand"]) == 0


@pytest.mark.parametrize("take", [True, False])
def test_pulmonic_sliver_destroyed_may_go_on_top(cards, take):
    s = build(cards, ["Pulmonic Sliver", "Doom Blade"])
    sl = put(s, "Pulmonic Sliver")
    mana(s, B=1, C=1)
    cast(s, "Doom Blade", [sl.id])
    assert _settle(s, take) == 1
    assert s.state.cards[sl.id].zone == ("p1:library" if take else "p1:graveyard")
    assert (s.state.zones["p1:library"][0] == sl.id) if take else True
