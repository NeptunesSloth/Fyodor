"""Wave 30G: optional actions and resolution memory (CR 2026-09-25). Real Oracle text (tests/fixtures/wave30g_action_memory_cards.json, from
data/cards.sqlite); every scenario checks the replay and a save and a load.

* 603.12: a reflexive triggered ability "when [something happens] this way" triggers on whether the event occurred earlier in the resolution
  of the spell or ability that created it, and is put on the stack (with its own targets, 603.3d) after it. It reads what the instruction did:
  how many ("that many", the Augusta ruling of 2026-03-20) and the object itself ("the exiled card's mana value", the Hidetsugu and Cait Sith
  rulings; a card in exile is a new object there, 400.7j; X in a mana cost is 0 anywhere but on the stack, 202.3e / 107.3b).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of
from tests.test_rules_wave7b_activation import ability_index
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30g_action_memory_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w30g", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN] + [
    real("Probe Fireball", "{X}{R}", 1, "Sorcery", "Probe Fireball deals X damage to any target.", None, "R"),
    real("Probe Plains", "", 0, "Basic Land — Plains", "({T}: Add {W}.)", None),
    real("Probe Wall", "{3}", 3, "Creature — Wall", "", ("0", "4")),
    real("Probe Three", "{2}{R}", 3, "Creature — Beast", "", ("1", "3"), "R"),
]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Hidetsugu, Devouring Chaos", "Augusta, Order Returned", "Cait Sith, Fortune Teller",
                                  "Agatha's Soul Cauldron", "Borborygmos and Fblthp", "Old Rutstein", "Neheb, Dreadhorde Champion",
                                  "Dáin Ironfoot", "Eastfarthing Farmer", "Tip the Scales"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_generous_plunderer_reflexive_line_is_read(cards):
    """(Its other line, damage by the defending player's artifacts, is not this wave's.)"""
    c = coverage.of_card_data(cards.resolve("Generous Plunderer"))
    assert [f.supported for f in c.features if f.id == "text:1"] == [True]


def counters(s, c, kind="+1/+1"):
    return s.state.cards[c.id].counters.get(kind, 0)


def answer(s, *prefer, limit=40):
    """Resolve everything; a choice is answered with ``prefer`` (when offered) or its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o for o in prefer if o in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def pick(s, kind, *ids, limit=20):
    """Pass priority until a decision of this kind is pending, then answer it with exactly these options (none: ``()``)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            assert d.kind == kind, (d.kind, d.prompt)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision came up")


def ready(s, *names, pid="p1"):
    for n in names:
        s.state.rules.controlled_since[card_named(s, n, pid).id].turn = 0


def stack_top(s, names, pid="p1"):
    """Put these cards on top of the library, the first named on top."""
    for name in reversed(names):
        act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"player": pid, "zone": "library"}, position="top")


def zone_of(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


# -- exile the top card, "When you exile a nonland card this way": the card's mana value (Hidetsugu) ----------------------------
def hidetsugu(cards, top):
    s = build(cards, ["Hidetsugu, Devouring Chaos", top], ["Llanowar Elves"])
    stack_top(s, [top])
    put(s, "Hidetsugu, Devouring Chaos")
    ready(s, "Hidetsugu, Devouring Chaos")
    mana(s, R=1, C=2)
    ch = card_named(s, "Hidetsugu, Devouring Chaos")
    act(s, "p1", type="activate_ability", card_id=ch.id, ability=ability_index(s, ch, "Exile the top card"))
    return s


def test_hidetsugu_deals_damage_equal_to_the_exiled_cards_mana_value(cards):
    """603.12 / the Hidetsugu ruling: the exiled nonland card's mana value (Grizzly Bears, 2) sizes the reflexive ability's damage."""
    s = hidetsugu(cards, "Grizzly Bears")
    answer(s, "p2")
    assert zone_of(s, "Grizzly Bears") == "p1:exile" and life(s, "p2") == 38
    check(s)


def test_hidetsugu_a_land_exiled_triggers_nothing(cards):
    """"When you exile a nonland card this way": a land card doesn't trigger it (the qualifier is read from the card where it went)."""
    s = hidetsugu(cards, "Probe Plains")
    answer(s, "p2")
    assert zone_of(s, "Probe Plains") == "p1:exile" and life(s, "p2") == 40 and not s.state.zones.get("stack")
    check(s)


def test_hidetsugu_x_in_the_mana_cost_of_the_exiled_card_is_zero(cards):
    """202.3e: X is 0 anywhere but on the stack: Probe Fireball ({X}{R}) in exile has mana value 1."""
    s = hidetsugu(cards, "Probe Fireball")
    answer(s, "p2")
    assert zone_of(s, "Probe Fireball") == "p1:exile" and life(s, "p2") == 39
    check(s)


# -- "each player exiles a card from their graveyard. When one or more nonland cards are exiled this way": how many (Augusta) -------
def augusta(cards, mine, theirs):
    s = build(cards, ["Augusta, Order Returned", mine], [theirs])
    put(s, "Augusta, Order Returned")
    ready(s, "Augusta, Order Returned")
    for who, name in (("p1", mine), ("p2", theirs)):
        act(s, who, type="move", card_ids=[card_named(s, name, who).id], to={"player": who, "zone": "graveyard"})
    act(s, "p1", type="pass_priority")  # -> declare attackers
    assert s.state.rules.decision.kind == "declare_attackers"
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Augusta, Order Returned").id, "target": "p2"}])
    answer(s)
    return s


@pytest.mark.parametrize(("theirs", "n"), [("Llanowar Elves", 2), ("Probe Plains", 1)])
def test_augusta_puts_a_counter_for_each_nonland_card_exiled(cards, theirs, n):
    """603.12 / the Augusta ruling: each player exiles one card, all at once; the reflexive ability counts the nonland ones ("that many")."""
    s = augusta(cards, "Grizzly Bears", theirs)
    assert zone_of(s, "Grizzly Bears") == "p1:exile" and zone_of(s, theirs, "p2") == "p2:exile"
    assert counters(s, card_named(s, "Augusta, Order Returned")) == n
    check(s)


def test_augusta_only_lands_exiled_triggers_nothing(cards):
    s = augusta(cards, "Probe Plains", "Probe Plains")
    assert zone_of(s, "Probe Plains") == "p1:exile" and counters(s, card_named(s, "Augusta, Order Returned")) == 0
    check(s)


# -- "you may discard any number of land cards. When you discard one or more cards this way, … twice that much damage" (Borborygmos) --
def borborygmos(cards):
    s = build(cards, ["Borborygmos and Fblthp", "Probe Plains", "Probe Plains", "Probe Plains"], ["Probe Wall"])
    stack_top(s, ["Probe Plains"])  # (drawn by the ability itself)
    put(s, "Probe Wall", "p2")
    to_hand(s, "Probe Plains")
    b = to_hand(s, "Borborygmos and Fblthp")
    mana(s, G=1, U=1, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=b.id)
    return s


@pytest.mark.parametrize("discarded", [2, 1])
def test_borborygmos_deals_twice_the_number_of_lands_discarded(cards, discarded):
    """603.12 / the Borborygmos and Fblthp ruling: the reflexive ability is a second trigger, targeted as it goes on the stack, and
    "twice that much" is twice the cards discarded: two lands, four damage (the 0/4 Wall dies); one land, two (it lives)."""
    s = borborygmos(cards)
    wall = card_named(s, "Probe Wall", "p2")
    pick(s, "confirm", "yes")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and len(d.options) == 2  # (the draw came first: two lands in hand)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:discarded])
    answer(s, wall.id)
    assert len([c for c in s.state.cards.values() if c.name == "Probe Plains" and c.zone == "p1:graveyard"]) == discarded
    assert (s.state.cards[wall.id].zone == "p2:graveyard") if discarded == 2 else (s.state.cards[wall.id].damage == 2)
    check(s)


def test_borborygmos_discarding_nothing_is_no_trigger(cards):
    s = borborygmos(cards)
    wall = card_named(s, "Probe Wall", "p2")
    pick(s, "confirm", "yes")
    pick(s, "choose_cards")
    answer(s, wall.id)
    assert s.state.cards[wall.id].damage == 0 and not s.state.zones.get("stack")
    check(s)


# -- "scry 1, then exile the top card. … When you exile a card this way, target creature you control gets +X/+0, where X is that card's mana value" --
def test_cait_sith_pumps_by_the_mana_value_of_the_card_it_exiled(cards):
    """603.12 / the Cait Sith ruling: X is worked out once, as the reflexive ability resolves, from the exiled card (Grizzly Bears, 2)."""
    s = build(cards, ["Cait Sith, Fortune Teller", "Grizzly Bears"])
    stack_top(s, ["Grizzly Bears"])
    put(s, "Cait Sith, Fortune Teller")
    assert pt(s, "Cait Sith, Fortune Teller") == (3, 3)
    act(s, "p1", type="pass_priority")  # -> beginning of combat: the trigger
    seen = []
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None:
            seen.append(d.kind)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])  # (scry: keep it on top)
        elif s.state.zones.get("stack"):
            if pt(s, "Cait Sith, Fortune Teller")[0] > 3:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert zone_of(s, "Grizzly Bears") == "p1:exile"
    assert pt(s, "Cait Sith, Fortune Teller") == (5, 3), seen
    check(s)


# -- "you may discard any number of cards. If you do, draw that many cards and add that much {R}" (Neheb) -------------------------
def neheb(cards, discard):
    s = build(cards, ["Neheb, Dreadhorde Champion", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt"])
    put(s, "Neheb, Dreadhorde Champion")
    ready(s, "Neheb, Dreadhorde Champion")
    held = [to_hand(s, n) for n in ("Grizzly Bears", "Llanowar Elves", "Lightning Bolt")]
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Neheb, Dreadhorde Champion").id, "target": "p2"}])
    pick(s, "choose_cards", *[c.id for c in held[:discard]])
    return s, held


@pytest.mark.parametrize("discard", [2, 0])
def test_neheb_draws_and_adds_as_many_as_it_discarded_not_as_much_as_it_dealt(cards, discard):
    """118.12 + the Neheb ruling of 2019-05-03: "that many" and "that much" are the cards discarded (2), not the combat damage dealt (5) or
    the cards drawn; choosing none does nothing."""
    s, held = neheb(cards, discard)
    answer(s)
    assert life(s, "p2") == 35  # (Neheb dealt 5)
    assert sum(1 for c in held if s.state.cards[c.id].zone == "p1:graveyard") == discard
    assert s.state.players["p1"].mana.get("R", 0) == discard
    hand = [c for c in s.state.zones["p1:hand"]]
    assert len(hand) == 3 - discard + discard  # (the cards drawn replace the ones discarded)
    check(s)


# -- "Create a [token]. When you do, …": the reflexive ability reads the token that was created (Dáin Ironfoot, Eastfarthing Farmer) ----
def axes(s):
    return [c for c in s.state.cards.values() if c.name == "Axe" and c.zone == "p1:battlefield"]


def test_dain_attaches_the_axe_he_just_made_not_another_one(cards):
    """603.12 + the rulings of Eastfarthing Farmer / Ratonhnhaké꞉ton ("triggers when you create a … token this way"): "it" in "attach it to
    target creature you control" is the token this very ability made (a new object, 400.7), though another Axe is already in play."""
    s = build(cards, ["Dáin Ironfoot", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    old = token_of(s, "p1", "Axe", "Token Artifact — Equipment", "0/0", 'Equipped creature gets +1/+0.\nEquip {2}')
    dain = to_hand(s, "Dáin Ironfoot")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=dain.id)
    answer(s, bears.id)
    new = [c for c in axes(s) if c.id != old.id]
    assert len(new) == 1 and s.state.cards[new[0].id].attached_to == bears.id and s.state.cards[old.id].attached_to is None
    assert pt(s, "Grizzly Bears") == (3, 2)
    check(s)


def test_dain_the_axe_gone_before_the_reflexive_ability_resolves_attaches_nothing(cards):
    """400.7: a token that left the battlefield is not the object the ability knows; the other Axe stays where it is."""
    s = build(cards, ["Dáin Ironfoot", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    old = token_of(s, "p1", "Axe", "Token Artifact — Equipment", "0/0", 'Equipped creature gets +1/+0.\nEquip {2}')
    dain = to_hand(s, "Dáin Ironfoot")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=dain.id)
    pick(s, "choose_one", bears.id)  # the reflexive ability is on the stack, targeting the Bears
    new = next(c for c in axes(s) if c.id != old.id)
    act(s, "p1", type="move", card_ids=[new.id], to={"player": "p1", "zone": "graveyard"})  # (the new Axe is gone)
    answer(s)
    assert s.state.cards[old.id].attached_to is None and pt(s, "Grizzly Bears") == (2, 2)
    check(s)


@pytest.mark.parametrize("doubled", [False, True])
def test_eastfarthing_farmer_triggers_once_for_each_token_made(cards, doubled):
    """603.12a + the Ajani, Nacatl Avenger ruling: a Doubling Season makes two Food tokens, so the reflexive ability triggers twice; each gives
    +1/+1 for each Food (2 of them): +2/+2, then +2/+2 again."""
    s = build(cards, ["Eastfarthing Farmer", "Doubling Season", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    if doubled:
        put(s, "Doubling Season")
    farmer = to_hand(s, "Eastfarthing Farmer")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=farmer.id)
    answer(s, bears.id)
    foods = [c for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield"]
    assert len(foods) == (2 if doubled else 1)
    assert pt(s, "Grizzly Bears") == ((2 + 2 * 2, 2 + 2 * 2) if doubled else (3, 3))
    check(s)


# -- "Sacrifice a creature. When you do, all creatures get -X/-X, where X is the sacrificed creature's toughness" (Tip the Scales) -------
def tip_the_scales(cards, counters_on_it):
    s = build(cards, ["Tip the Scales", "Grizzly Bears"], ["Probe Three", "Probe Wall"])
    bears = put(s, "Grizzly Bears")
    if counters_on_it:
        act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=counters_on_it)
    put(s, "Probe Three", "p2")
    put(s, "Probe Wall", "p2")
    tip = to_hand(s, "Tip the Scales")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=tip.id)
    answer(s)
    return s


@pytest.mark.parametrize(("counters_on_it", "three_dies"), [(1, True), (0, False)])
def test_tip_the_scales_reads_the_sacrificed_creature_as_it_last_existed(cards, counters_on_it, three_dies):
    """603.12 / 608.2h (the Tip the Scales ruling of 2025-04-04): X is the toughness it had on the battlefield: the 2/2 Bears with a +1/+1
    counter was a 3/3 (the 1/3 dies, the 0/4 lives), while one without was a 2/2 (neither dies; its printed toughness is read, not a new object)."""
    s = tip_the_scales(cards, counters_on_it)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard"
    assert zone_of(s, "Probe Three", "p2") == ("p2:graveyard" if three_dies else "p2:battlefield")
    assert zone_of(s, "Probe Wall", "p2") == "p2:battlefield" and pt(s, "Probe Wall", "p2") == (-(3 if three_dies else 2), 4 - (3 if three_dies else 2))
    check(s)


@pytest.mark.parametrize(("fodder", "x"), [("token", 1), ("commander", 3)])
def test_tip_the_scales_a_token_or_a_commander_sent_to_the_command_zone_is_still_read_as_it_was(cards, fodder, x):
    """400.7 / 903.9a: a token ceases to exist and a commander may go to the command zone, but the ability reads what each last was on the
    battlefield: a 1/1 Goblin token (X = 1), Krenko, Mob Boss (a 3/3: X = 3, so the 1/3 dies)."""
    s = build(cards, ["Tip the Scales"], ["Probe Three"])
    if fodder == "token":
        token_of(s, "p1", "Goblin", "Token Creature — Goblin", "1/1")
    else:
        act(s, "p1", type="move", card_ids=[card_named(s, "Krenko, Mob Boss").id], to={"player": "p1", "zone": "battlefield"})
    put(s, "Probe Three", "p2")
    tip = to_hand(s, "Tip the Scales")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=tip.id)
    answer(s)
    assert zone_of(s, "Probe Three", "p2") == ("p2:graveyard" if x == 3 else "p2:battlefield")
    assert not any(c.name in ("Goblin", "Krenko, Mob Boss") and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)


# -- "If a noncreature, nonland card is milled this way, …": a kind written with a comma (Old Rutstein) ------------------------------
@pytest.mark.parametrize(("top", "token"), [("Lightning Bolt", "Blood"), ("Probe Plains", "Treasure"), ("Grizzly Bears", "Insect")])
def test_old_rutstein_makes_the_token_for_the_kind_of_card_it_milled(cards, top, token):
    """608.2c: the three "If a … card is milled this way" sentences each look at the one card milled; "noncreature, nonland" is one kind."""
    s = build(cards, ["Old Rutstein", top])
    stack_top(s, [top])
    rutstein = to_hand(s, "Old Rutstein")
    mana(s, B=1, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=rutstein.id)
    answer(s)
    assert zone_of(s, top) == "p1:graveyard"
    made = sorted(c.name for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield")
    assert made == [token], made
    check(s)


# -- "Sacrifice / discard any number of …. … that many / up to that many …": the count of what was done, not an event's amount (608.2c) ----
def on_field(s, name, n, pid="p1"):
    """``n`` different cards of this name from the library onto the battlefield."""
    found = [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:library"][:n]
    for c in found:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return found


@pytest.mark.parametrize("sacrificed", [2, 0])
def test_scapeshift_searches_for_up_to_as_many_lands_as_it_sacrificed(cards, sacrificed):
    """Scapeshift: "Search your library for up to that many land cards" - that many is the lands sacrificed, not more."""
    s = build(cards, ["Scapeshift"])
    lands = on_field(s, "Forest", 3)
    spell = to_hand(s, "Scapeshift")
    mana(s, R=1, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pick(s, "choose_cards", *[c.id for c in lands[:sacrificed]])
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.max_choices == sacrificed  # (up to that many: a search for up to 0 still happens)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:sacrificed])
    answer(s)
    fetched = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:battlefield" and c.id not in {x.id for x in lands}]
    assert sum(s.state.cards[c.id].zone == "p1:battlefield" for c in lands) == 3 - sacrificed
    assert len(fetched) == sacrificed and all(s.state.cards[c.id].tapped for c in fetched)
    check(s)


@pytest.mark.parametrize("sacrificed", [2, 0])
def test_last_ditch_effort_deals_as_much_damage_as_creatures_sacrificed(cards, sacrificed):
    s = build(cards, ["Last-Ditch Effort", "Grizzly Bears", "Llanowar Elves", "Probe Three"])
    fodder = [put(s, "Grizzly Bears"), put(s, "Llanowar Elves"), put(s, "Probe Three")]
    spell = to_hand(s, "Last-Ditch Effort")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    pick(s, "choose_cards", *[c.id for c in fodder[:sacrificed]])
    answer(s)
    assert life(s, "p2") == 40 - sacrificed
    assert sum(s.state.cards[c.id].zone == "p1:graveyard" for c in fodder) == sacrificed
    check(s)


def test_nantuko_cultivator_counters_and_cards_are_the_lands_discarded(cards):
    """"you may discard any number of land cards. Put that many +1/+1 counters on this creature and draw that many cards.\""""
    s = build(cards, ["Nantuko Cultivator", "Probe Plains", "Probe Plains", "Grizzly Bears"])
    lands = [to_hand(s, "Probe Plains") for _ in range(1)] + [c for c in s.state.cards.values() if c.name == "Probe Plains" and c.zone == "p1:library"][:1]
    for c in lands[1:]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    creature = to_hand(s, "Nantuko Cultivator")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=creature.id)
    before = len(s.state.zones["p1:hand"])
    pick(s, "confirm", "yes")
    pick(s, "choose_cards", *[c.id for c in lands])
    answer(s)
    assert counters(s, creature) == 2 and len(s.state.zones["p1:hand"]) == before - 2 + 2
    assert all(s.state.cards[c.id].zone == "p1:graveyard" for c in lands)
    check(s)


# -- "sacrifice any number of artifacts. When you sacrifice one or more artifacts this way, tap up to that many target creatures …" (Nyssa) --
@pytest.mark.parametrize("sacrificed", [2, 1])
def test_nyssa_taps_up_to_as_many_creatures_and_draws_as_many_cards_as_artifacts_sacrificed(cards, sacrificed):
    """603.12 + the Nyssa of Traken rulings: the reflexive ability is targeted as it goes on the stack, up to that many targets (fewer may be
    chosen: the cards drawn don't change), and draws that many cards: the artifacts sacrificed (2, or 1), not the targets chosen."""
    s = build(cards, ["Nyssa of Traken", "Sol Ring", "Arcane Signet", "Llanowar Elves", "Grizzly Bears", "Lightning Bolt"], ["Probe Wall", "Probe Three"])
    put(s, "Nyssa of Traken")
    ready(s, "Nyssa of Traken")
    artifacts = [put(s, "Sol Ring"), put(s, "Arcane Signet")]
    walls = [put(s, "Probe Wall", "p2"), put(s, "Probe Three", "p2")]
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Nyssa of Traken").id, "target": "p2"}])
    pick(s, "choose_cards", *[c.id for c in artifacts[:sacrificed]])
    d = pick(s, "choose_cards", walls[0].id)  # (one target, though it could be up to the number sacrificed)
    assert d.max_choices == sacrificed, d.max_choices
    for _ in range(12):  # (the draw first; then Bob, with one creature tapped, declares no blocks)
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert sum(s.state.cards[c.id].zone == "p1:graveyard" for c in artifacts) == sacrificed
    assert s.state.cards[walls[0].id].tapped and not s.state.cards[walls[1].id].tapped
    assert len(s.state.zones["p1:hand"]) == hand + sacrificed
    check(s)


@pytest.mark.parametrize(("drawn", "most"), [(("Grizzly Bears", "Llanowar Elves"), 2), (("Grizzly Bears", "Probe Plains"), 1), (("Probe Plains", "Probe Plains"), 0)])
def test_seasoned_cryomancer_counts_only_the_nonland_cards_it_discarded(cards, drawn, most):
    """603.12: "When you discard one or more nonland cards this way" - the kind is read from the cards discarded (they are in the graveyard
    now, 400.7j); "up to that many target creatures" are the nonland ones: 2, 1 or no trigger at all."""
    s = build(cards, ["Seasoned Cryomancer", *drawn], ["Probe Wall", "Probe Three"])
    stack_top(s, list(drawn))
    walls = [put(s, "Probe Wall", "p2"), put(s, "Probe Three", "p2")]
    creature = to_hand(s, "Seasoned Cryomancer")
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=creature.id)
    if most:
        d = pick(s, "choose_cards", *[w.id for w in walls[:most]])
        assert d.max_choices == most
    answer(s)
    tapped = [w for w in walls if s.state.cards[w.id].tapped]
    assert len(tapped) == most and all(s.state.cards[w.id].counters.get("stun", 0) == 1 for w in tapped)
    check(s)


# -- "you may discard any number of cards. When you do, up to that many target creatures each get -2/-2" (Miasma Demon) -------------------
@pytest.mark.parametrize("discarded", [2, 1])
def test_miasma_demon_shrinks_up_to_as_many_creatures_as_cards_discarded(cards, discarded):
    """603.12 / 118.12: "When you do" is that some were discarded; "up to that many target creatures" is the cards discarded (2, or 1), the
    targets chosen as the reflexive ability goes on the stack (603.3d)."""
    s = build(cards, ["Miasma Demon", "Grizzly Bears", "Llanowar Elves"], ["Probe Wall", "Probe Three"])
    held = [to_hand(s, "Grizzly Bears"), to_hand(s, "Llanowar Elves")]
    walls = [put(s, "Probe Wall", "p2"), put(s, "Probe Three", "p2")]
    demon = to_hand(s, "Miasma Demon")
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=demon.id)
    pick(s, "confirm", "yes")
    pick(s, "choose_cards", *[c.id for c in held[:discarded]])
    d = pick(s, "choose_cards", *[w.id for w in walls[:discarded]])
    assert d.max_choices == discarded
    answer(s)
    assert sum(s.state.cards[c.id].zone == "p1:graveyard" for c in held) == discarded
    assert pt(s, "Probe Wall", "p2") == (-2, 2)
    assert pt(s, "Probe Three", "p2") == ((-1, 1) if discarded == 2 else (1, 3))
    check(s)
