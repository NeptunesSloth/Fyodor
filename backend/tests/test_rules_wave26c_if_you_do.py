"""Wave 26C: "If you do" wordings (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 118.12 / 107.3f / 118.3: "you may pay {X}{W}{U}{B}. If you do, draw X cards." (Elenda and Azor, Flameblast Dragon): X is chosen as the
  payment is made, the colored symbols beside it are paid with it, and the payment is offered only while those symbols can be paid.
* 118.12 / 608.2h: "Its controller may pay 1 life. If they do, they draw a card." (Gix, Yawgmoth Praetor): the payer is the controller of
  the object the trigger is about; "If they do" is that player's own payment.
* 118.12a / 608.2c: "You may sacrifice a Food. If you do, X. Otherwise, Y." is "If you don't, Y" on the same payment (Insatiable
  Appetite, Giant Opportunity, Rent Is Due).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, pick, until_asked
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

REAL = [
    ("Elenda and Azor", "{3}{W}{U}{B}", "Legendary Creature — Vampire Knight Sphinx", "6", "6",
     "Flying, ward {2}\nWhenever Elenda and Azor attacks, you may pay {X}{W}{U}{B}. If you do, draw X cards.\n"
     "At the beginning of each end step, you may pay 4 life. If you do, create a number of 1/1 black Vampire Knight creature tokens with "
     "lifelink equal to the number of cards you've drawn this turn."),
    ("Gix, Yawgmoth Praetor", "{1}{B}{B}", "Legendary Creature — Phyrexian Praetor", "3", "3",
     "Whenever a creature deals combat damage to one of your opponents, its controller may pay 1 life. If they do, they draw a card.\n"
     "{4}{B}{B}{B}, Discard X cards: Exile the top X cards of target opponent's library. You may play lands and cast spells from among "
     "cards exiled this way without paying their mana costs."),
    ("Insatiable Appetite", "{1}{G}", "Instant", None, None,
     "You may sacrifice a Food. If you do, target creature gets +5/+5 until end of turn. Otherwise, that creature gets +3/+3 until end of turn."),
    ("Giant Opportunity", "{2}{G}", "Sorcery", None, None,
     "You may sacrifice two Foods. If you do, create a 7/7 green Giant creature token. Otherwise, create three Food tokens. "
     "(They're artifacts with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")"),
    ("Rent Is Due", "{W}", "Enchantment", None, None,
     "At the beginning of your end step, you may tap two untapped creatures and/or Treasures you control. If you do, draw a card. "
     "Otherwise, sacrifice this enchantment."),
    ("Essence Bottle", "{2}", "Artifact", None, None,
     "{3}, {T}: Put an elixir counter on this artifact.\n{T}, Remove all elixir counters from this artifact: You gain 2 life for each elixir "
     "counter removed this way."),
    ("Molten Hydra", "{1}{R}", "Creature — Hydra", "1", "1",
     "{1}{R}{R}: Put a +1/+1 counter on this creature.\n{T}, Remove all +1/+1 counters from this creature: It deals damage to any target "
     "equal to the number of +1/+1 counters removed this way."),
    ("Geometric Nexus", "{2}", "Artifact", None, None,
     "Whenever a player casts an instant or sorcery spell, put a number of charge counters on this artifact equal to that spell's mana value.\n"
     "{6}, {T}, Remove all charge counters from this artifact: Create a 0/0 green and blue Fractal creature token. Put X +1/+1 counters on "
     "it, where X is the number of charge counters removed this way."),
    ("Vish Kal, Blood Arbiter", "{4}{W}{B}{B}", "Legendary Creature — Vampire", "5", "5",
     "Flying, lifelink\nSacrifice a creature: Put X +1/+1 counters on Vish Kal, where X is the sacrificed creature's power.\n"
     "Remove all +1/+1 counters from Vish Kal: Target creature gets -1/-1 until end of turn for each +1/+1 counter removed this way."),
    ("Lion's Eye Diamond", "{0}", "Artifact", None, None,
     "Discard your hand, Sacrifice this artifact: Add three mana of any one color. Activate only as an instant."),
    ("Dragonsoul Knight", "{2}{R}", "Creature — Human Knight", "2", "2",
     "First strike\n{W}{U}{B}{R}{G}: Until end of turn, this creature becomes a Dragon, gets +5/+3, and gains flying and trample."),
    ("Wishful Merfolk", "{1}{U}", "Creature — Merfolk", "3", "2", "Defender\n{1}{U}: This creature loses defender and becomes a Human until end of turn."),
    ("Flameblast Dragon", "{4}{R}{R}", "Creature — Dragon", "5", "5",
     "Flying\nWhenever this creature attacks, you may pay {X}{R}. If you do, it deals X damage to any target."),
]
EXTRA = [card(n, set_code="t26c", number=f"T{i:02d}", mana_cost=mc, cmc=float(len(mc.replace("{", "").split("}")) - 1), type_line=tl,
              colors=["B"], color_identity=["B"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [r[0] for r in REAL if r[0] != "Gix, Yawgmoth Praetor"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_gix_trigger_line_is_read(cards):
    gix = coverage.of_card_data(cards.resolve("Gix, Yawgmoth Praetor"))
    assert [f.supported for f in gix.features if f.id == "text:0"] == [True]


def ready(s, *names):
    for n in names:
        s.state.rules.controlled_since[card_named(s, n).id].turn = 0


def attack_with(s, name, **pool_mana):
    act(s, "p1", type="pass_priority")  # -> declare attackers
    assert s.state.rules.decision.kind == "declare_attackers"
    if pool_mana:
        mana(s, **pool_mana)  # (the pool empties as the main phase ends: pay with what is added during combat)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, name).id, "target": "p2"}])


def hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


# -- "pay {X}{W}{U}{B}" ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("x", [0, 3])
def test_x_with_colored_symbols_is_paid_together(cards, x):
    s = build(cards, ["Elenda and Azor"])
    put(s, "Elenda and Azor")
    ready(s, "Elenda and Azor")
    before = hand_size(s)
    attack_with(s, "Elenda and Azor", W=1, U=1, B=1, C=3)
    d = until_asked(s)
    assert d.player == "p1"
    # X up to what is left after {W}{U}{B} (118.3): {C}{C}{C} (so X = 3 pays all six mana)
    assert [o.id for o in d.options] == ["x:0", "x:1", "x:2", "x:3", "decline"]
    assert "options" not in s.view("p2")["rules"]["decision"]  # (her choice, privately)
    check(s)
    pick(s, f"x:{x}")
    answer(s)
    assert hand_size(s) == before + x
    check(s)


def test_x_payment_is_not_offered_when_the_colored_part_cannot_be_paid(cards):
    s = build(cards, ["Elenda and Azor"])
    put(s, "Elenda and Azor")
    ready(s, "Elenda and Azor")
    before = hand_size(s)
    attack_with(s, "Elenda and Azor", W=1, U=1, C=3)  # no {B}
    assert until_asked(s) is None  # nothing to decide: {X}{W}{U}{B} can't be paid at all
    assert hand_size(s) == before
    check(s)


# -- "its controller may pay 1 life. If they do, they draw a card" -----------------------------------------------
@pytest.mark.parametrize("pay", [True, False])
def test_gix_the_creatures_controller_pays_and_draws(cards, pay):
    s = build(cards, ["Gix, Yawgmoth Praetor", "Flameblast Dragon"])
    put(s, "Gix, Yawgmoth Praetor")
    put(s, "Flameblast Dragon")
    ready(s, "Flameblast Dragon")
    before, cards_before = life(s), hand_size(s)
    attack_with(s, "Flameblast Dragon")
    d = until_asked(s)
    while d is not None and "decline" not in [o.id for o in d.options] and "pay" not in [o.id for o in d.options]:
        pick(s, d.options[0].id)  # (the Dragon's own {X}{R} payment is not made: no mana)
        d = until_asked(s)
    assert d is not None and d.player == "p1"
    check(s)
    pick(s, "pay" if pay else "decline")
    answer(s)
    assert life(s) == before - (1 if pay else 0) and hand_size(s) == cards_before + (1 if pay else 0)
    check(s)


# -- "If you do, …. Otherwise, …." --------------------------------------------------------------------------------
@pytest.mark.parametrize("food,bonus", [(True, 5), (False, 3)])
def test_insatiable_appetite_otherwise_is_if_you_dont(cards, food, bonus):
    s = build(cards, ["Insatiable Appetite"])
    bear = creature(s, "p1", "Bear")
    if food:
        creature(s, "p1", "Food", pt="0/0", type_line="Token Artifact — Food")
    spell = to_hand(s, "Insatiable Appetite")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    d = until_asked(s)
    if food:
        pick(s, "pay")
        d = until_asked(s)
        if d is not None:  # (which Food: only one)
            pick(s, d.options[0].id)
    answer(s)
    from app.rules.plan import Plan

    got = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id])
    assert got.pt == (2 + bonus, 2 + bonus)
    check(s)


def test_giant_opportunity_otherwise_creates_food(cards):
    s = build(cards, ["Giant Opportunity"])
    spell = to_hand(s, "Giant Opportunity")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)  # (no Foods: the payment is not offered, the Otherwise branch runs)
    foods = [c for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield"]
    assert len(foods) == 3
    check(s)


def test_refused_forms(cards):
    # "Otherwise" after something that isn't an "If you do" stays manual; a payment nobody can read stays manual
    from app.rules import scripts

    assert scripts.parse_effects("Draw a card. Otherwise, discard a card.") is None
    assert scripts.parse_effects("You may pay {X}{X}. If you do, draw X cards.") is None


# -- "Remove all oil counters from ~: … the number removed this way" ------------------------------------------------
def counters(s, name, kind):
    return s.state.cards[card_named(s, name).id].counters.get(kind, 0)


def add_counters(s, name, kind, n):
    act(s, "p1", type="counter", card_ids=[card_named(s, name).id], kind=kind, delta=n)


def activate(s, name, start, **kw):
    c = card_named(s, name)
    index = next(i for i, a in enumerate(s.cards.resolve(name).get("oracle_text", "").split("\n")) if a.startswith(start))
    act(s, "p1", type="activate_ability", card_id=c.id, ability=index, **kw)


@pytest.mark.parametrize("n", [0, 3])
def test_essence_bottle_gains_for_every_counter_it_removed(cards, n):
    s = build(cards, ["Essence Bottle"])
    put(s, "Essence Bottle")
    if n:
        add_counters(s, "Essence Bottle", "elixir", n)
    before = life(s)
    activate(s, "Essence Bottle", "{T}, Remove all")  # (no X announced: it is every counter there is, 602.2b)
    answer(s)
    assert life(s) == before + 2 * n and counters(s, "Essence Bottle", "elixir") == 0
    check(s)


@pytest.mark.parametrize("n", [0, 2])
def test_molten_hydra_deals_damage_equal_to_the_counters_removed(cards, n):
    s = build(cards, ["Molten Hydra"])
    put(s, "Molten Hydra")
    ready(s, "Molten Hydra")
    if n:
        add_counters(s, "Molten Hydra", "+1/+1", n)
    before = life(s, "p2")
    activate(s, "Molten Hydra", "{T}, Remove all", targets=["p2"])
    answer(s)
    assert life(s, "p2") == before - n and counters(s, "Molten Hydra", "+1/+1") == 0
    check(s)


def test_geometric_nexus_token_gets_that_many_counters(cards):
    s = build(cards, ["Geometric Nexus"])
    put(s, "Geometric Nexus")
    add_counters(s, "Geometric Nexus", "charge", 4)
    mana(s, C=6)
    activate(s, "Geometric Nexus", "{6}")
    answer(s)
    fractal = next(c for c in s.state.cards.values() if c.name == "Fractal" and c.zone == "p1:battlefield")
    assert fractal.counters.get("+1/+1") == 4 and counters(s, "Geometric Nexus", "charge") == 0
    check(s)


def test_vish_kal_shrinks_the_target_for_each_counter_removed(cards):
    s = build(cards, ["Vish Kal, Blood Arbiter"])
    put(s, "Vish Kal, Blood Arbiter")
    bear = creature(s, "p2", "Bear", pt="3/3")
    add_counters(s, "Vish Kal, Blood Arbiter", "+1/+1", 3)
    activate(s, "Vish Kal, Blood Arbiter", "Remove all", targets=[bear.id])
    answer(s)
    assert bear.id not in s.state.cards  # (-3/-3: the 3/3 token died and ceased to exist)
    assert counters(s, "Vish Kal, Blood Arbiter", "+1/+1") == 0
    check(s)


def test_removed_this_way_is_read_only_when_the_cost_removed_them(cards):
    from app.rules import scripts

    # a trigger's "that much" / a cost that removes a fixed number never reads as the removed-all X
    assert scripts.parse_effects("Put X +1/+1 counters on it, where X is the number of charge counters removed this way.") is None


# -- "Discard your hand, Sacrifice this artifact: Add three mana of any one color." -----------------------------------
def test_lions_eye_diamond_discards_the_hand_as_a_cost(cards):
    s = build(cards, ["Lion's Eye Diamond", "Giant Opportunity", "Rent Is Due"])
    put(s, "Lion's Eye Diamond")
    to_hand(s, "Giant Opportunity")
    to_hand(s, "Rent Is Due")
    assert hand_size(s) == 2
    activate(s, "Lion's Eye Diamond", "Discard your hand")
    pick(s, "2")  # (which color: W U B R G)
    assert hand_size(s) == 0 and zone_of(s, "Giant Opportunity") == "p1:graveyard" and zone_of(s, "Lion's Eye Diamond") == "p1:graveyard"
    assert s.state.players["p1"].mana.get("B") == 3
    check(s)


# -- one subject, several predicates ----------------------------------------------------------------------------------
def chars_of(s, name):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name).id])


def test_dragonsoul_knight_becomes_gets_and_gains_until_end_of_turn(cards):
    s = build(cards, ["Dragonsoul Knight"])
    put(s, "Dragonsoul Knight")
    before = chars_of(s, "Dragonsoul Knight")
    assert set(before.subtypes) == {"Human", "Knight"} and before.pt == (2, 2)
    mana(s, W=1, U=1, B=1, R=1, G=1)
    activate(s, "Dragonsoul Knight", "{W}{U}{B}{R}{G}")
    answer(s)
    ch = chars_of(s, "Dragonsoul Knight")
    assert set(ch.subtypes) == {"Dragon"} and ch.pt == (7, 5) and {"flying", "trample", "first strike"} <= set(ch.keywords)
    check(s)


def test_wishful_merfolk_loses_defender_and_becomes_a_human(cards):
    s = build(cards, ["Wishful Merfolk"])
    put(s, "Wishful Merfolk")
    mana(s, U=2)
    assert "defender" in chars_of(s, "Wishful Merfolk").keywords
    activate(s, "Wishful Merfolk", "{1}{U}")
    answer(s)
    ch = chars_of(s, "Wishful Merfolk")
    assert set(ch.subtypes) == {"Human"} and "defender" not in ch.keywords
    check(s)
