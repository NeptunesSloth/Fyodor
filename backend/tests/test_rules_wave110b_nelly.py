"""Wave 110B: Nelly Borca, Impulsive Accuser (701.60 suspect, 701.15 goad every suspected creature, 603.2c a combat-damage batch, 608.2h)."""
from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.game_helpers import act, deck, enable
from tests.wave110b_kit import attack, check, drive, put, through_combat

NELLY = ("Vigilance\nWhenever Nelly Borca attacks, suspect target creature. Then goad all suspected creatures. (A suspected creature has menace and can't block.)\n"
         "Whenever one or more creatures an opponent controls deal combat damage to one or more of your opponents, you and the controller of those creatures each draw a card.")


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import fixture_cards
    from tests.test_rules_wave12a_counters_keywords import real

    settings.ensure_dirs()
    extra = [real("Nelly Borca, Impulsive Accuser", "{2}{R}{W}", 4, "Legendary Creature — Human Detective", NELLY, ("2", "4"), "RW")]
    build_database([*fixture_cards(), *extra], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def table(cards):
    decks = [deck(cards, c, [(1, "Nelly Borca, Impulsive Accuser"), (1, "Grizzly Bears"), (30, "Forest")]) for c in ("Krenko, Mob Boss", "Atraxa, Praetors' Voice", "Krenko, Mob Boss")]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def hand(s, pid):
    return len(s.state.zones[f"{pid}:hand"])


def test_nelly_suspects_and_goads_every_suspected_creature(cards):
    """Attacking, Nelly suspects Bob's Bears (target), then every suspected creature is goaded: the Bears must attack and can't block."""
    assert coverage.of_card_data(cards.resolve("Nelly Borca, Impulsive Accuser")).level == "FULL"
    s = table(cards)
    nelly, bears = put(s, "Nelly Borca, Impulsive Accuser"), put(s, "Grizzly Bears", "p2")
    attack(s, nelly, target="p3")
    drive(s, lambda d: [bears.id] if any(o.id == bears.id for o in d.options) else None)
    assert s.state.rules.object_id(bears.id) in s.state.rules.suspected
    from app.rules import keyword_actions
    from app.rules.plan import Plan

    assert "p1" in keyword_actions.goaded_by(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id]))
    check(s)


def test_nelly_both_players_draw_when_an_opponents_creature_damages_an_opponent(cards):
    """Carol has Nelly: Alice's Bears hit Bob (both Carol's opponents), so Carol and Alice each draw a card and Bob doesn't."""
    s = table(cards)
    put(s, "Nelly Borca, Impulsive Accuser", "p3")
    bears = put(s, "Grizzly Bears")
    before = {p: hand(s, p) for p in ("p1", "p2", "p3")}
    attack(s, bears, target="p2")
    through_combat(s)
    assert {p: hand(s, p) - before[p] for p in before} == {"p1": 1, "p2": 0, "p3": 1}
    check(s)
