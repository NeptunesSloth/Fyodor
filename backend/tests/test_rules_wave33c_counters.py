"""Wave 33C: counter wordings found by taking the 292 "counters" sole-blocker lines apart (CR 122.1, 122.6, 603.2, 603.4, 614.1c, 704.5q),
real Oracle text (tests/fixtures/wave33c_counters_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* "put another / an additional +1/+1 counter on …" (Yorvo, Cursed Wombat) is putting one more counter: through the counter choke point (122.6), so
  Doubling Season and Hardened Scales apply to it as to any put.
* "put +1/+1 counters on that creature equal to its power" (Experiment Twelve): "a number of" left out.
* "if its power is less than Shelinda's power" (Shelinda, Yevon Acolyte): the comparison the other way; an equal power is the "Otherwise".
* "… enters / becomes tapped / is cast while this creature has a -1/-1 counter on it" (Bristlebane Battler, Reluctant Dounguard, Moonshadow, Encumbered
  Reejerey, Pyromancer Ascension) is part of the trigger event (603.2), looked at as the event happens: no second look on resolution (603.4 is about an
  "if" after the comma). +1/+1 and -1/-1 counters on one permanent are removed in pairs (704.5q).
* "put a +1/+1 counter on each artifact creature and/or Vehicle you control" (Iron Spider), "… each other creature you control that's a token or a Rabbit"
  (Finneas), "… on each creature you control and those creatures gain deathtouch until end of turn" (Nalia de'Arnise).
* "Whenever you activate an exhaust / a boast / a power-up ability" (Adrenaline Jockey, Rangers' Refueler, Afterburner Expert, Frenzied Raider, Marvel Boy):
  the activated ability whose text begins with that ability word (702.177a, 702.142a, 702.193a).
* "Whenever one or more creatures you control enter, if one or more of them entered from a graveyard or was cast from a graveyard" (Celes, Rune Knight; Kotis,
  Sibsig Champion): some object of the batch an aggregated trigger is about (603.2c) came from a graveyard, or was cast from one.
* "put a +1/+1 counter on Yorvo. Then if that creature's power is greater than Yorvo's power, …": "that creature" is the one the trigger is about, not the
  source the sentence before put a counter on (the comparison is with the source).
* "Whenever an opponent loses life for the first time during each of their turns" (Valgavoth), "Whenever you draw your first or second card each turn" (Lady
  Octopus), "Whenever you cast a spell that targets an opponent or a creature an opponent controls" (Danitha, 115.9b), "Draw a card if that creature has a
  +1/+1 counter on it. If it doesn't, put …" (Marcus), "you may return target creature … if its power is less than this creature's power" (Sage-Eye Avengers),
  "put a +1/+1 counter on each of those creatures and they gain vigilance" (Unbreakable Formation), "Each other creature you control enters with an additional
  vigilance counter on it" (Tayam), "If it entered under your control, put a +1/+1 counter on Phelia" (the permanent she exiled, back under its owner's control),
  "if that opponent has more life than another of your opponents" (Breena: the player the attack was declared against, 508.3e), "If that spell is a Lesson, put
  an additional +1/+1 counter on that land" (Toph: "that spell" is the cast trigger's spell, not the land earthbend made)."""

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
from tests.test_rules_conditionals import counters, token_of
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave33c_counters_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w33c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Yorvo, Lord of Garenbrig", "Cursed Wombat", "Experiment Twelve", "Shelinda, Yevon Acolyte", "Bristlebane Battler", "Encumbered Reejerey",
        "Moonshadow", "Iron Spider, Stark Upgrade", "Finneas, Ace Archer", "Nalia de'Arnise", "Adrenaline Jockey", "Frenzied Raider",
        "Marvel Boy, Noh-Varr", "Rangers' Refueler", "Afterburner Expert", "Celes, Rune Knight", "Kotis, Sibsig Champion", "Marcus, Mutant Mayor",
        "Sage-Eye Avengers", "Unbreakable Formation", "Chlorophant", "Valgavoth, Harrower of Souls", "Lady Octopus, Inspired Inventor",
        "Danitha, Spear of Agony", "Pyromancer Ascension", "Rangers' Aetherhive", "Reluctant Dounguard", "Tayam, Luminous Enigma",
        "Phelia, Exuberant Shepherd", "Breena, the Demagogue", "Toph, Hardheaded Teacher"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def answer(s, *picks, limit=60):
    """Resolve everything; the decisions that come up are answered from ``picks`` in turn (an id, or a list of ids), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = [pick] if isinstance(pick, str) else pick or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, pid="p1", **m):
    """Cast ``name`` from the hand with this mana and let it resolve (a spell enters with its counters, 614.1c: moving a card by hand doesn't)."""
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id)
    answer(s)
    return card_named(s, name, pid)


def ready(s, *cs):
    """These permanents have been under their controller's control since before the turn began (302.6, 602.5a: {T} abilities)."""
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


@pytest.mark.parametrize("name", FULL)
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# -- "put another / an additional +1/+1 counter" (Yorvo, Lord of Garenbrig) -----------------------------------------------------------------
def test_yorvo_enters_with_four_and_a_smaller_creature_gets_it_one_counter_only(cards):
    s = build(cards, ["Yorvo, Lord of Garenbrig", "Grizzly Bears"], [])
    yorvo = cast(s, "Yorvo, Lord of Garenbrig", G=3)
    assert counters(s, yorvo) == 4 and pt(s, "Yorvo, Lord of Garenbrig") == (4, 4)
    cast(s, "Grizzly Bears", G=2)  # 2 power is not greater than Yorvo's 5 after the first counter: no "another"
    assert counters(s, yorvo) == 5
    check(s)


@pytest.mark.parametrize("extra, first, second", [(None, 1, 1), ("Doubling Season", 2, 2), ("Hardened Scales", 2, 2)])
def test_yorvo_puts_its_counters_through_the_replacements(cards, extra, first, second):
    """122.6 / 614.1: "put another +1/+1 counter" is a put like the first: Doubling Season doubles each, Hardened Scales adds one to each."""
    s = build(cards, ["Yorvo, Lord of Garenbrig", "Verdant Force", *([extra] if extra else [])], [])
    yorvo = cast(s, "Yorvo, Lord of Garenbrig", G=3)
    assert counters(s, yorvo) == 4
    if extra:
        put(s, extra)
    entered = counters(s, yorvo)
    cast(s, "Verdant Force", G=8)  # a 7/7: more power than Yorvo has after the first counter, so the second counter follows
    assert counters(s, yorvo) == entered + first + second
    check(s)


# -- "if its power is less than Shelinda's power" (Shelinda, Yevon Acolyte) ------------------------------------------------------------------
def test_shelinda_gives_the_counter_to_a_smaller_creature_and_otherwise_keeps_it(cards):
    s = build(cards, ["Shelinda, Yevon Acolyte", "Grizzly Bears", "Llanowar Elves"], [])
    shelinda = cast(s, "Shelinda, Yevon Acolyte", G=1, W=1)
    bears = cast(s, "Grizzly Bears", G=2)  # 2 is not less than Shelinda's 2: "Otherwise, put a +1/+1 counter on Shelinda"
    assert counters(s, shelinda) == 1 and counters(s, bears) == 0
    elves = cast(s, "Llanowar Elves", G=1)  # 1 is less than her 3 now
    assert counters(s, elves) == 1 and counters(s, shelinda) == 1
    check(s)


# -- mass counters: "each artifact creature and/or Vehicle you control" (Iron Spider), "that's a token or a Rabbit" (Finneas), "and those creatures gain" ----
def ability_index(s, c, do):
    """The index of the ability of ``c`` whose effects do ``do``."""
    from app.rules import scripts
    from app.rules.plan import Plan

    ch = Plan(s.state, c.controller, s.cards, None).ch(s.state.cards[c.id])
    return next(i for i, d in scripts.definitions(ch).items() if any(e.get("do") == do for e in d.get("effects") or []))


def attack(s, *attackers):
    act(s, "p1", type="pass_priority")  # → declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])


def through_combat(s, *picks, limit=60):
    """Play on to the second main phase (nobody blocks); the other decisions that come up are answered from ``picks`` in turn (an id or a label),
    else with their first options."""
    picks, asked = list(picks), []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            asked.append([(o.id, o.label) for o in d.options])
            want = picks.pop(0) if picks else None
            ids = [o.id for o in d.options if want in (o.id, o.label)] if want else []
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


@pytest.mark.parametrize("extra, each", [(None, 1), ("Doubling Season", 2)])
def test_iron_spider_puts_a_counter_on_each_artifact_creature_and_each_vehicle_only(cards, extra, each):
    """"each artifact creature and/or Vehicle you control": the Spider (an artifact creature) and a Vehicle that isn't a creature; not a creature that
    isn't an artifact. 122.6: the puts go through the choke point, so Doubling Season doubles each."""
    s = build(cards, ["Iron Spider, Stark Upgrade", "Smuggler's Copter", "Grizzly Bears", *([extra] if extra else [])], [])
    spider, copter, bears = put(s, "Iron Spider, Stark Upgrade"), put(s, "Smuggler's Copter"), put(s, "Grizzly Bears")
    if extra:
        put(s, extra)
    ready(s, spider)
    act(s, "p1", type="activate_ability", card_id=spider.id, ability=ability_index(s, spider, "add_counters"))
    answer(s)
    assert (counters(s, spider), counters(s, copter), counters(s, bears)) == (each, each, 0)
    check(s)


def test_finneas_puts_a_counter_on_each_other_token_and_rabbit_and_draws_at_ten_power(cards):
    s = build(cards, ["Finneas, Ace Archer", "Intrepid Rabbit", "Grizzly Bears"], [])
    finneas, rabbit, bears = put(s, "Finneas, Ace Archer"), put(s, "Intrepid Rabbit"), put(s, "Grizzly Bears")
    spirit = token_of(s, "p1", "Spirit", "Token Creature — Spirit", "1/1")
    ready(s, finneas)
    hand = len(s.state.zones["p1:hand"])
    attack(s, finneas)
    through_combat(s)
    assert (counters(s, spirit), counters(s, rabbit), counters(s, bears), counters(s, finneas)) == (1, 1, 0, 0)  # "other": not Finneas, a Rabbit too
    assert len(s.state.zones["p1:hand"]) == hand + 1  # 2 (Finneas) + 2 (Spirit) + 4 (Rabbit) + 2 (Bears) = 10: "Then if … total power 10 or greater"
    check(s)


def test_nalia_puts_a_counter_on_each_creature_and_they_gain_deathtouch_with_a_full_party(cards):
    s = build(cards, ["Nalia de'Arnise"], [])
    nalia = put(s, "Nalia de'Arnise")  # a Human Rogue: the party's Rogue
    kinds = {n: token_of(s, "p1", n, f"Token Creature — {n}", "1/1") for n in ("Cleric", "Warrior", "Wizard")}
    act(s, "p1", type="pass_priority")  # → beginning of combat
    for _ in range(10):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    for c in (nalia, *kinds.values()):
        assert counters(s, c) == 1, c.name
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    assert all("deathtouch" in plan.ch(s.state.cards[c.id]).keywords for c in (nalia, *kinds.values()))
    check(s)


def test_nalia_without_a_full_party_does_nothing(cards):
    s = build(cards, ["Nalia de'Arnise"], [])
    nalia = put(s, "Nalia de'Arnise")
    token_of(s, "p1", "Cleric", "Token Creature — Cleric", "1/1")
    act(s, "p1", type="pass_priority")
    for _ in range(10):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert counters(s, nalia) == 0
    check(s)


# -- "… while this creature has a -1/-1 counter on it" (Bristlebane Battler, Encumbered Reejerey, Moonshadow, Pyromancer Ascension) --------------
def test_bristlebane_battler_loses_a_minus_counter_whenever_another_creature_enters(cards):
    s = build(cards, ["Bristlebane Battler", "Grizzly Bears", "Llanowar Elves"], [])
    battler = cast(s, "Bristlebane Battler", G=1, C=1)
    assert counters(s, battler, "-1/-1") == 5 and pt(s, "Bristlebane Battler") == (1, 1)  # 6/6 entering with five -1/-1 counters
    cast(s, "Grizzly Bears", G=2)
    assert counters(s, battler, "-1/-1") == 4 and pt(s, "Bristlebane Battler") == (2, 2)
    cast(s, "Llanowar Elves", G=1)
    assert counters(s, battler, "-1/-1") == 3
    check(s)


def test_moonshadow_loses_a_counter_when_a_permanent_card_of_yours_goes_to_your_graveyard(cards):
    s = build(cards, ["Moonshadow", "Grizzly Bears", "Lightning Bolt"], [])
    moon = cast(s, "Moonshadow", B=1)
    assert counters(s, moon, "-1/-1") == 6 and pt(s, "Moonshadow") == (1, 1)
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[bears.id])  # its death puts a permanent card into the graveyard
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and counters(s, moon, "-1/-1") == 5
    check(s)


def test_encumbered_reejerey_loses_a_counter_when_tapped_and_plus_one_counters_cancel_minus_ones(cards):
    """704.5q: a +1/+1 and a -1/-1 counter on one permanent are removed as a pair — the "while" is looked at as it becomes tapped (603.2), after that."""
    s = build(cards, ["Encumbered Reejerey"], [])
    reejerey = cast(s, "Encumbered Reejerey", W=1, C=1)
    assert counters(s, reejerey, "-1/-1") == 3 and pt(s, "Encumbered Reejerey") == (2, 1)
    ready(s, reejerey)
    attack(s, reejerey)  # attacking taps it: "becomes tapped while it has a -1/-1 counter on it"
    through_combat(s)
    assert counters(s, reejerey, "-1/-1") == 2
    act(s, "p1", type="counter", card_ids=[reejerey.id], kind="+1/+1", delta=1)
    act(s, "p1", type="pass_priority")  # (state-based actions are checked before a player would receive priority)
    assert (counters(s, reejerey, "+1/+1"), counters(s, reejerey, "-1/-1")) == (0, 1)
    check(s)


def test_pyromancer_ascension_copies_a_spell_only_with_two_quest_counters(cards):
    s = build(cards, ["Pyromancer Ascension", "Lightning Bolt"], [])
    asc = put(s, "Pyromancer Ascension")
    act(s, "p1", type="counter", card_ids=[asc.id], kind="quest", delta=1)
    mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    stacked = [x for x in s.state.zones.get("stack", []) if s.state.cards[x].ability is not None]
    assert not stacked  # one quest counter: "while this enchantment has two or more quest counters on it" is false as the spell is cast
    answer(s)
    act(s, "p1", type="counter", card_ids=[asc.id], kind="quest", delta=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    stacked = [x for x in s.state.zones.get("stack", []) if s.state.cards[x].ability is not None]
    assert len(stacked) == 1
    check(s)


# -- "put +1/+1 counters on that creature equal to its power" (Experiment Twelve), "put an additional +1/+1 counter on it" (Cursed Wombat) ----------
def test_experiment_twelve_puts_counters_equal_to_its_power_when_turned_face_up(cards):
    s = build(cards, ["Experiment Twelve"], [])
    twelve = to_hand(s, "Experiment Twelve")
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=twelve.id, face_down=True)  # disguise: a 2/2 with ward {2}
    answer(s)
    assert s.state.cards[twelve.id].face_down
    mana(s, "p1", G=1, C=4)  # the disguise cost
    act(s, "p1", type="turn_face_up", card_id=twelve.id)
    answer(s)
    c = s.state.cards[twelve.id]
    assert not c.face_down and counters(s, twelve) == 4 and pt(s, "Experiment Twelve") == (8, 8)  # its 4 power, as a number of counters
    check(s)


@pytest.mark.parametrize("extra, adapt, additional", [(None, 2, 1), ("Doubling Season", 4, 2), ("Hardened Scales", 3, 2)])
def test_cursed_wombat_puts_an_additional_counter_once_each_turn_through_the_replacements(cards, extra, adapt, additional):
    """Adapt 2 puts counters on it, the permanent's granted ability puts one more (122.6: each a put, so Doubling Season / Hardened Scales apply to
    both) — and the counter put by that trigger doesn't set it off again: "This ability triggers only once each turn"."""
    s = build(cards, ["Cursed Wombat", *([extra] if extra else [])], [])
    wombat = put(s, "Cursed Wombat")
    if extra:
        put(s, extra)
    mana(s, "p1", B=1, G=1, C=2)
    act(s, "p1", type="activate_ability", card_id=wombat.id, ability=0)  # {2}{B}{G}: Adapt 2
    answer(s)
    assert counters(s, wombat) == adapt + additional
    check(s)


# -- "Whenever you activate an exhaust / a boast / a power-up ability" (Adrenaline Jockey, Rangers' Refueler, Afterburner Expert, Frenzied Raider, Marvel Boy) ---
def test_an_exhaust_activation_counts_for_jockey_refueler_and_afterburner_expert_but_another_ability_does_not(cards):
    s = build(cards, ["Adrenaline Jockey", "Rangers' Refueler", "Iron Spider, Stark Upgrade", "Afterburner Expert"], [])
    jockey, refueler, spider = put(s, "Adrenaline Jockey"), put(s, "Rangers' Refueler"), put(s, "Iron Spider, Stark Upgrade")
    expert = card_named(s, "Afterburner Expert")
    act(s, "p1", type="move", card_ids=[expert.id], to={"player": "p1", "zone": "graveyard"})
    ready(s, spider, refueler)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=spider.id, ability=ability_index(s, spider, "add_counters"))  # {T}: not an exhaust ability
    answer(s)
    assert counters(s, jockey) == 0 and len(s.state.zones["p1:hand"]) == hand and s.state.cards[expert.id].zone == "p1:graveyard"
    mana(s, "p1", C=4)
    act(s, "p1", type="activate_ability", card_id=refueler.id, ability=ability_index(s, refueler, "add_counters"))  # Exhaust — {4}
    answer(s)
    assert counters(s, jockey) == 1  # Adrenaline Jockey: "Whenever you activate an exhaust ability, put a +1/+1 counter on this creature."
    assert len(s.state.zones["p1:hand"]) == hand + 1  # Rangers' Refueler: "… draw a card."
    assert s.state.cards[expert.id].zone == "p1:battlefield"  # Afterburner Expert: "… return this card from your graveyard to the battlefield."
    check(s)


def test_frenzied_raider_gets_a_counter_when_a_boast_ability_is_activated(cards):
    s = build(cards, ["Frenzied Raider", "Duskwielder"], [])
    raider, dusk = put(s, "Frenzied Raider"), put(s, "Duskwielder")
    ready(s, dusk)
    attack(s, dusk)
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=dusk.id, ability=ability_index(s, dusk, "lose_life"))  # Boast — {1}
    answer(s)
    assert counters(s, raider) == 1
    assert (life(s, "p1"), life(s, "p2")) == (41, 38)  # the boast drained 1, then Duskwielder dealt its 1 combat damage
    check(s)


def test_marvel_boy_gets_a_counter_for_a_creature_entering_and_for_a_power_up_activation(cards):
    s = build(cards, ["Marvel Boy, Noh-Varr", "Brave Brawler"], [])
    boy = put(s, "Marvel Boy, Noh-Varr")
    brawler = cast(s, "Brave Brawler", W=1, C=1)  # another creature enters
    assert counters(s, boy) == 1
    mana(s, "p1", C=3)  # Power-up — {4}{W}, less the {1}{W} of its mana cost: it entered this turn (702.193a)
    act(s, "p1", type="activate_ability", card_id=brawler.id, ability=ability_index(s, brawler, "add_counters"))
    answer(s)
    assert counters(s, brawler) == 2 and counters(s, boy) == 2
    check(s)


# -- "if one or more of them entered from a graveyard or was cast from a graveyard" (Celes, Rune Knight; Kotis, Sibsig Champion) ------------------
def test_kotis_gets_two_counters_for_a_creature_put_onto_the_battlefield_from_a_graveyard_not_for_one_cast_from_the_hand(cards):
    s = build(cards, ["Kotis, Sibsig Champion", "Grizzly Bears", "Llanowar Elves", "Zombify"], [])
    kotis = put(s, "Kotis, Sibsig Champion")
    cast(s, "Grizzly Bears", G=2)  # cast from the hand: it entered from the stack
    assert counters(s, kotis) == 0
    elves = card_named(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Zombify").id, targets=[elves.id])
    answer(s)
    assert s.state.cards[elves.id].zone == "p1:battlefield" and counters(s, kotis) == 2  # entered from a graveyard
    check(s)


def test_celes_puts_a_counter_on_each_creature_you_control_when_others_enter_from_a_graveyard(cards):
    s = build(cards, ["Celes, Rune Knight", "Grizzly Bears", "Llanowar Elves", "Zombify"], [])
    celes = put(s, "Celes, Rune Knight")
    bears = put(s, "Grizzly Bears")
    elves = card_named(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Zombify").id, targets=[elves.id])
    answer(s)
    assert [counters(s, c) for c in (celes, bears, elves)] == [1, 1, 1]
    check(s)


def test_kotis_gets_two_counters_for_a_creature_it_let_you_cast_from_your_graveyard(cards):
    """"was cast from a graveyard": the spell cast with Kotis's own permission (exiling three other cards) enters from the stack, not from a graveyard."""
    s = build(cards, ["Kotis, Sibsig Champion", "Grizzly Bears", "Llanowar Elves", "Giant Growth", "Lightning Bolt"], [])
    kotis = put(s, "Kotis, Sibsig Champion")
    bears = card_named(s, "Grizzly Bears")
    for name in ("Grizzly Bears", "Llanowar Elves", "Giant Growth", "Lightning Bolt"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and counters(s, kotis) == 2
    check(s)


# -- "if its power is less than this creature's power" (Sage-Eye Avengers), "and they gain vigilance" (Unbreakable Formation), "If it doesn't," (Marcus) -------
@pytest.mark.parametrize("victim, bounced", [("Grizzly Bears", True), ("Verdant Force", False)])
def test_sage_eye_avengers_returns_a_target_only_if_its_power_is_less_than_its_own(cards, victim, bounced):
    s = build(cards, ["Sage-Eye Avengers"], ["Grizzly Bears", "Verdant Force"])
    avengers, target = put(s, "Sage-Eye Avengers"), put(s, victim, "p2")
    ready(s, avengers)
    attack(s, avengers)
    through_combat(s, target.id, "Yes")
    assert (s.state.cards[target.id].zone == "p2:hand") is bounced  # 2 < 4, but 7 is not less than 4
    check(s)


def test_unbreakable_formation_puts_a_counter_on_each_creature_it_made_indestructible_and_they_gain_vigilance(cards):
    s = build(cards, ["Unbreakable Formation", "Grizzly Bears", "Llanowar Elves"], [])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Unbreakable Formation").id)  # in the main phase: the addendum
    answer(s)
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    for c in (bears, elves):
        assert counters(s, c) == 1 and "vigilance" in plan.ch(s.state.cards[c.id]).keywords, c.name
    check(s)


def test_marcus_draws_for_a_creature_with_a_counter_and_otherwise_puts_one_on_it(cards):
    s = build(cards, ["Marcus, Mutant Mayor", "Grizzly Bears", "Llanowar Elves"], [])
    put(s, "Marcus, Mutant Mayor")
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    act(s, "p1", type="counter", card_ids=[elves.id], kind="+1/+1", delta=1)
    ready(s, bears, elves)
    hand = len(s.state.zones["p1:hand"])
    attack(s, bears, elves)
    through_combat(s)
    assert counters(s, bears) == 1 and counters(s, elves) == 1  # Bears had none: "If it doesn't, put a +1/+1 counter on it"
    assert len(s.state.zones["p1:hand"]) == hand + 1  # the Elves had one: "draw a card"
    check(s)


# -- "an opponent loses life for the first time during each of their turns" (Valgavoth, Harrower of Souls) ------------------------------------------
def to_main_of(s, who, limit=300):
    """Play on (nobody attacks or blocks) to the first main phase of ``who``'s next turn, resolving what comes up."""
    start = s.state.turn.number
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == "main1" and s.state.turn.active_player == who and s.state.turn.number > start and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached the main phase")


def test_valgavoth_triggers_for_an_opponents_first_life_loss_in_their_own_turn_only(cards):
    s = build(cards, ["Valgavoth, Harrower of Souls", "Sulfuric Vortex", "Lightning Bolt"], [])
    valgavoth = put(s, "Valgavoth, Harrower of Souls")
    put(s, "Sulfuric Vortex")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])  # Alice's own turn: Bob loses life, but not during his turn
    answer(s)
    assert life(s, "p2") == 37 and counters(s, valgavoth) == 0
    hand = len(s.state.zones["p1:hand"])
    to_main_of(s, "p2")  # Bob's upkeep: Sulfuric Vortex deals him 2 damage — his first loss of life during his own turn
    assert life(s, "p2") == 35 and counters(s, valgavoth) == 1
    assert len(s.state.zones["p1:hand"]) == hand + 1  # Valgavoth: "… and draw a card"
    check(s)


# -- "Whenever you draw your first or second card each turn" (Lady Octopus, Inspired Inventor) ------------------------------------------------------
def test_lady_octopus_gets_an_ingenuity_counter_for_each_of_the_first_two_cards_drawn_in_a_turn(cards):
    s = build(cards, ["Lady Octopus, Inspired Inventor", "Divination", "Divination"], [], forests=20)
    octopus = put(s, "Lady Octopus, Inspired Inventor")
    divinations = [c for c in s.state.cards.values() if c.name == "Divination" and c.owner == "p1"]
    for d in divinations:
        act(s, "p1", type="move", card_ids=[d.id], to={"zone": "hand"})
    mana(s, "p1", U=2, C=4)
    act(s, "p1", type="cast_spell", card_id=divinations[0].id)  # draws two: the first and the second card of the turn
    answer(s)
    assert counters(s, octopus, "ingenuity") == 2
    act(s, "p1", type="cast_spell", card_id=divinations[1].id)  # two more: the third and the fourth
    answer(s)
    assert counters(s, octopus, "ingenuity") == 2
    check(s)


# -- "Whenever you cast a spell that targets an opponent or a creature an opponent controls" (Danitha, Spear of Agony) -------------------------------
def test_danitha_gets_a_counter_for_a_spell_aimed_at_an_opponent_or_their_creature_but_not_at_your_own(cards):
    s = build(cards, ["Danitha, Spear of Agony", "Llanowar Elves", "Lightning Bolt", "Lightning Bolt", "Lightning Bolt"], ["Grizzly Bears"])
    danitha, elves, theirs = put(s, "Danitha, Spear of Agony"), put(s, "Llanowar Elves"), put(s, "Grizzly Bears", "p2")
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    for b in bolts:
        act(s, "p1", type="move", card_ids=[b.id], to={"zone": "hand"})
    for bolt, target, expected in ((bolts[0], elves.id, 0), (bolts[1], "p2", 1), (bolts[2], theirs.id, 2)):
        mana(s, "p1", R=1)
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[target])
        answer(s)
        assert counters(s, danitha) == expected, target
    check(s)


# -- "Each other creature you control enters with an additional vigilance counter on it" (Tayam, Luminous Enigma) --------------------------------------
@pytest.mark.parametrize("extra, n", [(None, 1), ("Doubling Season", 2)])
def test_tayam_gives_each_other_creature_a_vigilance_counter_as_it_enters_and_the_keyword_with_it(cards, extra, n):
    """614.1c / 122.6: the counter is part of how it enters (so Doubling Season doubles it); 122.1b: a vigilance counter gives vigilance."""
    s = build(cards, ["Tayam, Luminous Enigma", "Grizzly Bears", *([extra] if extra else [])], [])
    tayam = put(s, "Tayam, Luminous Enigma")
    if extra:
        put(s, extra)
    bears = cast(s, "Grizzly Bears", G=2)
    from app.rules.plan import Plan

    assert counters(s, bears, "vigilance") == n and "vigilance" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id]).keywords
    assert counters(s, tayam, "vigilance") == 0  # "other": Tayam was already there
    check(s)


# -- "If it entered under your control, put a +1/+1 counter on Phelia" (Phelia, Exuberant Shepherd) -------------------------------------------------
@pytest.mark.parametrize("owner, counter", [("p1", 1), ("p2", 0)])
def test_phelia_gets_a_counter_only_if_what_she_exiled_came_back_under_your_control(cards, owner, counter):
    """The exiled permanent returns under its owner's control at the next end step: yours (a counter) or an opponent's (none)."""
    s = build(cards, ["Phelia, Exuberant Shepherd", "Grizzly Bears"], ["Grizzly Bears"])
    phelia = put(s, "Phelia, Exuberant Shepherd")
    target = put(s, "Grizzly Bears", owner)
    ready(s, phelia)
    attack(s, phelia)
    through_combat(s, target.id)
    assert s.state.cards[target.id].zone.endswith("exile")
    for _ in range(40):
        if s.state.cards[target.id].zone.endswith("battlefield"):
            break
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert s.state.cards[target.id].zone.endswith("battlefield") and counters(s, phelia) == counter
    check(s)


# -- "if that opponent has more life than another of your opponents" (Breena, the Demagogue) ----------------------------------------------------
@pytest.mark.parametrize("bob_life, fires", [(40, True), (20, False)])
def test_breena_needs_the_attacked_player_to_have_more_life_than_another_of_her_controllers_opponents(cards, bob_life, fires):
    """Carol's Breena sees Alice attack Bob: both are Carol's opponents, and Alice has 30. Bob must have more life than her for it to trigger."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    decks = [deck(cards, "Krenko, Mob Boss", [(1, "Llanowar Elves"), (10, "Forest")]), deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")]),
             deck(cards, "Krenko, Mob Boss", [(1, "Breena, the Demagogue"), (10, "Mountain")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    breena, elves = put(s, "Breena, the Demagogue", "p3"), put(s, "Llanowar Elves")
    act(s, "p1", type="set_life", player="p1", value=30)
    act(s, "p1", type="set_life", player="p2", value=bob_life)
    ready(s, elves)
    hand = len(s.state.zones["p1:hand"])
    attack(s, elves)
    through_combat(s)
    assert counters(s, breena) == (2 if fires else 0)  # Carol puts the two counters on a creature she controls
    assert len(s.state.zones["p1:hand"]) == hand + (1 if fires else 0)  # Alice, "that attacking player", draws
    check(s)


# -- "If that spell is a Lesson, put an additional +1/+1 counter on that land." (Toph, Hardheaded Teacher) ----------------------------------------------
def test_toph_earthbends_for_each_spell_and_puts_an_additional_counter_on_the_land_for_a_lesson(cards):
    s = build(cards, ["Toph, Hardheaded Teacher", "Lightning Bolt", "Environmental Sciences"], [])
    put(s, "Toph, Hardheaded Teacher")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    for f in forests:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])  # not a Lesson: earthbend 1 only
    answer(s, forests[0].id)
    mana(s, "p1", C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Environmental Sciences").id)  # a Lesson: the land gets one more
    answer(s, forests[1].id)
    assert (counters(s, forests[0]), counters(s, forests[1])) == (1, 2)
    check(s)
