"""Wave 30G: optional actions and resolution memory (CR 2026-09-25). Real Oracle text (tests/fixtures/wave30g_action_memory_cards.json, from
data/cards.sqlite); every scenario checks the replay and a save and a load.

What the action before the connector did is bound for what comes after it:

* 603.12: a reflexive triggered ability "when [something happens] this way" triggers on whether the event occurred earlier in the resolution of
  the spell or ability that created it, and is put on the stack (with its own targets, 603.3d) after it. It reads how many ("that many", "twice
  that much", "up to that many target …": the Augusta, Borborygmos and Fblthp, Nyssa of Traken rulings) and the object itself ("the exiled
  card's mana value": the Hidetsugu and Cait Sith rulings; a card in exile is a new object there, 400.7j; X in a mana cost is 0 anywhere but on
  the stack, 202.3e) — also after "you may discard / sacrifice any number of …. When you do, …" (Miasma Demon, Swashbuckler Extraordinaire).
* 118.12 + 608.2c/h: "If you do" after a counted action ("any number of …") and its "that many / that much" are what was done — the Neheb
  ruling of 2019-05-03: the cards discarded, not the combat damage; "You may draw cards equal to X. If you do, discard that many cards": the
  number the draw was worked out to (Horrid Shadowspinner's ruling), chosen even when X is 0 (Champion of Wits's ruling).
* 603.12 after "Create a token.": once for each token made (the Ajani, Nacatl Avenger ruling), about that very token (Dáin Ironfoot attaches
  the Axe it made); 608.2h after "Sacrifice a creature.": its last known information (Tip the Scales ruling of 2025-04-04), a token or a
  commander sent to the command zone (903.9a) included.
* 118.12 with a probe: "you may have target player lose 3 life. If you do, …" (Ob Nixilis) and "you may tap it. When you do, …" (The Fire
  Nation Drill): chosen, unless it can't be paid (119.8, 614.17b: a life total that can't change; 701.26a, 118.3: only an untapped permanent
  can be tapped).
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
    real("Probe Arbor", "", 0, "Land Creature — Forest Dryad", "", ("1", "1"), "G"),
]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


FULL = ["Hidetsugu, Devouring Chaos", "Augusta, Order Returned", "Cait Sith, Fortune Teller", "Agatha's Soul Cauldron", "Borborygmos and Fblthp",
        "Old Rutstein", "Neheb, Dreadhorde Champion", "Dáin Ironfoot", "Eastfarthing Farmer", "Tip the Scales", "Nyssa of Traken",
        "Seasoned Cryomancer", "Miasma Demon", "Swashbuckler Extraordinaire", "Loamcrafter Faun", "Scapeshift", "Last-Ditch Effort",
        "Mana Seism", "Nantuko Cultivator", "Rites of Spring", "Horrid Shadowspinner", "Katara, Waterbending Master", "Champion of Wits",
        "Armor Wars", "Ob Nixilis, the Fallen", "The Fire Nation Drill", "Gitaxian Anatomist"]


@pytest.mark.parametrize("name", FULL)
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
    s = build(cards, ["Dáin Ironfoot", "Grizzly Bears", "Lightning Bolt"])
    bears = put(s, "Grizzly Bears")
    old = token_of(s, "p1", "Axe", "Token Artifact — Equipment", "0/0", 'Equipped creature gets +1/+0.\nEquip {2}')
    to_hand(s, "Lightning Bolt")  # (an instant to cast keeps priority with its controller while the reflexive ability waits)
    dain = to_hand(s, "Dáin Ironfoot")
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=dain.id)
    pick(s, "choose_one", bears.id)  # the reflexive ability is on the stack, targeting the Bears
    assert s.state.zones.get("stack")
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
    if fodder == "commander":
        assert zone_of(s, "Krenko, Mob Boss") == "p1:command"  # (903.9a: it went to the command zone; the ability still read it on the battlefield)
    check(s)


# -- "If a noncreature, nonland card is milled this way, …": a kind written with a comma (Old Rutstein) ------------------------------
@pytest.mark.parametrize(("top", "token"), [("Lightning Bolt", ["Blood"]), ("Probe Plains", ["Treasure"]), ("Grizzly Bears", ["Insect"]),
                                            ("Probe Arbor", ["Insect", "Treasure"])])
def test_old_rutstein_makes_the_token_for_the_kind_of_card_it_milled(cards, top, token):
    """608.2c: the three "If a … card is milled this way" sentences each look at the one card milled; "noncreature, nonland" is one kind; a
    card that is both a land and a creature (Dryad Arbor: the Old Rutstein ruling of 2021-11-19) gets both tokens."""
    s = build(cards, ["Old Rutstein", top])
    stack_top(s, [top])
    rutstein = to_hand(s, "Old Rutstein")
    mana(s, B=1, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=rutstein.id)
    answer(s)
    assert zone_of(s, top) == "p1:graveyard"
    made = sorted(c.name for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield")
    assert made == token, made
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


def has_double_strike(s, c):
    from app.rules.plan import Plan

    return "double strike" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords


# -- "you may sacrifice one or more Treasures. When you do, up to that many target creatures gain double strike" (Swashbuckler Extraordinaire) --
@pytest.mark.parametrize("sacrificed", [2, 1])
def test_swashbuckler_gives_double_strike_to_up_to_as_many_creatures_as_treasures_sacrificed(cards, sacrificed):
    """118.12 + 603.12: "one or more" is a choice of how many (some, or none at all); the reflexive ability's "up to that many" is that number."""
    s = build(cards, ["Swashbuckler Extraordinaire", "Grizzly Bears"])
    swash = put(s, "Swashbuckler Extraordinaire")
    bears = put(s, "Grizzly Bears")
    ready(s, "Grizzly Bears")
    for _ in range(2):
        token_of(s, "p1", "Treasure", "Token Artifact — Treasure", "0/0", "{T}, Sacrifice this token: Add one mana of any color.")
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    pick(s, "confirm", "yes")
    pick(s, "choose_cards", *[c.id for c in treasures[:sacrificed]])
    d = pick(s, "choose_cards", *[bears.id, swash.id][:sacrificed])
    assert d.max_choices == sacrificed
    answer(s)
    assert has_double_strike(s, bears) and has_double_strike(s, swash) == (sacrificed == 2)
    check(s)


# -- "you may discard one or more land cards. When you do, return up to that many target nonland permanent cards from your graveyard" ------
def test_loamcrafter_faun_returns_up_to_as_many_nonland_cards_as_lands_discarded(cards):
    s = build(cards, ["Loamcrafter Faun", "Probe Plains", "Probe Plains", "Grizzly Bears", "Llanowar Elves", "Sol Ring", "Lightning Bolt"])
    lands = [to_hand(s, "Probe Plains"), next(c for c in s.state.cards.values() if c.name == "Probe Plains" and c.zone == "p1:library")]
    act(s, "p1", type="move", card_ids=[lands[1].id], to={"zone": "hand"})
    dead = [card_named(s, n) for n in ("Grizzly Bears", "Llanowar Elves", "Sol Ring")]
    for c in dead + [card_named(s, "Lightning Bolt")]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    faun = to_hand(s, "Loamcrafter Faun")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=faun.id)
    pick(s, "confirm", "yes")
    pick(s, "choose_cards", *[c.id for c in lands])
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards" and d.max_choices == 2 and len(d.options) == 3  # (three permanent cards offered, the Bolt isn't one)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[c.id for c in dead[:2]])
    answer(s)
    assert sum(s.state.cards[c.id].zone == "p1:hand" for c in dead) == 2
    check(s)


# -- "You may draw cards equal to X. If you do, discard that many cards / a card": chosen, and the number it was worked out to (118.12) ------
def attack_with(s, name):
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, name).id, "target": "p2"}])


@pytest.mark.parametrize("counters_on_it", [2, 0])
def test_horrid_shadowspinner_discards_as_many_cards_as_its_power_drew(cards, counters_on_it):
    """118.12 + the Horrid Shadowspinner ruling of 2024-06-07: "that many" is its power when the draw was chosen (worked out once, 608.2h) -
    a 4/4 with two +1/+1 counters draws four and discards four, a plain one three and three."""
    s = build(cards, ["Horrid Shadowspinner", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Sol Ring", "Arcane Signet", "Opt"])
    shadow = put(s, "Horrid Shadowspinner")
    ready(s, "Horrid Shadowspinner")
    if counters_on_it:
        act(s, "p1", type="counter", card_ids=[shadow.id], kind="+1/+1", delta=counters_on_it)
    power = pt(s, "Horrid Shadowspinner")[0]
    for name in ("Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Sol Ring"):
        to_hand(s, name)  # (a hand to choose the discards from)
    before = len(s.state.zones["p1:hand"])
    attack_with(s, "Horrid Shadowspinner")
    pick(s, "confirm", "yes")
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_cards"  # (the discard of that many)
    assert d.min_choices == d.max_choices == power
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:power])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == before and len(s.state.zones["p1:graveyard"]) == power
    check(s)


@pytest.mark.parametrize("experience", [2, 0])
def test_katara_discards_a_card_once_she_chose_to_draw(cards, experience):
    """118.12: "If you do" asks whether you chose to draw ("regardless of what events actually occurred"; Champion of Wits's ruling: "if you
    use the ability, you discard … regardless of how many cards you draw"): with no experience counters that is a draw of none and a discard."""
    s = build(cards, ["Katara, Waterbending Master", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt"])
    put(s, "Katara, Waterbending Master")
    ready(s, "Katara, Waterbending Master")
    held = to_hand(s, "Lightning Bolt")
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Llanowar Elves")
    if experience:
        act(s, "p1", type="resource", player="p1", key="experience", delta=experience)
    attack_with(s, "Katara, Waterbending Master")
    pick(s, "confirm", "yes")
    d = pick(s, "choose_cards", held.id)  # (the one card discarded)
    assert d.min_choices == d.max_choices == 1
    answer(s)
    assert s.state.cards[held.id].zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == 3 + experience - 1  # (three in hand, one drawn for each experience counter, one discarded)
    check(s)


# -- "you may have target player lose 3 life. If you do, put three +1/+1 counters on ~" (Ob Nixilis, the Fallen) ----------------------------
@pytest.mark.parametrize(("locked", "counters_put"), [(False, 3), (True, 0)])
def test_ob_nixilis_the_fallen_grows_only_if_the_loss_could_be_chosen(cards, locked, counters_put):
    """118.12: "If you do" asks whether the player chose to have the target lose life ("regardless of what events actually occurred"); but a
    life total that can't change makes the loss impossible, so it can't be chosen (119.8, 614.17b): Platinum Emperion keeps both the life and the counters."""
    s = build(cards, ["Ob Nixilis, the Fallen"], ["Platinum Emperion"])
    ob = put(s, "Ob Nixilis, the Fallen")
    if locked:
        put(s, "Platinum Emperion", "p2")
    land = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=land.id)
    pick(s, "choose_one", "p2")  # (the target, as the landfall ability goes on the stack)
    pick(s, "confirm", "yes")  # (the "may", as it resolves)
    answer(s)
    assert life(s, "p2") == (40 if locked else 37) and counters(s, ob) == counters_put
    check(s)


# -- "When this enters, you may tap it. When you do, destroy target creature with power 4 or less" (The Fire Nation Drill) -----------------
def drill(cards):
    s = build(cards, ["The Fire Nation Drill"], ["Probe Three", "Twisted Abomination"])
    put(s, "Probe Three", "p2")
    put(s, "Twisted Abomination", "p2")  # (power 5: not a legal target)
    spell = to_hand(s, "The Fire Nation Drill")
    mana(s, B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    return s


@pytest.mark.parametrize("taps", [True, False])
def test_fire_nation_drill_destroys_only_if_it_was_tapped_for_it(cards, taps):
    """603.12 + 118.12: "When you do" is that the player chose to tap it: then a creature with power 4 or less is destroyed (the 5-power one is
    not even a legal target); declining taps nothing and triggers nothing."""
    s = drill(cards)
    three, big = card_named(s, "Probe Three", "p2"), card_named(s, "Twisted Abomination", "p2")
    pick(s, "confirm", "yes" if taps else "no")
    if taps:
        d = s.state.rules.decision
        assert d is not None and [o.id for o in d.options] == [three.id]  # (power 4 or less: not the 5/3)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[three.id])
    answer(s)
    assert s.state.cards[card_named(s, "The Fire Nation Drill").id].tapped is taps
    assert s.state.cards[three.id].zone == ("p2:graveyard" if taps else "p2:battlefield") and s.state.cards[big.id].zone == "p2:battlefield"
    check(s)


# -- "{T}: Exile target card from a graveyard. When a creature card is exiled this way, put a +1/+1 counter on target creature you control" ---
@pytest.mark.parametrize(("exiled", "counter"), [("Llanowar Elves", 1), ("Lightning Bolt", 0)])
def test_agatha_soul_cauldron_grows_a_creature_only_for_a_creature_card_exiled(cards, exiled, counter):
    """603.12: the singular "a creature card is exiled this way" is the one card this target named, judged where it went (a card in exile)."""
    s = build(cards, ["Agatha's Soul Cauldron", "Grizzly Bears"], [exiled])
    bears = put(s, "Grizzly Bears")
    cauldron = put(s, "Agatha's Soul Cauldron")
    target = card_named(s, exiled, "p2")
    act(s, "p2", type="move", card_ids=[target.id], to={"player": "p2", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=cauldron.id, ability=ability_index(s, cauldron, "Exile target card"), targets=[target.id])
    answer(s, bears.id)
    assert s.state.cards[target.id].zone == "p2:exile" and counters(s, bears) == counter
    check(s)


# -- "you may pay {2}. When you do, that creature deals damage equal to its power to target creature" (Halana, Kessig Ranger) ------------
def halana(cards, creature="Grizzly Bears", counters_first=0):
    """Halana's trigger for ``creature`` entering; p1 and p2 each hold a Lightning Bolt (so the reflexive ability waits on the stack for them)."""
    s = build(cards, ["Halana, Kessig Ranger", creature, "Lightning Bolt"], ["Probe Three", "Lightning Bolt"])
    put(s, "Halana, Kessig Ranger")
    three = put(s, "Probe Three", "p2")
    to_hand(s, "Lightning Bolt")
    bolt = to_hand(s, "Lightning Bolt", "p2")
    spell = to_hand(s, creature) if creature != "Krenko, Mob Boss" else card_named(s, creature)
    mana(s, R=3, G=1, C=4)
    mana(s, "p2", R=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    if counters_first:  # (it is a 3/3 before it can be paid for: the trigger has resolved as far as the question)
        while s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
        act(s, "p1", type="counter", card_ids=[spell.id], kind="+1/+1", delta=counters_first)
    return s, spell, three, bolt


@pytest.mark.parametrize(("pay", "counter", "dies"), [("yes", 0, False), ("yes", 1, True), ("no", 0, False)])
def test_halana_the_creature_that_entered_deals_damage_equal_to_its_power(cards, pay, counter, dies):
    """603.12 / 603.7c: "that creature" in the reflexive ability is the one the trigger was about, read as it resolves: the 2/2 Bears hurts
    the 1/3 for 2 (it lives), but a +1/+1 counter put on it with the ability on the stack makes it 3 (it dies); not paying: no reflexive ability."""
    s, bears, three, _ = halana(cards)
    pick(s, "choose_one", "pay" if pay == "yes" else "decline")
    if pay == "yes":
        pick(s, "choose_one", three.id)
        assert s.state.zones.get("stack")
    if counter:
        act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=counter)
    answer(s)
    assert s.state.cards[three.id].zone == ("p2:graveyard" if dies else "p2:battlefield")
    assert dies or s.state.cards[three.id].damage == (2 if pay == "yes" else 0)
    check(s)


@pytest.mark.parametrize("creature", ["Grizzly Bears", "Krenko, Mob Boss"])
def test_halana_a_creature_gone_before_the_ability_resolves_still_deals_its_last_known_power(cards, creature):
    """608.2h + 903.9a: the creature died (a commander to the command zone) with the reflexive ability on the stack: the damage is its last
    known power (the Bears with a counter, 3 — its printed 2 would not kill; Krenko, 3), so the 1/3 dies."""
    s, spell, three, bolt = halana(cards, creature, counters_first=1 if creature == "Grizzly Bears" else 0)
    pick(s, "choose_one", "pay")
    pick(s, "choose_one", three.id)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[spell.id])
    answer(s)
    assert s.state.cards[three.id].zone == "p2:graveyard"
    assert s.state.cards[spell.id].zone == ("p1:command" if creature == "Krenko, Mob Boss" else "p1:graveyard")
    check(s)


@pytest.mark.parametrize("pay", ["pay", "decline"])
def test_anointer_of_valor_puts_the_counter_on_the_attacker_not_on_itself(cards, pay):
    """603.12 / 603.7c: "that creature" is the attacking Bears the trigger is about (the Anointer, which stays home, gets nothing)."""
    s = build(cards, ["Anointer of Valor", "Grizzly Bears"])
    anointer, bears = put(s, "Anointer of Valor"), put(s, "Grizzly Bears")
    ready(s, "Grizzly Bears")
    act(s, "p1", type="pass_priority")  # -> declare attackers (mana left over from the main phase would be gone)
    mana(s, C=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
    pick(s, "choose_one", pay)
    answer(s)
    assert counters(s, bears) == (1 if pay == "pay" else 0) and counters(s, anointer) == 0
    check(s)


@pytest.mark.parametrize("name", ["Halana, Kessig Ranger", "Anointer of Valor", "Ancestral Katana"])
def test_coverage_full_trigger_event_kept(cards, name):
    """The same memory in "Whenever a creature attacks, you may pay {3}. When you do, put a +1/+1 counter on that creature" and "… attach this
    Equipment to it": the creature the trigger is about."""
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"
