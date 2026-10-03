"""Wave 11D: searching a player's graveyard, hand and library for cards with a name (Extirpate, Surgical Extraction, Counterbore,
Eradicate …), researched against CR 2026-09-25.

* 201.2 — the name searched for is the one the object had; 608.2h — last known information once it left;
* 701.23 — the searcher looks through hidden zones: only they learn what is there; 701.23b — they may find fewer;
* 701.24 — the searched player (the library's owner) shuffles afterwards.

Every scenario checks the other player's view, replays the history and reloads a save.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act, zone
from tests.test_rules_effects import mana, replay_matches, token
from tests.test_rules_player_choices import activate, assert_observer_sees_only_who, choose, reloaded
from tests.test_rules_wave11d_hand_and_names import reloaded_table, seen_by

EXTIRPATE = ("Choose target card in a graveyard other than a basic land card. Search its owner's graveyard, hand, and library for "
             "all cards with the same name as that card and exile them. Then that player shuffles.")
SURGICAL = EXTIRPATE.replace("all cards", "any number of cards")
COUNTERBORE = ("Counter target spell. Search its controller's graveyard, hand, and library for all cards with the same name as that "
               "spell and exile them. Then that player shuffles.")


def vipers_table(cards, owner="p2"):
    """Three Ambush Vipers per player; the owner's first is in the graveyard, the second in the hand, the third in the library."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(3, "Ambush Viper"), (12, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(3, "Ambush Viper"), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), "full"),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    vipers = [c for c in s.state.cards.values() if c.name == "Ambush Viper" and c.owner == owner]
    for c, z in zip(vipers[:2], ("graveyard", "hand"), strict=True):
        act(s, owner, type="move", card_ids=[c.id], to={"player": owner, "zone": z})
    return s, vipers


def test_extirpate_exiles_every_copy_from_the_graveyard_hand_and_library_and_shuffles(cards):
    s, (in_gy, in_hand, in_library) = vipers_table(cards)
    other = [c for c in zone(s.state, "p2", "hand") if c != in_hand.id]
    before = list(zone(s.state, "p2", "library"))
    src = token(s, "p1", "Extirpator", "1/1", text=f"{{1}}: {EXTIRPATE}")
    activate(s, src, targets=[in_gy.id])
    assert s.state.rules.decision is None  # "all cards": nothing to ask, so no decision whose timing could tell anything
    assert all(s.state.cards[c.id].zone == "p2:exile" for c in (in_gy, in_hand, in_library))
    assert len(zone(s.state, "p2", "library")) == len(before) - 1
    assert zone(s.state, "p2", "library") != [c for c in before if c != in_library.id]  # shuffled (701.24)
    assert all(s.state.cards[c].zone == "p2:hand" for c in other) and seen_by(s, "p1", other) == []
    replay_matches(s)
    replay_matches(reloaded_table(s))


def test_extirpate_cannot_target_a_basic_land_card(cards):
    s, _ = vipers_table(cards)
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone.endswith(":library"))
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "graveyard"})
    src = token(s, "p1", "Extirpator", "1/1", text=f"{{1}}: {EXTIRPATE}")
    mana(s, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[island.id])


def test_surgical_extraction_lets_the_searcher_find_fewer_in_private(cards):
    s, (in_gy, in_hand, in_library) = vipers_table(cards)
    src = token(s, "p1", "Extractor", "1/1", text=f"{{1}}: {SURGICAL}")
    activate(s, src, targets=[in_gy.id])
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {in_gy.id, in_hand.id, in_library.id}
    assert (d.min_choices, d.max_choices) == (0, 3)
    assert_observer_sees_only_who(s, "p2", "Alice")  # Bob learns nothing of what Alice is choosing among
    again = reloaded(s)
    choose(s, [in_gy.id, in_library.id])
    assert s.state.cards[in_gy.id].zone == "p2:exile" and s.state.cards[in_library.id].zone == "p2:exile"
    assert s.state.cards[in_hand.id].zone == "p2:hand" and s.state.cards[in_hand.id].revealed_to == []
    assert seen_by(s, "p1", [in_hand.id]) == []
    replay_matches(s)
    act(again, "p1", type="choose", decision_id=again.state.rules.decision.id, option_ids=[])  # finds none: still shuffles
    assert again.state.cards[in_hand.id].zone == "p2:hand" and again.state.rules.decision is None


def test_surgical_extraction_asks_even_when_only_the_target_is_there(cards):
    """Whether a decision appears must not say whether a hidden copy exists: it asks all the same."""
    s, (in_gy, in_hand, in_library) = vipers_table(cards)
    for c in (in_hand, in_library):
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    src = token(s, "p1", "Extractor", "1/1", text=f"{{1}}: {SURGICAL}")
    activate(s, src, targets=[in_gy.id])
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == [in_gy.id]
    choose(s, [])
    assert s.state.cards[in_gy.id].zone == "p2:graveyard"


def test_counterbore_searches_the_countered_spells_controller(cards):
    """Bob counters Alice's Ambush Viper: her other Vipers go too, from her hand, graveyard and library, and she shuffles."""
    s, bob_vipers = vipers_table(cards)
    mine = [c for c in s.state.cards.values() if c.name == "Ambush Viper" and c.owner == "p1"]
    for c, z in zip(mine[:2], ("hand", "graveyard"), strict=True):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": z})
    mana(s, G=1, C=1)
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="cast_spell", card_id=mine[0].id)
    assert mine[0].id in s.state.zones["stack"]
    src = token(s, "p2", "Borer", "1/1", text=f"{{1}}: {COUNTERBORE}")  # (Bob counters Alice's spell and searches her zones)
    mana(s, "p2", C=1)
    act(s, "p2", type="activate_ability", card_id=src.id, ability=0, targets=[mine[0].id])
    for _ in range(4):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert all(s.state.cards[c.id].zone == "p1:exile" for c in mine)  # the countered spell and the others, wherever they were
    assert all(s.state.cards[c.id].zone != "p2:exile" for c in bob_vipers)
    replay_matches(s)


def test_eradicate_remembers_the_name_of_a_token_that_was_exiled(cards):
    """The exiled creature ceased to exist as a token, but its name (last known information) is what is searched for."""
    s, (in_gy, in_hand, in_library) = vipers_table(cards)
    token(s, "p2", "Ambush Viper", "2/1")
    tok = next(c for c in s.state.cards.values() if c.name == "Ambush Viper" and c.zone == "p2:battlefield")  # (the token)
    src = token(s, "p1", "Eradicator", "1/1", text="{1}: Exile target nonblack creature. Search its controller's graveyard, hand, and "
                                                    "library for all cards with the same name as that creature and exile them. "
                                                    "Then that player shuffles.")
    activate(s, src, targets=[tok.id])
    assert tok.id not in s.state.cards
    assert all(s.state.cards[c.id].zone == "p2:exile" for c in (in_gy, in_hand, in_library))
    replay_matches(s)
