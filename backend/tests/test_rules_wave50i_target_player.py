"""Wave 50I: "Target player returns a … card from their graveyard to their hand." in a mode (CR 2026-09-25), real Oracle text
(tests/fixtures/wave50i_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 608.2d / 700.2c: the named player chooses the card from their own graveyard (Obscura Confluence, Donnie & April); with nothing to return nothing happens.
* 700.2b / 603.3c: "choose one or both. Each mode must target a different player" (Donnie & April); an "artifact, instant, or sorcery card" list.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave33b_modal import settle
from tests.test_rules_wave50i_modal_modes import cards_fixture, until_decision
from tests.wave9c_kit import build, card_named, check, mana, reloaded, to_hand, zone_of

cards = pytest.fixture()(cards_fixture)


def grave(s, name, pid="p2"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def answer_all(s, deciders):
    """Answer decisions: the modes (both), a player target (first p1, then p2), a card (the first offered); ``deciders`` collects who was asked for a card."""
    for _ in range(15):
        d = until_decision(s)
        if d is None:
            return
        ids = [o.id for o in d.options]
        if d.kind == "choose_cards" and "0:0" in ids:
            pick = ["0:0", "1:0"]
        elif d.kind == "choose_one" and "p1" in ids:
            pick = ["p1"]
        elif d.kind == "choose_one" and "p2" in ids:
            pick = ["p2"]
        else:
            deciders.append(d.player)
            pick = ids[:1]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    raise AssertionError("never settled")


def test_donnie_and_april_one_player_draws_the_other_returns_an_instant(cards):
    s = build(cards, ["Donnie & April, Adorkable Duo"], ["Lightning Bolt", "Grizzly Bears"], forests=30)
    bolt, bears = grave(s, "Lightning Bolt"), grave(s, "Grizzly Bears")
    to_hand(s, "Donnie & April, Adorkable Duo")
    mana(s, U=1, G=4)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Donnie & April, Adorkable Duo").id)
    deciders: list[str] = []
    answer_all(s, deciders)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 2  # (Alice drew two)
    assert s.state.cards[bolt.id].zone == "p2:hand" and s.state.cards[bears.id].zone == "p2:graveyard"  # (an instant; not the creature)
    check(s)
    check(reloaded(s))


def test_donnie_and_april_returns_nothing_without_an_artifact_instant_or_sorcery(cards):
    s = build(cards, ["Donnie & April, Adorkable Duo"], ["Grizzly Bears"], forests=30)
    bears = grave(s, "Grizzly Bears")
    to_hand(s, "Donnie & April, Adorkable Duo")
    mana(s, U=1, G=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Donnie & April, Adorkable Duo").id)
    answer_all(s, [])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)
    check(reloaded(s))


def test_obscura_confluence_the_target_player_chooses_which_creature_card_returns(cards):
    s = build(cards, ["Obscura Confluence"], ["Grizzly Bears", "Young Wolf"], forests=30)
    bears, wolf = grave(s, "Grizzly Bears"), grave(s, "Young Wolf")
    to_hand(s, "Obscura Confluence")
    mana(s, W=1, U=1, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Obscura Confluence").id, modes=[2, 2, 2], targets=["p2", "p2", "p2"])
    deciders: list[str] = []
    answer_all(s, deciders)
    settle(s)
    assert deciders[0] == "p2"  # (Bob chooses from Bob's graveyard)
    assert zone_of(s, "Grizzly Bears", "p2") == zone_of(s, "Young Wolf", "p2") == "p2:hand"  # (the third time there is nothing left to return)
    assert {bears.id, wolf.id} <= set(s.state.zones["p2:hand"])
    check(s)
    check(reloaded(s))
