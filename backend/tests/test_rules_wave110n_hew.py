"""Wave 110N: Hew the Entwood (701.21 sacrifice, 701.20 reveal; nonland artifacts enter, then the chosen lands tapped, the rest to the bottom)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

HEW, RELIC, GOLEM, BOLT = "Hew the Entwood", "Cheap Relic", "Relic Golem", "Plain Bolt"
EXTRA = [
    real(HEW, "{2}{R}{G}", 4, "Sorcery",
         "Sacrifice any number of lands. Reveal the top X cards of your library, where X is the number of lands sacrificed this way. Choose any number of artifact and/or "
         "land cards revealed this way. Put all nonland cards chosen this way onto the battlefield, then put all land cards chosen this way onto the battlefield tapped, "
         "then put the rest on the bottom of your library in a random order.", None, "RG"),
    real(RELIC, "{2}", 2, "Artifact", "", None),
    real(GOLEM, "{4}", 4, "Artifact Creature — Golem", "", ("3", "3")),
    real(BOLT, "{R}", 1, "Instant", "Plain Bolt deals 1 damage to any target.", None, "R"),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([HEW])


def pick(s, *ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def on_top(s, *names):
    """These cards, in order, on top of Alice's library."""
    for n in reversed(names):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "library"}, position="top")


def setup(cards, lands=3):
    s = build(cards, [HEW, RELIC, GOLEM, BOLT, "Mountain"], forests=9)
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:lands]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    to_hand(s, HEW)
    on_top(s, RELIC, "Mountain", BOLT, GOLEM)
    return s, forests


def test_artifacts_enter_untapped_lands_tapped_and_the_rest_go_to_the_bottom(cards):
    s, forests = setup(cards)
    mana(s, "p1", R=1, G=1, C=2)
    cast(s, HEW, pay=False)
    d = s.state.rules.decision
    assert d is not None
    pick(s, *[f.id for f in forests])  # sacrifice three lands: reveal Cheap Relic, Mountain, Plain Bolt
    assert all(s.state.cards[f.id].zone == "p1:graveyard" for f in forests)
    d = s.state.rules.decision
    assert {s.state.cards[o.card_id].name for o in d.options} == {RELIC}  # (the Golem is the fourth card: not revealed)
    pick(s, d.options[0].id)
    d = s.state.rules.decision
    assert {s.state.cards[o.card_id].name for o in d.options} == {"Mountain"}
    pick(s, d.options[0].id)
    answer(s)
    assert zone_of(s, RELIC) == "p1:battlefield" and not s.state.cards[card_named(s, RELIC).id].tapped
    assert zone_of(s, "Mountain") == "p1:battlefield" and s.state.cards[card_named(s, "Mountain").id].tapped
    lib = s.state.zones["p1:library"]
    assert s.state.cards[lib[-1]].name == BOLT and card_named(s, GOLEM).id == lib[0]  # (the Bolt went to the bottom, the Golem is the top card again)
    check(s)


def test_declined_cards_go_to_the_bottom_and_zero_lands_reveal_nothing(cards):
    s, forests = setup(cards)
    mana(s, "p1", R=1, G=1, C=2)
    cast(s, HEW, pay=False)
    pick(s, forests[0].id)  # reveal the Cheap Relic only
    pick(s)  # choose none of the artifacts
    answer(s)
    assert zone_of(s, RELIC) == "p1:library" and s.state.cards[s.state.zones["p1:library"][-1]].name == RELIC
    check(s)


def test_sacrificing_no_land_reveals_no_card(cards):
    s, forests = setup(cards)
    mana(s, "p1", R=1, G=1, C=2)
    cast(s, HEW, pay=False)
    pick(s)
    answer(s)
    assert zone_of(s, RELIC) == "p1:library" and all(s.state.cards[f.id].zone == "p1:battlefield" for f in forests)
    check(s)
