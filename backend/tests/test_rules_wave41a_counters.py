"""Wave 41A: the counters family, second pass, commanders first (CR 2026-09-25, real Oracle text, tests/fixtures/wave41a_counters_cards.json from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 603.10a, 608.2h: a leaves-the-battlefield ability looks back in time at the object as it last existed, its counters too. Reyhan: "if it had one or more
  +1/+1 counters on it, you may put that many +1/+1 counters on target creature" (an intervening "if" over an optional ability, and "that many" the number it
  had); Omarthis: "manifest a number of cards … equal to the number of counters on it"; Selfless Police Captain: "put its +1/+1 counters on target creature";
  Drizzt: "if it had power greater than Drizzt's power … equal to the difference" (checked again as each trigger resolves, ruling 2021-07-23). 122.6: every put
  goes through the counter choke point, so Hardened Scales / Doubling Season apply.
* 109.2, 700.4, 603.6c: "a creature … dies or is put into exile" (Athreos) is the creature, a permanent, put into exile from the battlefield; "is put into the
  command zone" (Reyhan, 903.9b: a commander that would go to its hand goes there instead); "is returned to its owner's hand" (Justice) left the battlefield for a
  hand; "another creature you control or a land you control is put into a graveyard from the battlefield" (Long Feng) and "an attacking creature you control or a
  blocking creature an opponent controls dies" (Death Tyrant: the dead object was attacking / blocking, 603.10a) are one event with two descriptions, one trigger
  however many it fits (603.2).
* 603.4, 700.4: "if it didn't die" (Taeko) is a fact about where the object went. 724: "while you're the monarch" (Tamiyo, Emberwilde Captain) is part of the trigger
  event, read as it happens (603.2; the ruling of 2020-11-10: no second look). 105.2: "a red source you control deals damage to one or more permanents and/or
  players" (The Red Terror) is its color as it dealt it.
* 614.1c, 903.8: "enters with two +1/+1 counters on it for each time you've cast your commander from the command zone this game" (The Swarmlord).
* 508.1, 400.7: "each creature you control that didn't attack or enter this turn" (The Fifth Doctor). 605.1a: "Add {U} for each counter on Nardole" (any kind).
  702.62b: "each suspended card you own" (Rose Tyler). "you control a prime number of lands" and "that many" (Zimone, ruling 2024-09-20); "the number of attacking
  creatures is greater than the number of quest counters on ED-E" (ruling 2024-03-08): both counted as it triggers and as it resolves (603.4).
* 611.2a: "up to one other target creature loses all abilities" with no duration lasts for the rest of the game (Abigale, ruling 2025-11-17), and the keyword counters put
  after it (613.7c, 122.1b) still give their keywords; "She loses all abilities and gains haste" of the object Hellcat returns.
* 702.62a-b: "Put three time counters on it. If it doesn't have suspend, it gains suspend." after "exile cards from the top of your library until you exile a
  nonland card" (The Tenth Doctor). 207.2d: a flavor word may carry a mark on a letter (Spider-Man India's "Pavitr's Sevā"); 201.5: a plural name's own "them"
  (Tui and La).
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
from tests.test_rules_conditionals import counters
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand

SYR = "Syr Vondam, Sunstar Exemplar"  # (PARTIAL: its second ability, a power check as it leaves, stays manual)
GRIST = "Grist, Voracious Larva // Grist, the Plague Swarm"  # (PARTIAL: its "isn't on the battlefield" static stays manual)
DATA = json.loads((Path(__file__).parent / "fixtures" / "wave41a_counters_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
MANUAL = json.loads((Path(__file__).parent / "fixtures" / "wave41a_manual_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="w41a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate([*DATA, *MANUAL]) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA if c["name"] not in ("Hardened Scales", "Doubling Season", "Stone Rain", "Dryad Arbor", "Zombify", GRIST, SYR)]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def answer(s, *picks, limit=60):
    """Resolve everything; the decisions that come up are answered from ``picks`` in turn (an id, a label or a list of them), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            want = picks.pop(0) if picks else None
            wants = [want] if isinstance(want, str) else list(want or [])
            ids = [o.id for o in d.options if o.id in wants or o.label in wants] or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, pid="p1", targets=None, x=None, picks=(), **m):
    """Cast ``name`` from the hand with this mana and let it resolve (a spell enters with its counters, 614.1c: moving a card by hand doesn't)."""
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id, **({"targets": targets} if targets else {}), **({"x_value": x} if x is not None else {}))
    answer(s, *picks)
    return card_named(s, name, pid)


def zone(s, c):
    return s.state.cards[c.id].zone


def add_counters(s, c, n, kind="+1/+1"):
    """By hand (the table's own counter action: no replacement effect looks at it)."""
    act(s, c.controller if hasattr(c, "controller") else "p1", type="counter", card_ids=[c.id], kind=kind, delta=n)


@pytest.mark.parametrize("name", FULL)
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("name", [c["name"] for c in MANUAL if c["name"] not in ("Sensei Golden-Tail", "Kalain, Reclusive Painter", "Brawn, Amadeus Cho", "Gluntch, the Bestower", "Super-Adaptoid", "Rinoa, Angel Wing", "Agent Maria Hill")])  # (Rinoa: test_rules_wave110o_a.py; Maria Hill: test_rules_wave110j_s7.py)  # (wave 110D: Brawn, Gluntch, Super-Adaptoid are FULL now)  # (wave 50J: Sensei's bushido is given as the ability it is, test_rules_wave50j_small.py)
def test_the_counters_cards_that_are_not_read_stay_manual(cards, name):
    """Rinoa ("one of them" from a batch of deaths), Tyvar (a mana ability resolving), Maria Hill (a teamwork cost) are refused."""
    assert coverage.of_card_data(cards.resolve(name)).level != "FULL", name


# -- Reyhan, Last of the Abzan: "if it had one or more +1/+1 counters on it, you may put that many +1/+1 counters on target creature" --------------
def test_reyhan_puts_the_counters_a_dying_creature_had_on_a_creature_through_hardened_scales(cards):
    """603.10a / 608.2h: Grizzly Bears had two +1/+1 counters as it died; 122.6: Hardened Scales makes the put three."""
    s = build(cards, ["Reyhan, Last of the Abzan", "Grizzly Bears", "Hardened Scales", "Murder"], [])
    reyhan = cast(s, "Reyhan, Last of the Abzan", B=1, G=1, C=1)
    assert counters(s, reyhan) == 3
    bears = put(s, "Grizzly Bears")
    put(s, "Hardened Scales")
    add_counters(s, bears, 2)
    cast(s, "Murder", targets=[bears.id], B=2, C=1)
    assert zone(s, bears) == "p1:graveyard" and counters(s, reyhan) == 3 + 2 + 1
    check(s)


def test_reyhan_does_nothing_for_a_creature_that_had_no_counters(cards):
    s = build(cards, ["Reyhan, Last of the Abzan", "Grizzly Bears", "Murder"], [])
    reyhan = cast(s, "Reyhan, Last of the Abzan", B=1, G=1, C=1)
    bears = put(s, "Grizzly Bears")
    cast(s, "Murder", targets=[bears.id], B=2, C=1)
    assert zone(s, bears) == "p1:graveyard" and counters(s, reyhan) == 3 and not s.state.zones.get("stack")
    check(s)


def test_reyhan_triggers_when_a_commander_goes_to_the_command_zone_instead_of_the_hand(cards):
    """903.9b: the owner of a commander that would be put into their hand puts it into the command zone instead; it left the battlefield for the command zone (Reyhan)."""
    s = build(cards, ["Reyhan, Last of the Abzan", "Capsize"], [])
    reyhan = cast(s, "Reyhan, Last of the Abzan", B=1, G=1, C=1)
    krenko = put(s, "Krenko, Mob Boss")
    add_counters(s, krenko, 2)
    mana(s, "p1", U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Capsize").id, targets=[krenko.id])
    answer(s, "Command zone")
    assert zone(s, krenko) == "p1:command" and counters(s, reyhan) == 3 + 2
    check(s)


# -- Omarthis, Ghostfire Initiate: "When Omarthis dies, manifest a number of cards from the top of your library equal to the number of counters on it" --
def manifested(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.controller == pid and c.zone == f"{pid}:battlefield" and c.face_down]


@pytest.mark.parametrize("extra, entered", [(None, 2), ("Doubling Season", 4)])
def test_omarthis_manifests_as_many_cards_as_the_counters_it_had_of_every_kind(cards, extra, entered):
    """603.10a / 608.2h: the number of counters of any kind on it as it last existed (122.1); 122.6: Doubling Season doubles the X it enters with; 701.40a."""
    s = build(cards, ["Omarthis, Ghostfire Initiate", "Murder", *([extra] if extra else [])], [])
    if extra:
        put(s, extra)
    omarthis = cast(s, "Omarthis, Ghostfire Initiate", x=2, C=4)
    assert counters(s, omarthis) == entered
    add_counters(s, omarthis, 1, "oil")
    to_hand(s, "Murder")
    library = len(s.state.zones["p1:library"])
    cast(s, "Murder", targets=[omarthis.id], B=2, C=1)
    assert zone(s, omarthis) == "p1:graveyard" and len(manifested(s)) == entered + 1
    assert len(s.state.zones["p1:library"]) == library - (entered + 1)
    check(s)


# -- Drizzt Do'Urden: "Whenever a creature dies, if it had power greater than Drizzt's power, put a number of +1/+1 counters on Drizzt equal to the difference" --
def test_drizzt_gets_counters_equal_to_the_difference_in_power_of_a_bigger_creature_that_died(cards):
    """608.2h: the dying creature's power as it last existed (5, with its two counters); Drizzt's is 3: the difference is 2. A smaller one gives nothing."""
    s = build(cards, ["Drizzt Do'Urden", "Grizzly Bears", "Llanowar Elves", "Murder"], [])
    drizzt = put(s, "Drizzt Do'Urden")
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    add_counters(s, bears, 3)  # a 5/5
    cast(s, "Murder", targets=[elves.id], B=2, C=1)  # a 1/1: power 1 is not greater than Drizzt's 3
    assert zone(s, elves) == "p1:graveyard" and counters(s, drizzt) == 0
    cast(s, "Murder", targets=[bears.id], B=2, C=1)
    assert zone(s, bears) == "p1:graveyard" and counters(s, drizzt) == 2
    check(s)


def test_drizzt_checks_the_power_again_as_each_trigger_resolves(cards):
    """The ruling of 2021-07-23: two 5-power creatures die at once, each triggers it; the first puts two counters (5 - 3), so Drizzt's power is 5 and the second's
    "greater than Drizzt's power" is false as it resolves (603.4)."""
    from tests.test_rules_conditionals import token_of

    s = build(cards, ["Drizzt Do'Urden", "Pyroclasm"], [])
    drizzt = put(s, "Drizzt Do'Urden")
    token_of(s, "p1", "Brute", "Token Creature — Brute", "5/1")
    token_of(s, "p1", "Brute", "Token Creature — Brute", "5/1")
    cast(s, "Pyroclasm", R=1, C=1)
    assert not [c for c in s.state.cards.values() if c.name == "Brute" and c.zone.endswith("battlefield")]
    assert counters(s, drizzt) == 2 and pt(s, "Drizzt Do'Urden") == (5, 5)
    check(s)


# -- Athreos, Shroud-Veiled: "Whenever a creature with a coin counter on it dies or is put into exile, return that card to the battlefield under your control" --
def on_battlefield(s, name, pid):
    return [c for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone == f"{pid}:battlefield"]


def test_athreos_returns_a_creature_with_a_coin_counter_that_dies_under_its_controller(cards):
    """700.4: it died; 400.7: what comes back is a new object, so it has no coin counter."""
    s = build(cards, ["Athreos, Shroud-Veiled", "Murder"], ["Grizzly Bears", "Llanowar Elves"])
    put(s, "Athreos, Shroud-Veiled")
    marked, plain = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    add_counters(s, marked, 1, "coin")
    cast(s, "Murder", targets=[plain.id], B=2, C=1)  # no coin counter: nothing returns
    assert zone(s, plain) == "p2:graveyard" and not on_battlefield(s, "Llanowar Elves", "p1")
    cast(s, "Murder", targets=[marked.id], B=2, C=1)
    (back,) = on_battlefield(s, "Grizzly Bears", "p1")
    assert back.id == marked.id and back.owner == "p2" and counters(s, back, "coin") == 0  # (Bob's card, back under Alice's control)
    check(s)


def test_athreos_returns_a_creature_with_a_coin_counter_that_is_exiled_too(cards):
    s = build(cards, ["Athreos, Shroud-Veiled", "Swords to Plowshares"], ["Grizzly Bears"])
    put(s, "Athreos, Shroud-Veiled")
    marked = put(s, "Grizzly Bears", "p2")
    add_counters(s, marked, 1, "coin")
    cast(s, "Swords to Plowshares", targets=[marked.id], W=1)
    assert on_battlefield(s, "Grizzly Bears", "p1") and not on_battlefield(s, "Grizzly Bears", "p2")
    check(s)


def test_athreos_has_no_card_to_return_for_a_token_with_a_coin_counter(cards):
    """111.7: a token that left the battlefield ceases to exist; "that card" is nothing, and nothing goes wrong."""
    from tests.test_rules_conditionals import token_of

    s = build(cards, ["Athreos, Shroud-Veiled", "Swords to Plowshares"], [])
    put(s, "Athreos, Shroud-Veiled")
    spirit = token_of(s, "p2", "Spirit", "Token Creature — Spirit", "1/1")
    add_counters(s, spirit, 1, "coin")
    cast(s, "Swords to Plowshares", targets=[spirit.id], W=1)
    assert not [c for c in s.state.cards.values() if c.zone.endswith("battlefield") and c.name == "Spirit"]
    check(s)


# -- Taeko, the Patient Avalanche: "Whenever another creature you control leaves the battlefield, if it didn't die, scry 1 and put a +1/+1 counter on Taeko" --
def test_taeko_grows_when_another_creature_of_yours_is_bounced_or_exiled_but_not_when_it_dies(cards):
    """700.4: a creature that went to a graveyard died; one that went to a hand or to exile left without dying (603.4: where it went is fixed once it left)."""
    s = build(cards, ["Taeko, the Patient Avalanche", "Grizzly Bears", "Llanowar Elves", "Young Wolf", "Murder", "Capsize", "Swords to Plowshares"], [])
    taeko = put(s, "Taeko, the Patient Avalanche")
    bears, elves, wolf = put(s, "Grizzly Bears"), put(s, "Llanowar Elves"), put(s, "Young Wolf")
    cast(s, "Murder", targets=[bears.id], B=2, C=1)
    assert zone(s, bears) == "p1:graveyard" and counters(s, taeko) == 0
    cast(s, "Capsize", targets=[elves.id], U=2, C=1)
    assert zone(s, elves) == "p1:hand" and counters(s, taeko) == 1
    cast(s, "Swords to Plowshares", targets=[wolf.id], W=1)
    assert zone(s, wolf) == "p1:exile" and counters(s, taeko) == 2
    check(s)


# -- Tamiyo, Upriser Crowned: "Whenever one or more creatures deal combat damage to you while you're the monarch, tap those creatures and put a stun counter on each" --
def through_combat(s, limit=80):
    """Play on to the second main phase; nobody blocks; the other decisions that come up are answered with their first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def swing(s, pid, names, target):
    """On ``pid``'s next turn ``names`` (their creatures, summoning sickness gone) attack ``target``; nobody blocks."""
    from tests.wave36a_kit import attack_as, ready, to_turn_of

    for n in names:
        ready(s, n, pid=pid)
    to_turn_of(s, pid)
    attack_as(s, pid, [card_named(s, n, pid) for n in names], target)
    through_combat(s)


@pytest.mark.parametrize("monarch, stunned", [("p1", 1), ("p2", 0)])
def test_tamiyo_taps_and_stuns_the_creatures_that_hurt_its_monarch_controller(cards, monarch, stunned):
    s = build(cards, ["Tamiyo, Upriser Crowned"], ["Grizzly Bears", "Young Wolf"])
    put(s, "Tamiyo, Upriser Crowned")
    bears, wolf = put(s, "Grizzly Bears", "p2"), put(s, "Young Wolf", "p2")
    act(s, "p1", type="set_monarch", player=monarch)
    swing(s, "p2", ["Grizzly Bears", "Young Wolf"], "p1")
    assert s.state.players["p1"].life == 40 - 2 - 1  # (both connected)
    for c in (bears, wolf):
        assert counters(s, c, "stun") == stunned and s.state.cards[c.id].tapped
    check(s)


# -- Long Feng, Grand Secretariat: "Whenever another creature you control or a land you control is put into a graveyard from the battlefield, …" ----------
def test_long_feng_puts_one_counter_for_a_creature_a_land_or_a_land_creature_that_dies(cards):
    """603.2: the two descriptions are of the one event; Dryad Arbor (a land creature) fits both and still triggers it once. Long Feng itself isn't "another"."""
    s = build(cards, ["Long Feng, Grand Secretariat", "Grizzly Bears", "Dryad Arbor", "Murder", "Stone Rain"], [])
    feng = put(s, "Long Feng, Grand Secretariat")
    bears, arbor, land = put(s, "Grizzly Bears"), put(s, "Dryad Arbor"), put(s, "Forest")
    cast(s, "Murder", targets=[bears.id], B=2, C=1)
    assert counters(s, feng) == 1
    cast(s, "Murder", targets=[arbor.id], B=2, C=1)
    assert zone(s, arbor) == "p1:graveyard" and counters(s, feng) == 2
    cast(s, "Stone Rain", targets=[land.id], R=1, C=2)
    assert zone(s, land) == "p1:graveyard" and counters(s, feng) == 3
    check(s)


# -- Death Tyrant: "Whenever an attacking creature you control or a blocking creature an opponent controls dies, create a 2/2 black Zombie creature token" ----
def test_death_tyrant_makes_a_zombie_for_each_of_its_two_kinds_of_creature_that_die(cards):
    """Alice's attacking Grizzly Bears and Bob's blocking one trade: two events at once, a Zombie for each (603.2); one that dies at rest is neither."""
    from tests.wave36a_kit import attack, block, next_own_turn

    s = build(cards, ["Death Tyrant", "Grizzly Bears", "Llanowar Elves", "Murder"], ["Grizzly Bears"])
    put(s, "Death Tyrant")
    mine, elves, theirs = put(s, "Grizzly Bears"), put(s, "Llanowar Elves"), put(s, "Grizzly Bears", "p2")
    next_own_turn(s)
    cast(s, "Murder", targets=[elves.id], B=2, C=1)  # not attacking or blocking
    zombies = lambda: [c for c in s.state.cards.values() if c.name == "Zombie" and c.zone == "p1:battlefield"]  # noqa: E731
    assert zone(s, elves) == "p1:graveyard" and not zombies()
    attack(s, mine)
    block(s, "p2", (theirs, mine))
    through_combat(s)
    assert zone(s, mine) == "p1:graveyard" and zone(s, theirs) == "p2:graveyard" and len(zombies()) == 2
    check(s)


# -- Justice, Vance Astrovik: "Whenever another nonland permanent you control is returned to its owner's hand, put a +1/+1 counter on Justice" ----------
def test_justice_grows_when_its_own_enter_trigger_bounces_a_permanent_of_yours(cards):
    """603.6c: the permanent left the battlefield for a hand while Justice was there; a creature of Bob's, or a land, doesn't count."""
    s = build(cards, ["Justice, Vance Astrovik", "Grizzly Bears", "Capsize"], ["Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves", "p2")
    justice = cast(s, "Justice, Vance Astrovik", U=1, C=2, picks=("Grizzly Bears",))  # (its enter trigger's target)
    assert zone(s, bears) == "p1:hand" and counters(s, justice) == 1
    cast(s, "Capsize", targets=[elves.id], U=2, C=1)  # Bob's creature: not "you control"
    assert zone(s, elves) == "p2:hand" and counters(s, justice) == 1
    check(s)


# -- The Swarmlord: "enters with two +1/+1 counters on it for each time you've cast your commander from the command zone this game" ---------------------
def table(cards, mine=(), theirs=(), commander="Krenko, Mob Boss"):
    """Alice (commander ``commander``) and Bob; ``mine`` / ``theirs`` are in Alice's / Bob's library; on to Alice's first main phase."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable
    from tests.test_rules_conditionals import until

    decks = [deck(cards, commander, [*((1, n) for n in mine), (20, "Forest")]), deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob"), decks, strict=True)], shuffle=False)), cards=cards)
    until(s, lambda s: s.state.turn.phase == "main1" and s.state.rules.decision is None)
    return s


@pytest.mark.parametrize("extra, first, second", [(None, 2, 4), ("Hardened Scales", 3, 5)])
def test_swarmlord_enters_with_counters_for_each_cast_from_the_command_zone_through_hardened_scales(cards, extra, first, second):
    """903.8: the second cast from the command zone costs {2} more and counts twice; 122.6 / 614.1c: it enters with them, Hardened Scales adds one to each put."""
    s = table(cards, ["Swords to Plowshares", *([extra] if extra else [])], commander="The Swarmlord")
    swarm = card_named(s, "The Swarmlord")
    if extra:
        put(s, extra)
    mana(s, "p1", G=1, U=1, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=swarm.id)
    answer(s)
    assert zone(s, swarm) == "p1:battlefield" and counters(s, swarm) == first
    cast(s, "Swords to Plowshares", targets=[swarm.id], W=1)
    answer(s, "Command zone")
    assert zone(s, swarm) == "p1:command"
    mana(s, "p1", G=1, U=1, R=1, C=5)  # {3}{G}{U}{R} and {2} of commander tax
    act(s, "p1", type="cast_spell", card_id=swarm.id)
    answer(s)
    assert zone(s, swarm) == "p1:battlefield" and counters(s, swarm) == second
    check(s)


# -- The Fifth Doctor: "At the beginning of your end step, put a +1/+1 counter on each creature you control that didn't attack or enter this turn. Untap those creatures" --
def test_the_fifth_doctor_counters_and_untaps_only_the_creatures_that_stayed_home_and_were_there_before(cards):
    """508.1, 400.7: Grizzly Bears attacked, Young Wolf was cast this turn; the Doctor himself and Llanowar Elves did neither, so both get a counter and untap."""
    from tests.wave36a_kit import attack, finish_turn, next_own_turn

    s = build(cards, ["The Fifth Doctor", "Grizzly Bears", "Llanowar Elves", "Young Wolf"], [])
    doctor, bears, elves = put(s, "The Fifth Doctor"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    next_own_turn(s)
    wolf = cast(s, "Young Wolf", G=1)
    act(s, "p1", type="tap", card_ids=[elves.id, doctor.id], tapped=True)
    attack(s, bears)
    through_combat(s)
    finish_turn(s)
    assert (counters(s, doctor), counters(s, elves), counters(s, bears), counters(s, wolf)) == (1, 1, 0, 0)
    assert not s.state.cards[elves.id].tapped and not s.state.cards[doctor.id].tapped
    check(s)


# -- Nardole, Resourceful Cyborg: "{T}: Add {U} for each counter on Nardole. Spend this mana only to cast noncreature spells" --------------------------
def test_nardole_adds_one_blue_per_counter_of_any_kind_for_noncreature_spells_only(cards):
    """605.1a, 122.1: a +1/+1 counter and an oil counter are two counters; the mana pays for Counterspell but not for the creature spell Merfolk Looter."""
    from app.rules.casting import castable
    from tests.wave36a_kit import next_own_turn

    s = build(cards, ["Nardole, Resourceful Cyborg", "Counterspell", "Merfolk Looter"], [])
    nardole = put(s, "Nardole, Resourceful Cyborg")
    next_own_turn(s)  # (no longer summoning sick: {T} may be paid, 302.6)
    spell, looter = to_hand(s, "Counterspell"), to_hand(s, "Merfolk Looter")
    can = lambda c: castable(s.state, "p1", s.state.cards[c.id], s.cards)  # noqa: E731
    assert not can(spell)  # (no counters: it adds nothing)
    add_counters(s, nardole, 1)
    assert not can(spell)  # {U}{U} is more than the one {U}
    add_counters(s, nardole, 1, "oil")
    assert can(spell) and not can(looter)  # two {U}: for a noncreature spell only
    check(s)


# -- The Red Terror: "Whenever a red source you control deals damage to one or more permanents and/or players, put a +1/+1 counter on The Red Terror" -----
def test_the_red_terror_counts_each_red_source_once_for_all_the_damage_it_deals_at_once(cards):
    """105.2 / 120.1: Lightning Bolt (a red source) to a player is one; Pyroclasm to three creatures at once is one more (603.2c); a green creature's combat damage isn't."""
    from tests.wave36a_kit import next_own_turn

    s = build(cards, ["The Red Terror", "Grizzly Bears", "Lightning Bolt", "Pyroclasm"], ["Llanowar Elves", "Grizzly Bears"])
    terror, bears = put(s, "The Red Terror"), put(s, "Grizzly Bears")
    put(s, "Llanowar Elves", "p2")
    put(s, "Grizzly Bears", "p2")
    next_own_turn(s)
    cast(s, "Lightning Bolt", targets=["p2"], R=1)
    assert s.state.players["p2"].life == 37 and counters(s, terror) == 1
    cast(s, "Pyroclasm", R=1, C=1)  # 2 damage to each of the five creatures
    assert counters(s, terror) == 2 and s.state.cards[terror.id].damage == 2 and zone(s, bears) == "p1:graveyard"
    check(s)


def test_the_red_terror_ignores_a_green_creatures_combat_damage_but_counts_a_red_ones(cards):
    from tests.wave36a_kit import attack, next_own_turn

    s = build(cards, ["The Red Terror", "Grizzly Bears", "Monastery Swiftspear"], [])
    terror = put(s, "The Red Terror")
    put(s, "Grizzly Bears")
    put(s, "Monastery Swiftspear")
    next_own_turn(s)
    attack(s, card_named(s, "Grizzly Bears"))
    through_combat(s)
    assert s.state.players["p2"].life == 38 and counters(s, terror) == 0
    next_own_turn(s)
    attack(s, card_named(s, "Monastery Swiftspear"))
    through_combat(s)
    assert s.state.players["p2"].life == 37 and counters(s, terror) == 1
    check(s)


# -- The Tenth Doctor: "Whenever you attack, exile cards from the top of your library until you exile a nonland card. Put three time counters on it. …" --
def test_the_tenth_doctor_suspends_the_first_nonland_card_it_exiles_from_the_top(cards):
    """702.62a-b: the land is exiled on the way, the nonland card stops it and is suspended with three time counters even though it had no suspend; at the
    beginning of its owner's upkeep one comes off (702.62b)."""
    from tests.wave36a_kit import attack, next_own_turn

    s = build(cards, ["The Tenth Doctor", "Grizzly Bears"], [])
    doctor = put(s, "The Tenth Doctor")
    next_own_turn(s)
    bears, forest = card_named(s, "Grizzly Bears"), next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "library"}, position="top")  # (the land is above the nonland card)
    attack(s, doctor)
    through_combat(s)
    assert zone(s, forest) == "p1:exile" and counters(s, forest, "time") == 0
    assert zone(s, bears) == "p1:exile" and counters(s, bears, "time") == 3 and bears.id in s.state.rules.suspended
    next_own_turn(s)
    assert counters(s, bears, "time") == 2  # (702.62b: one comes off at the beginning of its owner's upkeep)
    check(s)


# -- Selfless Police Captain: "When this creature leaves the battlefield, put its +1/+1 counters on target creature you control" --------------------------
@pytest.mark.parametrize("extra, moved", [(None, 3), ("Doubling Season", 6)])
def test_selfless_police_captain_puts_its_plus_one_counters_not_its_others_on_a_creature(cards, extra, moved):
    """122.8, 603.10a: the +1/+1 counters it had as it left (three; the oil counter isn't one) are put on the creature, through Doubling Season if it is out."""
    s = build(cards, ["Selfless Police Captain", "Grizzly Bears", "Swords to Plowshares", *([extra] if extra else [])], [])
    bears = put(s, "Grizzly Bears")
    captain = cast(s, "Selfless Police Captain", W=1, C=1)
    add_counters(s, captain, 2)
    add_counters(s, captain, 1, "oil")
    if extra:
        put(s, extra)
    cast(s, "Swords to Plowshares", targets=[captain.id], W=1, picks=("Grizzly Bears",))
    assert zone(s, captain) == "p1:exile" and counters(s, bears) == moved and counters(s, bears, "oil") == 0
    check(s)


# -- Rose Tyler: "put a time counter on it for each suspended card you own and each other permanent you control with a time counter on it" ----------------
def test_rose_tyler_counts_her_suspended_cards_and_her_other_permanents_with_time_counters(cards):
    """702.62b: Rift Bolt is suspended (in exile with suspend and a time counter): one; Grizzly Bears of Alice's has a time counter: one; Bob's doesn't count."""
    from tests.wave36a_kit import attack, next_own_turn

    s = build(cards, ["Rose Tyler", "Grizzly Bears", "Rift Bolt"], ["Grizzly Bears"])
    rose, bears, theirs = put(s, "Rose Tyler"), put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    add_counters(s, bears, 1, "time")
    add_counters(s, theirs, 1, "time")
    next_own_turn(s)
    mana(s, "p1", R=1)
    act(s, "p1", type="activate_ability", card_id=to_hand(s, "Rift Bolt").id, ability=1)  # "Suspend 1—{R}"
    attack(s, rose)
    through_combat(s)
    assert counters(s, rose, "time") == 2 and pt(s, "Rose Tyler") == (4, 4)  # ("Rose Tyler gets +1/+1 for each time counter on it")
    check(s)


# -- Abigale, Eloquent First-Year: "up to one other target creature loses all abilities. Put a flying counter, a first strike counter, and a lifelink counter on it" --
def test_abigale_strips_a_creature_of_its_abilities_and_the_keyword_counters_that_follow_still_work(cards):
    """611.2a: no duration, the rest of the game; 613.7c: the counters are put after, so their keywords (122.1b) come after the loss in layer 6."""
    from tests.wave36a_kit import next_own_turn

    s = build(cards, ["Abigale, Eloquent First-Year"], ["Monastery Swiftspear"])
    swift = put(s, "Monastery Swiftspear", "p2")
    assert {"haste", "prowess"} <= set(keywords(s, swift))
    cast(s, "Abigale, Eloquent First-Year", W=2, picks=("Monastery Swiftspear",))
    now = set(keywords(s, swift))
    assert not {"haste", "prowess"} & now and {"flying", "first strike", "lifelink"} <= now
    assert (counters(s, swift, "flying"), counters(s, swift, "first strike"), counters(s, swift, "lifelink")) == (1, 1, 1)
    next_own_turn(s)
    assert not {"haste", "prowess"} & set(keywords(s, swift))  # (it lasts)
    check(s)


# -- Hellcat, Undying Vigilante: "When Hellcat dies, return her to the battlefield under her owner's control with a +1/+1 counter on her. She loses all abilities and gains haste" --
def test_hellcat_comes_back_once_with_a_counter_no_abilities_but_haste(cards):
    """400.7: the new object has a +1/+1 counter (3/3), lost all abilities (611.2a: for good) and then gained haste (613.7b: later, so it has it); without her
    dies ability she stays dead the second time."""
    s = build(cards, ["Hellcat, Undying Vigilante", "Murder"], [])
    hellcat = cast(s, "Hellcat, Undying Vigilante", G=2)
    assert counters(s, hellcat) == 0 and pt(s, "Hellcat, Undying Vigilante") == (2, 2)
    cast(s, "Murder", targets=[hellcat.id], B=2, C=1)
    assert zone(s, hellcat) == "p1:battlefield" and counters(s, hellcat) == 1 and pt(s, "Hellcat, Undying Vigilante") == (3, 3)
    assert set(keywords(s, hellcat)) == {"haste"}
    cast(s, "Murder", targets=[hellcat.id], B=2, C=1)
    assert zone(s, hellcat) == "p1:graveyard"
    check(s)


# -- Opportunistic Dragon: "For as long as this creature remains on the battlefield, gain control of that permanent, it loses all abilities, and it can't attack or block" --
def test_opportunistic_dragon_strips_the_permanent_only_for_as_long_as_it_remains(cards):
    """611.2a: the wording without a duration is for good (Abigale), but inside "for as long as this creature remains on the battlefield" the loss of abilities is
    given that duration: with the Dragon gone the creature is its owner's again and has its abilities back."""
    s = build(cards, ["Opportunistic Dragon", "Murder"], ["Monastery Swiftspear"])
    swift = put(s, "Monastery Swiftspear", "p2")
    dragon = cast(s, "Opportunistic Dragon", R=2, C=2, picks=("Monastery Swiftspear",))
    assert zone(s, swift) == "p1:battlefield" and not {"haste", "prowess"} & set(keywords(s, swift))
    cast(s, "Murder", targets=[dragon.id], B=2, C=1)
    assert zone(s, dragon) == "p1:graveyard"
    assert zone(s, swift) == "p2:battlefield" and {"haste", "prowess"} <= set(keywords(s, swift))
    check(s)


# -- Grist, Voracious Larva: "Whenever Grist or another creature you control enters, if it entered from your graveyard or you cast it from your graveyard, you may pay {G}" --
def reanimate_next_to_grist(cards, answer_with):
    s = build(cards, [GRIST, "Zombify", "Grizzly Bears"], [])
    grist = put(s, GRIST)
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    mana(s, "p1", B=1, C=3, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Zombify").id, targets=[bears.id])
    answer(s, answer_with)
    assert zone(s, bears) == "p1:battlefield"
    return s, grist


@pytest.mark.parametrize("pick, face", [("Pay {G}", 1), ("Don't pay", 0)])
def test_grist_transforms_when_another_creature_enters_from_the_graveyard_and_its_controller_pays(cards, pick, face):
    """603.4: the "if" is about the creature that entered (it); "exile Grist, then return it … transformed" (712.14a) makes Grist, the Plague Swarm, a new object."""
    s, grist = reanimate_next_to_grist(cards, pick)
    assert s.state.cards[grist.id].face == face and s.state.cards[grist.id].zone == "p1:battlefield"
    check(s)


def test_grist_does_nothing_for_a_creature_that_enters_from_the_hand(cards):
    """603.4: it entered from the hand and wasn't cast from the graveyard: no trigger at all."""
    s = build(cards, [GRIST, "Grizzly Bears"], [])
    grist = put(s, GRIST)
    cast(s, "Grizzly Bears", G=2)
    assert not s.state.zones.get("stack") and s.state.rules.decision is None and s.state.cards[grist.id].face == 0
    check(s)


# -- Syr Vondam, Sunstar Exemplar: "Whenever another creature you control dies or is put into exile, put a +1/+1 counter on Syr Vondam and you gain 1 life" --
def test_syr_vondam_grows_and_gains_life_for_each_of_your_other_creatures_that_dies_or_is_exiled(cards):
    """109.2, 700.4: a creature put into exile is one exiled from the battlefield (603.6c); a creature of the opponent's, or a bounced one, isn't counted."""
    s = build(cards, [SYR, "Murder", "Swords to Plowshares", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    syr = put(s, SYR)
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    theirs = put(s, "Grizzly Bears", "p2")
    life = s.state.players["p1"].life
    cast(s, "Murder", targets=[theirs.id], B=2, C=1)
    assert counters(s, syr) == 0 and s.state.players["p1"].life == life
    cast(s, "Murder", targets=[bears.id], B=2, C=1)
    assert zone(s, bears) == "p1:graveyard" and counters(s, syr) == 1 and s.state.players["p1"].life == life + 1
    cast(s, "Swords to Plowshares", targets=[elves.id], W=1)
    assert zone(s, elves) == "p1:exile" and counters(s, syr) == 2 and s.state.players["p1"].life == life + 1 + 1 + 1  # (the Bears, the Elves, and Swords's own life for 1 power)
    check(s)


# -- Zimone, All-Questioning: "if a land entered the battlefield under your control this turn and you control a prime number of lands, create Primo … then put that many counters" --
@pytest.mark.parametrize("before, primo", [(2, 3), (3, 0)])
def test_zimone_makes_primo_with_as_many_counters_as_lands_when_that_number_is_prime(cards, before, primo):
    """Ruling 2024-09-20: counted as the ability triggers and again as it resolves; three lands (Zimone's end step, after a land drop) is prime, four is not."""
    from tests.wave36a_kit import finish_turn

    s = build(cards, ["Zimone, All-Questioning"], [])
    put(s, "Zimone, All-Questioning")
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"]
    act(s, "p1", type="move", card_ids=[c.id for c in forests[:before]], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[forests[before].id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forests[before].id)  # (the land that entered this turn; Zimone herself isn't a land)
    finish_turn(s)
    made = [c for c in s.state.cards.values() if c.name == "Primo, the Indivisible" and c.zone == "p1:battlefield"]
    assert len(made) == (1 if primo else 0) and all(counters(s, c) == primo for c in made)
    check(s)


# -- ED-E, Lonesome Eyebot: "Whenever you attack, if the number of attacking creatures is greater than the number of quest counters on ED-E, put a quest counter on it" --
def test_ede_grows_only_when_more_creatures_attack_than_it_has_quest_counters(cards):
    """603.4: 2 attackers > 0 counters: one; 1 attacker is not more than 1; 3 attackers > 1: a second."""
    from tests.wave36a_kit import attack, next_own_turn

    s = build(cards, ["ED-E, Lonesome Eyebot", "Grizzly Bears", "Llanowar Elves"], [])
    ede = put(s, "ED-E, Lonesome Eyebot")
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    for want, swing_with in ((1, [ede, bears]), (1, [bears]), (2, [ede, bears, elves])):
        next_own_turn(s)
        attack(s, *swing_with)
        through_combat(s)
        assert counters(s, ede, "quest") == want, (want, swing_with)
    check(s)


# -- Kid Loki: "Each creature you control that you've put one or more +1/+1 counters on this turn has hexproof" -------------------------------------------
def test_kid_loki_gives_hexproof_to_the_creatures_it_was_you_who_put_counters_on_this_turn_only(cards):
    """122.6: Young Wolf's undying puts the counter as it returns (a new object, but this turn's), and Kid Loki's own draw trigger puts one on him; the turn
    after, neither is hexproof (611.3a: it follows what happened this turn)."""
    from tests.wave36a_kit import next_own_turn

    s = build(cards, ["Kid Loki", "Young Wolf", "Grizzly Bears", "Murder", "Opt"], [])
    loki, wolf, bears = put(s, "Kid Loki"), put(s, "Young Wolf"), put(s, "Grizzly Bears")
    next_own_turn(s)
    assert "hexproof" not in keywords(s, wolf) and "hexproof" not in keywords(s, loki)
    cast(s, "Murder", targets=[wolf.id], B=2, C=1)  # undying: it comes back with a +1/+1 counter
    assert zone(s, wolf) == "p1:battlefield" and counters(s, wolf) == 1 and "hexproof" in keywords(s, wolf) and "hexproof" not in keywords(s, bears)
    cast(s, "Opt", U=1)  # the second card drawn this turn
    assert counters(s, loki) == 1 and "hexproof" in keywords(s, loki) and "hexproof" not in keywords(s, bears)
    next_own_turn(s)
    assert "hexproof" not in keywords(s, wolf) and "hexproof" not in keywords(s, loki) and counters(s, loki) == 1
    check(s)


# -- Raphael, the Muscle: "Double all damage that creatures you control with counters on them would deal" ----------------------------------------------
def test_raphael_doubles_the_damage_of_the_creatures_you_control_that_have_a_counter(cards):
    """609.7c, 614.1a: a source with a counter of any kind on it (the Bears' +1/+1 counter, 3 power) deals double, one without (Llanowar Elves) deals what it does."""
    from tests.wave36a_kit import attack, next_own_turn

    s = build(cards, ["Raphael, the Muscle", "Grizzly Bears", "Llanowar Elves"], [])
    put(s, "Raphael, the Muscle")
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    add_counters(s, bears, 1)
    next_own_turn(s)
    attack(s, bears, elves)
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 3 * 2 - 1
    check(s)


# -- Spider-Man India: "Pavitr's Sevā — Whenever you cast a creature spell, put a +1/+1 counter on target creature you control. It gains flying until end of turn" --
def keywords(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords


def test_spider_man_india_reads_a_flavor_word_with_a_mark_on_a_letter(cards):
    """207.2d: the flavor word has no rules meaning, whatever letters it is written with (Pavitr's Sevā)."""
    s = build(cards, ["Spider-Man India", "Grizzly Bears", "Llanowar Elves"], [])
    put(s, "Spider-Man India")
    elves = put(s, "Llanowar Elves")
    cast(s, "Grizzly Bears", G=2, picks=("Llanowar Elves",))
    assert counters(s, elves) == 1 and "flying" in keywords(s, elves)
    check(s)


# -- Tui and La, Moon and Ocean: "Whenever Tui and La become untapped, put a +1/+1 counter on them" ---------------------------------------------------
def test_tui_and_la_put_the_counter_on_themselves_when_they_untap(cards):
    """201.5: a plural name is the one object's own; "them" after its own event is that object. Untapping in the untap step makes the trigger."""
    from tests.wave36a_kit import next_own_turn

    s = build(cards, ["Tui and La, Moon and Ocean"], [])
    tui = put(s, "Tui and La, Moon and Ocean")
    act(s, "p1", type="tap", card_ids=[tui.id], tapped=True)
    assert counters(s, tui) == 0
    next_own_turn(s)  # (its untap step on the way)
    assert counters(s, tui) == 1
    check(s)


# -- Emberwilde Captain: "Whenever an opponent attacks you while you're the monarch, this creature deals damage to that player equal to …" ---------------
@pytest.mark.parametrize("monarch, hurt", [("p1", True), ("p2", False)])
def test_emberwilde_captain_only_hurts_an_attacker_while_its_controller_is_the_monarch(cards, monarch, hurt):
    """724, 603.2: "while you're the monarch" is part of the trigger event, looked at as the attack is declared."""
    s = build(cards, ["Emberwilde Captain"], ["Grizzly Bears"])
    put(s, "Emberwilde Captain")
    put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_monarch", player=monarch)
    swing(s, "p2", ["Grizzly Bears"], "p1")
    hand = len(s.state.zones["p2:hand"])
    assert s.state.players["p2"].life == (40 - hand if hurt else 40) and hand > 0
    check(s)


def test_emberwilde_captain_resolves_as_normal_when_the_monarch_changes_in_response(cards):
    """The ruling of 2020-11-10: "while you're the monarch" is part of the trigger event (603.2), not an intervening "if" (603.4): once it triggered, it resolves."""
    from tests.wave36a_kit import attack_as, ready, to_turn_of

    s = build(cards, ["Emberwilde Captain"], ["Grizzly Bears"])
    put(s, "Emberwilde Captain")
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="set_monarch", player="p1")
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack: the trigger can be answered before it resolves)
    ready(s, "Grizzly Bears", pid="p2")
    to_turn_of(s, "p2")
    attack_as(s, "p2", [bears], "p1")
    assert s.state.zones.get("stack") or s.state.rules.pending_triggers  # (the Captain's trigger)
    act(s, "p1", type="set_monarch", player="p2")  # … Bob becomes the monarch in response
    hand = len(s.state.zones["p2:hand"])
    through_combat(s)
    assert s.state.players["p2"].life == 40 - hand
    check(s)

# -- end --
