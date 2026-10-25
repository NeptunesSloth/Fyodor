"""Wave 100B: more "if you do / this way" riders (CR 2026-09-25), real Oracle text (tests/fixtures/wave100b_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* Rowen, Primitive Etchings, Keranos, God of Storms - "Reveal the first card you draw each turn. Whenever you reveal a basic land card this
  way, draw a card." (701.20a, 121.2: only the turn's first card drawn; the trigger waits until the draw is done, 603.3 - Rowen 2004-10-04;
  two Etchings reveal one card and both trigger - 2004-10-04; Keranos: "on each of your turns").
* Devouring Sugarmaw - "you may sacrifice an artifact, enchantment, or token. If you don't, tap this creature." (118.12: a token of any type).
* Reign of Terror - "Destroy all green creatures or all white creatures. They can't be regenerated. You lose 2 life for each creature that
  died this way." (608.2d: chosen as it resolves; 701.19c).
* Kellan Joins Up - "you may exile a nonland card with mana value 3 or less from your hand. If you do, it becomes plotted." (118.12: the exiled
  card is the payment's, 400.7j; 702.170c-d: cast free from exile on a later turn).
* Ego Drain, Specter's Shriek - "If you don't control a Faerie, exile a card from your hand." / "If you do, that player exiles that card. If a
  nonblack card is exiled this way, exile a card from your hand." (608.2d: chosen as it resolves, in private; an empty hand exiles nothing -
  2019-10-04).
* Gargantuan Gorilla - "you may sacrifice a Forest. If you sacrifice a snow Forest this way, … If you don't sacrifice a Forest, sacrifice this
  creature and it deals 7 damage to you." (701.21a; the sacrificed creature is the damage's source as it last existed, 608.2h).
* Werewolf Ransacker - "you may destroy target artifact. If that artifact is put into a graveyard this way, this creature deals 3 damage to
  that artifact's controller." (exiled instead: no damage - 2013-07-01).
* Metathran Aerostat - "You may put a creature card with mana value X from your hand onto the battlefield. If you do, return this creature to
  its owner's hand." (107.3a: X as announced; 118.12).
* Fold into Aether - "If that spell is countered this way, its controller may put a creature card from their hand onto the battlefield." (the
  countered spell's controller chooses, 608.2h).
* Swift Silence - "Counter all other spells. Draw a card for each spell countered this way." (701.6a).
* Innocuous Researcher - "you may untap all lands you control. If you do, you can't cast spells until your next turn." (603.5; 611.2b - the
  2024-02-02 ruling).
* Koya, Death from Above - "At the beginning of the next end step, you may pay {3}{B}. If you don't, return that card …" (118.12a).
* Auriok Survivors - "you may return target Equipment card from your graveyard to the battlefield. If you do, you may attach it to this
  creature." (603.5; 701.3a).
* Vanish into Memory - "… return that card to the battlefield under its owner's control. If you do, discard cards equal to that creature's
  toughness." (the returned creature's; a token never returns - the 2017-03-14 rulings).
* Dakra Mystic - "You may put the revealed cards into their owners' graveyards. If you don't, each player draws a card." (2014-04-26).
* Doors of Durin - "Until your next turn, it gains trample if you control a Dwarf and hexproof if you control an Elf." (608.2c).
* Lat-Nam's Legacy - "Shuffle a card from your hand into your library. If you do, draw two cards at the beginning of the next turn's upkeep."
  (an empty hand: no draws - 2008-10-01).
* Primal Surge - "… If it's a permanent card, you may put it onto the battlefield. If you do, repeat this process." (110.4a; the 2012-05-01
  rulings: it ends at a nonpermanent card or one not put).
* Locke, Treasure Hunter - "Until end of turn, you may cast a spell from among those cards." (every milled card; the 2025-06-06 rulings).
* Devouring Hellion - "you may sacrifice any number of creatures and/or planeswalkers. If you do, it enters with twice that many +1/+1
  counters on it." (devour 2 for both kinds, 702.82a).
* Deathbonnet Hulk - "you may exile a card from a graveyard. If a creature card was exiled this way, put a +1/+1 counter on this creature."
  (chosen as it resolves, any graveyard).
* Invasion of Kaldheim - "exile all cards from your hand, then draw that many cards. Until the end of your next turn, you may play cards
  exiled this way." ("that many": the cards exiled).
* Manabond - "you may reveal your hand and put all land cards from it onto the battlefield. If you do, discard your hand." (2004-10-04).
* Wicked Guardian - "you may have it deal 2 damage to another creature you control. If you do, draw a card." (chosen as it resolves;
  the 2019-10-04 rulings).
* Phenomenon Investigators - "you may return a nonland permanent you own to your hand. If you do, draw a card." (108.3: owned, whoever controls).
* Clash of Elements - "Its owner may put it on top of their library. If they do, Clash of Elements deals 2 damage to them. …" (the owner's choice).
* Theorist's Sanctum - "As this land enters, you may behold a Jace. If you don't, this land enters tapped." (701.4a: a Jace card in your hand
  or a Jace you control).
* Hedron Alignment - "If you do, you win the game if you own a card named Hedron Alignment in exile, in your hand, in your graveyard, and on the
  battlefield." / Atemsis - "If cards with at least six different mana values are revealed this way, that player loses the game." (rulings).
* Rescuer Sphinx - "As this creature enters, you may return a nonland permanent you control to its owner's hand. If you do, this creature
  enters with a +1/+1 counter on it." (614.12a; one already on the battlefield - 2019-05-03).
* Veteran's Voice - "Tap enchanted creature: Target creature other than the creature tapped this way gets +2/+1 until end of turn."
* Fishing Gear - "If it's a permanent card, you may put it onto the battlefield under your control. If you don't, create a 1/1 blue Fish
  creature token." (a nonpermanent or a declined card: the Fish - 2025-10-02).
* Moonring Mirror - "you may exile all cards from your hand face down. If you do, put all other cards you own exiled with this artifact into
  your hand." (both abilities' cards; not the ones just exiled - 2004-12-01).
* Read the Runes - "For each card drawn this way, discard a card unless you sacrifice a permanent." (sacrifice any, then discard the rest at
  once - 2004-10-04). Rally the Horde - "If the last card exiled isn't a land card, repeat this process. Create a 1/1 red Warrior creature
  token for each nonland card exiled this way."
* Long Rest - "If eight or more cards were returned to your hand this way, your life total becomes equal to your starting life total." (103.4)
* Bringer of the Last Gift - "Then each player returns all creature cards from their graveyard that weren't put there this way to the
  battlefield." (owners' control; not the cards just sacrificed).
* Vault 101: Birthday Party - "If an Equipment is put onto the battlefield this way, you may attach it to a creature you control." (701.3a)
* Inferno of the Star Mounts - "When its power becomes 20 this way, it deals 20 damage to any target." (exactly 20, from this ability - the
  2021-07-23 rulings).
* Mr. Foxglove - "draw cards equal to the number of cards in defending player's hand minus the number of cards in your hand. If you didn't
  draw cards this way, you may put a creature card from your hand onto the battlefield." (0 or less: none - 2024-07-26).
* Call the Spirit Dragons - "for each color, put a +1/+1 counter on a Dragon you control of that color. If you put +1/+1 counters on five
  Dragons this way, you win the game." (five different Dragons - 2025-04-04).
* Holistic Wisdom - "Return target card from your graveyard to your hand if it shares a card type with the card exiled this way." (the cost's)
* Wernog, Rider's Chaplain - "each opponent may investigate. Each opponent who doesn't loses 1 life. You investigate X times, where X is one
  plus the number of opponents who investigated this way." (101.4).
* Liege of the Hollows - "each player may pay any amount of mana. Then each player creates a number of 1/1 green Squirrel creature tokens
  equal to the amount of mana they paid this way." (active player first, the tokens at once - 2008-04-01).
* Hellfire - "deals X plus 3 damage to you, where X is the number of creatures that died this way." (a destroyed token counts, a creature a
  replacement effect exiled instead doesn't: the 2009-10-01 rulings).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, stops, to_phase
from tests.wave9c_kit import check, life, mana, pt, put, to_hand
from tests.wave52a_kit import build_n
from tests.wave100b_kit import hand_size, open_repo, run, zone

ROWEN, ETCHINGS, KERANOS, SUGARMAW, HELLFIRE = ("Rowen", "Primitive Etchings", "Keranos, God of Storms", "Devouring Sugarmaw // Have for Dinner",
                                                "Hellfire")
TERROR, TROLL, WARDEN, KELLAN = "Reign of Terror", "Albino Troll", "Soul Warden", "Kellan Joins Up"
EGO, SHRIEK, FAERIE, GORILLA = "Ego Drain", "Specter's Shriek", "Pestermite", "Gargantuan Gorilla"
DESERTER, AEROSTAT, FOLD, SWIFT = "Afflicted Deserter // Werewolf Ransacker", "Metathran Aerostat", "Fold into Aether", "Swift Silence"
RESEARCHER, KOYA, SURVIVORS, VANISH = "Innocuous Researcher", "Koya, Death from Above", "Auriok Survivors", "Vanish into Memory"
DAKRA, DURIN, LATNAM, SURGE = "Dakra Mystic", "Doors of Durin", "Lat-Nam's Legacy", "Primal Surge"
LOCKE, HELLION, HULK = "Locke, Treasure Hunter", "Devouring Hellion", "Deathbonnet Sprout // Deathbonnet Hulk"
KALDHEIM, MANABOND, GUARDIAN = "Invasion of Kaldheim // Pyre of the World Tree", "Manabond", "Wicked Guardian"
INVESTIGATORS, CLASH, SANCTUM = "Phenomenon Investigators", "Clash of Elements", "Theorist's Sanctum"
HEDRON, ATEMSIS, SPHINX, VOICE = "Hedron Alignment", "Atemsis, All-Seeing", "Rescuer Sphinx", "Veteran's Voice"
GEAR, MIRROR, RUNES, RALLY = "Fishing Gear", "Moonring Mirror", "Read the Runes", "Rally the Horde"
REST, BRINGER, VAULT101 = "Long Rest", "Bringer of the Last Gift", "Vault 101: Birthday Party"
INFERNO, FOXGLOVE, SPIRIT = "Inferno of the Star Mounts", "Mr. Foxglove", "Call the Spirit Dragons"
HOLISTIC, WERNOG, LIEGE = "Holistic Wisdom", "Wernog, Rider's Chaplain", "Liege of the Hollows"
BEARS, GIANT, RIP, ELVES = "Grizzly Bears", "Hill Giant", "Rest in Peace", "Llanowar Elves"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [ROWEN, ETCHINGS, KERANOS, SUGARMAW, HELLFIRE, TERROR, KELLAN, EGO, SHRIEK, GORILLA, DESERTER, AEROSTAT, FOLD, SWIFT, RESEARCHER, KOYA, SURVIVORS, VANISH, DAKRA, DURIN, LATNAM, SURGE, LOCKE, HELLION, HULK, KALDHEIM, MANABOND, GUARDIAN, INVESTIGATORS, CLASH, SANCTUM, HEDRON, ATEMSIS, SPHINX, VOICE, GEAR, MIRROR, RUNES, RALLY, REST, BRINGER, VAULT101, INFERNO, FOXGLOVE, SPIRIT, HOLISTIC, WERNOG, LIEGE])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def pick(*ids):
    """Answer with the options of these ids (cards or players), else the default (a scry keeps the card on top)."""
    def answer(d):
        if (d.prompt or "").startswith("Scry"):
            return []
        found = [o.id for o in d.options if o.id in ids or getattr(o, "card_id", None) in ids]
        return found[: max(1, d.min_choices)] or None
    return answer


def on_top(s, c, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "library"})
    assert s.state.zones[f"{pid}:library"][0] == c.id


def named(s, name, pid="p1", n=0):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid][n]


def revealed(s, c):
    return "*" in s.state.cards[c.id].revealed_to


def draw_step(s, turn=3):
    """Hand size before the turn's draw step, then stop in it (priority at every step), the draw done and any trigger waiting."""
    stops(s)
    to_phase(s, "upkeep", turn=turn)
    before = hand_size(s, "p1")
    to_phase(s, "draw", turn=turn)
    return before


# -- Rowen / Primitive Etchings / Keranos ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("land", [True, False])
def test_rowen_draws_when_the_first_card_drawn_is_a_basic_land(cards, land):
    s = build_n(cards, [ROWEN, BEARS])
    put(s, ROWEN)
    first = named(s, "Forest", n=3) if land else named(s, BEARS)
    on_top(s, first)
    second = s.state.zones["p1:library"][1]
    before = draw_step(s)
    assert revealed(s, first)
    run(s)
    assert first.id in s.state.zones["p1:hand"]
    assert hand_size(s, "p1") == before + 1 + (1 if land else 0)
    if land:  # (Rowen's own draw is not the turn's first card: not revealed, no more draws)
        assert second in s.state.zones["p1:hand"] and "*" not in s.state.cards[second].revealed_to
    check(s)


def test_rowen_reveals_only_the_turns_first_draw(cards):
    s = build_n(cards, [ROWEN, BEARS, "Opt"])
    put(s, ROWEN)
    on_top(s, named(s, BEARS))
    draw_step(s)
    run(s)  # (the draw step's card, the Bears: revealed, no trigger)
    opt = to_hand(s, "Opt")
    land = named(s, "Forest", n=5)
    on_top(s, land)
    to_phase(s, "main1")
    count = hand_size(s, "p1")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    run(s, pick())
    assert hand_size(s, "p1") == count - 1 + 1 and not revealed(s, land)  # (Opt's draw is the turn's second card)
    check(s)


def test_rowen_entering_after_the_first_draw_reveals_nothing_that_turn(cards):
    s = build_n(cards, [ROWEN, "Opt"])
    to_phase(s, "main1", turn=3)  # (Alice drew her draw step's card before Rowen was there)
    put(s, ROWEN)
    opt = to_hand(s, "Opt")
    land = named(s, "Forest", n=6)
    on_top(s, land)
    before = hand_size(s, "p1")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    run(s, pick())
    assert hand_size(s, "p1") == before - 1 + 1 and not revealed(s, land)
    check(s)


def test_two_primitive_etchings_reveal_once_and_both_trigger(cards):
    s = build_n(cards, [(2, ETCHINGS), (3, BEARS)])
    put(s, ETCHINGS)
    act(s, "p1", type="move", card_ids=[named(s, ETCHINGS, n=1).id], to={"player": "p1", "zone": "battlefield"})
    on_top(s, named(s, BEARS))
    before = draw_step(s)
    assert len(s.state.zones.get("stack", [])) == 2
    run(s)
    assert hand_size(s, "p1") == before + 3
    check(s)


def test_primitive_etchings_on_an_opponents_turn_counts_your_first_draw(cards):
    s = build_n(cards, [ETCHINGS, BEARS, "Opt"])
    put(s, ETCHINGS)
    stops(s)
    to_phase(s, "upkeep", turn=2)
    act(s, "p2", type="pass_priority")  # (Bob's upkeep: Alice gets priority after him)
    opt = to_hand(s, "Opt")
    bears = named(s, BEARS)
    on_top(s, bears)
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    before = hand_size(s, "p1")
    run(s, pick())
    assert revealed(s, bears) and hand_size(s, "p1") == before + 2  # (Opt's draw: the Bears, revealed - Etchings draws one more)
    check(s)


@pytest.mark.parametrize("land", [True, False])
def test_keranos_on_your_turn_draws_for_a_land_and_hits_for_a_nonland(cards, land):
    s = build_n(cards, [KERANOS, BEARS])
    put(s, KERANOS)
    on_top(s, named(s, "Forest", n=3) if land else named(s, BEARS))
    bob = life(s, "p2")
    before = draw_step(s)
    run(s, pick("p2"))
    assert hand_size(s, "p1") == before + 1 + (1 if land else 0)
    assert life(s, "p2") == bob - (0 if land else 3)
    check(s)


def test_keranos_reveals_nothing_on_an_opponents_turn(cards):
    s = build_n(cards, [KERANOS, BEARS, "Opt"])
    put(s, KERANOS)
    stops(s)
    to_phase(s, "upkeep", turn=2)
    act(s, "p2", type="pass_priority")  # (Bob's upkeep: Alice gets priority after him)
    opt = to_hand(s, "Opt")
    bears = named(s, BEARS)
    on_top(s, bears)
    mana(s, U=1)
    bob = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=opt.id)
    run(s, pick("p2"))
    assert life(s, "p2") == bob and not revealed(s, bears) and bears.id in s.state.zones["p1:hand"]
    check(s)


# -- Devouring Sugarmaw ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("what", ["token", "ring", "decline"])
def test_devouring_sugarmaw_sacrifices_an_artifact_enchantment_or_token_or_taps(cards, what):
    s = build_n(cards, [SUGARMAW, "Sol Ring", ELVES, "Raise the Alarm"])
    maw = put(s, SUGARMAW)
    ring = put(s, "Sol Ring")
    elves = put(s, ELVES)
    alarm = to_hand(s, "Raise the Alarm")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=alarm.id)
    run(s)
    soldier = next(c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Soldier")
    to_phase(s, "upkeep", turn=3)
    seen: list[str] = []

    def answer(d):
        seen.extend(getattr(o, "card_id", None) or o.id for o in d.options)
        want = "decline" if what == "decline" else {"token": soldier.id, "ring": ring.id}[what]
        return [o.id for o in d.options if o.id in (want, "pay" if what != "decline" else want) or getattr(o, "card_id", None) == want][:1] or None
    run(s, answer)
    assert elves.id not in seen and maw.id not in seen  # (a nontoken creature isn't one of the three kinds)
    if what == "decline":
        assert s.state.cards[maw.id].tapped and zone(s, ring) == "p1:battlefield"
    else:
        gone = soldier if what == "token" else ring
        assert gone.id not in s.state.zones["p1:battlefield"] and not s.state.cards[maw.id].tapped
    assert zone(s, elves) == "p1:battlefield"
    check(s)


# -- Hellfire -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("rip", [False, True])
def test_hellfire_deals_x_plus_three_for_the_creatures_that_died(cards, rip):
    s = build_n(cards, [HELLFIRE, BEARS, "Raise the Alarm", RIP], [GIANT])
    put(s, BEARS)
    put(s, GIANT, "p2")
    alarm = to_hand(s, "Raise the Alarm")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=alarm.id)
    run(s)
    if rip:
        put(s, RIP)
    spell = to_hand(s, HELLFIRE)
    mana(s, B=3, C=3)
    before = life(s)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    run(s)
    assert not [c for c in s.state.cards.values() if c.zone.endswith(":battlefield") and c.name in (BEARS, GIANT, "Soldier")]
    assert life(s) == before - (3 if rip else 3 + 4)  # (Bears, Hill Giant and the two Soldier tokens: four died; exiled instead, none did)
    check(s)


# -- Reign of Terror ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("color", ["green", "white"])
def test_reign_of_terror_destroys_the_chosen_color_without_regeneration(cards, color):
    s = build_n(cards, [TERROR, BEARS, WARDEN, TROLL], [ELVES])
    bears, warden, troll, elves = put(s, BEARS), put(s, WARDEN), put(s, TROLL), put(s, ELVES, "p2")
    mana(s, G=2)
    activate(s, "p1", troll, "Regenerate")
    run(s)
    spell = to_hand(s, TERROR)
    mana(s, B=5)
    before = life(s)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    run(s, lambda d: [o.id for o in d.options if color in (o.label or "")][:1] or None)
    for c in (bears, troll, elves):
        assert zone(s, c).endswith(":graveyard" if color == "green" else ":battlefield")
    assert zone(s, warden).endswith(":battlefield" if color == "green" else ":graveyard")
    assert life(s) == before - 2 * (3 if color == "green" else 1)  # (the shielded Troll died too: it can't be regenerated)
    check(s)


# -- Kellan Joins Up ------------------------------------------------------------------------------------------------------------------
def plotted(s, c):
    return [p for p in s.state.rules.permissions if p.card == c.id and p.free and p.sorcery]


@pytest.mark.parametrize("pay", [True, False])
def test_kellan_joins_up_plots_the_card_it_exiled_from_your_hand(cards, pay):
    s = build_n(cards, [KELLAN, BEARS, GIANT])
    bears, giant, kellan = to_hand(s, BEARS), to_hand(s, GIANT), to_hand(s, KELLAN)
    land = to_hand(s, "Forest")
    mana(s, G=1, W=1, U=1)
    act(s, "p1", type="cast_spell", card_id=kellan.id)
    offered: list[str] = []

    def answer(d):
        offered.extend(getattr(o, "card_id", None) or o.id for o in d.options)
        if not pay:
            return [o.id for o in d.options if o.id == "decline"] or None
        return [o.id for o in d.options if o.id == "pay" or getattr(o, "card_id", None) == bears.id][:1] or None
    run(s, answer)
    if not pay:
        assert zone(s, bears) == "p1:hand" and not plotted(s, bears)
        check(s)
        return
    assert giant.id not in offered and land.id not in offered  # (mana value 4; a land)
    assert zone(s, bears) == "p1:exile" and plotted(s, bears)
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="cast_spell", card_id=bears.id, free=True)  # 702.170d: on a later turn, without paying its mana cost
    run(s)
    assert zone(s, bears) == "p1:battlefield" and zone(s, giant) == "p1:hand"
    check(s)


# -- Ego Drain / Specter's Shriek -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("faerie", [False, True])
def test_ego_drain_exiles_a_card_from_your_hand_unless_you_control_a_faerie(cards, faerie):
    s = build_n(cards, [EGO, FAERIE, GIANT], [BEARS])
    if faerie:
        put(s, FAERIE)
    mine = to_hand(s, GIANT)
    bears = to_hand(s, BEARS, "p2")
    spell = to_hand(s, EGO)
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    asked: list[str] = []

    def answer(d):
        asked.append(d.player)
        return pick(bears.id, mine.id)(d)
    run(s, answer)
    assert zone(s, bears) == "p2:graveyard"
    assert zone(s, mine) == ("p1:hand" if faerie else "p1:exile")
    assert set(asked) <= {"p1"}  # (the choices are the caster's)
    check(s)


@pytest.mark.parametrize("theirs,mine", [("Lightning Bolt", True), ("Murder", True), ("Lightning Bolt", False), (None, True)])
def test_specters_shriek_exiles_one_of_yours_only_for_a_nonblack_card(cards, theirs, mine):
    s = build_n(cards, [SHRIEK, GIANT], ["Lightning Bolt", "Murder"])
    giant = to_hand(s, GIANT) if mine else None
    target = to_hand(s, theirs, "p2") if theirs else None
    spell = to_hand(s, SHRIEK)
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    run(s, pick(*(c.id for c in (target, giant) if c is not None)) if target is not None else (lambda d: [] if d.min_choices == 0 else None))
    if target is not None:
        assert zone(s, target) == "p2:exile"
    if giant is not None:
        assert zone(s, giant) == ("p1:exile" if theirs == "Lightning Bolt" else "p1:hand")
    check(s)


# -- Gargantuan Gorilla ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("what", ["snow", "plain", "none"])
def test_gargantuan_gorilla_forest_or_the_gorilla(cards, what):
    s = build_n(cards, [GORILLA, "Snow-Covered Forest"])
    ape = put(s, GORILLA)
    snow, forest = put(s, "Snow-Covered Forest"), put(s, "Forest")
    to_phase(s, "upkeep", turn=3)
    before = life(s)
    chosen = {"snow": [snow.id], "plain": [forest.id], "none": []}[what]
    run(s, lambda d: chosen if d.min_choices == 0 and any(o.id in (snow.id, forest.id) for o in d.options) else None)
    if what == "none":
        assert zone(s, ape) == "p1:graveyard" and life(s) == before - 7
    else:
        assert zone(s, ape) == "p1:battlefield" and life(s) == before
        assert ("trample" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[ape.id]).keywords) == (what == "snow")
    check(s)


# -- Werewolf Ransacker ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("rip", [False, True])
def test_werewolf_ransacker_hits_the_controller_of_the_artifact_put_into_a_graveyard(cards, rip):
    s = build_n(cards, [DESERTER, RIP], ["Sol Ring"])
    put(s, DESERTER)
    ring = put(s, "Sol Ring", "p2")
    if rip:
        put(s, RIP)
    bob = life(s, "p2")
    to_phase(s, "upkeep", turn=2)  # (no spells were cast last turn: it transforms, 701.28)
    run(s, pick(ring.id))
    assert zone(s, ring) == ("p2:exile" if rip else "p2:graveyard")
    assert life(s, "p2") == bob - (0 if rip else 3)
    check(s)


# -- Metathran Aerostat ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("chosen", [True, False])
def test_metathran_aerostat_puts_a_creature_of_mana_value_x_and_returns(cards, chosen):
    s = build_n(cards, [AEROSTAT, BEARS, GIANT])
    aero = put(s, AEROSTAT)
    bears, giant = to_hand(s, BEARS), to_hand(s, GIANT)
    mana(s, U=1, C=2)
    offered: list[str] = []

    def answer(d):
        offered.extend(getattr(o, "card_id", None) or o.id for o in d.options)
        return [bears.id] if chosen else []
    act(s, "p1", type="activate_ability", card_id=aero.id, ability=1, x_value=2)
    run(s, answer)
    assert giant.id not in offered  # (mana value 4, not X = 2)
    assert zone(s, bears) == ("p1:battlefield" if chosen else "p1:hand")
    assert zone(s, aero) == ("p1:hand" if chosen else "p1:battlefield")
    check(s)


# -- Fold into Aether / Swift Silence -------------------------------------------------------------------------------------------------
def test_fold_into_aether_lets_the_countered_spells_controller_put_a_creature(cards):
    s = build_n(cards, [FOLD], [BEARS, GIANT])
    stops(s)
    to_phase(s, "main1", turn=2)
    bears, giant = to_hand(s, BEARS, "p2"), to_hand(s, GIANT, "p2")
    fold = to_hand(s, FOLD)
    mana(s, "p2", G=2)
    act(s, "p2", type="cast_spell", card_id=bears.id)
    mana(s, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=fold.id, targets=[bears.id])
    asked: list[str] = []
    run(s, lambda d: asked.append(d.player) or pick(giant.id)(d))
    assert zone(s, bears) == "p2:graveyard" and zone(s, giant) == "p2:battlefield" and asked == ["p2"]
    check(s)


def test_swift_silence_counters_every_other_spell_and_draws_for_each(cards):
    s = build_n(cards, [SWIFT, BEARS, "Lightning Bolt"])
    stops(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    bears, bolt, swift = to_hand(s, BEARS), to_hand(s, "Lightning Bolt"), to_hand(s, SWIFT)
    mana(s, G=1, C=1, R=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    mana(s, W=1, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=swift.id)
    before, bob = hand_size(s, "p1"), life(s, "p2")
    run(s)
    assert zone(s, bears) == zone(s, bolt) == "p1:graveyard" and life(s, "p2") == bob
    assert hand_size(s, "p1") == before + 2
    check(s)


# -- Innocuous Researcher -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("untap", [True, False])
def test_innocuous_researcher_untaps_lands_then_no_spells_until_your_next_turn(cards, untap):
    s = build_n(cards, [RESEARCHER, "Lightning Bolt"])
    put(s, RESEARCHER)
    land = put(s, "Forest")
    act(s, "p1", type="tap", card_ids=[land.id])
    stops(s)
    to_phase(s, "end", turn=1)
    run(s, lambda d: (["yes"] if untap else ["no"]) if any(o.id == "yes" for o in d.options) else None)
    assert s.state.cards[land.id].tapped == (not untap)
    to_phase(s, "upkeep", turn=2)
    act(s, "p2", type="pass_priority")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    if untap:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
        to_phase(s, "main1", turn=3)
        mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    run(s)
    assert zone(s, bolt) == "p1:graveyard"
    check(s)


# -- Koya, Death from Above -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pay", [True, False])
def test_koya_keeps_the_creature_exiled_only_if_you_pay(cards, pay):
    s = build_n(cards, [KOYA], [GIANT])
    giant = put(s, GIANT, "p2")
    koya = to_hand(s, KOYA)
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=koya.id)
    run(s, pick(giant.id))
    assert zone(s, giant) == "p2:exile"

    stops(s)
    to_phase(s, "end", turn=1)
    mana(s, B=1, C=3)  # (the payment is offered while it can be made: 118.3)
    run(s, pick("pay" if pay else "decline"))
    assert zone(s, giant) == ("p2:exile" if pay else "p2:battlefield")
    check(s)


# -- Auriok Survivors -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("attach", [True, False])
def test_auriok_survivors_returns_an_equipment_and_may_attach_it(cards, attach):
    s = build_n(cards, [SURVIVORS, "Bonesplitter"])
    blade = named(s, "Bonesplitter")
    act(s, "p1", type="move", card_ids=[blade.id], to={"player": "p1", "zone": "graveyard"})
    survivors = to_hand(s, SURVIVORS)
    mana(s, W=1, C=5)
    act(s, "p1", type="cast_spell", card_id=survivors.id)
    asked: list[str] = []

    def answer(d):
        if any(getattr(o, "card_id", None) == blade.id for o in d.options):
            return pick(blade.id)(d)
        if not any(o.id == "no" for o in d.options):
            return None
        asked.append(d.prompt)
        return ["yes" if len(asked) == 1 or attach else "no"]  # (the return, then the attach)
    run(s, answer)
    assert zone(s, blade) == "p1:battlefield"
    assert (s.state.cards[blade.id].attached_to == survivors.id) == attach
    check(s)


# -- Vanish into Memory ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("token", [False, True])
def test_vanish_into_memory_discards_for_the_returned_creatures_toughness(cards, token):
    s = build_n(cards, [VANISH, "Raise the Alarm", (6, BEARS)], [GIANT])
    if token:
        alarm = to_hand(s, "Raise the Alarm")
        mana(s, W=2)
        act(s, "p1", type="cast_spell", card_id=alarm.id)
        run(s)
    target = next(c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Soldier") if token else put(s, GIANT, "p2")
    spell = to_hand(s, VANISH)
    mana(s, W=1, U=1, C=2)
    before = hand_size(s, "p1")
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[target.id])
    run(s)
    assert hand_size(s, "p1") == before - 1 + (1 if token else 3)  # (the power as it last existed)
    grave = len(s.state.zones["p1:graveyard"])
    to_phase(s, "main1", turn=3)
    assert len(s.state.zones["p1:graveyard"]) - grave == (0 if token else 3)
    if not token:
        assert zone(s, target) == "p2:battlefield"
    check(s)


# -- Dakra Mystic ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bin_them", [True, False])
def test_dakra_mystic_bins_the_revealed_cards_or_everyone_draws_them(cards, bin_them):
    s = build_n(cards, [DAKRA, BEARS], [GIANT])
    mystic = put(s, DAKRA)
    to_phase(s, "main1", turn=3)
    mine, theirs = named(s, BEARS), named(s, GIANT, "p2")
    on_top(s, mine)
    on_top(s, theirs, "p2")
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=mystic.id, ability=0)
    run(s, lambda d: [o.id for o in d.options if ("graveyard" in (o.label or "")) == bin_them][:1] or None)
    assert zone(s, mine) == ("p1:graveyard" if bin_them else "p1:hand")
    assert zone(s, theirs) == ("p2:graveyard" if bin_them else "p2:hand")
    check(s)


# -- Doors of Durin -------------------------------------------------------------------------------------------------------------------
def test_doors_of_durin_puts_the_creature_attacking_with_the_grants_it_qualifies_for(cards):
    s = build_n(cards, [DURIN, BEARS, ELVES, GIANT])
    put(s, DURIN)
    bears = put(s, BEARS)
    put(s, ELVES)  # (an Elf, no Dwarf)
    giant = named(s, GIANT)
    to_phase(s, "main1", turn=3)
    on_top(s, giant)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    run(s, pick("p2"))
    keywords = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[giant.id]).keywords
    assert zone(s, giant) == "p1:battlefield" and s.state.cards[giant.id].tapped and s.state.cards[giant.id].attacking is not None
    assert "hexproof" in keywords and "trample" not in keywords
    check(s)


# -- Lat-Nam's Legacy -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("card", [True, False])
def test_lat_nams_legacy_draws_two_next_upkeep_only_if_a_card_was_shuffled_in(cards, card):
    s = build_n(cards, [LATNAM, BEARS])
    bears = to_hand(s, BEARS) if card else None
    spell = to_hand(s, LATNAM)
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    run(s)
    assert hand_size(s, "p1") == 0
    if bears is not None:
        assert zone(s, bears) == "p1:library"
    to_phase(s, "main1", turn=2)
    assert hand_size(s, "p1") == (2 if card else 0)
    check(s)


# -- Primal Surge ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("keep_going", [True, False])
def test_primal_surge_repeats_until_a_nonpermanent_or_a_refusal(cards, keep_going):
    s = build_n(cards, [SURGE, BEARS, GIANT, "Lightning Bolt"])
    bears, giant, bolt = named(s, BEARS), named(s, GIANT), named(s, "Lightning Bolt")
    for c in (bolt, giant, bears):  # (Bears on top, then the Giant, then the Bolt)
        on_top(s, c)
    spell = to_hand(s, SURGE)
    mana(s, G=2, C=8)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answers = iter(["yes", "yes" if keep_going else "no"])
    run(s, lambda d: [next(answers)] if any(o.id == "yes" for o in d.options) else None)
    assert zone(s, bears) == "p1:battlefield"
    assert zone(s, giant) == ("p1:battlefield" if keep_going else "p1:exile")
    assert zone(s, bolt) == ("p1:exile" if keep_going else "p1:library")  # (an instant: the process ends there)
    check(s)


# -- Locke, Treasure Hunter -----------------------------------------------------------------------------------------------------------
def test_locke_mills_each_player_makes_a_treasure_and_lets_you_cast_one(cards):
    s = build_n(cards, [LOCKE], ["Lightning Bolt"])
    locke = put(s, LOCKE)
    to_phase(s, "main1", turn=3)
    forest, bolt = named(s, "Forest", n=7), named(s, "Lightning Bolt", "p2")
    on_top(s, forest)
    on_top(s, bolt, "p2")
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": locke.id, "target": "p2"}])
    run(s)
    assert zone(s, forest) == "p1:graveyard" and zone(s, bolt) == "p2:graveyard"
    assert len([c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Treasure"]) == 1  # (a land was milled)
    bob = life(s, "p2")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # (an instant from Bob's graveyard)
    run(s)
    assert life(s, "p2") == bob - 3
    check(s)


# -- Devouring Hellion ----------------------------------------------------------------------------------------------------------------
def test_devouring_hellion_devours_creatures_and_planeswalkers(cards):
    s = build_n(cards, [HELLION, BEARS, "Gideon Jura", "Sol Ring"])
    bears, ring, gideon = put(s, BEARS), put(s, "Sol Ring"), to_hand(s, "Gideon Jura")
    mana(s, W=2, C=3)
    act(s, "p1", type="cast_spell", card_id=gideon.id)
    run(s)
    hellion = to_hand(s, HELLION)
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=hellion.id)
    offered: list[str] = []

    def answer(d):
        offered.extend(getattr(o, "card_id", None) or o.id for o in d.options)
        return [next((o.id for o in d.options if o.id in (bears.id, gideon.id)), "done")]
    run(s, answer)
    assert ring.id not in offered  # (an artifact isn't one of the kinds)
    assert zone(s, bears) == "p1:graveyard" and zone(s, gideon) == "p1:graveyard"
    assert s.state.cards[hellion.id].counters.get("+1/+1") == 4
    check(s)


# -- Deathbonnet Hulk -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("what", ["creature", "land", "none"])
def test_deathbonnet_hulk_exiles_a_card_from_any_graveyard(cards, what):
    s = build_n(cards, [HULK], [GIANT])
    hulk = put(s, HULK)
    act(s, "p1", type="set_face", card_id=hulk.id, face=1)
    giant, forest = named(s, GIANT, "p2"), named(s, "Forest")
    for c, pid in ((giant, "p2"), (forest, "p1")):
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    to_phase(s, "upkeep", turn=3)
    chosen = {"creature": [giant.id], "land": [forest.id], "none": []}[what]
    run(s, lambda d: chosen if any(getattr(o, "card_id", None) == giant.id for o in d.options) else None)
    assert zone(s, giant) == ("p2:exile" if what == "creature" else "p2:graveyard")
    assert s.state.cards[hulk.id].counters.get("+1/+1", 0) == (1 if what == "creature" else 0)
    check(s)


# -- Invasion of Kaldheim -------------------------------------------------------------------------------------------------------------
def test_invasion_of_kaldheim_exiles_the_hand_draws_that_many_and_lets_you_play_them(cards):
    s = build_n(cards, [KALDHEIM, BEARS, "Lightning Bolt"])
    bears, bolt, siege = to_hand(s, BEARS), to_hand(s, "Lightning Bolt"), to_hand(s, KALDHEIM)
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=siege.id)
    run(s, pick("p2"))
    assert zone(s, bears) == zone(s, bolt) == "p1:exile" and hand_size(s, "p1") == 2
    bob = life(s, "p2")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    run(s)
    assert life(s, "p2") == bob - 3
    check(s)


# -- Manabond -------------------------------------------------------------------------------------------------------------------------
def test_manabond_puts_the_lands_from_your_hand_then_discards_the_rest(cards):
    s = build_n(cards, [MANABOND, BEARS])
    put(s, MANABOND)
    lands, bears = [to_hand(s, "Forest"), named(s, "Forest", n=1)], to_hand(s, BEARS)
    act(s, "p1", type="move", card_ids=[lands[1].id], to={"zone": "hand"})
    stops(s)
    to_phase(s, "end", turn=1)
    run(s)
    assert all(zone(s, c) == "p1:battlefield" for c in lands) and zone(s, bears) == "p1:graveyard"
    check(s)


# -- Wicked Guardian ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("deal", [True, False])
def test_wicked_guardian_hurts_one_of_your_creatures_to_draw(cards, deal):
    s = build_n(cards, [GUARDIAN, BEARS])
    bears, guardian = put(s, BEARS), to_hand(s, GUARDIAN)
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=guardian.id)
    before = hand_size(s, "p1")
    run(s, lambda d: ([bears.id] if deal else []) if any(getattr(o, "card_id", None) == bears.id for o in d.options) else None)
    assert zone(s, bears) == ("p1:graveyard" if deal else "p1:battlefield")
    assert hand_size(s, "p1") == before + (1 if deal else 0)
    check(s)


# -- Phenomenon Investigators ---------------------------------------------------------------------------------------------------------
def test_phenomenon_investigators_doubt_returns_a_permanent_you_own_to_draw(cards):
    s = build_n(cards, [INVESTIGATORS, "Sol Ring"], ["Sol Ring"])
    mine, theirs = put(s, "Sol Ring"), put(s, "Sol Ring", "p2")
    inv = to_hand(s, INVESTIGATORS)
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=inv.id)
    run(s, lambda d: [o.id for o in d.options if "Doubt" in (o.label or o.id)][:1] or None)
    stops(s)
    to_phase(s, "end", turn=1)
    offered: list[str] = []
    before = hand_size(s, "p1")

    def answer(d):
        offered.extend(getattr(o, "card_id", None) or o.id for o in d.options)
        return [mine.id] if mine.id in offered else None
    run(s, answer)
    assert theirs.id not in offered and zone(s, mine) == "p1:hand" and hand_size(s, "p1") == before + 2
    check(s)


# -- Clash of Elements ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("top", [True, False])
def test_clash_of_elements_lets_the_owner_choose_top_and_damage_or_bottom(cards, top):
    s = build_n(cards, [CLASH], [GIANT])
    giant = put(s, GIANT, "p2")
    spell = to_hand(s, CLASH)
    mana(s, U=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[giant.id])
    bob = life(s, "p2")
    asked: list[str] = []
    run(s, lambda d: asked.append(d.player) or [o.id for o in d.options if ("top" in (o.label or "")) == top][:1] or None)
    library = s.state.zones["p2:library"]
    assert asked == ["p2"] and library[0 if top else -1] == giant.id
    assert life(s, "p2") == bob - (2 if top else 0)
    check(s)


# -- Theorist's Sanctum ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("how", ["permanent", "card", "none"])
def test_theorists_sanctum_enters_untapped_only_if_you_behold_a_jace(cards, how):
    s = build_n(cards, [SANCTUM, "Jace Beleren"])
    jace = to_hand(s, "Jace Beleren")
    if how == "permanent":
        mana(s, U=2, C=1)
        act(s, "p1", type="cast_spell", card_id=jace.id)
        run(s)
    sanctum = to_hand(s, SANCTUM)
    act(s, "p1", type="play_land", card_id=sanctum.id)
    run(s, lambda d: [jace.id] if how != "none" and any(getattr(o, "card_id", None) == jace.id for o in d.options) else ["none"])
    assert zone(s, sanctum) == "p1:battlefield" and s.state.cards[sanctum.id].tapped == (how == "none")
    assert "*" not in s.state.cards[jace.id].revealed_to  # (shown, then hidden again; a chosen permanent is just chosen)
    check(s)


# -- Hedron Alignment / Atemsis -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("exiled", [True, False])
def test_hedron_alignment_wins_with_a_copy_in_each_zone(cards, exiled):
    s = build_n(cards, [(4, HEDRON)])
    copies = [named(s, HEDRON, n=i) for i in range(4)]
    put(s, HEDRON)
    act(s, "p1", type="move", card_ids=[copies[1].id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[copies[2].id], to={"player": "p1", "zone": "graveyard"})
    if exiled:
        act(s, "p1", type="move", card_ids=[copies[3].id], to={"player": "p1", "zone": "exile"})
    to_phase(s, "upkeep", turn=3)
    run(s)
    assert (s.state.rules.winner == "p1") == exiled
    check(s)


@pytest.mark.parametrize("six", [True, False])
def test_atemsis_makes_the_player_lose_for_six_mana_values(cards, six):
    s = build_n(cards, [ATEMSIS, ELVES, BEARS, FAERIE, GIANT, "Gideon Jura"])
    atemsis = put(s, ATEMSIS)
    to_phase(s, "main1", turn=3)
    for name in ("Forest", ELVES, BEARS, FAERIE, GIANT, "Gideon Jura" if six else "Llanowar Elves"):  # (mana values 0 to 5, or 0 to 4)
        to_hand(s, name)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": atemsis.id, "target": "p2"}])
    for _ in range(20):  # (through the combat damage step: the trigger, then its "may")
        if s.state.rules.winner is not None or s.state.turn.phase == "main2":
            break
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"]) if d is not None else act(s, s.state.rules.priority, type="pass_priority")
    assert (s.state.rules.winner == "p1") == six
    check(s)


# -- Rescuer Sphinx -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bounce", [True, False])
def test_rescuer_sphinx_returns_a_nonland_permanent_for_a_counter(cards, bounce):
    s = build_n(cards, [SPHINX, "Sol Ring", BEARS])
    ring, bears, sphinx = put(s, "Sol Ring"), put(s, BEARS), to_hand(s, SPHINX)
    forest = put(s, "Forest")
    mana(s, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=sphinx.id)
    offered: list[str] = []

    def answer(d):
        offered.extend(getattr(o, "card_id", None) or o.id for o in d.options)
        return [ring.id] if bounce and ring.id in [o.id for o in d.options] else ["done"]
    run(s, answer)
    assert forest.id not in offered and bears.id in offered
    assert zone(s, ring) == ("p1:hand" if bounce else "p1:battlefield")
    assert s.state.cards[sphinx.id].counters.get("+1/+1", 0) == (1 if bounce else 0)
    check(s)


# -- Veteran's Voice ------------------------------------------------------------------------------------------------------------------
def test_veterans_voice_pumps_another_creature_than_the_one_it_taps(cards):
    s = build_n(cards, [VOICE, BEARS, ELVES])
    bears, elves, voice = put(s, BEARS), put(s, ELVES), put(s, VOICE)
    act(s, "p1", type="attach", card_ids=[voice.id], to=bears.id)
    to_phase(s, "main1", turn=3)
    with pytest.raises(ActionError):
        activate(s, "p1", voice, "Tap enchanted", targets=[bears.id])
    activate(s, "p1", voice, "Tap enchanted", targets=[elves.id])
    run(s)
    assert s.state.cards[bears.id].tapped and pt(s, ELVES) == (3, 2)
    check(s)


# -- Fishing Gear ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("what", ["put", "decline", "instant"])
def test_fishing_gear_takes_a_permanent_or_makes_a_fish(cards, what):
    s = build_n(cards, [GEAR, BEARS], [GIANT, "Lightning Bolt"])
    gear, bears = put(s, GEAR), put(s, BEARS)
    act(s, "p1", type="attach", card_ids=[gear.id], to=bears.id)
    to_phase(s, "main1", turn=3)
    top = named(s, "Lightning Bolt" if what == "instant" else GIANT, "p2")
    on_top(s, top, "p2")
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    for _ in range(30):  # (through combat damage: the trigger, then its question)
        d = s.state.rules.decision
        if s.state.turn.phase == "main2":
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if what == "put" else "no"]) if d is not None \
            else act(s, s.state.rules.priority, type="pass_priority")
    fish = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Fish"]
    assert zone(s, top) == ("p1:battlefield" if what == "put" else "p2:exile")
    assert len(fish) == (0 if what == "put" else 1)
    check(s)


# -- Moonring Mirror ------------------------------------------------------------------------------------------------------------------
def test_moonring_mirror_swaps_your_hand_for_the_cards_it_exiled(cards):
    s = build_n(cards, [MIRROR, BEARS, "Opt", GIANT])
    put(s, MIRROR)
    opt, giant = to_hand(s, "Opt"), to_hand(s, GIANT)
    bears = named(s, BEARS)
    on_top(s, bears)
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    run(s, pick())  # (Opt draws the Bears; the Mirror exiles the next card face down)
    stashed = [c for c in s.state.zones["p1:exile"] if s.state.cards[c].face_down]
    hand = list(s.state.zones["p1:hand"])
    assert len(stashed) == 1 and bears.id in hand and giant.id in hand
    stops(s)
    to_phase(s, "upkeep", turn=3)
    run(s)
    assert s.state.zones["p1:hand"] == stashed
    assert len([c for c in s.state.zones["p1:exile"] if s.state.cards[c].face_down]) == len(hand)  # (face down: new hidden identities, 406.3)
    check(s)


# -- Read the Runes / Rally the Horde -------------------------------------------------------------------------------------------------
def test_read_the_runes_sacrifices_what_you_choose_then_discards_the_rest(cards):
    s = build_n(cards, [RUNES, "Sol Ring"])
    ring, runes = put(s, "Sol Ring"), to_hand(s, RUNES)
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=runes.id, x_value=3)
    run(s, lambda d: [ring.id] if any(o.id == ring.id or getattr(o, "card_id", None) == ring.id for o in d.options) else None)
    assert zone(s, ring) == "p1:graveyard"
    assert hand_size(s, "p1") == 1 and len(s.state.zones["p1:graveyard"]) == 1 + 1 + 2  # (three drawn, one permanent sacrificed, two discarded)
    check(s)


def test_rally_the_horde_repeats_until_the_last_card_is_a_land(cards):
    s = build_n(cards, [RALLY, BEARS, GIANT, ELVES, "Lightning Bolt"])
    order = [named(s, BEARS), named(s, GIANT), named(s, ELVES), named(s, "Lightning Bolt"), named(s, "Forest"), named(s, "Forest", n=1)]
    for c in reversed(order):
        on_top(s, c)
    spell = to_hand(s, RALLY)
    mana(s, R=1, C=5)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    run(s)
    assert all(zone(s, c) == "p1:exile" for c in order)  # (three nonland: again; Bolt, Forest, Forest: the last is a land, it stops)
    assert len([c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Warrior"]) == 4
    check(s)


# -- Long Rest ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("eight", [True, False])
def test_long_rest_resets_life_for_eight_cards_returned(cards, eight):
    names = ["Forest", ELVES, BEARS, FAERIE, GIANT, "Gideon Jura", RALLY, GORILLA]  # (mana values 0 to 7)
    s = build_n(cards, [REST, *names[1:]])
    picked = [named(s, n) for n in names[: 8 if eight else 7]]
    for c in picked:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="set_life", player="p1", value=12)
    spell = to_hand(s, REST)
    x = len(picked)
    mana(s, G=3, C=x)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x, targets=[c.id for c in picked], target_counts=[x])
    run(s)
    assert all(zone(s, c) == "p1:hand" for c in picked) and zone(s, spell) == "p1:exile"
    assert life(s) == (40 if eight else 12)
    check(s)


# -- Bringer of the Last Gift ---------------------------------------------------------------------------------------------------------
def test_bringer_of_the_last_gift_swaps_the_board_for_the_graveyards(cards):
    s = build_n(cards, [BRINGER, BEARS, ELVES], [GIANT, ELVES])
    bears, giant = put(s, BEARS), put(s, GIANT, "p2")
    mine, theirs = named(s, ELVES), named(s, ELVES, "p2")
    for c, pid in ((mine, "p1"), (theirs, "p2")):
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    bringer = to_hand(s, BRINGER)
    mana(s, B=2, C=6)
    act(s, "p1", type="cast_spell", card_id=bringer.id)
    run(s)
    assert zone(s, bears) == "p1:graveyard" and zone(s, giant) == "p2:graveyard"  # (put there this way: they stay)
    assert zone(s, mine) == "p1:battlefield" and zone(s, theirs) == "p2:battlefield" and zone(s, bringer) == "p1:battlefield"
    check(s)


# -- Vault 101: Birthday Party --------------------------------------------------------------------------------------------------------
def test_vault_101_puts_an_equipment_and_attaches_it(cards):
    s = build_n(cards, [VAULT101, BEARS, "Bonesplitter"])
    bears, blade = put(s, BEARS), named(s, "Bonesplitter")
    act(s, "p1", type="move", card_ids=[blade.id], to={"player": "p1", "zone": "graveyard"})
    saga = to_hand(s, VAULT101)
    mana(s, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=saga.id)
    run(s)  # (chapter I: a Human Soldier and a Food)
    to_phase(s, "main1", turn=3)
    run(s, lambda d: [blade.id] if any(getattr(o, "card_id", None) == blade.id for o in d.options) else [bears.id]
        if any(getattr(o, "card_id", None) == bears.id for o in d.options) else None)
    assert zone(s, blade) == "p1:battlefield" and s.state.cards[blade.id].attached_to == bears.id
    check(s)


# -- Inferno of the Star Mounts -------------------------------------------------------------------------------------------------------
def test_inferno_of_the_star_mounts_hits_once_its_power_becomes_twenty(cards):
    s = build_n(cards, [INFERNO])
    inferno = put(s, INFERNO)
    bob = life(s, "p2")
    for i in range(15):  # (6 power: the 14th makes it 20; the 15th, 21, doesn't trigger)
        mana(s, R=1)
        activate(s, "p1", inferno, "+1/+0")
        run(s, pick("p2"))
        assert life(s, "p2") == (bob - 20 if i >= 13 else bob)
    check(s)


# -- Mr. Foxglove ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bob_cards", [3, 0])
def test_mr_foxglove_draws_the_difference_or_puts_a_creature(cards, bob_cards):
    s = build_n(cards, [FOXGLOVE, BEARS])
    fox = put(s, FOXGLOVE)
    to_phase(s, "main1", turn=3)
    for c in [c for c in s.state.zones["p1:hand"] if c != named(s, BEARS).id]:
        act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "graveyard"})
    bears = to_hand(s, BEARS)
    for i in range(bob_cards):
        act(s, "p2", type="move", card_ids=[named(s, "Island", "p2", n=i).id], to={"zone": "hand"})
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": fox.id, "target": "p2"}])
    run(s, pick(bears.id))
    if bob_cards:
        assert hand_size(s, "p1") == 1 + 2 and zone(s, bears) == "p1:hand"
    else:
        assert zone(s, bears) == "p1:battlefield"
    check(s)


# -- Call the Spirit Dragons ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("five", [True, False])
def test_call_the_spirit_dragons_wins_with_five_dragons(cards, five):
    dragons = ["Pearl Dragon", "Dragonborn Looter", "Ebon Dragon", "Volcanic Dragon", "Avenging Hunter"]  # (W, U, B, R, G)
    s = build_n(cards, [SPIRIT, *dragons])
    put(s, SPIRIT)
    mine = [put(s, n) for n in dragons[: 5 if five else 4]]
    stops(s)
    to_phase(s, "upkeep", turn=3)
    run(s)
    assert all(s.state.cards[c.id].counters.get("+1/+1") == 1 for c in mine)
    assert (s.state.rules.winner == "p1") == five
    check(s)


# -- Holistic Wisdom ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("shared", [True, False])
def test_holistic_wisdom_returns_a_card_sharing_a_type_with_the_exiled_one(cards, shared):
    s = build_n(cards, [HOLISTIC, BEARS, GIANT, "Lightning Bolt"])
    wisdom = put(s, HOLISTIC)
    bears, bolt = named(s, BEARS), named(s, "Lightning Bolt")
    for c in (bears, bolt):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    giant = to_hand(s, GIANT)
    target = bears if shared else bolt
    mana(s, C=2)
    activate(s, "p1", wisdom, "Exile a card", targets=[target.id])
    run(s, pick(giant.id))
    assert zone(s, giant) == "p1:exile"
    assert zone(s, target) == ("p1:hand" if shared else "p1:graveyard")
    check(s)


# -- Wernog, Rider's Chaplain ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bob_does", [True, False])
def test_wernog_lets_opponents_investigate_or_lose_life(cards, bob_does):
    s = build_n(cards, [WERNOG])
    wernog = to_hand(s, WERNOG)
    mana(s, W=1, B=1)
    act(s, "p1", type="cast_spell", card_id=wernog.id)
    bob = life(s, "p2")
    asked: list[str] = []
    run(s, lambda d: asked.append(d.player) or ["yes" if bob_does else "no"] if any(o.id == "yes" for o in d.options) else None)
    clues = {p: len([c for c in s.state.cards.values() if c.zone == f"{p}:battlefield" and c.name == "Clue"]) for p in ("p1", "p2")}
    assert asked == ["p2"] and clues == ({"p1": 2, "p2": 1} if bob_does else {"p1": 1, "p2": 0})
    assert life(s, "p2") == bob - (0 if bob_does else 1)
    check(s)


# -- Liege of the Hollows -------------------------------------------------------------------------------------------------------------
def test_liege_of_the_hollows_gives_each_player_squirrels_for_their_mana(cards):
    s = build_n(cards, [LIEGE, "Murder"])
    liege, murder = put(s, LIEGE), to_hand(s, "Murder")
    mana(s, B=2, C=3)
    mana(s, "p2", C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[liege.id])
    order: list[str] = []

    def answer(d):
        if not any(o.id.startswith("x:") or o.id == "decline" for o in d.options):
            return None
        order.append(d.player)
        return ["x:2" if d.player == "p1" else "x:1"]
    run(s, answer)
    squirrels = {p: len([c for c in s.state.cards.values() if c.zone == f"{p}:battlefield" and c.name == "Squirrel"]) for p in ("p1", "p2")}
    assert zone(s, liege) == "p1:graveyard" and order == ["p1", "p2"] and squirrels == {"p1": 2, "p2": 1}
    check(s)
