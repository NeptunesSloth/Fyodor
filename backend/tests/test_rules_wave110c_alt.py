"""Wave 110C alternative costs: the Masteries' "if the cost was paid" lines (118.9, 608.2c).

* Ingenious Mastery, Devastating Mastery: the paid branch reads the cast record (one alternative cost: 118.9a); "an opponent" is chosen by the
  spell's controller as it resolves (the cycle's 2021-04-16 ruling).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, offers, put, real, to_hand, zone

EXTRA = [
    real('Ingenious Mastery', '{X}{2}{U}', 3, 'Sorcery',
         "You may pay {2}{U} rather than pay this spell's mana cost.\nIf the {2}{U} cost was paid, you draw three cards, then an opponent creates two Treasure tokens and they scry 2. If that cost wasn't paid, you draw X cards.", None, 'U'),
    real('Devastating Mastery', '{2}{W}{W}{W}{W}', 6, 'Sorcery',
         "You may pay {2}{W}{W} rather than pay this spell's mana cost.\nIf the {2}{W}{W} cost was paid, an opponent chooses up to two nonland permanents they control and returns them to their owner's hand.\nDestroy all nonland permanents.", None, 'W'),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _alt(s, name, **kw):
    card = to_hand(s, name)
    (offer,) = offers(s, card)
    act(s, "p1", type="cast_spell", card_id=card.id, alt_cost=offer.key, **kw)
    return card


@pytest.mark.parametrize("paid", [True, False])
def test_ingenious_mastery_alternative_cost_draws_three_and_gives_an_opponent_treasures_and_a_scry(cards, paid):
    """Ingenious Mastery: 118.9 the {2}{U} cost; paid: draw three, an opponent makes two Treasures and scries 2; else draw X."""
    s = build(cards, ["Ingenious Mastery"])
    hand = len(s.state.zones["p1:hand"])
    if paid:
        mana(s, U=1, C=2)
        _alt(s, "Ingenious Mastery")
    else:
        mana(s, U=1, C=4)
        cast(s, "Ingenious Mastery", x_value=2)
    asked = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            asked.append((d.player, d.kind))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert len(s.state.zones["p1:hand"]) == hand + (3 if paid else 2)  # (the spell was put into the hand and cast again: net zero)
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p2:battlefield"]
    assert len(treasures) == (2 if paid else 0)
    assert (("p2", "choose_cards") in asked) == paid  # (Bob scries 2, not Alice: 701.22a)
    check(s)


@pytest.mark.parametrize("paid", [True, False])
def test_devastating_mastery_opponent_returns_two_then_everything_else_is_destroyed(cards, paid):
    """Devastating Mastery: paid, the opponent chooses up to two nonland permanents they control and returns them (their choice); then all die."""
    s = build(cards, ["Devastating Mastery", "Grizzly Bears", "Forest"], ["Grizzly Bears", "Kami of Ancient Law", "Mulldrifter"])
    mine, forest = put(s, "Grizzly Bears"), put(s, "Forest")
    theirs = [put(s, "Grizzly Bears", "p2"), put(s, "Kami of Ancient Law", "p2"), put(s, "Mulldrifter", "p2")]
    if paid:
        mana(s, W=2, C=2)
        _alt(s, "Devastating Mastery")
        d = None
        for _ in range(10):
            d = s.state.rules.decision
            if d is not None and d.player == "p2":
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert d is not None and d.player == "p2" and d.max_choices == 2
        keep = [o.id for o in d.options if o.id in {theirs[0].id, theirs[1].id}]
        answer(s, keep)
    else:
        mana(s, W=4, C=2)
        cast(s, "Devastating Mastery")
        answer(s)
    assert zone(s, mine) == "p1:graveyard" and zone(s, forest) == "p1:battlefield"
    if paid:
        assert [zone(s, c) for c in theirs] == ["p2:hand", "p2:hand", "p2:graveyard"]
    else:
        assert [zone(s, c) for c in theirs] == ["p2:graveyard"] * 3
    check(s)
