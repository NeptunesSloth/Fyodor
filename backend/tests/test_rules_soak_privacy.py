"""Hidden information found by tools/soak.py: the commander list names each player's commander (903.3, public) but locates it only for a
viewer who may see it. A commander its owner put into their library (903.9b lets them) leaves the library unseen: its zone mustn't tell the
others the moment it is drawn, searched for or put back (400.2), as a face-down one's mustn't say which permanent it is (708.5)."""

from __future__ import annotations

from app.game.visibility import OMNISCIENT, SPECTATOR
from tests.game_helpers import act, find, make_session
from tests.test_rules_effects import replay_matches


def located(s, viewer):
    return next(c for p in s.view(viewer)["players"] if p["id"] == "p1" for c in p["commanders"])["zone"]


def test_a_commander_in_a_hidden_zone_is_not_located_for_others(cards):
    s = make_session(cards, shuffle=True)
    krenko = find(s.state, "Krenko, Mob Boss")
    assert located(s, "p2") == "p1:command"
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "library"})
    act(s, "p1", type="shuffle")
    for _ in range(40):
        act(s, "p1", type="draw", count=1)
        if s.state.cards[krenko.id].zone == "p1:hand":
            break
    assert s.state.cards[krenko.id].zone == "p1:hand"
    assert located(s, "p1") == "p1:hand" and located(s, OMNISCIENT) == "p1:hand"  # its owner (and the host's all-seeing view) still know
    assert located(s, "p2") is None and located(s, SPECTATOR) is None
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    assert located(s, "p2") == "p1:battlefield"  # public again
    replay_matches(s)



def test_the_soak_privacy_check_flags_a_hidden_name_but_not_one_inside_a_longer_visible_name(cards):
    """tools/soak.py's privacy check: a hidden card's name inside a longer visible name ("Badgermole" in the token "Badgermole Cub") isn't
    a leak; the name standing alone is."""
    import pytest

    from tools import soak

    s = make_session(cards)
    assert find(s.state, "Counterspell", "p2").zone == "p2:library"
    act(s, "p1", type="create_token", token={"name": "Counterspell Cub", "power": "1", "toughness": "1"})
    check = soak.Privacy(soak.CachedCards(cards)).check
    view = s.view("p1")
    assert "Counterspell Cub" in str(view)
    check(s, "p1", view)  # (inside a longer visible name: fine)
    with pytest.raises(AssertionError, match="Counterspell"):
        check(s, "p1", {**view, "leak": "Counterspell"})


def test_the_soak_privacy_check_lets_a_player_see_their_own_search(cards):
    """tools/soak.py's privacy check: Alice searching her own library sees her Sol Ring among the options while Bob's Sol Ring is in his
    library (soak seed 5201: Scapeshift and "Raugrin Triome"). That isn't a leak to Alice; the same name in Bob's view still is."""
    import pytest

    from app.game.factory import PlayerSetup, new_game
    from app.game.rules_state import Decision, DecisionOption
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable
    from tools import soak

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Sol Ring"), (5, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Sol Ring"), (5, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    mine, his = find(s.state, "Sol Ring", "p1"), find(s.state, "Sol Ring", "p2")
    assert mine.zone == "p1:library" and his.zone == "p2:library"
    s.state.rules.decision = Decision(id="d1", player="p1", kind="choose_cards", prompt="Search your library (artifact cards)",
                                      options=[DecisionOption(id=mine.id, label="Sol Ring", card_id=mine.id)], min_choices=0)
    check = soak.Privacy(soak.CachedCards(cards)).check
    check(s, "p1")  # (her own Sol Ring, in her own search)
    with pytest.raises(AssertionError, match="Sol Ring"):
        check(s, "p2", {**s.view("p2"), "leak": "Sol Ring"})
