"""Wave 110F session 16, on real Oracle text. Every scenario checks the replay and a save and a load.

* 702.26a-c, 701.52a: Ferris Wheel: "Choose target creature that hasn't been phased out with this Attraction. That creature phases out until you roll a 3 or less while rolling to visit
  your Attractions." (it phases in on that roll, only the roller's, and that Attraction can't choose it again).
* 702.159a, 611.2a, 706.2: Drop Tower: "Visit — Target creature gains flying until end of turn, or until any player rolls a 1, whichever comes first."
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real, rolls
from tests.test_rules_wave100k_instead import keywords
from tests.test_rules_wave100l_attractions import EXTRA, card_db, game, settle  # noqa: F401  (fixture DB with EXTRA)
from tests.wave9c_kit import card_named, check, mana, put, to_hand

EXTRA.append(card("Drop Tower", set_code="unf", number="209a", mana_cost="", cmc=0.0, type_line="Artifact — Attraction",
                  oracle_text="Visit — Target creature gains flying until end of turn, or until any player rolls a 1, whichever comes first.",
                  colors=[], color_identity=[], keywords=[]))
EXTRA.append(card("Ferris Wheel", set_code="unf", number="210", mana_cost="", cmc=0.0, type_line="Artifact — Attraction",
                  oracle_text="Visit — Choose target creature that hasn't been phased out with this Attraction. That creature phases out until you roll a 3 or less while rolling to visit your Attractions.",
                  colors=[], color_identity=[], keywords=[]))
EXTRA.append(real("Test Roller 110F", "{1}", 1, "Sorcery", "Roll a six-sided die.", None, ""))


@pytest.mark.parametrize("name", ["Drop Tower", "Ferris Wheel"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def to_main(s, turn, pick=None, limit=400):
    """Like the Attractions test's, but a decision offering ``pick`` takes it."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.number == turn and s.state.turn.phase == "main1" and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick] if pick in ids else ids[: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached that main phase")


def _tower(cards, monkeypatch, *dice):
    rolls(monkeypatch, *dice)
    s = game(cards, ["Grizzly Bears", "Test Roller 110F"], ["Drop Tower"])  # 209a: 2, 3 and 6 lit
    bears = put(s, "Grizzly Bears")
    put(s, "Drop Tower")
    to_main(s, 3)
    return s, bears


def test_the_visit_grants_flying(cards, monkeypatch):
    s, bears = _tower(cards, monkeypatch, 3)
    assert "Flying" in keywords(s, bears) or "flying" in keywords(s, bears)
    check(s)


@pytest.mark.parametrize(("die", "flies"), [(1, False), (2, True)])
def test_a_roll_of_1_ends_the_flying_any_other_roll_does_not(cards, monkeypatch, die, flies):
    s, bears = _tower(cards, monkeypatch, 3, die)
    to_hand(s, "Test Roller 110F")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Test Roller 110F").id)
    settle(s)
    assert ("flying" in {k.lower() for k in keywords(s, bears)}) is flies
    check(s)


def test_the_flying_ends_with_the_turn(cards, monkeypatch):
    s, bears = _tower(cards, monkeypatch, 3)
    to_main(s, 4)
    assert "flying" not in {k.lower() for k in keywords(s, bears)}
    check(s)


def _wheel(cards, monkeypatch, *dice):
    rolls(monkeypatch, *dice)
    s = game(cards, ["Grizzly Bears", "Llanowar Elves"], ["Ferris Wheel", "Information Booth"])  # 210: 4, 5, 6 lit; 218a: 2, 6
    bears, elf = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    put(s, "Ferris Wheel")
    put(s, "Information Booth")
    return s, bears, elf


def _zone(s, c):
    return s.state.cards[c.id].zone


def test_the_visit_phases_a_creature_out_until_a_low_roll_to_visit(cards, monkeypatch):
    s, bears, elf = _wheel(cards, monkeypatch, 5, 2)
    to_main(s, 3, pick=bears.id)
    assert _zone(s, bears) == "p1:phased" and _zone(s, elf) == "p1:battlefield"
    check(s)
    to_main(s, 5)  # (the roll of 2 is low: it phases in; Information Booth is visited)
    assert _zone(s, bears) == "p1:battlefield"
    check(s)


def test_a_high_roll_leaves_it_phased_out_and_the_wheel_cannot_choose_it_again(cards, monkeypatch):
    s, bears, elf = _wheel(cards, monkeypatch, 5, 6, 2, 5)
    to_main(s, 3, pick=bears.id)
    to_main(s, 5, pick=elf.id)  # (6: both Attractions visited; the Wheel's only legal target is the Elf: the Bears are phased out)
    assert _zone(s, bears) == "p1:phased" and _zone(s, elf) == "p1:phased"
    to_main(s, 7)  # (2: low, both phase in)
    assert _zone(s, bears) == "p1:battlefield" and _zone(s, elf) == "p1:battlefield"
    to_main(s, 9)  # (5: the Wheel is visited again but both creatures were phased out with it already: no target)
    assert _zone(s, bears) == "p1:battlefield" and _zone(s, elf) == "p1:battlefield"
    check(s)
