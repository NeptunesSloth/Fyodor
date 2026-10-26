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

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import (
    attack,
    build,
    card_named,
    cast,
    ch,
    check,
    drive,
    life,
    mana,
    put,
    repository,
    settle,
    through_combat,
    to_hand,
    zone_of,
)


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


def test_bronze_bombshell_stolen_sacrifices_and_hurts_thief(cards):
    """603.8 state trigger: a player other than the owner controls it, so that player sacrifices it and takes 7."""
    s = build(cards, ["Bronze Bombshell"], ["Control Magic", "Island"])
    bomb = put(s, "Bronze Bombshell")
    assert s.state.cards[bomb.id].zone == "p1:battlefield"
    drive(s)
    assert s.state.cards[bomb.id].zone == "p1:battlefield" and s.state.players["p2"].life == 40  # (own controller: nothing)
    to_phase(s, "main1", turn=2)
    mana(s, "p2", U=2, C=2)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Control Magic", "p2").id, targets=[bomb.id])
    drive(s)
    assert s.state.cards[bomb.id].zone == "p1:graveyard"
    assert s.state.players["p2"].life == 33 and s.state.players["p1"].life == 40
    check(s)


@pytest.mark.parametrize("veil, counter", [(True, "Counterspell"), (False, "Counterspell"), (True, "Mana Leak"), (False, "Mana Leak")])
def test_autumns_veil_blue_spells_cant_counter_your_spells(cards, veil, counter):
    """101.2, 701.6: this turn your spells can't be countered by blue or black spells (hard and soft counters alike)."""
    s = build(cards, ["Autumn's Veil", "Grizzly Bears"], [counter])
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})
    if veil:
        mana(s, "p1", G=1)
        cast(s, "Autumn's Veil")
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    mana(s, "p2", U=2, C=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, counter, "p2").id, targets=[card_named(s, "Grizzly Bears").id])
    drive(s, lambda d: ["decline"] if any(o.id == "decline" for o in d.options) else None)
    assert zone_of(s, "Grizzly Bears") == ("p1:battlefield" if veil else "p1:graveyard")
    check(s)


def test_autumns_veil_blue_spells_cant_target_your_creatures(cards):
    """115.2: creatures you control can't be the targets of blue or black spells this turn; a red spell still can."""
    s = build(cards, ["Autumn's Veil", "Grizzly Bears"], ["Unsummon", "Lightning Bolt"])
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", G=1)
    cast(s, "Autumn's Veil")
    mana(s, "p2", U=1)
    with pytest.raises(ActionError):
        cast(s, "Unsummon", [bears.id], pid="p2")
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"


def test_meandering_towershell_returns_attacking_next_turn(cards):
    """603.7, 508.4: exiled as it attacks, it returns tapped and attacking as its controller's next declare attackers step begins."""
    s = build(cards, ["Meandering Towershell", "Grizzly Bears"], [])
    shell = put(s, "Meandering Towershell")
    attack(s, shell)
    drive(s)
    assert s.state.cards[shell.id].zone == "p1:exile"
    to_phase(s, "main1", turn=3)
    attack(s, put(s, "Grizzly Bears"))
    through_combat(s)
    assert card_named(s, "Meandering Towershell").zone == "p1:battlefield" and card_named(s, "Meandering Towershell").tapped
    assert life(s, "p2") == 40 - 2 - 5  # (the Bears and the returned Turtle both dealt combat damage)
    check(s)


def _nissa(cards, graveyard=()):
    s = build(cards, ["Nissa of Shadowed Boughs", "Serra Angel", "Elvish Mystic", "Forest", "Forest", "Forest"], [])
    nissa = put(s, "Nissa of Shadowed Boughs")
    act(s, "p1", type="counter", card_ids=[nissa.id], kind="loyalty", delta=5 - s.state.cards[nissa.id].counters.get("loyalty", 0))
    for n in graveyard:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    return s, nissa


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_nissa_shadowed_boughs_plus_one_may_animate_the_land(cards, answer):
    """205.1b, 608.2d: untap the land; only if you choose it becomes a 3/3 haste menace Elemental creature land until end of turn."""
    s, nissa = _nissa(cards)
    forest = put(s, "Forest")
    act(s, "p1", type="tap", card_ids=[forest.id], tapped=True)
    act(s, "p1", type="activate_ability", card_id=nissa.id, ability=1)
    drive(s, lambda d: [forest.id] if forest.id in [o.id for o in d.options] else [answer] if answer in [o.id for o in d.options] else None)
    c = s.state.cards[forest.id]
    assert not c.tapped
    ch_ = ch(s, c)
    assert ch_.is_creature == (answer == "yes") and ch_.is_land
    assert (ch_.pt == (3, 3) and "menace" in ch_.keywords) if answer == "yes" else True
    check(s)


@pytest.mark.parametrize("hand_or_yard, name, ok", [("graveyard", "Serra Angel", False), ("graveyard", "Elvish Mystic", True), ("hand", "Elvish Mystic", True)])
def test_nissa_shadowed_boughs_minus_five_mana_value_up_to_lands(cards, hand_or_yard, name, ok):
    """608.2c: a creature card (hand or graveyard) with mana value at most your lands (2 here) enters with two +1/+1 counters."""
    s, nissa = _nissa(cards, graveyard=[name] if hand_or_yard == "graveyard" else ())
    if hand_or_yard == "hand":
        to_hand(s, name)
    put(s, "Forest")
    put(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=nissa.id, ability=2)
    drive(s, lambda d: [o.id for o in d.options if o.id != "no"][:1])
    c = card_named(s, name)
    if ok:
        assert c.zone == "p1:battlefield" and c.counters.get("+1/+1") == 2
    else:
        assert c.zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("full_party", [True, False])
def test_linvala_shield_of_sea_gate_full_party_locks_down_a_permanent(cards, full_party):
    """700.8, 611.2a: with a full party at the beginning of combat the chosen opponent permanent can't attack, block or activate until her controller's next turn."""
    party = ["Shrine Keeper", "Krovikan Scoundrel", "Oreskos Swiftclaw"][: 3 if full_party else 2]
    s = build(cards, ["Linvala, Shield of Sea Gate", *party], ["Grizzly Bears"])
    for n in ["Linvala, Shield of Sea Gate", *party]:
        put(s, n)
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="pass_priority")
    drive(s)
    imposed = ch(s, bears).imposed
    assert ("cant_attack_or_block" in imposed and "cant_activate" in imposed) == full_party
    check(s)


@pytest.mark.parametrize("mode", ["hexproof", "indestructible"])
def test_linvala_sacrifice_chooses_hexproof_or_indestructible(cards, mode):
    """700.2: Sacrifice Linvala, choose one of the two keywords; your creatures gain it until end of turn."""
    s = build(cards, ["Linvala, Shield of Sea Gate", "Shrine Keeper"], [])
    linvala, keeper = put(s, "Linvala, Shield of Sea Gate"), put(s, "Shrine Keeper")
    act(s, "p1", type="activate_ability", card_id=linvala.id, ability=2)
    drive(s, lambda d: [o.id for o in d.options if mode in o.label.lower()][:1] or None)
    assert s.state.cards[linvala.id].zone == "p1:graveyard"
    assert mode in ch(s, s.state.cards[keeper.id]).keywords
    check(s)


def test_weeping_angel_stops_being_a_creature_when_an_opponent_casts_a_creature(cards):
    """205.1b, 611.2: an opponent's creature spell makes it a non-creature (an artifact) until end of turn; a noncreature spell does not."""
    s = build(cards, ["Weeping Angel"], ["Grizzly Bears", "Lightning Bolt"])
    angel = put(s, "Weeping Angel")
    to_phase(s, "main1", turn=2)
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=["p1"])
    settle(s)
    assert ch(s, angel).is_creature
    mana(s, "p2", G=1, C=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Grizzly Bears", "p2").id)
    settle(s)
    assert not ch(s, angel).is_creature and "Artifact" in ch(s, angel).types
    check(s)


@pytest.mark.parametrize("blocked", [True, False])
def test_weeping_angel_combat_damage_to_a_creature_is_prevented_and_it_is_shuffled_away(cards, blocked):
    """615.1, 701.24: damage it would deal to a creature is prevented and that creature's owner shuffles it into their library; a player is hurt as usual."""
    s = build(cards, ["Weeping Angel"], ["Grizzly Bears", "Forest"])
    angel = put(s, "Weeping Angel")
    bears = put(s, "Grizzly Bears", "p2")
    attack(s, angel)
    through_combat(s, [(bears, angel)] if blocked else None)
    if blocked:
        assert s.state.cards[bears.id].zone == "p2:library" and life(s, "p2") == 40
    else:
        assert s.state.cards[bears.id].zone == "p2:battlefield" and life(s, "p2") < 40
    check(s)
