"""Wave 53B: a value chosen as the spell or ability resolves, used as the filter of the instructions after it (CR 608.2c-d, 205.2a, 105.1,
205.3m): "Choose a color. … discards all cards of that color", "Choose a card type, then reveal the top four cards … all cards of the chosen
type revealed this way", "Choose a permanent type. Return all cards of the chosen type from your graveyard". Real Oracle text
(tests/fixtures/wave53b_cards.json, from data/cards.sqlite); every scenario checks the replay and a save and a load.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import answer, on_top
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of
from tests.wave53b_kit import open_repo


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", ["Persecute", "Vigean Intuition", "Winding Way", "Creeping Renaissance", "Addle", "Crosis, the Purger", "Searing Rays"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def option_ids(s):
    return [o.id for o in s.state.rules.decision.options]


def cast(s, name, *, targets=None, **pool):
    c = to_hand(s, name)
    mana(s, "p1", **pool)
    act(s, "p1", type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def test_persecute_discards_every_card_of_the_color_chosen_as_it_resolves(cards):
    s = build(cards, ["Persecute"], ["Probe Bolt", "Probe Goblin", "Probe Elf", "Probe Relic"])
    for n in ("Probe Bolt", "Probe Goblin", "Probe Elf", "Probe Relic"):
        to_hand(s, n, "p2")
    cast(s, "Persecute", targets=["p2"], B=2, C=2)
    assert s.state.rules.decision.player == "p1" and option_ids(s) == ["White", "Blue", "Black", "Red", "Green"]
    answer(s, "Red")
    assert [zone_of(s, n, "p2") for n in ("Probe Bolt", "Probe Goblin", "Probe Elf", "Probe Relic")] == ["p2:graveyard", "p2:graveyard", "p2:hand", "p2:hand"]  # (colorless is no color: 105.2c)
    check(s)


def test_vigean_intuition_takes_the_cards_of_the_chosen_type_and_mills_the_rest(cards):
    s = build(cards, ["Vigean Intuition", "Probe Land", "Probe Elf", "Probe Relic", "Probe Rock"])
    for n in ("Probe Rock", "Probe Relic", "Probe Elf", "Probe Land"):
        on_top(s, n, "p1")
    cast(s, "Vigean Intuition", G=1, U=1, C=3)
    assert len(option_ids(s)) == 9 and "Land" in option_ids(s)
    answer(s, "Artifact")  # Probe Rock is an artifact creature: an artifact
    assert (zone_of(s, "Probe Relic"), zone_of(s, "Probe Rock")) == ("p1:hand", "p1:hand")
    assert (zone_of(s, "Probe Land"), zone_of(s, "Probe Elf")) == ("p1:graveyard", "p1:graveyard")
    check(s)


def test_winding_way_offers_only_the_two_types_it_lists(cards):
    s = build(cards, ["Winding Way", "Probe Land", "Probe Elf", "Probe Relic", "Probe Rock"])
    for n in ("Probe Rock", "Probe Relic", "Probe Elf", "Probe Land"):
        on_top(s, n, "p1")
    cast(s, "Winding Way", G=1, C=1)
    assert option_ids(s) == ["Creature", "Land"]
    answer(s, "Creature")
    assert sorted(zone_of(s, n) for n in ("Probe Elf", "Probe Rock")) == ["p1:hand", "p1:hand"]
    assert (zone_of(s, "Probe Land"), zone_of(s, "Probe Relic")) == ("p1:graveyard", "p1:graveyard")
    check(s)


def test_creeping_renaissance_offers_the_six_permanent_types(cards):
    s = build(cards, ["Creeping Renaissance", "Probe Relic", "Probe Elf", "Probe Bolt"])
    for n in ("Probe Relic", "Probe Elf", "Probe Bolt"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Creeping Renaissance", G=2, C=3)
    assert option_ids(s) == ["Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"]
    answer(s, "Artifact")
    assert (zone_of(s, "Probe Relic"), zone_of(s, "Probe Elf"), zone_of(s, "Probe Bolt")) == ("p1:hand", "p1:graveyard", "p1:graveyard")
    check(s)


def test_addle_chooses_one_card_of_the_color_named(cards):
    s = build(cards, ["Addle"], ["Probe Bolt", "Probe Goblin", "Probe Elf"])
    for n in ("Probe Bolt", "Probe Goblin", "Probe Elf"):
        to_hand(s, n, "p2")
    cast(s, "Addle", targets=["p2"], B=1, C=1)
    answer(s, "Red", card_named(s, "Probe Goblin", "p2").id)
    assert [zone_of(s, n, "p2") for n in ("Probe Bolt", "Probe Goblin", "Probe Elf")] == ["p2:hand", "p2:graveyard", "p2:hand"]
    check(s)


def test_searing_rays_counts_each_players_own_creatures_of_the_color(cards):
    s = build(cards, ["Searing Rays", "Probe Goblin", "Probe Elf"], ["Probe Goblin", "Probe Goblin"])
    put(s, "Probe Goblin")
    put(s, "Probe Elf")
    for g in [c for c in s.state.cards.values() if c.name == "Probe Goblin" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[g.id], to={"player": "p2", "zone": "battlefield"})
    before = (life(s, "p1"), life(s, "p2"))
    cast(s, "Searing Rays", R=1, C=2)
    answer(s, "Red")
    assert (before[0] - life(s, "p1"), before[1] - life(s, "p2")) == (1, 2)
    check(s)


def test_crosis_discards_the_chosen_color_after_the_payment(cards):
    s = build(cards, ["Crosis, the Purger", "Probe Swamp", "Probe Swamp", "Probe Swamp"], ["Probe Bolt", "Probe Goblin", "Probe Elf"])
    for n in ("Probe Bolt", "Probe Goblin", "Probe Elf"):
        to_hand(s, n, "p2")
    crosis = put(s, "Crosis, the Purger")
    s.state.rules.controlled_since[crosis.id].turn = 0
    for swamp in [c for c in s.state.cards.values() if c.name == "Probe Swamp" and c.owner == "p1"]:
        act(s, "p1", type="move", card_ids=[swamp.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="pass_priority")  # → combat: Alice declares attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": crosis.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one" and "Red" in option_ids(s))
    answer(s, "Red")
    assert [zone_of(s, n, "p2") for n in ("Probe Bolt", "Probe Goblin", "Probe Elf")] == ["p2:graveyard", "p2:graveyard", "p2:hand"]
    check(s)
