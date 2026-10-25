"""Wave 100B: "if you do" riders (CR 2026-09-25), real Oracle text (tests/fixtures/wave100b_cards.json, from data/cards.sqlite). Every
scenario checks the replay and a save and a load.

* Act of Authority - "you may exile target artifact or enchantment. If you do, its controller gains control of this enchantment." (608.2h:
  the controller the exiled permanent last had; no duration, 611.2a).
* Assault Suit - "you may have that player gain control of equipped creature until end of turn. If you do, untap it." (603.5, 118.12).
* Summoner's Sending - "Put a +1/+1 counter on it if the exiled card's mana value is 4 or greater." (the card in exile, 400.7j).
* Check for Traps - "If an instant card or a card with flash is exiled this way, they lose 1 life. Otherwise, you lose 1 life."
* Ravenous Rotbelly - "you may sacrifice up to three Zombies. When you sacrifice one or more Zombies this way, each opponent sacrifices that
  many creatures of their choice." (603.12: the reflexive ability, "that many": how many were sacrificed).
* Azra Bladeseeker - "each player on your team may discard a card, then each player who discarded a card this way draws a card." (102.4).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, stops, to_phase
from tests.wave9c_kit import check, life, mana, put, to_hand
from tests.wave52a_kit import build_n, put_all
from tests.wave100b_kit import hand_size, open_repo, run, tokens, zone

ACT, SUIT, SENDING, TRAPS, ROTBELLY, AZRA = ("Act of Authority", "Assault Suit", "Summoner's Sending", "Check for Traps", "Ravenous Rotbelly",
                                            "Azra Bladeseeker")
BEARS, GIANT, ZOMBIE, VIPER, BOLT, GROWTH = "Grizzly Bears", "Hill Giant", "Dregscape Zombie", "Ambush Viper", "Lightning Bolt", "Rampant Growth"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [ACT, SUIT, SENDING, TRAPS, ROTBELLY, AZRA])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def answer(*words):
    """Answer with the first option whose id or label contains one of these words (else the default)."""
    def pick(d):
        for w in words:
            ids = [o.id for o in d.options if o.id == w or w.lower() in (o.label or "").lower()]
            if ids:
                return ids[: max(1, d.min_choices)]
        return None
    return pick


def ids(*cs):
    want = {c.id for c in cs}

    def pick(d):
        found = [o.id for o in d.options if o.id in want or getattr(o, "card_id", None) in want]
        return found or None
    return pick


# -- Act of Authority -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("whose", ["theirs", "mine"])
def test_act_of_authority_gives_itself_to_the_exiled_permanents_controller(cards, whose):
    s = build_n(cards, [ACT, "Sol Ring"], ["Sol Ring"])
    act_card = put(s, ACT)
    ring = put(s, "Sol Ring", "p2" if whose == "theirs" else "p1")
    stops(s)
    to_phase(s, "upkeep", turn=3)
    run(s, ids(ring))
    assert zone(s, ring).endswith(":exile")
    assert s.state.cards[act_card.id].controller == ("p2" if whose == "theirs" else "p1")
    check(s)


def test_act_of_authority_declined_keeps_it(cards):
    s = build_n(cards, [ACT], ["Sol Ring"])
    act_card = put(s, ACT)
    ring = put(s, "Sol Ring", "p2")
    stops(s)
    to_phase(s, "upkeep", turn=3)
    run(s, answer("no", "decline", "don't"))
    assert zone(s, ring) == "p2:battlefield" and s.state.cards[act_card.id].controller == "p1"
    check(s)


# -- Assault Suit ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("accept", [True, False])
def test_assault_suit_lends_the_equipped_creature_untapped(cards, accept):
    s = build_n(cards, [SUIT, GIANT])
    suit = put(s, SUIT)
    giant = put(s, GIANT)
    act(s, "p1", type="attach", card_ids=[suit.id], to=giant.id)
    act(s, "p1", type="tap", card_ids=[giant.id])
    stops(s)
    to_phase(s, "upkeep", turn=2)
    run(s, answer("yes") if accept else answer("no"))
    g = s.state.cards[giant.id]
    assert g.controller == ("p2" if accept else "p1") and g.tapped is (not accept)
    if accept:  # until end of turn: back to Alice on her own turn
        to_phase(s, "main1", turn=3)
        assert s.state.cards[giant.id].controller == "p1"
    check(s)


# -- Summoner's Sending ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,counter", [(GIANT, 1), (BEARS, 0)])
def test_summoners_sending_counter_for_a_big_exiled_card(cards, name, counter):
    s = build_n(cards, [SENDING], [GIANT, BEARS])
    put(s, SENDING)
    victim = to_hand(s, name, "p2")
    act(s, "p2", type="move", card_ids=[victim.id], to={"zone": "graveyard"})
    stops(s)
    to_phase(s, "end", turn=1)
    run(s, ids(victim))
    assert zone(s, victim) == "p2:exile"
    spirits = tokens(s, "p1", "Spirit")
    assert len(spirits) == 1 and spirits[0].counters.get("+1/+1", 0) == counter
    check(s)


# -- Check for Traps ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,bob_loses", [(BOLT, True), (VIPER, True), (GROWTH, False)])
def test_check_for_traps_instant_or_flash_costs_them_a_life(cards, name, bob_loses):
    s = build_n(cards, [TRAPS], [name])
    pick = to_hand(s, name, "p2")
    spell = to_hand(s, TRAPS)
    mana(s, B=1, C=1)
    mine, theirs = life(s), life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    run(s, ids(pick))
    assert zone(s, pick) == "p2:exile"
    assert (life(s, "p2"), life(s)) == ((theirs - 1, mine) if bob_loses else (theirs, mine - 1))
    check(s)


# -- Ravenous Rotbelly ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("sacrificed", [0, 2])
def test_ravenous_rotbelly_each_opponent_sacrifices_that_many(cards, sacrificed):
    s = build_n(cards, [ROTBELLY, (2, ZOMBIE)], [BEARS, GIANT, VIPER])
    both = put_all(s, ZOMBIE)
    zombies = both if sacrificed else []
    theirs = [put(s, n, "p2") for n in (BEARS, GIANT, VIPER)]
    rot = to_hand(s, ROTBELLY)
    mana(s, B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=rot.id)
    chosen = {z.id for z in zombies}

    def pick(d):
        opts = [o.id for o in d.options]
        if d.player == "p1" and chosen & ({o.id for o in d.options} | {getattr(o, "card_id", None) for o in d.options}):
            return [o.id for o in d.options if o.id in chosen or getattr(o, "card_id", None) in chosen][: max(d.min_choices, len(chosen))]
        if d.player == "p1" and not sacrificed:
            return ["no"] if "no" in opts else [o.id for o in d.options if "done" in o.id.lower() or "none" in (o.label or "").lower()][:1] or None
        return None
    run(s, pick)
    assert zone(s, rot) == "p1:battlefield"
    assert sum(1 for z in zombies if zone(s, z) == "p1:graveyard") == sacrificed
    assert sum(1 for c in theirs if zone(s, c) == "p2:graveyard") == sacrificed
    check(s)


# -- Azra Bladeseeker -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("rummage", [True, False])
def test_azra_bladeseeker_discard_then_draw(cards, rummage):
    s = build_n(cards, [AZRA, BEARS])
    bears = to_hand(s, BEARS)
    azra = to_hand(s, AZRA)
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=azra.id)
    before = hand_size(s, "p1")
    run(s, (lambda d: [o.id for o in d.options if o.id == "pay" or getattr(o, "card_id", None) == bears.id][:1] or None) if rummage else answer("decline"))
    assert zone(s, bears) == ("p1:graveyard" if rummage else "p1:hand")
    assert hand_size(s, "p1") == before  # (one discarded and one drawn, or neither)
    check(s)


# -- Psychic Pickpocket / Obscura Interceptor (701.50f: it connives, so the reflexive ability triggers) ---------------------------------
PICKPOCKET, INTERCEPTOR, NEZUMI = "Psychic Pickpocket", "Obscura Interceptor", "Nezumi Graverobber // Nighteyes the Desecrator"


@pytest.mark.parametrize("name", [PICKPOCKET, INTERCEPTOR, NEZUMI])
def test_more_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_psychic_pickpocket_connives_then_returns_a_permanent(cards):
    s = build_n(cards, [PICKPOCKET, BEARS], [GIANT])
    giant = put(s, GIANT, "p2")
    bears = to_hand(s, BEARS)
    pick = to_hand(s, PICKPOCKET)
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=pick.id)
    run(s, ids(bears, giant))
    assert zone(s, giant) == "p2:hand"  # the reflexive ability's target, chosen after the connive
    assert zone(s, bears) == "p1:graveyard" and s.state.cards[pick.id].counters.get("+1/+1", 0) == 1  # (a nonland card discarded)
    check(s)


def test_psychic_pickpocket_reflexive_even_if_it_left(cards):
    """701.50b/f: it still connives (by last known information) after it left the battlefield, and the reflexive ability triggers."""
    s = build_n(cards, [PICKPOCKET, BEARS], [GIANT])
    giant = put(s, GIANT, "p2")
    to_hand(s, BEARS)
    pick = to_hand(s, PICKPOCKET)
    mana(s, U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=pick.id)
    for _ in range(10):  # the spell resolves; with the enters trigger on the stack the creature leaves
        if s.state.cards[pick.id].zone == "p1:battlefield" and s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="move", card_ids=[pick.id], to={"zone": "graveyard"})
    run(s, ids(giant))
    assert zone(s, giant) == "p2:hand"
    check(s)


def test_obscura_interceptor_returns_a_spell(cards):
    s = build_n(cards, [INTERCEPTOR, BEARS], [GIANT])
    stops(s)
    to_phase(s, "main1", turn=2)
    giant = to_hand(s, GIANT, "p2")
    mana(s, "p2", R=1, C=3)
    act(s, "p2", type="cast_spell", card_id=giant.id)
    to_hand(s, BEARS)
    inter = to_hand(s, INTERCEPTOR)
    mana(s, W=1, U=1, B=1, C=1)
    if s.state.rules.priority == "p2":
        act(s, "p2", type="pass_priority")
    act(s, "p1", type="cast_spell", card_id=inter.id)  # (flash)
    run(s, ids(giant))
    assert zone(s, giant) == "p2:hand" and zone(s, inter) == "p1:battlefield"
    check(s)


# -- Nezumi Graverobber -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("last_card", [True, False])
def test_nezumi_graverobber_flips_when_that_graveyard_is_empty(cards, last_card):
    s = build_n(cards, [NEZUMI], [BEARS, GIANT])
    nezumi = put(s, NEZUMI)
    victims = [to_hand(s, n, "p2") for n in ((BEARS,) if last_card else (BEARS, GIANT))]
    for v in victims:
        act(s, "p2", type="move", card_ids=[v.id], to={"zone": "graveyard"})
    mana(s, B=1, C=1)
    activate(s, "p1", s.state.cards[nezumi.id], "Exile target card", targets=[victims[0].id])
    run(s)
    assert zone(s, victims[0]) == "p2:exile"
    assert s.state.cards[nezumi.id].flipped is last_card
    check(s)


# -- Truce / Temporary Truce (101.4: each chooses in turn order, then the draws; 2 life for each card fewer than two drawn) ----------------
@pytest.mark.parametrize("name", ["Truce", "Temporary Truce"])
def test_truce_each_player_draws_up_to_two_and_gains_for_the_rest(cards, name):
    s = build_n(cards, [name])
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
    spell = to_hand(s, name)
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    asked = []

    def pick(d):
        asked.append(d.player)
        return ["0"] if d.player == "p1" else ["2"]
    mine, theirs = hand_size(s, "p1"), hand_size(s, "p2")  # (the spell is on the stack)
    lives = life(s), life(s, "p2")
    run(s, pick)
    assert asked == ["p1", "p2"]  # (APNAP: the caster first)
    assert (hand_size(s, "p1"), hand_size(s, "p2")) == (mine, theirs + 2)
    assert (life(s), life(s, "p2")) == (lives[0] + 4, lives[1])
    check(s)


def test_truce_a_short_library_draws_fewer_and_gains_for_them(cards):
    s = build_n(cards, ["Truce"])
    for c in [c for c in s.state.cards.values() if c.zone == "p2:library"][1:]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "exile"})
    spell = to_hand(s, "Truce")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    theirs, their_life = hand_size(s, "p2"), life(s, "p2")
    run(s, lambda d: ["1"] if d.player == "p1" else ["2"])
    assert hand_size(s, "p2") == theirs + 1 and life(s, "p2") == their_life + 2  # one card drawn: one less than two
    check(s)


# -- Flood of Tears ---------------------------------------------------------------------------------------------------------------------
FLOOD, SLUMBER = "Flood of Tears", "Faerie Slumber Party"


@pytest.mark.parametrize("name", [FLOOD, SLUMBER])
def test_bounce_riders_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("mine,offer", [(4, True), (3, False)])
def test_flood_of_tears_four_of_yours_lets_you_put_a_permanent(cards, mine, offer):
    s = build_n(cards, [FLOOD, BEARS, GIANT, "Sol Ring", ZOMBIE, VIPER], [BEARS, GIANT])
    ours = [put(s, n) for n in (BEARS, GIANT, "Sol Ring", ZOMBIE)[:mine]]
    theirs = [put(s, n, "p2") for n in (BEARS, GIANT)]  # (an opponent's permanents returned don't count)
    viper = to_hand(s, VIPER)
    spell = to_hand(s, FLOOD)
    mana(s, U=2, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    asked = []

    def pick(d):
        asked.append(d.prompt)
        found = [o.id for o in d.options if getattr(o, "card_id", None) == viper.id or o.id == viper.id]
        return found or None
    run(s, pick)
    assert all(zone(s, c) == "p1:hand" for c in ours) and all(zone(s, c) == "p2:hand" for c in theirs)
    assert zone(s, viper) == ("p1:battlefield" if offer else "p1:hand")
    assert bool(asked) is offer
    check(s)


# -- Faerie Slumber Party -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("case,faeries", [("theirs", 2), ("none", 0), ("borrowed", 2)])
def test_faerie_slumber_party_two_faeries_per_opponent_who_lost_a_creature(cards, case, faeries):
    s = build_n(cards, [SLUMBER, BEARS], [GIANT])
    put(s, BEARS)  # (Alice's own creature: she isn't an opponent)
    if case == "theirs":
        put(s, GIANT, "p2")
    if case == "borrowed":  # Bob controls Alice's creature: as it last existed, Bob controlled it (608.2h); it goes to Alice's hand
        lent = put(s, BEARS)
        act(s, "p2", type="set_controller", card_ids=[lent.id], player="p2")
    spell = to_hand(s, SLUMBER)
    mana(s, U=2, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    run(s)
    made = tokens(s, "p1", "Faerie")
    assert len(made) == faeries and not tokens(s, "p1", BEARS)
    check(s)
