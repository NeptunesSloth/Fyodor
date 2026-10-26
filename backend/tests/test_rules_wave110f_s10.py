"""Wave 110F session 10: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 702.33c: "As an additional cost to cast this spell, you may pay {1}{G} any number of times." + "3 life plus an additional 3 life for each additional {1}{G} you paid" (Taste of Paradise).
* 601.2, 609.4b: "you may cast a creature spell from that player's graveyard this turn, and you may spend mana as though it were mana of any color" (Whispersteel Dagger).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import attack
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
)
from tests.test_rules_wave100n_multi import cast
from tests.wave9c_kit import build, check, life, mana, put

EXTRA = [
    real('Whispersteel Dagger', '{2}', 2, 'Artifact — Equipment',
         "Equipped creature gets +2/+0.\nWhenever equipped creature deals combat damage to a player, you may cast a creature spell from that player's graveyard this turn, and you may spend mana as though it were mana of any color to cast that spell.\nEquip {3}", None, ''),
    real('Taste of Paradise', '{2}{G}', 3, 'Sorcery',
         "As an additional cost to cast this spell, you may pay {1}{G} any number of times.\nYou gain 3 life plus an additional 3 life for each additional {1}{G} you paid.", None, 'G'),
]
_BASE.extend(EXTRA)


@pytest.mark.parametrize("name", ["Whispersteel Dagger", "Taste of Paradise"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("target,second", [("p2", False), ("p1", False), ("p2", True)])
def test_dagger_casts_one_creature_from_the_damaged_players_graveyard(cards, target, second):
    """Only the damaged player's graveyard (not your own), one creature spell (a second needs its own grant), any color of mana."""
    s = build(cards, ["Whispersteel Dagger", "Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears", "Grizzly Bears"])
    dagger, runner = put(s, "Whispersteel Dagger"), put(s, "Grizzly Bears")
    act(s, "p1", type="attach", card_ids=[dagger.id], to=runner.id)
    ours = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1" and c.id != runner.id][0]
    theirs = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2"][:2]
    act(s, "p1", type="move", card_ids=[ours.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[c.id for c in theirs], to={"player": "p2", "zone": "graveyard"})
    attack(s, runner)
    answer(s)
    mana(s, "p1", U=4)
    if target == "p1":
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=ours.id, targets=[])
    else:
        act(s, "p1", type="cast_spell", card_id=theirs[0].id, targets=[])
        answer(s)
        assert s.state.cards[theirs[0].id].zone == "p1:battlefield"
        if second:
            with pytest.raises(ActionError):
                act(s, "p1", type="cast_spell", card_id=theirs[1].id, targets=[])
    check(s)


@pytest.mark.parametrize("times", [0, 1, 3])
def test_taste_of_paradise_gains_three_plus_three_per_extra_payment(cards, times):
    """702.33c: each extra {1}{G} paid adds 3 life."""
    s = build(cards, ["Taste of Paradise"])
    mana(s, "p1", G=1 + times, C=2 + times)
    cast(s, "Taste of Paradise", kicker=times)
    answer(s)
    assert life(s, "p1") == 40 + 3 + 3 * times
    check(s)
