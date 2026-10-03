"""Wave 7C: counters, second pass. Researched against CR 2026-09-25.

* 702.62b: a card is suspended if it is in exile, has suspend and has a time counter on it; "Exile ~ with three time
  counters on it." (Arc Blade, Rousing Refrain …) is a spell's own instruction (608.2m/n: the spell leaves the stack
  where the text puts it) that suspends the card. Cast from exile via suspend, it resolves and does it again.

Every scenario uses real Oracle text and checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, settle, to_hand
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_suspend import until

EXTRA = [
    card('Rousing Refrain', set_code='tst', number='T7C1', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Sorcery', oracle_text="Add {R} for each card in target opponent's hand. Until end of turn, you don't lose this mana as steps and phases end. Exile Rousing Refrain with three time counters on it.\nSuspend 3—{1}{R} (Rather than cast this card from your hand, you may pay {1}{R} and exile it with three time counters on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its mana cost.)", colors=['R'], color_identity=['R'], keywords=['Suspend']),
    card('Inspiring Refrain', set_code='tst', number='T7C2', mana_cost='{4}{U}{U}', cmc=6.0, type_line='Sorcery', oracle_text='Draw two cards. Exile Inspiring Refrain with three time counters on it.\nSuspend 3—{2}{U} (Rather than cast this card from your hand, you may pay {2}{U} and exile it with three time counters on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its mana cost.)', colors=['U'], color_identity=['U'], keywords=['Suspend']),
    card('Arc Blade', set_code='tst', number='T7C3', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Sorcery', oracle_text='Arc Blade deals 2 damage to any target. Exile Arc Blade with three time counters on it.\nSuspend 3—{2}{R} (Rather than cast this card from your hand, you may pay {2}{R} and exile it with three time counters on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its mana cost.)', colors=['R'], color_identity=['R'], keywords=['Suspend']),
    card('Reality Strobe', set_code='tst', number='T7C4', mana_cost='{4}{U}{U}', cmc=6.0, type_line='Sorcery', oracle_text="Return target permanent to its owner's hand. Exile Reality Strobe with three time counters on it.\nSuspend 3—{2}{U} (Rather than cast this card from your hand, you may pay {2}{U} and exile it with three time counters on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its mana cost.)", colors=['U'], color_identity=['U'], keywords=['Suspend']),
    card('Generous Patron', set_code='tst', number='T7C5', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Elf Advisor', oracle_text="When this creature enters, support 2. (Put a +1/+1 counter on each of up to two other target creatures.)\nWhenever you put one or more counters on a creature you don't control, draw a card.", power='1', toughness='4', colors=['G'], color_identity=['G'], keywords=['Support']),
    card('Mikey & Leo, Chaos & Order', set_code='tst', number='T7C6', mana_cost='{G/W}{G/W}', cmc=2.0, type_line='Legendary Creature — Mutant Ninja Turtle', oracle_text='Whenever you put a counter on a creature you control, draw a card. This ability triggers only once each turn.', power='2', toughness='2', colors=['G', 'W'], color_identity=['G', 'W']),
    card('Ant-Man, Colony Commander', set_code='tst', number='T7C7', mana_cost='{1}{G}{U}', cmc=3.0, type_line='Legendary Creature — Human Rogue Hero', oracle_text='Whenever Ant-Man attacks, you may pay {1}. When you do, put a +1/+1 counter on target creature.\nWhenever you put a +1/+1 counter on a creature, create a 1/1 green Insect creature token. This ability triggers only once each turn.', power='2', toughness='2', colors=['G', 'U'], color_identity=['G', 'U']),
    card('Knight of Wundagore', set_code='tst', number='T7C8', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Cat Knight Villain', oracle_text='Trample\nWhenever you put a +1/+1 counter on another creature, put a +1/+1 counter on this creature. This ability triggers only once each turn.', power='2', toughness='1', colors=['G'], color_identity=['G'], keywords=['Trample']),
    card('The Great Goblin', set_code='tst', number='T7C9', mana_cost='{1}{B/R}{B/R}', cmc=3.0, type_line='Legendary Creature — Goblin Noble', oracle_text='Whenever you put one or more counters on a Goblin, Orc, or Army you control, The Great Goblin deals 2 damage to target opponent.\nWhenever another Goblin, Orc, or Army you control dies, exile the top card of your library. You may play it until the end of your next turn.', power='3', toughness='2', colors=['B', 'R'], color_identity=['B', 'R']),
    card('Rhox Pummeler', set_code='tst', number='T7C10', mana_cost='{5}{G}', cmc=6.0, type_line='Creature — Rhino Soldier', oracle_text='This creature enters with a shield counter on it. (If it would be dealt damage or destroyed, remove a shield counter from it instead.)\nThis creature has trample as long as it has a shield counter on it.', power='6', toughness='3', colors=['G'], color_identity=['G']),
    card('Disciplined Duelist', set_code='tst', number='T7C11', mana_cost='{G}{W}{U}', cmc=3.0, type_line='Creature — Human Citizen', oracle_text='Double strike\nThis creature enters with a shield counter on it. (If it would be dealt damage or destroyed, remove a shield counter from it instead.)', power='2', toughness='1', colors=['G', 'U', 'W'], color_identity=['G', 'U', 'W'], keywords=['Double strike']),
    card('Singer of Swift Rivers', set_code='tst', number='T7C12', mana_cost='{1}{G}{U}', cmc=3.0, type_line='Creature — Merfolk Shaman', oracle_text='Flash\nWhen this creature enters, put a shield counter on another target creature you control. (If it would be dealt damage or destroyed, remove a shield counter from it instead.)\nYou may cast Merfolk spells as though they had flash.', power='3', toughness='2', colors=['G', 'U'], color_identity=['G', 'U'], keywords=['Flash']),
    card('Protection Magic', set_code='tst', number='T7C13', mana_cost='{1}{W}', cmc=2.0, type_line='Instant', oracle_text='Put a shield counter on each of up to three target creatures. (If a creature with a shield counter would be dealt damage or destroyed, remove a shield counter from it instead.)', colors=['W'], color_identity=['W']),
    card('Brokers Veteran', set_code='tst', number='T7C14', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Human Soldier', oracle_text='When this creature dies, put a shield counter on target creature you control. (If it would be dealt damage or destroyed, remove a shield counter from it instead.)', power='2', toughness='1', colors=['U'], color_identity=['U']),
    card('Keldon Warcaller', set_code='tst', number='T7C15', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Warrior', oracle_text='Whenever this creature attacks, put a lore counter on target Saga you control.', power='2', toughness='2', colors=['R'], color_identity=['R']),
    card('Mind Unbound', set_code='tst', number='T7C16', mana_cost='{4}{U}{U}', cmc=6.0, type_line='Enchantment', oracle_text='At the beginning of your upkeep, put a lore counter on this enchantment, then draw a card for each lore counter on this enchantment.', colors=['U'], color_identity=['U']),
    card('Proud Pack-Rhino', set_code='tst', number='T7C17', mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Rhino', oracle_text='When this creature enters, choose one —\n• Put a shield counter on target permanent. (If it would be dealt damage or destroyed, remove a shield counter from it instead.)\n• Proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)', power='3', toughness='3', colors=['W'], color_identity=['W'], keywords=['Proliferate']),
    card('Boon of Safety', set_code='tst', number='T7C18', mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text='Put a shield counter on target creature. (If it would be dealt damage or destroyed, remove a shield counter from it instead.)\nScry 1.', colors=['W'], color_identity=['W'], keywords=['Scry']),
    card('Rites of Flourishing', set_code='tst', number='T7C19', mana_cost='{2}{G}', cmc=3.0, type_line='Enchantment', oracle_text="At the beginning of each player's draw step, that player draws an additional card.\nEach player may play an additional land on each of their turns.", colors=['G'], color_identity=['G']),
    card('Gift of the Viper', set_code='tst', number='T7C20', mana_cost='{G}', cmc=1.0, type_line='Instant', oracle_text='Put a +1/+1 counter, a reach counter, and a deathtouch counter on target creature. Untap it.', colors=['G'], color_identity=['G']),
    card('Pouncing Kavu', set_code='tst', number='T7C21', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Kavu', oracle_text='Kicker {2}{R} (You may pay an additional {2}{R} as you cast this spell.)\nFirst strike\nIf this creature was kicked, it enters with two +1/+1 counters on it and with haste.', power='1', toughness='1', colors=['R'], color_identity=['R'], keywords=['First strike', 'Kicker']),
    card('Faerie Squadron', set_code='tst', number='T7C22', mana_cost='{U}', cmc=1.0, type_line='Creature — Faerie', oracle_text='Kicker {3}{U} (You may pay an additional {3}{U} as you cast this spell.)\nIf this creature was kicked, it enters with two +1/+1 counters on it and with flying.', power='1', toughness='1', colors=['U'], color_identity=['U'], keywords=['Kicker']),
    card('Kavu Titan', set_code='tst', number='T7C23', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Kavu', oracle_text='Kicker {2}{G} (You may pay an additional {2}{G} as you cast this spell.)\nIf this creature was kicked, it enters with three +1/+1 counters on it and with trample.', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Kicker']),
    card('Benalish Lancer', set_code='tst', number='T7C24', mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Human Knight', oracle_text='Kicker {2}{W} (You may pay an additional {2}{W} as you cast this spell.)\nIf this creature was kicked, it enters with two +1/+1 counters on it and with first strike.', power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=['Kicker']),
    card('Duskwalker', set_code='tst', number='T7C25', mana_cost='{B}', cmc=1.0, type_line='Creature — Human Minion', oracle_text="Kicker {3}{B} (You may pay an additional {3}{B} as you cast this spell.)\nIf this creature was kicked, it enters with two +1/+1 counters on it and with fear. (It can't be blocked except by artifact creatures and/or black creatures.)", power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=['Kicker']),
    card('Pouncing Wurm', set_code='tst', number='T7C26', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Wurm', oracle_text='Kicker {2}{G} (You may pay an additional {2}{G} as you cast this spell.)\nIf this creature was kicked, it enters with three +1/+1 counters on it and with haste.', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=['Kicker']),
    card('Bloodcrazed Paladin', set_code='tst', number='T7C27', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Vampire Knight', oracle_text='Flash\nThis creature enters with a +1/+1 counter on it for each creature that died this turn.', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=['Flash']),
    card('Grizzly Ghoul', set_code='tst', number='T7C28', mana_cost='{2}{B}{G}', cmc=4.0, type_line='Creature — Zombie Bear', oracle_text='Trample\nThis creature enters with a +1/+1 counter on it for each creature that died this turn.', power='4', toughness='3', colors=['B', 'G'], color_identity=['B', 'G'], keywords=['Trample']),
    card('Ferocious Tigorilla', set_code='tst', number='T7C29', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Cat Ape', oracle_text="This creature enters with your choice of a trample counter or a menace counter on it. (A creature with menace can't be blocked except by two or more creatures.)", power='4', toughness='3', colors=['R'], color_identity=['R']),
    card('Boot Nipper', set_code='tst', number='T7C30', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Beast', oracle_text='This creature enters with your choice of a deathtouch counter or a lifelink counter on it.', power='2', toughness='1', colors=['B'], color_identity=['B']),
    card('Wingfold Pteron', set_code='tst', number='T7C31', mana_cost='{5}{U}', cmc=6.0, type_line='Creature — Dinosaur', oracle_text="This creature enters with your choice of a flying counter or a hexproof counter on it. (A creature with hexproof can't be the target of spells or abilities your opponents control.)", power='3', toughness='6', colors=['U'], color_identity=['U']),
    card('Helica Glider', set_code='tst', number='T7C32', mana_cost='{2}{W}', cmc=3.0, type_line='Creature — Nightmare Squirrel', oracle_text='This creature enters with your choice of a flying counter or a first strike counter on it.', power='2', toughness='2', colors=['W'], color_identity=['W']),
    card('Flycatcher Giraffid', set_code='tst', number='T7C33', mana_cost='{4}{G}', cmc=5.0, type_line='Creature — Antelope Lizard', oracle_text='This creature enters with your choice of a reach counter or a vigilance counter on it.', power='3', toughness='5', colors=['G'], color_identity=['G']),
    card('Serpent Specialist', set_code='tst', number='T7C34', mana_cost='{G}', cmc=1.0, type_line='Creature — Human Snake Villain', oracle_text='Deathtouch\nPower-up — {3}{G}: Put two +1/+1 counters on this creature. (Activate each power-up ability only once. Reduce the cost by its mana cost if it entered this turn.)', power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=['Power-up', 'Deathtouch']),
    card("Captain Marvel, Earth's Protector", set_code='tst', number='T7C35', mana_cost='{3}{W}{W}', cmc=5.0, type_line='Legendary Creature — Human Kree Hero', oracle_text='Flash\nFlying, lifelink\nPower-up — {5}{W}{W}: Put a +1/+1 counter and an indestructible counter on Captain Marvel. (Activate each power-up ability only once. Reduce the cost by her mana cost if she entered this turn.)', power='5', toughness='4', colors=['W'], color_identity=['W'], keywords=['Flying', 'Power-up', 'Lifelink', 'Flash']),
    card('Blood Cultist', set_code='tst', number='T7C36', mana_cost='{1}{B}{R}', cmc=3.0, type_line='Creature — Human Wizard', oracle_text='{T}: This creature deals 1 damage to target creature.\nWhenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature.', power='1', toughness='1', colors=['B', 'R'], color_identity=['B', 'R']),
    card('Vampiric Sliver', set_code='tst', number='T7C37', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Sliver', oracle_text='All Sliver creatures have "Whenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature."', power='3', toughness='3', colors=['B'], color_identity=['B']),
    card('Sengir Vampire', set_code='tst', number='T7C38', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Vampire', oracle_text="Flying (This creature can't be blocked except by creatures with flying or reach.)\nWhenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature.", power='4', toughness='4', colors=['B'], color_identity=['B'], keywords=['Flying']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- helpers ---------------------------------------------------------------------------------------------------
def saved(s):
    """The table saved and loaded again (a restart): play goes on from the loaded one."""
    return GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def add(s, c, n, kind="+1/+1"):
    act(s, c.controller, type="counter", card_ids=[c.id], kind=kind, delta=n)


def counters(s, c):
    return {k: v for k, v in s.state.cards[c.id].counters.items() if v}


def zone(s, c):
    return s.state.cards[c.id].zone


def cast(s, name, pid="p1", targets=None, counts=None, **paid):
    c = to_hand(s, name, pid)
    mana(s, pid, **paid)
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}),
        **({"target_counts": counts} if counts else {}))
    return c


def cov(name):
    c = next(x for x in EXTRA if x["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize("name", [
    "Rousing Refrain", "Inspiring Refrain", "Arc Blade", "Reality Strobe", "Generous Patron", "Mikey & Leo, Chaos & Order",
    "Ant-Man, Colony Commander", "Knight of Wundagore", "The Great Goblin", "Rhox Pummeler", "Disciplined Duelist",
    "Singer of Swift Rivers", "Protection Magic", "Brokers Veteran", "Keldon Warcaller", "Mind Unbound", "Proud Pack-Rhino",
    "Boon of Safety",
])
def test_coverage_is_full(name):
    assert cov(name) == "FULL"


def hand_size(s, pid="p1"):
    return len([c for c in s.state.cards.values() if c.zone == f"{pid}:hand"])


# -- exile with time counters (702.62b) -------------------------------------------------------------------------
def test_arc_blade_suspends_itself_and_comes_back(cards):
    s = build(cards, "Arc Blade", p2=("Grizzly Bears",))
    blade = cast(s, "Arc Blade", targets=["p2"], R=2, C=3)
    settle(s)
    assert s.state.players["p2"].life == 38
    assert zone(s, blade) == "p1:exile" and counters(s, blade) == {"time": 3}
    assert blade.id in s.state.rules.suspended
    s = saved(s)
    replay_matches(s)
    until(s, lambda s: s.state.rules.decision is not None and (s.state.rules.decision.resume or {}).get("step") == "suspend_cast",
          limit=2000)
    assert counters(s, blade) == {}  # the last time counter came off at an upkeep
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 36
    assert zone(s, blade) == "p1:exile" and counters(s, blade) == {"time": 3} and blade.id in s.state.rules.suspended  # again
    replay_matches(saved(s))


def test_inspiring_refrain_draws_then_suspends(cards):
    s = build(cards, "Inspiring Refrain", "Forest", "Forest")
    before = hand_size(s)
    refrain = cast(s, "Inspiring Refrain", U=2, C=4)
    settle(s)
    assert hand_size(s) == before + 2  # (the spell itself is cast from the hand it was put in)
    assert zone(s, refrain) == "p1:exile" and counters(s, refrain) == {"time": 3}
    replay_matches(s)


# -- counters put (122.6, 603.2) ----------------------------------------------------------------------------------
def test_generous_patron_draws_once_for_counters_of_several_kinds(cards):
    """"Whenever you put one or more counters on a creature you don't control": Gift of the Viper puts three kinds at once
    (122.6): one trigger."""
    s = build(cards, "Generous Patron", "Gift of the Viper", "Forest", "Forest", "Forest", p2=("Grizzly Bears",))
    put(s, "Generous Patron")
    theirs = put(s, "Grizzly Bears", "p2")
    s = saved(s)
    before = hand_size(s)
    cast(s, "Gift of the Viper", targets=[theirs.id], G=1)
    settle(s)
    assert counters(s, theirs) == {"+1/+1": 1, "reach": 1, "deathtouch": 1}
    assert hand_size(s) == before + 1  # one card drawn
    replay_matches(s)
    replay_matches(saved(s))


def test_generous_patron_ignores_counters_on_its_own_creatures(cards):
    s = build(cards, "Generous Patron", "Gift of the Viper", "Forest", "Forest", "Forest", "Grizzly Bears")
    put(s, "Generous Patron")
    mine = put(s, "Grizzly Bears")
    before = hand_size(s)
    cast(s, "Gift of the Viper", targets=[mine.id], G=1)
    settle(s)
    assert hand_size(s) == before
    replay_matches(s)


def test_mikey_and_leo_draws_once_each_turn(cards):
    s = build(cards, "Mikey & Leo, Chaos & Order", "Gift of the Viper", "Gift of the Viper", "Grizzly Bears", "Forest", "Forest",
              "Forest")
    put(s, "Mikey & Leo, Chaos & Order")
    mine = put(s, "Grizzly Bears")
    before = hand_size(s)
    cast(s, "Gift of the Viper", targets=[mine.id], G=1)
    settle(s)
    assert hand_size(s) == before + 1
    cast(s, "Gift of the Viper", targets=[mine.id], G=1)
    settle(s)
    assert hand_size(s) == before + 1  # once each turn
    replay_matches(saved(s))


def test_ant_man_and_knight_of_wundagore_follow_plus_one_counters(cards):
    s = build(cards, "Ant-Man, Colony Commander", "Knight of Wundagore", "Gift of the Viper", "Grizzly Bears", "Forest",
              "Forest")
    put(s, "Ant-Man, Colony Commander")
    knight = put(s, "Knight of Wundagore")
    bears = put(s, "Grizzly Bears")
    cast(s, "Gift of the Viper", targets=[bears.id], G=1)
    settle(s)
    insects = [c for c in s.state.cards.values() if c.name == "Insect" and c.zone == "p1:battlefield"]
    assert len(insects) == 1
    assert counters(s, knight) == {"+1/+1": 1}  # a +1/+1 counter on another creature
    replay_matches(s)
    replay_matches(saved(s))


def test_the_great_goblin_hits_when_a_goblin_gets_counters(cards):
    s = build(cards, "The Great Goblin", "Gift of the Viper", "Forest", "Forest")
    put(s, "The Great Goblin")
    act(s, "p1", type="create_token", player="p1", token={"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1",
                                                          "toughness": "1"})
    goblin = next(c for c in s.state.cards.values() if c.name == "Goblin" and c.owner == "p1")
    cast(s, "Gift of the Viper", targets=[goblin.id], G=1)
    settle(s)
    assert s.state.players["p2"].life == 38
    replay_matches(s)


# -- shield counters (122.1c) ---------------------------------------------------------------------------------------
def test_rhox_pummeler_enters_with_a_shield_counter_that_stops_damage_once(cards):
    s = build(cards, "Rhox Pummeler", "Lightning Bolt", "Lightning Bolt")
    rhox = cast(s, "Rhox Pummeler", G=1, C=5)
    settle(s)
    assert counters(s, rhox) == {"shield": 1}
    s = saved(s)
    cast(s, "Lightning Bolt", targets=[rhox.id], R=1)
    settle(s)
    assert zone(s, rhox) == "p1:battlefield" and not counters(s, rhox) and not s.state.cards[rhox.id].damage
    cast(s, "Lightning Bolt", targets=[rhox.id], R=1)
    settle(s)
    assert zone(s, rhox) == "p1:graveyard"
    replay_matches(s)
    replay_matches(saved(s))


def test_shield_counter_replaces_destruction_by_an_effect(cards):
    s = build(cards, "Disciplined Duelist", "Murder", "Grizzly Bears", "Wrath of God")
    duelist = cast(s, "Disciplined Duelist", G=1, W=1, U=1)
    settle(s)
    bears = put(s, "Grizzly Bears")
    assert counters(s, duelist) == {"shield": 1}
    cast(s, "Murder", targets=[duelist.id], B=2, C=1)
    settle(s)
    assert zone(s, duelist) == "p1:battlefield" and not counters(s, duelist)
    add(s, duelist, 1, "shield")
    cast(s, "Wrath of God", W=2, C=2)
    settle(s)
    assert zone(s, duelist) == "p1:battlefield" and not counters(s, duelist) and zone(s, bears) == "p1:graveyard"
    replay_matches(s)
    replay_matches(saved(s))


def test_protection_magic_shields_up_to_three_creatures(cards):
    s = build(cards, "Protection Magic", "Grizzly Bears", "Llanowar Elves", "Pyroclasm")
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    cast(s, "Protection Magic", targets=[bears.id, elves.id], counts=[2], W=1, C=1)
    settle(s)
    assert counters(s, bears) == {"shield": 1} and counters(s, elves) == {"shield": 1}
    cast(s, "Pyroclasm", R=1, C=1)  # damage to each creature: all of it prevented, one counter each
    settle(s)
    assert zone(s, bears) == "p1:battlefield" and zone(s, elves) == "p1:battlefield"
    assert not counters(s, bears) and not counters(s, elves)
    replay_matches(saved(s))


def test_brokers_veteran_passes_a_shield_counter_on_death(cards):
    s = build(cards, "Brokers Veteran", "Grizzly Bears", "Lightning Bolt")
    vet, bears = put(s, "Brokers Veteran"), put(s, "Grizzly Bears")
    cast(s, "Lightning Bolt", targets=[vet.id], R=1)
    settle(s)
    assert zone(s, vet) == "p1:graveyard" and counters(s, bears) == {"shield": 1}
    replay_matches(saved(s))


# -- lore counters on things other than Sagas (714) -------------------------------------------------------------------
def test_mind_unbound_counts_its_lore_counters(cards):
    s = build(cards, "Mind Unbound", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest")
    mind = put(s, "Mind Unbound")
    until(s, lambda s: counters(s, mind) == {"lore": 1}, limit=400)
    settle(s)
    assert counters(s, mind) == {"lore": 1}
    replay_matches(saved(s))


# -- "If ~ was kicked, it enters with … counters on it and with <keyword>" (702.33e, 614.1c, 613.1f) ----------------------
def test_pouncing_kavu_kicked_enters_with_counters_and_haste(cards):
    from app.rules.plan import Plan

    s = build(cards, "Pouncing Kavu", "Pouncing Kavu")
    kavu = to_hand(s, "Pouncing Kavu")
    mana(s, R=3, C=3)
    act(s, "p1", type="cast_spell", card_id=kavu.id, kicker=1)
    settle(s)
    assert counters(s, kavu) == {"+1/+1": 2}
    assert "haste" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[kavu.id]).keywords
    s = saved(s)
    assert "haste" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[kavu.id]).keywords
    replay_matches(s)


def test_pouncing_kavu_unkicked_is_a_plain_creature(cards):
    from app.rules.plan import Plan

    s = build(cards, "Pouncing Kavu")
    kavu = cast(s, "Pouncing Kavu", R=1, C=1)
    settle(s)
    assert zone(s, kavu) == "p1:battlefield" and not counters(s, kavu)
    assert "haste" not in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[kavu.id]).keywords
    replay_matches(saved(s))


@pytest.mark.parametrize("name", ["Pouncing Kavu", "Faerie Squadron", "Kavu Titan", "Benalish Lancer", "Duskwalker", "Pouncing Wurm"])
def test_kicked_with_keyword_coverage(name):
    assert cov(name) == "FULL"


# -- "enters with a +1/+1 counter on it for each creature that died this turn" (614.1c, history 4D) ---------------------
def test_bloodcrazed_paladin_counts_the_creatures_that_died_this_turn(cards):
    s = build(cards, "Bloodcrazed Paladin", "Lightning Bolt", "Grizzly Bears")
    bears = put(s, "Grizzly Bears")
    cast(s, "Lightning Bolt", targets=[bears.id], R=1)
    settle(s)
    assert zone(s, bears) == "p1:graveyard"
    paladin = cast(s, "Bloodcrazed Paladin", B=1, C=1)
    settle(s)
    assert zone(s, paladin) == "p1:battlefield" and counters(s, paladin) == {"+1/+1": 1}
    replay_matches(s)
    replay_matches(saved(s))


def test_bloodcrazed_paladin_alone_has_no_counters(cards):
    s = build(cards, "Bloodcrazed Paladin")
    paladin = cast(s, "Bloodcrazed Paladin", B=1, C=1)
    settle(s)
    assert zone(s, paladin) == "p1:battlefield" and not counters(s, paladin)


@pytest.mark.parametrize("name", ["Bloodcrazed Paladin", "Grizzly Ghoul"])
def test_died_this_turn_counters_coverage(name):
    assert cov(name) == "FULL"


# -- "enters with your choice of a trample counter or a menace counter on it" (614.1c, 614.12a, 122.1b) ---------------
def test_ferocious_tigorilla_enters_with_the_chosen_keyword_counter(cards):
    from app.rules.plan import Plan

    s = build(cards, "Ferocious Tigorilla")
    tiger = cast(s, "Ferocious Tigorilla", R=1, G=1, C=3)
    d = s.state.rules.decision
    for _ in range(3):
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {"trample", "menace"}
    s = saved(s)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["menace"])
    settle(s)
    assert zone(s, tiger) == "p1:battlefield" and counters(s, tiger) == {"menace": 1}
    keywords = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[tiger.id]).keywords
    assert "menace" in keywords and "trample" not in keywords
    replay_matches(s)
    replay_matches(saved(s))


@pytest.mark.parametrize("name", ["Ferocious Tigorilla", "Boot Nipper", "Wingfold Pteron", "Helica Glider", "Flycatcher Giraffid"])
def test_choice_of_counter_coverage(name):
    assert cov(name) == "FULL"


# -- power-up (702.193) --------------------------------------------------------------------------------------------
def test_power_up_costs_less_the_turn_it_enters_and_only_once(cards):
    from app.game.errors import ActionError

    s = build(cards, "Serpent Specialist")
    snake = cast(s, "Serpent Specialist", G=1)
    settle(s)
    assert zone(s, snake) == "p1:battlefield"
    mana(s, C=2)
    with pytest.raises(ActionError):  # {3}{G} less {G}: {3}
        act(s, "p1", type="activate_ability", card_id=snake.id, ability=1)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=snake.id, ability=1)
    settle(s)
    assert counters(s, snake) == {"+1/+1": 2}
    s = saved(s)
    mana(s, C=3, G=1)
    with pytest.raises(ActionError):  # activate this ability only once
        act(s, "p1", type="activate_ability", card_id=snake.id, ability=1)
    replay_matches(s)


def test_power_up_costs_full_price_on_a_later_turn(cards):
    from app.game.errors import ActionError

    s = build(cards, "Serpent Specialist")
    snake = cast(s, "Serpent Specialist", G=1)
    settle(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack")
          and s.state.rules.decision is None, limit=600)
    mana(s, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=snake.id, ability=1)
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=snake.id, ability=1)
    settle(s)
    assert counters(s, snake) == {"+1/+1": 2}
    replay_matches(saved(s))


@pytest.mark.parametrize("name", ["Serpent Specialist", "Captain Marvel, Earth's Protector"])
def test_power_up_coverage(name):
    assert cov(name) == "FULL"


# -- "Whenever a creature dealt damage by this creature this turn dies" (700.4, 120.3) ----------------------------------
def _cultist_turn(cards, *opp):
    s = build(cards, "Blood Cultist", "Lightning Bolt", p2=opp)
    cultist = put(s, "Blood Cultist")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack")
          and s.state.rules.decision is None, limit=600)
    return s, cultist


def test_blood_cultist_grows_when_a_creature_it_damaged_dies(cards):
    s, cultist = _cultist_turn(cards, "Llanowar Elves")
    elves = put(s, "Llanowar Elves", "p2")
    act(s, "p1", type="activate_ability", card_id=cultist.id, ability=0, targets=[elves.id])
    settle(s)
    assert zone(s, elves) == "p2:graveyard" and counters(s, cultist) == {"+1/+1": 1}
    s = saved(s)
    replay_matches(s)


def test_blood_cultist_ignores_other_deaths_and_survivors_damaged_earlier(cards):
    s, cultist = _cultist_turn(cards, "Grizzly Bears", "Llanowar Elves")
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    cast(s, "Lightning Bolt", targets=[elves.id], R=1)  # not dealt damage by the Cultist
    settle(s)
    assert zone(s, elves) == "p2:graveyard" and not counters(s, cultist)
    act(s, "p1", type="activate_ability", card_id=cultist.id, ability=0, targets=[bears.id])
    settle(s)
    assert zone(s, bears) == "p2:battlefield" and not counters(s, cultist)  # 1 damage: it survives
    until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1" and not s.state.zones.get("stack")
          and s.state.rules.decision is None, limit=800)
    cast(s, "Lightning Bolt", targets=[bears.id], R=1)  # damaged by the Cultist on an earlier turn: no
    settle(s)
    assert zone(s, bears) == "p2:graveyard" and not counters(s, cultist)


@pytest.mark.parametrize("name", ["Blood Cultist", "Vampiric Sliver", "Sengir Vampire"])
def test_damaged_by_this_turn_dies_coverage(name):
    assert cov(name) == "FULL"
