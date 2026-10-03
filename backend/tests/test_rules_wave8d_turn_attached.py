"""Wave 8D: "this turn" state and attached-object wordings, researched against CR 2026-09-25.

* "~ enters with N +1/+1 counters on it if [this-turn history]" (Raid, Morbid, Revolt, "an opponent lost life this turn",
  "you've cast two or more spells this turn"): a replacement that is read as the permanent enters (614.1c, 122.6, 614.12),
  with the turn's history as it is then (608.2i).
* "[Equipped / enchanted creature] … if it's red" (Ring of Valkas): the host is read as the ability resolves (608.2c).
* "gets +1/+1 for each Aura and Equipment attached to it" on an Aura or Equipment: counted for the object it modifies
  (301.5, 303.4, 611.3a).
* "loses half their life, rounded up / down" (119.3, 107.1a): half of the life total when the instruction is carried out.
* "if you didn't lose life this turn" (Luminarch Ascension).

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, sba
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle, through_combat, until
from tests.test_rules_effects import replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Cindering Cutthroat', set_code='tst', number='E01', mana_cost='{2}{B/R}', cmc=3.0, type_line='Creature — Lizard Assassin', oracle_text='This creature enters with a +1/+1 counter on it if an opponent lost life this turn.\n{1}{B/R}: This creature gains menace until end of turn. (It can\'t be blocked except by two or more creatures.)', power='3', toughness='2', colors=['B', 'R'], color_identity=['B', 'R'], keywords=[]),  # noqa: E501
    card('Effortless Master', set_code='tst', number='E02', mana_cost='{2}{U}{R}', cmc=4.0, type_line='Creature — Orc Monk', oracle_text="Vigilance\nMenace (This creature can't be blocked except by two or more creatures.)\nThis creature enters with two +1/+1 counters on it if you've cast two or more spells this turn.", power='4', toughness='3', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Vigilance', 'Menace']),  # noqa: E501
    card('Gravetiller Wurm', set_code='tst', number='E03', mana_cost='{5}{G}', cmc=6.0, type_line='Creature — Wurm', oracle_text='Trample\nMorbid — This creature enters with four +1/+1 counters on it if a creature died this turn.', power='4', toughness='4', colors=['G'], color_identity=['G'], keywords=['Trample']),  # noqa: E501
    card('Greenwheel Liberator', set_code='tst', number='E04', mana_cost='{G}', cmc=1.0, type_line='Creature — Elf Warrior', oracle_text='Revolt — This creature enters with two +1/+1 counters on it if a permanent left the battlefield under your control this turn.', power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Ring of Valkas', set_code='tst', number='E05', mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment', oracle_text="Equipped creature has haste. (It can attack and {T} no matter when it came under your control.)\nAt the beginning of your upkeep, put a +1/+1 counter on equipped creature if it's red.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)", colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Golem-Skin Gauntlets', set_code='tst', number='E06', mana_cost='{1}', cmc=1.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +1/+0 for each Equipment attached to it.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Thran Power Suit', set_code='tst', number='E07', mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment', oracle_text="Equipped creature gets +1/+1 for each Aura and Equipment attached to it and has ward {2}. (Whenever equipped creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)", colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('With Great Power . . .', set_code='tst', number='E08', mana_cost='{3}{W}', cmc=4.0, type_line='Enchantment — Aura', oracle_text='Enchant creature you control\nEnchanted creature gets +2/+2 for each Aura and Equipment attached to it.\nAll damage that would be dealt to you is dealt to enchanted creature instead.', colors=['W'], color_identity=['W'], keywords=['Enchant']),  # noqa: E501
    card('Quietus Spike', set_code='tst', number='E09', mana_cost='{3}', cmc=3.0, type_line='Artifact — Equipment', oracle_text='Equipped creature has deathtouch.\nWhenever equipped creature deals combat damage to a player, that player loses half their life, rounded up.\nEquip {3}', colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Cruel Bargain', set_code='tst', number='E10', mana_cost='{B}{B}{B}', cmc=3.0, type_line='Sorcery', oracle_text='Draw four cards. You lose half your life, rounded up.', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Luminarch Ascension', set_code='tst', number='E11', mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment', oracle_text="At the beginning of each opponent's end step, if you didn't lose life this turn, you may put a quest counter on this enchantment. (Damage causes loss of life.)\n{1}{W}: Create a 4/4 white Angel creature token with flying. Activate only if this enchantment has four or more quest counters on it.", colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Raving Dead', set_code='tst', number='E12', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Zombie', oracle_text='Deathtouch\nWhenever this creature deals combat damage to a player, that player loses half their life, rounded down.', power='3', toughness='3', colors=['B'], color_identity=['B'], keywords=['Deathtouch']),  # noqa: E501
    card('Havoc Festival', set_code='tst', number='E13', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Enchantment', oracle_text="Players can't gain life.\nAt the beginning of each player's upkeep, that player loses half their life, rounded up.", colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Shard of the Nightbringer', set_code='tst', number='E14', mana_cost='{5}{B}', cmc=6.0, type_line='Creature — C\'tan', oracle_text='Flying\nDrain Life — When this creature enters, if you cast it, target opponent loses half their life, rounded up. You gain life equal to the life lost this way.', power='4', toughness='4', colors=['B'], color_identity=['B'], keywords=['Flying']),  # noqa: E501
    card('Runeclaw Bear', set_code='tst', number='E15', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA if c["name"] != "Runeclaw Bear"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def build(cards, *names, forests=9):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (forests, "Forest")])
    seats = [PlayerSetup("Alice", cards=alice),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(1, "Ambush Viper"), (10, "Island")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def card_named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_hand(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def put(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s)


def counters(s, name, kind="+1/+1"):
    return s.state.cards[card_named(s, name).id].counters.get(kind, 0)


def pt(s, name):
    c = s.state.cards[card_named(s, name).id]
    ch = Plan(s.state, "p1", s.cards, None).ch(c)
    return sba.power(c, ch), sba.toughness(c, ch)


def life(s, pid="p1"):
    return s.state.players[pid].life


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


# -- coverage ----------------------------------------------------------------------------------------------------
def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


def test_other_conditions_and_unknown_wordings_stay_manual():
    """Only this-turn history is read in an "enters with … if" line; a board condition (its own type could count itself,
    614.12) and "if you cast it" riders are not."""
    from tests.test_rules_scripts import ch as characteristics

    for text in ("This creature enters with a +1/+1 counter on it if you control a Goblin.",
                 "This creature enters with a +1/+1 counter on it if you attacked last turn."):
        assert coverage.of_characteristics(characteristics("Test", "Creature — Test", text)).level != "FULL", text


# -- enters with counters, if … this turn ------------------------------------------------------------------------
def test_cindering_cutthroat_enters_with_a_counter_only_after_an_opponent_lost_life(cards):
    s = build(cards, "Cindering Cutthroat")
    to_hand(s, "Cindering Cutthroat")
    act(s, "p1", type="life", player="p2", delta=-3)
    mana(s, R=3)
    cast(s, "Cindering Cutthroat")
    assert counters(s, "Cindering Cutthroat") == 1
    check(s)
    s = build(cards, "Cindering Cutthroat")
    to_hand(s, "Cindering Cutthroat")
    mana(s, R=3)
    cast(s, "Cindering Cutthroat")
    assert counters(s, "Cindering Cutthroat") == 0
    check(s)


def test_your_own_life_loss_is_not_an_opponents(cards):
    s = build(cards, "Cindering Cutthroat")
    to_hand(s, "Cindering Cutthroat")
    act(s, "p1", type="life", player="p1", delta=-3)
    mana(s, R=3)
    cast(s, "Cindering Cutthroat")
    assert counters(s, "Cindering Cutthroat") == 0


def test_effortless_master_counts_the_spell_that_is_itself_cast(cards):
    """"You've cast two or more spells this turn": itself is the second spell (601.2i), so one other spell first."""
    s = build(cards, "Effortless Master", "Runeclaw Bear")
    to_hand(s, "Effortless Master")
    to_hand(s, "Runeclaw Bear")
    mana(s, G=2)
    cast(s, "Runeclaw Bear")
    mana(s, U=1, R=1, G=2)
    cast(s, "Effortless Master")
    assert counters(s, "Effortless Master") == 2
    check(s)
    s = build(cards, "Effortless Master")
    to_hand(s, "Effortless Master")
    mana(s, U=1, R=1, G=2)
    cast(s, "Effortless Master")
    assert counters(s, "Effortless Master") == 0
    check(s)


def test_morbid_wurm_needs_a_creature_to_have_died_this_turn(cards):
    s = build(cards, "Gravetiller Wurm", "Runeclaw Bear")
    to_hand(s, "Gravetiller Wurm")
    bear = put(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    mana(s, G=6)
    cast(s, "Gravetiller Wurm")
    assert counters(s, "Gravetiller Wurm") == 4
    check(s)
    s = build(cards, "Gravetiller Wurm")
    to_hand(s, "Gravetiller Wurm")
    mana(s, G=6)
    cast(s, "Gravetiller Wurm")
    assert counters(s, "Gravetiller Wurm") == 0


def test_revolt_counts_any_permanent_leaving_under_your_control(cards):
    s = build(cards, "Greenwheel Liberator", "Runeclaw Bear")
    to_hand(s, "Greenwheel Liberator")
    bear = put(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "hand"})  # (it left the battlefield)
    mana(s, G=1)
    cast(s, "Greenwheel Liberator")
    assert counters(s, "Greenwheel Liberator") == 2
    check(s)


def test_the_history_is_per_turn(cards):
    """A creature that died on an earlier turn is no morbid (608.2i: "this turn")."""
    s = build(cards, "Gravetiller Wurm", "Runeclaw Bear")
    to_hand(s, "Gravetiller Wurm")
    bear = put(s, "Runeclaw Bear")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "graveyard"})
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
    mana(s, G=6)
    cast(s, "Gravetiller Wurm")
    assert counters(s, "Gravetiller Wurm") == 0
    check(s)


# -- "put a counter on equipped creature if it's red" -------------------------------------------------------------
def test_ring_of_valkas_pumps_only_a_red_creature(cards):
    for name, grows in (("Krenko, Mob Boss", 1), ("Runeclaw Bear", 0)):
        s = build(cards, "Ring of Valkas", "Runeclaw Bear")
        put(s, "Ring of Valkas")
        creature = put(s, name)
        ring = card_named(s, "Ring of Valkas")
        act(s, "p1", type="attach", card_ids=[ring.id], to=creature.id)
        until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
        assert counters(s, name) == grows, name
        check(s)


# -- "for each Aura and Equipment attached to it" ---------------------------------------------------------------
def test_equipment_counts_are_read_for_the_creature_they_modify(cards):
    s = build(cards, "Golem-Skin Gauntlets", "Thran Power Suit", "Runeclaw Bear")
    bear = put(s, "Runeclaw Bear")
    assert pt(s, "Runeclaw Bear") == (2, 2)
    put(s, "Golem-Skin Gauntlets")
    act(s, "p1", type="attach", card_ids=[card_named(s, "Golem-Skin Gauntlets").id], to=bear.id)
    assert pt(s, "Runeclaw Bear") == (3, 2)  # (+1/+0 for the one Equipment)
    put(s, "Thran Power Suit")
    act(s, "p1", type="attach", card_ids=[card_named(s, "Thran Power Suit").id], to=bear.id)
    assert pt(s, "Runeclaw Bear") == (6, 4)  # (two attached: Gauntlets +2/+0, Power Suit +2/+2)
    assert "ward" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).keywords
    act(s, "p1", type="detach", card_ids=[card_named(s, "Thran Power Suit").id])
    assert pt(s, "Runeclaw Bear") == (3, 2)
    check(s)


def test_an_aura_counts_itself(cards):
    s = build(cards, "With Great Power . . .", "Runeclaw Bear")
    bear = put(s, "Runeclaw Bear")
    put(s, "With Great Power . . .")
    act(s, "p1", type="attach", card_ids=[card_named(s, "With Great Power . . .").id], to=bear.id)
    assert pt(s, "Runeclaw Bear") == (4, 4)  # (the Aura itself is one Aura attached to it)
    check(s)


# -- half their life -----------------------------------------------------------------------------------------------
def test_cruel_bargain_loses_half_the_life_rounded_up(cards):
    s = build(cards, "Cruel Bargain")
    to_hand(s, "Cruel Bargain")
    act(s, "p1", type="life", player="p1", delta=1)  # 41
    mana(s, B=3)
    cast(s, "Cruel Bargain")
    assert life(s) == 20  # (half of 41 rounded up is 21)
    check(s)


def test_half_of_the_life_total_rounds_down_when_it_says_so():
    from app.rules import scripts
    from tests.test_rules_scripts import ch as characteristics

    d = scripts.definitions(characteristics("Raving Dead", "Creature — Zombie", next(c for c in EXTRA if c["name"] == "Raving Dead")["oracle_text"]))
    assert [e for x in d.values() for e in x.get("effects", []) if e["do"] == "lose_life"] == [
        {"do": "lose_life", "who": "event_player", "n": 0, "half": "down"}]


def test_shard_of_the_nightbringer_gains_the_life_actually_lost(cards):
    s = build(cards, "Shard of the Nightbringer")
    to_hand(s, "Shard of the Nightbringer")
    act(s, "p1", type="life", player="p2", delta=1)  # 41
    mana(s, B=6)
    cast(s, "Shard of the Nightbringer")
    settle(s)
    assert life(s, "p2") == 20 and life(s) == 40 + 21
    check(s)


# -- "if you didn't lose life this turn" ---------------------------------------------------------------------------
def test_luminarch_ascension_grows_on_a_turn_you_lost_no_life(cards):
    """Checked at the end step of the opponent's turn 2 (an intervening "if", 603.4): no loss of life that turn."""
    s = build(cards, "Luminarch Ascension")
    put(s, "Luminarch Ascension")
    until(s, lambda s: s.state.turn.number == 3)
    assert counters(s, "Luminarch Ascension", "quest") == 1
    check(s)
    s = build(cards, "Luminarch Ascension")
    put(s, "Luminarch Ascension")
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    act(s, "p1", type="life", player="p1", delta=-1)  # (lost this very turn: the opponent's end step is the same turn)
    until(s, lambda s: s.state.turn.number == 3)
    assert counters(s, "Luminarch Ascension", "quest") == 0
    check(s)


def test_quietus_spike_halves_the_life_of_the_player_the_creature_hit(cards):
    s = build(cards, "Quietus Spike")
    bear = token(s, "p1", "Bear", "2/2", "Haste")
    put(s, "Quietus Spike")
    act(s, "p1", type="attach", card_ids=[card_named(s, "Quietus Spike").id], to=bear.id)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    through_combat(s)
    assert life(s, "p2") == 38 - 19  # (2 combat damage: 40 → 38, then half of 38 is 19)
    check(s)
