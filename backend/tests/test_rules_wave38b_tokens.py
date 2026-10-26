"""Wave 38B: tokens with extra properties, real Oracle text (tests/fixtures/wave38b_tokens_cards.json, from data/cards.sqlite), CR 2026-09-25.
Every scenario checks the replay and a save and a load (``check``).

* 508.4, 506.3b: "for each opponent, you create a 2/2 … token that's tapped and attacking that opponent" (Stampede Surfer; Veteran Soldier's granted
  attack trigger on a commander): one token for each opponent, each attacking its own opponent; "that attacking player creates a tapped … token that's
  attacking that opponent" (Ellie, Brick Master, Combat Calligrapher): the attacking player is the creator and so the one who attacks with it;
  "you may have its controller create a … token that's tapped and attacking" (Najeela).
* 301.7, 702.122a, 111.3, 111.4: a Vehicle token is an artifact with a printed power and toughness and its own "Crew N" (Mu Yanling, Lita, Chandra).
* 614.16 (Doubling Season) applies to every one of those creations, and the extra tokens enter attacking too.
* 603.7 / 701.55 (Davros): an instruction that only creates a token leaves the turn's log as it was, so the villainous choice reads who lost life.
* "you had enter the battlefield under your control this turn" (Gyome), "create that many … with flying, then put a +1/+1 counter on ~" (Falcon and Redwing).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import characteristics as chars
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle, through_combat, until
from tests.wave9c_kit import card_named, check, mana, put

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave38b_tokens_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w38b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Stampede Surfer", "Veteran Soldier", "Mu Yanling, Wind Rider", "Lita, Mechanical Engineer", "Ellie, Brick Master", "Combat Calligrapher",
        "Najeela, the Blade-Blossom", "Gyome, Master Chef", "Falcon and Redwing", "Davros, Dalek Creator", "HYDRA Troopers", "Chandra, Spark Hunter", "The Third Doctor", "Emergent Sequence"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_setzer_is_full_since_coin_flips_are_events(cards):
    """The Vehicle token line is read; "whenever you win a coin flip" is read since wave 45C (705.2: the flipper wins or loses)."""
    assert coverage.of_card_data(cards.resolve("Setzer, Wandering Gambler")).level == "FULL"


# -- the table: Alice (Krenko, her commander), Bob and Carol ------------------------------------------------------------------------------------
def table(cards, mine=(), bob=(), carol=(), players=3):
    seats = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (9, "Forest")])),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (10, "Island")])),
             PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in carol), (10, "Mountain")]))][:players]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    for pid in s.state.players:  # (a wall each, so that combat waits for the blockers to be declared)
        act(s, pid, type="create_token", player=pid, token={"name": f"Wall {pid}", "type_line": "Token Creature — Wall", "power": "0",
                                                             "toughness": "4", "text": "Defender"})
    return s


def hasty(s, pid, name, pt="2/2"):
    """A creature that can attack this turn (302.6)."""
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": p, "toughness": t, "text": "Haste"})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def of(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def named(s, name, zone="battlefield"):
    return [s.state.cards[c.id] for c in s.state.cards.values() if c.name == name and c.zone.endswith(f":{zone}")]


def attacking(c):
    return c.attacking.id if c.attacking is not None else None


def to_attack(s, turn, pid="p1"):
    until(s, lambda s: s.state.turn.number == turn and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers" and s.state.rules.decision.player == pid)


def declare(s, *pairs, pid="p1"):
    act(s, pid, type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


def to_blocks(s, limit=40):
    """Let the attack triggers resolve, up to the declare blockers step (the walls make the defenders declare)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_blockers", "declare_attackers"):
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never got to blockers")


def answer(s, label):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label.lower() == label)])


# -- 508.4: for each opponent, a token attacking that opponent (Stampede Surfer, Veteran Soldier) --------------------------------------------------
def test_stampede_surfer_makes_a_boar_attacking_each_opponent(cards):
    s = table(cards, mine=("Stampede Surfer",))
    surfer = put(s, "Stampede Surfer")  # (haste)
    to_attack(s, 1)
    declare(s, (surfer, "p2"))
    to_blocks(s)
    boars = named(s, "Boar")
    assert sorted(attacking(b) for b in boars) == ["p2", "p3"] and all(b.tapped and b.controller == "p1" for b in boars)
    assert [(of(s, b).pt, of(s, b).colors) for b in boars] == [((2, 2), {"G"})] * 2
    check(s)
    through_combat(s)  # (the Boars were never declared as attackers; they deal damage like any attacker)
    assert s.state.players["p3"].life == 40 - 2 and s.state.players["p2"].life < s.state.players["p3"].life
    check(s)


def test_stampede_surfer_with_doubling_season_two_boars_attack_each_opponent(cards):
    """614.16: each opponent's creation is doubled by Doubling Season, and the added tokens enter tapped and attacking the same opponent."""
    s = table(cards, mine=("Stampede Surfer", "Doubling Season"))
    put(s, "Doubling Season")
    surfer = put(s, "Stampede Surfer")
    to_attack(s, 1)
    declare(s, (surfer, "p3"))
    to_blocks(s)
    boars = named(s, "Boar")
    assert sorted(attacking(b) for b in boars) == ["p2", "p2", "p3", "p3"] and all(b.tapped for b in boars)
    check(s)


def veteran_table(cards):
    s = table(cards, mine=("Veteran Soldier",))
    put(s, "Veteran Soldier")
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    return s, krenko


def test_veteran_soldier_grants_the_commander_a_soldier_for_each_opponent_when_none_has_more_life(cards):
    s, krenko = veteran_table(cards)
    assert any(ab.kind == "triggered" and "tapped and attacking that opponent" in ab.text for ab in of(s, krenko).abilities)
    to_attack(s, 4)  # (Alice's second turn: Krenko is no longer summoning sick)
    declare(s, (krenko, "p2"))
    to_blocks(s)
    soldiers = named(s, "Soldier")
    assert sorted(attacking(c) for c in soldiers) == ["p2", "p3"] and all(c.tapped for c in soldiers)
    check(s)


def test_veteran_soldier_makes_nothing_when_an_opponent_has_more_life_than_the_player_attacked(cards):
    s, krenko = veteran_table(cards)
    act(s, "p3", type="set_life", player="p3", value=50)
    to_attack(s, 4)
    declare(s, (krenko, "p2"))  # (603.4: the intervening "if" is false as it triggers)
    to_blocks(s)
    assert not named(s, "Soldier")
    check(s)


# -- 508.4, 506.3b: another player creates the token (Ellie, Najeela) ----------------------------------------------------------------------------
def test_ellie_the_attacking_player_creates_a_zombie_attacking_the_opponent_they_attacked(cards):
    s = table(cards, mine=("Ellie, Brick Master",))
    put(s, "Ellie, Brick Master")
    wolf = hasty(s, "p2", "Wolf", "2/2")
    to_attack(s, 2, "p2")
    declare(s, (wolf, "p3"), pid="p2")  # Bob attacks Carol, one of Alice's opponents
    to_blocks(s)
    (zombie,) = named(s, "Cordyceps Infected")
    assert zombie.controller == "p2" and zombie.tapped and attacking(zombie) == "p3"
    assert of(s, zombie).pt == (1, 1) and of(s, zombie).colors == {"B"}
    check(s)


def test_combat_calligrapher_the_attacking_player_creates_a_flying_inkling_attacking_the_opponent(cards):
    s = table(cards, mine=("Combat Calligrapher",))
    put(s, "Combat Calligrapher")
    wolf = hasty(s, "p2", "Wolf", "2/2")
    to_attack(s, 2, "p2")
    declare(s, (wolf, "p3"), pid="p2")
    to_blocks(s)
    (inkling,) = named(s, "Inkling")
    assert inkling.controller == "p2" and inkling.tapped and attacking(inkling) == "p3"
    assert of(s, inkling).pt == (2, 1) and of(s, inkling).colors == {"W", "B"} and "flying" in of(s, inkling).keywords
    check(s)


def test_ellie_does_not_trigger_when_the_attack_is_against_alice(cards):
    s = table(cards, mine=("Ellie, Brick Master",))
    put(s, "Ellie, Brick Master")
    wolf = hasty(s, "p2", "Wolf", "2/2")
    to_attack(s, 2, "p2")
    declare(s, (wolf, "p1"), pid="p2")  # (Alice is not one of her own opponents)
    to_blocks(s)
    assert not named(s, "Cordyceps Infected")
    check(s)


def najeela_table(cards, season=False):
    s = table(cards, mine=("Najeela, the Blade-Blossom", *(("Doubling Season",) if season else ())), players=2)
    if season:
        put(s, "Doubling Season")
    najeela = put(s, "Najeela, the Blade-Blossom")
    to_attack(s, 3)  # (Alice's second turn)
    declare(s, (najeela, "p2"))
    return s


def test_najeela_may_have_the_warriors_controller_create_a_warrior_tapped_and_attacking(cards):
    s = najeela_table(cards)
    answer(s, "yes")
    to_blocks(s)
    (warrior,) = [w for w in named(s, "Warrior") if w.is_token]
    assert warrior.tapped and attacking(warrior) == "p2" and warrior.controller == "p1"
    check(s)


def test_najeela_with_doubling_season_both_warriors_enter_attacking(cards):
    """614.16: Doubling Season doubles the creation; both tokens are created tapped and attacking (508.4)."""
    s = najeela_table(cards, season=True)
    answer(s, "yes")
    to_blocks(s)
    warriors = [w for w in named(s, "Warrior") if w.is_token]
    assert len(warriors) == 2 and all(w.tapped and attacking(w) == "p2" for w in warriors)
    check(s)


def test_najeela_declined_makes_nothing(cards):
    s = najeela_table(cards)
    answer(s, "no")
    to_blocks(s)
    assert not [w for w in named(s, "Warrior") if w.is_token]
    check(s)


# -- 301.7, 702.122a: Vehicle tokens (Mu Yanling, Lita) ----------------------------------------------------------------------------------------
def crew_index(s, c):
    return next(ab.index for ab in of(s, c).abilities if ab.text.startswith("Crew"))


def cast_mu_yanling(s):
    muyanling = card_named(s, "Mu Yanling, Wind Rider")
    act(s, "p1", type="move", card_ids=[muyanling.id], to={"zone": "hand"})
    mana(s, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=muyanling.id)
    settle(s)
    return muyanling


def test_mu_yanling_makes_a_vehicle_that_crews_and_has_flying(cards):
    s = table(cards, mine=("Mu Yanling, Wind Rider",), players=2)
    muyanling = cast_mu_yanling(s)
    (vehicle,) = named(s, "Vehicle")
    ch = of(s, vehicle)
    assert vehicle.is_token and "Artifact" in ch.types and "Vehicle" in ch.subtypes and not ch.is_creature  # (301.7a: no P/T-as-creature yet)
    printed = chars.of(s.state.cards[vehicle.id], s.cards)  # (208.3: a noncreature permanent has no P/T: the token's printed values)
    assert (printed.power, printed.toughness) == ("3", "2") and (ch.power, ch.toughness) == (None, None)
    assert not ch.colors and "flying" in ch.keywords  # ("Vehicles you control have flying.")
    assert any(ab.text.startswith("Crew 1") for ab in ch.abilities)
    check(s)
    act(s, "p1", type="activate_ability", card_id=vehicle.id, ability=crew_index(s, vehicle), crew=[muyanling.id])
    settle(s)
    assert of(s, vehicle).is_creature and of(s, vehicle).pt == (3, 2)  # (301.7b, 702.122a: until end of turn)
    check(s)


def test_mu_yanling_with_doubling_season_makes_two_vehicles(cards):
    s = table(cards, mine=("Mu Yanling, Wind Rider", "Doubling Season"), players=2)
    put(s, "Doubling Season")
    cast_mu_yanling(s)
    assert len(named(s, "Vehicle")) == 2
    check(s)


def test_lita_makes_a_zeppelin_that_needs_three_power_to_crew(cards):
    s = table(cards, mine=("Lita, Mechanical Engineer",), players=2)
    lita = put(s, "Lita, Mechanical Engineer")
    ogre = hasty(s, "p1", "Ogre", "3/3")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (Lita is no longer summoning sick)
    ability = next(ab.index for ab in of(s, lita).abilities if ab.kind == "activated")
    mana(s, W=1, C=3)
    act(s, "p1", type="activate_ability", card_id=lita.id, ability=ability)
    settle(s)
    (zeppelin,) = named(s, "Zeppelin")
    ch = of(s, zeppelin)
    printed = chars.of(s.state.cards[zeppelin.id], s.cards)  # (208.3: no P/T until it's a creature; the token's printed 5/5)
    assert "Vehicle" in ch.subtypes and "Artifact" in ch.types and not ch.is_creature and (printed.power, printed.toughness) == ("5", "5")
    assert "flying" in ch.keywords and any(a.text.startswith("Crew 3") for a in ch.abilities)
    act(s, "p1", type="activate_ability", card_id=zeppelin.id, ability=crew_index(s, zeppelin), crew=[ogre.id])
    settle(s)
    assert of(s, zeppelin).is_creature and s.state.cards[ogre.id].tapped
    check(s)


# -- 111.10, 608.2d: "create your choice of a Clue token, a Food token, or a Treasure token" (The Third Doctor) ------------------------------------
def cast_third_doctor(s):
    doctor = card_named(s, "The Third Doctor")
    act(s, "p1", type="move", card_ids=[doctor.id], to={"zone": "hand"})
    mana(s, G=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=doctor.id)
    for _ in range(10):  # (the enters trigger resolves: the choice comes up)
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one":
            return doctor, d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


@pytest.mark.parametrize("kind, text", [("Food", "{2}, {T}, Sacrifice this token: You gain 3 life."), ("Clue", "{2}, Sacrifice this token: Draw a card."),
                                        ("Treasure", "{T}, Sacrifice this token: Add one mana of any color.")])
def test_third_doctor_creates_the_token_its_controller_chooses(cards, kind, text):
    s = table(cards, mine=("The Third Doctor",), players=2)
    doctor, d = cast_third_doctor(s)
    assert d.player == "p1" and sorted(o.label for o in d.options) == ["Clue token", "Food token", "Treasure token"]
    check(s)  # (a save and a load with the choice open)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == f"{kind} token")])
    settle(s)
    (made,) = named(s, kind)
    assert made.is_token and any(ab.text == text for ab in of(s, made).abilities) and len(named(s, "Food") + named(s, "Clue") + named(s, "Treasure")) == 1
    assert of(s, doctor).pt == (int(of(s, doctor).power) + 1, int(of(s, doctor).toughness) + 1)  # ("gets +1/+1 for each noncreature token you control": the one just made)
    check(s)


def test_third_doctor_with_doubling_season_the_chosen_token_is_made_twice(cards):
    s = table(cards, mine=("The Third Doctor", "Doubling Season"), players=2)
    put(s, "Doubling Season")
    _, d = cast_third_doctor(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Clue token")])
    settle(s)
    assert len(named(s, "Clue")) == 2 and not named(s, "Food") and not named(s, "Treasure")
    check(s)


# -- a trailing "if" after a token with keywords (HYDRA Troopers) ----------------------------------------------------------------------------------
def hydra_table(cards, in_graveyard):
    s = table(cards, mine=("HYDRA Troopers", "Grizzly Bears", "Llanowar Elves"), players=2)
    for name in in_graveyard:
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"zone": "graveyard"})
    troopers = card_named(s, "HYDRA Troopers")
    act(s, "p1", type="move", card_ids=[troopers.id], to={"zone": "hand"})
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=troopers.id)
    settle(s)
    return s


def test_hydra_troopers_makes_the_tapped_villain_with_menace_when_two_creature_cards_are_in_the_graveyard(cards):
    s = hydra_table(cards, ("Grizzly Bears", "Llanowar Elves"))
    (villain,) = [c for c in named(s, "Villain") if c.is_token]
    assert villain.tapped and of(s, villain).pt == (2, 1) and "menace" in of(s, villain).keywords and of(s, villain).colors == {"B"}
    assert len(s.state.zones["p1:graveyard"]) == 2  # (nothing milled)
    check(s)


def test_hydra_troopers_mills_two_cards_otherwise(cards):
    s = hydra_table(cards, ())
    assert not [c for c in named(s, "Villain") if c.is_token] and len(s.state.zones["p1:graveyard"]) == 2
    check(s)


# -- the token wordings that follow a count, a keyword or an earlier instruction -----------------------------------------------------------------
def test_gyome_makes_a_food_for_each_nontoken_creature_that_entered_under_your_control_this_turn(cards):
    s = table(cards, mine=("Gyome, Master Chef", "Grizzly Bears", "Llanowar Elves"), players=2)
    for name in ("Gyome, Master Chef", "Grizzly Bears", "Llanowar Elves"):
        put(s, name)
    hasty(s, "p1", "Goblin Token", "1/1")  # (a token is no nontoken creature)
    until(s, lambda s: len(named(s, "Food")) >= 3 or s.state.turn.number > 2, limit=400)  # (at Alice's end step; the table goes on to Bob's turn by itself)
    settle(s)
    assert len(named(s, "Food")) == 3  # (Gyome, the Bears and the Elves: not the two Walls or the Goblin)
    check(s)


def test_gyome_counts_the_creature_that_entered_and_has_died_since(cards):
    """The ruling: Gyome counts all nontoken creatures that entered under your control this turn, even if some are no longer on the battlefield."""
    s = table(cards, mine=("Gyome, Master Chef", "Grizzly Bears", "Llanowar Elves"), players=2)
    for name in ("Gyome, Master Chef", "Grizzly Bears", "Llanowar Elves"):
        put(s, name)
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="set_damage", card_ids=[bears.id], value=99)  # (lethal damage: it dies as the engine next looks at the table, 704.5g)
    act(s, s.state.rules.priority, type="pass_priority")
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    until(s, lambda s: len(named(s, "Food")) >= 3 or s.state.turn.number > 2, limit=400)
    settle(s)
    assert len(named(s, "Food")) == 3
    check(s)


def test_emergent_sequence_counts_the_lands_that_entered_this_turn_with_the_one_it_fetched(cards):
    s = table(cards, mine=("Emergent Sequence",), players=2)
    put(s, "Forest")  # (a land that entered under Alice's control this turn)
    sequence = card_named(s, "Emergent Sequence")
    act(s, "p1", type="move", card_ids=[sequence.id], to={"zone": "hand"})
    mana(s, G=1, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=sequence.id)
    settle(s)
    fractals = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.counters.get("+1/+1")]
    assert len(fractals) == 1 and fractals[0].counters["+1/+1"] == 2  # (the Forest from the hand and the one it fetched: the ruling counts the fetched land)
    ch = of(s, fractals[0])
    assert ch.is_creature and "Land" in ch.types and "Fractal" in ch.subtypes and ch.colors == {"G", "U"} and ch.pt == (2, 2)
    check(s)


def test_falcon_and_redwing_makes_that_many_birds_then_grows(cards):
    s = table(cards, mine=("Falcon and Redwing",), players=2)
    falcon = put(s, "Falcon and Redwing")
    power = of(s, falcon).pt[0]
    to_attack(s, 3)
    declare(s, (falcon, "p2"))
    through_combat(s)
    birds = named(s, "Bird")
    assert len(birds) == power and all("flying" in of(s, b).keywords for b in birds)  # (as many as the combat damage dealt)
    assert s.state.cards[falcon.id].counters.get("+1/+1") == 1 and s.state.players["p2"].life == 40 - power
    check(s)


def test_davros_makes_a_dalek_when_an_opponent_lost_three_life_then_that_opponent_faces_the_choice(cards):
    s = table(cards, mine=("Davros, Dalek Creator",), players=2)
    put(s, "Davros, Dalek Creator")
    ogre = hasty(s, "p1", "Ogre", "3/3")
    to_attack(s, 1)
    declare(s, (ogre, "p2"))
    through_combat(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one" and s.state.rules.decision.player == "p2",
          limit=80)
    (dalek,) = named(s, "Dalek")
    assert "menace" in of(s, dalek).keywords and of(s, dalek).pt == (3, 3) and "Artifact" in of(s, dalek).types
    d = s.state.rules.decision  # (701.55: the opponent who lost 3 life faces a villainous choice)
    assert sorted(o.label for o in d.options) == ["That player discards a card", "You draw a card"]
    check(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "You draw a card")])
    settle(s)
    check(s)


# -- what stays refused --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    # "that player" in a trigger about a player attacking one of your opponents is the attacker, not the one attacked
    "Whenever a player attacks one of your opponents, that attacking player creates a tapped 1/1 black Fungus Zombie creature token that's attacking that player.",
    # a Vehicle with a quoted ability the engine can't run, "crew" on anything but a Vehicle, a printed P/T on another noncreature artifact
    'When this creature enters, create a 3/2 colorless Vehicle artifact token with crew 1 and "Whenever this token attacks, harmonize the aether."',
    "When this creature enters, create a 1/1 white Soldier creature token with crew 1.",
    "When this creature enters, create a 3/2 colorless Equipment artifact token.",
    # X with no definition
    "When this creature enters, create an X/X colorless Vehicle artifact token with crew 2.",
    # (Tomik's and Katilda's quoted grants are read since wave 44C: tests/test_rules_wave44c_*.py)
    # ("each opponent dealt damage" is read since wave 52B: Malcolm, tests/test_rules_wave52b_small.py. "for each player being attacked" is read since wave 40A: Commander Liara Portyr's ruling of
    # 2022-06-10 — a player whose planeswalker is attacked, and who isn't attacked too, doesn't count; tests/test_rules_wave40a_if_you_do.py)
])
def test_refused(text):
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Test Card", "Creature — Test", text)
    assert coverage.of_characteristics(chs).level != "FULL", text
