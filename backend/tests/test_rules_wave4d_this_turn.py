""""This turn" game-state conditions (wave 4D): the per-turn history (app/rules/history.py, TurnLog) and the
condition grammar over it (app/rules/conditions.py), read by intervening-if triggers (603.4), "Activate only if"
restrictions (602.5), "as long as … this turn" statics and "If …" sentences (608.2c).

608.2i: such effects look back in time — the objects as they were then (a spell as it was cast, 601.2i; a creature
as it last existed on the battlefield, 700.4 / 603.10a), whether or not they're still there. The history is saved
with the table and starts over with each turn. Every scenario uses real Commander-legal cards with their current
Oracle text, and checks that replaying the recorded history reproduces the table; several also save and reload the
table mid-turn and go on playing from the reloaded one.
"""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import conditions, coverage, history, restrictions, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import (
    attack,
    build,
    cast,
    combat_step,
    creature,
    names_on_field,
    sandbox,
    settle,
    the_end_step,
    through_combat,
    to_hand,
    until,
)
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card('Idol of Oblivion', set_code='tst', number='D400', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='{T}: Draw a card. Activate only if you created a token this turn.\n{8}, {T}, Sacrifice this artifact: Create a 10/10 colorless Eldrazi creature token.'),
    card('Bennie Bracks, Zoologist', set_code='tst', number='D401', mana_cost='{3}{W}', cmc=4.0, type_line='Legendary Creature — Elf Druid', oracle_text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nAt the beginning of each end step, if you created a token this turn, draw a card.", power='3', toughness='2', colors=['W'], color_identity=['W'], keywords=['Convoke']),
    card('Minas Tirith', set_code='tst', number='D402', mana_cost='', cmc=0.0, type_line='Legendary Land', oracle_text='Minas Tirith enters tapped unless you control a legendary creature.\n{T}: Add {W}.\n{1}{W}, {T}: Draw a card. Activate only if you attacked with two or more creatures this turn.', color_identity=['W']),
    card('Deathreap Ritual', set_code='tst', number='D403', mana_cost='{2}{B}{G}', cmc=4.0, type_line='Enchantment', oracle_text='Morbid — At the beginning of each end step, if a creature died this turn, you may draw a card.', colors=['B', 'G'], color_identity=['B', 'G'], keywords=['Morbid']),
    card('Sygg, River Cutthroat', set_code='tst', number='D404', mana_cost='{U/B}{U/B}', cmc=2.0, type_line='Legendary Creature — Merfolk Rogue', oracle_text='At the beginning of each end step, if an opponent lost 3 or more life this turn, you may draw a card. (Damage causes loss of life.)', power='1', toughness='3', colors=['B', 'U'], color_identity=['B', 'U']),
    card('Rumor Gatherer', set_code='tst', number='D405', mana_cost='{1}{W}{W}', cmc=3.0, type_line='Creature — Elf Wizard', oracle_text='Alliance — Whenever another creature you control enters, scry 1. If this is the second time this ability has resolved this turn, draw a card instead.', power='2', toughness='1', colors=['W'], color_identity=['W'], keywords=['Alliance', 'Scry']),
    card('Lyse Hext', set_code='tst', number='D406', mana_cost='{1}{W}{U}', cmc=3.0, type_line='Legendary Creature — Human Rebel Monk', oracle_text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nNoncreature spells you cast cost {1} less to cast.\nAs long as you've cast two or more noncreature spells this turn, Lyse Hext has double strike.", power='2', toughness='2', colors=['U', 'W'], color_identity=['U', 'W'], keywords=['Prowess']),
    card('Lunar Convocation', set_code='tst', number='D407', mana_cost='{W}{B}', cmc=2.0, type_line='Enchantment', oracle_text='At the beginning of your end step, if you gained life this turn, each opponent loses 1 life.\nAt the beginning of your end step, if you gained and lost life this turn, create a 1/1 black Bat creature token with flying.\n{1}{B}, Pay 2 life: Draw a card.', colors=['B', 'W'], color_identity=['B', 'W']),
    card('Hall of Oracles', set_code='tst', number='D408', mana_cost='', cmc=0.0, type_line='Land', oracle_text="{T}: Add {C}.\n{1}, {T}: Add one mana of any color.\n{T}: Put a +1/+1 counter on target creature. Activate only as a sorcery and only if you've cast an instant or sorcery spell this turn."),
    card('Canyon Crab', set_code='tst', number='D409', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Crab', oracle_text="{1}{U}: This creature gets +2/-2 until end of turn.\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, draw a card, then discard a card.", power='0', toughness='5', colors=['U'], color_identity=['U']),
    card('Blitzball', set_code='tst', number='D410', mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='{T}: Add one mana of any color.\nGOOOOAAAALLL! — {T}, Sacrifice this artifact: Draw two cards. Activate only if an opponent was dealt combat damage by a legendary creature this turn.', keywords=['GOOOOAAAALLL!']),
    card('The Raven Man', set_code='tst', number='D411', mana_cost='{1}{B}', cmc=2.0, type_line='Legendary Creature — Human Wizard', oracle_text='At the beginning of each end step, if a player discarded a card this turn, create a 1/1 black Bird creature token with flying and "This token can\'t block."\n{3}{B}, {T}: Each opponent discards a card. Activate only as a sorcery.', power='2', toughness='1', colors=['B'], color_identity=['B']),
    card('Titan Hunter', set_code='tst', number='D412', mana_cost='{4}{B}', cmc=5.0, type_line='Creature — Human Warrior', oracle_text="At the beginning of each player's end step, if no creatures died this turn, this creature deals 4 damage to that player.\n{1}{B}, Sacrifice a creature: You gain 4 life.", power='4', toughness='5', colors=['B'], color_identity=['B']),
    card('Slick Sequence', set_code='tst', number='D413', mana_cost='{U}{R}', cmc=2.0, type_line='Instant', oracle_text="Slick Sequence deals 2 damage to any target. If you've cast another spell this turn, draw a card.", colors=['R', 'U'], color_identity=['R', 'U']),
    card('Lictor', set_code='tst', number='D415', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Tyranid', oracle_text="Flash\nPheromone Trail — When this creature enters, if a creature entered the battlefield under an opponent's control this turn, create a 3/3 green Tyranid Warrior creature token with trample.", power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=['Pheromone Trail', 'Flash']),
    card('Mercadian Atlas', set_code='tst', number='D416', mana_cost='{5}', cmc=5.0, type_line='Artifact — Book', oracle_text="At the beginning of your end step, if you didn't play a land this turn, you may draw a card."),
    card('Dream Thief', set_code='tst', number='D417', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Faerie Rogue', oracle_text="Flying\nWhen this creature enters, draw a card if you've cast another blue spell this turn.", power='2', toughness='1', colors=['U'], color_identity=['U'], keywords=['Flying']),
    card('Inner-Flame Igniter', set_code='tst', number='D418', mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Elemental Warrior', oracle_text='{2}{R}: Creatures you control get +1/+0 until end of turn. If this is the third time this ability has resolved this turn, creatures you control gain first strike until end of turn.', power='2', toughness='2', colors=['R'], color_identity=['R']),
    card('Sandstalker Moloch', set_code='tst', number='D419', mana_cost='{1}{G}{G}', cmc=3.0, type_line='Creature — Lizard', oracle_text='Flash\nWhen this creature enters, if an opponent cast a blue and/or black spell this turn, look at the top four cards of your library. You may reveal a permanent card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.', power='4', toughness='2', colors=['G'], color_identity=['G'], keywords=['Flash']),
    card('Skarrgan Firebird', set_code='tst', number='D420', mana_cost='{4}{R}{R}', cmc=6.0, type_line='Creature — Phoenix', oracle_text='Bloodthirst 3 (If an opponent was dealt damage this turn, this creature enters with three +1/+1 counters on it.)\nFlying\n{R}{R}{R}: Return this card from your graveyard to your hand. Activate only if an opponent was dealt damage this turn.', power='3', toughness='3', colors=['R'], color_identity=['R'], keywords=['Flying', 'Bloodthirst']),
    card('Fairgrounds Trumpeter', set_code='tst', number='D421', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Elephant', oracle_text='At the beginning of each end step, if a +1/+1 counter was put on a permanent under your control this turn, put a +1/+1 counter on this creature.', power='2', toughness='2', colors=['G'], color_identity=['G']),
    card('White Glove Gourmand', set_code='tst', number='D422', mana_cost='{2}{W}{B}', cmc=4.0, type_line='Creature — Human Noble', oracle_text='When this creature enters, create two 1/1 white Human Soldier creature tokens.\nAt the beginning of your end step, if another Human died under your control this turn, create a Food token.', power='2', toughness='2', colors=['B', 'W'], color_identity=['B', 'W'], keywords=['Food']),
    card('River of Tears', set_code='tst', number='D424', mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {U}. If you played a land this turn, add {B} instead.', color_identity=['B', 'U']),
    card('Air Nomad Student', set_code='tst', number='D425', mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Human Monk', oracle_text="Flying\nAt the beginning of your end step, if this creature didn't attack this turn, put a +1/+1 counter on it.", power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=['Flying']),
    card('Dunerider Outlaw', set_code='tst', number='D426', mana_cost='{B}{B}', cmc=2.0, type_line='Creature — Human Rebel Rogue', oracle_text='Protection from green\nAt the beginning of each end step, if this creature dealt damage to an opponent this turn, put a +1/+1 counter on it.', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=['Protection']),
    card('Cactuar', set_code='tst', number='D427', mana_cost='{G}', cmc=1.0, type_line='Creature — Plant', oracle_text="Trample\nAt the beginning of your end step, if this creature didn't enter the battlefield this turn, return it to its owner's hand.", power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=['Trample']),
    card('Kami of Transience', set_code='tst', number='D428', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Spirit', oracle_text='Trample\nWhenever you cast an enchantment spell, put a +1/+1 counter on this creature.\nAt the beginning of each end step, if an enchantment was put into your graveyard from the battlefield this turn, you may return this card from your graveyard to your hand.', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Trample']),
    card("Smuggler's Share", set_code='tst', number='D429', mana_cost='{2}{W}', cmc=3.0, type_line='Enchantment', oracle_text='At the beginning of each end step, draw a card for each opponent who drew two or more cards this turn, then create a Treasure token for each opponent who had two or more lands enter the battlefield under their control this turn.', colors=['W'], color_identity=['W'], keywords=['Treasure']),
    card('Land Tax', set_code='tst', number='D430', mana_cost='{W}', cmc=1.0, type_line='Enchantment', oracle_text='At the beginning of your upkeep, if an opponent controls more lands than you, you may search your library for up to three basic land cards, reveal them, put them into your hand, then shuffle.', colors=['W'], color_identity=['W']),
    card('Nimble Brigand', set_code='tst', number='D431', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Human Rogue', oracle_text="This creature can't be blocked if you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nWhenever this creature deals combat damage to a player, draw a card.", power='1', toughness='3', colors=['U'], color_identity=['U']),
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


def hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def activate(s, c, ability, pid="p1", **kw):
    act(s, pid, type="activate_ability", card_id=c.id, ability=ability, **kw)
    settle(s)


def cov(name):
    c = next(x for x in EXTRA if x["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


def keywords(s, c, pid="p1"):
    plan = Plan.view(s.state, pid, s.cards)
    return plan.ch(s.state.cards[c.id]).keywords


# -- the wording -----------------------------------------------------------------------------------------------
SPELL = 'sel:{"zones":["stack"]}'


@pytest.mark.parametrize(("text", "expected"), [
    ("you created a token this turn", {"history": "tokens", "who": "you", "n": 1}),  # Idol of Oblivion
    ("you attacked with two or more creatures this turn", {"history": "attackers", "n": 2}),  # Minas Tirith
    ("no creatures attacked this turn", {"not": {"history": "attacked", "who": "any"}}),
    ("you gained and lost life this turn",  # Lunar Convocation
     {"all": [{"history": "gained", "n": 1}, {"history": "lost", "who": "you", "n": 1}]}),
    ("you gained or lost life this turn",  # Star Charter
     {"any": [{"history": "gained", "n": 1}, {"history": "lost", "who": "you", "n": 1}]}),
    ("you've cast another spell this turn", {"history": "cast", "who": "you", "sel": SPELL, "n": 1, "op": ">=", "other": True}),
    ("you've cast two or more noncreature spells this turn",  # Lyse Hext
     {"history": "cast", "who": "you", "sel": 'sel:{"not_types":["Creature"],"zones":["stack"]}', "n": 2, "op": ">="}),
    ("an opponent cast a blue and/or black spell this turn",  # Sandstalker Moloch
     {"history": "cast", "who": "opponent", "sel": 'sel:{"colors":["B","U"],"zones":["stack"]}', "n": 1, "op": ">="}),
    ("you haven't cast a spell from your hand this turn",  # Canyon Crab
     {"not": {"history": "cast", "who": "you", "sel": SPELL, "n": 1, "op": ">=", "from": "hand"}}),
    ("a player discarded a card this turn", {"history": "facts", "kind": "discard", "who": "any", "n": 1}),  # The Raven Man
    ("you've scried or surveilled this turn",
     {"any": [{"history": "facts", "kind": "scry", "who": "you", "n": 1}, {"history": "facts", "kind": "surveil", "who": "you", "n": 1}]}),
    ("an opponent was dealt damage this turn", {"history": "damage", "who": "opponent", "n": 1}),
    ("an opponent was dealt combat damage by a legendary creature this turn",
     {"history": "damage", "who": "opponent", "n": 1, "combat": True,
      "source": {"types": ["Creature"], "supertypes": ["Legendary"]}}),
    ("this is the second time this ability has resolved this turn", {"history": "resolution", "n": 2}),
    ("you didn't play a land this turn", {"not": {"history": "lands", "n": 1}}),
    ("no creatures died this turn",
     {"history": "departed", "sel": 'sel:{"types":["Creature"]}', "n": 0, "op": "==", "died": True}),
    ("another Human died under your control this turn",
     {"history": "departed", "sel": 'sel:{"subtypes":["Human"]}', "n": 1, "op": ">=", "died": True, "who": "you", "other": True}),
    ("a creature entered the battlefield under an opponent's control this turn",
     {"history": "entered", "sel": 'sel:{"types":["Creature"]}', "n": 1, "who": "opponent"}),
])
def test_wordings(text, expected):
    assert conditions.parse(text) == expected


@pytest.mark.parametrize("text", [
    "you've cast a spell with flying this turn",  # (keywords aren't recorded)
    "you put a counter on a creature this turn",  # (who put a counter isn't recorded)
    "a spell was warped this turn",  # (warp isn't modelled)
    "you attacked with two or more Merfolk this turn",  # (only how many creatures)
    "an opponent has cast another spell this turn",
    "it was the second spell you cast this turn",
])
def test_refused_wordings(text):
    assert conditions.parse(text, objects=True) is None


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_the_cards_are_automated(name):
    assert cov(name) == "FULL"


def test_intervening_if_with_you_may():
    """603.4 + 603.5: "if a creature died this turn, you may draw a card" — the gate over the whole optional ability."""
    found = scripts.parse_effects("if a creature died this turn, you may draw a card.")
    assert found is None  # (not as one instruction; as an ability's whole body:)
    d = scripts._intervening_may("if a creature died this turn, you may draw a card.", None, False)
    assert d == ([{"do": "only_if", "cond": {"history": "died", "who": "any", "n": 1}, "skip": 1},
                  {"do": "draw", "who": "you", "n": 1}], None, True)
    assert scripts._intervening_may("if it's a creature, you may draw a card.", None, False) is None


# -- tokens created (111.2) --------------------------------------------------------------------------------------
def test_idol_of_oblivion_only_after_creating_a_token(cards):
    """Activate only if you created a token this turn: not before; after (even once the token is gone — Idol's
    ruling); not on the next turn; and the history survives a save and reload."""
    s = build(cards, "Idol of Oblivion")
    idol = put(s, "Idol of Oblivion")
    with pytest.raises(ActionError, match="created a token"):
        act(s, "p1", type="activate_ability", card_id=idol.id, ability=0)
    act(s, "p2", type="create_token", player="p2", token={"name": "Theirs", "type_line": "Token Artifact — Clue", "text": ""})
    with pytest.raises(ActionError):  # (an opponent's token isn't one you created)
        act(s, "p1", type="activate_ability", card_id=idol.id, ability=0)
    clue = creature(s, "p1", "Mine")
    act(s, "p1", type="move", card_ids=[clue.id], to={"player": "p1", "zone": "graveyard"})  # (gone: still created)
    s = saved(s)
    before = hand_size(s)
    activate(s, idol, 0)
    assert hand_size(s) == before + 1
    replay_matches(s)


def test_bennie_bracks_draws_at_each_end_step_after_a_token(cards):
    s = build(cards, "Bennie Bracks, Zoologist")
    put(s, "Bennie Bracks, Zoologist")
    before = hand_size(s)
    the_end_step(s)  # (no token: the ability doesn't trigger, 603.4)
    assert hand_size(s) == before
    # turn 2 (Bob's): Alice creates a token during it — "each end step"
    creature(s, "p1", "Mine")
    before = hand_size(s)
    the_end_step(s)
    assert hand_size(s) == before + 2  # (and Alice's draw step on turn 3)
    replay_matches(s)


# -- attackers (508.1) --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("how_many", "ok"), [(1, False), (2, True)])
def test_minas_tirith_after_two_attackers(cards, how_many, ok):
    s = sandbox(cards, "Minas Tirith")
    tirith = put(s, "Minas Tirith")
    attackers = [creature(s, "p1", f"Bear{i}") for i in range(how_many)]
    combat_step(s)
    attack(s, *((a, "p2") for a in attackers))
    through_combat(s)
    mana(s, W=1, C=1)
    if not ok:
        with pytest.raises(ActionError, match="two or more creatures"):
            act(s, "p1", type="activate_ability", card_id=tirith.id, ability=2)
        return
    s = saved(s)
    before = hand_size(s)
    activate(s, tirith, 2)
    assert hand_size(s) == before + 1
    replay_matches(s)


# -- creatures that died (700.4), intervening "if" with "you may" ------------------------------------------------------
@pytest.mark.parametrize("died", [True, False])
def test_deathreap_ritual_morbid_you_may_draw(cards, died):
    s = build(cards, "Deathreap Ritual")
    put(s, "Deathreap Ritual")
    bear = creature(s, "p2", "Bear")
    if died:
        act(s, "p1", type="set_damage", card_ids=[bear.id], delta=2)
        act(s, "p1", type="pass_priority")
        settle(s)
        assert s.state.cards[bear.id].zone != "p2:battlefield" if bear.id in s.state.cards else True
    before = hand_size(s)
    seen = []
    turn = s.state.turn.number

    def done(s):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and "draw" in (d.prompt or "").lower():
            seen.append(d.prompt)
        return s.state.turn.number > turn and s.state.turn.phase == "main1"

    until(s, done)
    assert bool(seen) == died
    assert hand_size(s) == before + (1 if died else 0)
    replay_matches(s)


def test_titan_hunter_no_creatures_died(cards):
    """"if no creatures died this turn": a turn when one died, no damage; a quiet turn, 4 damage to that player."""
    s = build(cards, "Titan Hunter")
    put(s, "Titan Hunter")
    bear = creature(s, "p1", "Bear")
    act(s, "p1", type="set_damage", card_ids=[bear.id], delta=2)
    act(s, "p1", type="pass_priority")
    settle(s)
    life = s.state.players["p1"].life
    the_end_step(s)
    assert s.state.players["p1"].life == life  # (a creature died this turn)
    life2 = s.state.players["p2"].life
    the_end_step(s)  # (Bob's turn: nothing died — Bob is dealt 4)
    assert s.state.players["p2"].life == life2 - 4
    replay_matches(s)


def test_white_glove_gourmand_another_human_died_under_your_control(cards):
    s = build(cards, "White Glove Gourmand")
    gourmand = to_hand(s, "White Glove Gourmand")
    mana(s, W=2, B=2)
    cast(s, gourmand)
    soldier = next(c for c in s.state.cards.values() if c.name == "Human Soldier" and c.zone == "p1:battlefield")
    act(s, "p1", type="set_damage", card_ids=[soldier.id], delta=1)
    act(s, "p1", type="pass_priority")
    settle(s)
    s = saved(s)
    the_end_step(s)
    assert "Food" in names_on_field(s)
    replay_matches(s)


# -- life gained / lost (120.3, 119) -------------------------------------------------------------------------------
@pytest.mark.parametrize(("gain", "lose", "bat"), [(True, True, True), (True, False, False), (False, True, False)])
def test_lunar_convocation_gained_and_lost(cards, gain, lose, bat):
    s = build(cards, "Lunar Convocation")
    conv = put(s, "Lunar Convocation")
    if gain:
        act(s, "p1", type="life", player="p1", delta=2)
    if lose:
        mana(s, B=1, C=1)
        activate(s, conv, 2)  # (Pay 2 life: life lost, 119.4 — and not net change, the card's ruling)
    the_end_step(s)
    assert ("Bat" in names_on_field(s)) == bat
    replay_matches(s)


def test_sygg_an_opponent_lost_three(cards):
    s = build(cards, "Sygg, River Cutthroat")
    put(s, "Sygg, River Cutthroat")
    act(s, "p2", type="life", player="p2", delta=-2)
    before = hand_size(s)
    the_end_step(s)
    assert hand_size(s) == before
    act(s, "p2", type="life", player="p2", delta=-3)
    before = hand_size(s)
    the_end_step(s)  # (Bob's turn: "each end step"; then Alice's draw step)
    assert hand_size(s) == before + 2
    replay_matches(s)


# -- spells cast (601.2i) -------------------------------------------------------------------------------------------
def test_lyse_hext_double_strike_after_two_noncreature_spells(cards):
    """Spells cast before she entered count too (her ruling); a creature spell doesn't."""
    s = build(cards, "Lyse Hext", "Lightning Bolt", "Slick Sequence", "Grizzly Bears")
    bolt, bears = to_hand(s, "Lightning Bolt"), to_hand(s, "Grizzly Bears")
    to_hand(s, "Slick Sequence")
    mana(s, R=1)
    cast(s, bolt, targets=["p2"])
    lyse = put(s, "Lyse Hext")
    mana(s, G=2)
    cast(s, bears)
    assert "double strike" not in keywords(s, lyse)
    s = saved(s)
    mana(s, U=1, R=1)
    cast(s, named(s, "Slick Sequence"), targets=["p2"])
    assert "double strike" in keywords(s, lyse)
    until(s, lambda s: s.state.turn.number == 2)
    assert "double strike" not in keywords(s, lyse)  # (a new turn: nothing cast yet)
    replay_matches(s)


@pytest.mark.parametrize("first", [True, False])
def test_slick_sequence_another_spell(cards, first):
    """It doesn't count itself (its ruling: another spell, which may have been countered or still be on the stack)."""
    s = build(cards, "Slick Sequence", "Lightning Bolt")
    seq, bolt = to_hand(s, "Slick Sequence"), to_hand(s, "Lightning Bolt")
    if first:
        mana(s, R=1)
        cast(s, bolt, targets=["p2"])
    before = hand_size(s)
    mana(s, U=1, R=1)
    cast(s, seq, targets=["p2"])
    assert hand_size(s) == before - 1 + (1 if first else 0)
    replay_matches(s)


@pytest.mark.parametrize("first", [True, False])
def test_dream_thief_another_blue_spell(cards, first):
    """Dream Thief's own spell isn't "another" (the permanent it became remembers it, 608.3)."""
    s = build(cards, "Dream Thief", "Slick Sequence")
    thief, seq = to_hand(s, "Dream Thief"), to_hand(s, "Slick Sequence")
    if first:
        mana(s, U=1, R=1)
        cast(s, seq, targets=["p2"])
    before = hand_size(s)
    mana(s, U=1, C=2)
    cast(s, thief)
    assert hand_size(s) == before - 1 + (1 if first else 0)
    replay_matches(s)


@pytest.mark.parametrize("cast_one", [True, False])
def test_canyon_crab_from_your_hand(cards, cast_one):
    s = build(cards, "Canyon Crab", "Lightning Bolt")
    put(s, "Canyon Crab")
    bolt = to_hand(s, "Lightning Bolt")
    if cast_one:
        mana(s, R=1)
        cast(s, bolt, targets=["p2"])
    seen = []
    turn = s.state.turn.number

    def done(s):
        d = s.state.rules.decision
        if d is not None and "discard" in (d.prompt or "").lower():
            seen.append(d.prompt)
        return s.state.turn.number > turn and s.state.turn.phase == "main1"

    until(s, done)
    assert bool(seen) != cast_one
    replay_matches(s)


def test_hall_of_oracles_and_fairgrounds_trumpeter(cards):
    """Hall of Oracles: only after an instant or sorcery this turn; the +1/+1 counter it puts on a creature you control
    makes Fairgrounds Trumpeter grow at the end step."""
    s = build(cards, "Hall of Oracles", "Fairgrounds Trumpeter", "Lightning Bolt")
    hall = put(s, "Hall of Oracles")
    trumpeter = put(s, "Fairgrounds Trumpeter")
    with pytest.raises(ActionError, match="instant or sorcery"):
        act(s, "p1", type="activate_ability", card_id=hall.id, ability=2, targets=[trumpeter.id])
    mana(s, R=1)
    cast(s, to_hand(s, "Lightning Bolt"), targets=["p2"])
    activate(s, hall, 2, targets=[trumpeter.id])
    assert s.state.cards[trumpeter.id].counters.get("+1/+1") == 1
    s = saved(s)
    the_end_step(s)
    assert s.state.cards[trumpeter.id].counters.get("+1/+1") == 2
    replay_matches(s)


def test_sandstalker_moloch_an_opponent_cast_a_blue_spell(cards):
    """On Bob's turn Bob casts a blue-red spell; Alice flashes in Sandstalker Moloch: it looks at four cards."""
    s = build(cards, "Sandstalker Moloch", p2=("Slick Sequence",))
    moloch = to_hand(s, "Sandstalker Moloch")
    act(s, "p1", type="set_prefs", response="on")  # (Alice stops when Bob passes: she has a flash creature)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    mana(s, "p2", U=1, R=1)
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Slick Sequence", "p2").id, targets=["p1"])
    settle(s)
    if s.state.rules.priority == "p2":
        act(s, "p2", type="pass_priority")
    assert s.state.rules.priority == "p1" and s.state.turn.active_player == "p2"
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=moloch.id)
    prompts = []
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            prompts.append(d.prompt or d.kind)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[moloch.id].zone == "p1:battlefield"
    assert any("among them" in p for p in prompts)  # (it looked at the top four)
    replay_matches(s)


# -- discards (701.9a), damage to a player (120.3) --------------------------------------------------------------------
def test_the_raven_man_after_a_discard(cards):
    s = build(cards, "The Raven Man")
    raven = put(s, "The Raven Man")
    the_end_step(s)
    assert "Bird" not in names_on_field(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    mana(s, B=1, C=3)
    activate(s, raven, 1)  # (each opponent discards a card)
    the_end_step(s)
    assert "Bird" in names_on_field(s)
    replay_matches(s)


def test_blitzball_combat_damage_by_a_legendary_creature(cards):
    s = sandbox(cards, "Blitzball")
    ball = put(s, "Blitzball")
    plain = creature(s, "p1", "Plain")
    legend = creature(s, "p1", "Legend", type_line="Legendary Creature — Test")
    combat_step(s)
    attack(s, (plain, "p2"))
    through_combat(s)
    with pytest.raises(ActionError, match="legendary"):
        act(s, "p1", type="activate_ability", card_id=ball.id, ability=1)
    assert s.state.players["p2"].life < 40
    assert legend is not None
    replay_matches(s)


def test_blitzball_after_a_legend_connects(cards):
    s = sandbox(cards, "Blitzball")
    ball = put(s, "Blitzball")
    legend = creature(s, "p1", "Legend", type_line="Legendary Creature — Test")
    combat_step(s)
    attack(s, (legend, "p2"))
    through_combat(s)
    s = saved(s)
    before = hand_size(s)
    activate(s, ball, 1)
    assert hand_size(s) == before + 2
    replay_matches(s)


def test_skarrgan_firebird_an_opponent_was_dealt_damage(cards):
    s = build(cards, "Skarrgan Firebird", "Lightning Bolt")
    bird = named(s, "Skarrgan Firebird")
    act(s, "p1", type="move", card_ids=[bird.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, R=3)
    with pytest.raises(ActionError, match="dealt damage"):
        act(s, "p1", type="activate_ability", card_id=bird.id, ability=2)
    act(s, "p2", type="life", player="p2", delta=-3)  # (life lost isn't damage, 120.3)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=bird.id, ability=2)
    mana(s, R=1)
    cast(s, to_hand(s, "Lightning Bolt"), targets=["p2"])
    activate(s, bird, 2)
    assert s.state.cards[bird.id].zone == "p1:hand"
    replay_matches(s)


# -- entered under an opponent's control; lands played ------------------------------------------------------------------
def test_lictor_after_an_opponent_s_creature_entered(cards):
    s = build(cards, "Lictor")
    lictor = to_hand(s, "Lictor")
    creature(s, "p2", "Theirs")
    mana(s, G=1, C=3)
    cast(s, lictor)
    assert "Tyranid Warrior" in names_on_field(s)
    replay_matches(s)


def test_lictor_without(cards):
    s = build(cards, "Lictor")
    lictor = to_hand(s, "Lictor")
    creature(s, "p1", "Mine")
    mana(s, G=1, C=3)
    cast(s, lictor)
    assert "Tyranid Warrior" not in names_on_field(s)
    replay_matches(s)


@pytest.mark.parametrize("play", [True, False])
def test_mercadian_atlas_if_you_didn_t_play_a_land(cards, play):
    s = build(cards, "Mercadian Atlas")
    put(s, "Mercadian Atlas")
    if play:
        forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
        act(s, "p1", type="play_land", card_id=forest.id)
    before = hand_size(s)
    the_end_step(s)
    assert hand_size(s) == before + (0 if play else 1)
    replay_matches(s)


# -- how many times this ability resolved this turn ----------------------------------------------------------------------
def test_rumor_gatherer_second_resolution_draws_instead(cards):
    """First creature: scry 1; second: draw instead; third: scry again (only the second time — the count goes on
    across a save and reload)."""
    s = build(cards, "Rumor Gatherer", "Grizzly Bears", "Llanowar Elves", "Canyon Crab")
    put(s, "Rumor Gatherer")
    for name in ("Grizzly Bears", "Llanowar Elves", "Canyon Crab"):
        to_hand(s, name)
    prompts = []

    def enter(s, name, **pool):
        before = hand_size(s)
        mana(s, **pool)
        act(s, "p1", type="cast_spell", card_id=named(s, name).id)
        for _ in range(10):
            d = s.state.rules.decision
            if d is not None:
                prompts.append(d.prompt or "")
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])
            elif s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
            else:
                break
        return hand_size(s) - before + 1  # (the creature card left the hand)

    assert enter(s, "Grizzly Bears", G=2) == 0 and any("Scry" in p for p in prompts)
    s = saved(s)
    prompts.clear()
    assert enter(s, "Llanowar Elves", G=1) == 1 and not any("Scry" in p for p in prompts)
    assert enter(s, "Canyon Crab", U=1, C=1) == 0 and any("Scry" in p for p in prompts)
    replay_matches(s)


def test_inner_flame_igniter_third_resolution(cards):
    s = build(cards, "Inner-Flame Igniter")
    igniter = put(s, "Inner-Flame Igniter")
    for i in range(3):
        mana(s, R=1, C=2)
        activate(s, igniter, 0)
        assert ("first strike" in keywords(s, igniter)) == (i == 2)
    replay_matches(s)


# -- the history: per turn, saved, not shown ---------------------------------------------------------------------------
def test_the_history_starts_over_each_turn_and_isn_t_shown(cards):
    s = build(cards, "Lightning Bolt")
    mana(s, R=1)
    cast(s, to_hand(s, "Lightning Bolt"), targets=["p2"])
    log = s.state.rules.turn_log
    assert [c.types for c in log.casts] == [["Instant"]] and any(f.kind == "damage" and f.player == "p2" for f in log.facts)
    view = json.dumps(s.view("p2"))
    assert '"turn_log"' not in view and '"facts"' not in view
    until(s, lambda s: s.state.turn.number == 2)
    plan = Plan.view(s.state, "p1", s.cards)
    assert not history.log_for(plan).casts
    assert history.log_for(plan, last=True).casts  # (last turn's, kept for "last turn")


def test_restriction_names_its_condition():
    found = restrictions.parse("{T}: Draw a card. Activate only if you created a token this turn.")
    assert found == [{"kind": "if", "cond": {"history": "tokens", "who": "you", "n": 1}, "text": "you created a token this turn"}]


# -- a mana ability: "If you played a land this turn, add {B} instead." ---------------------------------------------------
def test_river_of_tears_after_playing_a_land(cards):
    """Its ruling: {B} only after you *played* a land (305.1), not after one was put onto the battlefield; next turn,
    {U} again until you play one."""
    from app.rules.casting import mana_abilities

    s = build(cards, "River of Tears")
    river = put(s, "River of Tears")  # (put onto the battlefield, not played)
    assert dict(mana_abilities(s.state, s.state.cards[river.id], s.cards))[0].options == (("U",),)
    act(s, "p1", type="activate_ability", card_id=river.id, ability=0)
    assert dict(s.state.players["p1"].mana) == {"U": 1}
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest.id)
    assert dict(mana_abilities(s.state, s.state.cards[river.id], s.cards))[0].options == (("B",),)
    s = saved(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert dict(mana_abilities(s.state, s.state.cards[river.id], s.cards))[0].options == (("U",),)
    replay_matches(s)


# -- what this object did this turn -------------------------------------------------------------------------------------
def test_air_nomad_student_and_dunerider_outlaw(cards):
    """The Outlaw attacks and deals damage to Bob: it gets a counter at the end step; the Student didn't attack: it gets
    one too. On Bob's turn ("each end step") the Outlaw dealt no damage: no counter."""
    s = sandbox(cards, "Air Nomad Student", "Dunerider Outlaw")
    student, outlaw = put(s, "Air Nomad Student"), put(s, "Dunerider Outlaw")
    combat_step(s)
    attack(s, (outlaw, "p2"))
    through_combat(s)
    s = saved(s)
    the_end_step(s)
    assert s.state.cards[outlaw.id].counters.get("+1/+1") == 1
    assert s.state.cards[student.id].counters.get("+1/+1") == 1
    the_end_step(s)
    assert s.state.cards[outlaw.id].counters.get("+1/+1") == 1
    replay_matches(s)


def test_air_nomad_student_that_attacked_gets_nothing(cards):
    s = sandbox(cards, "Air Nomad Student")
    student = put(s, "Air Nomad Student")
    combat_step(s)
    attack(s, (student, "p2"))
    through_combat(s)
    the_end_step(s)
    assert not s.state.cards[student.id].counters.get("+1/+1")
    replay_matches(s)


def test_cactuar_returns_unless_it_entered_this_turn(cards):
    s = build(cards, "Cactuar")
    cactuar = put(s, "Cactuar")
    the_end_step(s)
    assert s.state.cards[cactuar.id].zone == "p1:battlefield"  # (it entered this turn)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    the_end_step(s)
    assert s.state.cards[cactuar.id].zone == "p1:hand"
    replay_matches(s)


def test_kami_of_transience_after_an_enchantment_went_to_your_graveyard(cards):
    """608.2i: the enchantment needn't still be in the graveyard; 400.3: it went to its owner's graveyard."""
    s = build(cards, "Kami of Transience", "Deathreap Ritual")
    kami = named(s, "Kami of Transience")
    act(s, "p1", type="move", card_ids=[kami.id], to={"player": "p1", "zone": "graveyard"})
    ritual = put(s, "Deathreap Ritual")
    the_end_step(s)
    assert s.state.cards[kami.id].zone == "p1:graveyard"
    act(s, "p1", type="move", card_ids=[ritual.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[ritual.id], to={"player": "p1", "zone": "exile"})
    the_end_step(s)
    assert s.state.cards[kami.id].zone == "p1:hand"
    replay_matches(s)


# -- amounts of this turn's history ------------------------------------------------------------------------------------
@pytest.mark.parametrize(("draws", "lands", "cards_drawn", "treasures"), [(2, 2, 1, 1), (1, 1, 0, 0), (3, 0, 1, 0)])
def test_smugglers_share_counts_opponents(cards, draws, lands, cards_drawn, treasures):
    """One card per opponent who drew two or more cards this turn, one Treasure per opponent who had two or more lands
    enter under their control — read as it resolves (608.2h), how many each drew is public, which cards isn't."""
    s = build(cards, "Smuggler's Share")
    put(s, "Smuggler's Share")
    if draws:
        act(s, "p2", type="draw", count=draws)
    for _ in range(lands):
        island = next(c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library")
        act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    s = saved(s)
    before = hand_size(s)
    the_end_step(s)
    assert hand_size(s) == before + cards_drawn
    assert names_on_field(s).count("Treasure") == treasures
    replay_matches(s)


def test_values_of_this_turn():
    from app.rules import values

    assert values.parse_count("the amount of life you gained this turn") == {"turn_history": "gained"}
    assert values.parse_count("the number of creatures that died this turn") == \
        {"turn_history": "died", "sel": 'sel:{"types":["Creature"]}'}
    assert values.parse_count("opponent who lost life this turn") == {"turn_history": "opponents_who", "what": "lost", "n": 1}
    assert values.parse_count("cards you've drawn this turn") == {"turn_history": "drew"}


# -- an intervening "if" over an optional ability (603.4 + 603.5), any condition -------------------------------------------
@pytest.mark.parametrize("behind", [True, False])
def test_land_tax_asks_only_when_an_opponent_has_more_lands(cards, behind):
    s = build(cards, "Land Tax")
    put(s, "Land Tax")
    for _ in range(2 if behind else 0):
        island = next(c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:library")
        act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    if not behind:
        put(s, "Forest")
    prompts = []

    def done(s):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and "Land Tax" in (d.prompt or ""):
            prompts.append(d.prompt)
        return s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None

    before = hand_size(s)
    until(s, done)
    assert bool(prompts) == behind
    assert hand_size(s) == before + 1 + (1 if behind else 0)  # (the draw step; a Forest found)
    replay_matches(s)


# -- crimes (700.13) ----------------------------------------------------------------------------------------------------
def test_nimble_brigand_after_a_crime(cards):
    """Targeting your own creature is no crime; targeting an opponent is (700.13), and it lasts the turn."""
    s = build(cards, "Nimble Brigand", "Lightning Bolt", "Slick Sequence")
    brigand = put(s, "Nimble Brigand")
    mine = creature(s, "p1", "Mine", pt="5/5")
    mana(s, R=1)
    cast(s, to_hand(s, "Lightning Bolt"), targets=[mine.id])
    assert "cant_be_blocked" not in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[brigand.id]).imposed
    mana(s, U=1, R=1)
    cast(s, to_hand(s, "Slick Sequence"), targets=["p2"])
    s = saved(s)
    assert "cant_be_blocked" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[brigand.id]).imposed
    until(s, lambda s: s.state.turn.number == 2)
    assert "cant_be_blocked" not in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[brigand.id]).imposed
    replay_matches(s)
