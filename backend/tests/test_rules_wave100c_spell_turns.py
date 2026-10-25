"""Wave 100C: commanders, extra turns, turn-long limits and this turn's graveyard history (app/rules/static_spell100c.py), real Oracle text
(tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario checks the replay and a save and a load.

* 903.3 / 408.1: "returns each commander they control … to the command zone": each to its owner's command zone.
* 611.2a / 611.2c: "Creatures you control gain indestructible." states no duration: it lasts, for the creatures there as it resolved.
* 514.2 / 605.1a: "Until end of turn, target player can't cast instant or sorcery spells, and … can't activate abilities that aren't mana
  abilities": mana abilities stay possible; the next turn the player may cast them again.
* "Cards put there from the battlefield this turn": the creatures that died this turn, not a card milled from the library.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check
from tests.wave100c_kit import cast, chars, move, one, open_repo, put_on, settle, to_phase, zone

PROMOTED = ["Leadership Vacuum", "Chance for Glory", "Abeyance", "Thrilling Encore", "Sudden Salvation"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def commander(s, pid):
    return next(c for c in s.state.cards.values() if c.commander_key is not None and c.owner == pid)


def test_leadership_vacuum_returns_the_target_players_commanders_only(cards):
    """Leadership Vacuum: "Target player returns each commander they control from the battlefield to the command zone." / "Draw a card."
    Bob's commander goes back; Alice's stays."""
    s = build(cards, ["Leadership Vacuum"], [])
    atraxa, krenko = commander(s, "p2"), commander(s, "p1")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Leadership Vacuum", targets=["p2"], U=1, C=2)
    assert zone(s, atraxa) == "p2:command" and zone(s, krenko) == "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_chance_for_glory_lasting_indestructible_extra_turn_then_alice_loses(cards):
    """Chance for Glory: "Creatures you control gain indestructible. Take an extra turn after this one. At the beginning of that turn's end
    step, you lose the game." The creature keeps indestructible into the extra turn (no duration: 611.2a); at its end step Alice loses."""
    s = build(cards, ["Chance for Glory", "Grizzly Bears"], ["Llanowar Elves"])
    bear, theirs = put_on(s, "Grizzly Bears"), put_on(s, "Llanowar Elves", "p2")
    cast(s, "Chance for Glory", R=1, W=1, C=1)
    assert "indestructible" in chars(s, bear).keywords and "indestructible" not in chars(s, theirs).keywords
    act(s, "p1", type="set_stops", own=["main1"], others=[], smart_pass=False)
    to_phase(s, "main1", turn=2)
    assert s.state.turn.active_player == "p1" and "indestructible" in chars(s, bear).keywords
    for _ in range(40):
        if s.state.rules.winner is not None:
            break
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.winner == "p2" and s.state.turn.number == 2 and s.state.turn.phase == "end"
    check(s)


def test_abeyance_stops_instants_and_nonmana_abilities_this_turn_only(cards):
    """Abeyance: "Until end of turn, target player can't cast instant or sorcery spells, and that player can't activate abilities that aren't
    mana abilities." Bob can still tap Sol Ring for mana, but not cast Lightning Bolt nor activate Lifespark Spellbomb; on his turn he can."""
    s = build(cards, ["Abeyance"], ["Lightning Bolt", "Sol Ring", "Lifespark Spellbomb"])
    ring, bomb = put_on(s, "Sol Ring", "p2"), put_on(s, "Lifespark Spellbomb", "p2")
    bolt = move(s, one(s, "Lightning Bolt", "p2"), "hand")
    act(s, "p2", type="set_stops", own=["main1"], others=["main1"], smart_pass=False)
    cast(s, "Abeyance", targets=["p2"], W=1, C=1)
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1, "G": 1})
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=bomb.id, ability=1)
    act(s, "p2", type="activate_ability", card_id=ring.id, ability=0)  # (a mana ability: allowed)
    assert s.state.cards[ring.id].tapped
    to_phase(s, "main1", turn=2)
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])
    settle(s)
    assert zone(s, bolt) == "p2:graveyard" and s.state.players["p1"].life == 37
    check(s)


def test_thrilling_encore_takes_every_creature_that_died_this_turn(cards):
    """Thrilling Encore: both players' creatures destroyed this turn come back under Alice's control; a creature card milled from the library
    (not put there from the battlefield) stays."""
    s = build(cards, ["Thrilling Encore", "Day of Judgment", "Grizzly Bears", "Llanowar Elves"], ["Benalish Hero"])
    bear, hero = put_on(s, "Grizzly Bears"), put_on(s, "Benalish Hero", "p2")
    milled = move(s, one(s, "Llanowar Elves"), "graveyard")
    cast(s, "Day of Judgment", W=2, C=2)
    assert zone(s, bear) == "p1:graveyard" and zone(s, hero) == "p2:graveyard"
    cast(s, "Thrilling Encore", B=1, C=4)
    assert zone(s, bear) == "p1:battlefield" and zone(s, hero) == "p1:battlefield" and s.state.cards[hero.id].controller == "p1"
    assert zone(s, milled) == "p1:graveyard"
    check(s)


def test_sudden_salvation_returns_tapped_to_owners_and_draws_for_each_opponent_holding_one(cards):
    """Sudden Salvation: up to three target permanent cards put into graveyards from the battlefield this turn return tapped under their owners'
    control; Alice draws one card (Bob is the one opponent who controls one of them)."""
    s = build(cards, ["Sudden Salvation", "Day of Judgment", "Grizzly Bears"], ["Benalish Hero", "Llanowar Elves"])
    bear, hero, elves = put_on(s, "Grizzly Bears"), put_on(s, "Benalish Hero", "p2"), put_on(s, "Llanowar Elves", "p2")
    cast(s, "Day of Judgment", W=2, C=2)
    hand = len(s.state.zones["p1:hand"])
    spell = cast(s, "Sudden Salvation", targets=[bear.id, hero.id, elves.id], target_counts=[3], W=2, C=2)
    assert zone(s, spell) == "p1:graveyard"
    assert zone(s, bear) == "p1:battlefield" and zone(s, hero) == "p2:battlefield" and zone(s, elves) == "p2:battlefield"
    assert all(s.state.cards[c.id].tapped for c in (bear, hero, elves))
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (one card drawn: one opponent)
    check(s)
