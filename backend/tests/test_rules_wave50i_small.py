"""Wave 50I: small mode wordings (CR 2026-09-25), real Oracle text (tests/fixtures/wave50i_cards.json, from data/cards.sqlite). Every scenario checks the replay
and a save and a load.

* 701.44a: "Target creature you control explores, then it explores again." (Over the Edge): the same creature explores twice, each reveal on its own.
* 115.7d / 700.2: a mode that is all "You may choose new targets for target spell." (Insidious Will) keeps every target unless the player chooses another.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave33b_modal import settle
from tests.test_rules_wave50i_modal_modes import cards_fixture, counters, until_decision
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand, zone_of

cards = pytest.fixture()(cards_fixture)


def test_over_the_edge_explores_twice(cards):
    s = build(cards, ["Over the Edge", "Grizzly Bears"], forests=30)
    put(s, "Grizzly Bears")
    to_hand(s, "Over the Edge")
    mana(s, G=2)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Over the Edge").id, modes=[1], targets=[card_named(s, "Grizzly Bears").id])
    settle(s)
    # (the top of the library is a Forest each time: two lands into the hand, no counter)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2 and counters(s, "Grizzly Bears") == 0
    check(s)
    check(reloaded(s))


def test_halo_charged_skaab_puts_an_instant_sorcery_or_battle_card_on_top(cards):
    """"…an instant, sorcery, or battle card from your graveyard on top of your library": a list of three card types (the Forest milled with the Bolt isn't offered)."""
    s = build(cards, ["Halo-Charged Skaab", "Lightning Bolt"], forests=30)
    to_hand(s, "Halo-Charged Skaab")
    mana(s, U=1, G=4)
    bolt = card_named(s, "Lightning Bolt")  # (the top of the library, with a Forest under it: both are milled)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Halo-Charged Skaab").id)
    d = until_decision(s)
    assert d is not None and d.player == "p1" and [o.card_id for o in d.options] == [bolt.id]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bolt.id])
    settle(s)
    assert s.state.zones["p1:library"][0] == bolt.id
    check(s)
    check(reloaded(s))


@pytest.mark.parametrize("change", [True, False])
def test_insidious_will_may_choose_new_targets(cards, change):
    s = build(cards, ["Lightning Bolt"], ["Insidious Will"], forests=30)
    bolt, will = to_hand(s, "Lightning Bolt"), to_hand(s, "Insidious Will", "p2")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, "p2", U=2, C=2)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=will.id, modes=[1], targets=[bolt.id])
    for _ in range(10):
        d = until_decision(s)
        if d is None:
            break
        ids = [o.id for o in d.options]
        want = ["p1"] if change and "p1" in ids else ["keep"] if "keep" in ids else ids[:1]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=want)
    settle(s)
    assert (life(s, "p1"), life(s, "p2")) == ((37, 40) if change else (40, 37))
    assert zone_of(s, "Lightning Bolt") == "p1:graveyard"
    check(s)
    check(reloaded(s))
