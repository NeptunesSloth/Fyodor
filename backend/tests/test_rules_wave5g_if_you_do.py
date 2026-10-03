"""Wave 5G: second pass on "If you do" (CR 2026-09-25).

Sized payments (app/rules/paid_x.py over app/rules/optional_payment.py): "you may pay {X}. If you do, …X…" — X
appears in no cost of the ability, so its controller chooses it as the payment is made (107.3f, 118.12), never more
than they can pay (118.3, 601.2h) or than the text allows ("where X is less than or equal to the amount of life you
gained", "X can't be greater than the amount of life you gained this turn"); "you may pay X life, where X is its
power" (107.3c: X defined by the text, worked out once as it is paid, 608.2h; 119.4). The rest of the ability reads
the X paid. The choice is the payer's, in private.

The cards are real Commander cards, their Oracle text transcribed from the card database. Every scenario checks
that replaying the recorded history reproduces the table and that the state survives a save."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import creature, life, on_field, pick, settle, to_hand, until, until_asked
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card('Vigil for the Lost', set_code="tst", number="G1", mana_cost='{3}{W}', cmc=4.0, type_line='Enchantment',
         oracle_text='Whenever a creature you control dies, you may pay {X}. If you do, you gain X life.', colors=['W'], color_identity=['W']),
    card('Hero of Leina Tower', set_code="tst", number="G2", mana_cost='{G}', cmc=1.0, type_line='Creature — Human Warrior',
         oracle_text='Heroic — Whenever you cast a spell that targets this creature, you may pay {X}. If you do, put X +1/+1 counters on this creature.', power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=['Heroic']),
    card('Squealing Devil', set_code="tst", number="G3", mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Devil',
         oracle_text="Fear (This creature can't be blocked except by artifact creatures and/or black creatures.)\nWhen this creature enters, you may pay {X}. If you do, target creature gets +X/+0 until end of turn.\nWhen this creature enters, sacrifice it unless {B} was spent to cast it.", power='2', toughness='1', colors=['R'], color_identity=['B', 'R'], keywords=['Fear']),
    card('Well of Lost Dreams', set_code="tst", number="G4", mana_cost='{4}', cmc=4.0, type_line='Artifact',
         oracle_text='Whenever you gain life, you may pay {X}, where X is less than or equal to the amount of life you gained. If you do, draw X cards.', colors=[], color_identity=[]),
    card('Shanna, Purifying Blade', set_code="tst", number="G5", mana_cost='{G}{W}{U}', cmc=3.0, type_line='Legendary Creature — Human Warrior',
         oracle_text="Lifelink\nAt the beginning of your end step, you may pay {X}. If you do, draw X cards. X can't be greater than the amount of life you gained this turn.", power='3', toughness='3', colors=['G', 'U', 'W'], color_identity=['G', 'U', 'W'], keywords=['Lifelink']),
    card('Mask of Griselbrand', set_code="tst", number="G6", mana_cost='{1}{B}{B}', cmc=3.0, type_line='Legendary Artifact — Equipment',
         oracle_text='Equipped creature has flying and lifelink.\nWhenever equipped creature dies, you may pay X life, where X is its power. If you do, draw X cards.\nEquip {3}', colors=['B'], color_identity=['B'], keywords=['Equip']),
    card('Niv-Mizzet, Ghost Counsel', set_code="tst", number="G7", mana_cost='{2}{W}{W}{B}{B}', cmc=6.0, type_line='Legendary Creature — Spirit Dragon',
         oracle_text='Flying\nWhenever you gain life, you may pay that much life. If you do, draw that many cards.\n{T}: Each opponent loses 1 life and you gain 1 life.', power='4', toughness='4', colors=['B', 'W'], color_identity=['B', 'W'], keywords=['Flying']),
    card('Madame Null, Power Broker', set_code="tst", number="G8", mana_cost='{2}{B}', cmc=3.0, type_line='Legendary Creature — Demon Advisor',
         oracle_text='Deathtouch\nWhenever another creature you control enters, you may pay life equal to its power. If you do, put that many +1/+1 counters on it.', power='1', toughness='3', colors=['B'], color_identity=['B'], keywords=['Deathtouch']),
    card('Taj-Nar Swordsmith', set_code="tst", number="G9", mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Cat Soldier',
         oracle_text='When this creature enters, you may pay {X}. If you do, search your library for an Equipment card with mana value X or less, put that card onto the battlefield, then shuffle.', power='2', toughness='3', colors=['W'], color_identity=['W']),
    card('Relentless Dead', set_code="tst", number="G10", mana_cost='{B}{B}', cmc=2.0, type_line='Creature — Zombie',
         oracle_text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature dies, you may pay {B}. If you do, return it to its owner's hand.\nWhen this creature dies, you may pay {X}. If you do, return another target Zombie creature card with mana value X from your graveyard to the battlefield.", power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=['Menace']),
    card('Mortarion, Daemon Primarch', set_code="tst", number="G11", mana_cost='{5}{B}', cmc=6.0, type_line='Legendary Creature — Demon Primarch',
         oracle_text="Flying\nPrimarch of the Death Guard — At the beginning of your end step, you may pay {X}. If you do, create X 2/2 black Astartes Warrior creature tokens with menace. X can't be greater than the amount of life you lost this turn.", power='5', toughness='6', colors=['B'], color_identity=['B'], keywords=['Flying', 'Primarch of the Death Guard']),
    card("Stark's Ingenuity", set_code="tst", number="G12", mana_cost='{2}{U}', cmc=3.0, type_line='Enchantment — Aura',
         oracle_text='Enchant creature you control\nWhen this Aura enters, you may pay {X}. If you do, draw X cards.\nWhenever you draw a card, put a +1/+1 counter on enchanted creature.', colors=['U'], color_identity=['U'], keywords=['Enchant']),
]
SIZED = ["Vigil for the Lost", "Hero of Leina Tower", "Squealing Devil", "Well of Lost Dreams", "Shanna, Purifying Blade",
         "Mask of Griselbrand", "Niv-Mizzet, Ghost Counsel", "Madame Null, Power Broker", "Taj-Nar Swordsmith",
         "Mortarion, Daemon Primarch", "Stark's Ingenuity"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (12, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (12, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def roundtrip(s):
    replay_matches(s)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def pt(s, c):
    from app.rules.plan import Plan

    got = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return got.pt


def hand(s, pid="p1"):
    return zone(s.state, pid, "hand")


def bolt(s, target, pid="p1"):
    """Alice bolts her own creature (the death that triggers Vigil / Mask)."""
    b = to_hand(s, "Lightning Bolt", pid)
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=b.id, targets=[target.id])


# -- the wording ------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", SIZED)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_refused_forms(cards):
    # an X in a target's definition: the target is chosen before X (603.3d)
    dead = coverage.of_card_data(cards.resolve("Relentless Dead"))
    assert [f.supported for f in dead.features if f.id == "text:2"] == [False]
    # an X the rest of the ability never reads, "If you don't" after an X, a cap with nothing to cap
    assert scripts.parse_effects("You may pay {X}. If you do, draw a card.") is None
    assert scripts.parse_effects("You may pay {X}. If you don't, draw X cards.") is None
    assert scripts.parse_effects("Draw a card. X can't be greater than the amount of life you gained this turn.") is None


def test_wordings():
    found = scripts.parse_effects("You may pay {X}. If you do, you gain X life.")
    assert found is not None
    pay, gate, gain = found[0]
    assert pay["choose_x"] == {"max": None} and gain["n"] == {"paid_x": pay["bind"]}
    found = scripts.parse_effects("You may pay {X}. If you do, draw X cards. X can't be greater than the amount of life you "
                                  "gained this turn.")
    assert found is not None and found[0][0]["choose_x"] == {"max": {"turn_history": "gained"}}


# -- "you may pay {X}" ---------------------------------------------------------------------------
@pytest.mark.parametrize("x", [0, 2, None])
def test_vigil_for_the_lost_x_chosen_as_it_is_paid(cards, x):
    s = build(cards, p1=("Vigil for the Lost", "Lightning Bolt"))
    on_field(s, "Vigil for the Lost")
    bear = creature(s, "p1", "Bear")
    mana(s, "p1", C=3)
    bolt(s, bear)
    d = until_asked(s)
    assert d.player == "p1"
    # X up to what Alice can pay (118.3): {C}{C}{C} in her pool
    assert [o.id for o in d.options] == ["x:0", "x:1", "x:2", "x:3", "decline"]
    assert "options" not in s.view("p2")["rules"]["decision"]  # (her choice, privately)
    roundtrip(s)
    before = life(s)
    pick(s, "decline" if x is None else f"x:{x}")
    settle(s)
    assert life(s) == before + (x or 0)
    assert s.state.players["p1"].mana.get("C", 0) == 3 - (x or 0)
    roundtrip(s)


def test_vigil_with_no_mana_offers_only_zero(cards):
    s = build(cards, p1=("Vigil for the Lost", "Lightning Bolt"))
    on_field(s, "Vigil for the Lost")
    bear = creature(s, "p1", "Bear")
    bolt(s, bear)
    d = until_asked(s)
    assert [o.id for o in d.options] == ["x:0", "decline"]
    pick(s, "x:0")
    settle(s)
    roundtrip(s)


def test_hero_of_leina_tower_counters(cards):
    s = build(cards, p1=("Hero of Leina Tower", "Giant Growth"))
    hero = on_field(s, "Hero of Leina Tower")
    growth = to_hand(s, "Giant Growth")
    mana(s, "p1", G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[hero.id])
    d = until_asked(s)
    assert [o.id for o in d.options] == ["x:0", "x:1", "x:2", "decline"]
    pick(s, "x:2")
    settle(s)
    assert s.state.cards[hero.id].counters.get("+1/+1", 0) == 2
    roundtrip(s)


def test_squealing_devil_pumps_its_target_by_x(cards):
    s = build(cards, p1=("Squealing Devil",))
    devil = to_hand(s, "Squealing Devil")
    bear = creature(s, "p1", "Bear")
    mana(s, "p1", R=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=devil.id)
    for _ in range(20):
        d = until_asked(s)
        if d is None:
            break
        ids = [o.id for o in d.options]
        if d.min_choices > 1:
            pick(s, *ids[:d.min_choices])
        elif "x:2" in ids:
            pick(s, "x:2")
        elif bear.id in ids:
            pick(s, bear.id)
        else:
            pick(s, ids[0])
    assert pt(s, bear) == (4, 2)
    roundtrip(s)


# -- the limits ------------------------------------------------------------------------------------
def test_well_of_lost_dreams_no_more_than_the_life_gained(cards):
    s = build(cards, p1=("Well of Lost Dreams", "Spike Feeder"))
    on_field(s, "Well of Lost Dreams")
    feeder = on_field(s, "Spike Feeder")
    act(s, "p1", type="counter", card_ids=[feeder.id], kind="+1/+1", delta=2)
    mana(s, "p1", C=5)
    act(s, "p1", type="activate_ability", card_id=feeder.id, ability=1)
    d = until_asked(s)
    assert [o.id for o in d.options] == ["x:0", "x:1", "x:2", "decline"]  # (2 life gained, though {5} is there)
    drawn = len(hand(s))
    pick(s, "x:2")
    settle(s)
    assert len(hand(s)) == drawn + 2 and s.state.players["p1"].mana.get("C", 0) == 3
    roundtrip(s)


@pytest.mark.parametrize("gain", [True, False])
def test_shanna_no_more_than_the_life_gained_this_turn(cards, gain):
    """The X chosen at her end step is capped by the life gained this turn (the turn's history), and by her lands."""
    s = build(cards, p1=("Shanna, Purifying Blade", "Spike Feeder"))
    on_field(s, "Shanna, Purifying Blade")
    feeder = on_field(s, "Spike Feeder")
    act(s, "p1", type="counter", card_ids=[feeder.id], kind="+1/+1", delta=2)
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:4]
    act(s, "p1", type="move", card_ids=[c.id for c in forests], to={"player": "p1", "zone": "battlefield"})
    if gain:
        act(s, "p1", type="activate_ability", card_id=feeder.id, ability=1)
        settle(s)
    until(s, lambda s: s.state.rules.decision is not None or s.state.turn.phase == "end" and s.state.zones.get("stack"))
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    assert [o.id for o in d.options] == (["x:0", "x:1", "x:2", "decline"] if gain else ["x:0", "decline"])
    drawn = len(hand(s))
    pick(s, "x:2" if gain else "x:0")
    settle(s)
    assert len(hand(s)) == drawn + (2 if gain else 0)
    roundtrip(s)


# -- life X ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("paid", [True, False])
def test_mask_of_griselbrand_pays_the_power_as_it_last_existed(cards, paid):
    s = build(cards, p1=("Mask of Griselbrand", "Lightning Bolt"))
    mask = on_field(s, "Mask of Griselbrand")
    bear = creature(s, "p1", "Bear", pt="3/2")
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=mask.id, ability=2, targets=[bear.id])
    settle(s)
    assert s.state.cards[mask.id].attached_to == bear.id
    bolt(s, bear)
    d = until_asked(s)
    assert d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"] and "3 life" in d.options[0].label
    before, drawn = life(s), len(hand(s))
    pick(s, "pay" if paid else "decline")
    settle(s)
    assert life(s) == before - (3 if paid else 0)
    assert len(hand(s)) == drawn + (3 if paid else 0)
    roundtrip(s)


def test_madame_null_that_many_counters(cards):
    s = build(cards, p1=("Madame Null, Power Broker", "Grizzly Bears"))
    on_field(s, "Madame Null, Power Broker")
    before = life(s)
    bear = to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    d = until_asked(s)
    assert d is not None and "2 life" in d.options[0].label
    pick(s, "pay")
    settle(s)
    assert life(s) == before - 2 and s.state.cards[bear.id].counters.get("+1/+1", 0) == 2
    roundtrip(s)


def test_niv_mizzet_pays_that_much_life(cards):
    s = build(cards, p1=("Niv-Mizzet, Ghost Counsel", "Spike Feeder"))
    on_field(s, "Niv-Mizzet, Ghost Counsel")
    feeder = on_field(s, "Spike Feeder")
    act(s, "p1", type="counter", card_ids=[feeder.id], kind="+1/+1", delta=2)
    act(s, "p1", type="activate_ability", card_id=feeder.id, ability=1)
    d = until_asked(s)
    assert d is not None and "2 life" in d.options[0].label
    before, drawn = life(s), len(hand(s))
    pick(s, "pay")
    settle(s)
    assert life(s) == before - 2 and len(hand(s)) == drawn + 2
    roundtrip(s)


def test_a_life_payment_too_large_isnt_offered(cards):
    """119.4: Alice at 2 life can't pay 3 — PAY isn't offered (the ability does nothing)."""
    s = build(cards, p1=("Mask of Griselbrand", "Lightning Bolt"))
    mask = on_field(s, "Mask of Griselbrand")
    bear = creature(s, "p1", "Bear", pt="3/2")
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=mask.id, ability=2, targets=[bear.id])
    settle(s)
    act(s, "p1", type="set_life", player="p1", value=2)
    drawn = len(hand(s))
    bolt(s, bear)
    assert until_asked(s) is None
    assert len(hand(s)) == drawn and life(s) == 2
    roundtrip(s)
