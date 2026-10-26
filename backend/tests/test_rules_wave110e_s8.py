"""Wave 110E session 8: Oracle-text scenarios for cards promoted this session (each docstring names the rule)."""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
import tests.test_rules_wave110e_s7  # noqa: F401  (registers the cards)
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)

SHRIEK = real("Fell Beast's Shriek", "{U}{R}", 2, "Sorcery",
              "Each opponent chooses a creature they control. Tap and goad the chosen creatures. (Until your next turn, those creatures attack each combat if able "
              "and attack a player other than you if able.)\nSplice onto instant or sorcery {2}{U}{R} (As you cast an instant or sorcery spell, you may reveal this "
              "card from your hand and pay its splice cost. If you do, add this card's effects to that spell.)", None, "UR")
SIP = real("Test Sip", "{U}", 1, "Instant", "You gain 1 life.", None, "U")
CULPRIT = real("Expose the Culprit", "{1}{R}", 2, "Instant",
               "Choose one or both —\n• Turn target face-down creature face up.\n• Exile any number of face-up creatures you control with disguise in a face-down pile, "
               "shuffle that pile, then cloak them. (To cloak a card, put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its "
               "mana cost if it's a creature card.)", None, "R")
DISGUISER = real("Test Disguiser", "{1}{G}", 2, "Creature — Elf", "Disguise {1}{G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}.)", ("3", "3"), "G")
AMBUSH = real("Auditore Ambush", "{2}{U}{B}", 4, "Sorcery",
              "Choose one or both —\n• Return target creature to its owner's hand.\n• Target player searches their library and/or graveyard for a card named Ezio, "
              "Blade of Vengeance, reveals it, and puts it into their hand. If they search their library this way, they shuffle.", None, "UB")
EZIO = real("Ezio, Blade of Vengeance", "{3}{U}{B}", 5, "Legendary Creature — Human Assassin",
            "Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nWhenever an Assassin you control deals combat damage to a player, draw a card.",
            ("5", "5"), "UB")
WINGS = real("Arcanum Wings", "{1}{U}", 2, "Enchantment — Aura",
             "Enchant creature\nEnchanted creature has flying.\nAura swap {2}{U} ({2}{U}: Exchange this Aura with an Aura card in your hand.)", None, "U")
BOON = real("Test Boon", "{1}{G}", 2, "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+2.", None, "G")
RELIC = real("Test Relic Aura", "{1}{G}", 2, "Enchantment — Aura", "Enchant artifact\nEnchanted artifact gets +2/+2.", None, "G")
REFLECT = real("Infinite Reflection", "{5}{U}", 6, "Enchantment — Aura",
               "Enchant creature\nWhen this Aura enters attached to a creature, each other nontoken creature you control becomes a copy of that creature.\n"
               "Nontoken creatures you control enter as a copy of enchanted creature.", None, "U")
WOLF = real("Test Wolf", "{1}{G}", 2, "Creature — Wolf", "", ("3", "3"), "G")
DANCE = real("Corpse Dance", "{2}{B}", 3, "Instant",
             "Buyback {2} (You may pay an additional {2} as you cast this spell. If you do, put this card into your hand as it resolves.)\n"
             "Return the top creature card of your graveyard to the battlefield. That creature gains haste until end of turn. Exile it at the beginning of the next end step.",
             None, "B")
BARGE = real("War Barge", "{4}", 4, "Artifact",
             "{3}: Target creature gains islandwalk until end of turn. When this artifact leaves the battlefield this turn, destroy that creature. A creature destroyed this way "
             "can't be regenerated. (A creature with islandwalk can't be blocked as long as defending player controls an Island.)", None, "")
REGENERATOR = real("Test Regenerator", "{1}{G}", 2, "Creature — Troll", "{G}: Regenerate this creature.", ("2", "2"), "G")
SMASH = real("Test Smash", "{R}", 1, "Instant", "Destroy target artifact.", None, "R")
base.EXTRA.extend([SMASH, BARGE, REGENERATOR, DANCE, REFLECT, WOLF, WINGS, BOON, RELIC, SHRIEK, SIP, CULPRIT, DISGUISER, AMBUSH, EZIO])


@pytest.mark.parametrize("name", [c["name"] for c in (SHRIEK, CULPRIT, AMBUSH, WINGS, REFLECT)])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_fell_beasts_shriek_each_opponent_taps_and_goads_the_creature_they_chose(cards):
    """608.2c, 701.39a: each opponent picks one of their creatures; those creatures become tapped and goaded by the caster."""
    from tests.test_rules_conditionals import creature
    from tests.test_rules_wave110e_cards import answer, cast
    from tests.wave9c_kit import build, check, mana

    s = build(cards, ["Fell Beast's Shriek"])
    a, b = creature(s, "p2", "Aaa", "2/2"), creature(s, "p2", "Bbb", "3/3")
    mana(s, U=1, R=1)
    cast(s, "Fell Beast's Shriek")
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id])
    answer(s)
    assert s.state.cards[a.id].tapped and not s.state.cards[b.id].tapped
    from app.rules.keyword_actions import goaded_by
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    assert goaded_by(plan.ch(s.state.cards[a.id])) == {"p1"} and not goaded_by(plan.ch(s.state.cards[b.id]))
    check(s)


def test_fell_beasts_shriek_spliced_onto_an_instant_adds_its_text_and_cost(cards):
    """702.47a: spliced onto an instant, the spell also makes each opponent choose a creature to tap and goad; the splice cost {2}{U}{R} is extra."""
    from tests.test_rules_conditionals import creature
    from tests.test_rules_wave110e_cards import answer
    from tests.wave9c_kit import build, check, mana, to_hand

    s = build(cards, ["Test Sip", "Fell Beast's Shriek"])
    a = creature(s, "p2", "Aaa", "2/2")
    sip, shriek = to_hand(s, "Test Sip"), to_hand(s, "Fell Beast's Shriek")
    mana(s, U=2, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=sip.id, splice=[shriek.id])
    answer(s)
    assert s.state.cards[a.id].tapped and s.state.cards[shriek.id].zone == "p1:hand" and s.state.players["p1"].life == 41
    check(s)


def _expose(cards, modes, pick_disguisers):
    from tests.test_rules_conditionals import creature
    from tests.test_rules_wave110e_cards import answer, cast
    from tests.wave9c_kit import build, mana, put

    s = build(cards, ["Expose the Culprit", "Test Disguiser", "Grizzly Bears"])
    d = put(s, "Test Disguiser")
    bears = put(s, "Grizzly Bears")
    creature(s, "p2", "Plain", "2/2")
    return s, d, bears, (mana, cast, answer)


def _face_down(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.face_down and c.zone == f"{pid}:battlefield"]


@pytest.mark.parametrize("take", [True, False])
def test_expose_the_culprit_cloaks_only_the_disguise_creatures_you_choose(cards, take):
    """701.58, 406.3: any number (0 too) of face-up creatures with disguise are exiled face down, shuffled, then cloaked; a creature without disguise is not an option."""
    from tests.wave9c_kit import check

    s, d, bears, (mana, cast, answer) = _expose(cards, [1], take)
    mana(s, R=1, C=1)
    cast(s, "Expose the Culprit", modes=[1])
    for _ in range(10):
        dec = s.state.rules.decision
        if dec is None:
            break
        assert [o.id for o in dec.options] == [d.id]  # (the Bears has no disguise)
        act(s, dec.player, type="choose", decision_id=dec.id, option_ids=[d.id] if take else [])
    answer(s)
    down = _face_down(s)
    assert len(down) == (1 if take else 0) and s.state.cards[bears.id].zone == "p1:battlefield" and not s.state.cards[bears.id].face_down
    assert all(c.name == "Test Disguiser" for c in down)  # (the same card, now a face-down permanent: 708.4)
    check(s)


def test_expose_the_culprit_first_mode_turns_the_cloaked_creature_face_up(cards):
    """701.58 then 708.8: a cloaked (face-down) creature is the target of mode one and is turned face up."""
    from tests.wave9c_kit import check

    s, d, bears, (mana, cast, answer) = _expose(cards, [1], True)
    mana(s, R=2, C=2)
    cast(s, "Expose the Culprit", modes=[1])
    for _ in range(10):
        dec = s.state.rules.decision
        if dec is None:
            break
        act(s, dec.player, type="choose", decision_id=dec.id, option_ids=[d.id])
    answer(s)
    (hidden,) = _face_down(s)
    cast(s, "Expose the Culprit", [hidden.id], modes=[0])
    answer(s)
    assert not s.state.cards[hidden.id].face_down
    check(s)


@pytest.mark.parametrize(("zone", "searcher"), [("library", "p2"), ("graveyard", "p2"), ("library", "p1")])
def test_auditore_ambush_the_target_player_searches_their_own_zones_for_ezio(cards, zone, searcher):
    """701.23a: the targeted player (not the caster) searches their library and/or graveyard; 701.24g: only a library search shuffles; the card goes to that player's hand."""
    from tests.test_rules_wave110e_cards import answer, cast
    from tests.wave9c_kit import build, card_named, check, mana

    s = build(cards, ["Auditore Ambush", "Ezio, Blade of Vengeance"], ["Ezio, Blade of Vengeance"])
    mine, theirs = card_named(s, "Ezio, Blade of Vengeance", "p1"), card_named(s, "Ezio, Blade of Vengeance", "p2")
    ezio = theirs if searcher == "p2" else mine
    if zone == "graveyard":
        act(s, searcher, type="move", card_ids=[ezio.id], to={"player": searcher, "zone": "graveyard"})
    other = mine if searcher == "p2" else theirs
    before = list(s.state.zones[f"{searcher}:library"])
    mana(s, U=1, B=1, C=2)
    cast(s, "Auditore Ambush", [searcher], modes=[1])
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        want = [o.id for o in d.options if o.id in (ezio.id, "graveyard" if zone == "graveyard" else "both")] or [d.options[0].id]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=want[:1])
    answer(s)
    assert s.state.cards[ezio.id].zone == f"{searcher}:hand" and s.state.cards[other.id].zone != f"{searcher}:hand"
    shuffled = any("shuffle" in (p.t or "") for entry in s.state.log for p in entry.parts)
    assert shuffled == (zone == "library")
    if zone == "graveyard":
        assert s.state.zones[f"{searcher}:library"] == before  # (no library search, no shuffle)
    check(s)


def _swap(cards, hand, answer_with):
    from tests.test_rules_conditionals import creature
    from tests.wave9c_kit import build, mana, put, to_hand

    s = build(cards, ["Arcanum Wings", *hand])
    bear = creature(s, "p1", "Bear", "2/2")
    wings = put(s, "Arcanum Wings")
    aura = [to_hand(s, n) for n in hand]
    mana(s, U=1, C=2)
    return s, bear, wings, aura


def _activate_swap(s, wings, pick):
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[wings.id])
    index = next(a.index for a in ch.abilities if a.text.startswith("{2}{U}:"))
    act(s, "p1", type="activate_ability", card_id=wings.id, ability=index)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None and s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        if d is None:
            break
        ids = [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[i for i in ids if i in pick][:1] or ids[:1])


@pytest.mark.parametrize("hand", [["Test Boon"], ["Test Relic Aura"], []])
def test_aura_swap_exchanges_this_aura_with_an_aura_card_in_hand(cards, hand):
    """702.65a: the Aura card from hand enters (choosing what it enchants, 303.4f) and this Aura returns to hand; 702.65b/303.4g: an Aura that can't enter means no exchange."""
    from tests.wave9c_kit import check

    s, bear, wings, aura = _swap(cards, hand, None)
    act(s, "p1", type="attach", card_ids=[wings.id], to=bear.id)
    _activate_swap(s, wings, {bear.id})
    swapped = hand == ["Test Boon"]
    assert s.state.cards[wings.id].zone == ("p1:hand" if swapped else "p1:battlefield")
    if swapped:
        assert s.state.cards[aura[0].id].zone == "p1:battlefield" and s.state.cards[aura[0].id].attached_to == bear.id
    elif aura:
        assert s.state.cards[aura[0].id].zone == "p1:hand"
    check(s)


@pytest.mark.parametrize("pid", ["p1", "p2"])
def test_infinite_reflection_copies_the_enchanted_creature_now_and_for_later_entries(cards, pid):
    """707.9/707.2: the trigger turns each other nontoken creature you control into a copy of the enchanted one; 614.1c: later nontoken creatures of its controller enter as copies of it, an opponent's do not."""
    from tests.test_rules_conditionals import creature
    from tests.test_rules_wave100f_attached import to_phase
    from tests.test_rules_wave100f_control import ch
    from tests.test_rules_wave110e_cards import answer, cast
    from tests.wave9c_kit import build, check, mana, put

    s = build(cards, ["Infinite Reflection", "Shivan Dragon", "Grizzly Bears", "Test Wolf"], ["Test Wolf"])
    dragon, bears = put(s, "Shivan Dragon"), put(s, "Grizzly Bears")
    theirs = creature(s, "p2", "Theirs", "1/1")
    mana(s, U=1, C=5)
    cast(s, "Infinite Reflection", [dragon.id])
    answer(s)
    named = lambda c: ch(s, s.state.cards[c.id]).name  # noqa: E731
    assert (named(dragon), named(bears), named(theirs)) == ("Shivan Dragon", "Shivan Dragon", "Theirs")
    if pid == "p2":
        to_phase(s, "main1", turn=2)
    mana(s, pid, G=1, C=1)
    wolf = cast(s, "Test Wolf", pid=pid)
    answer(s)
    assert named(wolf) == ("Shivan Dragon" if pid == "p1" else "Test Wolf")
    check(s)


@pytest.mark.parametrize("buyback", [False, True])
def test_corpse_dance_returns_the_top_creature_card_with_haste_and_exiles_it_at_end_step(cards, buyback):
    """404.1, 400.7, 603.7: the last creature card put into the graveyard (a land above it is skipped) returns, hasty, and is exiled at the next end step; 702.27a buyback returns the spell to hand."""
    from tests.test_rules_wave100f_attached import to_phase
    from tests.test_rules_wave110e_cards import answer
    from tests.wave9c_kit import build, check, mana, to_hand
    from tests.wave110d_kit import ch, grave_new, now

    s = build(cards, ["Corpse Dance", "Grizzly Bears", "Test Wolf", "Forest"])
    old, top = grave_new(s, "Grizzly Bears"), grave_new(s, "Test Wolf")
    grave_new(s, "Forest")
    dance = to_hand(s, "Corpse Dance")
    mana(s, B=1, C=2 + (2 if buyback else 0))
    act(s, "p1", type="cast_spell", card_id=dance.id, **({"buyback": True} if buyback else {}))
    answer(s)
    assert now(s, top).zone == "p1:battlefield" and now(s, old).zone == "p1:graveyard" and "haste" in ch(s, now(s, top)).keywords
    assert s.state.cards[dance.id].zone == ("p1:hand" if buyback else "p1:graveyard")
    to_phase(s, "main2", turn=1)
    to_phase(s, "main1", turn=2)
    assert now(s, top).zone == "p1:exile"
    check(s)


@pytest.mark.parametrize("shield", [False, True])
def test_war_barge_destruction_cant_be_regenerated(cards, shield):
    """701.19c, 614.8: the delayed destroy ignores a regeneration shield ("can't be regenerated" is part of that destruction); the shield saves it from other destruction only."""
    from tests.wave9c_kit import build, check, mana, put
    from tests.wave110d_kit import settle

    s = build(cards, ["War Barge", "Test Regenerator", "Test Smash"], [])
    barge, troll = put(s, "War Barge"), put(s, "Test Regenerator")
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=barge.id, ability=0, targets=[troll.id], target_counts=[1])
    settle(s)
    if shield:
        mana(s, "p1", G=1)
        act(s, "p1", type="activate_ability", card_id=troll.id, ability=0)
        settle(s)
    mana(s, "p1", R=1)
    base.cast(s, "Test Smash", [barge.id])
    settle(s)
    assert s.state.cards[troll.id].zone == "p1:graveyard"
    check(s)
