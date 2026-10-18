"""Wave 30R: this turn's history - counts and conditions of what left the battlefield, spells cast of a kind, who dealt the damage a
creature died of, "your team" (CR 2026-09-25), real Oracle text (tests/fixtures/wave30r_cards.json, from data/cards.sqlite). Every
scenario checks the replay and a save and a load; three players play them, so a count of "your graveyard" / "they" tells players apart.

* 700.4 / 400.7 / 608.2i: "dies" is being put into a graveyard from the battlefield and it is a fact of the past - a creature that died and
  came back is still one that died this turn, a token that died counts (it was put into the graveyard before it ceased to exist, 111.7).
  "Put into YOUR graveyard" is the owner's (400.3): a creature you stole that dies goes to its owner's graveyard.
* 601.2i / 608.2h: "the number of instant and sorcery spells you've cast this turn" counts the spells as they were cast, countered or not,
  and is read as the effect is carried out; "other" leaves out the spell that is counting; "they" is the player of the trigger.
* 603.4 / 120.3: "if Hawkeye dealt damage to it this turn" is a fact of the past, checked when the creature dies.
* 102.4: outside a team game "your team" means "you".
* 500.4 / 514: a new turn starts a new count.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import counters, settle, token_of, until
from tests.wave9c_kit import card_named, check, life, mana, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30r_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30r", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
EXTRA += [card("Probe Bear", set_code="t30r", number="R90", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Bear", colors=["G"],
               color_identity=["G"], oracle_text="", power="2", toughness="2"),
          card("Probe Elk", set_code="t30r", number="R91", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Elk", colors=["G"],
               color_identity=["G"], oracle_text="", power="2", toughness="2"),
          card("Probe Cantrip", set_code="t30r", number="R92", mana_cost="{U}", cmc=1.0, type_line="Instant", colors=["U"],
               color_identity=["U"], oracle_text="Scry 1."),
          card("Probe Study", set_code="t30r", number="R93", mana_cost="{U}", cmc=1.0, type_line="Sorcery", colors=["U"],
               color_identity=["U"], oracle_text="Scry 1."),
          card("Probe Trinket", set_code="t30r", number="R94", mana_cost="{1}", cmc=1.0, type_line="Artifact", oracle_text=""),
          card("Probe Mouse", set_code="t30r", number="R96", mana_cost="{G}", cmc=1.0, type_line="Creature — Mouse", colors=["G"],
               color_identity=["G"], oracle_text="", power="1", toughness="1"),
          card("Probe Ox", set_code="t30r", number="R98", mana_cost="{2}{G}", cmc=3.0, type_line="Creature — Ox", colors=["G"],
               color_identity=["G"], oracle_text="", power="3", toughness="3"),
          card("Probe Wrath", set_code="t30r", number="R97", mana_cost="{B}{B}", cmc=2.0, type_line="Sorcery", colors=["B"],
               color_identity=["B"], oracle_text="Destroy all creatures."),
          card("Probe Salve", set_code="t30r", number="R95", mana_cost="{W}", cmc=1.0, type_line="Instant", colors=["W"],
               color_identity=["W"], oracle_text="You gain 2 life.")]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def three(cards, alice=(), bob=(), carol=()):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in alice), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in carol), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # -> Alice's main phase
    return s


def bf(s, name, pid, controller=None):
    """Put ``name`` (owned by ``pid``) onto the battlefield under ``controller``'s control (its owner's, unless said)."""
    c = card_named(s, name, pid)
    act(s, controller or pid, type="move", card_ids=[c.id], to={"player": controller or pid, "zone": "battlefield"})
    return c


def to_turn(s, n):
    until(s, lambda s: s.state.turn.number == n and s.state.turn.phase == "main1" and s.state.rules.decision is None, limit=400)


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def ability_index(s, c, needle):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return next(a.index for a in ch.abilities if needle in a.text)


def die(s, c):
    """The creature dies: it is put into its owner's graveyard from the battlefield (700.4)."""
    act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "graveyard"})


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.is_token and c.zone.endswith(":battlefield")]


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s)


def level(name):
    from app.rules import coverage

    c = next(c for c in EXTRA if c["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


NAMES = [c["name"] for c in DATA if c["name"] != "Demilich"]  # (Demilich stays PARTIAL: its graveyard cast, "exiling four … cards", is read by hand)


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(name):
    assert level(name) == "FULL", name


# -- "for each creature put into your graveyard from the battlefield this turn" (Asmira, Holy Avenger) ------------------------------------
def test_asmira_counts_what_went_to_your_graveyard_and_starts_over_each_turn(cards):
    s = three(cards, alice=["Asmira, Holy Avenger", "Probe Bear", "Probe Elk"], bob=["Probe Bear"], carol=["Probe Elk"])
    asmira = bf(s, "Asmira, Holy Avenger", "p1")
    mine = bf(s, "Probe Bear", "p1")
    other = bf(s, "Probe Elk", "p1")
    theirs = bf(s, "Probe Bear", "p2")
    die(s, mine)
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "battlefield"})  # it came back: still one that died (400.7)
    die(s, theirs)  # Bob's creature went to BOB's graveyard: not "your graveyard"
    assert other.id in s.state.cards
    to_turn(s, 2)  # (Alice's end step: Asmira counted one)
    assert counters(s, asmira) == 1
    check(s)
    die(s, mine)  # turn 2 (Bob's): "each end step" counts Alice's graveyard again, this turn's only
    to_turn(s, 3)
    assert counters(s, asmira) == 2
    to_turn(s, 4)  # nothing died on turn 3: the count of turn 2 isn't carried over (500.4)
    assert counters(s, asmira) == 2
    check(s)


def test_asmira_counts_a_creature_you_owned_but_did_not_control(cards):
    s = three(cards, alice=["Asmira, Holy Avenger", "Probe Bear"], bob=["Probe Elk"], carol=["Probe Bear"])
    asmira = bf(s, "Asmira, Holy Avenger", "p1")
    stolen = bf(s, "Probe Bear", "p1", controller="p3")  # Alice's Bear, under Carol's control
    mine = bf(s, "Probe Elk", "p2", controller="p1")  # Bob's Elk, under Alice's control
    die(s, mine)
    die(s, stolen)  # (it goes to its owner's graveyard: Alice's)
    to_turn(s, 2)
    assert counters(s, asmira) == 1  # only the Bear: the Elk went to Bob's graveyard
    check(s)


def test_a_token_counts_as_a_creature_put_into_your_graveyard(cards):
    s = three(cards, alice=["Asmira, Holy Avenger"])
    asmira = bf(s, "Asmira, Holy Avenger", "p1")
    token = token_of(s, "p1", "Probe Goblin", "Token Creature — Goblin", "1/1")
    die(s, token)
    to_turn(s, 2)
    assert counters(s, asmira) == 1  # (Fresh Meat's ruling: creature tokens that entered under your control count)
    check(s)


# -- the same count made by spells and by a nontoken-only wording (Fresh Meat, Caller of the Claw, Urborg Justice) -------------------------
def test_fresh_meat_counts_tokens_and_owned_creatures_caller_of_the_claw_only_nontoken(cards):
    s = three(cards, alice=["Fresh Meat", "Caller of the Claw", "Probe Bear", "Probe Elk"], bob=["Probe Bear"])
    mine, stolen = bf(s, "Probe Bear", "p1"), bf(s, "Probe Elk", "p1", controller="p2")
    token = token_of(s, "p1", "Probe Goblin", "Token Creature — Goblin", "1/1")
    theirs = bf(s, "Probe Bear", "p2")
    for c in (mine, stolen, token, theirs):
        die(s, c)  # Alice's graveyard: the Bear, the Elk (hers, under Bob's control) and a token; Bob's Bear went to Bob's
    to_hand(s, "Caller of the Claw")
    mana(s, "p1", G=3)
    cast(s, "Caller of the Claw")  # "for each NONTOKEN creature put into your graveyard from the battlefield this turn": the Bear and the Elk
    assert len(tokens(s, "Bear")) == 2
    check(s)
    to_hand(s, "Fresh Meat")
    mana(s, "p1", G=4)
    cast(s, "Fresh Meat")  # three creatures of Alice's (two cards, one token): three 3/3 Beasts
    assert len(tokens(s, "Beast")) == 3
    check(s)


def test_urborg_justice_makes_the_target_sacrifice_one_for_each(cards):
    s = three(cards, alice=["Urborg Justice", "Probe Bear", "Probe Elk"], bob=["Probe Bear", "Probe Elk", "Probe Mouse"])
    for n in ("Probe Bear", "Probe Elk"):
        die(s, bf(s, n, "p1"))
    for n in ("Probe Bear", "Probe Elk", "Probe Mouse"):
        bf(s, n, "p2")
    to_hand(s, "Urborg Justice")
    mana(s, "p1", B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Urborg Justice").id, targets=["p2"])
    settle(s)
    assert len([c for c in s.state.cards.values() if c.owner == "p2" and c.zone == "p2:battlefield"]) == 1
    check(s)


# -- "nontoken creature you controlled that died this turn" (Tobias, Doomed Conqueror) ----------------------------------------------------
def test_tobias_counts_the_nontoken_creatures_you_controlled_as_they_died(cards):
    s = three(cards, alice=["Tobias, Doomed Conqueror", "Probe Bear", "Probe Wrath"], bob=["Probe Bear"], carol=["Probe Elk"])
    tobias = bf(s, "Tobias, Doomed Conqueror", "p1")
    bf(s, "Probe Bear", "p1")
    bf(s, "Probe Elk", "p3", controller="p1")  # Carol's, under Alice's control as it dies
    bf(s, "Probe Bear", "p2")
    token_of(s, "p1", "Probe Goblin", "Token Creature — Goblin", "1/1")
    to_hand(s, "Probe Wrath")
    mana(s, "p1", B=2)
    cast(s, "Probe Wrath")  # everything dies together: Tobias' ability looks back at them all (603.10a)
    assert tobias.id in s.state.cards and s.state.cards[tobias.id].zone == "p1:graveyard"
    assert len(tokens(s, "Zombie")) == 3  # the Bear, Carol's Elk, Tobias itself - not Bob's Bear, not the Goblin token
    check(s)


# -- "creature that left the battlefield under your control" (Kutzil's Flanker) and "put into your hand from the battlefield" (Barrin) -----------
def test_kutzils_flanker_counts_creatures_that_left_under_your_control(cards):
    s = three(cards, alice=["Kutzil's Flanker", "Probe Bear", "Probe Elk"], bob=["Probe Bear"])
    bounced, exiled = bf(s, "Probe Bear", "p1"), bf(s, "Probe Elk", "p1")
    theirs = bf(s, "Probe Bear", "p2")
    act(s, "p1", type="move", card_ids=[bounced.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[exiled.id], to={"zone": "exile"})
    act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "hand"})  # left under Bob's control: not Alice's
    to_hand(s, "Kutzil's Flanker")
    mana(s, "p1", W=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kutzil's Flanker").id)
    settle(s)  # (the first mode: a +1/+1 counter for each)
    assert counters(s, card_named(s, "Kutzil's Flanker")) == 2
    check(s)


def test_barrin_draws_once_for_a_permanent_put_into_your_hand_from_the_battlefield(cards):
    s = three(cards, alice=["Barrin, Tolarian Archmage", "Probe Bear", "Probe Elk"], bob=["Probe Bear"])
    bf(s, "Barrin, Tolarian Archmage", "p1")
    settle(s)
    for n in ("Probe Bear", "Probe Elk"):
        c = bf(s, n, "p1")
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    n = hand(s)
    to_turn(s, 2)
    assert hand(s) == n + 1  # one card, however many were put into the hand
    check(s)


def test_barrin_does_not_count_an_opponents_hand_or_a_graveyard(cards):
    s = three(cards, alice=["Barrin, Tolarian Archmage", "Probe Bear"], bob=["Probe Bear"])
    bf(s, "Barrin, Tolarian Archmage", "p1")
    settle(s)
    act(s, "p2", type="move", card_ids=[bf(s, "Probe Bear", "p2").id], to={"zone": "hand"})  # Bob's: not YOUR hand
    die(s, bf(s, "Probe Bear", "p1"))
    n = hand(s)
    to_turn(s, 2)
    assert hand(s) == n
    check(s)


# -- a land you controlled put into a graveyard from the battlefield (The Lady of Otaria) -------------------------------------------------
def test_lady_of_otaria_sees_a_land_you_controlled_go_to_a_graveyard(cards):
    s = three(cards, alice=["The Lady of Otaria", "Probe Bear"])
    bf(s, "The Lady of Otaria", "p1")
    die(s, bf(s, "Probe Bear", "p1"))  # (a creature: not a land)
    top = list(s.state.zones["p1:library"][:4])
    to_turn(s, 2)
    assert list(s.state.zones["p1:library"][:4]) == top
    check(s)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    die(s, forest)  # (turn 2: Bob's - "each end step")
    top = list(s.state.zones["p1:library"][:4])
    to_turn(s, 3)
    assert sorted(s.state.zones["p1:library"][-4:]) == sorted(top)  # revealed four, no Dwarves: they go to the bottom
    check(s)


# -- "enters with a +1/+1 counter on it for each creature that died under your control this turn" (Callous Sell-Sword) ---------------------
def test_callous_sell_sword_enters_with_a_counter_for_each_creature_that_died_under_your_control(cards):
    s = three(cards, alice=["Callous Sell-Sword // Burn Together", "Probe Bear", "Probe Elk"], bob=["Probe Bear"])
    mine = bf(s, "Probe Bear", "p1")
    token = token_of(s, "p1", "Probe Goblin", "Token Creature — Goblin", "1/1")
    theirs = bf(s, "Probe Bear", "p2")
    elk = bf(s, "Probe Elk", "p1")  # (lives)
    for c in (mine, token, theirs):
        die(s, c)
    to_hand(s, "Callous Sell-Sword // Burn Together")
    mana(s, "p1", B=2)
    cast(s, "Callous Sell-Sword // Burn Together")
    assert counters(s, card_named(s, "Callous Sell-Sword // Burn Together")) == 2  # the Bear and the token; not Bob's Bear
    assert elk.id in s.state.cards
    check(s)


# -- "the number of instant and sorcery spells you've cast this turn" (Lock and Load, Thunder Salvo, Outlaw Stitcher, Magebane Lizard) -----
def test_lock_and_load_counts_your_other_instant_and_sorcery_spells_countered_or_not(cards):
    s = three(cards, alice=["Lock and Load", "Probe Cantrip", "Probe Study", "Probe Bear"], bob=["Counterspell", "Probe Cantrip"])
    for n in ("Probe Cantrip", "Probe Study", "Probe Bear", "Lock and Load"):
        to_hand(s, n)
    mana(s, "p1", U=9, G=2)
    to_hand(s, "Counterspell", "p2")
    mana(s, "p2", U=3)
    cast(s, "Probe Bear")  # a creature spell: not an instant or sorcery
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Probe Cantrip").id)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Counterspell", "p2").id, targets=[card_named(s, "Probe Cantrip").id])
    settle(s)  # Alice's Cantrip was countered: cast all the same (601.2i). Bob's Counterspell is Bob's
    cast(s, "Probe Study")
    n = hand(s)
    cast(s, "Lock and Load")
    assert hand(s) == n - 1 + 3  # one card, and one more for each other instant / sorcery spell Alice cast: the Cantrip and the Study
    check(s)


def test_lock_and_load_alone_draws_one(cards):
    s = three(cards, alice=["Lock and Load"])
    to_hand(s, "Lock and Load")
    mana(s, "p1", U=3)
    n = hand(s)
    cast(s, "Lock and Load")
    assert hand(s) == n - 1 + 1  # (it doesn't count itself: "other")
    check(s)


@pytest.mark.parametrize(("first", "dies"), [(True, True), (False, False)])
def test_thunder_salvo_adds_the_other_spells_you_cast(cards, first, dies):
    s = three(cards, alice=["Thunder Salvo", "Probe Cantrip"], bob=["Probe Ox"])
    ox = bf(s, "Probe Ox", "p2")
    to_hand(s, "Thunder Salvo")
    mana(s, "p1", U=2, R=2)
    if first:
        to_hand(s, "Probe Cantrip")
        cast(s, "Probe Cantrip")
    cast(s, "Thunder Salvo", targets=[ox.id])  # 2 plus the number of other spells you've cast this turn: 3 damage to a 3/3, or 2
    assert (s.state.cards[ox.id].zone == "p2:graveyard") == dies
    check(s)


@pytest.mark.parametrize(("spells", "counters_on_token"), [(0, 0), (1, 2)])
def test_outlaw_stitcher_counts_the_spells_other_than_the_first(cards, spells, counters_on_token):
    s = three(cards, alice=["Outlaw Stitcher", "Probe Cantrip"])
    to_hand(s, "Outlaw Stitcher")
    mana(s, "p1", U=5)
    if spells:
        to_hand(s, "Probe Cantrip")
        cast(s, "Probe Cantrip")
    cast(s, "Outlaw Stitcher")  # the Stitcher is a spell too: with one before it, the token gets two counters for the one after the first
    zombie = tokens(s, "Zombie Rogue")
    assert len(zombie) == 1 and counters(s, zombie[0]) == counters_on_token
    check(s)


def test_magebane_lizard_hurts_each_caster_for_their_own_count_this_turn(cards):
    s = three(cards, alice=["Magebane Lizard", "Probe Cantrip", "Probe Study", "Probe Bear"], bob=["Probe Cantrip", "Probe Trinket"])
    bf(s, "Magebane Lizard", "p1")
    for n in ("Probe Cantrip", "Probe Study", "Probe Bear"):
        to_hand(s, n)
    mana(s, "p1", U=4, G=2)
    cast(s, "Probe Cantrip")
    assert life(s, "p1") == 39
    cast(s, "Probe Study")
    assert life(s, "p1") == 37  # her second noncreature spell: 2 damage
    cast(s, "Probe Bear")
    assert life(s, "p1") == 37  # a creature spell doesn't trigger it
    to_turn(s, 2)
    to_hand(s, "Probe Cantrip", "p2")
    to_hand(s, "Probe Trinket", "p2")
    mana(s, "p2", U=2, C=1)
    cast(s, "Probe Cantrip", "p2")
    assert (life(s, "p2"), life(s, "p1")) == (39, 37)  # Bob's first this turn: 1 damage to Bob - not Alice's count, not last turn's
    cast(s, "Probe Trinket", "p2")
    assert life(s, "p2") == 37
    check(s)


# -- "create X tokens that are copies of another target creature, where X is one plus the number of instant and sorcery spells you've cast" ---
def test_rionya_makes_one_copy_plus_one_for_each_instant_or_sorcery_cast(cards):
    s = three(cards, alice=["Rionya, Fire Dancer", "Probe Cantrip", "Probe Study", "Probe Bear", "Probe Elk"])
    rionya = bf(s, "Rionya, Fire Dancer", "p1")
    bear = bf(s, "Probe Bear", "p1")
    for n in ("Probe Cantrip", "Probe Study", "Probe Elk"):
        to_hand(s, n)
    mana(s, "p1", U=3, G=2)
    cast(s, "Probe Cantrip")
    cast(s, "Probe Study")
    cast(s, "Probe Elk")  # (a creature spell: not counted)
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack") and s.state.rules.decision is None, limit=60)
    assert rionya.id in s.state.cards and bear.id in s.state.cards
    assert len(tokens(s, "Probe Bear")) == 3  # one plus the Cantrip and the Study
    check(s)


@pytest.mark.parametrize(("spells", "paid"), [(0, 4), (2, 2)])
def test_demilich_costs_less_for_each_instant_and_sorcery_spell_cast_this_turn(cards, spells, paid):
    s = three(cards, alice=["Demilich", "Probe Cantrip", "Probe Study", "Probe Bear"])
    to_hand(s, "Demilich")
    to_hand(s, "Probe Bear")
    mana(s, "p1", U=8, G=2)
    cast(s, "Probe Bear")  # (a creature spell: no reduction)
    for n in ("Probe Cantrip", "Probe Study")[:spells]:
        to_hand(s, n)
        cast(s, n)
    before = s.state.players["p1"].mana.get("U", 0)
    cast(s, "Demilich")
    assert s.state.cards[card_named(s, "Demilich").id].zone == "p1:battlefield"
    assert before - s.state.players["p1"].mana.get("U", 0) == paid  # {U}{U}{U}{U}, less {U} for each instant or sorcery spell cast
    check(s)


# -- "if Hawkeye dealt damage to it this turn" (Hawkeye, Avenging Archer) ------------------------------------------------------------
def hawkeye_table(cards):
    s = three(cards, alice=["Hawkeye, Avenging Archer", "Probe Wrath", "Probe Mouse"], bob=["Probe Bear", "Probe Mouse", "Probe Wrath"], carol=["Probe Elk"])
    hawkeye = bf(s, "Hawkeye, Avenging Archer", "p1")
    s.state.rules.controlled_since[hawkeye.id].turn = 0  # (not summoning sick)
    for n, p in (("Probe Mouse", "p1"), ("Probe Bear", "p2"), ("Probe Mouse", "p2"), ("Probe Elk", "p3")):
        bf(s, n, p)
    return s, hawkeye


def ping(s, hawkeye, target):
    act(s, "p1", type="activate_ability", card_id=hawkeye.id, ability=ability_index(s, hawkeye, "deals 1 damage"), targets=[target.id])
    settle(s)


def test_hawkeye_draws_only_for_an_opponents_creature_it_damaged_this_turn(cards):
    s, hawkeye = hawkeye_table(cards)
    bear = card_named(s, "Probe Bear", "p2")
    ping(s, hawkeye, bear)  # 1 damage to Bob's Bear: it lives
    to_hand(s, "Probe Wrath")
    mana(s, "p1", B=2)
    n = hand(s)
    cast(s, "Probe Wrath")  # every creature dies together: Bob's damaged Bear, Bob's Mouse, Carol's Elk, Alice's own Mouse and Hawkeye
    assert s.state.cards[bear.id].zone == "p2:graveyard" and s.state.cards[hawkeye.id].zone == "p1:graveyard"
    assert hand(s) == n - 1 + 1  # the Wrath left the hand and one card was drawn: only the Bear was dealt damage by Hawkeye
    check(s)


def test_hawkeye_kills_a_one_toughness_creature_and_draws(cards):
    s, hawkeye = hawkeye_table(cards)
    n = hand(s)
    mouse = card_named(s, "Probe Mouse", "p2")
    ping(s, hawkeye, mouse)
    assert s.state.cards[mouse.id].zone == "p2:graveyard"
    assert hand(s) == n + 1
    check(s)


def test_hawkeye_does_not_count_damage_from_an_earlier_turn(cards):
    s, hawkeye = hawkeye_table(cards)
    bear = card_named(s, "Probe Bear", "p2")
    ping(s, hawkeye, bear)
    to_turn(s, 2)  # Bob's turn: the damage was dealt last turn
    n = hand(s)
    to_hand(s, "Probe Wrath", "p2")
    mana(s, "p2", B=2)
    cast(s, "Probe Wrath", "p2")  # the Bear dies (and Hawkeye with it): not dealt damage by Hawkeye THIS turn
    assert s.state.cards[bear.id].zone == "p2:graveyard"
    assert hand(s) == n
    check(s)


# -- "if your team gained life this turn" (Regna, the Redeemer) ----------------------------------------------------------------------
def test_regna_makes_warriors_when_you_gained_life_and_not_when_an_opponent_did(cards):
    s = three(cards, alice=["Regna, the Redeemer", "Probe Salve"], bob=["Probe Salve"])
    bf(s, "Regna, the Redeemer", "p1")
    to_hand(s, "Probe Salve")
    mana(s, "p1", W=1)
    cast(s, "Probe Salve")
    to_turn(s, 2)
    assert len(tokens(s, "Warrior")) == 2  # Alice gained life on turn 1: her end step
    to_hand(s, "Probe Salve", "p2")
    mana(s, "p2", W=1)
    cast(s, "Probe Salve", "p2")  # Bob gained life on turn 2: not Alice's team (102.4)
    to_turn(s, 4)
    assert len(tokens(s, "Warrior")) == 2  # (and turn 3 had no life gain of Alice's)
    check(s)


def test_regna_does_nothing_on_a_turn_nobody_gained_life(cards):
    s = three(cards, alice=["Regna, the Redeemer"])
    bf(s, "Regna, the Redeemer", "p1")
    to_turn(s, 2)
    assert not tokens(s, "Warrior")
    check(s)
