"""Wave 8B: trigger bodies and events from the trigger catch-all, researched against CR 2026-09-25.

* Superlatives (app/rules/extremes.py; 603.4, 608.2c): "if you control the creature with the greatest power or tied for the
  greatest power" (Thickest in the Thicket, Triumph of Ferocity, Abzan Beastmaster, Triumph of Cruelty), "… the artifact with
  the greatest mana value or tied …" (Padeem), "… a creature with the greatest power among creatures on the battlefield"
  (High Score, Éomer): some object of that kind you control has a value no object of that kind on the battlefield beats.
* Looks (701.22b, 701.25c; history.note_look, app/rules/events.py): "Whenever you scry or surveil" (Matoya, Saheeli),
  "Whenever you surveil" (Disinformation Campaign), "Whenever you surveil for the first time each turn" (Whispering Snitch).
* "Reveal the top card of your library and put that card into your hand. You lose / gain life equal to its mana value."
  (Dark Confidant, Dark Tutelage, Augury Adept): "that card" is the card revealed.
* "Each opponent loses life equal to the life they lost this turn." (Wound Reflection, Archfiend of Despair) and
  "Investigate for each opponent who lost life this turn." (Teysa): this turn's log (119.3), read per opponent.

Every scenario checks the replay; the longer ones also reload the game from its saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle, until
from tests.test_rules_effects import replay_matches

# Real Oracle wording (the local card database, current).
EXTRA = [
    card('Matoya, Archon Elder', set_code='tst', number='E01', mana_cost='{2}{U}', cmc=3.0, type_line='Legendary Creature — Human Warlock', oracle_text='Whenever you scry or surveil, draw a card. (Draw after you scry or surveil.)', power='1', toughness='4', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Whispering Snitch', set_code='tst', number='E02', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Vampire Rogue', oracle_text='Whenever you surveil for the first time each turn, this creature deals 1 damage to each opponent and you gain 1 life.', power='1', toughness='3', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Saheeli, Consul of Oversight', set_code='tst', number='E03', mana_cost='{3}{W}{W}', cmc=5.0, type_line='Legendary Creature — Human Advisor', oracle_text='Flying\nWhenever you scry or surveil, create a 1/1 colorless Thopter artifact creature token with flying. This ability triggers only once each turn.', power='4', toughness='4', colors=['W'], color_identity=['W'], keywords=['Flying']),  # noqa: E501
    card('Thickest in the Thicket', set_code='tst', number='E04', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Enchantment', oracle_text="When this enchantment enters, put X +1/+1 counters on target creature, where X is that creature's power.\nAt the beginning of your end step, draw two cards if you control the creature with the greatest power or tied for the greatest power.", colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('High Score', set_code='tst', number='E05', mana_cost='{2}{G}', cmc=3.0, type_line='Enchantment', oracle_text='If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.\nAt the beginning of your end step, draw a card if you control a creature with the greatest power among creatures on the battlefield.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Padeem, Consul of Innovation', set_code='tst', number='E06', mana_cost='{3}{U}', cmc=4.0, type_line='Legendary Creature — Vedalken Artificer', oracle_text="Artifacts you control have hexproof. (They can't be the targets of spells or abilities your opponents control.)\nAt the beginning of your upkeep, if you control the artifact with the greatest mana value or tied for the greatest mana value, draw a card.", power='1', toughness='4', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
    card('Dark Confidant', set_code='tst', number='E07', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Human Wizard', oracle_text='At the beginning of your upkeep, reveal the top card of your library and put that card into your hand. You lose life equal to its mana value.', power='2', toughness='1', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Augury Adept', set_code='tst', number='E08', mana_cost='{1}{W/U}{W/U}', cmc=3.0, type_line='Creature — Kithkin Wizard', oracle_text='Whenever this creature deals combat damage to a player, reveal the top card of your library and put that card into your hand. You gain life equal to its mana value.', power='2', toughness='2', colors=['U', 'W'], color_identity=['U', 'W'], keywords=[]),  # noqa: E501
    card('Wound Reflection', set_code='tst', number='E09', mana_cost='{5}{B}', cmc=6.0, type_line='Enchantment', oracle_text='At the beginning of each end step, each opponent loses life equal to the life they lost this turn. (Damage causes loss of life.)', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Teysa, Opulent Oligarch', set_code='tst', number='E10', mana_cost='{1}{W}{B}', cmc=3.0, type_line='Legendary Creature — Human Advisor', oracle_text='Deathtouch\nAt the beginning of your end step, investigate for each opponent who lost life this turn.\nWhenever a Clue you control is put into a graveyard from the battlefield, create a 1/1 white and black Spirit creature token with flying. This ability triggers only once each turn.', power='2', toughness='3', colors=['B', 'W'], color_identity=['B', 'W'], keywords=['Investigate', 'Deathtouch']),  # noqa: E501
    card('Sophina, Spearsage Deserter', set_code='tst', number='E11', mana_cost='{2}{R}{W}', cmc=4.0, type_line='Legendary Creature — Human Soldier', oracle_text='Menace\nWhenever Sophina, Spearsage Deserter attacks, investigate once for each nontoken attacking creature. (To investigate, create a Clue token. It\'s an artifact with "{2}, Sacrifice this artifact: Draw a card.")\nPartner—Friends forever (You can have two commanders if both have this ability.)', power='4', toughness='4', colors=['R', 'W'], color_identity=['R', 'W'], keywords=['Investigate', 'Partner', 'Menace']),  # noqa: E501
    card('Consider', set_code='tst', number='E13', mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\nDraw a card.', colors=['U'], color_identity=['U'], keywords=['Surveil']),  # noqa: E501
    card('Wurmcoil Engine', set_code='tst', number='E14', mana_cost='{6}', cmc=6.0, type_line='Artifact Creature — Phyrexian Wurm', oracle_text='Deathtouch, lifelink\nWhen this creature dies, create a 3/3 colorless Phyrexian Wurm artifact creature token with deathtouch and a 3/3 colorless Phyrexian Wurm artifact creature token with lifelink.', power='6', toughness='6', colors=[], color_identity=[], keywords=['Lifelink', 'Deathtouch']),  # noqa: E501
    card('Hill Giant', set_code='tst', number='E15', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Giant', oracle_text='', power='3', toughness='3', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Éomer of the Riddermark', set_code='tst', number='E16', mana_cost='{4}{R}', cmc=5.0, type_line='Legendary Creature — Human Knight', oracle_text='Haste\nWhenever Éomer attacks, if you control a creature with the greatest power among creatures on the battlefield, create a 1/1 white Human Soldier creature token.', power='5', toughness='4', colors=['R'], color_identity=['R'], keywords=['Haste']),  # noqa: E501
    card('Archfiend of Despair', set_code='tst', number='E17', mana_cost='{6}{B}{B}', cmc=8.0, type_line='Creature — Demon', oracle_text="Flying\nYour opponents can't gain life.\nAt the beginning of each end step, each opponent loses life equal to the life that player lost this turn. (Damage causes loss of life.)", power='6', toughness='6', colors=['B'], color_identity=['B'], keywords=['Flying']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA if c["name"] not in ("Wurmcoil Engine", "Hill Giant", "Consider")]
FULL += ["Consider"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def reloaded(s):
    """The table as a fresh session rebuilt from the saved history (a save and a load)."""
    return GameSession(s.history.rebuild(), cards=s.cards)


def build(cards, mine, theirs=("Hill Giant", "Wurmcoil Engine")):
    alice = deck(cards, "Krenko, Mob Boss", [*(n if isinstance(n, tuple) else (1, n) for n in mine), (15, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (12, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False))
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def to_hand(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:library")
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def cast(s, name, pid="p1"):
    act(s, pid, type="cast_spell", card_id=named(s, name, pid).id)
    settle(s)


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def life(s, pid):
    return s.state.players[pid].life


def on_battlefield(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone == f"{pid}:battlefield"]


def end_step(s):
    """Alice's end step (or the turn's), its triggers resolved."""
    stops(s)
    until(s, lambda s: s.state.turn.phase == "end")
    settle(s)


def stops(s):
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=["upkeep", "end"], others=["upkeep", "end"])


def defined(text, type_line="Creature — Test"):
    from tests.test_rules_scripts import ch

    return scripts.definitions(ch("X", type_line, text))


# -- coverage ----------------------------------------------------------------------------------------------------
def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text", [
    "At the beginning of your upkeep, draw a card if you control the creature with the greatest power.",  # (a tie leaves no one)
    "At the beginning of your upkeep, draw a card if you control the creature with the greatest power or tied for the greatest toughness.",
    "At the beginning of your upkeep, draw a card if you control a creature with the greatest power among artifacts on the battlefield.",
    "Whenever you scry or surveil for the first time each turn, draw a card.",  # (the first of which?)
    "Whenever an opponent scries, draw a card.",
    "At the beginning of your upkeep, investigate once for each opponent who has more cards in hand than you.",
])
def test_wordings_that_stay_manual(text):
    assert not defined(text), text


def test_the_reveal_lines_read_the_revealed_card():
    d = defined("At the beginning of your upkeep, reveal the top card of your library and put that card into your hand. "
                "You lose life equal to its mana value.")[0]
    assert [e["do"] for e in d["effects"]] == ["look_top", "pick_looked", "lose_life"]
    assert d["effects"][2]["n"] == {"mana_value": "ref:e1"} and d["effects"][1]["as"] == "e1"


# -- superlatives ------------------------------------------------------------------------------------------------
def test_thickest_in_the_thicket_draws_only_with_the_greatest_power(cards):
    """608.2c: the creature with the greatest power among all creatures; a tie counts ("or tied")."""
    s = build(cards, ("Thickest in the Thicket", "Hill Giant"))
    put(s, "Thickest in the Thicket")
    put(s, "Hill Giant")
    put(s, "Wurmcoil Engine", "p2")  # 6 power against 3
    before = hand(s)
    end_step(s)
    assert hand(s) == before
    replay_matches(s)

    s = build(cards, ("Thickest in the Thicket", "Hill Giant"))
    put(s, "Thickest in the Thicket")
    put(s, "Hill Giant")
    put(s, "Hill Giant", "p2")  # tied at 3
    before = hand(s)
    end_step(s)
    assert hand(s) == before + 2
    replay_matches(s)
    assert hand(reloaded(s)) == hand(s)


def test_thickest_in_the_thicket_needs_a_creature_of_yours(cards):
    s = build(cards, ("Thickest in the Thicket",))
    put(s, "Thickest in the Thicket")
    put(s, "Hill Giant", "p2")  # you control no creature: nobody you control has the greatest
    before = hand(s)
    end_step(s)
    assert hand(s) == before
    s = build(cards, ("Thickest in the Thicket", "Wurmcoil Engine"))
    put(s, "Thickest in the Thicket")
    put(s, "Wurmcoil Engine")
    put(s, "Hill Giant", "p2")
    before = hand(s)
    end_step(s)
    assert hand(s) == before + 2


def test_high_score_counts_a_tie_among_all_creatures(cards):
    s = build(cards, ("High Score", "Hill Giant"))
    put(s, "High Score")
    put(s, "Hill Giant")
    put(s, "Hill Giant", "p2")
    before = hand(s)
    end_step(s)
    assert hand(s) == before + 1
    s = build(cards, ("High Score", "Hill Giant"))
    put(s, "High Score")
    put(s, "Hill Giant")
    put(s, "Wurmcoil Engine", "p2")
    before = hand(s)
    end_step(s)
    assert hand(s) == before
    replay_matches(s)


def test_padeem_compares_the_mana_value_of_artifacts(cards):
    """The artifact with the greatest mana value (202.3), any controller's: Sol Ring (1) loses to an opponent's Wurmcoil
    Engine (6); a tie draws; Padeem herself is no artifact."""
    def upkeep_draws(mine, theirs):
        s = build(cards, ("Padeem, Consul of Innovation", "Sol Ring", "Wurmcoil Engine"), theirs=("Wurmcoil Engine",))
        put(s, "Padeem, Consul of Innovation")
        for name in mine:
            put(s, name)
        for name in theirs:
            put(s, name, "p2")
        stops(s)
        until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "upkeep")
        settle(s)
        return s, hand(s)

    assert upkeep_draws(["Sol Ring"], ["Wurmcoil Engine"])[1] == 0
    assert upkeep_draws([], ["Wurmcoil Engine"])[1] == 0  # (no artifact of yours at all)
    assert upkeep_draws(["Sol Ring"], [])[1] == 1
    s, n = upkeep_draws(["Wurmcoil Engine"], ["Wurmcoil Engine"])
    assert n == 1
    replay_matches(s)


# -- scry and surveil --------------------------------------------------------------------------------------------
def test_matoya_draws_when_you_scry_or_surveil(cards):
    s = build(cards, ("Matoya, Archon Elder", "Opt", "Consider"))
    put(s, "Matoya, Archon Elder")
    to_hand(s, "Opt")
    to_hand(s, "Consider")
    before = hand(s)
    mana(s, U=2)
    cast(s, "Opt")
    assert hand(s) == before - 1 + 1 + 1  # (Opt left the hand, drew one, and Matoya drew one)
    cast(s, "Consider")
    assert hand(s) == before - 2 + 2 + 2
    replay_matches(s)
    assert hand(reloaded(s)) == hand(s)


def test_the_look_events_are_the_controllers_own():
    from app.rules import events

    assert events.parse_condition("you scry") == {"event": "scry", "subject": "player", "player": "you"}
    assert events.parse_condition("an opponent scries") is None and events.parse_condition("you scry for the first time each turn")["nth"] == 1


def test_whispering_snitch_triggers_for_the_first_surveil_each_turn_only(cards):
    s = build(cards, ("Whispering Snitch", (2, "Consider"), "Opt"))
    put(s, "Whispering Snitch")
    to_hand(s, "Consider")
    to_hand(s, "Consider")
    to_hand(s, "Opt")
    mana(s, U=3)
    cast(s, "Opt")  # (a scry is not a surveil)
    assert life(s, "p2") == 40 and life(s, "p1") == 40
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Consider" and c.zone == "p1:hand"))
    settle(s)
    assert life(s, "p2") == 39 and life(s, "p1") == 41
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Consider" and c.zone == "p1:hand"))
    settle(s)
    assert life(s, "p2") == 39 and life(s, "p1") == 41  # (the second surveil of the turn: no trigger)
    replay_matches(s)
    s = reloaded(s)
    assert life(s, "p2") == 39


def test_saheeli_makes_one_thopter_each_turn(cards):
    s = build(cards, ("Saheeli, Consul of Oversight", "Opt"))
    put(s, "Saheeli, Consul of Oversight")
    to_hand(s, "Opt")
    mana(s, U=2)
    cast(s, "Opt")
    assert len(on_battlefield(s, "Thopter")) == 1
    replay_matches(s)
    s = reloaded(s)
    assert len(on_battlefield(s, "Thopter")) == 1


# -- reveal the top card -----------------------------------------------------------------------------------------
def test_dark_confidant_loses_life_equal_to_the_revealed_mana_value(cards):
    s = build(cards, ("Dark Confidant", "Wurmcoil Engine"))
    put(s, "Dark Confidant")
    w = named(s, "Wurmcoil Engine")
    act(s, "p1", type="move", card_ids=[w.id], to={"zone": "library"}, position="top")
    assert s.state.zones["p1:library"][0] == w.id
    before = hand(s)
    stops(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "upkeep")
    settle(s)
    assert s.state.cards[w.id].zone == "p1:hand" and hand(s) == before + 1
    assert life(s, "p1") == 34 and life(s, "p2") == 40
    replay_matches(s)
    s = reloaded(s)
    assert life(s, "p1") == 34


def test_dark_confidant_with_an_empty_library_loses_nothing(cards):
    s = build(cards, ("Dark Confidant",))
    put(s, "Dark Confidant")
    act(s, "p1", type="move", card_ids=list(s.state.zones["p1:library"]), to={"zone": "graveyard"})
    stops(s)
    before = hand(s)
    stops(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "upkeep")
    settle(s)
    assert hand(s) == before and life(s, "p1") == 40
    assert s.state.rules.decision is None
    replay_matches(s)


def test_augury_adept_gains_life_equal_to_the_revealed_mana_value(cards):
    d = defined("Whenever ~ deals combat damage to a player, reveal the top card of your library and put that card into your "
                "hand. You gain life equal to its mana value.")[0]
    assert d["effects"][2]["do"] == "gain_life" and d["effects"][2]["n"] == {"mana_value": "ref:e1"}


# -- life lost this turn -----------------------------------------------------------------------------------------
def test_wound_reflection_repeats_the_life_each_opponent_lost(cards):
    s = build(cards, ("Wound Reflection",))
    put(s, "Wound Reflection")
    act(s, "p1", type="life", player="p2", delta=-3)
    assert life(s, "p2") == 37
    end_step(s)
    assert life(s, "p2") == 34 and life(s, "p1") == 40
    replay_matches(s)
    assert life(reloaded(s), "p2") == 34


def test_wound_reflection_does_nothing_when_no_life_was_lost(cards):
    s = build(cards, ("Wound Reflection",))
    put(s, "Wound Reflection")
    end_step(s)
    assert life(s, "p2") == 40
    # the next turn is Bob's: his end step triggers it too ("each end step"), for what Alice lost on his turn
    act(s, "p1", type="life", player="p1", delta=-2)  # (Alice loses life on Bob's turn: she isn't an opponent of herself)
    stops(s)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "end")
    settle(s)
    assert life(s, "p1") == 38 and life(s, "p2") == 40


def test_teysa_investigates_for_each_opponent_who_lost_life(cards):
    s = build(cards, ("Teysa, Opulent Oligarch",))
    put(s, "Teysa, Opulent Oligarch")
    act(s, "p1", type="life", player="p2", delta=-1)
    end_step(s)
    assert len(on_battlefield(s, "Clue")) == 1
    replay_matches(s)
    s = build(cards, ("Teysa, Opulent Oligarch",))
    put(s, "Teysa, Opulent Oligarch")
    end_step(s)
    assert on_battlefield(s, "Clue") == []


def test_sophina_investigates_once_for_each_nontoken_attacking_creature():
    d = defined("Whenever ~ attacks, investigate once for each nontoken attacking creature.")[0]
    assert d["effects"][0]["do"] == "create_token" and d["effects"][0]["token"]["name"] == "Clue"
    assert d["effects"][0]["n"] == {"count": 'sel:{"attacking":true,"token":false,"types":["Creature"]}'}
