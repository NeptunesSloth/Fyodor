"""Wave 51H: offering (CR 702.48, 118.7, 601.2b, 601.2f-h, 2026-09-25), real Oracle text (tests/fixtures/wave51h_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* 702.48a-b: "[Quality] offering" is an optional additional cost, "sacrifice a [quality] permanent" you control, chosen as the spell is cast and paid with its cost; chosen, the
  spell may be cast any time you could cast an instant; not chosen, it is cast at sorcery speed for its whole cost.
* 702.48c, 118.7: the sacrificed permanent's mana cost takes that much off the total: generic off generic only, each colored symbol off that color, an excess colored symbol off
  generic mana (ruling 2022-10-14), never below {0}; a hybrid symbol is the half the player prefers (118.7e).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave51h_kit import open_repo

MOON, AKKI, KITSUNE, HELLKITE = "Patron of the Moon", "Patron of the Akki", "Patron of the Kitsune", "Blast-Furnace Hellkite"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [MOON, AKKI, KITSUNE, HELLKITE])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def spell_on_stack(s, **spare):
    """Alice casts a creature spell, so a sorcery couldn't be cast now (307.1); the ``spare`` mana stays in her pool, and she holds priority."""
    act(s, "p1", type="set_prefs", hold_priority=True)
    piker = to_hand(s, "Goblin Piker")  # {1}{R}
    mana(s, **{k: v + (1 if k in "RC" else 0) for k, v in {"R": 0, "C": 0, **spare}.items()})
    act(s, "p1", type="cast_spell", card_id=piker.id)
    assert s.state.zones["stack"]


def offer(s, name):
    return [card_named(s, name).id + ":offering"]


def cast_with_offering(s, name, pick=None):
    """Cast it sacrificing one; a question about which permanent to sacrifice is answered with the card named ``pick`` (the first option otherwise)."""
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id, optional_costs=offer(s, name))
    if (d := s.state.rules.decision) is not None:
        ids = [o.id for o in d.options if pick is None or s.state.cards[o.id].name == pick]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[:1])


def sacrifice_for(cards, patron, sacrificed, **pool):
    """Alice with ``sacrificed`` on the battlefield, ``patron`` in hand, a spell on the stack and exactly ``pool`` spare mana."""
    s = build(cards, [patron, *sacrificed, "Goblin Piker"])
    for name in sacrificed:
        put(s, name)
    to_hand(s, patron)
    spell_on_stack(s, **pool)
    return s


def test_instant_speed_offering_takes_the_sacrificed_colored_mana_off(cards):
    s = sacrifice_for(cards, MOON, ["Soratami Savant"], C=3)  # {5}{U}{U} less {2}{U}{U} is {3}: no blue needed (generic off generic alone would leave {1}{U}{U})
    assert card_named(s, MOON).id in s.view("p1")["rules"]["hints"]["castable"]
    assert s.view("p1")["rules"]["hints"]["optional_costs"][card_named(s, MOON).id][0]["label"] == "Moonfolk offering: sacrifice a Moonfolk"
    cast_with_offering(s, MOON)
    assert zone_of(s, "Soratami Savant") == "p1:graveyard" and zone_of(s, MOON) == "stack"
    assert s.state.players["p1"].mana == {}
    check(s)


def test_not_chosen_it_is_a_sorcery_speed_cast_for_the_whole_cost(cards):
    s = sacrifice_for(cards, MOON, ["Soratami Savant"], C=3)
    patron = card_named(s, MOON)
    with pytest.raises(ActionError, match="offering"):
        act(s, "p1", type="cast_spell", card_id=patron.id)  # no offering chosen, a spell is on the stack
    assert zone_of(s, MOON) == "p1:hand" and zone_of(s, "Soratami Savant") == "p1:battlefield"
    settle(s)
    mana(s, U=2, C=5)
    act(s, "p1", type="cast_spell", card_id=patron.id)  # main phase, empty stack: the full {5}{U}{U}
    assert zone_of(s, MOON) == "stack" and zone_of(s, "Soratami Savant") == "p1:battlefield" and s.state.players["p1"].mana == {"C": 3}
    check(s)


def test_too_little_mana_for_the_reduced_cost_changes_nothing(cards):
    s = sacrifice_for(cards, MOON, ["Soratami Savant"], C=2)  # {3} is needed
    with pytest.raises(ActionError):
        cast_with_offering(s, MOON)
    assert zone_of(s, "Soratami Savant") == "p1:battlefield" and zone_of(s, MOON) == "p1:hand"
    check(s)


def test_a_colored_symbol_the_spell_lacks_takes_generic_mana_off(cards):
    # Festering Goblin's {B}: Patron of the Akki has no black mana in {4}{R}{R}, so it is {1} off generic (118.7b, ruling 2022-10-14): {3}{R}{R}
    s = sacrifice_for(cards, AKKI, ["Festering Goblin"], R=1, C=4)
    with pytest.raises(ActionError):
        cast_with_offering(s, AKKI)  # {3}{R}{R} needs two red
    assert zone_of(s, "Festering Goblin") == "p1:battlefield"
    mana(s, R=1)
    cast_with_offering(s, AKKI)
    assert zone_of(s, AKKI) == "stack" and zone_of(s, "Festering Goblin") == "p1:graveyard" and s.state.players["p1"].mana == {"C": 1}
    check(s)


def test_a_hybrid_symbol_is_the_half_the_player_prefers(cards):
    # Boggart Ram-Gang {R/G}{R/G}{R/G}: red and red (off the two {R}), then {1} off generic (118.7e): {4}{R}{R} becomes {3}
    s = sacrifice_for(cards, AKKI, ["Boggart Ram-Gang"], C=2)
    with pytest.raises(ActionError):
        cast_with_offering(s, AKKI)
    mana(s, C=1)
    cast_with_offering(s, AKKI)
    assert zone_of(s, "Boggart Ram-Gang") == "p1:graveyard" and s.state.players["p1"].mana == {}
    check(s)


def test_artifact_offering_takes_a_blue_symbol_off_generic(cards):
    s = sacrifice_for(cards, HELLKITE, ["Secret Door", "Soratami Savant"], R=2, C=6)  # {7}{R}{R} less {U}: {6}{R}{R}
    assert s.view("p1")["rules"]["hints"]["optional_costs"][card_named(s, HELLKITE).id][0]["label"] == "Artifact offering: sacrifice an Artifact"
    cast_with_offering(s, HELLKITE)  # only the artifact creature can be sacrificed: no question
    assert zone_of(s, "Secret Door") == "p1:graveyard" and zone_of(s, "Soratami Savant") == "p1:battlefield" and s.state.players["p1"].mana == {}
    check(s)


def test_the_sacrifice_is_chosen_among_the_permanents_that_qualify(cards):
    s = sacrifice_for(cards, AKKI, ["Mons's Goblin Raiders", "Boggart Ram-Gang"], C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, AKKI).id, optional_costs=offer(s, AKKI))
    d = s.state.rules.decision
    assert d is not None and {s.state.cards[o.id].name for o in d.options} == {"Mons's Goblin Raiders", "Boggart Ram-Gang"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if s.state.cards[o.id].name == "Boggart Ram-Gang"])
    assert zone_of(s, "Boggart Ram-Gang") == "p1:graveyard" and zone_of(s, "Mons's Goblin Raiders") == "p1:battlefield" and zone_of(s, AKKI) == "stack"
    check(s)


def test_nothing_to_sacrifice_no_offering_and_no_instant_speed(cards):
    s = build(cards, [KITSUNE, "Goblin Piker"], ["Flourishing Fox"])  # a Fox, but Bob's
    put(s, "Flourishing Fox", "p2")
    patron = to_hand(s, KITSUNE)
    spell_on_stack(s, W=4, C=2)
    hints = s.view("p1")["rules"]["hints"]
    assert patron.id not in hints.get("castable", []) and patron.id not in hints.get("optional_costs", {})
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=patron.id, optional_costs=offer(s, KITSUNE))
    check(s)


def test_a_fox_pays_for_the_kitsune(cards):
    s = sacrifice_for(cards, KITSUNE, ["Flourishing Fox"], W=2, C=4)  # {4}{W}{W} less {W}: {4}{W}, one white left over
    cast_with_offering(s, KITSUNE)
    assert zone_of(s, KITSUNE) == "stack" and s.state.players["p1"].mana == {"W": 1}
    check(s)
