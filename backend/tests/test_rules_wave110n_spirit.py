"""Wave 110N: Spirit-Sister's Call (603.5/608.2c the sacrifice shares a card type with the chosen card; the returned card is exiled instead of leaving)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

CALL, RELIC, GOLEM = "Spirit-Sister's Call", "Cheap Relic", "Relic Golem"
EXTRA = [
    real(CALL, "{2}{W}", 3, "Enchantment",
         "At the beginning of your end step, choose target permanent card in your graveyard. You may sacrifice a permanent that shares a card type with the chosen card. "
         "If you do, return the chosen card from your graveyard to the battlefield and it gains \"If this permanent would leave the battlefield, exile it instead of "
         "putting it anywhere else.\"", None, "W"),
    real(RELIC, "{2}", 2, "Artifact", "", None),
    real(GOLEM, "{4}", 4, "Artifact Creature — Golem", "", ("3", "3")),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([CALL])


def pick(s, *ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def to_decision(s):
    """Pass priority until a decision opens (or the stack is empty)."""
    for _ in range(20):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")


def to_sacrifice(s, target=None):
    """Choose the trigger's target (the first graveyard card unless ``target``), then pass priority until the sacrifice question."""
    d = to_decision(s)
    assert d is not None and "target" in d.prompt
    pick(s, target or d.options[0].id)
    return to_decision(s)


def setup(cards, grave, field, extra=()):
    s = build(cards, [CALL, *grave, *field, *extra])
    put(s, CALL)
    for n in field:
        put(s, n)
    for n in grave:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    stops(s)
    to_phase(s, "end")
    return s


def test_sacrificing_a_creature_returns_a_creature_card_exiled_if_it_leaves(cards):
    s = setup(cards, ["Grizzly Bears"], ["Llanowar Elves"], ["Murder"])
    elves = card_named(s, "Llanowar Elves")
    assert to_sacrifice(s) is not None
    pick(s, elves.id)
    answer(s)
    assert zone_of(s, "Llanowar Elves") == "p1:graveyard" and zone_of(s, "Grizzly Bears") == "p1:battlefield"
    mana(s, "p1", B=3)
    cast(s, "Murder", [card_named(s, "Grizzly Bears").id], pay=False)
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:exile"
    check(s)


def test_the_sacrifice_may_be_declined(cards):
    s = setup(cards, ["Grizzly Bears"], ["Llanowar Elves"])
    to_sacrifice(s)
    pick(s)
    answer(s)
    assert zone_of(s, "Llanowar Elves") == "p1:battlefield" and zone_of(s, "Grizzly Bears") == "p1:graveyard"
    check(s)


def test_without_a_permanent_sharing_a_type_nothing_can_be_sacrificed(cards):
    s = setup(cards, [RELIC], ["Llanowar Elves"])  # an artifact card to return, no artifact to sacrifice
    assert to_sacrifice(s) is None
    assert zone_of(s, RELIC) == "p1:graveyard" and zone_of(s, "Llanowar Elves") == "p1:battlefield"
    check(s)


def test_an_artifact_creature_card_can_be_paid_for_with_either_type(cards):
    s = setup(cards, [GOLEM], [RELIC, "Llanowar Elves"])
    d = to_sacrifice(s)
    assert {s.state.cards[o.card_id].name for o in d.options} == {RELIC, "Llanowar Elves"}
    pick(s, next(o.id for o in d.options if s.state.cards[o.card_id].name == RELIC))
    answer(s)
    assert zone_of(s, GOLEM) == "p1:battlefield" and zone_of(s, RELIC) == "p1:graveyard"
    check(s)
