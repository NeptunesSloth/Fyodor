"""Wave 100M: cards whose missing lines spanned several families. Real Oracle text, every scenario checks the replay and a save and a load.

* "Whenever …, you may exile this card from your graveyard. If you do / When you do, …" on an instant (Kozilek's Return, Ugin's Binding,
  Council's Deliberation): 113.6m, the ability works only from the graveyard (it moves the card out of it); the spell itself still resolves.
* Phyrexian Processor: X is the life paid as it entered, as it last existed if it's gone (608.2h).
* Clone Shell: the card it exiled face down (607.2a), seen only by its exiler (406.3); a noncreature one stays exiled face up (its rulings).
* Jace Reawakened: "+1: You may exile … from your hand. If you do, it becomes plotted." (702.170c; Kellan Joins Up's reading).
* Spider-Man 2099: a land played or a spell cast this turn from anywhere other than your hand (graveyard, command zone), 603.4.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand


def rc(name, cost, cmc, types, text, pt=None, colors=(), identity=None, keywords=(), loyalty=None):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    extra |= {"loyalty": loyalty} if loyalty else {}
    return card(name, set_code="tst", number=f"100M-{name[:7]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(identity if identity is not None else colors), keywords=list(keywords), **extra)


EXTRA = [
    rc("Kozilek's Return", "{2}{R}", 3, "Instant", "Devoid (This card has no color.)\nKozilek's Return deals 2 damage to each creature.\nWhenever you "
       "cast an Eldrazi creature spell with mana value 7 or greater, you may exile this card from your graveyard. If you do, this card deals 5 damage "
       "to each creature.", identity="R", keywords=["Devoid"]),
    rc("Ugin's Binding", "{2}{U}", 3, "Instant", "Devoid (This card has no color.)\nReturn target nonland permanent you don't control to its owner's "
       "hand.\nWhenever you cast a colorless spell with mana value 7 or greater, you may exile this card from your graveyard. When you do, return each "
       "nonland permanent you don't control to its owner's hand.", identity="U", keywords=["Devoid"]),
    rc("Council's Deliberation", "{1}{U}", 2, "Instant", "Draw a card.\nWhenever you scry, if you control an Island, you may exile this card from your "
       "graveyard. If you do, draw a card.", colors="U"),
    rc("Phyrexian Processor", "{4}", 4, "Artifact", "As this artifact enters, pay any amount of life.\n{4}, {T}: Create an X/X black Phyrexian Minion "
       "creature token, where X is the life paid as this artifact entered."),
    rc("Clone Shell", "{5}", 5, "Artifact Creature — Shapeshifter", "Imprint — When this creature enters, look at the top four cards of your library, "
       "exile one face down, then put the rest on the bottom of your library in any order.\nWhen this creature dies, turn the exiled card face up. If "
       "it's a creature card, put it onto the battlefield under your control.", ("2", "2"), keywords=["Imprint"]),
    rc("Jace Reawakened", "{U}{U}", 2, "Legendary Planeswalker — Jace", "You can't cast Jace Reawakened during your first, second, or third turns "
       "of the game.\n+1: Draw a card, then discard a card.\n+1: You may exile a nonland card with mana value 3 or less from your hand. If you do, it "
       "becomes plotted.\n−6: Until end of turn, whenever you cast a spell, copy it. You may choose new targets for the copy.", colors="U",
       loyalty="3"),
    rc("Spider-Man 2099", "{U}{R}", 2, "Legendary Creature — Spider Human Hero", "From the Future — You can't cast Spider-Man 2099 during your first, "
       "second, or third turns of the game.\nDouble strike, vigilance\nAt the beginning of your end step, if you've played a land or cast a spell this "
       "turn from anywhere other than your hand, Spider-Man 2099 deals damage equal to his power to any target.", ("2", "3"), colors="UR",
       keywords=["Vigilance", "From the Future", "Double strike"]),
    rc("Banefire", "{X}{R}", 1, "Sorcery", "Banefire deals X damage to any target.\nIf X is 5 or more, this spell can't be countered and the damage "
       "can't be prevented.", colors="R"),
    rc("Tezzeret, Master of the Bridge", "{4}{U}{B}", 6, "Legendary Planeswalker — Tezzeret", "Creature and planeswalker spells you cast have affinity "
       "for artifacts. (They cost {1} less to cast for each artifact you control.)\n+2: Tezzeret deals X damage to each opponent, where X is the number "
       "of artifacts you control. You gain X life.\n−3: Return target artifact card from your graveyard to your hand.\n−8: Exile the top ten cards of "
       "your library. Put all artifact cards from among them onto the battlefield.", colors="UB", loyalty="5"),
    rc("Nissa, Ascended Animist", "{3}{G}{G}{G/P}{G/P}", 7, "Legendary Planeswalker — Nissa", "Compleated ({G/P} can be paid with {G} or 2 life. For "
       "each {G/P} paid with life, this planeswalker enters with two fewer loyalty counters.)\n+1: Create an X/X green Phyrexian Horror creature token, "
       "where X is Nissa's loyalty.\n−1: Destroy target artifact or enchantment.\n−7: Until end of turn, creatures you control get +1/+1 for each "
       "Forest you control and gain trample.", colors="G", loyalty="7", keywords=["Compleated"]),
    rc('Descend upon the Sinful', '{4}{W}{W}', 6, 'Sorcery', 'Exile all creatures.\nDelirium — Create a 4/4 white Angel creature token with flying if there are '
       'four or more card types among cards in your graveyard.', colors='W', keywords=['Delirium']),
    rc('Hymn of the Faller', '{1}{B}', 2, 'Sorcery', 'Surveil 1, then you draw a card and lose 1 life. (To surveil 1, look at the top card of your library. '
       'You may put it into your graveyard.)\nVoid — If a nonland permanent left the battlefield this turn or a spell was warped this turn, draw another '
       'card.', colors='B', keywords=['Surveil', 'Void']),
    rc('Blood for Bones', '{3}{B}', 4, 'Sorcery', 'As an additional cost to cast this spell, sacrifice a creature.\nReturn a creature card from your '
       'graveyard to the battlefield, then return another creature card from your graveyard to your hand.', colors='B'),
    rc('Under the Skin', '{2}{G}', 3, 'Sorcery', "Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a "
       "2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nYou may return a permanent "
       "card from your graveyard to your hand.", colors='G', keywords=['Manifest', 'Manifest dread']),
    card("Startled Awake // Persistent Nightmare", set_code="tst", number="100M-startled", layout="transform", mana_cost=None, cmc=4.0,
         type_line="Sorcery // Creature — Nightmare", colors=["U"], color_identity=["U"], image_uris=None, card_faces=[
             {"object": "card_face", "name": "Startled Awake", "mana_cost": "{2}{U}{U}", "type_line": "Sorcery", "colors": ["U"],
              "oracle_text": "Target opponent mills thirteen cards.\n{3}{U}{U}: Put this card from your graveyard onto the battlefield transformed. "
                             "Activate only as a sorcery."},
             {"object": "card_face", "name": "Persistent Nightmare", "mana_cost": "", "type_line": "Creature — Nightmare", "colors": ["U"],
              "oracle_text": "Skulk (This creature can't be blocked by creatures with greater power.)\nWhen this creature deals combat damage to a "
                             "player, return it to its owner's hand.", "power": "1", "toughness": "1"}]),
    rc('Malicious Affliction', '{B}{B}', 2, 'Instant', 'Morbid — When you cast this spell, if a creature died this turn, you may copy Malicious Affliction '
       'and may choose a new target for the copy.\nDestroy target nonblack creature.', colors='B', keywords=['Morbid']),
    rc('Bygone Marvels', '{G}{G}', 2, 'Sorcery', 'Descend 8 — When you cast this spell, if there are eight or more permanent cards in your graveyard, copy '
       'this spell twice. You may choose new targets for the copies.\nReturn target permanent card from your graveyard to your hand. Exile Bygone '
       'Marvels.', colors='G', keywords=['Descend']),
    rc('Icebreaker Kraken', '{10}{U}{U}', 12, 'Snow Creature — Kraken', "Affinity for snow lands (This spell costs {1} less to cast for each snow land you "
       "control.)\nWhen this creature enters, artifacts and creatures target opponent controls don't untap during that player's next untap step.\n"
       "Return three snow lands you control to their owner's hand: Return this creature to its owner's hand.", ('8', '8'), colors='U', keywords=['Affinity']),
    rc('Risk Factor', '{2}{R}', 3, 'Instant', "Target opponent may have Risk Factor deal 4 damage to them. If that player doesn't, you draw three cards.\n"
       "Jump-start (You may cast this card from your graveyard by discarding a card in addition to paying its other costs. Then exile this card.)",
       colors='R', keywords=['Jump', 'Jump-start']),
    rc('Dark Dabbling', '{2}{B}', 3, 'Instant', 'Regenerate target creature. Draw a card. (The next time the creature would be destroyed this turn, instead '
       'tap it, remove it from combat, and heal all damage on it.)\nSpell mastery — If there are two or more instant and/or sorcery cards in your '
       'graveyard, also regenerate each other creature you control.', colors='B', keywords=['Heal', 'Regenerate', 'Spell mastery']),
    rc('Savage Punch', '{1}{G}', 2, 'Sorcery', "Target creature you control fights target creature you don't control.\nFerocious — The creature you "
       "control gets +2/+2 until end of turn before it fights if you control a creature with power 4 or greater.", colors='G', keywords=['Ferocious', 'Fight']),
]
HELPERS = [
    rc("Ulamog's Crusher", "{8}", 8, "Creature — Eldrazi", "Annihilator 2 (Whenever this creature attacks, defending player sacrifices two permanents "
       "of their choice.)\nThis creature attacks each combat if able.", ("8", "8"), keywords=["Annihilator"]),
    rc("Shatter", "{1}{R}", 2, "Instant", "Destroy target artifact.", colors="R"),
    rc("Crucible of Worlds", "{3}", 3, "Artifact", "You may play lands from your graveyard."),
    rc("Hero's Downfall", "{1}{B}{B}", 3, "Instant", "Destroy target creature or planeswalker.", colors="B"),
    rc('Snow-Covered Island', '', 0, 'Basic Snow Land — Island', '({T}: Add {U}.)', identity='U'),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *HELPERS], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *prefer, limit=60):
    """Resolve everything; a decision is answered with the first option whose label holds one of ``prefer``, else the first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = [o.id for o in d.options if any(p in o.label for p in prefer)][:1] or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_graveyard(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


@pytest.mark.parametrize("pay", [True, False])
def test_kozileks_return_works_only_from_the_graveyard(cards, pay):
    s = build(cards, ["Kozilek's Return", "Ulamog's Crusher", "Grizzly Bears"], ["Twisted Abomination"])
    finks = put(s, "Twisted Abomination", "p2")
    ret = to_hand(s, "Kozilek's Return")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=ret.id)
    answer(s)
    assert s.state.cards[finks.id].damage == 2 and s.state.cards[ret.id].zone == "p1:graveyard"
    bears = put(s, "Grizzly Bears")
    crusher = to_hand(s, "Ulamog's Crusher")
    mana(s, C=8)
    act(s, "p1", type="cast_spell", card_id=crusher.id)
    assert s.state.zones["stack"]  # (the trigger above the Crusher: it resolves first, the ruling)
    answer(s, "Pay" if pay else "Decline", "Don't")
    assert s.state.cards[crusher.id].zone == "p1:battlefield" and s.state.cards[crusher.id].damage == 0
    if pay:
        assert s.state.cards[ret.id].zone == "p1:exile" and s.state.cards[bears.id].zone == "p1:graveyard"
    else:
        assert s.state.cards[ret.id].zone == "p1:graveyard" and s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_kozileks_return_in_hand_doesnt_trigger(cards):
    s = build(cards, ["Kozilek's Return", "Ulamog's Crusher", "Grizzly Bears"])
    to_hand(s, "Kozilek's Return")
    bears = put(s, "Grizzly Bears")
    mana(s, C=8)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ulamog's Crusher").id)
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].damage == 0
    check(s)


def test_ugins_binding_bounces_then_returns_each_from_the_graveyard(cards):
    s = build(cards, ["Ugin's Binding", "Ulamog's Crusher", "Grizzly Bears"], ["Kitchen Finks", "Llanowar Elves", "Island"])
    finks, elves, land = put(s, "Kitchen Finks", "p2"), put(s, "Llanowar Elves", "p2"), put(s, "Island", "p2")
    bears = put(s, "Grizzly Bears")
    binding = to_hand(s, "Ugin's Binding")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=binding.id, targets=[finks.id])
    answer(s)
    assert s.state.cards[finks.id].zone == "p2:hand" and s.state.cards[binding.id].zone == "p1:graveyard"
    mana(s, C=8)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ulamog's Crusher").id)
    answer(s, "Pay")
    assert s.state.cards[binding.id].zone == "p1:exile"
    assert s.state.cards[elves.id].zone == "p2:hand" and s.state.cards[land.id].zone == "p2:battlefield"
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("island", [True, False])
def test_councils_deliberation_draws_again_on_a_scry_with_an_island(cards, island):
    s = build(cards, ["Council's Deliberation", "Opt", "Island"])
    if island:
        put(s, "Island")
    council = to_hand(s, "Council's Deliberation")
    mana(s, U=2)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=council.id)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand  # (cast one, drew one)
    mana(s, U=1)
    opt = to_hand(s, "Opt")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=opt.id)
    answer(s, "Pay")
    assert s.state.cards[council.id].zone == ("p1:exile" if island else "p1:graveyard")
    assert len(s.state.zones["p1:hand"]) == hand + island  # (Opt's card for itself, and the graveyard's one only with an Island)
    check(s)


def choose(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


@pytest.mark.parametrize("gone", [False, True])
def test_phyrexian_processor_makes_minions_the_size_of_the_life_paid(cards, gone):
    s = build(cards, ["Phyrexian Processor", "Shatter"])
    proc = to_hand(s, "Phyrexian Processor")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=proc.id)
    until(s, lambda s: s.state.rules.decision is not None)
    choose(s, ["6"])
    answer(s)
    assert s.state.players["p1"].life == 34 and s.state.cards[proc.id].zone == "p1:battlefield"
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=proc.id, ability=1)
    if gone:  # (destroyed in response: the life paid as it last existed, 608.2h)
        mana(s, R=2)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Shatter").id, targets=[proc.id])
        until(s, lambda s: s.state.cards[proc.id].zone != "p1:battlefield")
        assert s.state.cards[proc.id].zone == "p1:graveyard"  # (Shatter above the ability: LIFO, 405.5)
    answer(s)
    minion = next(c for c in s.state.cards.values() if c.name == "Phyrexian Minion")
    assert pt(s, "Phyrexian Minion") == (6, 6) and minion.controller == "p1"
    check(s)


def test_clone_shell_hides_a_card_then_puts_a_creature_onto_the_battlefield(cards):
    from app.game.visibility import can_see

    s = build(cards, ["Clone Shell", "Grizzly Bears", "Opt", "Llanowar Elves", "Murder"])
    shell = to_hand(s, "Clone Shell")
    mana(s, C=5)
    act(s, "p1", type="cast_spell", card_id=shell.id)
    until(s, lambda s: s.state.rules.decision is not None)
    bears = card_named(s, "Grizzly Bears")
    d = s.state.rules.decision
    assert d.player == "p1" and bears.id in [o.id for o in d.options] and d.min_choices == 1  # (one must be exiled: the ruling)
    choose(s, [bears.id])
    answer(s)
    b = s.state.cards[bears.id]
    assert b.zone == "p1:exile" and b.face_down and can_see(s.state, b, "p1") and not can_see(s.state, b, "p2")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[shell.id])
    answer(s)
    b = s.state.cards[bears.id]
    assert s.state.cards[shell.id].zone == "p1:graveyard" and b.zone == "p1:battlefield" and not b.face_down and b.controller == "p1"
    check(s)


def test_clone_shell_leaves_a_noncreature_card_face_up_in_exile(cards):
    s = build(cards, ["Clone Shell", "Opt", "Grizzly Bears", "Murder"])
    shell = to_hand(s, "Clone Shell")
    mana(s, C=5)
    act(s, "p1", type="cast_spell", card_id=shell.id)
    until(s, lambda s: s.state.rules.decision is not None)
    opt = card_named(s, "Opt")
    choose(s, [opt.id])
    answer(s)
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[shell.id])
    answer(s)
    o = s.state.cards[opt.id]
    assert o.zone == "p1:exile" and not o.face_down  # (the ruling: it simply remains in exile face up)
    check(s)


def test_jace_reawakened_plots_a_cheap_nonland_card_from_your_hand(cards):
    s = build(cards, ["Jace Reawakened", "Grizzly Bears", "Ulamog's Crusher"])
    jace = put(s, "Jace Reawakened")
    act(s, "p1", type="set_counter", card_id=jace.id, kind="loyalty", value=3)
    bears, crusher, land = to_hand(s, "Grizzly Bears"), to_hand(s, "Ulamog's Crusher"), to_hand(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=jace.id, ability=2)
    offered: list[str] = []
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            offered += [getattr(o, "card_id", None) or o.id for o in d.options]
            choose(s, [o.id for o in d.options if o.id == "pay" or getattr(o, "card_id", None) == bears.id or o.id == bears.id][:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert crusher.id not in offered and land.id not in offered  # (mana value 8; a land)
    assert s.state.cards[bears.id].zone == "p1:exile" and [p for p in s.state.rules.permissions if p.card == bears.id and p.free and p.sorcery]
    assert s.state.cards[jace.id].counters.get("loyalty") == 4
    check(s)


def to_next_turn(s, limit=300):
    """Play through this turn's end step (Bob is its only target choice) into the next turn's first main phase."""
    turn = s.state.turn.number
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.number > turn and s.state.turn.phase == "main1" and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            choose(s, [o.id for o in d.options if o.id == "p2"][:1] or [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


@pytest.mark.parametrize("how", ["flashback", "commander", "graveyard land", "hand"])
def test_spider_man_2099_strikes_after_a_play_from_anywhere_but_your_hand(cards, how):
    s = build(cards, ["Spider-Man 2099", "Firebolt", "Crucible of Worlds", "Mountain"])
    put(s, "Spider-Man 2099")
    if how == "flashback":
        fb = card_named(s, "Firebolt")
        act(s, "p1", type="move", card_ids=[fb.id], to={"zone": "graveyard"})
        mana(s, R=1, C=4)
        act(s, "p1", type="cast_spell", card_id=fb.id, targets=["p2"])
    elif how == "commander":
        mana(s, R=2, C=2)
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Krenko, Mob Boss").id)
    elif how == "graveyard land":
        put(s, "Crucible of Worlds")
        mountain = card_named(s, "Mountain")
        act(s, "p1", type="move", card_ids=[mountain.id], to={"zone": "graveyard"})
        act(s, "p1", type="play_land", card_id=mountain.id)
        assert s.state.cards[mountain.id].zone == "p1:battlefield"
    else:
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Firebolt").id, targets=["p2"])
        act(s, "p1", type="play_land", card_id=to_hand(s, "Mountain").id)
    answer(s)
    life = s.state.players["p2"].life
    to_next_turn(s)
    assert s.state.players["p2"].life == life - (0 if how == "hand" else 2)  # (his power, 2)
    check(s)


@pytest.mark.parametrize("x", [4, 5])
def test_banefire_with_x_5_or_more_cant_be_countered_or_prevented(cards, x):
    s = build(cards, ["Banefire"], ["Counterspell", "Test Ward"])
    put(s, "Test Ward", "p2")  # ("Prevent all damage that would be dealt to you.")
    act(s, "p2", type="set_prefs", response="on")
    fire = to_hand(s, "Banefire")
    mana(s, R=1, C=x)
    act(s, "p1", type="cast_spell", card_id=fire.id, targets=["p2"], x_value=x)
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Counterspell", "p2").id, targets=[fire.id])
    answer(s)
    assert s.state.cards[fire.id].zone == "p1:graveyard" and s.state.players["p2"].life == (35 if x == 5 else 40)  # (countered, or its 5)
    check(s)


def test_banefire_x_4_is_prevented(cards):
    s = build(cards, ["Banefire"], ["Test Ward"])
    put(s, "Test Ward", "p2")
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Banefire").id, targets=["p2"], x_value=4)
    answer(s)
    assert s.state.players["p2"].life == 40
    check(s)


def test_tezzeret_master_of_the_bridge_drains_by_artifacts(cards):
    s = build(cards, ["Tezzeret, Master of the Bridge", "Sol Ring", "Phyrexian Processor"])
    tez = put(s, "Tezzeret, Master of the Bridge")
    put(s, "Sol Ring")
    put(s, "Phyrexian Processor")
    act(s, "p1", type="activate_ability", card_id=tez.id, ability=1)
    answer(s, "0")
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == 42  # (two artifacts)
    check(s)


def test_tezzeret_master_of_the_bridge_puts_the_exiled_artifacts_onto_the_battlefield(cards):
    s = build(cards, ["Tezzeret, Master of the Bridge", "Sol Ring", "Phyrexian Processor", "Grizzly Bears", "Shatter"])
    tez = put(s, "Tezzeret, Master of the Bridge")
    act(s, "p1", type="set_counter", card_id=tez.id, kind="loyalty", value=8)
    lib = list(s.state.zones["p1:library"])
    top = lib[:10]
    act(s, "p1", type="activate_ability", card_id=tez.id, ability=3)
    answer(s, "0")
    proc, bears = card_named(s, "Phyrexian Processor"), card_named(s, "Grizzly Bears")
    assert proc.id in top and bears.id in top
    assert s.state.cards[proc.id].zone == "p1:battlefield" and s.state.cards[bears.id].zone == "p1:exile"
    assert all(s.state.cards[c].zone in ("p1:exile", "p1:battlefield") for c in top)
    check(s)


def test_nissa_ascended_animist_makes_a_horror_of_her_loyalty_and_pumps_by_forests(cards):
    s = build(cards, ["Nissa, Ascended Animist", "Grizzly Bears", "Llanowar Elves", "Hero's Downfall"])
    nissa = put(s, "Nissa, Ascended Animist")
    act(s, "p1", type="set_counter", card_id=nissa.id, kind="loyalty", value=3)
    act(s, "p1", type="activate_ability", card_id=nissa.id, ability=1)
    mana(s, B=2, C=1)  # (destroyed in response: her loyalty as she last existed, 4 — the cost was paid, 606.4; its ruling)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Hero's Downfall").id, targets=[nissa.id])
    answer(s)
    assert s.state.cards[nissa.id].zone == "p1:graveyard" and pt(s, "Phyrexian Horror") == (4, 4)
    check(s)


def test_nissa_ascended_animist_ultimate_counts_forests_once(cards):
    s = build(cards, ["Nissa, Ascended Animist", "Grizzly Bears", "Llanowar Elves"], forests=12)
    nissa = put(s, "Nissa, Ascended Animist")
    act(s, "p1", type="set_counter", card_id=nissa.id, kind="loyalty", value=7)
    bears = put(s, "Grizzly Bears")
    forests = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"]
    for f in forests[:2]:
        act(s, "p1", type="move", card_ids=[f], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=nissa.id, ability=3)
    answer(s)
    assert pt(s, "Grizzly Bears") == (4, 4)
    act(s, "p1", type="move", card_ids=[forests[2]], to={"player": "p1", "zone": "battlefield"})
    put(s, "Llanowar Elves")  # (not a creature you controlled as it resolved: 611.2c)
    assert pt(s, "Grizzly Bears") == (4, 4) and pt(s, "Llanowar Elves") == (1, 1)
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    assert "trample" in plan.ch(s.state.cards[bears.id]).keywords
    check(s)


def run(s, *picks, limit=80):
    """Resolve everything; the n-th decision takes the options its pick names (ids, card ids or labels), else the first options."""
    todo, seen = list(picks), []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            want = set(todo.pop(0)) if todo else set()
            seen.append((d.kind, d.player, [(o.id, o.label) for o in d.options]))
            ids = [o.id for o in d.options if want & {o.id, o.label, getattr(o, "card_id", None)}][: max(1, d.max_choices or 1)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return seen
    raise AssertionError(f"never settled: {seen}")


def zone(s, c):
    return s.state.cards[c.id].zone


@pytest.mark.parametrize("delirium", [True, False])
def test_descend_upon_the_sinful_counts_types_after_the_exile(cards, delirium):
    s = build(cards, ["Descend upon the Sinful", "Grizzly Bears", "Sol Ring", "Lightning Bolt", "Ulamog's Crusher"], ["Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves", "p2")
    for name in ("Forest", "Lightning Bolt", "Ulamog's Crusher", *(["Sol Ring"] if delirium else [])):
        to_graveyard(s, name)  # (land, instant, creature: the spell itself doesn't count, its ruling)
    mana(s, W=2, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Descend upon the Sinful").id)
    run(s)
    assert zone(s, bears) == "p1:exile" and zone(s, elves) == "p2:exile"
    assert [c.name for c in s.state.cards.values() if c.name == "Angel" and c.zone == "p1:battlefield"] == (["Angel"] if delirium else [])
    check(s)


@pytest.mark.parametrize("left", [True, False])
def test_hymn_of_the_faller_draws_another_after_a_nonland_permanent_left(cards, left):
    s = build(cards, ["Hymn of the Faller", "Grizzly Bears", "Murder"])
    if left:
        mana(s, B=3)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[put(s, "Grizzly Bears").id])
        run(s)
    hymn = to_hand(s, "Hymn of the Faller")
    hand = len(s.state.zones["p1:hand"])
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=hymn.id)
    run(s)
    assert s.state.players["p1"].life == 39 and len(s.state.zones["p1:hand"]) == hand - 1 + 1 + left
    check(s)


def test_blood_for_bones_may_return_the_sacrificed_creature(cards):
    s = build(cards, ["Blood for Bones", "Grizzly Bears", "Ulamog's Crusher"])
    bears = put(s, "Grizzly Bears")
    crusher = to_graveyard(s, "Ulamog's Crusher")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Blood for Bones").id)
    run(s, [crusher.id])  # (the other is the only one left for the hand)
    assert zone(s, bears) == "p1:hand" and zone(s, crusher) == "p1:battlefield"
    check(s)


def test_under_the_skin_may_return_the_card_the_dread_milled(cards):
    s = build(cards, ["Under the Skin", "Grizzly Bears", "Sol Ring"])
    skin = to_hand(s, "Under the Skin")
    bears, ring = card_named(s, "Grizzly Bears"), card_named(s, "Sol Ring")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=skin.id)
    run(s, [bears.id], [ring.id])
    assert zone(s, bears) == "p1:battlefield" and s.state.cards[bears.id].face_down and zone(s, ring) == "p1:hand"
    check(s)


def test_startled_awake_mills_then_returns_transformed_from_the_graveyard(cards):
    s = build(cards, ["Startled Awake // Persistent Nightmare"])
    awake = to_hand(s, "Startled Awake // Persistent Nightmare")
    library = len(s.state.zones["p2:library"])
    mana(s, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=awake.id, targets=["p2"])
    run(s)
    assert len(s.state.zones["p2:library"]) == max(0, library - 13) and zone(s, awake) == "p1:graveyard"
    mana(s, U=2, C=3)
    act(s, "p1", type="activate_ability", card_id=awake.id, ability=1)
    run(s)
    a = s.state.cards[awake.id]
    assert a.zone == "p1:battlefield" and a.face == 1
    check(s)


@pytest.mark.parametrize("died", [True, False])
def test_malicious_affliction_copies_itself_only_after_a_death(cards, died):
    s = build(cards, ["Malicious Affliction", "Murder"], ["Llanowar Elves", "Kitchen Finks", "Monastery Swiftspear"])
    elves, finks, swift = (put(s, n, "p2") for n in ("Llanowar Elves", "Kitchen Finks", "Monastery Swiftspear"))
    if died:
        mana(s, B=3)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[swift.id])
        run(s)
    mana(s, B=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Malicious Affliction").id, targets=[elves.id])
    assert len(s.state.zones["stack"]) == (2 if died else 1)  # (an intervening "if": no trigger at all, 603.4)
    act(s, "p1", type="set_prefs", hold_priority=False)
    run(s, ["yes"], [finks.id])
    assert zone(s, elves) == "p2:graveyard"
    f = s.state.cards[finks.id]
    assert (f.zone != "p2:battlefield" or bool(f.counters.get("-1/-1"))) == died  # (the copy's new target; persist brings it back)
    check(s)


@pytest.mark.parametrize("descend", [True, False])
def test_bygone_marvels_copies_twice_with_eight_permanent_cards(cards, descend):
    s = build(cards, ["Bygone Marvels", "Grizzly Bears", "Sol Ring", "Opt"], forests=9)
    gy = [card_named(s, "Grizzly Bears"), card_named(s, "Sol Ring")] + [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:5 + descend]
    for c in gy:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    to_graveyard(s, "Opt")  # (an instant: not a permanent card)
    marvels = to_hand(s, "Bygone Marvels")
    mana(s, G=2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=marvels.id, targets=[gy[0].id])
    assert len(s.state.zones["stack"]) == (2 if descend else 1)  # (603.4: no trigger with seven)
    act(s, "p1", type="set_prefs", hold_priority=False)
    run(s, ["choose"], [gy[1].id], [gy[2].id])
    back = [c for c in gy if zone(s, c) == "p1:hand"]
    assert len(back) == (3 if descend else 1) and zone(s, marvels) == "p1:exile"
    check(s)


def test_icebreaker_kraken_costs_less_per_snow_land_and_freezes_artifacts_and_creatures(cards):
    s = build(cards, ["Icebreaker Kraken", *["Snow-Covered Island"] * 1], ["Sol Ring", "Llanowar Elves", "Island"])
    snow = card_named(s, "Snow-Covered Island")
    act(s, "p1", type="move", card_ids=[snow.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="tap", card_ids=[snow.id])  # (tapped, it still counts: "each snow land you control")
    ring, elves, island = put(s, "Sol Ring", "p2"), put(s, "Llanowar Elves", "p2"), put(s, "Island", "p2")
    act(s, "p2", type="tap", card_ids=[ring.id, elves.id, island.id])
    mana(s, U=2, C=9)  # ({10}{U}{U}, one snow land: {1} less)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Icebreaker Kraken").id)
    run(s, ["p2"])
    assert s.state.cards[card_named(s, "Icebreaker Kraken").id].zone == "p1:battlefield"
    to_next_turn(s)
    assert s.state.turn.active_player == "p2"
    assert s.state.cards[ring.id].tapped and s.state.cards[elves.id].tapped and not s.state.cards[island.id].tapped
    check(s)


def three(cards, mine=()):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (10, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    carol = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


@pytest.mark.parametrize("take", [True, False])
def test_risk_factor_asks_only_the_target_opponent(cards, take):
    s = three(cards, ["Risk Factor"])
    risk = to_hand(s, "Risk Factor")
    hand = len(s.state.zones["p1:hand"])
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=risk.id, targets=["p3"])
    seen = run(s, ["pay" if take else "decline"])
    assert [p for _, p, _ in seen] == ["p3"]
    assert s.state.players["p3"].life == (36 if take else 40) and len(s.state.zones["p1:hand"]) == hand - 1 + (0 if take else 3)
    check(s)


@pytest.mark.parametrize("mastery", [True, False])
def test_dark_dabbling_also_shields_each_other_creature_with_spell_mastery(cards, mastery):
    s = build(cards, ["Dark Dabbling", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Opt"], ["Kitchen Finks"])
    bears, elves, finks = put(s, "Grizzly Bears"), put(s, "Llanowar Elves"), put(s, "Kitchen Finks", "p2")
    if mastery:
        to_graveyard(s, "Lightning Bolt")
        to_graveyard(s, "Opt")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Dark Dabbling").id, targets=[bears.id])
    run(s)
    shields = {c.name: s.state.rules.regen_shields.get(s.state.rules.object_id(c.id), 0) for c in (bears, elves, finks)}
    assert shields == {"Grizzly Bears": 1, "Llanowar Elves": 1 if mastery else 0, "Kitchen Finks": 0}  # (the target once: "each other")
    check(s)


@pytest.mark.parametrize("ferocious", [True, False])
def test_savage_punch_pumps_before_the_fight_with_ferocious(cards, ferocious):
    s = build(cards, ["Savage Punch", "Grizzly Bears", "Twisted Abomination"], ["Hundred-Talon Kami"])
    bears, kami = put(s, "Grizzly Bears"), put(s, "Hundred-Talon Kami", "p2")
    if ferocious:
        put(s, "Twisted Abomination")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Savage Punch").id)
    run(s, [bears.id], [kami.id])
    assert zone(s, bears) == ("p1:battlefield" if ferocious else "p1:graveyard") and zone(s, kami) == ("p2:graveyard" if ferocious else "p2:battlefield")
    check(s)
