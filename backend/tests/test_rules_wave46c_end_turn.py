"""Wave 46C: "End the turn." (CR 724.1, 2026-09-25), real Oracle text (tests/fixtures/wave46c_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 724.1b: Time Stop [7170] exiles every object on the stack, itself included - the spell it answered is exiled, not countered (ruling 2007-07-15).
* 724.1a, 724.1d: Ultima [8446] destroys all artifacts and creatures, then ends the turn; the "dies" ability that destroying triggered ceases to exist (ruling 2025-06-06);
  an attacking creature is removed from combat and no combat damage is dealt.
* 514.1, 724.1d: the cleanup step happens in its entirety - the player whose turn it is discards down to their maximum hand size.
* 602.5, 724.1: Sundial of the Infinite [2794] ("{1}, {T}: End the turn. Activate only during your turn.").
* 724.1: Day's Undoing [5770] shuffles hand and graveyard into the library, draws seven, and ends the turn only if it's the caster's turn.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave46c_kit import FULL, cast, life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def respond(s, pid, name, **kw):
    """This player casts the spell (Alice already passed), then everything settles."""
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    for _ in range(20):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def test_time_stop_exiles_the_spell_it_answers_and_itself_and_ends_the_turn(cards):
    s = build(cards, ["Shock"], ["Time Stop"])
    stops(s)
    to_hand(s, "Shock")
    to_hand(s, "Time Stop", "p2")
    mana(s, R=1)
    mana(s, "p2", U=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Shock").id, targets=["p2"])
    respond(s, "p2", "Time Stop")
    assert zone_of(s, "Shock") == "p1:exile" and zone_of(s, "Time Stop", "p2") == "p2:exile"  # 724.1b: exiled, not put into a graveyard
    assert life(s, "p2") == 40  # Shock never resolved
    assert s.state.turn.number == 2 and s.state.turn.active_player == "p2"
    check(s)


def test_time_stop_with_a_full_hand_asks_for_the_cleanup_discard_before_the_turn_ends(cards):
    s = build(cards, ["Time Stop"], [])
    to_hand(s, "Time Stop")
    for cid in s.state.zones["p1:library"][:8]:  # (the table starts with empty hands)
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "hand"})
    assert len(s.state.zones["p1:hand"]) == 9
    mana(s, U=2, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Time Stop").id)
    for _ in range(10):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.player == "p1" and s.state.turn.number == 1  # 514.1: 8 in hand after the cast, 7 is the maximum
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert len(s.state.zones["p1:hand"]) == 7 and s.state.turn.number == 2 and s.state.turn.active_player == "p2"
    check(s)


def test_ultima_destroys_then_ends_the_turn_and_the_triggers_it_caused_cease(cards):
    s = build(cards, ["Ultima", "Doomed Traveler", "Hill Giant"], [])
    put(s, "Doomed Traveler")
    put(s, "Hill Giant")
    to_hand(s, "Ultima")
    mana(s, W=2, C=3)
    cast(s, "Ultima")
    assert zone_of(s, "Doomed Traveler") == "p1:graveyard" and zone_of(s, "Hill Giant") == "p1:graveyard"
    assert zone_of(s, "Ultima") == "p1:exile"  # 724.1b: the resolving sorcery is exiled too
    assert not any(c.name == "Spirit" for c in s.state.cards.values())  # 724.1a: the dies ability never reached the stack
    assert s.state.turn.number == 2
    check(s)


def test_an_attacker_is_removed_from_combat_by_the_end_of_the_turn(cards):
    s = build(cards, ["Hill Giant"], ["Time Stop"])
    stops(s)
    giant = put(s, "Hill Giant")
    to_hand(s, "Time Stop", "p2")
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p2"}])
    act(s, "p1", type="pass_priority")
    mana(s, "p2", U=6)
    respond(s, "p2", "Time Stop")
    assert life(s, "p2") == 40 and s.state.cards[giant.id].attacking is None  # 724.1d: no combat damage
    assert s.state.turn.number == 4 and s.state.turn.active_player == "p2"
    check(s)


def test_sundial_of_the_infinite_ends_the_turn_on_its_controllers_turn_only(cards):
    s = build(cards, ["Sundial of the Infinite"], [])
    sundial = put(s, "Sundial of the Infinite")
    mana(s, C=1)
    activate(s, "p1", sundial)
    for _ in range(10):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.number == 2 and s.state.cards[sundial.id].tapped
    check(s)


def test_sundial_cannot_be_activated_on_an_opponents_turn(cards):
    s = build(cards, ["Sundial of the Infinite"], [])
    sundial = put(s, "Sundial of the Infinite")
    stops(s)
    to_phase(s, "upkeep", turn=2)
    mana(s, C=1)
    with pytest.raises(ActionError):
        activate(s, "p1", sundial)  # "Activate only during your turn."
    check(s)


def test_days_undoing_shuffles_draws_seven_and_ends_the_turn(cards):
    s = build(cards, ["Day's Undoing", "Hill Giant"], [])
    to_hand(s, "Day's Undoing")
    to_hand(s, "Hill Giant")
    mana(s, U=1, C=2)
    cast(s, "Day's Undoing")
    assert len(s.state.zones["p1:hand"]) == 7 and not s.state.zones.get("p1:graveyard")
    assert zone_of(s, "Day's Undoing") == "p1:exile"  # 724.1b: exiled while resolving, after its shuffle
    assert s.state.turn.number == 2
    check(s)


def obeka_on_alices_turn(s, answer):
    """Bob's Obeka (in play since his turn 2) is activated in Alice's turn 3; the player whose turn it is - Alice - answers."""
    stops(s)
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="pass_priority")
    obeka = card_named(s, "Obeka, Brute Chronologist", "p2")
    activate(s, "p2", obeka)
    for _ in range(4):  # (both pass: the ability resolves and asks)
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.kind == "confirm"  # 608.2d: the active player decides, not Obeka's controller
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[answer])
    return obeka


def test_obekas_ability_lets_the_player_whose_turn_it_is_end_the_turn(cards):
    s = build(cards, [], ["Obeka, Brute Chronologist"])
    put(s, "Obeka, Brute Chronologist", "p2")
    obeka = obeka_on_alices_turn(s, "yes")
    assert s.state.turn.number == 4 and s.state.turn.active_player == "p2" and not s.state.cards[obeka.id].tapped  # (it untapped in its controller's untap step)
    check(s)


def test_obekas_ability_does_nothing_when_the_player_whose_turn_it_is_declines(cards):
    s = build(cards, [], ["Obeka, Brute Chronologist"])
    put(s, "Obeka, Brute Chronologist", "p2")
    obeka = obeka_on_alices_turn(s, "no")
    assert s.state.turn.number == 3 and s.state.cards[obeka.id].tapped
    check(s)


def test_hurkyls_final_meditation_bounces_all_nonland_permanents_and_ends_the_turn(cards):
    s = build(cards, ["Hurkyl's Final Meditation", "Hill Giant"], ["Grizzly Bears"])
    put(s, "Hill Giant"), put(s, "Grizzly Bears", "p2")
    to_hand(s, "Hurkyl's Final Meditation")
    mana(s, U=3, C=4)  # on its controller's turn: no extra {3}
    cast(s, "Hurkyl's Final Meditation")
    assert zone_of(s, "Hill Giant") == "p1:hand" and zone_of(s, "Grizzly Bears", "p2") == "p2:hand"
    assert s.state.turn.number == 2 and zone_of(s, "Hurkyl's Final Meditation") == "p1:exile"
    check(s)


def test_hurkyls_final_meditation_costs_three_more_on_other_turns(cards):
    s = build(cards, ["Hurkyl's Final Meditation"], [])
    to_hand(s, "Hurkyl's Final Meditation")
    stops(s)
    to_phase(s, "upkeep", turn=2)
    act(s, "p2", type="pass_priority")
    mana(s, U=3, C=4)
    with pytest.raises(ActionError, match="Not enough mana to pay"):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Hurkyl's Final Meditation").id)  # {4}{U}{U}{U} and {3} more
    mana(s, C=3)
    cast(s, "Hurkyl's Final Meditation")
    assert s.state.turn.number == 3
    check(s)


def test_glorious_end_ends_the_turn_and_its_controller_loses_at_their_next_end_step(cards):
    # 724.1e: the end step of this turn is skipped, so "your next end step" is the one of Alice's next turn; the delayed trigger (603.7) is made as the spell resolves
    s = build(cards, ["Glorious End"], [])
    to_hand(s, "Glorious End")
    mana(s, R=1, C=2)
    cast(s, "Glorious End")
    assert s.state.turn.number == 2 and s.state.turn.active_player == "p2" and zone_of(s, "Glorious End") == "p1:exile"
    assert [d.controller for d in s.state.rules.delayed] == ["p1"] and s.state.rules.winner is None
    stops(s)
    to_phase(s, "end", turn=3)  # Bob's end step passed without a loss; this is Alice's
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.rules.winner is None:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.winner == "p2"
    check(s)
