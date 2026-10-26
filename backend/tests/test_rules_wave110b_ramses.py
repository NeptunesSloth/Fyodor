"""Wave 110B: Ramses, Assassin Lord (603.4 intervening "if", 508.1 who an attacker was declared against, 104.3a/704.5a a player loses)."""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.game_helpers import act, deck, enable
from tests.wave110b_kit import attack, check, put, through_combat

NAMES = ("Alice", "Bob", "Carol")


RAMSES = "Deathtouch\nOther Assassins you control get +1/+1.\nWhenever a player loses the game, if they were attacked this turn by an Assassin you controlled, you win the game."


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import fixture_cards
    from tests.test_rules_wave12a_counters_keywords import real

    settings.ensure_dirs()
    extra = [real("Ramses, Assassin Lord", "{1}{B}{B}", 3, "Legendary Creature — Human Assassin", RAMSES, ("3", "3"), "B")]
    build_database([*fixture_cards(), *extra], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def table(cards, attacker):
    """Alice has Ramses and ``attacker`` (a creature); Bob and Carol are the opponents."""
    decks = [deck(cards, c, [(1, "Ramses, Assassin Lord"), (1, "Grizzly Bears"), (9, "Forest")]) for c in ("Krenko, Mob Boss", "Atraxa, Praetors' Voice", "Krenko, Mob Boss")]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(NAMES, decks, strict=True)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    ramses = put(s, "Ramses, Assassin Lord")
    return s, ramses, put(s, attacker) if attacker != "Ramses, Assassin Lord" else ramses


@pytest.mark.parametrize("attacker,victim,wins", [("Ramses, Assassin Lord", "p2", True), ("Grizzly Bears", "p2", False)])
def test_ramses_wins_when_the_attacked_player_loses(cards, attacker, victim, wins):
    """Bob, attacked by Ramses (an Assassin), loses the game to the damage: Alice wins even with Carol alive; attacked by a Bear he doesn't."""
    assert coverage.of_card_data(cards.resolve("Ramses, Assassin Lord")).level == "FULL"
    s, _, creature = table(cards, attacker)
    act(s, "p2", type="life", player="p2", delta=-39)
    attack(s, creature, target=victim)
    try:
        through_combat(s)
    except ActionError:
        assert wins  # the game ended while play went on

    assert (s.state.rules.winner == "p1") is wins
    check(s)


def test_ramses_does_not_win_for_a_player_who_was_not_attacked(cards):
    """Carol loses (not attacked by an Assassin this turn): no win, even though Bob was attacked."""
    s, _, ramses = table(cards, "Ramses, Assassin Lord")
    attack(s, ramses, target="p2")
    act(s, "p3", type="life", player="p3", delta=-40)
    assert s.state.rules.winner is None
    check(s)
