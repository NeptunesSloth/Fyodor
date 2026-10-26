"""Wave 110E: 903.9b audit. A commander that would be put into its owner's hand or library may go to the command zone instead, wherever a wave 110 primitive moves it."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave110c_lose import EXTRA as L_EXTRA
from tests.test_rules_wave110c_sin import EXTRA as SIN_EXTRA
from tests.test_rules_wave110h_s9 import EXTRA as H_EXTRA
from tests.test_rules_wave110h_s9 import _glimpse
from tests.test_rules_wave110i_more import EXTRA as I_EXTRA
from tests.wave9c_kit import build, card_named
from tests.wave110c_kit import cast, check, life, make_db, mana, put, to_hand
from tests.wave110j_kit import ability
from tests.wave110k_kit import EXTRA as K_EXTRA
from tests.wave110k_kit import cast_on

WANT = {"This Is How It Ends", "Skyblade's Boon", "Glimpse of Tomorrow", "Runeclaw Bear", "Puppet Master", "Lightning Bolt", "Grizzly Bears"}

EXTRA = [*SIN_EXTRA, *L_EXTRA, *[c for c in (*H_EXTRA, *I_EXTRA, *K_EXTRA) if c["name"] in WANT]]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def build_with(cards, commander, mine=()):
    """Alice's commander is ``commander`` (a real commander: replay and save/load know it); Bob's is Atraxa."""
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=deck(cards, commander, [*((1, n) for n in mine), (9, "Forest")])),
                                     PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")]))], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def zone(s, c):
    return s.state.cards[c.id].zone


def play(s, ans, limit=80):
    """Settle everything: the 903.9b question gets ``ans``, the 903.9a one ("no"), everything else its first option; returns the 903.9b prompts seen."""
    asked = []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            if "903.9b" in d.prompt:
                asked.append(d.prompt)
            pick = ans if "903.9b" in d.prompt else "no" if d.prompt.endswith("command zone?") else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:library")])
def test_sin_dies_trigger_asks_before_shuffling_a_commander_in(cards, ans, where):
    """shuffle_dead110c: Sin (the commander) shuffled into its owner's library by its own dies trigger (903.9b, 701.24)."""
    s = build_with(cards, "Sin, Unending Cataclysm", ["Plain Bear", "Doom Blade"])
    put(s, "Plain Bear")
    sin = to_hand(s, "Sin, Unending Cataclysm")
    mana(s, G=1, U=1, C=5)
    act(s, "p1", type="cast_spell", card_id=sin.id)
    play(s, "no")
    blade = to_hand(s, "Doom Blade")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=blade.id, targets=[sin.id])
    assert len(play(s, ans)) == 1 and zone(s, sin) == where
    check(s)


def test_glimpse_asks_before_shuffling_the_commander_in(cards):
    """glimpse110h: Krenko is a permanent its owner owns; 903.9b is asked (first option: command zone) before the shuffle, so it is never revealed."""
    s = _glimpse(cards, ["Runeclaw Bear"], ["Krenko, Mob Boss", "Runeclaw Bear"])
    krenko = card_named(s, "Krenko, Mob Boss")
    assert zone(s, krenko) == "p1:command"
    check(s)


@pytest.mark.parametrize("ans,where,paid", [("yes", "p1:command", False), ("no", "p1:hand", True)])
def test_puppet_master_asks_before_returning_a_commander(cards, ans, where, paid):
    """bounce_gate110i: Krenko dies enchanted by Puppet Master (903.9a declined); returning it to hand asks 903.9b first. In the command zone it
    was not returned to hand, so the {U}{U}{U} payment is not offered (Puppet Master stays in the graveyard)."""
    s = build(cards, ["Puppet Master", "Lightning Bolt"], [])
    krenko = put(s, "Krenko, Mob Boss")
    mana(s, U=3)
    master = cast(s, "Puppet Master", [krenko.id])
    play(s, ans)
    mana(s, R=1, U=3)
    cast(s, "Lightning Bolt", [krenko.id])
    assert len(play(s, ans)) == 1 and zone(s, krenko) == where
    assert zone(s, master) == ("p1:hand" if paid else "p1:graveyard")
    check(s)


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:hand")])
def test_skyblade_boon_asks_before_returning_a_commander_to_hand(cards, ans, where):
    """return_self_hand110k: the Aura (the commander) returned from the battlefield or graveyard by its own ability asks 903.9b first."""
    s = build_with(cards, "Skyblade's Boon", ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    boon = cast_on(s, "Skyblade's Boon", bears)
    mana(s, W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=boon.id, ability=ability(s, boon, "{2}{W}"))
    assert len(play(s, ans)) == 1 and zone(s, boon) == where
    check(s)


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:hand")])
def test_lich_mirror_asks_before_shuffling_the_commander_in(cards, ans, where):
    """mirror_in110c (Lich's Mirror, 614.1a): the lose-the-game replacement shuffles Krenko in only after its owner answered 903.9b; in the command
    zone it cannot be drawn (the unshuffled library of the scenario hands it back in the seven cards otherwise)."""
    s = build(cards, ["Lich's Mirror"])
    put(s, "Lich's Mirror")
    krenko = put(s, "Krenko, Mob Boss")
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")
    assert len(play(s, ans)) == 1 and life(s) == 20 and len(s.state.zones["p1:hand"]) == 7
    assert (zone(s, krenko) == "p1:command") == (ans == "yes")
    check(s)


@pytest.mark.parametrize("ans,where", [("yes", "p2:command"), ("no", "p2:library")])
def test_this_is_how_it_ends_asks_before_shuffling_a_chosen_commander(cards, ans, where):
    """shuffle_other110k (701.55a): the owner picks "shuffle another creature" and chooses their commander, Atraxa: 903.9b is asked before the shuffle."""
    s = build(cards, ["This Is How It Ends"], ["Grizzly Bears"])
    victim, atraxa = put(s, "Grizzly Bears", "p2"), put(s, "Atraxa, Praetors' Voice", "p2")
    c = to_hand(s, "This Is How It Ends")
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[victim.id])
    picks = ["b", atraxa.id]
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        asked += ["903.9b" in d.prompt]
        pick = ans if "903.9b" in d.prompt else "no" if d.prompt.endswith("command zone?") else picks.pop(0) if picks else d.options[0].id
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    assert asked.count(True) == 1 and zone(s, atraxa) == where and zone(s, victim) == "p2:library"
    check(s)
