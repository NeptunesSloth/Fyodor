"""Wave 100J (2): more counter lines (app/rules/counters100j.py), on the real Oracle text of tests/fixtures/wave100j_cards.json."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_wave21r_review import three
from tests.test_rules_wave30m_durations import stops
from tests.test_rules_wave100j_counters import card_db, combat, counters, murder  # noqa: F401 (card_db: the fixture)
from tests.wave9c_kit import build, check, mana, pt, put
from tests.wave100e_kit import answer, chars, hand, loyal, to_phase, tokens


def ability(s, c, needle):
    return next(a.index for a in chars(s, c).abilities if needle in a.text)


def resolve(s, chooser):
    """Resolve the stack, ``chooser(d)`` answering every decision."""
    while (d := s.state.rules.decision) is not None or s.state.zones.get("stack"):
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chooser(d))


def library_card(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone in (f"{pid}:library", f"{pid}:hand"))


def cast_on(s, name, targets, **m):
    c = library_card(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=list(targets))
    return c


# -- Withengar Unbound ---------------------------------------------------------------------------------------------------------------------------------
def test_withengar_unbound_grows_when_a_player_loses_the_game(cards):
    s = three(cards, ["Elbrus, the Binding Blade // Withengar Unbound", "Lightning Bolt"])
    w = put(s, "Elbrus, the Binding Blade // Withengar Unbound")
    act(s, "p1", type="set_face", card_id=w.id, face=1)
    act(s, "p3", type="set_life", player="p3", value=3)
    cast_on(s, "Lightning Bolt", ["p3"], R=1)
    answer(s)
    assert "p3" in s.state.rules.lost and counters(s, w) == 13
    check(s)


# -- Gideon, Champion of Justice -----------------------------------------------------------------------------------------------------------------------
def test_gideon_becomes_a_creature_sized_once_and_prevents_damage_to_him(cards):
    s = build(cards, ["Gideon, Champion of Justice", "Lightning Bolt"])
    gid = loyal(s, "Gideon, Champion of Justice", loyalty=3)
    act(s, "p1", type="activate_ability", card_id=gid.id, ability=ability(s, gid, "Until end of turn"))
    answer(s)
    size = counters(s, gid, "loyalty")
    assert chars(s, gid).is_creature and "Planeswalker" in chars(s, gid).types and pt(s, "Gideon, Champion of Justice") == (size, size)
    act(s, "p1", type="counter", card_ids=[gid.id], kind="loyalty", delta=2)
    assert pt(s, "Gideon, Champion of Justice") == (size, size)  # set as it resolved, not updated (the ruling)
    cast_on(s, "Lightning Bolt", [gid.id], R=1)
    answer(s)
    assert counters(s, gid, "loyalty") == size + 2 and s.state.cards[gid.id].damage == 0  # all damage to him prevented this turn
    check(s)


# -- Celestial Convergence -----------------------------------------------------------------------------------------------------------------------------
def convergence_at_upkeep(cards, alice, bob):
    s = build(cards, ["Celestial Convergence"])
    conv = put(s, "Celestial Convergence")
    act(s, "p1", type="counter", card_ids=[conv.id], kind="omen", delta=1 - counters(s, conv, "omen"))
    act(s, "p1", type="set_life", player="p1", value=alice)
    act(s, "p2", type="set_life", player="p2", value=bob)
    to_phase(s, "upkeep", turn=2)
    for _ in range(20):
        r = s.state.rules
        if r.winner is not None or r.draw_reason is not None:
            return s
        if r.decision is not None:
            act(s, r.decision.player, type="choose", decision_id=r.decision.id, option_ids=[r.decision.options[0].id])
        else:
            act(s, r.priority, type="pass_priority")
    raise AssertionError("the game never ended")


def test_celestial_convergence_the_highest_life_total_wins(cards):
    s = convergence_at_upkeep(cards, 30, 25)
    assert s.state.rules.winner == "p1" and s.state.rules.draw_reason is None
    check(s)


def test_celestial_convergence_a_tie_for_the_highest_is_a_draw(cards):
    s = convergence_at_upkeep(cards, 30, 30)
    assert s.state.rules.winner is None and s.state.rules.draw_reason is not None
    check(s)


# -- Torment of Venom ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("answer_with", ["sacrifice", "discard", "life"])
def test_torment_of_venom_another_permanent_a_card_or_3_life(cards, answer_with):
    s = build(cards, ["Torment of Venom"], ["Grizzly Bears", "Sol Ring"])
    bear, ring = put(s, "Grizzly Bears", "p2"), put(s, "Sol Ring", "p2")
    act(s, "p2", type="move", card_ids=[library_card(s, "Island", "p2").id], to={"zone": "hand"})
    in_hand = hand(s, "p2")
    offered = []

    def choose(d):
        assert d.player == "p2"
        ids = [o.id for o in d.options]
        offered.append(ids)
        if "decline" in ids:
            return {"sacrifice": ["pay:0"], "discard": ["pay:1"], "life": ["decline"]}[answer_with]
        return [ring.id] if ring.id in ids else ids[:1]

    cast_on(s, "Torment of Venom", [bear.id], B=2, C=2)
    resolve(s, choose)
    assert {"pay:0", "pay:1", "decline"} <= set(offered[0]) and not any(bear.id in o for o in offered)  # not the target ("another")
    assert s.state.cards[bear.id].zone == "p2:graveyard"  # three -1/-1 counters (704.5f after it resolved)
    assert (s.state.cards[ring.id].zone == "p2:graveyard") == (answer_with == "sacrifice")
    assert hand(s, "p2") == in_hand - (answer_with == "discard")
    assert s.state.players["p2"].life == (37 if answer_with == "life" else 40)
    check(s)


# -- Biogenic Upgrade ----------------------------------------------------------------------------------------------------------------------------------
def test_biogenic_upgrade_distributes_then_doubles_on_each_target(cards):
    s = build(cards, ["Biogenic Upgrade", "Grizzly Bears", "Llanowar Elves"])
    bear, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    c = library_card(s, "Biogenic Upgrade")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, G=2, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bear.id, elves.id], target_counts=[2], division=[2, 1])
    answer(s)
    assert counters(s, bear) == 6 and counters(s, elves) == 2  # (1 + 2) doubled, 1 doubled (701.10e)
    check(s)


# -- Torrent Sculptor ----------------------------------------------------------------------------------------------------------------------------------
def test_torrent_sculptor_gets_half_the_exiled_cards_mana_value_rounded_up(cards):
    s = build(cards, ["Torrent Sculptor // Flamethrower Sonata", "Murder", "Lightning Bolt"])
    murder_card, bolt = library_card(s, "Murder"), library_card(s, "Lightning Bolt")
    for c in (murder_card, bolt):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    sculptor = cast_on(s, "Torrent Sculptor // Flamethrower Sonata", [], U=2, C=2)
    answer(s, murder_card.id)
    assert s.state.cards[murder_card.id].zone == "p1:exile" and counters(s, sculptor) == 2  # mana value 3: half, rounded up
    check(s)


# -- Floodpits Drowner ---------------------------------------------------------------------------------------------------------------------------------
def test_floodpits_drowner_shuffles_itself_and_a_stunned_creature_away(cards):
    s = build(cards, ["Floodpits Drowner"], ["Grizzly Bears", "Llanowar Elves"])
    drowner = put(s, "Floodpits Drowner")
    bear, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="stun", delta=1)
    to_phase(s, "main1", turn=2)
    mana(s, U=1, C=1)
    with pytest.raises(ActionError):  # no stun counter on the Elves
        act(s, "p1", type="activate_ability", card_id=drowner.id, ability=ability(s, drowner, "Shuffle"), targets=[elves.id])
    act(s, "p1", type="activate_ability", card_id=drowner.id, ability=ability(s, drowner, "Shuffle"), targets=[bear.id])
    answer(s)
    assert s.state.cards[drowner.id].zone == "p1:library" and s.state.cards[bear.id].zone == "p2:library"
    check(s)


# -- finality counters: Chaos Shrine's Black Crystal, Emperor of Bones ---------------------------------------------------------------------------------
def test_chaos_shrines_black_crystal_returns_an_exiled_creature_with_a_finality_counter(cards):
    s = build(cards, ["Chaos Shrine's Black Crystal", "Grizzly Bears", "Murder", "Murder"])
    put(s, "Chaos Shrine's Black Crystal")
    bear = put(s, "Grizzly Bears")
    murder(s, bear)
    assert s.state.cards[bear.id].zone == "p1:exile"
    to_phase(s, "upkeep", turn=2)
    answer(s, "yes", bear.id)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and counters(s, bear, "finality") == 1
    to_phase(s, "main1")
    murder(s, bear)
    assert s.state.cards[bear.id].zone == "p1:exile"  # (122.1h: exiled instead of put into the graveyard)
    check(s)


def test_emperor_of_bones_reanimates_its_exiled_card_with_finality_and_haste(cards):
    s = build(cards, ["Emperor of Bones"], ["Grizzly Bears"])
    emperor = put(s, "Emperor of Bones")
    bear = library_card(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bear.id], to={"player": "p2", "zone": "graveyard"})
    to_phase(s, "begin_combat")
    answer(s, bear.id)
    assert s.state.cards[bear.id].zone == "p2:exile"
    to_phase(s, "main2")
    mana(s, B=1, C=1)
    act(s, "p1", type="activate_ability", card_id=emperor.id, ability=ability(s, emperor, "Adapt"))
    answer(s, bear.id)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and counters(s, bear, "finality") == 1 and "haste" in chars(s, bear).keywords
    to_phase(s, "cleanup")
    assert s.state.cards[bear.id].zone == "p2:exile"  # sacrificed at the end step: exiled instead (finality)
    check(s)


# -- Edifice of Authority ------------------------------------------------------------------------------------------------------------------------------
def test_edifice_of_authority_locks_a_creature_down_until_your_next_turn(cards):
    s = build(cards, ["Edifice of Authority"], ["Llanowar Elves"])
    edifice, elves = put(s, "Edifice of Authority"), put(s, "Llanowar Elves", "p2")
    lock = ability(s, edifice, "Until your next turn")
    act(s, "p1", type="counter", card_ids=[edifice.id], kind="brick", delta=2)
    mana(s, C=1)
    with pytest.raises(ActionError):  # two brick counters: not yet
        act(s, "p1", type="activate_ability", card_id=edifice.id, ability=lock, targets=[elves.id])
    act(s, "p1", type="counter", card_ids=[edifice.id], kind="brick", delta=1)
    act(s, "p1", type="activate_ability", card_id=edifice.id, ability=lock, targets=[elves.id])
    answer(s)
    to_phase(s, "main1", turn=1)  # Bob's turn
    assert {"cant_attack_or_block", "cant_activate"} <= set(chars(s, elves).imposed)
    to_phase(s, "main1", turn=1)  # Alice's next turn: it ended
    assert not {"cant_attack_or_block", "cant_activate"} & set(chars(s, elves).imposed)
    check(s)


# -- Norn's Decree -------------------------------------------------------------------------------------------------------------------------------------
def test_norns_decree_draws_only_when_an_attacked_player_is_poisoned(cards):
    s = build(cards, ["Norn's Decree", "Grizzly Bears"])
    put(s, "Norn's Decree")
    bear = put(s, "Grizzly Bears")
    before = hand(s, "p1")
    combat(s, [bear])
    assert hand(s, "p1") == before + 1  # (her draw step only: Bob isn't poisoned)
    act(s, "p2", type="resource", player="p2", key="poison", delta=1)
    before = hand(s, "p1")
    combat(s, [bear])
    assert hand(s, "p1") == before + 2  # her draw step and the Decree
    check(s)


# -- Arcus Acolyte -------------------------------------------------------------------------------------------------------------------------------------
def test_arcus_acolyte_grants_outlast_only_to_creatures_without_counters(cards):
    s = build(cards, ["Arcus Acolyte", "Grizzly Bears"])
    acolyte, bear = put(s, "Arcus Acolyte"), put(s, "Grizzly Bears")
    outlast = "{G/W}, {T}: Put a +1/+1 counter on"
    assert sum(outlast in a.text for a in chars(s, bear).abilities) == 1 and sum(outlast in a.text for a in chars(s, acolyte).abilities) == 1
    to_phase(s, "main1", turn=2)
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=ability(s, bear, outlast))
    answer(s)
    assert counters(s, bear) == 1 and not any(outlast in a.text for a in chars(s, bear).abilities)  # it has a counter now
    check(s)


# -- Awakening of Vitu-Ghazi ---------------------------------------------------------------------------------------------------------------------------
def test_awakening_of_vitu_ghazi_makes_a_legendary_land_creature_named_vitu_ghazi(cards):
    s = build(cards, ["Awakening of Vitu-Ghazi", "Forest"])
    land = put(s, "Forest")
    cast_on(s, "Awakening of Vitu-Ghazi", [land.id], G=2, C=3)
    answer(s)
    ch = chars(s, land)
    assert ch.name == "Vitu-Ghazi" and "Legendary" in ch.supertypes and {"Land", "Creature"} <= set(ch.types) and "Elemental" in ch.subtypes
    assert "haste" in ch.keywords and counters(s, land) == 9 and pt(s, "Forest") == (9, 9)
    check(s)


# -- Xira, the Golden Sting ----------------------------------------------------------------------------------------------------------------------------
def test_xira_rewards_the_death_only_while_the_egg_counter_is_on_it(cards):
    s = build(cards, ["Xira, the Golden Sting", "Murder", "Murder"], ["Grizzly Bears", "Llanowar Elves"])
    xira = put(s, "Xira, the Golden Sting")
    for m in [c for c in s.state.cards.values() if c.name == "Murder"]:
        act(s, "p1", type="move", card_ids=[m.id], to={"zone": "hand"})
    bear, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    combat(s, [xira], lambda d: [bear.id] if bear.id in [o.id for o in d.options] else None, turn=0)
    assert counters(s, bear, "egg") == 1
    act(s, "p1", type="counter", card_ids=[bear.id], kind="egg", delta=-1)
    before = hand(s, "p1")
    murder(s, bear)
    assert hand(s, "p1") == before - 1 and not tokens(s, "Insect", "p1")  # no egg counter as it died: nothing
    combat(s, [xira], lambda d: [elves.id] if elves.id in [o.id for o in d.options] else None)
    before = hand(s, "p1")
    murder(s, elves)
    assert hand(s, "p1") == before - 1 + 1 and len(tokens(s, "Insect", "p1")) == 1
    check(s)


# -- Hallowed Respite ----------------------------------------------------------------------------------------------------------------------------------
def test_hallowed_respite_counters_yours_and_taps_theirs(cards):
    s = build(cards, ["Hallowed Respite", "Hallowed Respite", "Grizzly Bears"], ["Grizzly Bears"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    cast_on(s, "Hallowed Respite", [mine.id], W=1, U=1)
    answer(s)
    assert s.state.cards[mine.id].zone == "p1:battlefield" and counters(s, mine) == 1 and not s.state.cards[mine.id].tapped
    cast_on(s, "Hallowed Respite", [theirs.id], W=1, U=1)
    answer(s)
    assert s.state.cards[theirs.id].zone == "p2:battlefield" and counters(s, theirs) == 0 and s.state.cards[theirs.id].tapped
    check(s)


# -- Wicked Slumber ------------------------------------------------------------------------------------------------------------------------------------
def test_wicked_slumber_puts_each_stun_counter_on_either_target(cards):
    s = build(cards, ["Wicked Slumber", "Wicked Slumber"], ["Grizzly Bears", "Llanowar Elves"])
    bear, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    picks = iter([bear.id, elves.id])
    c = library_card(s, "Wicked Slumber")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bear.id, elves.id], target_counts=[2])
    resolve(s, lambda d: [next(picks)])
    assert all(s.state.cards[x.id].tapped and counters(s, x, "stun") == 1 for x in (bear, elves))
    c = library_card(s, "Wicked Slumber")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bear.id], target_counts=[1])
    answer(s)
    assert counters(s, bear, "stun") == 3 and counters(s, elves, "stun") == 1  # one target: both on it
    check(s)


# -- batch 3 ------------------------------------------------------------------------------------------------------------------------------------------
def test_amzu_sizes_one_insect_by_the_greatest_mana_value_once_each_turn(cards):
    s = build(cards, ["Amzu, Swarm's Hunger", "Torrent Sculptor // Flamethrower Sonata", "Murder", "Lightning Bolt"])
    put(s, "Amzu, Swarm's Hunger")
    murder_card, bolt = library_card(s, "Murder"), library_card(s, "Lightning Bolt")
    for c in (murder_card, bolt):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    cast_on(s, "Torrent Sculptor // Flamethrower Sonata", [], U=2, C=2)
    answer(s, murder_card.id, "yes")  # (the Sculptor exiles Murder, mana value 3: Amzu's ability, 603.2c)
    insects = tokens(s, "Insect", "p1")
    assert len(insects) == 1 and counters(s, insects[0]) == 3 and s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)


def test_portent_tracker_removes_from_an_opponents_battle_and_adds_otherwise(cards):
    s = build(cards, ["Portent Tracker", "Invasion of Gobakhan // Lightshield Array"])
    tracker = put(s, "Portent Tracker")
    siege = cast_on(s, "Invasion of Gobakhan // Lightshield Array", [], W=1, C=1)
    answer(s, "p2")
    defense = counters(s, siege, "defense")
    to_phase(s, "main1", turn=2)
    act(s, "p1", type="activate_ability", card_id=tracker.id, ability=ability(s, tracker, "Choose target battle"), targets=[siege.id])
    answer(s)
    assert counters(s, siege, "defense") == defense - 1  # Bob protects it
    check(s)


def test_sphere_of_annihilation_exiles_itself_and_everything_small_enough(cards):
    s = build(cards, ["Sphere of Annihilation", "Grizzly Bears", "Probe Ogre", "Murder", "Sol Ring"], ["Grizzly Bears"])
    bear, ogre, ring = put(s, "Grizzly Bears"), put(s, "Probe Ogre"), put(s, "Sol Ring")
    dead, spell = library_card(s, "Grizzly Bears", "p2"), library_card(s, "Murder")
    act(s, "p2", type="move", card_ids=[dead.id], to={"player": "p2", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[spell.id], to={"player": "p1", "zone": "graveyard"})
    sphere = library_card(s, "Sphere of Annihilation")
    act(s, "p1", type="move", card_ids=[sphere.id], to={"zone": "hand"})
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=sphere.id, x_value=2)
    answer(s)
    assert counters(s, sphere, "void") == 2
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=2)
    answer(s)
    zones = {c.name: s.state.cards[c.id].zone for c in (sphere, bear, ogre, ring, spell)}
    assert zones == {"Sphere of Annihilation": "p1:exile", "Grizzly Bears": "p1:exile", "Probe Ogre": "p1:battlefield", "Sol Ring": "p1:battlefield",
                     "Murder": "p1:graveyard"}
    assert s.state.cards[dead.id].zone == "p2:exile"  # a creature card in a graveyard, mana value 2
    check(s)


def test_venerated_teacher_levels_up_only_creatures_with_level_up(cards):
    s = build(cards, ["Venerated Teacher", "Student of Warfare", "Grizzly Bears"])
    student, bear = put(s, "Student of Warfare"), put(s, "Grizzly Bears")
    cast_on(s, "Venerated Teacher", [], U=1, C=2)
    answer(s)
    assert counters(s, student, "level") == 2 and counters(s, bear, "level") == 0 and pt(s, "Student of Warfare") == (3, 3)
    check(s)
