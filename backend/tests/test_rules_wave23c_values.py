"""Wave 23C: value grammar (CR 2026-09-25) — "where X is …" and the quantities the engine already evaluates.

* 107.3c / 608.2h: X defined by text is read as the instruction is carried out ("its power", "that creature's power" for the recipient of
  the counters; "the exiled card's mana value" — the one card an activation cost exiled, 118.3 / 602.2b).
* 105.1: "the number of colors that spell is"; 122.1: counters among a group of permanents; 205.3m: creatures that share a creature type
  (a changeling has every one, 702.73a); 205.3j: planeswalker types.
* 603.10a: "the power of the creature that died" (as it last existed); 120.1 / 603.2c: "the amount of damage those creatures dealt to that
  player" (the damage trigger's amount, a batch's total).
* 608.2h: "that player" in a definition is the player the sentence is about (a target player): "the number of cards in that player's
  graveyard", "the number of artifacts that player controls".
* "…, where X is …, then <next instruction>": the definition ends at ", then".

Every scenario uses real Oracle text (tests/fixtures/wave23c_cards.json, from data/cards.sqlite), checks that replaying the recorded
history reproduces the table, and that a save/load round trip keeps it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage, values
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave5j_token_copies import cast, ch, drive, find, game, mana, put, roundtrip, token

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave23c_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t23c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]
FODDER = [
    card("Probe Four", set_code="t23c", number="C90", mana_cost="{3}{G}", cmc=4.0, type_line="Creature — Beast", oracle_text="", power="4", toughness="4",
         colors=["G"], color_identity=["G"]),
    card("Probe Gold", set_code="t23c", number="C91", mana_cost="{R}{G}", cmc=2.0, type_line="Sorcery", oracle_text="You gain 1 life.",
         colors=["R", "G"], color_identity=["R", "G"]),
    card("Probe Rock", set_code="t23c", number="C93", mana_cost="{3}", cmc=3.0, type_line="Artifact", oracle_text=""),
    card("Probe Changeling", set_code="t23c", number="C92", mana_cost="{1}", cmc=1.0, type_line="Creature — Shapeshifter",
         oracle_text="Changeling (This card is every creature type.)", power="1", toughness="1", keywords=["Changeling"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *FODDER], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def evaluate(s, phrase, pid="p1", **ctx):
    v = values.parse_count(phrase, it="self")
    assert v is not None, phrase
    return values.evaluate(Plan(s.state, pid, s.cards, None), {"controller": pid, **ctx}, v)


def counters(s, c):
    return dict(s.state.cards[c.id].counters)


def unready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


# -- the recipient's own power / the card a cost exiled ---------------------------------------------------------------------------
def test_heroes_bane_puts_counters_equal_to_its_own_power(cards):
    s = game(cards, ["Heroes' Bane"])
    bane = cast(s, "Heroes' Bane", G=2, C=3)
    drive(s)
    assert counters(s, bane) == {"+1/+1": 4}  # enters with four +1/+1 counters
    mana(s, "p1", G=2, C=2)
    act(s, "p1", type="activate_ability", card_id=bane.id, ability=next(a.index for a in ch(s, bane).abilities if a.kind == "activated"))
    drive(s)
    assert counters(s, bane) == {"+1/+1": 8}  # X is its power as the ability resolves (4), put on it all at once
    roundtrip(s)


def test_souls_might_doubles_the_targets_power_in_counters(cards):
    s = game(cards, ["Soul's Might", "Probe Four"])
    probe = put(s, "Probe Four")
    cast(s, "Soul's Might", targets=[probe.id], G=1, C=4)
    drive(s)
    assert counters(s, probe) == {"+1/+1": 4} and ch(s, probe).pt == (8, 8)
    roundtrip(s)


def test_necropolis_counts_the_card_the_cost_exiled(cards):
    s = game(cards, ["Necropolis", "Probe Four", "Probe Gold"])
    wall = put(s, "Necropolis")
    probe = put(s, "Probe Four", "graveyard")
    act(s, "p1", type="activate_ability", card_id=wall.id, ability=next(a.index for a in ch(s, wall).abilities if a.kind == "activated"),
        cost_choices=[{"component": 0, "cards": [probe.id]}])
    drive(s)
    assert s.state.cards[probe.id].zone == "p1:exile"
    assert counters(s, wall) == {"+0/+1": 4}  # X = the exiled card's mana value (4)
    assert ch(s, wall).pt == (0, 5)
    roundtrip(s)


# -- colors of the spell, the damage a trigger is about, the creature that died -------------------------------------------------
def test_mana_cannons_deal_damage_for_each_color_of_the_spell(cards):
    s = game(cards, ["Mana Cannons", "Probe Gold"])
    put(s, "Mana Cannons")
    cast(s, "Probe Gold", R=1, G=1)
    drive(s, choose=lambda d: ["p2"] if "p2" in [o.id for o in d.options] else None)
    assert s.state.players["p2"].life == 38  # a red and green spell is two colors (105.1)
    roundtrip(s)


def test_deaths_presence_counts_the_power_of_the_creature_that_died(cards):
    s = game(cards, ["Death's Presence", "Probe Four", "Probe Changeling", "Murder"])
    put(s, "Death's Presence")
    four, small = put(s, "Probe Four"), put(s, "Probe Changeling")
    cast(s, "Murder", targets=[four.id], B=2, C=1)  # it dies (700.4)
    drive(s, choose=lambda d: [small.id] if small.id in [o.id for o in d.options] else None)
    assert counters(s, small) == {"+1/+1": 4}  # its power as it last existed (603.10a)
    roundtrip(s)


def attack(s, c):
    until(s, lambda s: s.state.turn.number == 1 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"}])


def test_quartzwood_crasher_makes_a_token_as_big_as_the_damage_dealt(cards):
    s = game(cards, ["Quartzwood Crasher"])
    crasher = put(s, "Quartzwood Crasher")
    unready(s, crasher)
    attack(s, crasher)
    until(s, lambda s: s.state.players["p2"].life < 40 and not s.state.zones.get("stack"), limit=60)
    assert s.state.players["p2"].life == 34
    beasts = [c for c in s.state.cards.values() if c.is_token and c.name == "Dinosaur Beast"]
    assert len(beasts) == 1 and ch(s, beasts[0]).pt == (6, 6)  # X is the 6 damage the Crasher dealt to that player
    roundtrip(s)


# -- "that player": the target player's graveyard / artifacts ------------------------------------------------------------------
def test_keening_stone_mills_as_many_cards_as_the_targets_graveyard(cards):
    s = game(cards, ["Keening Stone"], ["Probe Four", "Probe Gold", "Probe Changeling"])
    stone = put(s, "Keening Stone")
    for n in ("Probe Four", "Probe Gold", "Probe Changeling"):
        put(s, n, "graveyard", pid="p2")
    before = len(s.state.zones["p2:graveyard"])
    mana(s, "p1", C=5)
    act(s, "p1", type="activate_ability", card_id=stone.id, ability=next(a.index for a in ch(s, stone).abilities if a.kind == "activated"),
        targets=["p2"])
    drive(s)
    assert before == 3 and len(s.state.zones["p2:graveyard"]) == 6  # X = 3: that player's own graveyard, not yours
    roundtrip(s)


def test_curious_herd_counts_the_artifacts_that_player_controls(cards):
    s = game(cards, ["Curious Herd"])
    for n in ("Clue A", "Clue B"):
        token(s, "p2", n, None, "Token Artifact — Clue")
    token(s, "p1", "Mine", None, "Token Artifact — Treasure")  # (yours don't count)
    cast(s, "Curious Herd", targets=["p2"], G=1, C=3)
    drive(s)
    beasts = [c for c in s.state.cards.values() if c.is_token and c.name == "Beast" and c.controller == "p1"]
    assert len(beasts) == 2
    roundtrip(s)


def test_eldritch_pact_reads_the_targets_graveyard(cards):
    s = game(cards, ["Eldritch Pact", "Probe Four"], ["Probe Four"])
    put(s, "Probe Four", "graveyard", pid="p2")
    hand = len(s.state.zones["p2:hand"])
    cast(s, "Eldritch Pact", targets=["p2"], B=1, C=6)
    drive(s)
    assert s.state.players["p2"].life == 39 and len(s.state.zones["p2:hand"]) == hand + 1  # one card in their graveyard: they draw one, lose 1
    roundtrip(s)


# -- groups: counters, shared types, power and/or toughness, planeswalker types ------------------------------------------------
def test_counters_among_permanents_you_control(cards):
    s = game(cards, ["Probe Four", "Probe Changeling"])
    a, b = put(s, "Probe Four"), put(s, "Probe Changeling")
    act(s, "p1", type="counter", card_ids=[a.id], kind="+1/+1", delta=2)
    act(s, "p1", type="counter", card_ids=[b.id], kind="time", delta=3)
    assert evaluate(s, "the number of counters on permanents you control") == 5
    assert evaluate(s, "the number of time counters among permanents you control") == 3
    assert evaluate(s, "the number of different kinds of counters among permanents you control") == 2
    assert evaluate(s, "the number of +1/+1 counters on creatures you control") == 2


def test_greatest_number_of_creatures_sharing_a_type_counts_a_changeling_for_every_type(cards):
    s = game(cards, ["Probe Four", "Probe Changeling"])
    put(s, "Probe Four")
    token(s, "p1", "Elf A", "1/1", "Token Creature — Elf Warrior")
    token(s, "p1", "Elf B", "1/1", "Token Creature — Elf Druid")
    phrase = "the greatest number of creatures you control that have a creature type in common"
    assert evaluate(s, phrase) == 2  # two Elves (the Beast is alone)
    put(s, "Probe Changeling")
    assert evaluate(s, phrase) == 3  # 702.73a: the changeling is an Elf, a Beast, a Warrior … at once
    assert evaluate(s, "the greatest power and/or toughness among creatures you control") == 4


def test_basalt_ravager_deals_damage_for_the_creatures_sharing_a_type(cards):
    s = game(cards, ["Basalt Ravager"])
    token(s, "p1", "Wizard A", "1/1", "Token Creature — Wizard")
    token(s, "p1", "Wizard B", "1/1", "Token Creature — Wizard")
    cast(s, "Basalt Ravager", R=1, C=3)
    drive(s, choose=lambda d: ["p2"] if "p2" in [o.id for o in d.options] else None)
    assert s.state.players["p2"].life == 37  # the Ravager is a Wizard too: three Wizards
    roundtrip(s)


# -- the definition ends at ", then" ------------------------------------------------------------------------------------------
def test_ugins_insight_scries_for_the_greatest_mana_value_then_draws(cards):
    s = game(cards, ["Ugin's Insight", "Probe Four"])
    put(s, "Probe Four")
    cast(s, "Ugin's Insight", U=2, C=3)
    hand = len(s.state.zones["p1:hand"])
    drive(s)
    assert len(s.state.zones["p1:hand"]) == hand + 3  # scry X (X = 4, the Beast's mana value), then the three cards
    assert find(s, "Ugin's Insight").zone == "p1:graveyard"
    roundtrip(s)


def test_find_ugins_insight_scry_amount_is_the_greatest_mana_value():
    c = next(c for c in EXTRA if c["name"] == "Ugin's Insight")
    from app.rules import scripts
    from app.rules.characteristics import printed_from_data

    d = scripts.definitions(printed_from_data({**c, "faces": []}, 0))
    scry, draw = d[0]["effects"][:2]
    assert scry["do"] == "scry" and scry["n"]["max"] == "mana_value" and draw["do"] == "draw" and draw["n"] == 3


# -- "the same name as that spell" ---------------------------------------------------------------------------------------------
def test_aven_shrine_counts_the_cards_in_all_graveyards_with_the_spells_name(cards):
    s = game(cards, ["Aven Shrine", "Probe Four", "Probe Four", "Probe Gold"], ["Probe Four"])
    put(s, "Aven Shrine")
    mine = [c for c in s.state.cards.values() if c.name == "Probe Four" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[mine[0].id], to={"player": "p1", "zone": "graveyard"})
    put(s, "Probe Four", "graveyard", pid="p2")  # (any graveyard counts)
    put(s, "Probe Gold", "graveyard")  # (another name doesn't)
    life = s.state.players["p1"].life
    act(s, "p1", type="move", card_ids=[mine[1].id], to={"player": "p1", "zone": "hand"})
    mana(s, "p1", G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=mine[1].id)
    drive(s)
    assert s.state.players["p1"].life == life + 2  # the player who cast it gains X = 2
    roundtrip(s)


def test_greatest_mana_value_among_your_commanders_looks_in_every_zone(cards):
    s = game(cards)
    assert evaluate(s, "the greatest mana value among your commanders") == 4  # Krenko, Mob Boss waits in the command zone
    krenko = find(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "graveyard"})
    assert evaluate(s, "the greatest mana value among your commanders") == 4  # 903.3: still the commander in a graveyard
    assert evaluate(s, "the greatest mana value among your commanders", pid="p2") == 4  # Atraxa, Praetors' Voice: mana value 4 as well


# -- "the mana value of the permanent exiled this way" / "the toughness of the card returned this way" ------------------------------
def test_ruinous_intrusion_counts_the_mana_value_of_what_it_exiled(cards):
    s = game(cards, ["Ruinous Intrusion", "Probe Rock", "Probe Four"])
    rock, beast = put(s, "Probe Rock"), put(s, "Probe Four")
    spell = put(s, "Ruinous Intrusion", "hand")
    mana(s, "p1", G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[rock.id, beast.id], target_counts=[1, 1])
    drive(s)
    assert s.state.cards[rock.id].zone == "p1:exile" and counters(s, beast) == {"+1/+1": 3}  # X = 3, the exiled artifact's mana value
    roundtrip(s)


def test_foul_renewal_shrinks_by_the_toughness_of_the_card_it_returned(cards):
    s = game(cards, ["Foul Renewal", "Probe Four"], ["Probe Four"])
    gone = put(s, "Probe Four", "graveyard")
    theirs = put(s, "Probe Four", "battlefield", pid="p2")
    spell = put(s, "Foul Renewal", "hand")
    mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[gone.id, theirs.id], target_counts=[1, 1])
    drive(s)
    assert s.state.cards[gone.id].zone == "p1:hand" and s.state.cards[theirs.id].zone == "p2:graveyard"  # -4/-4 (the returned card's toughness) kills it
    roundtrip(s)


# -- review (wave 23C) ---------------------------------------------------------------------------------------------------------
def test_change_of_fortune_counts_the_discards_it_just_made(cards):
    s = game(cards, ["Change of Fortune", "Probe Four", "Probe Gold"])
    put(s, "Probe Four", "hand")
    put(s, "Probe Gold", "hand")
    cast(s, "Change of Fortune", R=1, C=3)
    drive(s)
    # 608.2h: the two cards discarded earlier in this resolution count (the turn's log notes events only when triggers are checked)
    assert len(s.state.zones["p1:hand"]) == 2 and find(s, "Probe Four").zone == "p1:graveyard"
    roundtrip(s)


def test_counters_on_an_unbound_granter_stay_manual():
    # Gutter Grime's Ooze: "… equal to the number of slime counters on Gutter Grime." A token an effect created never has its
    # ‹granter› bound to an object, so the count would read 0 (and the Ooze die): the token's text stays manual.
    assert values.parse_count("the number of slime counters on ‹granter›", it="self") is None
    assert values.parse_count("the number of counters on permanents you control", it="self") is not None


@pytest.mark.parametrize("text", [
    "Exile two creature cards from your graveyard: You gain life equal to the exiled card's mana value.",  # (which one?)
    "{T}, Exile this creature: You gain life equal to the exiled card's mana value.",  # (not a card from a graveyard / hand)
    "When this creature enters, you gain life equal to the exiled card's mana value.",  # (no cost exiled anything)
])
def test_the_exiled_card_needs_exactly_one_card_a_cost_exiled_from_a_graveyard_or_hand(text):
    from tests.test_rules_wave5j_token_copies import ok

    assert not ok(text)
    assert ok("Exile a creature card from your graveyard: You gain life equal to the exiled card's mana value.")
