"""Wave 110E: 903.9b audit. A commander that would be put into its owner's hand or library may go to the command zone instead, wherever a wave 110 primitive moves it."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import until
from tests.test_rules_wave110c_analyst import EXTRA as ANALYST_EXTRA
from tests.test_rules_wave110c_lose import EXTRA as L_EXTRA
from tests.test_rules_wave110c_neera import EXTRA as NEERA_EXTRA
from tests.test_rules_wave110c_omnath import EXTRA as OMNATH_EXTRA
from tests.test_rules_wave110c_prodder import EXTRA as PRODDER_EXTRA
from tests.test_rules_wave110c_sin import EXTRA as SIN_EXTRA
from tests.test_rules_wave110f_s5 import EXTRA as F_EXTRA
from tests.test_rules_wave110g_s11 import EXTRA as G_EXTRA
from tests.test_rules_wave110h_s9 import EXTRA as H_EXTRA
from tests.test_rules_wave110h_s9 import _glimpse
from tests.test_rules_wave110i_more import EXTRA as I_EXTRA
from tests.test_rules_wave110n_sword import EXTRA as SWORD_EXTRA
from tests.wave9c_kit import build, card_named
from tests.wave110b_kit import EXTRA as B_EXTRA
from tests.wave110c_kit import cast, check, life, make_db, mana, put, to_hand
from tests.wave110j_kit import ability
from tests.wave110k_kit import EXTRA as K_EXTRA
from tests.wave110k_kit import cast_on

WANT = {"This Is How It Ends", "Skyblade's Boon", "Glimpse of Tomorrow", "Runeclaw Bear", "Puppet Master", "Lightning Bolt", "Grizzly Bears"}

EXTRA = [*SIN_EXTRA, *L_EXTRA, *NEERA_EXTRA, *[c for c in G_EXTRA if c["name"].startswith("J")], *[c for c in F_EXTRA if c["name"] in ("Remove Enchantments", "Pacifism", "Glorious Anthem")], *[c for c in B_EXTRA if c["name"] in ("Soulfire Grand Master", "Staggershock")], *OMNATH_EXTRA[:2], *PRODDER_EXTRA[:1], *ANALYST_EXTRA, *SWORD_EXTRA, *[c for c in (*H_EXTRA, *I_EXTRA, *K_EXTRA) if c["name"] in WANT]]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def build_with(cards, commander, mine=(), theirs=()):
    """Alice's commander is ``commander`` (a real commander: replay and save/load know it); Bob's is Atraxa."""
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=deck(cards, commander, [*((1, n) for n in mine), (9, "Forest")])),
                                     PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((2, n) for n in theirs), (10, "Island")]))], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def zone(s, c):
    return s.state.cards[c.id].zone


def play(s, ans, limit=80, prefer=()):
    """Settle everything: the 903.9b question gets ``ans``, the 903.9a one ("no"), everything else its first option; returns the 903.9b prompts seen."""
    asked = []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            if "903.9b" in d.prompt:
                asked.append(d.prompt)
            pick = ans if "903.9b" in d.prompt else "no" if d.prompt.endswith("command zone?") else next((o.id for o in d.options if o.id in prefer), None)
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


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:library")])
def test_neera_bottoms_a_commander_spell_after_903_9b(cards, ans, where):
    """spell_bottom110c (Neera, 903.9b): the commander spell Neera puts on the bottom of its owner's library is asked first; either way it is not countered or
    resolved, and the rest of Neera's ability still runs (a free nonland card is cast)."""
    s = build_with(cards, "Lightning Bolt", ["Neera, Wild Mage", "Grizzly Bears"])
    put(s, "Neera, Wild Mage")
    bolt = card_named(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    assert len(play(s, ans)) == 1 and zone(s, bolt) == where and life(s, "p2") == 40
    check(s)


def to_top(s, c, who="p1"):
    """Move ``c`` (the commander) from the command zone to the top of its owner's library."""
    act(s, "p1", type="move", card_ids=[c.id], to={"player": who, "zone": "library"}, position="top")
    assert zone(s, c) == f"{who}:library"


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:hand")])
def test_sword_point_diplomacy_asks_before_a_revealed_commander_goes_to_hand(cards, ans, where):
    """sword_hand110n (118.12): the revealed commander would go to hand because no opponent paid; its owner is asked 903.9b, and the other two cards
    still reach the hand."""
    s = build_with(cards, "Krenko, Mob Boss", ["Sword-Point Diplomacy"])
    krenko = card_named(s, "Krenko, Mob Boss")
    to_top(s, krenko)
    sword = to_hand(s, "Sword-Point Diplomacy")
    top3 = list(s.state.zones["p1:library"][:3])
    hand0 = len(s.state.zones["p1:hand"])
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=sword.id)
    assert len(play(s, ans, prefer=("decline",))) == 1 and zone(s, krenko) == where
    assert all(zone(s, s.state.cards[c]) == "p1:hand" for c in top3[1:])
    assert len(s.state.zones["p1:hand"]) == hand0 - 1 + 2 + (where == "p1:hand")
    check(s)


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:hand")])
def test_paranormal_analyst_asks_before_the_binned_commander_goes_to_hand(cards, ans, where):
    """dread_return110c (701.62a): the commander manifest dread put into the graveyard returns to hand only after its owner answered 903.9b (903.9a declined first)."""
    s = build_with(cards, "Krenko, Mob Boss", ["Paranormal Analyst", "Dissection Tools"])
    krenko = card_named(s, "Krenko, Mob Boss")
    to_top(s, krenko)
    put(s, "Paranormal Analyst")
    tools = to_hand(s, "Dissection Tools")
    mana(s, C=5)
    act(s, "p1", type="cast_spell", card_id=tools.id)
    for _ in range(8):  # the Equipment's trigger resolves, then the manifest dread choice opens
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[1].id])  # manifest the other card: the commander is binned
    assert any(c.face_down and c.zone == "p1:battlefield" for c in s.state.cards.values()) and zone(s, krenko) == "p1:graveyard"
    assert len(play(s, ans)) == 1 and zone(s, krenko) == where
    check(s)


def next_turn_top(s, c, stop, upkeep=False):
    """During turn 2 put a Forest and ``c`` (a commander) on top of Alice's library (``c`` first from the top for an upkeep trigger, else the draw takes
    the Forest and ``c`` is next); run to ``stop`` in her turn 3."""
    forest = next(f for f in s.state.cards.values() if f.name == "Forest" and f.zone == "p1:library")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main2")
    for x in ((forest, c) if upkeep else (c, forest)):
        act(s, "p1", type="move", card_ids=[x.id], to={"player": "p1", "zone": "library"}, position="top")
    until(s, lambda s: stop(s) and s.state.turn.number == 3)


@pytest.mark.parametrize("commander,reveal,mono", [("Triple Mono", "reveal", 3), ("Triple Mono", "hand", 0), ("Krenko, Mob Boss", None, 0)])
@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:hand")])
def test_omnath_asks_before_a_commander_goes_to_hand(cards, commander, reveal, mono, ans, where):
    """omnath110c (701.20a, 106.1): the top card, a commander, goes to hand either way; its owner is asked 903.9b, and revealing it still adds the three mana."""
    s = build_with(cards, commander, ["Omnath, Locus of All"])
    put(s, "Omnath, Locus of All")
    c = card_named(s, commander)
    next_turn_top(s, c, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    if reveal:
        assert {o.id for o in d.options} == {"reveal", "hand"}
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[reveal])
    assert len(play(s, ans, prefer=("B",))) == 1 and zone(s, c) == where
    p1 = s.state.players["p1"]
    assert sum(u.sym == "B" for u in p1.mana_units) + p1.mana.get("B", 0) == mono
    check(s)


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:hand")])
def test_sin_prodder_asks_before_a_commander_goes_to_hand(cards, ans, where):
    """prodder110c (701.20a, 608.2d): no opponent has the revealed commander binned, so it goes to hand, after its owner's 903.9b answer; no damage is dealt."""
    s = build_with(cards, "Krenko, Mob Boss", ["Sin Prodder"])
    put(s, "Sin Prodder")
    krenko = card_named(s, "Krenko, Mob Boss")
    next_turn_top(s, krenko, lambda s: s.state.rules.decision is not None, upkeep=True)
    assert s.state.rules.decision.player == "p2"
    assert len(play(s, ans, prefer=("no",))) == 1 and zone(s, krenko) == where and life(s, "p2") == 40
    check(s)


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:hand")])
def test_soulfire_hand_replacement_asks_before_a_commander_spell_returns(cards, ans, where):
    """rebound_hand110b (614.1a, 616.1): the commander Staggershock, cast from hand with Soulfire's replacement, is put into hand instead of rebounding: 903.9b is
    asked then; in the command zone it is not rebounded either (it never was exiled), and its damage was dealt."""
    s = build_with(cards, "Staggershock", ["Soulfire Grand Master"])
    master = put(s, "Soulfire Grand Master")
    shock = card_named(s, "Staggershock")
    act(s, "p1", type="move", card_ids=[shock.id], to={"player": "p1", "zone": "hand"})
    mana(s, U=1, R=1, C=2)
    act(s, "p1", type="activate_ability", card_id=master.id, ability=2)
    play(s, "no")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=["p2"])
    assert len(play(s, ans, prefer=("hand",))) == 1 and zone(s, shock) == where and life(s, "p2") == 38
    check(s)


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:hand")])
def test_remove_enchantments_asks_before_a_commander_enchantment_returns(cards, ans, where):
    """remove_enchantments110f (608.2c, 903.9b): the commander Anthem is among the enchantments returned to hand; the owner is asked, and the next
    instruction (destroying Bob's Aura on my Bear) still happens."""
    s = build_with(cards, "Glorious Anthem", ["Remove Enchantments", "Grizzly Bears"], ["Pacifism"])
    anthem = put(s, "Glorious Anthem")
    bear, aura = put(s, "Grizzly Bears"), put(s, "Pacifism", "p2")
    act(s, "p2", type="attach", card_ids=[aura.id], to=bear.id)
    spell = to_hand(s, "Remove Enchantments")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    assert len(play(s, ans)) == 1 and zone(s, anthem) == where and zone(s, aura) == "p2:graveyard"
    check(s)


@pytest.mark.parametrize("ans,where", [("yes", "p1:command"), ("no", "p1:library")])
def test_jotun_grunt_cost_asks_before_a_commander_goes_to_the_bottom(cards, ans, where):
    """gy_pairs110g (702.24a, 903.9b): the pair paid for the upkeep cost includes the commander from the graveyard; its owner is asked, and the cost still counts as
    paid (the Giant is not sacrificed)."""
    s = build_with(cards, "Krenko, Mob Boss", ["J\u00f6tun Grunt", *["Forest"] * 20], ["Island"] * 20)
    grunt = put(s, "J\u00f6tun Grunt")
    krenko = card_named(s, "Krenko, Mob Boss")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[krenko.id, forest.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="pass_priority")
    play(s, "no")  # (903.9a, asked as the game goes on: declined, Krenko stays in the graveyard)
    assert zone(s, krenko) == "p1:graveyard"
    until(s, lambda s: s.state.rules.decision is not None and s.state.turn.number == 3)
    assert len(play(s, ans, prefer=("pay",))) == 1 and zone(s, krenko) == where and zone(s, grunt) == "p1:battlefield"
    assert zone(s, forest) == "p1:library"
    check(s)
