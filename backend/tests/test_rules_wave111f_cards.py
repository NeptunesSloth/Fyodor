"""Wave 111F: Star Trek cards (trk/trc, Oracle text of 2026-10-30). Real Oracle text; every scenario checks the replay and a save and a load.

* The Star Trek creature types (wave 111E's block in app/rules/creature_types.py, 205.3a/205.3m): Borg tokens (Tenacious Drone, Borg Incursion),
  "another Klingon or Warrior you control dies" (Curzon Dax), "creature types among non-Borg creatures you control" (Saavik), "he's a Klingon Spy in
  addition to his other types" (Voq, 707.9b).
* "mana value X or less …, where X is Julian Bashir's power": read again as it resolves (608.2b). "Then return a land card … If you can't, create a
  Treasure token." (Temporal Conqueror). "… abilities from artifact sources your opponents control" (Species 8472, 115.2). "with a Communicator attached
  to it/them" (Combadge, Starfleet Communicator, 301.5). Worf: one target per opponent (601.2c), Warriors with haste until end of turn.
* Token copies: "Choose X target creatures … For each of them, create a token that's a copy …" (Dominion Infiltration, 707.9b changeling), "If this
  spell was kicked, instead for each creature target opponent controls, …" (Mirror Universe Intrusion: the kicked group replaces the other, 601.2c),
  "Each Equipment token you control becomes a copy of target Equipment …" (Gwyndala, 611.2c). A station line's flavor word (U.S.S. Prometheus, 207.2d).
* Free casts: "That player may exile it. If they don't, you may cast …" (Brazen Bluff, 608.2d/608.2g), "Copy that card X times, where X is …" (Infinite
  Diversity, 707.12). Alexander: an opponent picked at random as it resolves, X the greatest mana value revealed (701.20a). Dr. McCoy: a dies-this-turn
  trigger whose return waits for the next end step (603.7, 400.7); "When Dr. McCoy enters, choose one —" (201.5c).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act, turn_on
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import card_named, check, life, mana, put, to_hand

EXTRA = [
    real("Tenacious Drone", "{1}{B}", 2, "Artifact Creature — Borg", "When this creature dies, create a 1/1 colorless Borg artifact creature token.",
         ("2", "1"), "B"),
    real("Curzon Dax, Bound by Blood", "{2}{R}{W}", 4, "Legendary Creature — Trill Warrior",
         "Whenever another Klingon or Warrior you control dies, Curzon Dax deals 1 damage to each opponent.\n"
         "When Curzon Dax dies, you may put a creature card with mana value 3 or less from your hand onto the battlefield.", ("4", "3"), "RW"),
    real("Borg Incursion", "{2}{W}", 3, "Instant",
         "Create two 1/1 colorless Borg artifact creature tokens, then artifact creatures you control gain protection from the color of your choice until "
         "end of turn. (They can't be blocked, targeted, dealt damage, enchanted, or equipped by anything of that color.)", None, "W"),
    real("Saavik, Stoic Student", "{4}{W}", 5, "Legendary Creature — Vulcan Advisor",
         "Flash\nFederation — When Saavik enters, she deals X damage to target attacking or blocking creature an opponent controls, where X is the number "
         "of creature types among non-Borg creatures you control.", ("2", "2"), "W"),
    real("Voq, Torchbearer", "{3}{B}", 4, "Legendary Creature — Klingon Spy",
         "Menace\nChoH'a' — You may have Voq enter as a copy of a creature card in a graveyard, except he's a Klingon Spy in addition to his other types "
         "and has menace.", ("4", "3"), "B"),
    real("Julian Bashir, Frontier Doctor", "{2}{W}", 3, "Legendary Creature — Human Doctor",
         "Seek out — Whenever you draw your second card each turn, put a +1/+1 counter on Julian Bashir.\n"
         "Whenever Julian Bashir attacks, return target creature card with mana value X or less from your graveyard to the battlefield, where X is "
         "Julian Bashir's power.", ("1", "1"), "W"),
    real("Temporal Conqueror", "{2}{G}", 3, "Creature — Na'kuhl Warrior",
         "When this creature enters, mill three cards. Then return a land card from your graveyard to your hand. If you can't, create a Treasure token. "
         "(To mill three cards, put the top three cards from your library into your graveyard.)", ("2", "3"), "G"),
    real("Species 8472", "{4}{G}{G}", 6, "Creature — Insect Beast",
         "Strange new worlds — When this creature enters, you gain life equal to the number of differently named lands you control.\n"
         "This creature can't be blocked by artifact creatures.\n"
         "This creature can't be the target of abilities from artifact sources your opponents control.", ("7", "5"), "G"),
    real("Combadge", "{3}", 3, "Artifact — Communicator Equipment",
         "When you cast this spell, copy it. (The copy becomes a token.)\n"
         "Equipped creature has \"Whenever this creature attacks while you control another creature with a Communicator attached to it, this creature "
         "can't be blocked this turn.\"\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)", None, ""),
    real("Starfleet Communicator", "{3}", 3, "Artifact — Communicator Equipment",
         "When you cast this spell, copy it. (The copy becomes a token.)\n"
         "Equipped creature has \"Whenever this creature attacks, draw X cards, then you may put up to X land cards from your hand onto the battlefield "
         "tapped, where X is the number of other creatures you control with a Communicator attached to them.\"\nEquip {1}", None, ""),
    real("Worf, Intelligence Contractor", "{2}{R}", 3, "Legendary Creature — Klingon Warrior Spy",
         "When Worf enters, for each opponent, gain control of up to one target creature that player controls with mana value 3 or less until end of "
         "turn. Untap those creatures. Until end of turn, they become Warriors in addition to their other types and gain haste.", ("3", "2"), "R"),
    real("Dominion Infiltration", "{X}{R}{R}{R}", 3, "Sorcery",
         "Choose X target creatures your opponents control. For each of them, create a token that's a copy of that creature, except it has "
         "changeling. Those tokens gain haste. Exile those tokens at the beginning of the next end step. (They're every creature type.)", None, "R"),
    real("Mirror Universe Intrusion", "{1}{U}{B}", 3, "Sorcery",
         "Kicker {4}{U}{B} (You may pay an additional 4 as you cast this spell.)\n"
         "Create a token that's a copy of target creature an opponent controls, except it has menace. If this spell was kicked, instead for each "
         "creature target opponent controls, create a token that's a copy of that creature, except it has menace.", None, "UB"),
    real("Gwyndala, the Progeny", "{1}{U}", 2, "Legendary Creature — Vau-N'Akat Advisor",
         "When Gwyndala enters, create a colorless Equipment artifact token named Neuroflux Heirloom with \"Equipped creature gets +1/+1\" and "
         "equip {2}. Attach it to Gwyndala.\n{2}: Each Equipment token you control becomes a copy of target Equipment you control until end of turn.",
         ("1", "1"), "U"),
    real("U.S.S. Prometheus, Prototype", "{5}", 5, "Legendary Artifact — Spacecraft",
         "Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an "
         "artifact creature at 4+.)\n4+ | Flying\n8+ | Multivector Assault Mode — Whenever U.S.S. Prometheus deals combat damage to an opponent, it "
         "deals that much damage to each other opponent.", ("6", "6"), ""),
    real("Brazen Bluff", "{R}{R}", 2, "Instant",
         "Choose target noncreature spell an opponent controls. That player may exile it. If they don't, you may cast a noncreature spell from "
         "your hand without paying its mana cost.", None, "R"),
    real("Infinite Diversity", "{7}{R}{R}", 9, "Sorcery",
         "Federation — Exile target instant or sorcery card from your graveyard. Copy that card X times, where X is the number of creature types "
         "among non-Borg creatures you control. You may cast the copies without paying their mana costs. Exile Infinite Diversity.", None, "R"),
    real("Alexander, Ship's Fool", "{3}{R}{W}", 5, "Legendary Creature — Klingon Human",
         "Vigilance, haste\n{T}: Each player reveals the top card of their library, then draws a card. Alexander deals X damage to a random opponent, "
         "where X is the greatest mana value among cards revealed this way.", ("3", "5"), "RW"),
    real('Dr. Leonard "Bones" McCoy', "{1}{G}{G}", 3, "Legendary Creature — Human Doctor",
         "Flash\nWhen Dr. McCoy enters, choose one —\n• Return target non-Doctor permanent card from your graveyard to your hand.\n"
         "• Choose up to one other target creature. When it dies this turn, return that card to the battlefield under its owner's control with a "
         "+1/+1 counter on it at the beginning of the next end step.", ("3", "2"), "G"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Zf Elf", "{G}", 1, "Creature — Elf", "", ("1", "1"), "G"),
    real("Zf Sage", "{1}", 1, "Artifact", "{1}: Draw a card.", None, ""),
    real("Zf Shock", "{R}", 1, "Instant", "Zf Shock deals 2 damage to any target.", None, "R"),
    real("Zf Medic", "{1}{W}", 2, "Creature — Human Doctor", "", ("1", "1"), "W"),
    real("Zf Rod", "{1}", 1, "Artifact", "{T}: Zf Rod deals 1 damage to target creature.", None, ""),
    real("Zf Pinger", "{1}{R}", 2, "Creature — Human Wizard", "{T}: Zf Pinger deals 1 damage to target creature.", ("1", "1"), "R"),
    real("Zf Gear", "{1}", 1, "Artifact — Equipment", "Equipped creature gets +1/+0.\nEquip {1}", None, ""),
    real("Zf Klingon", "{1}{R}", 2, "Creature — Klingon Scientist", "", ("2", "2"), "R"),
    real("Zf Warrior", "{1}{R}", 2, "Creature — Human Warrior", "", ("2", "2"), "R"),
    real("Zf Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Zf Drone", "{1}{B}", 2, "Creature — Borg Human Rogue", "", ("2", "2"), "B"),
    real("Zf Giant", "{3}{R}", 4, "Creature — Giant", "", ("5", "5"), "R"),
    real("Zf Wall", "{2}", 2, "Artifact Creature — Wall", "", ("0", "4"), ""),
    real("Zf Dragon", "{4}{R}{R}", 6, "Creature — Dragon", "Flying", ("5", "5"), "R"),
    real("Zf Kill", "{B}", 1, "Instant", "Destroy target creature.", None, "B"),
]


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


# -- helpers ----------------------------------------------------------------------------------------------------------------------------------
def three(cards, mine=(), bobs=(), carols=(), sandbox=False):
    """Alice, Bob and Carol; rules on, Alice's first main phase. ``sandbox``: rules off, set things up, then ``rules_on`` (whatever is on the
    battlefield by then isn't summoning sick)."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (10, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bobs), (10, "Island")])
    carol = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in carols), (10, "Island")])
    game = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)], shuffle=False)
    s = GameSession(game if sandbox else enable(game), cards=cards)
    if not sandbox:
        act(s, "p1", type="pass_priority")
    return s


def rules_on(s):
    """A sandbox table goes live: Alice's first main phase."""
    turn_on(s)
    act(s, "p1", type="pass_priority")


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


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id if hasattr(c, "id") else c])


def field(s, pid="p1"):
    return [s.state.cards[i] for i in s.state.zones.get(f"{pid}:battlefield", [])]


def kill(s, victim, pid="p1"):
    """``pid`` casts Zf Kill on ``victim`` and everything resolves."""
    mana(s, pid, B=1)
    cast(s, "Zf Kill", [victim.id], pid=pid)
    answer(s)


def to_gy(s, c):
    act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})


# -- Borg tokens ------------------------------------------------------------------------------------------------------------------------------
def test_tenacious_drone_leaves_a_borg_token(cards):
    s = three(cards, ["Tenacious Drone", "Zf Kill"])
    drone = put(s, "Tenacious Drone")
    kill(s, drone)
    assert s.state.cards[drone.id].zone == "p1:graveyard"
    [token] = [c for c in field(s) if c.is_token]
    c = ch(s, token)
    assert c.name == "Borg" and c.pt == (1, 1) and c.types == frozenset({"Artifact", "Creature"}) and c.subtypes == frozenset({"Borg"})
    assert not c.colors
    check(s)


@pytest.mark.parametrize("color", ["Red", "Green"])
def test_borg_incursion_protects_the_artifact_creatures_it_saw(cards, color):
    s = three(cards, ["Borg Incursion", "Zf Wall", "Zf Bear"])
    wall, bear = put(s, "Zf Wall"), put(s, "Zf Bear")
    mana(s, W=1, C=2)
    cast(s, "Borg Incursion")
    answer(s, color)
    borgs = [c for c in field(s) if c.is_token]
    assert len(borgs) == 2 and all(ch(s, b).subtypes == frozenset({"Borg"}) for b in borgs)
    shield = f"Protection from {color.lower()}."
    for c in [*borgs, wall]:
        assert shield in {a.text for a in ch(s, c).abilities}
    assert shield not in {a.text for a in ch(s, bear).abilities}  # (not an artifact)
    # 611.2c: an artifact creature that arrives later doesn't gain it
    act(s, "p1", type="create_token", player="p1", token={"name": "Late Borg", "type_line": "Token Artifact Creature — Borg", "power": "1",
                                                           "toughness": "1", "text": ""})
    late = next(c for c in field(s) if c.name == "Late Borg")
    assert shield not in {a.text for a in ch(s, late).abilities}
    check(s)


# -- Curzon Dax ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("victim", "owner", "pings"), [("Zf Klingon", "p1", True), ("Zf Warrior", "p1", True), ("Zf Bear", "p1", False),
                                                         ("Zf Klingon", "p2", False)])
def test_curzon_dax_pings_each_opponent_when_another_klingon_or_warrior_dies(cards, victim, owner, pings):
    s = three(cards, ["Curzon Dax, Bound by Blood", "Zf Klingon", "Zf Warrior", "Zf Bear", "Zf Kill"], bobs=["Zf Klingon"])
    put(s, "Curzon Dax, Bound by Blood")
    target = put(s, victim, owner)
    kill(s, target)
    assert (life(s, "p2"), life(s, "p3"), life(s, "p1")) == ((39, 39, 40) if pings else (40, 40, 40))
    check(s)


@pytest.mark.parametrize("put_one", [True, False])
def test_curzon_dax_dying_puts_a_small_creature_from_hand(cards, put_one):
    s = three(cards, ["Curzon Dax, Bound by Blood", "Zf Klingon", "Zf Giant", "Zf Kill"])
    dax = put(s, "Curzon Dax, Bound by Blood")
    klingon, giant = to_hand(s, "Zf Klingon"), to_hand(s, "Zf Giant")
    mana(s, B=1)
    cast(s, "Zf Kill", [dax.id])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            ids = {o.id for o in d.options}
            assert giant.id not in ids  # (mana value 4)
            pick = [klingon.id] if put_one and klingon.id in ids else [o.id for o in d.options if o.id not in (klingon.id,)][:d.min_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[klingon.id].zone == ("p1:battlefield" if put_one else "p1:hand")
    assert life(s, "p2") == 40  # (Curzon Dax's own death isn't "another")
    check(s)


# -- Saavik --------------------------------------------------------------------------------------------------------------------------------------
def _saavik_in_combat(cards, borg_human):
    """Alice attacks Bob with Zf Warrior (Human Warrior); Bob blocks with Zf Dragon; Alice flashes Saavik in after blockers."""
    s = three(cards, ["Saavik, Stoic Student", "Zf Warrior", "Zf Drone", "Tenacious Drone"], bobs=["Zf Dragon", "Zf Giant"], sandbox=True)
    warrior = put(s, "Zf Warrior")
    put(s, "Tenacious Drone")  # (a Borg: doesn't count)
    if borg_human:
        put(s, "Zf Drone")  # (Borg Human Rogue: not counted at all, not even its Rogue)
    dragon = put(s, "Zf Dragon", "p2")
    put(s, "Zf Giant", "p2")  # (Bob's, but not in combat)
    rules_on(s)
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": warrior.id, "target": "p2"}])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers" and d.player == "p2":
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": dragon.id, "attacker_id": warrior.id}])
            break
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.phase == "declare_blockers"
    return s, warrior, dragon


@pytest.mark.parametrize("borg_human", [False, True])
def test_saavik_deals_the_number_of_creature_types_among_non_borg_creatures(cards, borg_human):
    s, warrior, dragon = _saavik_in_combat(cards, borg_human)
    assert s.state.rules.priority == "p1"
    mana(s, W=1, C=4)
    cast(s, "Saavik, Stoic Student", [dragon.id])
    answer(s)
    # Saavik (Vulcan Advisor) + Zf Warrior (Human Warrior): Vulcan, Advisor, Human, Warrior = 4; the Borg creatures add nothing
    assert s.state.cards[dragon.id].damage == 4
    check(s)


def test_saavik_targets_only_an_opponents_creature_in_combat(cards):
    s, warrior, dragon = _saavik_in_combat(cards, False)
    giant = card_named(s, "Zf Giant", "p2")
    mana(s, W=1, C=4)
    cast(s, "Saavik, Stoic Student")
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and {o.id for o in d.options} == {dragon.id} and giant.id not in {o.id for o in d.options}
    with pytest.raises(ActionError):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[warrior.id])  # (her controller's own attacker)
    answer(s)
    assert s.state.cards[dragon.id].damage == 4
    check(s)


# -- Voq ---------------------------------------------------------------------------------------------------------------------------------------
def _voq(s, pick):
    """Cast Voq; the entry question is answered with ``pick`` (a card id, or None: decline)."""
    mana(s, B=1, C=3)
    voq = cast(s, "Voq, Torchbearer")
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            chosen = [pick] if pick in ids else ["none"] if "none" in ids else ids[:max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return voq


def test_voq_enters_as_a_copy_of_a_graveyard_creature_plus_klingon_spy_and_menace(cards):
    s = three(cards, ["Voq, Torchbearer"], bobs=["Zf Dragon"])
    dragon = card_named(s, "Zf Dragon", "p2")
    to_gy(s, dragon)
    voq = _voq(s, dragon.id)
    c = ch(s, voq)
    assert c.name == "Zf Dragon" and c.pt == (5, 5)
    assert c.subtypes == frozenset({"Dragon", "Klingon", "Spy"})
    assert {"flying", "menace"} <= {k.lower() for k in c.keywords}
    assert s.state.cards[dragon.id].zone == "p2:graveyard"  # (a copy of the card: it stays)
    check(s)


def test_voq_declines_and_enters_as_himself(cards):
    s = three(cards, ["Voq, Torchbearer"], bobs=["Zf Dragon"])
    to_gy(s, card_named(s, "Zf Dragon", "p2"))
    voq = _voq(s, None)
    c = ch(s, voq)
    assert c.name == "Voq, Torchbearer" and c.pt == (4, 3) and "menace" in {k.lower() for k in c.keywords}
    check(s)


# -- Julian Bashir ---------------------------------------------------------------------------------------------------------------------------
def _decision(s, limit=20):
    """Pass priority until a decision comes up (it is returned), or nothing is left."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            return d
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


def _bashir_attacks(cards, counters):
    s = three(cards, ["Julian Bashir, Frontier Doctor", "Zf Elf", "Zf Bear", "Zf Giant"], sandbox=True)
    bashir = put(s, "Julian Bashir, Frontier Doctor")
    elf, bear, giant = (card_named(s, n) for n in ("Zf Elf", "Zf Bear", "Zf Giant"))
    act(s, "p1", type="move", card_ids=[elf.id, bear.id, giant.id], to={"player": "p1", "zone": "graveyard"})
    if counters:
        act(s, "p1", type="set_counter", card_id=bashir.id, kind="+1/+1", value=counters)
    rules_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bashir.id, "target": "p2"}])
    return s, bashir, elf, bear, giant


@pytest.mark.parametrize("counters", [0, 1])
def test_julian_bashir_returns_a_creature_card_with_mana_value_up_to_his_power(cards, counters):
    s, bashir, elf, bear, giant = _bashir_attacks(cards, counters)
    d = _decision(s)
    assert d is not None and {o.id for o in d.options} & {elf.id, bear.id, giant.id} == ({elf.id} if counters == 0 else {elf.id, bear.id})
    pick = bear if counters else elf
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick.id])
    answer(s)
    assert s.state.cards[pick.id].zone == "p1:battlefield" and s.state.cards[giant.id].zone == "p1:graveyard"
    check(s)


def test_julian_bashir_bound_is_read_again_as_it_resolves(cards):
    s, bashir, elf, bear, giant = _bashir_attacks(cards, 1)
    act(s, "p1", type="set_prefs", response="on")  # (Alice keeps priority with the trigger on the stack)
    d = _decision(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])
    assert s.state.zones.get("stack") and s.state.rules.priority == "p1"
    act(s, "p1", type="set_counter", card_id=bashir.id, kind="+1/+1", value=0)  # (power 1 now: the Bear's mana value 2 is too much, 608.2b)
    answer(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    check(s)


def test_julian_bashir_seek_out_counts_the_second_draw(cards):
    from app.rules import history

    s = three(cards, ["Julian Bashir, Frontier Doctor", "Zf Sage"])
    bashir, sage = put(s, "Julian Bashir, Frontier Doctor"), put(s, "Zf Sage")
    seen = []
    for _ in range(3):
        mana(s, C=1)
        act(s, "p1", type="activate_ability", card_id=sage.id, ability=0)
        answer(s)
        drew = history.log_for(Plan(s.state, "p1", s.cards, None)).drew.get("p1", 0)
        seen.append((drew, s.state.cards[bashir.id].counters.get("+1/+1", 0)))
    assert all(n == (1 if drew >= 2 else 0) for drew, n in seen) and seen[-1][1] == 1  # (only the second card drawn this turn)
    check(s)


# -- Temporal Conqueror ----------------------------------------------------------------------------------------------------------------------
def _top(s, names, pid="p1"):
    """The named cards of ``pid`` on top of their library, the first named on top."""
    ids: list[str] = []
    for n in names:
        ids.append(next(c.id for c in s.state.cards.values() if c.name == n and c.owner == pid and c.id not in ids and not c.zone.endswith("battlefield")))
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "library"})
    assert s.state.zones[f"{pid}:library"][: len(ids)] == ids
    return ids


@pytest.mark.parametrize(("milled", "in_gy", "returned"), [
    (["Zf Bear", "Mountain", "Zf Elf"], False, True),      # a land milled: it comes back, no Treasure
    (["Zf Bear", "Zf Elf", "Zf Giant"], False, False),     # no land card at all: a Treasure instead
    (["Zf Bear", "Zf Elf", "Zf Giant"], True, True),       # a land card already in the graveyard counts too
])
def test_temporal_conqueror_returns_a_land_card_or_makes_a_treasure(cards, milled, in_gy, returned):
    s = three(cards, ["Temporal Conqueror", "Zf Bear", "Zf Elf", "Zf Giant"])
    if in_gy:
        land = next(c for c in s.state.cards.values() if c.name == "Mountain" and c.owner == "p1" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "graveyard"})
    ids = _top(s, milled)
    mana(s, G=1, C=2)
    cast(s, "Temporal Conqueror")
    answer(s)
    assert all(s.state.cards[i].zone in ("p1:graveyard", "p1:hand") for i in ids)
    lands_in_hand = [c for c in (s.state.cards[i] for i in s.state.zones["p1:hand"]) if c.name == "Mountain"]
    treasures = [c for c in field(s) if c.name == "Treasure"]
    assert (len(lands_in_hand), len(treasures)) == ((1, 0) if returned else (0, 1))
    check(s)


# -- Species 8472 ------------------------------------------------------------------------------------------------------------------------------
def _species(cards):
    s = three(cards, ["Species 8472", "Zf Rod"], bobs=["Zf Rod", "Zf Pinger", "Zf Bear"], sandbox=True)
    species = put(s, "Species 8472")
    mine = put(s, "Zf Rod")
    rod, pinger, bear = put(s, "Zf Rod", "p2"), put(s, "Zf Pinger", "p2"), put(s, "Zf Bear", "p2")
    rules_on(s)
    return s, species, mine, rod, pinger, bear


def test_species_8472_cant_be_targeted_by_an_opponents_artifact_ability(cards):
    s, species, mine, rod, pinger, bear = _species(cards)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and not s.state.zones.get("stack") and s.state.rules.priority == "p2")
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=rod.id, ability=0, targets=[species.id])
    act(s, "p2", type="activate_ability", card_id=rod.id, ability=0, targets=[bear.id])  # (another creature: fine)
    answer(s)
    act(s, "p2", type="activate_ability", card_id=pinger.id, ability=0, targets=[species.id])  # (a creature's ability, not an artifact's)
    answer(s)
    assert s.state.cards[species.id].damage == 1 and s.state.cards[bear.id].damage == 1
    check(s)


def test_species_8472_can_be_targeted_by_its_controllers_artifact(cards):
    s, species, mine, rod, pinger, bear = _species(cards)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=0, targets=[species.id])
    answer(s)
    assert s.state.cards[species.id].damage == 1
    check(s)


def test_species_8472_gains_life_for_each_land_name(cards):
    s = three(cards, ["Species 8472"], sandbox=True)
    for c in [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Mountain"][:3]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    rules_on(s)
    mana(s, G=2, C=4)
    cast(s, "Species 8472")
    answer(s)
    assert life(s) == 41  # (three Mountains: one name)
    check(s)


# -- Communicators -------------------------------------------------------------------------------------------------------------------------
def _cast_pair(s, name, cost=3):
    """Cast the Communicator: its cast trigger copies it, so two of them enter (one a token)."""
    mana(s, C=cost)
    cast(s, name)
    answer(s)
    pair = [c for c in field(s) if c.name == name]
    assert len(pair) == 2 and sorted(c.is_token for c in pair) == [False, True]
    return pair


def _to_blocks(s):
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            return d
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blocks")


def test_combadge_copy_and_unblockable_when_another_communicator_host_is_there(cards):
    s = three(cards, ["Combadge", "Zf Bear", "Zf Elf"], bobs=["Zf Giant"], sandbox=True)
    bear, elf, giant = put(s, "Zf Bear"), put(s, "Zf Elf"), put(s, "Zf Giant", "p2")
    rules_on(s)
    first, second = _cast_pair(s, "Combadge")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=first.id, ability=2, targets=[bear.id])  # (Equip {2})
    answer(s)
    act(s, "p1", type="attach", card_ids=[second.id], to=elf.id)
    assert s.state.cards[first.id].attached_to == bear.id
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    d = _to_blocks(s)
    assert d.player == "p2"
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": giant.id, "attacker_id": bear.id}])
    act(s, "p2", type="declare_blockers", blocks=[])
    check(s)


@pytest.mark.parametrize("other", ["none", "gear"])
def test_combadge_needs_another_creature_with_a_communicator(cards, other):
    s = three(cards, ["Combadge", "Zf Bear", "Zf Elf", "Zf Gear"], bobs=["Zf Giant"], sandbox=True)
    bear, elf, giant = put(s, "Zf Bear"), put(s, "Zf Elf"), put(s, "Zf Giant", "p2")
    badge = put(s, "Combadge")
    act(s, "p1", type="attach", card_ids=[badge.id], to=bear.id)
    if other == "gear":  # (an Equipment that isn't a Communicator)
        gear = put(s, "Zf Gear")
        act(s, "p1", type="attach", card_ids=[gear.id], to=elf.id)
    rules_on(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    _to_blocks(s)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": giant.id, "attacker_id": bear.id}])  # (no trigger: it can be blocked)
    check(s)


@pytest.mark.parametrize("hosts", [1, 2])
def test_starfleet_communicator_draws_and_puts_lands_for_each_other_communicator_host(cards, hosts):
    s = three(cards, ["Starfleet Communicator", "Combadge", "Zf Bear", "Zf Elf", "Zf Warrior"], sandbox=True)
    bear, elf, warrior = put(s, "Zf Bear"), put(s, "Zf Elf"), put(s, "Zf Warrior")
    badge = put(s, "Combadge")
    act(s, "p1", type="attach", card_ids=[badge.id], to=elf.id)
    lands = [c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Mountain"][:3]
    act(s, "p1", type="move", card_ids=[c.id for c in lands], to={"zone": "hand"})
    rules_on(s)
    first, second = _cast_pair(s, "Starfleet Communicator")
    act(s, "p1", type="attach", card_ids=[first.id], to=bear.id)
    if hosts == 2:
        act(s, "p1", type="attach", card_ids=[second.id], to=warrior.id)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    put_lands: list[str] = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
            continue
        if d is not None:
            ids = [o.id for o in d.options if o.id in {c.id for c in lands}]
            assert d.max_choices == hosts  # (up to X: the other creatures with a Communicator — the Elf (Combadge), and the Warrior)
            put_lands = ids[: d.max_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=put_lands)
            continue
        if s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert len(put_lands) == hosts
    assert all(s.state.cards[i].zone == "p1:battlefield" and s.state.cards[i].tapped for i in put_lands)
    assert len(s.state.zones["p1:hand"]) == hand + hosts - len(put_lands)  # (drew X, put X lands)
    check(s)


# -- Worf --------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("carols", [True, False])
def test_worf_borrows_one_small_creature_of_each_opponent_as_a_hasty_warrior(cards, carols):
    s = three(cards, ["Worf, Intelligence Contractor"], bobs=["Zf Bear", "Zf Giant"], carols=["Zf Elf"])
    bear, giant, elf = put(s, "Zf Bear", "p2"), put(s, "Zf Giant", "p2"), put(s, "Zf Elf", "p3")
    act(s, "p2", type="tap", card_ids=[bear.id])
    mana(s, R=1, C=2)
    cast(s, "Worf, Intelligence Contractor")
    asked = []
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            ids = {o.id for o in d.options}
            asked.append(ids)
            pick = [bear.id] if bear.id in ids else [elf.id] if elf.id in ids and carols else []
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert asked[:2] == [{bear.id}, {elf.id}]  # (one group per opponent, 601.2c; the Giant's mana value is 4)
    taken = [bear, elf] if carols else [bear]
    for c in taken:
        x = ch(s, c)
        assert s.state.cards[c.id].controller == "p1" and not s.state.cards[c.id].tapped
        assert "Warrior" in x.subtypes and "haste" in {k.lower() for k in x.keywords}
    assert s.state.cards[giant.id].controller == "p2"
    if not carols:
        assert s.state.cards[elf.id].controller == "p3" and "Warrior" not in ch(s, elf).subtypes
    check(s)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert s.state.cards[bear.id].controller == "p2" and "Warrior" not in ch(s, bear).subtypes  # (until end of turn)
    check(s)


# -- token copies -------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("x", [0, 2])
def test_dominion_infiltration_copies_x_targets_as_hasty_changelings_until_the_end_step(cards, x):
    s = three(cards, ["Dominion Infiltration"], bobs=["Zf Bear", "Zf Dragon"], carols=["Zf Giant"])
    bear, dragon, giant = put(s, "Zf Bear", "p2"), put(s, "Zf Dragon", "p2"), put(s, "Zf Giant", "p3")
    mana(s, R=3, C=x)
    cast(s, "Dominion Infiltration", [bear.id, giant.id][:x], x_value=x)
    answer(s)
    made = [c for c in field(s) if c.is_token]
    assert sorted(ch(s, c).name for c in made) == sorted(["Zf Bear", "Zf Giant"][:x])
    for c in made:
        x_ch = ch(s, c)
        assert {"Borg", "Klingon", "Bear" if x_ch.name == "Zf Bear" else "Giant"} <= x_ch.subtypes  # (changeling: every creature type, 702.73a)
        assert "haste" in {k.lower() for k in x_ch.keywords}
    assert s.state.cards[dragon.id].controller == "p2"
    check(s)
    until(s, lambda s: s.state.turn.number == 2)
    assert not [c for c in field(s) if c.is_token]  # (exiled at the beginning of the next end step)
    check(s)


@pytest.mark.parametrize("kicked", [False, True])
def test_mirror_universe_intrusion_copies_one_creature_or_all_of_target_opponents(cards, kicked):
    s = three(cards, ["Mirror Universe Intrusion"], bobs=["Zf Bear", "Zf Dragon"], carols=["Zf Giant"])
    put(s, "Zf Bear", "p2"), put(s, "Zf Dragon", "p2")
    giant = put(s, "Zf Giant", "p3")
    mana(s, U=2 if kicked else 1, B=2 if kicked else 1, C=5 if kicked else 1)
    spell = to_hand(s, "Mirror Universe Intrusion")
    if kicked:
        act(s, "p1", type="cast_spell", card_id=spell.id, kicker=1, targets=["p2"], target_counts=[0, 1])
    else:
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[giant.id], target_counts=[1, 0])
    answer(s)
    made = sorted(ch(s, c).name for c in field(s) if c.is_token)
    assert made == (["Zf Bear", "Zf Dragon"] if kicked else ["Zf Giant"])  # (kicked: every creature Bob controls; 608.2c "instead")
    assert all("menace" in {k.lower() for k in ch(s, c).keywords} for c in field(s) if c.is_token)
    check(s)


# -- Gwyndala -----------------------------------------------------------------------------------------------------------------------------------
def test_gwyndala_heirloom_and_equipment_tokens_become_copies_until_end_of_turn(cards):
    s = three(cards, ["Gwyndala, the Progeny", "Zf Gear", "Zf Bear"])
    gear, bear = put(s, "Zf Gear"), put(s, "Zf Bear")
    act(s, "p1", type="attach", card_ids=[gear.id], to=bear.id)
    mana(s, U=1, C=1)
    gwyndala = cast(s, "Gwyndala, the Progeny")
    answer(s)
    [heirloom] = [c for c in field(s) if c.is_token]
    assert ch(s, heirloom).name == "Neuroflux Heirloom" and s.state.cards[heirloom.id].attached_to == gwyndala.id
    assert ch(s, gwyndala).pt == (2, 2)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=gwyndala.id, ability=1, targets=[gear.id])
    answer(s)
    assert ch(s, heirloom).name == "Zf Gear" and s.state.cards[heirloom.id].attached_to == gwyndala.id  # (still attached: not a copiable value)
    assert ch(s, gwyndala).pt == (2, 1) and ch(s, bear).pt == (3, 2) and ch(s, gear).name == "Zf Gear"
    check(s)
    until(s, lambda s: s.state.turn.number == 2)
    assert ch(s, heirloom).name == "Neuroflux Heirloom" and ch(s, gwyndala).pt == (2, 2)  # (until end of turn)
    check(s)


# -- U.S.S. Prometheus --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("charge", [7, 8])
def test_prometheus_at_eight_deals_its_combat_damage_to_each_other_opponent(cards, charge):
    s = three(cards, ["U.S.S. Prometheus, Prototype"], sandbox=True)
    ship = put(s, "U.S.S. Prometheus, Prototype")
    act(s, "p1", type="set_counter", card_id=ship.id, kind="charge", value=charge)
    rules_on(s)
    assert ch(s, ship).is_creature and ch(s, ship).pt == (6, 6)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ship.id, "target": "p2"}])
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack"))
    assert (life(s, "p2"), life(s, "p3"), life(s)) == (34, 34 if charge == 8 else 40, 40)
    check(s)


# -- free casts ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("exiles", [True, False])
def test_brazen_bluff_the_spells_controller_exiles_it_or_you_cast_for_free(cards, exiles):
    s = three(cards, ["Brazen Bluff", "Zf Bear", "Zf Rod", "Zf Giant"], bobs=["Zf Kill"])
    bear = put(s, "Zf Bear")
    rod, giant = to_hand(s, "Zf Rod"), to_hand(s, "Zf Giant")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    mana(s, "p2", B=1)
    kill = cast(s, "Zf Kill", [bear.id], pid="p2")
    for _ in range(5):
        if s.state.rules.priority == "p1":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    mana(s, R=2)
    cast(s, "Brazen Bluff", [kill.id])
    asked = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            asked.append((d.player, sorted(o.id for o in d.options)))
            if d.player == "p2":
                act(s, "p2", type="choose", decision_id=d.id, option_ids=["exile" if exiles else "keep"])
            else:
                assert giant.id not in {o.id for o in d.options}  # (a creature spell isn't offered)
                act(s, "p1", type="choose", decision_id=d.id, option_ids=[rod.id] if rod.id in {o.id for o in d.options} else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert asked[0] == ("p2", ["exile", "keep"])  # (the target spell's controller decides first)
    if exiles:
        assert s.state.cards[kill.id].zone == "p2:exile" and s.state.cards[bear.id].zone == "p1:battlefield"
        assert s.state.cards[rod.id].zone == "p1:hand" and len(asked) == 1
    else:
        assert s.state.cards[kill.id].zone == "p2:graveyard" and s.state.cards[bear.id].zone == "p1:graveyard"
        assert s.state.cards[rod.id].zone == "p1:battlefield"  # (cast without paying its mana cost)
    check(s)


@pytest.mark.parametrize("types", [1, 3])
def test_infinite_diversity_copies_the_card_once_per_creature_type_among_non_borg_creatures(cards, types):
    s = three(cards, ["Infinite Diversity", "Zf Shock", "Zf Elf", "Zf Warrior", "Tenacious Drone"])
    shock = card_named(s, "Zf Shock")
    to_gy(s, shock)
    put(s, "Tenacious Drone")  # (a Borg: none of its types count)
    put(s, "Zf Elf")  # (Elf)
    if types == 3:
        put(s, "Zf Warrior")  # (Human Warrior)
    mana(s, R=2, C=7)
    spell = cast(s, "Infinite Diversity", [shock.id])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.id == "p2"] or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p2") == 40 - 2 * types  # (each copy cast for free, each targeting Bob)
    assert s.state.cards[shock.id].zone == "p1:exile" and s.state.cards[spell.id].zone == "p1:exile"
    check(s)


# -- Alexander ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("tops", "x"), [((("Zf Giant", "p1"), ("Zf Bear", "p2"), ("Island", "p3")), 4), ((("Mountain", "p1"), ("Island", "p2"), ("Island", "p3")), 0)])
def test_alexander_reveals_draws_and_hits_a_random_opponent_for_the_greatest_mana_value(cards, tops, x):
    s = three(cards, ["Alexander, Ship's Fool", "Zf Giant"], bobs=["Zf Bear"], sandbox=True)
    alexander = put(s, "Alexander, Ship's Fool")
    rules_on(s)  # (Alice's draw step: the tops are set after it)
    for name, pid in tops:
        _top(s, [name], pid)
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2", "p3")}
    act(s, "p1", type="activate_ability", card_id=alexander.id, ability=1)
    answer(s)
    assert {p: len(s.state.zones[f"{p}:hand"]) for p in hands} == {p: n + 1 for p, n in hands.items()}  # (each player drew the revealed card)
    lost = sorted(40 - life(s, p) for p in ("p2", "p3"))
    assert lost == [0, x] and life(s) == 40  # (one opponent, picked at random; never Alexander's controller)
    check(s)


# -- Dr. McCoy ------------------------------------------------------------------------------------------------------------------------------------
def _mccoy(s, mode, target):
    """Cast Dr. McCoy; the mode is the one whose label starts with ``mode``, the target ``target`` (a card id)."""
    mana(s, G=2, C=1)
    mccoy = cast(s, 'Dr. Leonard "Bones" McCoy')
    seen = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            seen.append({o.id: o.label for o in d.options})
            mode_pick = [o.id for o in d.options if o.label.startswith(mode)]
            pick = mode_pick[:1] or ([target] if target in ids else ids[: max(1, d.min_choices)])
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return mccoy, seen


@pytest.mark.parametrize("whose", ["p1", "p2"])
def test_mccoy_returns_the_creature_that_died_this_turn_at_the_next_end_step(cards, whose):
    s = three(cards, ['Dr. Leonard "Bones" McCoy', "Zf Bear", "Zf Kill"], bobs=["Zf Bear"])
    bear = put(s, "Zf Bear", whose)
    _mccoy(s, "Choose up to one", bear.id)
    kill(s, bear)
    assert s.state.cards[bear.id].zone == f"{whose}:graveyard"
    until(s, lambda s: s.state.turn.number == 2)
    back = s.state.cards[bear.id]
    assert back.zone == f"{whose}:battlefield" and back.controller == whose and back.counters.get("+1/+1") == 1  # (under its owner's control)
    assert ch(s, back).pt == (3, 3)
    check(s)


def test_mccoy_watches_only_this_turn(cards):
    s = three(cards, ['Dr. Leonard "Bones" McCoy', "Zf Bear", "Zf Kill"])
    bear = put(s, "Zf Bear")
    _mccoy(s, "Choose up to one", bear.id)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.priority == "p1")
    kill(s, bear)  # (dies on a later turn: not "this turn")
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    until(s, lambda s: s.state.turn.number == 5)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    check(s)


def test_mccoy_card_that_left_the_graveyard_doesnt_come_back(cards):
    s = three(cards, ['Dr. Leonard "Bones" McCoy', "Zf Bear", "Zf Kill"])
    bear = put(s, "Zf Bear")
    _mccoy(s, "Choose up to one", bear.id)
    kill(s, bear)
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "exile"})
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "graveyard"})  # (a new object, 400.7)
    until(s, lambda s: s.state.turn.number == 2)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    check(s)


def test_mccoy_returns_a_non_doctor_permanent_card(cards):
    s = three(cards, ['Dr. Leonard "Bones" McCoy', "Zf Bear", "Zf Medic", "Zf Kill"])
    bear, medic, spell = card_named(s, "Zf Bear"), card_named(s, "Zf Medic"), card_named(s, "Zf Kill")
    act(s, "p1", type="move", card_ids=[bear.id, medic.id, spell.id], to={"player": "p1", "zone": "graveyard"})
    _, seen = _mccoy(s, "Return target", bear.id)
    targets = next(x for x in seen if bear.id in x)
    assert medic.id not in targets and spell.id not in targets  # (a Doctor; not a permanent card)
    assert s.state.cards[bear.id].zone == "p1:hand"
    check(s)
