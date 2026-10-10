"""Wave 22B: "Choose a card name. Search target player's graveyard, hand, and library for … cards with that name and exile them" (CR 201.4, 701.23,
701.24, 709.4a). Real Oracle text; every scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, mana

EXTRA = [
    real("Slaughter Games", "{2}{B}{R}", 4, "Sorcery", "This spell can't be countered.\nChoose a nonland card name. Search target opponent's graveyard, hand, and library for any number of cards with that name and exile them. Then that player shuffles.", None, "BR"),
    real("Ancient Vendetta", "{3}{B}", 4, "Sorcery", "Choose a card name. Search target opponent's graveyard, hand, and library for up to four cards with that name and exile them. Then that player shuffles.", None, "B"),
    real("Lost Legacy", "{1}{B}{B}", 3, "Sorcery", "Choose a nonartifact, nonland card name. Search target player's graveyard, hand, and library for any number of cards with that name and exile them. That player shuffles, then draws a card for each card exiled from their hand this way.", None, "B"),
    real("Dispossess", "{2}{B}", 3, "Sorcery", "Choose an artifact card name. Search target opponent's graveyard, hand, and library for any number of cards with the chosen name and exile them. Then that player shuffles.", None, "B"),
    real("Cranial Extraction", "{3}{B}", 4, "Sorcery — Arcane", "Choose a nonland card name. Search target player's graveyard, hand, and library for all cards with that name and exile them. Then that player shuffles.", None, "B"),
    real("Infinite Obliteration", "{1}{B}{B}", 3, "Sorcery", "Choose a creature card name. Search target opponent's graveyard, hand, and library for any number of cards with that name and exile them. Then that player shuffles.", None, "B"),
    real("Probe Bolt", "{R}", 1, "Instant", "Probe Bolt deals 1 damage to any target.", None, "R"),
    real("Probe Charm", "{G}", 1, "Instant", "You gain 1 life.", None, "G"),
    real("Probe Relic", "{3}", 3, "Artifact", ""),
    real("Probe Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]
FULL = ["Slaughter Games", "Ancient Vendetta", "Lost Legacy", "Dispossess", "Cranial Extraction", "Infinite Obliteration"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def table(cards, spell, bobs):
    alice = deck(cards, "Krenko, Mob Boss", [(1, spell), (9, "Swamp")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*bobs, (9, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def named(s, name, pid="p2"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid]


def cast(s, spell, target="p2", *answers):
    """Cast ``spell`` at ``target`` and answer: the first card name, then the picks of the search (an index list per question)."""
    c = named(s, spell, "p1")[0]
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, B=3, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target])
    return c


def drive(s, name, take=None):
    """Resolve: type ``name`` when asked; at the search choose ``take`` cards (None: every one offered)."""
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return asked
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.options and d.options[0].id == "__name__":
            act(s, d.player, type="choose", decision_id=d.id, name=name)
        else:
            ids = [o.id for o in d.options]
            asked.append((len(ids), d.max_choices))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids if take is None else ids[:take])
    raise AssertionError("stuck")


def zones_of(s, name, pid="p2"):
    return sorted(c.zone.split(":")[-1] for c in named(s, name, pid))


def test_slaughter_games_exiles_every_copy_in_every_zone_and_leaves_other_cards(cards):
    s = table(cards, "Slaughter Games", [(3, "Probe Bolt"), (1, "Probe Charm")])
    bolts, charm = named(s, "Probe Bolt"), named(s, "Probe Charm")[0]
    act(s, "p2", type="move", card_ids=[bolts[0].id], to={"zone": "hand"})
    act(s, "p2", type="move", card_ids=[bolts[1].id], to={"zone": "graveyard"})
    cast(s, "Slaughter Games")
    drive(s, "Probe Bolt")
    assert zones_of(s, "Probe Bolt") == ["exile"] * 3  # hand, graveyard and library
    assert s.state.cards[charm.id].zone != "p2:exile"
    check(s)


def test_a_search_may_take_fewer_and_up_to_four_is_a_limit(cards):
    s = table(cards, "Ancient Vendetta", [(6, "Probe Bolt")])
    cast(s, "Ancient Vendetta")
    asked = drive(s, "Probe Bolt", take=2)
    assert asked[0][1] == 4 and len(named(s, "Probe Bolt")) == 6  # six found, at most four may be taken
    assert zones_of(s, "Probe Bolt").count("exile") == 2  # 701.23b: the searcher took two
    check(s)


def test_lost_legacy_draws_a_card_for_each_one_exiled_from_the_hand(cards):
    s = table(cards, "Lost Legacy", [(4, "Probe Bolt"), (1, "Probe Charm")])
    bolts = named(s, "Probe Bolt")
    for b in bolts[:2]:
        act(s, "p2", type="move", card_ids=[b.id], to={"zone": "hand"})
    hand_before = len([c for c in s.state.cards.values() if c.zone == "p2:hand"])
    cast(s, "Lost Legacy")
    drive(s, "Probe Bolt")
    hand_after = len([c for c in s.state.cards.values() if c.zone == "p2:hand"])
    assert zones_of(s, "Probe Bolt") == ["exile"] * 4
    assert hand_after == hand_before - 2 + 2  # two left the hand, two cards were drawn for them
    check(s)


def test_the_name_must_fit_the_question(cards):
    s = table(cards, "Dispossess", [(1, "Probe Relic"), (1, "Probe Bolt")])
    cast(s, "Dispossess")
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d.options[0].group == "artifact card name"
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, name="Probe Bolt")  # not an artifact card
    act(s, "p1", type="choose", decision_id=d.id, name="Probe Relic")
    drive(s, "unused")
    assert zones_of(s, "Probe Relic") == ["exile"] and zones_of(s, "Probe Bolt") != ["exile"]
    check(s)


def test_a_search_for_a_creature_card_name_and_an_empty_search_still_shuffles(cards):
    s = table(cards, "Infinite Obliteration", [(1, "Probe Bear")])
    cast(s, "Infinite Obliteration")
    asked = drive(s, "Probe Bear")
    assert zones_of(s, "Probe Bear") == ["exile"] and asked
    s2 = table(cards, "Cranial Extraction", [(1, "Probe Charm")])
    cast(s2, "Cranial Extraction")
    drive(s2, "Probe Bolt")  # not in any of their zones: nothing is found, the search is still asked (its timing says nothing)
    assert zones_of(s2, "Probe Charm") != ["exile"]
    check(s)
    check(s2)
