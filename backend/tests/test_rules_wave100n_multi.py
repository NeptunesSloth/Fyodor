"""Wave 100N: cards whose missing lines spanned several families. Real Oracle text; every scenario checks the replay and a save and a load.

* "instead" restatements of the replaced damage (608.2c): "… to that permanent or player and the damage can't be prevented" (Lightning Surge,
  Arrow Storm: 615.12), "… to each of those permanents and/or players" (Shower of Coals), "X plus 2" (Crater's Claws), "if that target is white
  and/or blue" (Lithomantic Barrage).
* Ability-word lines: "this spell can't be countered" under spell mastery (Exquisite Firecraft: judged as the counterspell resolves), "Then if …"
  (Might of the Old Ways: after the pump, its ruling), "that creature enters with two additional +1/+1 counters" (Necromantic Summons, 122.6),
  an addendum naming a target two lines up (Code of Constraint), "instead you and each permanent you control gain protection" (Faith's Shield).
* Exact builds (app/rules/multi100n.py): Searing Blaze (player-relative target), Concussive Bolt (the set isn't locked in, 611.2c), To the
  Slaughter (one of each kind if able), "When you cast this spell while …" (Ancestral Communion, Social Snub: checked only as it is cast).
* "Permanents you control can't be the targets of blue or black spells your opponents control this turn." (Display of Dominance, 115.2).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

EXTRA = [
    real('Lightning Surge', '{3}{R}{R}', 5, 'Sorcery',
         "Lightning Surge deals 4 damage to any target.\nThreshold — If there are seven or more cards in your graveyard, instead Lightning Surge deals 6 damage to that permanent or player and the damage can't be prevented.\nFlashback {5}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)", None, 'R'),
    real('Arrow Storm', '{3}{R}{R}', 5, 'Sorcery',
         "Arrow Storm deals 4 damage to any target.\nRaid — If you attacked this turn, instead Arrow Storm deals 5 damage to that permanent or player and the damage can't be prevented.", None, 'R'),
    real("Crater's Claws", '{X}{R}', 1, 'Sorcery',
         "Crater's Claws deals X damage to any target.\nFerocious — Crater's Claws deals X plus 2 damage instead if you control a creature with power 4 or greater.", None, 'R'),
    real('Shower of Coals', '{3}{R}{R}', 5, 'Sorcery',
         'Shower of Coals deals 2 damage to each of up to three targets.\nThreshold — Shower of Coals deals 4 damage to each of those permanents and/or players instead if there are seven or more cards in your graveyard.', None, 'R'),
    real('Lithomantic Barrage', '{R}', 1, 'Sorcery',
         "This spell can't be countered.\nLithomantic Barrage deals 1 damage to target creature or planeswalker. It deals 5 damage instead if that target is white and/or blue.", None, 'R'),
    real('Exquisite Firecraft', '{1}{R}{R}', 3, 'Sorcery',
         "Exquisite Firecraft deals 4 damage to any target.\nSpell mastery — If there are two or more instant and/or sorcery cards in your graveyard, this spell can't be countered.", None, 'R'),
    real('Might of the Old Ways', '{1}{G}', 2, 'Instant',
         'Target creature gets +2/+2 until end of turn.\nCoven — Then if you control three or more creatures with different powers, draw a card.', None, 'G'),
    real('Necromantic Summons', '{4}{B}', 5, 'Sorcery',
         'Put target creature card from a graveyard onto the battlefield under your control.\nSpell mastery — If there are two or more instant and/or sorcery cards in your graveyard, that creature enters with two additional +1/+1 counters on it.', None, 'B'),
    real('Code of Constraint', '{2}{U}', 3, 'Instant',
         "Target creature gets -4/-0 until end of turn.\nDraw a card.\nAddendum — If you cast this spell during your main phase, tap that creature and it doesn't untap during its controller's next untap step.", None, 'U'),
    real("Faith's Shield", '{W}', 1, 'Instant',
         'Target permanent you control gains protection from the color of your choice until end of turn.\nFateful hour — If you have 5 or less life, instead you and each permanent you control gain protection from the color of your choice until end of turn.', None, 'W'),
    real('Searing Blaze', '{R}{R}', 2, 'Instant',
         "Searing Blaze deals 1 damage to target player or planeswalker and 1 damage to target creature that player or that planeswalker's controller controls.\nLandfall — If you had a land enter the battlefield under your control this turn, Searing Blaze deals 3 damage to that player or planeswalker and 3 damage to that creature instead.", None, 'R'),
    real('Concussive Bolt', '{3}{R}{R}', 5, 'Sorcery',
         "Concussive Bolt deals 4 damage to target player or planeswalker.\nMetalcraft — If you control three or more artifacts, creatures controlled by that player or by that planeswalker's controller can't block this turn.", None, 'R'),
    real('To the Slaughter', '{2}{B}', 3, 'Instant',
         'Target player sacrifices a creature or planeswalker of their choice.\nDelirium — If there are four or more card types among cards in your graveyard, instead that player sacrifices a creature and a planeswalker of their choice.', None, 'B'),
    real('Ancestral Communion', '{1}{G}', 2, 'Sorcery',
         'When you cast this spell while you control your commander, copy this spell. You may choose a new target for the copy.\nReturn target permanent card from your graveyard to your hand.', None, 'G'),
    real('Social Snub', '{1}{W}{B}', 3, 'Sorcery',
         'When you cast this spell while you control a creature, you may copy this spell.\nEach player sacrifices a creature of their choice. Each opponent loses 1 life and you gain 1 life.', None, 'BW'),
    real('Display of Dominance', '{1}{G}', 2, 'Instant',
         "Choose one —\n• Destroy target blue or black noncreature permanent.\n• Permanents you control can't be the targets of blue or black spells your opponents control this turn.", None, 'G'),
    real('Swallow Whole', '{W}', 1, 'Sorcery',
         "As an additional cost to cast this spell, tap an untapped creature you control.\nExile target tapped creature. Put a +1/+1 counter on the creature tapped to pay this spell's additional cost.", None, 'W'),
    real('Thought Distortion', '{4}{B}{B}', 6, 'Sorcery',
         "This spell can't be countered.\nTarget opponent reveals their hand. Exile all noncreature, nonland cards from that player's hand and graveyard.", None, 'B'),
    real('Qutrub Forayer', '{2}{B}', 3, 'Creature — Zombie Horror',
         'When this creature enters, choose one —\n• Destroy target creature that was dealt damage this turn.\n• Exile up to two target cards from a single graveyard.', ('3', '2'), 'B'),
    real('Exile into Darkness', '{4}{B}', 5, 'Sorcery',
         'Target player sacrifices a creature of their choice with mana value 3 or less.\nAt the beginning of your upkeep, if you have more cards in hand than each opponent, you may return this card from your graveyard to your hand.', None, 'B'),
    real('Vengeful Rebirth', '{4}{R}{G}', 6, 'Sorcery',
         "Return target card from your graveyard to your hand. If you return a nonland card to your hand this way, Vengeful Rebirth deals damage equal to that card's mana value to any target.\nExile Vengeful Rebirth.", None, 'GR'),
    real('Inferno Trap', '{3}{R}', 4, 'Instant — Trap',
         "If you've been dealt damage by two or more creatures this turn, you may pay {R} rather than pay this spell's mana cost.\nInferno Trap deals 4 damage to target creature.", None, 'R'),
    real('Mega Flare', '{2}{R}', 3, 'Sorcery',
         'Kicker {3}{R}{R}\nIf this spell was kicked, create a 6/6 red Dragon creature token with flying.\nFor each opponent, choose up to one target creature that player controls. Mega Flare deals damage equal to the greatest power among creatures you control to each of the chosen creatures.', None, 'R'),
    real('Gruesome Discovery', '{2}{B}{B}', 4, 'Sorcery',
         'Target player discards two cards.\nMorbid — If a creature died this turn, instead that player reveals their hand, you choose two cards from it, then that player discards those cards.', None, 'B'),
    real('Breaking Wave', '{2}{U}{U}', 4, 'Sorcery',
         'You may cast this spell as though it had flash if you pay {2} more to cast it. (You may cast it any time you could cast an instant.)\nSimultaneously untap all tapped creatures and tap all untapped creatures.', None, 'U'),
    real('Encircling Fissure', '{2}{W}', 3, 'Instant',
         "Prevent all combat damage that would be dealt this turn by creatures target opponent controls.\nAwaken 2—{4}{W} (If you cast this spell for {4}{W}, also put two +1/+1 counters on target land you control and it becomes a 0/0 Elemental creature with haste. It's still a land.)", None, 'W'),
    real("Gustha's Scepter", '{0}', 0, 'Artifact',
         "{T}: Exile a card from your hand face down. You may look at it for as long as it remains exiled.\n{T}: Return a card you own exiled with this artifact to your hand.\nWhen you lose control of this artifact, put all cards exiled with this artifact into their owner's graveyard.", None, ''),
    real('Duplicity', '{3}{U}{U}', 5, 'Enchantment',
         "When this enchantment enters, exile the top five cards of your library face down.\nAt the beginning of your upkeep, you may exile all cards from your hand face down. If you do, put all other cards you own exiled with this enchantment into your hand.\nAt the beginning of your end step, discard a card.\nWhen you lose control of this enchantment, put all cards exiled with this enchantment into their owner's graveyard.", None, 'U'),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real('Donate', '{2}{U}', 3, 'Sorcery', 'Target player gains control of target permanent you control.', None, 'U'),
    real('Mending Hands', '{W}', 1, 'Instant', 'Prevent the next 4 damage that would be dealt to any target this turn.', None, 'W'),
]
STEPS = ["main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat", "main2", "end"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def to_graveyard(s, n, name="Forest", pid="p1"):
    """``n`` more of the player's cards named ``name`` (from the library) into their graveyard."""
    cards = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]
    assert len(cards) == n
    act(s, pid, type="move", card_ids=[c.id for c in cards], to={"player": pid, "zone": "graveyard"})


def gy(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:graveyard", []))


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


# -- restated damage -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("threshold", [False, True])
def test_lightning_surge_with_threshold_deals_6_that_cant_be_prevented(cards, threshold):
    s = build(cards, ["Lightning Surge", "Mending Hands"])
    mana(s, W=1)
    cast(s, "Mending Hands", ["p2"])  # (the next 4 damage to Bob is prevented)
    answer(s)
    to_graveyard(s, (7 if threshold else 6) - gy(s))
    mana(s, R=2, C=3)
    cast(s, "Lightning Surge", ["p2"])
    answer(s)
    assert life(s, "p2") == (34 if threshold else 40)  # (6 dealt despite the shield: 615.12; else 4, all prevented — never 10, its ruling)
    check(s)


@pytest.mark.parametrize("ferocious", [False, True])
def test_craters_claws_x_plus_2_with_a_power_4_creature(cards, ferocious):
    s = build(cards, ["Crater's Claws", "Garruk's Horde", "Grizzly Bears"])
    put(s, "Garruk's Horde" if ferocious else "Grizzly Bears")
    mana(s, R=1, C=1)
    cast(s, "Crater's Claws", ["p2"], x_value=1)
    answer(s)
    assert life(s, "p2") == (37 if ferocious else 39)
    check(s)


@pytest.mark.parametrize("threshold", [False, True])
def test_shower_of_coals_four_to_each_target_with_threshold(cards, threshold):
    s = build(cards, ["Shower of Coals"], ["Garruk's Horde"])
    horde = put(s, "Garruk's Horde", "p2")
    to_graveyard(s, 7 if threshold else 6)
    mana(s, R=2, C=3)
    cast(s, "Shower of Coals", ["p2", horde.id], target_counts=[2])
    answer(s)
    n = 4 if threshold else 2
    assert life(s, "p2") == 40 - n and s.state.cards[horde.id].damage == n
    check(s)


@pytest.mark.parametrize("name, dealt", [("Mulldrifter", 5), ("Grizzly Bears", 1)])
def test_lithomantic_barrage_five_to_a_blue_target(cards, name, dealt):
    s = build(cards, ["Lithomantic Barrage"], [name])
    target = put(s, name, "p2")
    mana(s, R=1)
    cast(s, "Lithomantic Barrage", [target.id])
    answer(s)
    if dealt == 5:
        assert s.state.cards[target.id].zone == "p2:graveyard"
    else:
        assert s.state.cards[target.id].damage == 1
    check(s)


# -- ability-word lines --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mastery", [False, True])
def test_exquisite_firecraft_cant_be_countered_with_spell_mastery(cards, mastery):
    s = build(cards, ["Exquisite Firecraft", "Lightning Bolt", "Opt"], ["Counterspell"])
    names = ["Lightning Bolt", "Opt"] if mastery else ["Lightning Bolt"]
    act(s, "p1", type="move", card_ids=[card_named(s, n).id for n in names], to={"player": "p1", "zone": "graveyard"})
    mana(s, R=2, C=1)
    act(s, "p2", type="set_stops", own=["main1"], others=["main1"], smart_pass=False)
    fire = cast(s, "Exquisite Firecraft", ["p2"])
    mana(s, "p2", U=2)
    cast(s, "Counterspell", [fire.id], pid="p2")
    answer(s)
    assert life(s, "p2") == (36 if mastery else 40)
    assert s.state.cards[fire.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("target, draws", [("Grizzly Bears", True), ("Garruk's Horde", False)])
def test_might_of_the_old_ways_counts_powers_after_the_pump(cards, target, draws):
    """Bears 2/2, Kami 2/2, Horde 7/7: +2/+2 on the Bears makes 4, 2, 7 (three powers); on the Horde 2, 2, 9 (its ruling)."""
    s = build(cards, ["Might of the Old Ways", "Grizzly Bears", "Kami of Ancient Law", "Garruk's Horde"])
    for n in ("Grizzly Bears", "Kami of Ancient Law", "Garruk's Horde"):
        put(s, n)
    mana(s, G=1, C=1)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Might of the Old Ways", [card_named(s, target).id])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + draws
    check(s)


@pytest.mark.parametrize("mastery", [False, True])
def test_necromantic_summons_two_counters_with_spell_mastery(cards, mastery):
    s = build(cards, ["Necromantic Summons", "Lightning Bolt", "Opt"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "graveyard"})
    names = ["Lightning Bolt", "Opt"] if mastery else ["Opt"]
    act(s, "p1", type="move", card_ids=[card_named(s, n).id for n in names], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1, C=4)
    cast(s, "Necromantic Summons", [bears.id])
    answer(s)
    got = s.state.cards[bears.id]
    assert got.zone == "p1:battlefield" and got.controller == "p1"
    assert got.counters.get("+1/+1", 0) == (2 if mastery else 0)
    check(s)


@pytest.mark.parametrize("main", [True, False])
def test_code_of_constraint_addendum_taps_and_freezes_in_your_main_phase(cards, main):
    s = build(cards, ["Code of Constraint"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    if not main:
        act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
        until(s, lambda s: s.state.turn.phase == "begin_combat" and s.state.rules.priority == "p1")
    hand = len(s.state.zones["p1:hand"])
    mana(s, U=1, C=2)
    cast(s, "Code of Constraint", [bears.id])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (a card drawn)
    assert s.state.cards[bears.id].tapped == main
    if main:  # 502.3: it stays tapped through Bob's next untap step
        until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
        assert s.state.cards[bears.id].tapped
    check(s)


@pytest.mark.parametrize("fateful", [False, True])
def test_faiths_shield_fateful_hour_covers_you_and_each_permanent(cards, fateful):
    s = build(cards, ["Faith's Shield", "Grizzly Bears", "Kami of Ancient Law"])
    bears, kami = put(s, "Grizzly Bears"), put(s, "Kami of Ancient Law")
    if fateful:
        act(s, "p1", type="set_life", player="p1", value=5)
    mana(s, W=1)
    cast(s, "Faith's Shield", [bears.id])
    answer(s, "Red")
    assert "Protection from red" in {a.text.rstrip(".") for a in ch(s, bears).abilities}
    assert ("Protection from red" in {a.text.rstrip(".") for a in ch(s, kami).abilities}) == fateful
    assert any(x["player"] == "p1" and x["quality"] == "red" for x in s.state.rules.player_shields) == fateful
    check(s)


# -- exact builds ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("landfall", [False, True])
def test_searing_blaze_player_and_their_creature_three_each_with_landfall(cards, landfall):
    s = build(cards, ["Searing Blaze"], ["Garruk's Horde"])
    horde = put(s, "Garruk's Horde", "p2")
    if landfall:
        act(s, "p1", type="play_land", card_id=to_hand(s, "Forest").id)
    mana(s, R=2)
    cast(s, "Searing Blaze", ["p2", horde.id], target_counts=[1, 1])
    answer(s)
    n = 3 if landfall else 1
    assert life(s, "p2") == 40 - n and s.state.cards[horde.id].damage == n
    check(s)


def test_searing_blaze_needs_a_creature_that_player_controls(cards):
    s = build(cards, ["Searing Blaze"], ["Garruk's Horde"])
    horde = put(s, "Garruk's Horde", "p2")
    mana(s, R=2)
    with pytest.raises(ActionError):
        cast(s, "Searing Blaze", ["p1", horde.id], target_counts=[1, 1])  # (Alice and Bob's creature: not "a creature that player controls")
    check(s)


@pytest.mark.parametrize("metalcraft", [False, True])
def test_concussive_bolt_metalcraft_creatures_cant_block_even_later_ones(cards, metalcraft):
    s = build(cards, ["Concussive Bolt", "Sol Ring", "Arcane Signet", "Bonesplitter"], ["Grizzly Bears", "Garruk's Horde"])
    bears = put(s, "Grizzly Bears", "p2")
    for n in ["Sol Ring", "Arcane Signet", "Bonesplitter"][: 3 if metalcraft else 2]:
        put(s, n)
    mana(s, R=2, C=3)
    cast(s, "Concussive Bolt", ["p2"])
    answer(s)
    horde = put(s, "Garruk's Horde", "p2")  # (it came later: still can't block, the set isn't locked in)
    assert life(s, "p2") == 36
    for c in (bears, horde):
        assert ("cant_block" in ch(s, c).imposed) == metalcraft
    check(s)


@pytest.mark.parametrize("delirium", [False, True])
def test_to_the_slaughter_delirium_one_of_each(cards, delirium):
    s = build(cards, ["To the Slaughter", "Lightning Bolt", "Rampant Growth", "Sol Ring"], ["Grizzly Bears", "Gideon Jura"])
    bears, gideon = put(s, "Grizzly Bears", "p2"), put(s, "Gideon Jura", "p2")
    act(s, "p2", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    names = ["Lightning Bolt", "Rampant Growth", "Sol Ring"] if delirium else ["Lightning Bolt", "Rampant Growth"]
    act(s, "p1", type="move", card_ids=[card_named(s, n).id for n in names], to={"player": "p1", "zone": "graveyard"})
    to_graveyard(s, 1)  # (a land: four card types with the artifact, three without)
    mana(s, B=1, C=2)
    cast(s, "To the Slaughter", ["p2"])
    answer(s)
    gone = [c for c in (bears, gideon) if s.state.cards[c.id].zone == "p2:graveyard"]
    assert len(gone) == (2 if delirium else 1)
    check(s)


def test_to_the_slaughter_a_creature_planeswalker_cant_be_both_choices(cards):
    """Alice's Gideon is a creature and a planeswalker this turn: as her "creature" she must pick the Bears, so that Gideon is left to be her
    planeswalker (the 2016-04-08 ruling: one of each if able)."""
    s = build(cards, ["To the Slaughter", "Gideon Jura", "Grizzly Bears", "Lightning Bolt", "Rampant Growth", "Sol Ring"])
    gideon, bears = put(s, "Gideon Jura"), put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    act(s, "p1", type="activate_ability", card_id=gideon.id, ability=2)  # ("0: Until end of turn, Gideon Jura becomes a 6/6 … creature …")
    answer(s)
    assert ch(s, gideon).is_creature
    act(s, "p1", type="move", card_ids=[card_named(s, n).id for n in ("Lightning Bolt", "Rampant Growth", "Sol Ring")],
        to={"player": "p1", "zone": "graveyard"})
    to_graveyard(s, 1)
    mana(s, B=1, C=2)
    cast(s, "To the Slaughter", ["p1"])
    answer(s)  # (no choice left: the Bears as the creature, Gideon as the planeswalker)
    assert s.state.cards[gideon.id].zone == "p1:graveyard" and s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("commander", [False, True])
def test_ancestral_communion_copies_while_you_control_your_commander(cards, commander):
    s = build(cards, ["Ancestral Communion", "Grizzly Bears", "Sol Ring"])
    if commander:
        put(s, "Krenko, Mob Boss")
    bears, ring = card_named(s, "Grizzly Bears"), card_named(s, "Sol Ring")
    act(s, "p1", type="move", card_ids=[bears.id, ring.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, G=1, C=1)
    cast(s, "Ancestral Communion", [bears.id])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and "new target" in d.prompt.lower() or d is not None and ring.id in {o.id for o in d.options}:
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.id in ("yes", ring.id)][:1])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[bears.id].zone == "p1:hand"
    assert s.state.cards[ring.id].zone == ("p1:hand" if commander else "p1:graveyard")
    check(s)


@pytest.mark.parametrize("creature", [False, True])
def test_social_snub_may_copy_while_you_control_a_creature(cards, creature):
    """Checked only as it is cast: the copy resolves first and takes Alice's creature, the original still resolves."""
    s = build(cards, ["Social Snub", "Grizzly Bears"], ["Grizzly Bears", "Kami of Ancient Law"])
    if creature:
        put(s, "Grizzly Bears")
    theirs = [put(s, "Grizzly Bears", "p2"), put(s, "Kami of Ancient Law", "p2")]
    mana(s, W=1, B=1, C=1)
    cast(s, "Social Snub")
    asked = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.kind)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if d.kind == "confirm" else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert ("confirm" in asked) == creature
    assert sum(s.state.cards[c.id].zone == "p2:graveyard" for c in theirs) == (2 if creature else 1)
    assert life(s, "p2") == (38 if creature else 39) and life(s, "p1") == (42 if creature else 41)
    check(s)


@pytest.mark.parametrize("bolted", [False, True])
def test_swallow_whole_counter_on_the_creature_tapped_for_its_cost(cards, bolted):
    """The tapped creature gets the counter only while it is still that object (400.7): Bob bolts it in response, the exile still happens (its
    2020-04-17 rulings)."""
    s = build(cards, ["Swallow Whole", "Grizzly Bears"], ["Garruk's Horde", "Lightning Bolt"])
    bears, horde = put(s, "Grizzly Bears"), put(s, "Garruk's Horde", "p2")
    act(s, "p2", type="tap", card_ids=[horde.id])
    if bolted:
        act(s, "p2", type="set_stops", own=["main1"], others=["main1"], smart_pass=False)
    mana(s, W=1)
    cast(s, "Swallow Whole", [horde.id])
    for _ in range(5):  # (the creature to tap for the cost: the Bears, the only one)
        if (d := s.state.rules.decision) is None or s.state.zones.get("stack"):
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert s.state.cards[bears.id].tapped
    if bolted:
        mana(s, "p2", R=1)
        cast(s, "Lightning Bolt", [bears.id], pid="p2")
    answer(s)
    assert s.state.cards[horde.id].zone == "p2:exile"
    assert s.state.cards[bears.id].zone == ("p1:graveyard" if bolted else "p1:battlefield")
    assert s.state.cards[bears.id].counters.get("+1/+1", 0) == (0 if bolted else 1)
    check(s)


def test_thought_distortion_exiles_noncreature_nonland_cards_from_hand_and_graveyard(cards):
    s = build(cards, ["Thought Distortion"], ["Lightning Bolt", "Grizzly Bears", "Counterspell", "Mulldrifter"])
    bolt, bears = to_hand(s, "Lightning Bolt", "p2"), to_hand(s, "Grizzly Bears", "p2")
    counter, drifter = card_named(s, "Counterspell", "p2"), card_named(s, "Mulldrifter", "p2")
    act(s, "p2", type="move", card_ids=[counter.id, drifter.id], to={"player": "p2", "zone": "graveyard"})
    mana(s, B=2, C=4)
    cast(s, "Thought Distortion", ["p2"])
    answer(s)
    assert [s.state.cards[c.id].zone for c in (bolt, bears, counter, drifter)] == ["p2:exile", "p2:hand", "p2:exile", "p2:graveyard"]
    check(s)


def test_qutrub_forayer_mode_exiles_up_to_two_cards_from_one_graveyard(cards):
    """A modal trigger's "from a single graveyard" group (the mode's groups join the ability's, 601.2c / 603.3c): two of Bob's cards, not one of
    each player's; the other mode has no legal target, so it isn't offered (700.2b)."""
    s = build(cards, ["Qutrub Forayer", "Grizzly Bears"], ["Lightning Bolt", "Opt"])
    for pid, names in (("p2", ["Lightning Bolt", "Opt"]), ("p1", ["Grizzly Bears"])):
        act(s, pid, type="move", card_ids=[card_named(s, n, pid).id for n in names], to={"player": pid, "zone": "graveyard"})
    bolt, opt, bears = card_named(s, "Lightning Bolt", "p2"), card_named(s, "Opt", "p2"), card_named(s, "Grizzly Bears")
    mana(s, B=1, C=2)
    cast(s, "Qutrub Forayer")
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and "mode" in d.prompt:
            assert [o.label for o in d.options] == ["Exile up to two target cards from a single graveyard."]
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif d is not None:
            with pytest.raises(ActionError):
                act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id, bolt.id])
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[bolt.id, opt.id])
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert [s.state.cards[c.id].zone for c in (bolt, opt, bears)] == ["p2:exile", "p2:exile", "p1:graveyard"]
    check(s)


def test_exile_into_darkness_only_a_creature_with_mana_value_3_or_less(cards):
    s = build(cards, ["Exile into Darkness"], ["Grizzly Bears", "Garruk's Horde"])
    bears, horde = put(s, "Grizzly Bears", "p2"), put(s, "Garruk's Horde", "p2")
    mana(s, B=1, C=4)
    cast(s, "Exile into Darkness", ["p2"])
    answer(s)  # (no choice: the Bears are the only one, the Horde has mana value 7)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[horde.id].zone == "p2:battlefield"
    check(s)


@pytest.mark.parametrize("name, dealt", [("Lightning Bolt", 1), ("Forest", 0)])
def test_vengeful_rebirth_damage_only_for_a_nonland_card(cards, name, dealt):
    s = build(cards, ["Vengeful Rebirth", "Lightning Bolt"])
    back = card_named(s, name)
    act(s, "p1", type="move", card_ids=[back.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, R=1, G=1, C=4)
    spell = cast(s, "Vengeful Rebirth", [back.id, "p2"], target_counts=[1, 1])
    answer(s)
    assert s.state.cards[back.id].zone == "p1:hand" and s.state.cards[spell.id].zone == "p1:exile"
    assert life(s, "p2") == 40 - dealt
    check(s)


@pytest.mark.parametrize("attackers", [1, 2])
def test_inferno_trap_costs_r_after_two_creatures_dealt_you_damage(cards, attackers):
    from app.rules import alt_costs
    from app.rules import characteristics as chars

    s = build(cards, ["Inferno Trap"], ["Grizzly Bears", "Kami of Ancient Law"])
    theirs = [put(s, "Grizzly Bears", "p2"), put(s, "Kami of Ancient Law", "p2")][:attackers]
    for c in theirs:
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p2")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p1"} for c in theirs])
    until(s, lambda s: s.state.turn.phase == "end_combat" and s.state.rules.priority == "p1")
    assert life(s, "p1") == 40 - 2 * attackers
    trap = to_hand(s, "Inferno Trap")
    offers = alt_costs.offers(s.state, "p1", trap, chars.of(trap, s.cards), s.cards)
    assert bool(offers) == (attackers == 2)  # (two different creatures, its ruling)
    if offers:
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=trap.id, targets=[theirs[0].id], alt_cost=offers[0].key)
        answer(s)
        assert s.state.cards[theirs[0].id].zone == "p2:graveyard"
    check(s)


@pytest.mark.parametrize("kicked", [False, True])
def test_mega_flare_greatest_power_to_each_chosen_creature(cards, kicked):
    s = build(cards, ["Mega Flare", "Grizzly Bears"], ["Garruk's Horde"])
    put(s, "Grizzly Bears")
    horde = put(s, "Garruk's Horde", "p2")
    mana(s, R=3 if kicked else 1, C=5 if kicked else 2)
    cast(s, "Mega Flare", [horde.id], kicker=int(kicked), target_counts=[1])
    answer(s)
    assert s.state.cards[horde.id].damage == (6 if kicked else 2)  # (the kicker's 6/6 Dragon comes first: 608.2c)
    check(s)


@pytest.mark.parametrize("morbid", [False, True])
def test_gruesome_discovery_morbid_you_choose_from_the_revealed_hand(cards, morbid):
    s = build(cards, ["Gruesome Discovery", "Lightning Bolt"], ["Grizzly Bears", "Opt", "Counterspell", "Island"])
    hand = [to_hand(s, n, "p2") for n in ("Opt", "Counterspell", "Island")]
    if morbid:
        bears = put(s, "Grizzly Bears", "p2")
        mana(s, R=1)
        cast(s, "Lightning Bolt", [bears.id])
        answer(s)
    mana(s, B=2, C=2)
    cast(s, "Gruesome Discovery", ["p2"])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            assert d.player == ("p1" if morbid else "p2")
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[hand[1].id, hand[2].id])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert [s.state.cards[c.id].zone for c in hand] == ["p2:hand", "p2:graveyard", "p2:graveyard"]
    check(s)


def test_breaking_wave_swaps_tapped_and_untapped_creatures(cards):
    """Both groups are read before either changes; a stunned creature loses the counter instead of untapping (122.1d)."""
    s = build(cards, ["Breaking Wave", "Grizzly Bears", "Kami of Ancient Law"], ["Garruk's Horde", "Mulldrifter"])
    bears, kami, horde, drifter = put(s, "Grizzly Bears"), put(s, "Kami of Ancient Law"), put(s, "Garruk's Horde", "p2"), put(s, "Mulldrifter", "p2")
    act(s, "p1", type="tap", card_ids=[bears.id])
    act(s, "p2", type="tap", card_ids=[drifter.id])
    act(s, "p2", type="counter", card_ids=[drifter.id], kind="stun", delta=1)
    mana(s, U=2, C=2)
    cast(s, "Breaking Wave")
    answer(s)
    assert [s.state.cards[c.id].tapped for c in (bears, kami, horde, drifter)] == [False, True, True, True]
    assert not s.state.cards[drifter.id].counters.get("stun")
    check(s)


def test_encircling_fissure_prevents_combat_damage_by_that_opponents_creatures(cards):
    """Bob's attackers deal no combat damage to Alice; her own blocker's damage isn't prevented."""
    s = build(cards, ["Encircling Fissure", "Kami of Ancient Law"], ["Grizzly Bears", "Garruk's Horde"])
    kami = put(s, "Kami of Ancient Law")
    bears, horde = put(s, "Grizzly Bears", "p2"), put(s, "Garruk's Horde", "p2")
    for c in (bears, horde):
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p2")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p1"} for c in (bears, horde)])
    until(s, lambda s: s.state.rules.priority == "p1" and s.state.turn.phase == "declare_attackers")
    mana(s, W=1, C=2)
    cast(s, "Encircling Fissure", ["p2"], target_counts=[1, 0])  # (the awaken land group: none, not cast for awaken)
    answer(s)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_blockers")
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": kami.id, "attacker_id": bears.id}])
    until(s, lambda s: s.state.turn.phase == "end_combat")
    assert life(s, "p1") == 40 and s.state.cards[kami.id].damage == 0
    assert s.state.cards[bears.id].zone == "p2:graveyard"  # (the Kami's damage isn't Bob's creature's: 2 kills the Bears)
    check(s)


@pytest.mark.parametrize("how", ["donate", "bounce"])
def test_gusthas_scepter_cards_go_to_the_graveyard_when_you_lose_control(cards, how):
    """Another player gains control of it (Donate: 603.10d, Alice's trigger), or it leaves the battlefield (Capsize): the card exiled face down with
    it goes to its owner's graveyard (the 2004-10-04 ruling; the same wording on Duplicity)."""
    s = build(cards, ["Gustha's Scepter", "Grizzly Bears", "Donate", "Capsize"])
    scepter, bears = put(s, "Gustha's Scepter"), to_hand(s, "Grizzly Bears")
    act(s, "p1", type="activate_ability", card_id=scepter.id, ability=0)
    answer(s, bears.id)
    assert s.state.cards[bears.id].zone == "p1:exile" and s.state.cards[bears.id].face_down
    if how == "donate":
        mana(s, U=1, C=2)
        cast(s, "Donate", ["p2", scepter.id], target_counts=[1, 1])
    else:
        mana(s, U=2, C=1)
        cast(s, "Capsize", [scepter.id])
    answer(s)
    assert s.state.cards[scepter.id].zone == ("p2:battlefield" if how == "donate" else "p1:hand")
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)


def test_display_of_dominance_stops_blue_and_black_spells_of_opponents(cards):
    s = build(cards, ["Display of Dominance", "Grizzly Bears"], ["Capsize", "Lightning Bolt"])
    bears = put(s, "Grizzly Bears")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Display of Dominance").id, modes=[1])
    answer(s)
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.rules.priority == "p2")  # (Bob, in Alice's beginning of combat step)
    mana(s, "p2", U=3)
    with pytest.raises(ActionError):
        cast(s, "Capsize", [bears.id], pid="p2")  # (a blue spell of an opponent: no)
    mana(s, "p2", R=1)
    cast(s, "Lightning Bolt", [bears.id], pid="p2")  # (a red one still may)
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)
