"""Review of wave 25C (if-you-do / instead / this-turn sweep): regression tests on real Oracle text, replayed and reloaded.

* A "you may put a … card from your hand onto the battlefield" whose "may" moved from the triggered / loyalty ability to the effect
  (scripts._own_choice) is asked whenever the hand holds cards, so whether the question appears doesn't tell the other players that a
  matching card is there (hidden information, 402.3).
* "You may cast that card. If you don't, …" (Chandra, Torch of Defiance) with an {X} card exiled: the native cast announces X (601.2b), and
  "If you don't" reads the player's answer instead of always happening (608.2c)."""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_refused_look import choose, decision, put, stack_library
from tests.test_rules_wave25c_exile_riders import OURS, cards  # noqa: F401 (the fixture)


def build(cards):  # noqa: F811
    from app.game.factory import PlayerSetup, new_game
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(1, n) for n in OURS] + [(1, "Endless One"), (1, "Lightning Bolt"), (2, "Grizzly Bears"),
                                                                     (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def reloaded(s):
    return GameSession(s.history.rebuild(), cards=s.cards).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def test_garruk_asks_even_without_a_green_creature_card_in_hand(cards):  # noqa: F811
    s = build(cards)
    garruk = put(s, "Garruk, Caller of Beasts", "battlefield")
    act(s, "p1", type="counter", card_ids=[garruk.id], kind="loyalty", delta=4)
    for c in [c for c in s.state.cards.values() if c.zone == "p1:hand"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library", "player": "p1"})
    put(s, "Lightning Bolt", "hand")  # (a card, but no green creature card)
    act(s, "p1", type="activate_ability", card_id=garruk.id, ability=1)
    pass_until_stack_empty(s)
    d = decision(s, "put_from_hand")
    assert d.player == "p1" and d.options == [] and d.min_choices == 0  # asked all the same: nothing to tell Bob
    choose(s, [], resolve=True)
    assert s.state.rules.decision is None
    replay_matches(s)
    assert reloaded(s)


@pytest.mark.parametrize("cast", [True, False])
def test_chandra_with_an_x_card_exiled_reads_whether_it_was_cast_natively(cards, cast):  # noqa: F811
    s = build(cards)
    chandra = put(s, "Chandra, Torch of Defiance", "battlefield")
    act(s, "p1", type="counter", card_ids=[chandra.id], kind="loyalty", delta=4)
    top = stack_library(s, ["Endless One"])[0]  # mana cost {X}
    act(s, "p1", type="activate_ability", card_id=chandra.id, ability=0)
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [top]
    choose(s, [top] if cast else [], resolve=True)
    if cast:
        d = decision(s, "free_x")
        assert [o.id for o in d.options] == ["x:0", "x:other"]  # (a paid cast may announce any X, 107.3a; only 0 is affordable)
        choose(s, ["x:0"], resolve=True)
    assert s.state.rules.decision is None
    assert s.state.players["p2"].life == (40 if cast else 38)  # "If you don't, Chandra deals 2 damage to each opponent"
    assert s.state.cards[top].zone == ("p1:graveyard" if cast else "p1:exile")
    replay_matches(s)
    assert reloaded(s)
