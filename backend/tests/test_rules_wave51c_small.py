"""Wave 51C: popular cards still short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave51c_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 608.2c, 118.12a: "Counter target noncreature spell unless its controller pays {1}. Ferocious - If you control a creature with power 4 or
  greater, counter that spell instead." (Stubborn Denial): the condition is checked as the spell resolves; when it holds nobody is offered a payment.
* 404.1, 608.2c: "Draw a card. If a graveyard has twenty or more cards in it, draw three cards instead." (Visions of Beyond): any player's graveyard.
* 402.2, 122.1: "Your maximum hand size is twenty." and "you win the game if there are twenty or more counters on it or you have twenty or more
  cards in hand" (Twenty-Toed Toad): counters of every kind together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, hand_size
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import pick, until_asked
from tests.test_rules_wave34b_activated import activate, attack, next_turn, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Stubborn Denial", "Visions of Beyond", "Twenty-Toed Toad", "Render Silent", "Void Winnower", "Desecrate Reality", "Gyruda, Doom of Depths", "Stitch Together", "Everybody Lives!", "Uncivil Unrest", "Collective Inferno", "Loading Zone", "Generous Plunderer", "Bloodroot Apothecary", "Urabrask's Forge", "Silkguard", "Eclipsed Realms", "Dawn-Blessed Pennant", "Zenith Chronicler", "Court of Ambition", "Fatal Push", "Case of the Ransacked Lab", "Case of the Locked Hothouse", "Case of the Shifting Visage", "Swarmyard Massacre", "Summon: Leviathan", "Thraben Charm", "Stonespeaker Crystal", "The Death of Gwen Stacy", "Reaver Titan"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def settle(s, answer="yes", limit=40):
    """Resolve everything; an optional ability is answered ``answer``, any other choice with its first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer] if answer in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


# -- Stubborn Denial ---------------------------------------------------------------------------------------------------------------------------
def deny_bolt(cards, ferocious_for):
    """Alice bolts Bob; Bob answers with Stubborn Denial; ``ferocious_for`` (p1 / p2 / None) controls a Craw Wurm (power 6) first."""
    s = build(cards, ["Lightning Bolt", "Craw Wurm"], ["Stubborn Denial", "Craw Wurm"])
    if ferocious_for:
        put(s, "Craw Wurm", ferocious_for)
    bolt = to_hand(s, "Lightning Bolt")
    denial = to_hand(s, "Stubborn Denial", "p2")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, "p2", U=1)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=denial.id, targets=[bolt.id])
    return s, bolt


@pytest.mark.parametrize("pays", [True, False])
def test_stubborn_denial_without_a_big_creature_asks_for_one(cards, pays):
    s, bolt = deny_bolt(cards, None)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["pay", "decline"]
    pick(s, "pay" if pays else "decline")
    settle(s)
    assert (life(s, "p2"), zone_of(s, "Lightning Bolt")) == ((37, "p1:graveyard") if pays else (40, "p1:graveyard"))
    check(s)


def test_stubborn_denial_counters_outright_with_a_power_four_creature(cards):
    s, bolt = deny_bolt(cards, "p2")
    assert until_asked(s) is None  # (nothing to pay: the spell is countered as the ability resolves)
    assert life(s, "p2") == 40 and zone_of(s, "Lightning Bolt") == "p1:graveyard"
    assert s.state.players["p1"].mana.get("C", 0) == 1  # (the {1} was never asked for)
    check(s)


def test_stubborn_denial_ignores_the_big_creature_of_the_spells_caster(cards):
    s, bolt = deny_bolt(cards, "p1")  # ("you control": Stubborn Denial's controller, Bob)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    pick(s, "pay")
    settle(s)
    assert life(s, "p2") == 37
    check(s)


# -- Visions of Beyond -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("owner,drawn", [("p2", 3), (None, 1)])
def test_visions_of_beyond_looks_at_every_graveyard(cards, owner, drawn):
    s = build(cards, ["Visions of Beyond"], islands=30)
    if owner:  # twenty cards into Bob's graveyard
        ids = [c.id for c in s.state.cards.values() if c.owner == owner and c.zone == f"{owner}:library"][:20]
        act(s, owner, type="move", card_ids=ids, to={"player": owner, "zone": "graveyard"})
    to_hand(s, "Visions of Beyond")
    mana(s, U=1, C=1)
    before = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Visions of Beyond").id)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before - 1 + drawn
    check(s)


# -- Twenty-Toed Toad --------------------------------------------------------------------------------------------------------------------------
def toad_table(cards, in_hand, counters=0):
    s = build(cards, ["Twenty-Toed Toad"], forests=45)
    toad = put(s, "Twenty-Toed Toad")
    if counters:
        act(s, "p1", type="counter", card_ids=[toad.id], kind="charge", delta=counters)
    next_turn(s)
    extra = in_hand - len(s.state.zones["p1:hand"])
    ids = [c.id for c in s.state.cards.values() if c.zone == "p1:library"][:extra]
    act(s, "p1", type="move", card_ids=ids, to={"player": "p1", "zone": "hand"})
    return s, toad


def test_toad_hand_size_is_twenty(cards):
    s = build(cards, ["Twenty-Toed Toad"])
    assert hand_size.maximum(Plan(s.state, "p1", s.cards, None), "p1") == 7
    put(s, "Twenty-Toed Toad")
    assert hand_size.maximum(Plan(s.state, "p1", s.cards, None), "p1") == 20
    check(s)


@pytest.mark.parametrize("in_hand,counters,wins", [(20, 0, True), (19, 0, False), (3, 20, True), (3, 19, False)])
def test_toad_wins_on_twenty_cards_or_twenty_counters(cards, in_hand, counters, wins):
    s, toad = toad_table(cards, in_hand, counters)
    stops(s)
    attack(s, toad)
    settle(s)
    assert (s.state.rules.winner == "p1") is wins
    check(s)


# -- Render Silent -----------------------------------------------------------------------------------------------------------------------------
def test_render_silent_stops_the_countered_spells_controller_only(cards):
    """"Counter target spell. Its controller can't cast spells this turn.": Alice (the spell's controller) can't cast; Bob (who cast Render Silent) is not limited."""
    s = build(cards, ["Lightning Bolt", "Grizzly Bears"], ["Render Silent"])
    bolt, bears = to_hand(s, "Lightning Bolt"), to_hand(s, "Grizzly Bears")
    silent = to_hand(s, "Render Silent", "p2")
    act(s, "p2", type="set_prefs", response="on")
    mana(s, "p2", W=1, U=2)
    mana(s, R=1, G=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=silent.id, targets=[bolt.id])
    settle(s)
    assert life(s, "p2") == 40 and zone_of(s, "Lightning Bolt") == "p1:graveyard"
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)
    assert [x["player"] for x in s.state.rules.cast_limits] == ["p1"]  # (not Bob, who cast Render Silent)
    check(s)


# -- Void Winnower -----------------------------------------------------------------------------------------------------------------------------
def test_void_winnower_stops_even_spells_of_opponents(cards):
    s = build(cards, ["Grizzly Bears", "Llanowar Elves"], ["Void Winnower"])
    put(s, "Void Winnower", "p2")
    bears, elves = to_hand(s, "Grizzly Bears"), to_hand(s, "Llanowar Elves")
    mana(s, G=3)
    with pytest.raises(ActionError):  # (mana value 2 is even)
        act(s, "p1", type="cast_spell", card_id=bears.id)
    act(s, "p1", type="cast_spell", card_id=elves.id)  # (mana value 1 is odd)
    settle(s)
    assert zone_of(s, "Llanowar Elves") == "p1:battlefield"
    check(s)


def to_blockers(s, limit=40):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blockers asked")


def test_void_winnower_stops_even_creatures_of_opponents_blocking(cards):
    s = build(cards, ["Void Winnower"], ["Grizzly Bears", "Llanowar Elves"])
    winnower = put(s, "Void Winnower")
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    next_turn(s)
    attack(s, winnower)
    to_blockers(s)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": winnower.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": elves.id, "attacker_id": winnower.id}])
    settle(s)
    assert zone_of(s, "Llanowar Elves", "p2") == "p2:graveyard"
    check(s)


# -- Desecrate Reality -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("paid", [{"C": 7}, {"G": 7}])
def test_desecrate_reality_even_exile_and_odd_return_with_adamant(cards, paid):
    s = build(cards, ["Desecrate Reality", "Llanowar Elves", "Grizzly Bears"], ["Grizzly Bears", "Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    mine = [card_named(s, n) for n in ("Llanowar Elves", "Grizzly Bears")]
    act(s, "p1", type="move", card_ids=[c.id for c in mine], to={"player": "p1", "zone": "graveyard"})
    desecrate = to_hand(s, "Desecrate Reality")
    mana(s, **paid)
    with pytest.raises(ActionError):  # (Llanowar Elves: mana value 1, odd)
        act(s, "p1", type="cast_spell", card_id=desecrate.id, targets=[elves.id], target_counts=[1])
    act(s, "p1", type="cast_spell", card_id=desecrate.id, targets=[bears.id], target_counts=[1])
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile" and zone_of(s, "Llanowar Elves", "p2") == "p2:battlefield"
    back = paid == {"C": 7}  # (adamant: three colorless mana; only the odd card, Llanowar Elves, may return)
    assert (zone_of(s, "Llanowar Elves") == "p1:battlefield") is back and zone_of(s, "Grizzly Bears") == "p1:graveyard"
    check(s)


# -- Gyruda, Doom of Depths ----------------------------------------------------------------------------------------------------------------------
def test_gyruda_takes_an_even_creature_milled_by_either_player(cards):
    s = build(cards, ["Gyruda, Doom of Depths", "Hill Giant", "Llanowar Elves"], ["Grizzly Bears", "Craw Wurm"])
    for pid, names in (("p1", ["Hill Giant", "Llanowar Elves"]), ("p2", ["Grizzly Bears", "Craw Wurm"])):
        for name in reversed(names):  # (the top four cards of each library: these two, then two lands)
            act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"player": pid, "zone": "library"}, position="top")
    gyruda = to_hand(s, "Gyruda, Doom of Depths")
    mana(s, U=2, G=4)
    act(s, "p1", type="cast_spell", card_id=gyruda.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    labels = sorted(o.label for o in d.options)
    assert labels == ["Craw Wurm", "Grizzly Bears", "Hill Giant"], labels  # (mana values 6, 2, 4 are even: Llanowar Elves, 1, is not offered)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Grizzly Bears")])
    settle(s)
    bears = card_named(s, "Grizzly Bears", "p2")
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].controller == "p1"
    assert zone_of(s, "Llanowar Elves") == "p1:graveyard"
    check(s)


# -- Tergrid, God of Fright ----------------------------------------------------------------------------------------------------------------------
TERGRID = "Tergrid, God of Fright // Tergrid's Lantern"


def test_tergrid_is_full_and_nexus_of_fate_too(cards):
    for name in (TERGRID, "Nexus of Fate"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def tergrid_table(cards, theirs):
    s = build(cards, [TERGRID, "Mind Rot", "Diabolic Edict"], list(theirs))
    put(s, TERGRID)
    return s


def test_tergrid_takes_a_discarded_permanent_card_but_not_a_spell(cards):
    s = tergrid_table(cards, ["Grizzly Bears", "Lightning Bolt"])
    for n in ("Grizzly Bears", "Lightning Bolt"):
        to_hand(s, n, "p2")
    to_hand(s, "Mind Rot")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mind Rot").id, targets=["p2"])
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p1:battlefield"  # (put onto the battlefield under Alice's control)
    assert zone_of(s, "Lightning Bolt", "p2") == "p2:graveyard"  # (not a permanent card)
    check(s)


def test_tergrid_takes_a_sacrificed_nontoken_permanent(cards):
    s = tergrid_table(cards, ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Diabolic Edict")
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Diabolic Edict").id, targets=["p2"])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_tergrid_ignores_its_own_controllers_discards(cards):
    s = tergrid_table(cards, [])
    to_hand(s, "Mind Rot")
    to_hand(s, "Diabolic Edict")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mind Rot").id, targets=["p1"])  # (Alice discards: Tergrid is hers)
    settle(s)
    assert zone_of(s, "Diabolic Edict") == "p1:graveyard"
    check(s)


# -- Stitch Together ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("fillers,where", [(6, "p1:battlefield"), (5, "p1:hand")])
def test_stitch_together_threshold_returns_the_card_to_the_battlefield_instead(cards, fillers, where):
    """Seven cards in the graveyard as it resolves (the target card counts, Stitch Together itself is on the stack): the card goes to the battlefield instead of the hand."""
    s = build(cards, ["Stitch Together", "Grizzly Bears"])
    lands = [c.id for c in s.state.cards.values() if c.zone == "p1:library" and c.name == "Forest"][:fillers]
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id, *lands], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Stitch Together")
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Stitch Together").id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == where
    check(s)


# -- Everybody Lives! --------------------------------------------------------------------------------------------------------------------------
def test_everybody_lives_players_have_hexproof_and_lose_no_life(cards):
    s = build(cards, ["Lightning Bolt", "Everybody Lives!"])
    first = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=2, W=2)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"])  # (before: Bob can be targeted)
    settle(s)
    assert life(s, "p2") == 37
    lives = to_hand(s, "Everybody Lives!")
    act(s, "p1", type="cast_spell", card_id=lives.id)
    settle(s)
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    second = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=2)
    with pytest.raises(ActionError):  # (Bob has hexproof against his opponent)
        act(s, "p1", type="cast_spell", card_id=second.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=second.id, targets=["p1"])
    settle(s)
    assert life(s, "p1") == 40 and len(bolts) == 1  # (3 damage to Alice was dealt, the life loss can't happen)
    check(s)


# -- Uncivil Unrest ----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("counter,dealt", [(True, 6 + 1), (False, 2 + 1)])  # (Bears 3 doubled + Elves 1; Bears 2 + Elves 1)
def test_uncivil_unrest_doubles_only_damage_from_creatures_with_a_plus_counter(cards, counter, dealt):
    s = build(cards, ["Uncivil Unrest", "Grizzly Bears", "Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    put(s, "Uncivil Unrest")
    if counter:  # (the Bears become 3/3: 3 damage, doubled to 6; the Elves have no counter)
        act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    next_turn(s)
    stops(s)
    attack(s, bears, elves)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - dealt
    check(s)


# -- Collective Inferno ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("chosen,dealt", [("Bear", 4 + 1), ("Elf", 2 + 2)])  # (the chosen type's creature deals double: Bears 2, Elves 1)
def test_collective_inferno_doubles_damage_of_the_chosen_type(cards, chosen, dealt):
    s = build(cards, ["Collective Inferno", "Grizzly Bears", "Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    inferno = to_hand(s, "Collective Inferno")
    mana(s, R=2, G=3)
    act(s, "p1", type="cast_spell", card_id=inferno.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    pick(s, next(o.id for o in d.options if o.label == chosen))
    settle(s)
    next_turn(s)
    stops(s)
    attack(s, bears, elves)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - dealt
    check(s)


# -- Loading Zone ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("target_pid,counters", [("p1", 2), ("p2", 1)])
def test_loading_zone_doubles_counters_on_your_creatures_only(cards, target_pid, counters):
    s = build(cards, ["Loading Zone", "Battlegrowth", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Loading Zone")
    bears = put(s, "Grizzly Bears", target_pid)
    spell = to_hand(s, "Battlegrowth")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].counters.get("+1/+1", 0) == counters
    check(s)


# -- Generous Plunderer ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("artifacts", [0, 2])
def test_generous_plunderer_hits_defending_player_for_their_artifacts(cards, artifacts):
    """"it deals damage to defending player equal to the number of artifacts they control": the count is Bob's, read as the trigger resolves (his Treasure from the upkeep trigger counts)."""
    s = build(cards, ["Generous Plunderer"], ["Sol Ring", "Arcane Signet"])
    plunderer = put(s, "Generous Plunderer")
    for name in ("Sol Ring", "Arcane Signet")[:artifacts]:
        put(s, name, "p2")
    next_turn(s)  # (the upkeep trigger is answered with its first option)
    stops(s)
    attack(s, plunderer)
    mine = sum(1 for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Treasure")
    theirs = sum(1 for c in s.state.cards.values() if c.zone == "p2:battlefield" and c.name in ("Sol Ring", "Arcane Signet", "Treasure"))
    assert theirs >= artifacts and mine in (0, 1)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - theirs - pt(s, "Generous Plunderer")[0]  # (the trigger's damage, then its combat damage)
    check(s)


# -- Bloodroot Apothecary ----------------------------------------------------------------------------------------------------------------------
def test_bloodroot_apothecary_poisons_an_opponent_sacrificing_a_noncreature_token_only(cards):
    s = build(cards, ["Bloodroot Apothecary"])
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Bloodroot Apothecary").id)
    settle(s)  # (Alice and Bob each create a Treasure)
    treasure = lambda pid: next(c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == f"{pid}:battlefield")  # noqa: E731
    activate(s, "p1", treasure("p1"))
    settle(s)
    assert s.state.players["p2"].resources["poison"] == 0 and s.state.players["p1"].resources["poison"] == 0  # (her own sacrifice)
    stops(s)
    act(s, "p1", type="pass_priority")  # (Bob gets priority in the same step)
    assert s.state.rules.priority == "p2"
    activate(s, "p2", treasure("p2"))
    settle(s)
    assert s.state.players["p2"].resources["poison"] == 2
    check(s)


# -- Urabrask's Forge --------------------------------------------------------------------------------------------------------------------------
def test_urabrasks_forge_makes_a_token_as_big_as_its_oil_and_sacrifices_it_at_the_end_step(cards):
    s = build(cards, ["Urabrask's Forge"])
    forge = put(s, "Urabrask's Forge")
    next_turn(s)
    stops(s)
    to_phase(s, "begin_combat")
    settle(s)  # (the oil counter, then the token with trample and haste)
    token = next(c for c in s.state.cards.values() if c.name == "Phyrexian Horror" and c.zone == "p1:battlefield")
    assert s.state.cards[forge.id].counters["oil"] == 2 and pt(s, "Phyrexian Horror") == (2, 1)  # (the first combat, turn 1, gave the first counter and a token that is long gone)
    assert sum(1 for c in s.state.cards.values() if c.name == "Phyrexian Horror" and c.zone == "p1:battlefield") == 1
    to_phase(s, "end")
    settle(s)
    assert token.id not in s.state.cards  # (sacrificed at the beginning of the next end step: a token ceases to exist)
    assert s.state.cards[forge.id].counters["oil"] == 2
    check(s)


# -- Silkguard ---------------------------------------------------------------------------------------------------------------------------------
def test_silkguard_gives_hexproof_to_the_creature_it_made_modified_only(cards):
    """"Put a +1/+1 counter on each of up to X target creatures you control. Auras, Equipment, and modified creatures you control gain hexproof": the counters come first, so the target is modified."""
    s = build(cards, ["Silkguard", "Grizzly Bears", "Llanowar Elves"], ["Lightning Bolt"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    guard = to_hand(s, "Silkguard")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=guard.id, targets=[bears.id], x_value=1, target_counts=[1])
    settle(s)
    assert s.state.cards[bears.id].counters.get("+1/+1", 0) == 1
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=2)
    stops(s)
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    with pytest.raises(ActionError):  # (modified: hexproof)
        act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[bears.id])
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[elves.id])  # (no counter, no Aura, no Equipment: targetable)
    settle(s)
    assert zone_of(s, "Llanowar Elves") == "p1:graveyard"
    check(s)


# -- Dawn-Blessed Pennant, Eclipsed Realms -----------------------------------------------------------------------------------------------------
TRIBES = ["Elemental", "Elf", "Faerie", "Giant", "Goblin", "Kithkin", "Merfolk", "Treefolk"]


def choose_tribe(s, tribe):
    d = until_asked(s)
    assert d is not None and d.player == "p1" and sorted(o.id for o in d.options) == sorted(TRIBES)  # (only the eight Lorwyn types are offered)
    pick(s, tribe)
    settle(s)


def test_dawn_blessed_pennant_gains_life_for_permanents_of_the_chosen_type(cards):
    s = build(cards, ["Dawn-Blessed Pennant", "Llanowar Elves", "Grizzly Bears"])
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Dawn-Blessed Pennant").id)
    choose_tribe(s, "Elf")
    assert s.state.cards[card_named(s, "Dawn-Blessed Pennant").id].choices["Chosen creature type"] == "Elf"
    mana(s, G=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    settle(s)
    assert life(s) == 40  # (a Bear is not an Elf)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Llanowar Elves").id)
    settle(s)
    assert life(s) == 41
    check(s)


def test_eclipsed_realms_mana_is_only_for_spells_of_the_chosen_type(cards):
    s = build(cards, ["Eclipsed Realms", "Llanowar Elves", "Lightning Bolt"])
    act(s, "p1", type="play_land", card_id=to_hand(s, "Eclipsed Realms").id)
    choose_tribe(s, "Elf")
    elves, bolt = to_hand(s, "Llanowar Elves"), to_hand(s, "Lightning Bolt")
    with pytest.raises(ActionError):  # (its one coloured mana is restricted to spells of the chosen type: a Bolt is no Elf)
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=elves.id)
    settle(s)
    assert zone_of(s, "Llanowar Elves") == "p1:battlefield"
    check(s)


# -- Zenith Chronicler ---------------------------------------------------------------------------------------------------------------------------
def test_zenith_chronicler_draws_for_everyone_but_the_caster_once_a_turn(cards):
    """"Whenever a player casts their first multicolored spell each turn, each other player draws a card.": Bob draws for Alice's Helix, nobody for her Bolt or her second multicolored spell."""
    s = build(cards, ["Zenith Chronicler", "Lightning Helix", "Terminate", "Lightning Bolt"], ["Llanowar Elves"], forests=20, islands=20)
    put(s, "Zenith Chronicler")
    elves = put(s, "Llanowar Elves", "p2")
    hands = lambda: (len(s.state.zones["p1:hand"]), len(s.state.zones["p2:hand"]))  # noqa: E731
    mana(s, R=4, W=1, B=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])  # (mono-coloured: nothing)
    settle(s)
    assert hands() == (0, 0)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Helix").id, targets=["p2"])
    settle(s)
    assert hands() == (0, 1)  # (Bob draws; Alice, who cast it, does not)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Terminate").id, targets=[elves.id])  # (her second multicolored spell this turn)
    settle(s)
    assert hands() == (0, 1)
    check(s)


# -- Court of Ambition ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("monarch,cost,lost", [(True, "Discard two cards", 6), (False, "Discard a card", 3)])
def test_court_of_ambition_loses_more_life_when_you_are_the_monarch(cards, monarch, cost, lost):
    """"... each opponent loses 3 life unless they discard a card. If you're the monarch, instead each opponent loses 6 life unless they discard two cards.": Bob declines."""
    s = build(cards, ["Court of Ambition"], ["Grizzly Bears", "Llanowar Elves"])
    mana(s, B=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Court of Ambition").id)
    settle(s)
    assert s.state.table.monarch == "p1"
    if not monarch:
        act(s, "p2", type="set_monarch", player="p2")
    for n in ("Grizzly Bears", "Llanowar Elves"):
        to_hand(s, n, "p2")
    to_phase(s, "upkeep", turn=3)
    d = until_asked(s)
    assert d is not None and d.player == "p2" and cost in d.prompt
    held = len(s.state.zones["p2:hand"])
    pick(s, "decline")
    settle(s)
    assert life(s, "p2") == 40 - lost and len(s.state.zones["p2:hand"]) == held
    check(s)


# -- Fatal Push ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("revolt,target,dies", [(False, "Grizzly Bears", True), (False, "Hill Giant", False), (True, "Hill Giant", True), (True, "Craw Wurm", False)])
def test_fatal_push_mana_value_two_or_four_with_revolt(cards, revolt, target, dies):
    """Mana values: Grizzly Bears 2, Hill Giant 4, Craw Wurm 6. Revolt (a permanent left the battlefield under your control this turn) raises the limit from 2 to 4 instead."""
    s = build(cards, ["Fatal Push", "Llanowar Elves"], ["Grizzly Bears", "Hill Giant", "Craw Wurm"])
    victim = put(s, target, "p2")
    if revolt:
        elves = put(s, "Llanowar Elves")
        act(s, "p1", type="move", card_ids=[elves.id], to={"player": "p1", "zone": "graveyard"})
    push = to_hand(s, "Fatal Push")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=push.id, targets=[victim.id])
    settle(s)
    assert (s.state.cards[victim.id].zone == "p2:graveyard") is dies
    check(s)


# -- Cases (719) ---------------------------------------------------------------------------------------------------------------------------------
def solved(s, name):
    return "Solved" in s.state.cards[card_named(s, name).id].choices


@pytest.mark.parametrize("spells,is_solved", [(4, True), (3, False)])
def test_case_of_the_ransacked_lab_solves_at_the_end_step_with_four_instants_or_sorceries(cards, spells, is_solved):
    """719.3a: "To solve - You've cast four or more instant and sorcery spells this turn": at the beginning of your end step, if that holds and it is not solved, it becomes solved."""
    s = build(cards, ["Case of the Ransacked Lab", "Lightning Bolt", "Opt", "Seething Song", "Swords to Plowshares"], ["Llanowar Elves"])
    put(s, "Case of the Ransacked Lab")
    elves = put(s, "Llanowar Elves", "p2")
    mana(s, R=3, U=1, W=1, C=1)
    casts = [("Lightning Bolt", {"targets": ["p2"]}), ("Opt", {}), ("Seething Song", {}), ("Swords to Plowshares", {"targets": [elves.id]})]
    for name, kw in casts[:spells]:
        act(s, "p1", type="cast_spell", card_id=to_hand(s, name).id, **kw)
        settle(s)
    assert not solved(s, "Case of the Ransacked Lab")
    stops(s)
    to_phase(s, "end")
    settle(s)
    assert solved(s, "Case of the Ransacked Lab") is is_solved
    check(s)


@pytest.mark.parametrize("is_solved,draws", [(False, 0), (True, 1)])
def test_case_solved_ability_works_only_while_solved(cards, is_solved, draws):
    """719.3c: "Solved - Whenever you cast an instant or sorcery spell, draw a card." triggers only if the Case has the solved designation."""
    s = build(cards, ["Case of the Ransacked Lab", "Lightning Bolt"], forests=20)
    case = put(s, "Case of the Ransacked Lab")
    if is_solved:
        act(s, "p1", type="set_choice", card_id=case.id, key="Solved", value="Yes")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == draws
    check(s)


@pytest.mark.parametrize("is_solved", [True, False])
def test_case_of_the_locked_hothouse_plays_from_the_top_of_the_library_once_solved(cards, is_solved):
    s = build(cards, ["Case of the Locked Hothouse"], forests=20)
    case = put(s, "Case of the Locked Hothouse")
    if is_solved:
        act(s, "p1", type="set_choice", card_id=case.id, key="Solved", value="Yes")
    top = s.state.zones["p1:library"][0]
    assert s.state.cards[top].name == "Forest"
    if is_solved:
        act(s, "p1", type="play_land", card_id=top)  # (719.3c: the Solved ability gives the permission to play lands from the top)
        assert s.state.cards[top].zone == "p1:battlefield"
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="play_land", card_id=top)
    check(s)


def test_swarmyard_massacre_shrinks_everything_that_is_not_a_squirrel_insect_rat_or_spider(cards):
    """Two Squirrel tokens, then each creature that isn't an Insect, Rat, Spider, or Squirrel gets -1/-1 for each of those I control (2): Bears (2/2) and Elves (1/1) die, Hill Giant (3/3) lives, the Squirrels aren't hit."""
    s = build(cards, ["Swarmyard Massacre", "Llanowar Elves"], ["Grizzly Bears", "Hill Giant"])
    elves, bears, giant = put(s, "Llanowar Elves"), put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p2")
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Swarmyard Massacre").id)
    settle(s)
    assert (s.state.cards[elves.id].zone, s.state.cards[bears.id].zone, s.state.cards[giant.id].zone) == ("p1:graveyard", "p2:graveyard", "p2:battlefield")
    assert pt(s, "Hill Giant", "p2") == (1, 1)
    assert sum(1 for c in s.state.cards.values() if c.name == "Squirrel" and c.zone == "p1:battlefield") == 2
    check(s)


@pytest.mark.parametrize("targets,exiled", [(["p1", "p2"], {"p1", "p2"}), (["p2"], {"p2"}), ([], set())])
def test_thraben_charm_exiles_the_graveyards_of_the_players_it_targets(cards, targets, exiled):
    """"Exile any number of target players' graveyards.": zero, one or both players, each graveyard whole."""
    s = build(cards, ["Thraben Charm", "Llanowar Elves", "Lightning Bolt"], ["Grizzly Bears", "Hill Giant"])
    for pid, names in (("p1", ("Llanowar Elves", "Lightning Bolt")), ("p2", ("Grizzly Bears", "Hill Giant"))):
        act(s, pid, type="move", card_ids=[card_named(s, n, pid).id for n in names], to={"player": pid, "zone": "graveyard"})
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Thraben Charm").id, modes=[2], targets=targets, target_counts=[len(targets)])
    settle(s)
    for pid in ("p1", "p2"):
        own_spell = 1 if pid == "p1" else 0  # (Thraben Charm itself goes to Alice's graveyard once it has resolved)
        assert len(s.state.zones[f"{pid}:graveyard"]) == (own_spell if pid in exiled else 2 + own_spell)
        assert len(s.state.zones[f"{pid}:exile"]) == (2 if pid in exiled else 0)
    check(s)


def test_reaver_titan_has_protection_from_mana_value_three_or_less_despite_its_flavor_word(cards):
    """"Void Shields - Protection from mana value 3 or less" (a flavor word, 207.2d): Bob's Grizzly Bears (mana value 2) can't block it, his Hill Giant (4) can."""
    s = build(cards, ["Reaver Titan", "Craw Wurm"], ["Grizzly Bears", "Hill Giant"])
    titan, wurm = put(s, "Reaver Titan"), put(s, "Craw Wurm")
    bears, giant = put(s, "Grizzly Bears", "p2"), put(s, "Hill Giant", "p2")
    next_turn(s)
    crew = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(titan).abilities if a.text.startswith("Crew"))
    act(s, "p1", type="activate_ability", card_id=titan.id, ability=crew, crew=[wurm.id])
    settle(s)
    attack(s, titan)
    to_blockers(s)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": titan.id}])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": giant.id, "attacker_id": titan.id}])
    settle(s)
    check(s)


def test_summon_leviathan_returns_creatures_that_are_not_sea_creatures(cards):
    s = build(cards, ["Summon: Leviathan", "Llanowar Elves"], ["Grizzly Bears"])
    elves, bears = put(s, "Llanowar Elves"), put(s, "Grizzly Bears", "p2")
    mana(s, U=2, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Summon: Leviathan").id)
    settle(s)
    assert (s.state.cards[elves.id].zone, s.state.cards[bears.id].zone) == ("p1:hand", "p2:hand")
    assert zone_of(s, "Summon: Leviathan") == "p1:battlefield"  # (it is a Leviathan itself)
    check(s)


def test_case_of_the_locked_hothouse_is_solved_with_seven_lands(cards):
    s = build(cards, ["Case of the Locked Hothouse"], forests=20)
    case = put(s, "Case of the Locked Hothouse")
    lands = [c.id for c in s.state.cards.values() if c.zone == "p1:library" and c.name == "Forest"][:7]
    act(s, "p1", type="move", card_ids=lands, to={"player": "p1", "zone": "battlefield"})
    stops(s)
    to_phase(s, "end")
    settle(s)
    assert "Solved" in s.state.cards[case.id].choices
    check(s)
