"""Wave 34C: the X of a triggered ability that some other object gave it (CR 2026-09-25), real Oracle text
(tests/fixtures/wave34c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 107.3a: a cycling cost with {X} is announced as cycling is activated; "When you cycle this card, create an X/X …" reads that X (Shark
  Typhoon ruling 2020-04-17: X may be 0 and the ability still triggers; Rampaging War Mammoth ruling 2023-06-16).
* 107.3e: "Whenever you cast a spell with {X} in its mana cost, … X …" uses the X of the spell cast (Zaxara ruling 2020-04-17).
* 107.3i: "When you cast this spell, … X …" is an ability of the spell itself, so it has the spell's X (Photon Blast Barrage).
* A trigger whose X nothing gives it (no {X} in the spell cast, no Cycling {X}) stays manual: its X would read 0.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature
from tests.test_rules_conditionals import settle as settle_stack
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, check, life, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave34c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w34c", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Shark Typhoon", "Rampaging War Mammoth", "Webstrike Elite", "Valor's Flagship", "Zaxara, the Exemplary",
        "Nev, the Practical Dean", "Photon Blast Barrage"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def on_battlefield(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:battlefield"]


def pool_total(s, pid="p1"):
    return sum(s.state.players[pid].mana.values())


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_cards_that_read_another_objects_x_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# -- 107.3a: Cycling {X} ----------------------------------------------------------------------------------------
def test_shark_typhoon_cycled_for_x_makes_an_x_by_x_shark(cards):
    s = build(cards, ["Shark Typhoon"])
    typhoon = to_hand(s, "Shark Typhoon")
    mana(s, U=4)
    with pytest.raises(ActionError):  # 107.3a: X is announced as cycling is activated
        act(s, "p1", type="activate_ability", card_id=typhoon.id, ability=1)
    act(s, "p1", type="activate_ability", card_id=typhoon.id, ability=1, x_value=2)  # {X}{1}{U}: four mana
    assert pool_total(s) == 0 and s.state.cards[typhoon.id].zone == "p1:graveyard"
    settle_stack(s)
    (shark,) = on_battlefield(s, "Shark")
    assert pt(s, "Shark") == (2, 2)  # the token's printed X/X is the cycling X (111.3, 608.2h)
    check(s)


def test_cycling_x_is_offered_with_an_x_prompt_hint(cards):
    from app.rules.casting import activatable

    s = build(cards, ["Shark Typhoon", "Webstrike Elite"])
    typhoon = to_hand(s, "Shark Typhoon")
    assert {"card_id": typhoon.id, "ability": 1, "x": True} in activatable(s.state, "p1", s.cards)  # (the client asks for X: needsX)
    check(s)


def test_shark_typhoon_cycled_for_zero_still_triggers_and_the_shark_dies(cards):
    s = build(cards, ["Shark Typhoon"])
    typhoon = to_hand(s, "Shark Typhoon")
    mana(s, U=2)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=typhoon.id, ability=1, x_value=0)
    settle_stack(s)
    assert not on_battlefield(s, "Shark")  # a 0/0: put into the graveyard by state-based actions (704.5f)
    assert len(s.state.zones["p1:hand"]) == hand  # (the cycled card left the hand, the cycling ability drew one)
    check(s)


def test_rampaging_war_mammoth_targets_up_to_the_cycling_x(cards):
    s = build(cards, ["Rampaging War Mammoth"], theirs=["Sol Ring", "Mind Stone", "Arcane Signet"])
    rings = [put(s, n, "p2") for n in ("Sol Ring", "Mind Stone", "Arcane Signet")]
    mammoth = to_hand(s, "Rampaging War Mammoth")
    mana(s, R=5)
    act(s, "p1", type="activate_ability", card_id=mammoth.id, ability=1, x_value=2)  # {X}{2}{R}
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 2 and d.min_choices == 0  # 601.2c: up to X, X is the cycling cost's
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[rings[0].id, rings[1].id])
    answer(s)
    assert [s.state.cards[r.id].zone for r in rings] == ["p2:graveyard", "p2:graveyard", "p2:battlefield"]
    check(s)


def test_rampaging_war_mammoth_cycled_for_zero_has_no_targets_but_still_cycles(cards):
    s = build(cards, ["Rampaging War Mammoth"], theirs=["Sol Ring"])
    ring = put(s, "Sol Ring", "p2")
    mammoth = to_hand(s, "Rampaging War Mammoth")
    mana(s, R=3)
    act(s, "p1", type="activate_ability", card_id=mammoth.id, ability=1, x_value=0)
    answer(s)
    assert s.state.cards[mammoth.id].zone == "p1:graveyard" and s.state.cards[ring.id].zone == "p2:battlefield"
    check(s)


def test_webstrike_elite_destroys_only_the_permanent_with_mana_value_x(cards):
    s = build(cards, ["Webstrike Elite"], theirs=["Sol Ring", "Mind Stone"])
    ring, stone = put(s, "Sol Ring", "p2"), put(s, "Mind Stone", "p2")
    elite = to_hand(s, "Webstrike Elite")
    mana(s, G=4)
    act(s, "p1", type="activate_ability", card_id=elite.id, ability=1, x_value=2)  # {X}{G}{G}
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == [stone.id]  # mana value 2: the Mind Stone, not the Sol Ring
    answer(s, stone.id)
    assert s.state.cards[stone.id].zone == "p2:graveyard" and s.state.cards[ring.id].zone == "p2:battlefield"
    check(s)


def test_valors_flagship_cycled_for_x_makes_x_pilots(cards):
    s = build(cards, ["Valor's Flagship"])
    flagship = to_hand(s, "Valor's Flagship")
    mana(s, W=6)
    act(s, "p1", type="activate_ability", card_id=flagship.id, ability=2, x_value=3)  # {X}{2}{W}
    settle_stack(s)
    pilots = on_battlefield(s, "Pilot")
    assert len(pilots) == 3 and all("saddles Mounts" in (p.token.text if p.token else "") for p in pilots)
    check(s)


# -- 107.3e / 107.3i: a spell's X in a cast trigger -------------------------------------------------------------
def test_zaxara_puts_the_x_of_the_spell_cast_on_the_hydra(cards):
    s = build(cards, ["Zaxara, the Exemplary", "Stroke of Genius"])
    put(s, "Zaxara, the Exemplary")
    stroke = to_hand(s, "Stroke of Genius")
    mana(s, U=6)
    act(s, "p1", type="cast_spell", card_id=stroke.id, targets=["p1"], x_value=3)  # {X}{2}{U}
    settle_stack(s)
    (hydra,) = on_battlefield(s, "Hydra")
    assert s.state.cards[hydra.id].counters == {"+1/+1": 3} and pt(s, "Hydra") == (3, 3)  # the trigger resolved before the spell
    check(s)


def test_zaxara_with_x_zero_makes_a_hydra_that_dies(cards):
    s = build(cards, ["Zaxara, the Exemplary", "Stroke of Genius"])
    put(s, "Zaxara, the Exemplary")
    stroke = to_hand(s, "Stroke of Genius")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=stroke.id, targets=["p1"], x_value=0)
    settle_stack(s)
    assert not on_battlefield(s, "Hydra")  # 0/0 (the 2020-04-17 ruling)
    check(s)


def test_nev_counts_only_the_first_x_spell_each_turn(cards):
    s = build(cards, ["Nev, the Practical Dean", "Stroke of Genius", "Stroke of Genius"])
    nev = put(s, "Nev, the Practical Dean")
    first, second = [c for c in s.state.cards.values() if c.name == "Stroke of Genius" and c.owner == "p1"][:2]
    for spell in (first, second):
        act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    mana(s, U=12)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p1"], x_value=2)
    settle_stack(s)
    assert s.state.cards[nev.id].counters == {"+1/+1": 2}
    act(s, "p1", type="cast_spell", card_id=second.id, targets=["p1"], x_value=4)
    settle_stack(s)
    assert s.state.cards[nev.id].counters == {"+1/+1": 2}  # (not the first this turn)
    check(s)


def test_photon_blast_barrage_copies_itself_x_times(cards):
    s = build(cards, ["Photon Blast Barrage"])
    ogre = creature(s, "p2", "Ogre", "2/9")
    barrage = to_hand(s, "Photon Blast Barrage")
    mana(s, R=5)
    act(s, "p1", type="cast_spell", card_id=barrage.id, targets=[ogre.id], x_value=2)  # {X}{R}{R}
    answer(s)
    assert s.state.cards[ogre.id].damage == 3  # the spell and its two copies (X = 2): 1 damage each
    check(s)


# -- an X nothing gives stays manual (107.3: it would read 0) ---------------------------------------------------
@pytest.mark.parametrize("name,type_line,mana_cost,text", [
    ("Plain Cycler", "Creature — Test", "{2}{U}", "Cycling {1}{U}\nWhen you cycle this card, create an X/X blue Shark creature token with flying."),
    ("Plain Watcher", "Creature — Test", "{2}{G}", "Whenever you cast a spell, put X +1/+1 counters on this creature."),
    ("Plain Caster", "Sorcery", "{2}{R}", "When you cast this spell, draw X cards."),
])
def test_an_x_nothing_gives_the_trigger_stays_manual(name, type_line, mana_cost, text):
    from app.rules import oracle
    from app.rules.characteristics import Characteristics, parse_type_line

    sup, types, sub = parse_type_line(type_line)
    chs = Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, mana_cost=mana_cost, oracle_text=text,
                          abilities=tuple(oracle.parse_abilities(text, spell=bool(types & {"Instant", "Sorcery"}))))
    assert coverage.of_characteristics(chs).level != "FULL"


# ====================================================================================================================
# X in an amount: "X plus 3", "X minus one", "five times X", "half X", conditions on a defined X (107.1, 107.3c)
# ====================================================================================================================
def hand_names(s, pid="p1"):
    return sorted(s.state.cards[c].name for c in s.state.zones[f"{pid}:hand"])


def green_creature(s, pid, name):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Elf", "power": "1", "toughness": "1",
                                                        "colors": ["G"], "text": ""})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def until_decision(s, limit=30):
    from tests.test_rules_conditionals import until_asked

    return until_asked(s, limit)


@pytest.mark.parametrize("x,gain", [(0, 3), (2, 5)])
def test_vitalizing_cascade_gains_x_plus_three(cards, x, gain):
    s = build(cards, ["Vitalizing Cascade"])
    spell = to_hand(s, "Vitalizing Cascade")
    mana(s, G=2 + x, W=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x)
    settle_stack(s)
    assert life(s) == 40 + gain  # (107.1b: with X = 0 it is 0 plus 3)
    check(s)


def test_an_havva_inn_counts_the_green_creatures_as_it_resolves(cards):
    s = build(cards, ["An-Havva Inn"])
    a = green_creature(s, "p1", "Elf A")
    green_creature(s, "p1", "Elf B")
    green_creature(s, "p2", "Elf C")
    inn = to_hand(s, "An-Havva Inn")
    mana(s, G=3)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"  # (hold priority: something can happen with the spell on the stack)
    act(s, "p1", type="cast_spell", card_id=inn.id)  # three green creatures now …
    act(s, "p1", type="move", card_ids=[a.id], to={"zone": "graveyard"})  # … two when it resolves (a token ceases to exist)
    settle_stack(s)
    assert life(s) == 40 + 2 + 1  # 107.3c: the value of X may change while the spell is on the stack — X = 2, plus 1
    check(s)


def test_meteor_shower_divides_x_plus_one_damage(cards):
    s = build(cards, ["Meteor Shower"])
    ogre, wall = creature(s, "p2", "Ogre", "2/9"), creature(s, "p2", "Wall", "0/9")
    spell = to_hand(s, "Meteor Shower")
    mana(s, R=5)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[ogre.id, wall.id], target_counts=[2], x_value=2)  # {X}{X}{R}: 2 + 1 = 3 to divide (601.2d)
    d = s.state.rules.decision
    assert d is not None and d.kind == "divide" and d.display["total"] == 3
    act(s, "p1", type="choose", decision_id=d.id, amounts=[2, 1])
    settle_stack(s)
    assert (s.state.cards[ogre.id].damage, s.state.cards[wall.id].damage) == (2, 1)
    check(s)


@pytest.mark.parametrize("x,mine,theirs", [(3, 3, 2), (0, 0, 0), (1, 1, 0)])
def test_eiganjo_uprising_gives_the_opponent_one_fewer(cards, x, mine, theirs):
    s = build(cards, ["Eiganjo Uprising"])
    spell = to_hand(s, "Eiganjo Uprising")
    mana(s, R=2 + x, W=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x)
    settle_stack(s)
    assert (len(on_battlefield(s, "Samurai")), len(on_battlefield(s, "Samurai", "p2"))) == (mine, theirs)  # 107.1b: X minus one is never below 0
    check(s)


def test_crackle_with_power_deals_five_times_x_to_each_of_up_to_x_targets(cards):
    s = build(cards, ["Crackle with Power"])
    wall = creature(s, "p2", "Wall", "0/20")
    spell = to_hand(s, "Crackle with Power")
    mana(s, R=8)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[wall.id, "p2"], target_counts=[2], x_value=2)  # {X}{X}{X}{R}{R}
    settle_stack(s)
    assert s.state.cards[wall.id].damage == 10 and life(s, "p2") == 30
    check(s)


@pytest.mark.parametrize("x,gain,draws", [(5, 2, 2), (1, 0, 0)])
def test_hydroid_krasis_halves_x_rounding_down(cards, x, gain, draws):
    s = build(cards, ["Hydroid Krasis"])
    krasis = to_hand(s, "Hydroid Krasis")
    mana(s, G=x + 1, U=1)
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=krasis.id, x_value=x)
    settle_stack(s)
    assert life(s) == 40 + gain and len(s.state.zones["p1:hand"]) == before - 1 + draws  # the cast trigger resolved first, with this X (107.3i)
    assert s.state.cards[krasis.id].counters == {"+1/+1": x}
    check(s)


def test_contaminated_drink_gets_half_x_rad_counters_rounded_up(cards):
    s = build(cards, ["Contaminated Drink"])
    spell = to_hand(s, "Contaminated Drink")
    mana(s, U=3, B=2)
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=3)
    settle_stack(s)
    assert len(s.state.zones["p1:hand"]) == before - 1 + 3 and s.state.players["p1"].resources["rad"] == 2
    check(s)


def test_epiphany_reveals_x_plus_one_cards(cards):
    s = build(cards, ["Epiphany at the Drownyard"])
    spell = to_hand(s, "Epiphany at the Drownyard")
    mana(s, U=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2)
    d = until_decision(s)
    assert d is not None and d.kind == "choose_cards" and len(d.options) == 3  # X plus one = 3 cards to separate into two piles
    check(s)


# -- "If X is N or more" after a defined X (107.3c) ----------------------------------------------------------------
def test_shantotto_draws_only_when_the_mana_spent_is_four_or_more(cards):
    s = build(cards, ["Shantotto, Tactician Magician", "Stroke of Genius", "Divination"])
    put(s, "Shantotto, Tactician Magician")
    big, small = to_hand(s, "Stroke of Genius"), to_hand(s, "Divination")
    base = pt(s, "Shantotto, Tactician Magician")
    mana(s, U=9)
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=big.id, targets=["p1"], x_value=2)  # {X}{2}{U}: five mana spent
    settle_stack(s)
    assert pt(s, "Shantotto, Tactician Magician")[0] == base[0] + 5
    assert len(s.state.zones["p1:hand"]) == before - 1 + 2 + 1  # Stroke of Genius's two cards and Shantotto's (X = 5 ≥ 4)
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=small.id)  # {2}{U}: three mana spent
    settle_stack(s)
    assert pt(s, "Shantotto, Tactician Magician")[0] == base[0] + 5 + 3
    assert len(s.state.zones["p1:hand"]) == before - 1 + 2  # Divination's two; X = 3: no extra card
    check(s)


# -- the shields, the hands, the tokens: an X that is announced ---------------------------------------------------
def test_festival_of_the_guildpact_prevents_x_and_draws(cards):
    s = build(cards, ["Festival of the Guildpact"])
    spell = to_hand(s, "Festival of the Guildpact")
    pinger = creature(s, "p1", "Pinger", "1/1", text="{0}: This creature deals 5 damage to target player.")
    mana(s, W=4)
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=3)
    settle_stack(s)
    assert len(s.state.zones["p1:hand"]) == before - 1 + 1 and s.state.rules.prevention.get("p1") == 3
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=0, targets=["p1"])
    settle_stack(s)
    assert life(s) == 40 - 2  # 5 damage, 3 of them prevented (615.7)
    check(s)


def test_panacea_prevents_x_for_two_x(cards):
    s = build(cards, ["Panacea"])
    panacea = put(s, "Panacea")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=panacea.id, ability=0, targets=["p1"], x_value=2)  # {X}{X}, {T}
    settle_stack(s)
    assert s.state.rules.prevention.get("p1") == 2
    check(s)


def test_mind_warp_chooses_x_cards_from_the_hand(cards):
    s = build(cards, ["Mind Warp"], theirs=["Sol Ring", "Mind Stone", "Arcane Signet"])
    for n in ("Sol Ring", "Mind Stone", "Arcane Signet"):
        to_hand(s, n, "p2")
    spell = to_hand(s, "Mind Warp")
    mana(s, B=6)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], x_value=2)  # {X}{3}{B}
    d = until_decision(s)
    assert d is not None and d.player == "p1" and d.min_choices == d.max_choices == 2 and len(d.options) == 3
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:2])
    settle_stack(s)
    assert len(hand_names(s, "p2")) == 1 and len(s.state.zones["p2:graveyard"]) == 2
    check(s)


def test_mind_warp_with_a_short_hand_takes_all_of_it(cards):
    s = build(cards, ["Mind Warp"], theirs=["Sol Ring"])
    to_hand(s, "Sol Ring", "p2")
    spell = to_hand(s, "Mind Warp")
    mana(s, B=8)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], x_value=4)
    settle_stack(s)
    assert hand_names(s, "p2") == [] and len(s.state.zones["p2:graveyard"]) == 1
    check(s)


@pytest.mark.parametrize("x", [3, 0])
def test_farmer_cotton_makes_x_halflings_and_x_foods(cards, x):
    s = build(cards, ["Farmer Cotton"])
    cotton = to_hand(s, "Farmer Cotton")
    mana(s, G=x + 1, W=1)
    act(s, "p1", type="cast_spell", card_id=cotton.id, x_value=x)
    settle_stack(s)
    assert (len(on_battlefield(s, "Halfling")), len(on_battlefield(s, "Food"))) == (x, x)  # one instruction: both kinds (701.7a)
    check(s)


def test_geometer_arthropod_looks_at_x_cards_for_the_spell_cast(cards):
    s = build(cards, ["Geometer's Arthropod", "Stroke of Genius"])
    put(s, "Geometer's Arthropod")
    stroke = to_hand(s, "Stroke of Genius")
    mana(s, U=6)
    act(s, "p1", type="cast_spell", card_id=stroke.id, targets=["p2"], x_value=3)
    d = until_decision(s)
    assert d is not None and d.player == "p1" and len(d.options) == 3  # the top X cards (107.3e: the X of the spell cast)
    check(s)


def test_temper_prevents_x_and_counts_what_was_prevented(cards):
    s = build(cards, ["Temper"])
    bear = creature(s, "p1", "Bear", "2/9")
    pinger = creature(s, "p1", "Pinger", "1/1", text="{0}: This creature deals 5 damage to target creature.")
    spell = to_hand(s, "Temper")
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], x_value=2)
    settle_stack(s)
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=0, targets=[bear.id])
    settle_stack(s)
    assert s.state.cards[bear.id].damage == 3 and s.state.cards[bear.id].counters.get("+1/+1") == 2  # 5 − 2 prevented; one counter for each 1 prevented
    check(s)


def orcus_with_x(cards, x):
    s = build(cards, ["Orcus, Prince of Undeath", "Grizzly Bears", "Llanowar Elves", "Mind Stone"])
    for n in ("Grizzly Bears", "Llanowar Elves", "Mind Stone"):
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == n and c.owner == "p1")], to={"zone": "graveyard"})
    orcus = to_hand(s, "Orcus, Prince of Undeath")
    mana(s, B=1, R=1, C=2 + x)
    act(s, "p1", type="cast_spell", card_id=orcus.id, x_value=x)  # {X}{2}{B}{R}
    return s


def test_orcus_returns_creatures_with_total_mana_value_up_to_x(cards):
    s = orcus_with_x(cards, 3)
    d = until_decision(s)
    assert d is not None and d.kind == "choose_cards" and d.resume["step"] == "trigger_modes"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["1:0"])  # the second mode
    d = until_decision(s)
    assert d is not None and d.max_choices == 2 and {s.state.cards[o.id].name for o in d.options} == {"Grizzly Bears", "Llanowar Elves"}  # (up to X = 3: both)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])  # total mana value 2 + 1 = 3 ≤ X
    settle_stack(s)
    assert {c.name for c in on_battlefield_all(s)} >= {"Grizzly Bears", "Llanowar Elves", "Orcus, Prince of Undeath"}  # total mana value 3 ≤ X
    check(s)


def test_orcus_with_a_small_x_cannot_take_more_mana_value_than_x(cards):
    s = orcus_with_x(cards, 2)
    d = until_decision(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["1:0"])
    d = until_decision(s)
    assert d is not None and d.max_choices == 2  # up to X = 2 cards …
    with pytest.raises(ActionError):  # … whose total mana value (2 + 1) is over X = 2
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if s.state.cards[o.id].name == "Grizzly Bears")])
    settle_stack(s)
    assert {c.name for c in on_battlefield_all(s)} >= {"Grizzly Bears"} and not on_battlefield(s, "Llanowar Elves")
    check(s)


def test_rampaging_yao_guai_destroys_artifacts_with_total_mana_value_up_to_x(cards):
    s = build(cards, ["Rampaging Yao Guai"], theirs=["Sol Ring", "Mind Stone", "Arcane Signet"])
    ring, stone, signet = (put(s, n, "p2") for n in ("Sol Ring", "Mind Stone", "Arcane Signet"))
    guai = to_hand(s, "Rampaging Yao Guai")
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=guai.id, x_value=3)  # {X}{G}{G}{G}
    d = until_decision(s)
    assert d is not None and d.resume["step"] == "trigger_group"
    with pytest.raises(ActionError):  # 601.2c: 2 + 2 is over X = 3 — asked again, the ability is not lost
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[stone.id, signet.id])
    assert s.state.rules.decision is not None and s.state.rules.decision.id == d.id
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ring.id, stone.id])  # 1 + 2 = 3
    settle_stack(s)
    assert [s.state.cards[c.id].zone for c in (ring, stone, signet)] == ["p2:graveyard", "p2:graveyard", "p2:battlefield"]
    assert s.state.cards[guai.id].counters == {"+1/+1": 3}
    check(s)


def island(s, name):
    act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": "Token Land — Island", "text": ""})


def test_spectral_deluge_reads_the_islands_as_it_resolves(cards):
    s = build(cards, ["Spectral Deluge"], theirs=["Grizzly Bears", "Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    wall, brute = creature(s, "p2", "Wall", "0/3"), creature(s, "p2", "Brute", "4/4")
    island(s, "Isle A")
    island(s, "Isle B")
    deluge = to_hand(s, "Spectral Deluge")
    mana(s, U=6)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=deluge.id)  # two Islands now …
    island(s, "Isle C")  # … three when it resolves (107.3c: the value of X may change while it is on the stack)
    settle_stack(s)
    assert s.state.cards[bears.id].zone == s.state.cards[elves.id].zone == "p2:hand"
    assert wall.id not in s.state.cards or s.state.cards[wall.id].zone != "p2:battlefield"  # toughness 3 ≤ X = 3 (a token that left ceases to exist)
    assert s.state.cards[brute.id].zone == "p2:battlefield"
    check(s)


def test_scourge_of_fleets_returns_creatures_with_toughness_up_to_the_islands(cards):
    s = build(cards, ["Scourge of Fleets"], theirs=["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    brute = creature(s, "p2", "Brute", "4/4")
    island(s, "Isle A")
    island(s, "Isle B")
    kraken = to_hand(s, "Scourge of Fleets")
    mana(s, U=7)
    act(s, "p1", type="cast_spell", card_id=kraken.id)
    settle_stack(s)
    assert s.state.cards[bears.id].zone == "p2:hand" and s.state.cards[brute.id].zone == "p2:battlefield"  # X = 2: the 2/2 only
    check(s)


def test_abandon_hope_discards_x_then_takes_x_cards_from_their_hand(cards):
    s = build(cards, ["Abandon Hope", "Llanowar Elves", "Grizzly Bears"], theirs=["Sol Ring", "Mind Stone"])
    for n in ("Sol Ring", "Mind Stone"):
        to_hand(s, n, "p2")
    spell = to_hand(s, "Abandon Hope")
    to_hand(s, "Llanowar Elves")
    mana(s, B=1, C=1, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], x_value=1, cost_choices=[])  # {X}{1}{B}; discard X cards
    for _ in range(20):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert len(hand_names(s, "p2")) == 1 and len(s.state.zones["p2:graveyard"]) == 1  # X = 1 card taken
    assert "Llanowar Elves" in [s.state.cards[c].name for c in s.state.zones["p1:graveyard"]]  # the additional cost: X cards discarded
    check(s)


def test_alabaster_potion_gains_x_life_in_its_first_mode(cards):
    s = build(cards, ["Alabaster Potion"])
    potion = to_hand(s, "Alabaster Potion")
    mana(s, W=5)
    act(s, "p1", type="cast_spell", card_id=potion.id, modes=[0], targets=["p1"], x_value=3)
    settle_stack(s)
    assert life(s) == 43
    check(s)


def test_kairi_returns_nonland_permanents_with_total_mana_value_six_or_less(cards):
    s = build(cards, ["Kairi, the Swirling Sky"], theirs=["Sol Ring", "Mind Stone", "Solemn Simulacrum"])
    kairi = put(s, "Kairi, the Swirling Sky")
    ring, stone, solemn = (put(s, n, "p2") for n in ("Sol Ring", "Mind Stone", "Solemn Simulacrum"))
    pinger = creature(s, "p1", "Pinger", "1/1", text="{0}: This creature deals 9 damage to target creature.")
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=0, targets=[kairi.id])
    d = until_decision(s)
    assert d is not None and d.resume["step"] == "trigger_modes"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["0:0"])
    d = until_decision(s)
    assert d is not None and d.resume["step"] == "trigger_group"
    with pytest.raises(ActionError):  # 1 + 2 + 4 = 7 is over 6: chosen again, the ability stays (601.2c)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[ring.id, stone.id, solemn.id])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[stone.id, solemn.id])  # 2 + 4 = 6
    settle_stack(s)
    assert s.state.cards[stone.id].zone == "p2:hand" and s.state.cards[solemn.id].zone == "p2:hand" and s.state.cards[ring.id].zone == "p2:battlefield"
    check(s)


def on_battlefield_all(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield"]


@pytest.mark.parametrize("text", [
    "Create two Treasure tokens and a Food token.",
    "Create X 1/1 white Halfling creature tokens and X Food tokens.",
])
def test_several_kinds_of_token_each_with_its_own_number(text):
    from app.rules import scripts

    found = scripts.parse_effects(text)
    assert found is not None and len(found[0]) == 1 and len(found[0][0]["more"]) == 1
