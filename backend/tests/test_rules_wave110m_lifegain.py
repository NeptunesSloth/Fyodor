"""Wave 110M: "Whenever a white instant or sorcery spell causes you to gain life, ... deals 3 damage to target creature or player." (Firesong and Sunspeaker).
A spell causes a gain when its own resolution gains the life or when its lifelink damage does (702.15b, 120.3f); a copy of a spell is a spell too (707.10).
"Creature or player" is a creature or a player: not a planeswalker or a battle (115.1). Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110m_kit import *

FIRESONG = "Firesong and Sunspeaker"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([FIRESONG])


def table(cards, mine, theirs=("Elite Vanguard",)):
    s = build(cards, [FIRESONG, *mine], list(theirs), forests=20)
    put(s, FIRESONG)
    put(s, "Elite Vanguard", "p2")
    return s


def test_a_white_instant_that_gains_you_life_deals_three(cards):
    s = table(cards, ["Revitalize"])
    cast(s, "Revitalize", extra="")
    fund(s, "")
    answer(s, "p2")
    assert life(s) == 43 and life(s, "p2") == 37
    check(s)


def test_creature_or_player_cannot_target_a_planeswalker_but_can_target_a_creature(cards):
    s = table(cards, ["Revitalize"])
    vanguard = card_named(s, "Elite Vanguard", "p2")
    cast(s, "Revitalize")
    d = next(iter([s.state.rules.decision]))
    assert d is not None and vanguard.id in [o.id for o in d.options] and "p2" in [o.id for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[vanguard.id])
    answer(s)
    assert zone_of(s, "Elite Vanguard", "p2") == "p2:graveyard"  # (3 damage kills the 2/1)
    check(s)


def test_a_gain_that_goes_to_another_player_is_not_yours(cards):
    s = table(cards, ["Swords to Plowshares"])
    cast(s, "Swords to Plowshares", [card_named(s, "Elite Vanguard", "p2").id])
    answer(s)
    assert life(s, "p2") == 42 and life(s) == 40  # (its controller gained the life: no trigger)
    check(s)


def test_swords_on_your_own_creature_gains_you_life_from_a_white_spell(cards):
    s = table(cards, ["Swords to Plowshares", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    cast(s, "Swords to Plowshares", [bears.id])
    answer(s, "p2")
    assert life(s) == 42 and life(s, "p2") == 37
    check(s)


def test_a_red_spell_gains_life_by_lifelink_but_is_not_white(cards):
    s = table(cards, ["Lightning Bolt"])
    cast(s, "Lightning Bolt", ["p2"])
    answer(s)
    assert life(s) == 43 and life(s, "p2") == 37  # (the lifelink gain is caused by a red spell: no trigger)
    check(s)


def hit_p2(s):
    """Resolve everything, aiming every trigger at Bob and ordering the rest as offered."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if "p2" in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def test_a_red_and_white_spell_causes_both_its_own_gain_and_its_lifelink_gain(cards):
    s = table(cards, ["Lightning Helix"])
    cast(s, "Lightning Helix", ["p2"])
    hit_p2(s)
    assert life(s) == 46 and life(s, "p2") == 31  # (the lifelink gain and the spell's own gain: two triggers, 3 damage each, after the Helix's 3)
    check(s)
