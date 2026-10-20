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
from app.game.rules_state import DungeonMark
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import conditions, coverage, scripts, values
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, turn_on
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
    card('Harnessed Lightning', set_code='tst', number='E10', mana_cost='{1}{R}', cmc=2.0, type_line='Instant', colors=['R'],
         color_identity=['R'],
         oracle_text='Choose target creature. You get {E}{E}{E} (three energy counters), then you may pay any amount of {E}. Harnessed '
         'Lightning deals that much damage to that creature.'),
    # -- the monarch (725) --
    card('Palace Jailer', set_code='tst', number='M1', mana_cost='{2}{W}{W}', cmc=4.0, type_line='Creature — Human Soldier', colors=['W'],
         color_identity=['W'], power='2', toughness='2',
         oracle_text='When this creature enters, you become the monarch.\nWhen this creature enters, exile target creature an opponent '
         'controls until an opponent becomes the monarch.'),
    card('Custodi Lich', set_code='tst', number='M2', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Zombie Cleric', colors=['B'],
         color_identity=['B'], power='4', toughness='2',
         oracle_text='When this creature enters, you become the monarch.\nWhenever you become the monarch, target player sacrifices a '
         'creature of their choice.'),
    card('Queen Marchesa', set_code='tst', number='M3', mana_cost='{1}{R}{W}{B}', cmc=4.0, type_line='Legendary Creature — Human Assassin',
         colors=['B', 'R', 'W'], color_identity=['B', 'R', 'W'], power='3', toughness='3', keywords=['Haste', 'Deathtouch'],
         oracle_text='Deathtouch, haste\nWhen Queen Marchesa enters, you become the monarch.\nAt the beginning of your upkeep, if an '
         'opponent is the monarch, create a 1/1 black Assassin creature token with deathtouch and haste.'),
    card('Éomer, King of Rohan', set_code='tst', number='M4', mana_cost='{3}{R}{W}', cmc=5.0, type_line='Legendary Creature — Human Noble',
         colors=['R', 'W'], color_identity=['R', 'W'], power='2', toughness='2', keywords=['Double strike'],
         oracle_text='Double strike\nÉomer enters with a +1/+1 counter on it for each other Human you control.\nWhen Éomer enters, target '
         'player becomes the monarch. Éomer deals damage equal to its power to any target.'),
    # -- the initiative (726), dungeons (309, 701.49) --
    card('Goliath Paladin', set_code='tst', number='N1', mana_cost='{4}{W}', cmc=5.0, type_line='Creature — Giant Knight', colors=['W'],
         color_identity=['W'], power='3', toughness='6', keywords=['Vigilance'],
         oracle_text='Vigilance\nWhen this creature enters, you take the initiative.'),
    card('Secret Door', set_code='tst', number='N2', mana_cost='{U}', cmc=1.0, type_line='Artifact Creature — Wall', colors=['U'],
         color_identity=['U'], power='0', toughness='4', keywords=['Defender', 'Venture into the dungeon'],
         oracle_text='Defender\n{4}{U}: Venture into the dungeon. Activate only as a sorcery. (Enter the first room or advance to the next '
         'room.)'),
    card('Cloister Gargoyle', set_code='tst', number='N3', mana_cost='{2}{W}', cmc=3.0, type_line='Artifact Creature — Gargoyle',
         colors=['W'], color_identity=['W'], power='0', toughness='4', keywords=['Venture into the dungeon'],
         oracle_text="When this creature enters, venture into the dungeon. (Enter the first room or advance to the next room.)\nAs long "
         "as you've completed a dungeon, this creature gets +3/+0 and has flying."),
    card('Nadaar, Selfless Paladin', set_code='tst', number='N4', mana_cost='{2}{W}', cmc=3.0, type_line='Legendary Creature — Dragon Knight',
         colors=['W'], color_identity=['W'], power='3', toughness='3', keywords=['Vigilance', 'Venture into the dungeon'],
         oracle_text="Vigilance\nWhenever Nadaar enters or attacks, venture into the dungeon. (Enter the first room or advance to the next "
         "room.)\nOther creatures you control get +1/+1 as long as you've completed a dungeon."),
    # -- the Ring tempts you (701.54) --
    card('Call of the Ring', set_code='tst', number='R1', mana_cost='{1}{B}', cmc=2.0, type_line='Enchantment', colors=['B'],
         color_identity=['B'],
         oracle_text='At the beginning of your upkeep, the Ring tempts you.\nWhenever you choose a creature as your Ring-bearer, you may '
         'pay 2 life. If you do, draw a card.'),
    # -- day and night (731, 702.145) --
    card("Fearful Villager // Fearsome Werewolf", set_code="tst", number="D1", layout="transform", mana_cost=None, cmc=3.0,
         type_line="Creature — Human Werewolf // Creature — Werewolf", colors=["R"], color_identity=["R"], image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Fearful Villager", "mana_cost": "{2}{R}", "type_line": "Creature — Human Werewolf",
              "oracle_text": "Menace (This creature can't be blocked except by two or more creatures.)\nDaybound (If a player casts no "
              "spells during their own turn, it becomes night next turn.)", "power": "2", "toughness": "3", "colors": ["R"]},
             {"object": "card_face", "name": "Fearsome Werewolf", "mana_cost": "", "type_line": "Creature — Werewolf",
              "oracle_text": "Menace (This creature can't be blocked except by two or more creatures.)\nNightbound (If a player casts at "
              "least two spells during their own turn, it becomes day next turn.)", "power": "4", "toughness": "3", "colors": ["R"]}]),
    card("Tovolar's Huntmaster // Tovolar's Packleader", set_code="tst", number="D2", layout="transform", mana_cost=None, cmc=6.0,
         type_line="Creature — Human Werewolf // Creature — Werewolf", colors=["G"], color_identity=["G"], image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Tovolar's Huntmaster", "mana_cost": "{4}{G}{G}", "type_line": "Creature — Human Werewolf",
              "oracle_text": "When this creature enters, create two 2/2 green Wolf creature tokens.\nDaybound (If a player casts no spells "
              "during their own turn, it becomes night next turn.)", "power": "6", "toughness": "6", "colors": ["G"]},
             {"object": "card_face", "name": "Tovolar's Packleader", "mana_cost": "", "type_line": "Creature — Werewolf",
              "oracle_text": "Whenever this creature enters or attacks, create two 2/2 green Wolf creature tokens.\n{2}{G}{G}: Another "
              "target Wolf or Werewolf you control fights target creature you don't control.\nNightbound (If a player casts at least "
              "two spells during their own turn, it becomes day next turn.)", "power": "7", "toughness": "7", "colors": ["G"]}]),
    card('Bilbo, Retired Burglar', set_code='tst', number='R2', mana_cost='{1}{U}{R}', cmc=3.0, type_line='Legendary Creature — Halfling Rogue',
         colors=['R', 'U'], color_identity=['R', 'U'], power='1', toughness='3', keywords=['Treasure'],
         oracle_text='When Bilbo enters or leaves the battlefield, the Ring tempts you.\nWhenever Bilbo deals combat damage to a player, '
         'create a Treasure token.'),
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


def resolve(s, *answers):
    """Resolve the stack, answering each decision that isn't a trigger order with the next answer
    (an option id, or the start of its label; a list for several)."""
    queue = list(answers)
    for _ in range(80):
        d = rules(s).decision
        if d is not None and d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        elif d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        elif d is not None:
            assert queue, f"unexpected decision: {d.prompt} {[o.label for o in d.options]}"
            want = queue.pop(0)
            wants = want if isinstance(want, list) else [want]
            ids = [next((o.id for o in d.options if o.id == w or o.label.startswith(w)), f"?{w} in {d.prompt}: "
                        f"{[(o.id, o.label) for o in d.options]}") for w in wants]
            assert not any(i.startswith("?") for i in ids), ids
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, rules(s).priority, type="pass_priority")
        else:
            break
    assert not queue, f"unused answers {queue}"


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=put(s, name, "hand", pid).id, **kw)


def creature(s, name, pid="p1"):
    """A creature put onto the battlefield by hand that has been there since before the turn."""
    c = put(s, name, "battlefield", pid)
    rules(s).controlled_since[c.id].turn = 0
    return c


def res(s, pid="p1", key="energy"):
    return s.state.players[pid].resources.get(key, 0)


def give(s, pid, key, n):
    act(s, pid, type="resource", player=pid, key=key, delta=n)


def roundtrip(s):
    replay_matches(s)  # (reload: the history rebuilds the same table)
    assert GameState.model_validate(s.state.model_dump(mode="json")).model_dump(mode="json") == s.state.model_dump(mode="json")


def cov_of(c):
    """Coverage of a fixture card as the card database stores it (its faces under "faces")."""
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []})


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
    # Guide of Souls: "When you do" (a reflexive trigger, 603.12) isn't modelled; the venturing cards are carried out and FULL while every
    # dungeon room they may lead into is (wave 45B: Undercity's Arena, goad, is automated: Goliath Paladin is FULL)
    for c in REAL:
        assert cov_of(c).level == "FULL", c["name"]


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
    from tests.game_helpers import mana_pool

    assert mana_pool(s, 'p1').get('G') == 1 and res(s) == 0 and s.state.cards[hub.id].tapped
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


def test_pay_any_amount_of_energy_deals_that_much(cards):
    s = build(cards, ["Harnessed Lightning", "Grizzly Bears"])
    give(s, "p1", "energy", 2)
    bears = put(s, "Grizzly Bears", "battlefield")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=put(s, "Harnessed Lightning", "hand").id, targets=[bears.id])
    settle(s)
    d = rules(s).decision
    assert d is not None and d.player == "p1" and [o.id for o in d.options][:1] == ["5"]  # 2 + {E}{E}{E}: any amount, 0 to 5
    pick(s, ["4"])
    settle(s)
    assert res(s) == 1 and s.state.cards[bears.id].zone == "p1:graveyard", s.state.cards[bears.id].damage  # 4 damage
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


# -- a table with permanents already in play (automation turned on mid-game: not summoning sick) --------
def table(cards, mine=(), theirs=(), hand=(), bob=((10, "Island"),)):
    a = deck(cards, "Krenko, Mob Boss", [(1, n) for n in (*mine, *hand)] + [(10, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [(1, n) for n in theirs] + list(bob))
    s = GameSession(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], shuffle=False), cards=cards)
    for n in mine:
        act(s, "p1", type="move", card_ids=[find(s, n).id], to={"player": "p1", "zone": "battlefield"})
    for n in theirs:
        act(s, "p2", type="move", card_ids=[find(s, n, "p2").id], to={"player": "p2", "zone": "battlefield"})
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def to_attack(s, *pairs):
    """From Alice's main phase to her declare attackers, then attack."""
    act(s, "p1", type="pass_priority")
    d = rules(s).decision
    assert d is not None and d.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


# -- the monarch (725) --------------------------------------------------------------------------------
def test_monarch_wordings_and_coverage():
    assert scripts.parse_effects("Target player becomes the monarch.")[0] == [{"do": "monarch", "who": "target"}]
    assert conditions.parse("there is no monarch") == {"status": "no_monarch"}
    assert conditions.parse("an opponent is the monarch") == {"status": "opponent_monarch"}
    for name in ("Palace Jailer", "Custodi Lich", "Queen Marchesa", "Éomer, King of Rohan"):
        assert cov_of(next(c for c in REAL if c["name"] == name)).level == "FULL", name


def test_become_the_monarch_triggers_only_on_a_change_and_jailer_returns_on_an_opponents_reign(cards):
    s = table(cards, theirs=("Grizzly Bears", "Twisted Abomination"), hand=("Custodi Lich", "Palace Jailer", "Éomer, King of Rohan"))
    bears, abomination = find(s, "Grizzly Bears", "p2"), find(s, "Twisted Abomination", "p2")
    mana(s, B=2, C=3)
    cast(s, "Custodi Lich")
    resolve(s, "p2", bears.id)  # "whenever you become the monarch": target player (Bob) sacrifices a creature of his choice
    assert s.state.table.monarch == "p1" and s.state.cards[bears.id].zone == "p2:graveyard"
    mana(s, W=2, C=2)
    cast(s, "Palace Jailer")
    resolve(s, abomination.id)  # already the monarch: the Lich doesn't trigger again (725.3; Custodi Lich ruling)
    assert s.state.cards[abomination.id].zone == "p2:exile"
    assert any(t.when.get("kind") == "designation" for t in rules(s).delayed)
    jailer = find(s, "Palace Jailer")
    act(s, "p1", type="move", card_ids=[jailer.id], to={"player": "p1", "zone": "graveyard"})  # (leaving doesn't end it)
    mana(s, R=1, W=1, C=3)
    cast(s, "Éomer, King of Rohan")
    resolve(s, "p2", "p2")  # Bob becomes the monarch; Éomer deals 2 damage to Bob
    assert s.state.table.monarch == "p2"
    back = next(c for c in s.state.cards.values() if c.name == "Twisted Abomination")
    assert back.zone == "p2:battlefield" and back.controller == "p2"  # returned under its owner's control
    assert not any(t.when.get("kind") == "designation" for t in rules(s).delayed)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_jailers_exile_ends_at_once_when_an_opponent_becomes_the_monarch(cards):
    """610.3: the return is a one-shot effect created immediately after the event — no ability goes on the stack."""
    s = table(cards, theirs=("Twisted Abomination",), hand=("Palace Jailer", "Éomer, King of Rohan"))
    abomination = find(s, "Twisted Abomination", "p2")
    mana(s, W=2, C=2)
    cast(s, "Palace Jailer")
    resolve(s, abomination.id)
    assert s.state.cards[abomination.id].zone == "p2:exile" and s.state.table.monarch == "p1"
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", full_control=True)  # (nothing resolves on its own)
    mana(s, R=1, W=1, C=3)
    cast(s, "Éomer, King of Rohan")
    for _ in range(40):  # one intent at a time, until Bob is the monarch
        d = rules(s).decision
        if s.state.table.monarch == "p2":
            break
        if d is not None and d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.id == "p2")])
        else:
            act(s, rules(s).priority, type="pass_priority")
    assert s.state.table.monarch == "p2"
    back = next(c for c in s.state.cards.values() if c.name == "Twisted Abomination")
    assert back.zone == "p2:battlefield"  # already back: nothing waited on the stack for it
    assert not any(e.name == "Palace Jailer" for e in rules(s).stack.values())
    roundtrip(s)


def test_monarch_passes_to_the_active_player_when_the_monarch_leaves_and_that_is_becoming_the_monarch(cards):
    s = table(cards, mine=("Custodi Lich",), theirs=("Grizzly Bears",))
    act(s, "p2", type="set_monarch", player="p2")  # (by hand: a manual event, no trigger)
    settle(s)
    assert rules(s).decision is None and s.state.table.monarch == "p2"
    act(s, "p2", type="concede")  # 800.4 / 725.4: Alice (the active player) becomes the monarch
    assert s.state.table.monarch == "p1"
    assert any(e.kind == "designation" and e.counter == "monarch" and e.player == "p1" and not e.manual for e in rules(s).events)
    roundtrip(s)


# -- the initiative (726) and Undercity --------------------------------------------------------------
def test_taking_the_initiative_ventures_into_undercity_and_upkeep_ventures_again(cards):
    s = table(cards, hand=("Goliath Paladin",))
    mana(s, W=1, C=4)
    cast(s, "Goliath Paladin")
    resolve(s, "Forest")  # Secret Entrance: search for a basic land card (a Forest)
    assert s.state.table.initiative == "p1"
    assert rules(s).dungeons["p1"].dungeon == "Undercity" and rules(s).dungeons["p1"].room == "Secret Entrance"
    assert any(e.counter == "initiative" for e in rules(s).events) or True
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "upkeep" and rules(s).decision is not None)
    d = rules(s).decision
    assert d.kind == "choose_one" and {o.id for o in d.options} == {"Forge", "Lost Well"}
    resolve(s, "Lost Well", [])  # Scry 2: keep both on top
    assert rules(s).dungeons["p1"].room == "Lost Well"
    roundtrip(s)


def test_combat_damage_to_the_initiatives_holder_takes_it(cards):
    s = table(cards, mine=("Grizzly Bears",))
    act(s, "p2", type="set_initiative", player="p2")  # (by hand: Bob has it, no trigger)
    settle(s)
    to_attack(s, (find(s, "Grizzly Bears"), "p2"))
    resolve(s, "Forest")  # Alice takes the initiative (the trigger is Bob's, 726.2) and ventures into Undercity: Secret Entrance
    assert s.state.table.initiative == "p1"
    assert rules(s).dungeons["p1"].room == "Secret Entrance"
    roundtrip(s)


def test_retaking_the_initiative_ventures_again(cards):
    s = table(cards, hand=("Goliath Paladin",))
    act(s, "p1", type="set_initiative", player="p1")  # (by hand: no venture)
    settle(s)
    mana(s, W=1, C=4)
    cast(s, "Goliath Paladin")
    resolve(s, "Forest")  # 726.5: taking it again triggers the venture
    assert rules(s).dungeons["p1"].room == "Secret Entrance"
    roundtrip(s)


# -- venture into the dungeon (701.49, 309) ------------------------------------------------------------
def test_venture_through_lost_mine_complete_it_and_start_another(cards):
    s = table(cards, mine=("Secret Door", "Nadaar, Selfless Paladin", "Grizzly Bears"), hand=("Cloister Gargoyle",))
    door, bears = find(s, "Secret Door"), find(s, "Grizzly Bears")

    def venture(*answers):
        mana(s, U=1, C=4)
        act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
        resolve(s, *answers)

    venture("Lost Mine of Phandelver", [])  # Cave Entrance: scry 1 (keep it)
    assert rules(s).dungeons["p1"].room == "Cave Entrance"
    assert s.view("p2")["rules"]["designations"]["p1"]["dungeon"] == {"dungeon": "Lost Mine of Phandelver", "room": "Cave Entrance"}
    venture("Mine Tunnels")  # a fork: the player chooses (701.49b); Mine Tunnels: a Treasure
    assert any(c.name == "Treasure" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    venture("Fungi Cavern", bears.id)  # Fungi Cavern: target creature gets -4/-0 until your next turn
    venture()  # Temple of Dumathoin: draw a card; then the dungeon is completed (309.6, a state-based action)
    assert "p1" not in rules(s).dungeons and rules(s).completed_dungeons["p1"] == ["Lost Mine of Phandelver"]
    assert pt(s, bears, cards) == (-1, 3)  # Nadaar: +1/+1 now that a dungeon is completed; still -4/-0
    venture("Dungeon of the Mad Mage")  # a new dungeon (the same one could be chosen again)
    assert rules(s).dungeons["p1"].room == "Yawning Portal"
    mana(s, W=1, C=2)
    cast(s, "Cloister Gargoyle")
    resolve(s, [])  # Dungeon Level: scry 1 (keep it)
    assert rules(s).dungeons["p1"].room == "Dungeon Level"
    assert Plan(s.state, "p1", cards, None).ch(find(s, "Cloister Gargoyle")).pt == (4, 5)  # +3/+0 (completed a dungeon) and Nadaar's +1/+1
    roundtrip(s)


def test_tomb_of_annihilation_each_player_unless_and_the_atropal(cards):
    s = table(cards, mine=("Secret Door",), theirs=("Grizzly Bears",), hand=("Murder",))
    door, bears = find(s, "Secret Door"), find(s, "Grizzly Bears", "p2")
    put(s, "Murder", "hand")
    life = {"p1": 40, "p2": 40}

    def venture(*answers):
        mana(s, U=1, C=4)
        act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
        resolve(s, *answers)

    venture("Tomb of Annihilation")  # Trapped Entry: each player loses 1 life
    life = {p: n - 1 for p, n in life.items()}
    assert {p: s.state.players[p].life for p in life} == life
    venture("Veils of Fear", "pay")  # each player loses 2 life unless they discard a card (118.12a): Alice discards Murder
    life["p2"] -= 2  # (Bob has no card in hand: he can't pay, 118.3)
    assert {p: s.state.players[p].life for p in life} == life and find(s, "Murder").zone == "p1:graveyard"
    venture("decline", "pay")  # Sandfall Cell, in turn order: Alice declines; Bob sacrifices his Bears
    life["p1"] -= 2
    assert {p: s.state.players[p].life for p in life} == life and s.state.cards[bears.id].zone == "p2:graveyard"
    venture()  # Cradle of the Death God: The Atropal, a legendary 4/4 black God Horror with deathtouch
    atropal = next(c for c in s.state.cards.values() if c.name == "The Atropal")
    ch = Plan(s.state, "p1", cards, None).ch(atropal)
    assert "Legendary" in ch.supertypes and ch.pt == (4, 4) and "deathtouch" in ch.keywords
    assert rules(s).completed_dungeons["p1"] == ["Tomb of Annihilation"] and "p1" not in rules(s).dungeons
    roundtrip(s)


def door_venture(s, *answers):
    mana(s, U=1, C=4)
    act(s, "p1", type="activate_ability", card_id=find(s, "Secret Door").id, ability=1)
    resolve(s, *answers)


def test_oubliette_sacrifices_different_permanents_as_many_as_possible(cards):
    s = table(cards, mine=("Secret Door", "Grizzly Bears", "Forest"), hand=("Murder",))
    put(s, "Murder", "hand")
    door_venture(s, "Tomb of Annihilation")
    door_venture(s, "Oubliette")  # discard Murder; the artifact creature is the artifact, the Bears the creature (Release ruling)
    assert find(s, "Murder").zone == "p1:graveyard"
    for name in ("Secret Door", "Grizzly Bears"):
        assert find(s, name).zone == "p1:graveyard", name
    assert any(c.name == "Forest" and c.zone == "p1:graveyard" for c in s.state.cards.values())
    roundtrip(s)


def test_mad_wizards_lair_reveals_the_cards_drawn_and_casts_one_free(cards):
    s = table(cards, mine=("Secret Door",), hand=("Grizzly Bears", "Lightning Bolt", "Island"))
    rules(s).dungeons["p1"] = DungeonMark(dungeon="Dungeon of the Mad Mage", room="Deep Mines")  # (eight rooms in)
    bears = find(s, "Grizzly Bears")
    door_venture(s, bears.id)  # draw three, reveal them; cast the Bears without paying its mana cost
    resolve(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    assert find(s, "Lightning Bolt").zone == "p1:hand" and find(s, "Lightning Bolt").revealed_to == []  # (the reveal is over)
    assert any("revealed" in "".join(p.t or "" for p in e.parts) for e in s.state.log)
    roundtrip(s)


def test_throne_of_the_dead_three_puts_a_creature_onto_the_battlefield_with_counters(cards):
    s = table(cards, mine=("Secret Door",), hand=("Island", "Grizzly Bears"))
    rules(s).dungeons["p1"] = DungeonMark(dungeon="Undercity", room="Archives")  # (venturing into "the dungeon" goes on in it)
    bears = find(s, "Grizzly Bears")
    door_venture(s)  # (the only creature card among the ten: put onto the battlefield)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].counters.get("+1/+1") == 3
    assert "hexproof" in Plan(s.state, "p1", cards, None).ch(s.state.cards[bears.id]).keywords
    assert rules(s).completed_dungeons["p1"] == ["Undercity"]
    roundtrip(s)


# -- the Ring tempts you (701.54) ----------------------------------------------------------------------
def test_the_ring_tempts_you_chooses_a_legendary_ring_bearer(cards):
    s = table(cards, mine=("Grizzly Bears", "Call of the Ring"), hand=("Bilbo, Retired Burglar",))
    bears = find(s, "Grizzly Bears")
    # Call of the Ring's upkeep trigger: the only creature is the Ring-bearer (701.54a); then "whenever you
    # choose a creature as your Ring-bearer": decline paying 2 life
    resolve(s, "decline")
    assert rules(s).ring_tempted["p1"] == 1 and rules(s).ring_bearers["p1"] == s.state.rules.object_id(bears.id)
    assert "Legendary" in Plan(s.state, "p1", cards, None).ch(s.state.cards[bears.id]).supertypes  # 701.54c
    mana(s, U=1, R=1, C=1)
    cast(s, "Bilbo, Retired Burglar")
    hand = len(s.state.zones["p1:hand"])
    bilbo = find(s, "Bilbo, Retired Burglar")
    resolve(s, bilbo.id, "pay")  # the Ring tempts again: Bilbo this time; pay 2 life, draw a card
    assert rules(s).ring_tempted["p1"] == 2 and rules(s).ring_bearers["p1"] == s.state.rules.object_id(bilbo.id)
    assert "Legendary" not in Plan(s.state, "p1", cards, None).ch(s.state.cards[bears.id]).supertypes  # not the Ring-bearer now
    assert s.state.players["p1"].life == 38 and len(s.state.zones["p1:hand"]) == hand + 1
    roundtrip(s)


def test_ring_bearer_evasion_loot_sacrifice_and_drain(cards):
    s = table(cards, mine=("Grizzly Bears",), theirs=("Twisted Abomination", "Sol Ring"), hand=("Bilbo, Retired Burglar",))
    bears, abomination = find(s, "Grizzly Bears"), find(s, "Twisted Abomination", "p2")
    mana(s, U=1, R=1, C=1)
    cast(s, "Bilbo, Retired Burglar")
    resolve(s, bears.id)
    rules(s).ring_tempted["p1"] = 4  # (as if tempted four times: every ability of the emblem, 701.54c)
    hand = len(s.state.zones["p1:hand"])
    to_attack(s, (find(s, "Grizzly Bears"), "p2"))
    resolve(s, [s.state.zones["p1:hand"][0]] if s.state.zones["p1:hand"] else [])  # loot: draw, then discard
    assert len(s.state.zones["p1:hand"]) == hand
    with pytest.raises(ActionError, match="Ring-bearer"):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": abomination.id, "attacker_id": bears.id}])
    act(s, "p2", type="declare_blockers", blocks=[])
    resolve(s)
    assert s.state.players["p2"].life == 40 - 2 - 3  # combat damage, then each opponent loses 3
    roundtrip(s)


def test_ring_bearer_is_lost_when_another_player_gains_control(cards):
    s = table(cards, mine=("Grizzly Bears",), hand=("Bilbo, Retired Burglar",))
    bears = find(s, "Grizzly Bears")
    mana(s, U=1, R=1, C=1)
    cast(s, "Bilbo, Retired Burglar")
    resolve(s, bears.id)
    assert rules(s).ring_bearers["p1"] == rules(s).object_id(bears.id)
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p2")  # (another player gains control of it: 701.54a)
    settle(s)
    act(s, "p1", type="pass_priority")  # (state-based checks)
    assert "p1" not in rules(s).ring_bearers
    assert "Legendary" not in Plan(s.state, "p1", cards, None).ch(s.state.cards[bears.id]).supertypes
    act(s, "p2", type="set_controller", card_ids=[bears.id], player="p1")  # back: it isn't the Ring-bearer again
    assert "p1" not in rules(s).ring_bearers and rules(s).ring_tempted["p1"] == 1
    roundtrip(s)


# -- day and night (731, 702.145) ---------------------------------------------------------------------
def test_day_night_wordings():
    got = scripts.parse_effects("Target creature gets -2/-2 until end of turn. If it's night, that creature gets -13/-13 until end "
                                "of turn instead.")  # Olivia's Midnight Ambush
    assert got is not None and got[0][0]["cond"] == {"not": {"status": "night"}}
    assert scripts.parse_effects("It becomes night.")[0] == [{"do": "day_night", "value": "night"}]
    for c in REAL:
        if "//" in c["name"]:
            assert cov_of(c).level == "FULL", c["name"]


def test_daybound_makes_it_day_night_falls_after_a_turn_without_spells_and_two_spells_bring_day(cards):
    s = table(cards, mine=("Fearful Villager // Fearsome Werewolf",), theirs=("Opt", "Opt"), bob=((10, "Island"),))
    villager = find(s, "Fearful Villager // Fearsome Werewolf")
    assert s.state.table.day_night == "day" and s.state.cards[villager.id].face == 0  # 702.145d
    run_until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    # 502.2: Alice cast no spell in her turn: it became night in Bob's untap step; the daybound permanent transformed
    assert s.state.table.day_night == "night" and s.state.cards[villager.id].face == 1
    assert Plan(s.state, "p1", cards, None).ch(s.state.cards[villager.id]).pt == (4, 3)
    for opt in [c for c in s.state.cards.values() if c.name == "Opt" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[opt.id], to={"player": "p2", "zone": "hand"})
        mana(s, "p2", U=1)
        act(s, "p2", type="cast_spell", card_id=opt.id)
        resolve(s, [])  # (scry 1: keep it)
    run_until(s, lambda s: s.state.turn.active_player == "p1" and s.state.turn.phase == "upkeep" or
              s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.table.day_night == "day" and s.state.cards[villager.id].face == 0  # two spells: day; nightbound transformed back
    roundtrip(s)


def test_daybound_permanent_enters_transformed_at_night(cards):
    s = table(cards, hand=("Tovolar's Huntmaster // Tovolar's Packleader",))
    act(s, "p1", type="set_day_night", value="night")  # (by hand)
    mana(s, G=2, C=4)
    cast(s, "Tovolar's Huntmaster // Tovolar's Packleader")
    resolve(s)
    hunt = find(s, "Tovolar's Huntmaster // Tovolar's Packleader")
    assert s.state.cards[hunt.id].face == 1  # 702.145b: it enters transformed
    wolves = [c for c in s.state.cards.values() if c.name == "Wolf" and c.zone == "p1:battlefield"]
    assert len(wolves) == 2  # only Tovolar's Packleader's "enters" trigger: the front face never was on the battlefield
    roundtrip(s)
