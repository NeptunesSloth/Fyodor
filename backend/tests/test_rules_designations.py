"""Counters on players and designations (wave 3E): energy (107.14), experience, poison (122.1f,
704.5c), rad counters (728), proliferate's players (701.34), the monarch (725), the initiative and
Undercity (726, 309, 701.49), venture into the dungeon, the Ring tempts you (701.54), day and night
(731). Real Commander cards, current Oracle text; every scenario also replays its history and
survives a save / load."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import conditions, coverage, scripts, values
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, replay_matches, rules, run_until

REAL = [
    card('Prologue to Phyresis', set_code='tst', number='E1', mana_cost='{1}{U}', cmc=2.0, type_line='Instant', colors=['U'],
         color_identity=['U'], oracle_text='Each opponent gets a poison counter.\nDraw a card.'),
    card('Guide of Souls', set_code='tst', number='E2', mana_cost='{W}', cmc=1.0, type_line='Creature — Human Cleric', colors=['W'],
         color_identity=['W'], power='1', toughness='2',
         oracle_text='Whenever another creature you control enters, you gain 1 life and get {E} (an energy counter).\nWhenever you '
         'attack, you may pay {E}{E}{E}. When you do, put two +1/+1 counters and a flying counter on target attacking creature. It '
         'becomes an Angel in addition to its other types.'),
    card('Aether Hub', set_code='tst', number='E3', mana_cost='', cmc=0.0, type_line='Land', colors=[], color_identity=[],
         oracle_text='When this land enters, you get {E} (an energy counter).\n{T}: Add {C}.\n{T}, Pay {E}: Add one mana of any color.'),
    card('Architect of the Untamed', set_code='tst', number='E4', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Elf Artificer Druid',
         colors=['G'], color_identity=['G'], power='2', toughness='3', keywords=['Landfall'],
         oracle_text='Landfall — Whenever a land you control enters, you get {E} (an energy counter).\nPay eight {E}: Create a 6/6 '
         'colorless Beast artifact creature token.'),
    card('Sphinx of the Revelation', set_code='tst', number='E5', mana_cost='{3}{W}{U}', cmc=5.0, type_line='Artifact Creature — Sphinx',
         colors=['U', 'W'], color_identity=['U', 'W'], power='4', toughness='5', keywords=['Flying', 'Lifelink'],
         oracle_text='Flying, lifelink\nWhenever you gain life, you get that many {E} (energy counters).\n{W}{U}{U}, {T}, Pay X {E}: '
         'Draw X cards.'),
    card('Feral Ghoul', set_code='tst', number='E6', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Zombie Mutant', colors=['B'],
         color_identity=['B'], power='2', toughness='2', keywords=['Menace'],
         oracle_text='Menace\nWhenever another creature you control dies, put a +1/+1 counter on this creature.\nWhen this creature '
         'dies, each opponent gets a number of rad counters equal to its power.'),
    card('Vishgraz, the Doomhive', set_code='tst', number='E7', mana_cost='{2}{W}{B}{G}', cmc=5.0,
         type_line='Legendary Creature — Phyrexian Insect', colors=['B', 'G', 'W'], color_identity=['B', 'G', 'W'], power='3',
         toughness='3', keywords=['Toxic', 'Menace'],
         oracle_text='Menace, toxic 1 (Players dealt combat damage by this creature also get a poison counter.)\nWhen Vishgraz '
         'enters, create three 1/1 colorless Phyrexian Mite artifact creature tokens with toxic 1 and "This token can\'t block."\n'
         'Vishgraz gets +1/+1 for each poison counter your opponents have.'),
    card('Territorial Gorger', set_code='tst', number='E8', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Gremlin', colors=['R'],
         color_identity=['R'], power='2', toughness='2', keywords=['Trample'],
         oracle_text='Trample\nWhenever you get one or more {E} (energy counters), this creature gets +2/+2 until end of turn.'),
    card('Infectious Inquiry', set_code='tst', number='E9', mana_cost='{2}{B}', cmc=3.0, type_line='Sorcery', colors=['B'],
         color_identity=['B'], oracle_text='You draw two cards and you lose 2 life. Each opponent gets a poison counter.'),
]


@pytest.fixture()
def cards(settings, card_db):
    build_database(fixture_cards() + REAL, settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(card_db, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards, names=(), bob=((10, "Island"),)):
    a = deck(cards, "Krenko, Mob Boss", [(1, n) for n in names] + [(10, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", list(bob))
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def find(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, where, pid="p1"):
    c = find(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": where})
    return s.state.cards[c.id]


def pick(s, ids):
    d = rules(s).decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def settle(s):
    """Order one's own triggers as offered and pass until the stack is empty (or another choice is asked)."""
    for _ in range(40):
        d = rules(s).decision
        if d is not None and d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        elif d is None and s.state.zones.get("stack"):
            act(s, rules(s).priority, type="pass_priority")
        else:
            return


def res(s, pid="p1", key="energy"):
    return s.state.players[pid].resources.get(key, 0)


def give(s, pid, key, n):
    act(s, pid, type="resource", player=pid, key=key, delta=n)


def roundtrip(s):
    replay_matches(s)  # (reload: the history rebuilds the same table)
    assert GameState.model_validate(s.state.model_dump(mode="json")).model_dump(mode="json") == s.state.model_dump(mode="json")


def pt(s, c, cards):
    return Plan(s.state, "p1", cards, None).ch(s.state.cards[c.id]).pt


# -- the wording ------------------------------------------------------------------------------------
def test_player_counter_wordings_are_read_and_the_rest_refused():
    def fx(text):
        got = scripts.parse_effects(text)
        return got[0] if got else None

    assert fx("Each opponent gets a poison counter.") == [{"do": "player_counter", "who": "each_opponent", "counter": "poison", "n": 1}]
    assert fx("You get an experience counter.") == [{"do": "player_counter", "who": "you", "counter": "experience", "n": 1}]
    assert fx("You get six {E}.") == [{"do": "player_counter", "who": "you", "counter": "energy", "n": 6}]
    assert fx("You gain 1 life and get {E}.")[1] == {"do": "player_counter", "who": "you", "counter": "energy", "n": 1}
    assert fx("Target player gets four rad counters.") == [{"do": "player_counter", "who": "target", "counter": "rad", "n": 4}]
    assert fx("You get that many {E}.")[0]["n"] == {"event_amount": 1}
    edict = fx("Each opponent sacrifices a creature or planeswalker of their choice and gets a poison counter.")
    assert edict is not None and edict[1]["counter"] == "poison" and edict[1]["who"] == "each_opponent"
    assert fx("You get a ticket counter.") is None  # (a kind with no rules here: never a guess)
    assert fx("You get half X rad counters, rounded up.") is None
    assert values.parse_count("the number of poison counters your opponents have") == {"player_counters": "poison", "of": "opponents"}
    assert values.parse_count("the amount of {E} you have") == {"player_counters": "energy"}
    corrupted = conditions.parse("an opponent has three or more poison counters")
    assert corrupted == {"value": {"player_counters": "poison"}, "op": ">=", "n": 3, "per_opponent": True}
    assert conditions.parse("you have no rad counters") == {"value": {"player_counters": "rad"}, "op": "==", "n": 0}


def test_coverage_of_the_counter_cards():
    for c in REAL:
        if c["name"] in ("Guide of Souls",):  # ("When you do": a reflexive trigger, 603.12: not modelled)
            assert coverage.of_card_data(c).level != "FULL"
            continue
        assert coverage.of_card_data(c).level == "FULL", c["name"]


# -- energy (107.14) --------------------------------------------------------------------------------
def test_energy_is_gained_and_paid_by_an_activated_ability(cards):
    s = build(cards, ["Architect of the Untamed", "Aether Hub"])
    put(s, "Architect of the Untamed", "battlefield")
    give(s, "p1", "energy", 6)
    architect = find(s, "Architect of the Untamed")
    with pytest.raises(ActionError, match="8 energy"):
        act(s, "p1", type="activate_ability", card_id=architect.id, ability=1)
    act(s, "p1", type="play_land", card_id=put(s, "Aether Hub", "hand").id)
    settle(s)
    assert res(s) == 8  # landfall {E} and the Hub's own {E}
    act(s, "p1", type="activate_ability", card_id=architect.id, ability=1)
    assert res(s) == 0  # paid as the ability was activated (602.2b)
    settle(s)
    beasts = [c for c in s.state.cards.values() if c.name == "Beast" and c.zone == "p1:battlefield"]
    assert len(beasts) == 1 and beasts[0].token.power == "6"
    roundtrip(s)


def test_energy_mana_ability_is_activated_by_hand_only(cards):
    s = build(cards, ["Aether Hub", "Grizzly Bears"])
    hub = put(s, "Aether Hub", "battlefield")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=hub.id, ability=2, mana_choice="G")  # no energy: can't pay
    give(s, "p1", "energy", 1)
    act(s, "p1", type="activate_ability", card_id=hub.id, ability=2, mana_choice="G")
    assert s.state.players["p1"].mana.get("G") == 1 and res(s) == 0 and s.state.cards[hub.id].tapped
    roundtrip(s)


def test_energy_mana_ability_is_never_spent_by_the_auto_payer(cards):
    s = build(cards, ["Aether Hub", "Grizzly Bears"])
    put(s, "Aether Hub", "battlefield")
    give(s, "p1", "energy", 3)
    bears = put(s, "Grizzly Bears", "hand")
    mana(s, C=1)
    with pytest.raises(ActionError):  # {1}{G}: the Hub's colorless is fine, its {E} ability is not used for {G}
        act(s, "p1", type="cast_spell", card_id=bears.id)
    assert res(s) == 3


def test_pay_x_energy_draws_x(cards):
    s = build(cards, ["Sphinx of the Revelation"])
    sphinx = put(s, "Sphinx of the Revelation", "battlefield")
    rules(s).controlled_since[sphinx.id].turn = 0  # (it has been there since before the turn)
    give(s, "p1", "energy", 5)
    mana(s, W=1, U=2)
    hand = len(s.state.zones["p1:hand"])
    with pytest.raises(ActionError, match="X"):
        act(s, "p1", type="activate_ability", card_id=sphinx.id, ability=2)
    with pytest.raises(ActionError, match="6 energy"):
        act(s, "p1", type="activate_ability", card_id=sphinx.id, ability=2, x_value=6)
    act(s, "p1", type="activate_ability", card_id=sphinx.id, ability=2, x_value=3)
    assert res(s) == 2
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + 3
    roundtrip(s)


def test_that_many_energy_on_life_gain_and_one_or_more_energy_trigger(cards):
    s = build(cards, ["Sphinx of the Revelation", "Territorial Gorger", "Guide of Souls", "Grizzly Bears"])
    put(s, "Sphinx of the Revelation", "battlefield")
    gorger = put(s, "Territorial Gorger", "battlefield")
    put(s, "Guide of Souls", "battlefield")
    bears = put(s, "Grizzly Bears", "hand")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    # Guide: gain 1 life and get {E}; the Sphinx: gained 1 → that many {E}; each energy event pumps the Gorger
    assert s.state.players["p1"].life == 41 and res(s) == 2
    settle(s)
    assert pt(s, gorger, cards) == (6, 6)
    roundtrip(s)


# -- poison (122.1f, 704.5c) -------------------------------------------------------------------------
def test_each_opponent_gets_a_poison_counter_and_ten_lose(cards):
    s = build(cards, ["Prologue to Phyresis", "Infectious Inquiry", "Vishgraz, the Doomhive"])
    vish = put(s, "Vishgraz, the Doomhive", "battlefield")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=put(s, "Prologue to Phyresis", "hand").id)
    settle(s)
    assert res(s, "p2", "poison") == 1 and res(s, "p1", "poison") == 0
    assert pt(s, vish, cards) == (4, 4)  # +1/+1 for each poison counter your opponents have
    give(s, "p2", "poison", 8)
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=put(s, "Infectious Inquiry", "hand").id)
    settle(s)
    assert res(s, "p2", "poison") == 10
    assert "p2" in rules(s).lost  # 704.5c
    roundtrip(s)


# -- rad counters (728) -----------------------------------------------------------------------------
def test_rad_counters_mill_and_cost_life_at_the_precombat_main_phase(cards):
    s = build(cards, ["Feral Ghoul"], bob=((3, "Grizzly Bears"), (10, "Island")))
    ghoul = put(s, "Feral Ghoul", "battlefield")
    act(s, "p1", type="set_damage", card_ids=[ghoul.id], delta=2)
    act(s, "p1", type="pass_priority")  # it dies (704.5g): each opponent gets rad counters equal to its power
    settle(s)
    assert res(s, "p2", "rad") == 2
    library = list(s.state.zones["p2:library"])[1:]  # (Bob draws the top card first, in his draw step)
    assert [s.state.cards[c].name for c in library[:2]] == ["Grizzly Bears", "Grizzly Bears"]
    run_until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and not s.state.zones.get("stack"))
    settle(s)
    assert set(library[:2]) <= set(s.state.zones["p2:graveyard"]) and s.state.zones["p2:library"] == library[2:]
    assert res(s, "p2", "rad") == 0 and s.state.players["p2"].life == 38
    assert any("Rad counters" in str(e.parts) for e in s.state.log)  # (the inherent trigger, no source: 728.1)
    roundtrip(s)


def test_rad_trigger_does_nothing_without_rad_counters_and_lands_keep_counters(cards):
    s = build(cards, ["Feral Ghoul"], bob=((10, "Island"),))
    give(s, "p2", "rad", 3)
    act(s, "p2", type="set_prefs", response="on")  # (Bob stops with the trigger on the stack)
    run_until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and bool(s.state.zones.get("stack")))
    # the inherent trigger: no source, controlled by the active player (728.1)
    assert [(rules(s).stack[c].name, rules(s).stack[c].controller) for c in s.state.zones["stack"]] == [("Rad counters", "p2")]
    give(s, "p2", "rad", -3)  # (gone before it resolves: 603.4, the ability does nothing)
    library = list(s.state.zones["p2:library"])
    settle(s)
    assert s.state.zones["p2:library"] == library and s.state.players["p2"].life == 40
    give(s, "p2", "rad", 2)
    run_until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")
    settle(s)  # two Islands milled: no life lost, the counters stay
    assert res(s, "p2", "rad") == 2 and s.state.players["p2"].life == 40
    roundtrip(s)
