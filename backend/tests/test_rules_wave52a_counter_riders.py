"""Wave 52A: counterspell riders that put the countered card to use (CR 2026-09-25), real Oracle text (tests/fixtures/wave52a_cards.json, from data/cards.sqlite). Every
scenario checks the replay and a save and a load.

* 608.2c / 701.6a / 702.62b: Delay - "Counter target spell. If the spell is countered this way, exile it with three time counters on it instead of putting it into its
  owner's graveyard. If it doesn't have suspend, it gains suspend." The card is exiled instead, suspended with three time counters, and its owner casts it for free when the
  last counter comes off.
* 608.2g: Transcendent Dragon - "When this creature enters, if you cast it, counter target spell. If that spell is countered this way, exile it instead of putting it into its
  owner's graveyard, then you may cast it without paying its mana cost." A spell that can't be countered stays on the stack: there is no card to cast.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_suspend import until
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, life, mana, reloaded, to_hand, zone_of
from tests.wave52a_kit import open_repo

DELAY, DRAGON = "Delay", "Transcendent Dragon"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [DELAY, DRAGON])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def counters(s, name):
    return {k: v for k, v in s.state.cards[card_named(s, name).id].counters.items() if v}


# -- Delay ---------------------------------------------------------------------------------------------------------------------------------
def delayed(cards):
    s = build(cards, [DELAY, "Lightning Bolt"])
    bolt, delay = to_hand(s, "Lightning Bolt"), to_hand(s, DELAY)
    mana(s, "p1", R=1, U=1, C=1)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=delay.id, targets=[bolt.id])
    settle(s)
    return s, bolt


def test_delay_exiles_the_countered_spell_with_three_time_counters_and_suspends_it(cards):
    s, bolt = delayed(cards)
    assert zone_of(s, "Lightning Bolt") == "p1:exile" and zone_of(s, DELAY) == "p1:graveyard"
    assert counters(s, "Lightning Bolt") == {"time": 3}
    assert bolt.id in s.state.rules.suspended  # it has suspend now (702.62b), whether or not it printed it
    assert life(s, "p2") == 40
    check(s)


def test_delay_the_suspended_spell_is_cast_for_free_when_the_last_counter_comes_off(cards):
    s, bolt = delayed(cards)
    s = reloaded(s)
    until(s, lambda s: s.state.rules.decision is not None and (s.state.rules.decision.resume or {}).get("step") == "suspend_cast", limit=6000)
    assert counters(s, "Lightning Bolt") == {}  # its owner's third upkeep took the last counter
    d = s.state.rules.decision
    assert d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision  # the target of the spell cast now
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    assert zone_of(s, "Lightning Bolt") == "p1:graveyard" and life(s, "p2") == 37
    check(s)


# -- Transcendent Dragon -----------------------------------------------------------------------------------------------------------------
def dragon(cards, spell, target=None):
    s = build(cards, [DRAGON, spell])
    cast_first, flash = to_hand(s, spell), to_hand(s, DRAGON)
    mana(s, "p1", R=1, G=2, U=2, C=4)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=cast_first.id, **({"targets": [target]} if target else {}))
    act(s, "p1", type="cast_spell", card_id=flash.id)
    for _ in range(10):  # the Dragon resolves; its enters trigger asks for its target (the first spell is the only one) and resolves
        d = s.state.rules.decision
        if d is not None and "without paying" in d.prompt or not s.state.zones.get("stack"):
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s


def test_transcendent_dragon_counters_exiles_and_casts_the_spell_for_free(cards):
    s = dragon(cards, "Lightning Bolt", "p2")
    assert zone_of(s, "Lightning Bolt") == "p1:exile"
    d = s.state.rules.decision
    assert d is not None and [s.state.cards[o.id].name for o in d.options if o.id in s.state.cards] == ["Lightning Bolt"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision  # the target of the spell cast now
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    assert life(s, "p2") == 37 and zone_of(s, "Lightning Bolt") == "p1:graveyard"  # cast without paying its mana cost
    check(s)


def test_transcendent_dragon_the_cast_is_optional(cards):
    s = dragon(cards, "Lightning Bolt", "p2")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert zone_of(s, "Lightning Bolt") == "p1:exile" and life(s, "p2") == 40
    check(s)


def test_transcendent_dragon_a_spell_that_cant_be_countered_is_not_cast_again(cards):
    s = dragon(cards, "Prowling Serpopard")
    assert s.state.rules.decision is None  # nothing was countered: nothing exiled, nothing to cast
    settle(s)
    assert zone_of(s, "Prowling Serpopard") == "p1:battlefield" and zone_of(s, DRAGON) == "p1:battlefield"
    check(s)


