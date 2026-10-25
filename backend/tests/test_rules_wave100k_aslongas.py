"""Wave 100K: "as long as" statics. Real Oracle text, every scenario checks the replay and a save and a load.

* "As long as this creature is monstrous, it has reach and can block an additional ninety-nine creatures each combat." (Hundred-Handed One,
  509.1a: block_extra 99, only while it is monstrous, 701.37b).
* "As long as this creature is attacking, defending player can't cast spells." (Wardscale Dragon): 506.2, 802.1b: the player it attacks;
  another opponent (multiplayer) still can.
* 115.2: "can't be the target of black or red spells your opponents control" (Fiendslayer Paladin), "… of abilities your opponents control"
  (Shanna, Sisay's Legacy): its controller's own spells and abilities may.
* "{R/G}: Target spell can't be countered." (Vexing Shusher): that one spell (101.2).
* "As long as there are two or more creature cards in your graveyard, this creature gets +2/+2 and is all creature types." (Undercover Skrull,
  205.3m, 613.1d: a condition about graveyard cards, never the battlefield's characteristics).
* "Whenever you cast a spell, creatures you control can't be the targets of spells or abilities your opponents control this turn." (Veilstone
  Amulet: a rules effect, so a creature that comes later this turn too, 611.2c).
* "At end of combat, gain control of all creatures blocking this creature for as long as you control this creature." (The Wretched: its
  blockers as it resolves, 511.3; its rulings).
* "After this phase, there is an additional combat phase. Only land creatures can attack during that combat phase." (Bumi, Unleashed: only that
  combat phase, its ruling; 500.8).
* "Sacrifice this creature: Until end of turn, if a nontoken creature would enter and it wasn't cast, exile it instead." (Mistcaller: tokens and
  cast creatures still enter, its rulings; 614.12, 611.2a).
* "During your end step, Warrior tokens you control have "This token can't be sacrificed."" (Zurgo: the mobilized tokens survive their end step
  sacrifice, 701.21a; any other step they can be).
* A token created with two quoted abilities (Pursued Whale's Pirate: "This token can't block" and "Creatures you control attack each combat if
  able.", 111.4, 508.1d, its ruling); the same grammar: Ozox's Jumblebones, Relic Robber's Goblin Construct.
* "As this creature enters, you may reveal a Dragon card from your hand. If you do or if you control a Dragon, this creature enters with a +1/+1
  counter on it." (Dragon's Disciple, 614.1c, 614.12a: asked in private; one counter even with both, its ruling).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import token_of, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [
    real('Hundred-Handed One', '{2}{W}{W}', 4, 'Creature — Giant',
         "Vigilance\n{3}{W}{W}{W}: Monstrosity 3. (If this creature isn't monstrous, put three +1/+1 counters on it and it becomes monstrous.)\nAs long as this "
         "creature is monstrous, it has reach and can block an additional ninety-nine creatures each combat.", ('3', '5'), 'W'),
    real('Wardscale Dragon', '{4}{W}{W}', 6, 'Creature — Dragon',
         "Flying\nAs long as this creature is attacking, defending player can't cast spells.", ('4', '4'), 'W'),
    real('Fiendslayer Paladin', '{1}{W}{W}', 3, 'Creature — Human Knight',
         "First strike (This creature deals combat damage before creatures without first strike.)\nLifelink (Damage dealt by this creature also causes you to "
         "gain that much life.)\nThis creature can't be the target of black or red spells your opponents control.", ('2', '2'), 'W'),
    real("Shanna, Sisay's Legacy", '{G}{W}', 2, 'Legendary Creature — Human Warrior',
         "Shanna can't be the target of abilities your opponents control.\nShanna gets +1/+1 for each creature you control.", ('0', '0'), 'GW'),
    real('Vexing Shusher', '{R/G}{R/G}', 2, 'Creature — Goblin Shaman',
         "This spell can't be countered.\n{R/G}: Target spell can't be countered.", ('2', '2'), 'GR'),
    real('Rangers of Ithilien', '{2}{U}{U}', 4, 'Creature — Human Ranger',
         'Vigilance\nWhen this creature enters, gain control of up to one target creature with lesser power for as long as you control this creature. Then the '
         'Ring tempts you.', ('3', '3'), 'U'),
    real('Imaginary Threats', '{2}{U}{U}', 4, 'Instant',
         "Creatures target opponent controls attack this turn if able. During that player's next untap step, creatures they control don't untap.\nCycling {2} "
         "({2}, Discard this card: Draw a card.)", None, 'U'),
    real('Walking Desecration', '{2}{B}', 3, 'Creature — Zombie',
         '{B}, {T}: Creatures of the creature type of your choice attack this turn if able.', ('1', '1'), 'B'),
    real('Undercover Skrull', '{1}{G}', 2, 'Creature — Skrull Shapeshifter Villain',
         'As long as there are two or more creature cards in your graveyard, this creature gets +2/+2 and is all creature types.\n{T}: Add one mana of any color.',
         ('1', '1'), 'G'),
    real('Veilstone Amulet', '{3}', 3, 'Artifact',
         "Whenever you cast a spell, creatures you control can't be the targets of spells or abilities your opponents control this turn.", None, ''),
    real('The Wretched', '{3}{B}{B}', 5, 'Creature — Demon',
         'At end of combat, gain control of all creatures blocking this creature for as long as you control this creature.', ('2', '5'), 'B'),
    real('Bumi, Unleashed', '{3}{R}{G}', 5, 'Legendary Creature — Human Noble Ally',
         'Trample\nWhen Bumi enters, earthbend 4.\nWhenever Bumi deals combat damage to a player, untap all lands you control. After this phase, there is an '
         'additional combat phase. Only land creatures can attack during that combat phase.', ('5', '4'), 'GR'),
    real('Mistcaller', '{U}', 1, 'Creature — Merfolk Wizard',
         "Sacrifice this creature: Until end of turn, if a nontoken creature would enter and it wasn't cast, exile it instead.", ('1', '1'), 'U'),
    real("Zurgo, Thunder's Decree", '{R}{W}{B}', 3, 'Legendary Creature — Orc Warrior',
         'Mobilize 2 (Whenever this creature attacks, create two tapped and attacking 1/1 red Warrior creature tokens. Sacrifice them at the beginning of the '
         'next end step.)\nDuring your end step, Warrior tokens you control have "This token can\'t be sacrificed."', ('2', '4'), 'BRW'),
    real('Pursued Whale', '{5}{U}{U}', 7, 'Creature — Whale',
         'When this creature enters, each opponent creates a 1/1 red Pirate creature token with "This token can\'t block" and "Creatures you control attack '
         'each combat if able."\nSpells your opponents cast that target this creature cost {3} more to cast.', ('8', '8'), 'U'),
    real("Dragon's Disciple", '{1}{W}', 2, 'Creature — Human Monk',
         'As this creature enters, you may reveal a Dragon card from your hand. If you do or if you control a Dragon, this creature enters with a +1/+1 '
         'counter on it.\nDragons you control have ward {1}. (Whenever a Dragon you control becomes the target of a spell or ability an opponent controls, '
         'counter it unless that player pays {1}.)', ('1', '3'), 'W'),
    real('Ozox, the Clattering King', '{2}{B}', 3, 'Legendary Creature — Skeleton Noble',
         'Ozox can\'t block.\nWhen Ozox dies, create Jumblebones, a legendary 2/1 black Skeleton creature token with "Jumblebones can\'t block" and "When '
         'Jumblebones leaves the battlefield, return target card named Ozox, the Clattering King from your graveyard to your hand."', ('3', '2'), 'B'),
    real('Relic Robber', '{2}{R}', 3, 'Creature — Goblin Rogue',
         'Haste\nWhenever this creature deals combat damage to a player, that player creates a 0/1 colorless Goblin Construct artifact creature token with '
         '"This token can\'t block" and "At the beginning of your upkeep, this token deals 1 damage to you."', ('2', '2'), 'R'),
]
HELPERS = [real("Gideon's Lawkeeper", '{W}', 1, 'Creature — Human Soldier', '{W}, {T}: Tap target creature.', ('1', '1'), 'W'),
           real('Reanimate', '{B}', 1, 'Sorcery', "Put target creature card from a graveyard onto the battlefield under your control. You lose life equal to "
                "that card's mana value.", None, 'B'),
           real('Shivan Dragon', '{4}{R}{R}', 6, 'Creature — Dragon', 'Flying\n{R}: This creature gets +1/+0 until end of turn.', ('5', '5'), 'R')]
NAMES = [c["name"] for c in EXTRA]
STEPS = ["main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat", "main2", "end"]


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


def settle(s, limit=60):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.mark.parametrize("monstrous", [False, True])
def test_hundred_handed_one_blocks_every_attacker_once_monstrous(cards, monstrous):
    s = build(cards, ["Hundred-Handed One"], ["Grizzly Bears", "Llanowar Elves", "Monastery Swiftspear"])
    giant = put(s, "Hundred-Handed One")
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    if monstrous:
        mana(s, W=3, C=3)
        act(s, "p1", type="activate_ability", card_id=giant.id, ability=1)
        settle(s)
        assert s.state.cards[giant.id].counters.get("+1/+1") == 3
    attackers = [put(s, n, "p2") for n in ("Grizzly Bears", "Llanowar Elves", "Monastery Swiftspear")]
    for c in attackers:
        s.state.rules.controlled_since[c.id].turn = 0
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p2")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p1"} for c in attackers])
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_blockers")
    blocks = [{"blocker_id": giant.id, "attacker_id": c.id} for c in attackers]
    if not monstrous:
        with pytest.raises(ActionError):
            act(s, "p1", type="declare_blockers", blocks=blocks)
        blocks = blocks[:1]
    act(s, "p1", type="declare_blockers", blocks=blocks)
    g = s.state.cards[giant.id]
    assert {g.blocking, *g.blocking_more} == {c.id for c in attackers[: len(blocks)]}
    check(s)


def three(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Wardscale Dragon"), (10, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Opt"), (10, "Island")])
    carol = deck(cards, "Atraxa, Praetors' Voice", [(1, "Opt"), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_wardscale_dragon_silences_only_the_player_it_attacks(cards):
    s = three(cards)
    dragon = put(s, "Wardscale Dragon")
    s.state.rules.controlled_since[dragon.id].turn = 0
    for pid in ("p2", "p3"):
        to_hand(s, "Opt", pid)
        act(s, pid, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": dragon.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.priority == "p2" and s.state.rules.decision is None)
    mana(s, "p2", U=1)
    with pytest.raises(ActionError):  # (Bob is the defending player)
        act(s, "p2", type="cast_spell", card_id=card_named(s, "Opt", "p2").id)
    act(s, "p2", type="pass_priority")
    until(s, lambda s: s.state.rules.priority == "p3" and s.state.rules.decision is None)
    mana(s, "p3", U=1)
    act(s, "p3", type="cast_spell", card_id=card_named(s, "Opt", "p3").id)  # (Carol isn't attacked)
    settle(s)
    assert card_named(s, "Opt", "p3").zone == "p3:graveyard"
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.rules.priority == "p2" and s.state.rules.decision is None)
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Opt", "p2").id)  # (the Dragon no longer attacks: 506.4)
    settle(s)
    assert card_named(s, "Opt", "p2").zone == "p2:graveyard"
    check(s)


def test_fiendslayer_paladin_refuses_only_an_opponents_black_or_red_spell(cards):
    s = build(cards, ["Lightning Bolt", "Giant Growth"], ["Fiendslayer Paladin", "Lightning Bolt"])
    paladin = put(s, "Fiendslayer Paladin", "p2")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    with pytest.raises(ActionError):  # (Alice's red spell: 115.2)
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[paladin.id])
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Giant Growth").id, targets=[paladin.id])  # (a green one may)
    settle(s)
    assert s.state.cards[paladin.id].zone == "p2:battlefield"
    from app.rules import targets
    from app.rules.plan import Plan

    plan = Plan(s.state, "p2", s.cards, None)
    theirs = targets.as_spell(plan.ch(card_named(s, "Lightning Bolt", "p2")))
    assert targets.can_target(plan, "p2", paladin, plan.ch(paladin), theirs)  # (its controller's own red spell may)
    assert not targets.can_target(plan, "p1", paladin, plan.ch(paladin), targets.as_spell(plan.ch(bolt)))
    check(s)


def test_shanna_refuses_only_an_opponents_ability(cards):
    s = build(cards, ["Gideon's Lawkeeper", "Lightning Bolt"], ["Shanna, Sisay's Legacy", "Grizzly Bears"])
    shanna = put(s, "Shanna, Sisay's Legacy", "p2")
    put(s, "Grizzly Bears", "p2")
    keeper = put(s, "Gideon's Lawkeeper")
    s.state.rules.controlled_since[keeper.id].turn = 0
    mana(s, W=1)
    with pytest.raises(ActionError):  # (Alice's ability: 115.2)
        act(s, "p1", type="activate_ability", card_id=keeper.id, ability=0, targets=[shanna.id])
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[shanna.id])  # (a spell may: Shanna is 2/2)
    settle(s)
    assert s.state.cards[shanna.id].zone == "p2:graveyard"
    check(s)


@pytest.mark.parametrize("hushed", [False, True])
def test_vexing_shusher_makes_the_target_spell_uncounterable(cards, hushed):
    s = build(cards, ["Vexing Shusher", "Grizzly Bears"], ["Counterspell"])
    shusher = put(s, "Vexing Shusher")
    to_hand(s, "Counterspell", "p2")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    act(s, "p1", type="set_prefs", hold_priority=True)
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    if hushed:
        mana(s, R=1)
        act(s, "p1", type="activate_ability", card_id=shusher.id, ability=1, targets=[bears.id])
        act(s, "p1", type="pass_priority")
        until(s, lambda s: s.state.zones["stack"] == [bears.id] and s.state.rules.priority == "p1")
        act(s, "p1", type="pass_priority")
    else:
        act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    mana(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Counterspell", "p2").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == ("p1:battlefield" if hushed else "p1:graveyard")
    check(s)


def test_rangers_of_ithilien_steals_a_smaller_creature_while_you_control_them(cards):
    """Its rulings: lesser power than the Rangers as the target is chosen; the Ring tempts you; control lasts while you control the Rangers."""
    s = build(cards, ["Rangers of Ithilien"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    big = token_of(s, "p2", "Ogre", "Token Creature — Ogre", "3/3")
    rangers = to_hand(s, "Rangers of Ithilien")
    mana(s, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=rangers.id)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind != "confirm" and bears.id in {o.id for o in d.options})
    d = s.state.rules.decision
    assert big.id not in {o.id for o in d.options}  # (3 isn't less than 3)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].controller == "p1" and "p1" in s.state.rules.ring_bearers  # (the Ring tempted Alice: 701.54a)
    act(s, "p1", type="set_damage", card_ids=[rangers.id], value=3)  # (the Rangers die: 704.5g)
    until(s, lambda s: s.state.cards[rangers.id].zone == "p1:graveyard" and not s.state.zones.get("stack"))
    assert s.state.cards[bears.id].controller == "p2"
    check(s)


def bobs_main(s):
    """Everyone stops in every step; Alice has priority in Bob's first main phase (turn 2)."""
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None and not s.state.zones.get("stack"))
    if s.state.rules.priority == "p2":
        act(s, "p2", type="pass_priority")
    assert s.state.rules.priority == "p1"


def bob_declares(s, attackers):
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p2")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p1"} for c in attackers])


def test_imaginary_threats_forces_the_attack_then_nothing_of_theirs_untaps(cards):
    """Its rulings: none of that player's creatures untap during their next untap step, those that enter later included."""
    s = build(cards, ["Imaginary Threats"], ["Grizzly Bears", "Llanowar Elves"])
    bears = put(s, "Grizzly Bears", "p2")
    s.state.rules.controlled_since[bears.id].turn = 0
    bobs_main(s)
    mana(s, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Imaginary Threats").id, targets=["p2"])
    settle(s)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p2")
    with pytest.raises(ActionError):  # (508.1d: the Bears must attack)
        act(s, "p2", type="declare_attackers", attackers=[])
    bob_declares(s, [bears])
    elves = put(s, "Llanowar Elves", "p2")  # (it comes later: tapped, it stays tapped too)
    act(s, "p2", type="tap", card_ids=[elves.id])
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")
    assert s.state.cards[bears.id].tapped and s.state.cards[elves.id].tapped
    until(s, lambda s: s.state.turn.number == 6 and s.state.turn.phase == "main1")
    assert not s.state.cards[bears.id].tapped  # (only that next untap step)
    check(s)


def test_walking_desecration_forces_only_the_chosen_type(cards):
    s = build(cards, ["Walking Desecration"], ["Grizzly Bears", "Llanowar Elves"])
    imp = put(s, "Walking Desecration")
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    for c in (imp, bears, elves):
        s.state.rules.controlled_since[c.id].turn = 0
    bobs_main(s)
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=imp.id, ability=0)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.player == "p1")
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["Bear"])
    settle(s)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p2")
    with pytest.raises(ActionError):  # (the Bears are a Bear: 508.1d)
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": elves.id, "target": "p1"}])
    bob_declares(s, [bears])  # (the Elves needn't)
    assert s.state.cards[bears.id].attacking is not None and s.state.cards[elves.id].attacking is None
    check(s)


def test_undercover_skrull_is_every_creature_type_with_two_creature_cards_in_your_graveyard(cards):
    from app.rules.plan import Plan

    s = build(cards, ["Undercover Skrull", "Grizzly Bears", "Llanowar Elves"], ["Monastery Swiftspear"])
    skrull = put(s, "Undercover Skrull")

    def ch():
        return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[skrull.id])

    act(s, "p1", type="move", card_ids=[card_named(s, "Grizzly Bears").id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[card_named(s, "Monastery Swiftspear", "p2").id], to={"player": "p2", "zone": "graveyard"})
    assert ch().pt == (1, 1) and "Goblin" not in ch().subtypes  # (one creature card in Alice's graveyard: Bob's doesn't count)
    act(s, "p1", type="move", card_ids=[card_named(s, "Llanowar Elves").id], to={"player": "p1", "zone": "graveyard"})
    assert ch().pt == (3, 3) and {"Goblin", "Elf", "Skrull", "Shapeshifter"} <= ch().subtypes
    check(s)


def test_veilstone_amulet_shields_your_creatures_for_the_turn(cards):
    from app.rules import targets
    from app.rules.plan import Plan

    s = build(cards, ["Veilstone Amulet", "Grizzly Bears", "Llanowar Elves"], ["Lightning Bolt"])
    put(s, "Veilstone Amulet")
    elves = put(s, "Llanowar Elves")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    settle(s)
    bears = card_named(s, "Grizzly Bears")
    plan = Plan(s.state, "p2", s.cards, None)
    bolt = targets.as_spell(plan.ch(card_named(s, "Lightning Bolt", "p2")))
    for c in (elves, bears):  # (the Bears entered after the trigger resolved: 611.2c)
        assert not targets.can_target(plan, "p2", s.state.cards[c.id], plan.ch(s.state.cards[c.id]), bolt)
        assert targets.can_target(plan, "p1", s.state.cards[c.id], plan.ch(s.state.cards[c.id]), bolt)  # (Alice's own may)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    plan = Plan(s.state, "p2", s.cards, None)
    assert targets.can_target(plan, "p2", s.state.cards[elves.id], plan.ch(s.state.cards[elves.id]), bolt)  # (this turn only)
    check(s)


def test_the_wretched_takes_its_blockers_while_you_control_it(cards):
    s = build(cards, ["The Wretched"], ["Grizzly Bears", "Llanowar Elves", "Monastery Swiftspear"])
    wretched = put(s, "The Wretched")
    bears, elves = token_of(s, "p2", "Wall", "Token Creature — Wall", "0/4"), token_of(s, "p2", "Ox", "Token Creature — Ox", "0/4")
    idle = put(s, "Monastery Swiftspear", "p2")
    s.state.rules.controlled_since[wretched.id].turn = 0
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": wretched.id, "target": "p2"}])
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": wretched.id}, {"blocker_id": elves.id, "attacker_id": wretched.id}])
    until(s, lambda s: (d := s.state.rules.decision) is not None and "Divide" in d.prompt)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, amounts=[2, 0])  # (its 2 damage, all to the first: 510.1c)
    until(s, lambda s: s.state.turn.phase == "main2")
    assert [s.state.cards[c.id].controller for c in (bears, elves, idle)] == ["p1", "p1", "p2"]  # (its blockers, not the other creature)
    act(s, "p1", type="set_damage", card_ids=[wretched.id], value=5)  # (it dies: control ends, 611.2b)
    until(s, lambda s: s.state.cards[wretched.id].zone == "p1:graveyard" and not s.state.zones.get("stack"))
    assert [s.state.cards[c.id].controller for c in (bears, elves)] == ["p2", "p2"]
    check(s)


def test_bumi_adds_a_combat_where_only_land_creatures_attack(cards):
    s = build(cards, ["Bumi, Unleashed", "Grizzly Bears"])
    forest = put(s, "Forest")
    bears = put(s, "Grizzly Bears")
    bumi = to_hand(s, "Bumi, Unleashed")
    mana(s, R=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=bumi.id)
    until(s, lambda s: (d := s.state.rules.decision) is not None and forest.id in {o.id for o in d.options})
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[forest.id])  # (earthbend 4: a 4/4 land creature with haste)
    settle(s)
    for c in (bumi, bears):
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bumi.id, "target": "p2"}])
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and s.state.rules.combats == 2)
    with pytest.raises(ActionError):  # (the Bears aren't a land creature)
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": forest.id, "target": "p2"}])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 40 - 5 - 4
    check(s)


def test_mistcaller_exiles_uncast_nontoken_creatures_this_turn(cards):
    s = build(cards, ["Mistcaller", "Grizzly Bears", "Llanowar Elves", "Raise the Alarm", "Reanimate"])
    imp = put(s, "Mistcaller")
    act(s, "p1", type="activate_ability", card_id=imp.id, ability=0)  # (its cost: sacrifice it)
    settle(s)
    assert s.state.cards[imp.id].zone == "p1:graveyard"
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Reanimate").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:exile"  # (put onto the battlefield, not cast)
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Raise the Alarm").id)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]) == 2  # (tokens still enter)
    elves = to_hand(s, "Llanowar Elves")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=elves.id)
    settle(s)
    assert s.state.cards[elves.id].zone == "p1:battlefield"  # (a cast creature enters)
    check(s)


def test_zurgo_keeps_the_mobilized_warriors_through_your_end_step(cards):
    s = build(cards, ["Zurgo, Thunder's Decree"])
    zurgo = put(s, "Zurgo, Thunder's Decree")
    s.state.rules.controlled_since[zurgo.id].turn = 0
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": zurgo.id, "target": "p2"}])
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number == turn + 1 and s.state.turn.phase == "main1")

    def warriors():
        return [c for c in s.state.cards.values() if c.is_token and c.name == "Warrior" and c.zone == "p1:battlefield"]

    assert len(warriors()) == 2  # (their "sacrifice at the beginning of the next end step" did nothing: 701.21a)
    act(s, "p1", type="move", card_ids=[zurgo.id], to={"player": "p1", "zone": "graveyard"})
    check(s)


def test_pursued_whale_gives_each_opponent_a_pirate_that_makes_them_attack(cards):
    s = build(cards, ["Pursued Whale"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    s.state.rules.controlled_since[bears.id].turn = 0
    mana(s, U=2, C=5)
    whale = to_hand(s, "Pursued Whale")
    act(s, "p1", type="cast_spell", card_id=whale.id)
    settle(s)
    pirate = next(c for c in s.state.cards.values() if c.is_token and c.name == "Pirate")
    assert pirate.controller == "p2"
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    s.state.rules.controlled_since[whale.id].turn = 0
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": whale.id, "target": "p2"}])
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_blockers")
    with pytest.raises(ActionError):  # ("This token can't block")
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": pirate.id, "attacker_id": whale.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": whale.id}])  # (the Bears may)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p2")
    with pytest.raises(ActionError):  # (the Pirate's ability: every creature Bob controls, 508.1d)
        act(s, "p2", type="declare_attackers", attackers=[])
    bob_declares(s, [pirate])
    check(s)


@pytest.mark.parametrize("hand, controls, reveal, counters", [
    (False, False, None, 0), (True, False, "none", 0), (True, False, "dragon", 1), (False, True, None, 1), (True, True, None, 1)])
def test_dragons_disciple_counter_for_a_revealed_or_controlled_dragon(cards, hand, controls, reveal, counters):
    s = build(cards, ["Dragon's Disciple", "Shivan Dragon", "Shivan Dragon", "Grizzly Bears"])
    first, second = [c for c in s.state.cards.values() if c.name == "Shivan Dragon"]
    if controls:
        act(s, "p1", type="move", card_ids=[first.id], to={"player": "p1", "zone": "battlefield"})
    if hand:
        act(s, "p1", type="move", card_ids=[second.id], to={"zone": "hand"})
    to_hand(s, "Grizzly Bears")  # (another card in hand: asked even with no Dragon there, hidden information)
    disciple = to_hand(s, "Dragon's Disciple")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=disciple.id)
    until(s, lambda s: s.state.rules.decision is not None or s.state.cards[disciple.id].zone == "p1:battlefield")
    d = s.state.rules.decision
    assert (d is not None) == (not controls)  # (you control one: nothing to ask)
    if d is not None:
        ids = [o.id for o in d.options]
        assert (second.id in ids) == hand and "none" in ids
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[second.id if reveal == "dragon" else "none"])
    settle(s)
    assert s.state.cards[disciple.id].zone == "p1:battlefield" and not s.state.cards[disciple.id].tapped
    assert s.state.cards[disciple.id].counters.get("+1/+1", 0) == counters
    check(s)


def test_ozox_jumblebones_returns_ozox_when_it_leaves(cards):
    s = build(cards, ["Ozox, the Clattering King"])
    ozox = put(s, "Ozox, the Clattering King")
    act(s, "p1", type="set_damage", card_ids=[ozox.id], value=2)  # (it dies: 704.5g)

    def bones():
        return next((c for c in s.state.cards.values() if c.is_token and c.name == "Jumblebones" and c.zone == "p1:battlefield"), None)

    until(s, lambda s: bones() is not None and not s.state.zones.get("stack"))
    assert s.state.cards[ozox.id].zone == "p1:graveyard"
    act(s, "p1", type="set_damage", card_ids=[bones().id], value=1)
    until(s, lambda s: s.state.cards[ozox.id].zone == "p1:hand")
    check(s)


def test_relic_robbers_construct_pings_its_controller_each_upkeep(cards):
    s = build(cards, ["Relic Robber"])
    robber = put(s, "Relic Robber")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": robber.id, "target": "p2"}])  # (haste)
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number == turn + 1 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
    construct = next(c for c in s.state.cards.values() if c.is_token and c.name == "Goblin Construct")
    assert construct.controller == "p2" and s.state.players["p2"].life == 40 - 2 - 1  # (combat damage, then Bob's upkeep)
    check(s)
