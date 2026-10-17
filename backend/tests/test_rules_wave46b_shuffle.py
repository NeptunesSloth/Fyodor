"""Wave 46B: "Target player shuffles up to N target cards from their graveyard into their library" (CR 2026-09-25, real Oracle text,
tests/fixtures/wave46b_cards.json). Every scenario checks the replay and a save and a load.

* 701.24a: to shuffle cards into a library is to put them in, then shuffle it; the cards chosen are in the target player's graveyard (the spell names
  the player first, so the cards on offer are only that graveyard's), up to the number named (Stream of Consciousness ruling 2018-12-07: zero is fine).
* 608.2b (Memory's Journey ruling 2011-09-22): a card that is no longer a legal target isn't shuffled in, the player still shuffles their library; if the
  player is no longer a legal target the spell does nothing (no effect even though the cards are still legal).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave5j_token_copies import drive
from tests.test_rules_wave38a_trailing_ifs import table
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave36a_kit import to_gy
from tests.wave46b_kit import make_repo, zone


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Memory's Journey", "Stream of Consciousness", "Krosan Reclamation", "Dwell on the Past", "Gaea's Blessing",
                                  "Rite of Renewal", "Quandrix Command"])
def test_the_shufflers_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pick(*first):
    """Answer the target questions in order: the player, then the cards."""
    queue = list(first)
    return lambda d: queue.pop(0) if queue else None


def test_stream_of_consciousness_shuffles_chosen_cards_into_the_targets_library(cards):
    s = table(cards, ["Stream of Consciousness", "Grizzly Bears", "Soul Warden", "Young Wolf"])
    bears, warden = to_gy(s, "Grizzly Bears"), to_gy(s, "Soul Warden")
    to_hand(s, "Stream of Consciousness")
    mana(s, U=4)
    library = len(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Stream of Consciousness").id)
    drive(s, pick(["p1"], [bears.id]))
    assert zone(s, "Grizzly Bears") == "p1:library" and zone(s, "Soul Warden") == "p1:graveyard"
    assert len(s.state.zones["p1:library"]) == library + 1 and warden.id in s.state.zones["p1:graveyard"]
    check(s)


def test_the_cards_on_offer_are_only_the_chosen_players_graveyard(cards):
    s = table(cards, ["Stream of Consciousness", "Grizzly Bears"], ["Soul Warden"])
    mine, theirs = to_gy(s, "Grizzly Bears"), to_gy(s, "Soul Warden", "p2")
    to_hand(s, "Stream of Consciousness")
    mana(s, U=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Stream of Consciousness").id)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])
    d = s.state.rules.decision
    assert [o.id for o in d.options] == [theirs.id] and mine.id not in [o.id for o in d.options]
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[mine.id])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[theirs.id])
    drive(s)
    assert zone(s, "Soul Warden", "p2") == "p2:library" and zone(s, "Grizzly Bears") == "p1:graveyard"
    check(s)


def test_with_no_card_chosen_the_player_still_shuffles_their_library(cards):
    s = table(cards, ["Memory's Journey", "Grizzly Bears"])
    to_hand(s, "Memory's Journey")
    mana(s, U=2)
    before = list(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Memory's Journey").id)
    drive(s, pick(["p1"], []))
    assert zone(s, "Memory's Journey") == "p1:graveyard"
    assert len(s.state.zones["p1:library"]) == len(before) and not set(before) & set(s.state.zones["p1:library"])  # (701.20d: a shuffled library is all new)
    check(s)


def test_a_card_that_left_the_graveyard_is_not_shuffled_in(cards):
    s = table(cards, ["Stream of Consciousness", "Grizzly Bears", "Soul Warden"])
    bears, warden = to_gy(s, "Grizzly Bears"), to_gy(s, "Soul Warden")
    to_hand(s, "Stream of Consciousness")
    mana(s, U=4)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Stream of Consciousness").id)
    for answer in (["p1"], [bears.id, warden.id]):
        act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=answer)
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "exile"})  # (a new object in exile: no longer the card that was targeted)
    drive(s)
    assert zone(s, "Grizzly Bears") == "p1:exile" and zone(s, "Soul Warden") == "p1:library"
    check(s)


def want(*ids):
    """Answer each question with the wanted options it offers (the player, the creature, the card, whichever comes up)."""
    def choose(d):
        offered = [o.id for o in d.options]
        return [i for i in ids if i in offered][: max(1, d.max_choices)] or None
    return choose


def test_quandrix_command_mode_with_two_target_groups(cards):
    s = table(cards, ["Quandrix Command", "Grizzly Bears", "Soul Warden"])
    put(s, "Grizzly Bears")
    warden = to_gy(s, "Soul Warden")
    to_hand(s, "Quandrix Command")
    mana(s, G=1, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Quandrix Command").id, modes=[2, 3])
    drive(s, want("p1", warden.id, card_named(s, "Grizzly Bears").id))
    assert zone(s, "Soul Warden") == "p1:library" and card_named(s, "Grizzly Bears").counters == {"+1/+1": 2}
    check(s)


def test_loaming_shaman_trigger_shuffles_any_number_of_an_opponents_cards(cards):
    s = table(cards, ["Loaming Shaman"], ["Grizzly Bears", "Soul Warden", "Young Wolf"])
    bears, warden = to_gy(s, "Grizzly Bears", "p2"), to_gy(s, "Soul Warden", "p2")
    to_hand(s, "Loaming Shaman")
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Loaming Shaman").id)
    drive(s, want("p2", bears.id, warden.id))
    assert zone(s, "Grizzly Bears", "p2") == "p2:library" and zone(s, "Soul Warden", "p2") == "p2:library"
    check(s)


def test_rite_of_renewal_numbers_its_groups_across_both_sentences(cards):
    s = table(cards, ["Rite of Renewal", "Grizzly Bears", "Soul Warden"])
    bears, warden = to_gy(s, "Grizzly Bears"), to_gy(s, "Soul Warden")
    to_hand(s, "Rite of Renewal")
    mana(s, G=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Rite of Renewal").id)
    answers = [[bears.id], ["p1"], [warden.id]]  # (the card to return, the player, the card the player's graveyard gives)
    for answer in answers:
        d = s.state.rules.decision
        offered = [o.id for o in d.options]
        assert set(answer) <= set(offered)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=answer)
    drive(s)
    assert zone(s, "Grizzly Bears") == "p1:hand" and zone(s, "Soul Warden") == "p1:library" and zone(s, "Rite of Renewal") == "p1:exile"
    check(s)
