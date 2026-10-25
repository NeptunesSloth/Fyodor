"""Wave 110B session 12 (real Oracle text in tests/fixtures/wave110b_cards.json).

* Stunning Reversal: 614.1a, 614.5 the next loss of the game this turn draws seven and sets life to 1; the card is exiled; used up after one loss.
* Genku: 700.2, a mode not yet chosen this turn (modal memory) makes one of three tokens per nontoken permanent leaving.
* Unidentified Hovership: 607.2a, 701.62a the exiled card's owner (not the Vehicle's controller) manifests dread when the Vehicle leaves.
* Martyr's Bond: 603.10a, 608.2h each opponent sacrifices a permanent sharing a card type with the one that went to the graveyard (as it last existed).
* Rendmaw, Creaking Nest: 205.2a a played card with two or more types (Ornithopter, Dryad Arbor) or entering gives each player a goaded Bird (701.15a, for the rest of the game).
* Oblivious Bookworm: 708.2, 708.8 the end-step loot discards unless a permanent entered face down under your control this turn or you turned one face up this turn.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import build, card_named, ch, check, drive, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Oblivious Bookworm", "Stunning Reversal", "Genku, Future Shaper", "Unidentified Hovership", "Martyr's Bond", "Rendmaw, Creaking Nest"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _bookworm(cards, face_down_this_turn, turn_up_this_turn=False):
    s = build(cards, ["Oblivious Bookworm", "Willbender", "Forest", "Forest", "Forest"], [])
    put(s, "Oblivious Bookworm")
    if turn_up_this_turn:  # cast face down on turn 1, turned up on turn 3
        mana(s, "p1", C=3)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Willbender").id, face_down=True)
        drive(s)
        to_phase(s, "main1", turn=3)
        mana(s, "p1", U=1, C=1)
        act(s, "p1", type="turn_face_up", card_id=card_named(s, "Willbender").id)
        drive(s)
    elif face_down_this_turn:
        mana(s, "p1", C=3)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Willbender").id, face_down=True)
        drive(s)
    return s


@pytest.mark.parametrize("face_down, turn_up, discards", [(False, False, 1), (True, False, 0), (False, True, 0)])
def test_oblivious_bookworm_discards_unless_face_down_history(cards, face_down, turn_up, discards):
    s = _bookworm(cards, face_down, turn_up)
    gy = lambda: len(s.state.zones["p1:graveyard"])  # noqa: E731
    before = gy()
    to_phase(s, "main1", turn=s.state.turn.number + 2 if turn_up else 2)
    drive(s)
    assert gy() - before == discards  # (the may-draw was taken in all three cases)
    check(s)


def _lose(s):
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")  # (the next state-based check: a table edit is not an intent)
    drive(s)


def _reversal(cards):
    s = build(cards, ["Stunning Reversal", "Forest"], [])
    mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Stunning Reversal").id)
    drive(s)
    return s


def test_stunning_reversal_replaces_the_first_loss_only(cards):
    s = _reversal(cards)
    card = card_named(s, "Stunning Reversal")
    assert s.state.cards[card.id].zone == "p1:exile"
    hand = len(s.state.zones["p1:hand"])
    _lose(s)
    assert s.state.players["p1"].life == 1 and len(s.state.zones["p1:hand"]) == hand + 7 and s.state.rules.winner is None
    _lose(s)  # used up
    assert s.state.rules.winner == "p2"
    check(s)


def test_stunning_reversal_ends_with_the_turn(cards):
    s = _reversal(cards)
    to_phase(s, "main1", turn=3)
    _lose(s)
    assert s.state.rules.winner == "p2"


def test_genku_makes_each_token_once_per_turn_and_ignores_tokens(cards):
    s = build(cards, ["Genku, Future Shaper", "Zuran Orb", "Forest", "Forest", "Forest", "Forest"], [])
    put(s, "Genku, Future Shaper")
    orb = put(s, "Zuran Orb")
    forests = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:4]
    for fid in forests:
        act(s, "p1", type="move", card_ids=[fid], to={"player": "p1", "zone": "battlefield"})
    seen = []
    for fid in forests:
        act(s, "p1", type="activate_ability", card_id=orb.id, ability=0)
        drive(s, lambda d, fid=fid: [fid] if fid in [o.id for o in d.options] else None)
        toks = sorted(c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.token)
        seen.append(toks)
    assert [len(t) for t in seen] == [1, 2, 3, 3]  # (the fourth leaving finds every mode chosen)
    assert sorted(seen[-1]) == ["Fox", "Moonfolk", "Rat"]
    check(s)


def test_unidentified_hovership_gives_the_owner_of_the_exiled_card_a_manifest(cards):
    s = build(cards, ["Unidentified Hovership", "Shatter"], ["Grizzly Bears", "Forest", "Forest", "Forest"])
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, "p1", W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Unidentified Hovership").id)
    drive(s, lambda d: [bears.id] if bears.id in [o.id for o in d.options] else None)
    assert s.state.cards[bears.id].zone == "p2:exile"
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Shatter").id, targets=[card_named(s, "Unidentified Hovership").id])
    drive(s)
    down = [c for c in s.state.cards.values() if c.zone.endswith(":battlefield") and c.face_down]
    assert [c.controller for c in down] == ["p2"]
    check(s)


@pytest.mark.parametrize("opp_has_creature", [True, False])
def test_martyrs_bond_makes_opponents_sacrifice_a_permanent_sharing_a_type(cards, opp_has_creature):
    s = build(cards, ["Martyr's Bond", "Grizzly Bears", "Lightning Bolt"], ["Grizzly Bears", "Forest"])
    put(s, "Martyr's Bond")
    mine = put(s, "Grizzly Bears")
    forest = put(s, "Forest", "p2")
    theirs = put(s, "Grizzly Bears", "p2") if opp_has_creature else None
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[mine.id])
    drive(s)
    assert s.state.cards[mine.id].zone == "p1:graveyard"
    assert s.state.cards[forest.id].zone == "p2:battlefield"  # (a land shares nothing with a creature)
    if theirs is not None:
        assert s.state.cards[theirs.id].zone == "p2:graveyard"
    check(s)


def _birds(s):
    return [c for c in s.state.cards.values() if c.name == "Bird" and c.zone.endswith(":battlefield")]


def test_rendmaw_goads_a_bird_for_each_player_when_it_enters_or_a_multitype_card_is_played(cards):
    from app.rules import keyword_actions

    s = build(cards, ["Rendmaw, Creaking Nest", "Grizzly Bears", "Ornithopter", "Dryad Arbor"], [])
    mana(s, "p1", B=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Rendmaw, Creaking Nest").id)
    drive(s)
    birds = _birds(s)
    assert sorted(b.controller for b in birds) == ["p1", "p2"] and all(b.tapped for b in birds)
    assert all(keyword_actions.goaded_by(ch(s, b)) == {"p1"} for b in birds)
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)  # one card type: nothing
    drive(s)
    assert len(_birds(s)) == 2
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ornithopter").id)  # artifact creature
    drive(s)
    assert len(_birds(s)) == 4
    act(s, "p1", type="play_land", card_id=to_hand(s, "Dryad Arbor").id)  # land creature
    drive(s)
    assert len(_birds(s)) == 6
    check(s)


def test_oblivious_bookworm_manifest_counts_as_entering_face_down(cards):
    """708.2: a manifested card enters face down (701.40a), so the end-step loot does not discard."""
    s = build(cards, ["Oblivious Bookworm", "Grizzly Bears", "Reality Shift", "Forest", "Forest", "Forest"], [])
    put(s, "Oblivious Bookworm")
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Reality Shift").id, targets=[bears.id])
    drive(s)
    assert any(c.face_down and c.zone == "p1:battlefield" for c in s.state.cards.values())
    gy = lambda: len(s.state.zones["p1:graveyard"])  # noqa: E731
    before = gy()
    to_phase(s, "main1", turn=2)
    drive(s)
    assert gy() == before
    check(s)


@pytest.mark.parametrize("pick", [0, 1])
def test_lose_replacements_616_1_choice(cards, pick):
    """616.1: Stunning Reversal and Exquisite Archangel both replace the loss; the player picks one, the other stays for the next loss."""
    s = build(cards, ["Stunning Reversal", "Exquisite Archangel", "Forest"], [])
    put(s, "Exquisite Archangel")
    mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Stunning Reversal").id)
    drive(s)
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and len(d.options) == 2
    names = [o.label for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[pick].id])
    drive(s)
    assert s.state.rules.winner is None
    if names[pick] == "Stunning Reversal":
        assert s.state.players["p1"].life == 1
    else:
        assert s.state.players["p1"].life == 40
    check(s)
