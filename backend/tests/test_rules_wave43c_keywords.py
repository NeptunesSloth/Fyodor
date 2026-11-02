"""Wave 43C: keyword costs that weren't plain mana (cumulative upkeep, echo, ward; CR 2026-09-25), real Oracle text
(tests/fixtures/wave43c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 702.24a cumulative upkeep: "put an age counter on this permanent. Then you may pay [cost] for each age counter on it. If you don't, sacrifice it." The cost
  is paid once for each age counter, all at once (118.3: no partial payment, so a cost that can't be paid in full can't be paid): {B} and 1 life (Infernal Darkness),
  "Sacrifice a creature" (Phyrexian Soulgorger, which may sacrifice itself) / "a land" (Polar Kraken), "Discard a card" (Vexing Sphinx), "Put a -1/-1 counter on this
  creature" (Aboroth), "{G} or {W}" for each counter (Arctic Nishoba, Earthen Goo, Jotun Owl Keeper, Krovikan Whispers: that many hybrid {G/W}), "Draw a card" (Psychic
  Vortex: a replaced draw is still a payment), "Add {R}" (Braid of Fire), "An opponent gains 1 life" / "Have an opponent create a 1/1 red Survivor creature token" (Wall
  of Shards, Varchild's War-Riders: an opponent chosen for each age counter, not a target). 702.24b: two instances each count every age counter.
* 702.30a echo: "sacrifice it unless you pay [echo cost]" when it came under your control since your last upkeep; "Echo—Discard a card." and "Echo—Sacrifice two
  lands." are optional payments (118.12a); a permanent that changes controller owes it again to the new controller.
* 702.21a ward: "counter it unless that player pays [cost]": "Pay life equal to Raubahn's power" (sized as the ward trigger resolves, 702.21b, 608.2h), "Discard a card or pay
  {2}", "Sacrifice a legendary artifact or legendary creature" and "Get five poison counters" (the player who targeted, not the permanent's controller).

Refused (manual, with the reason): Sheltering Ancient (a +1/+1 counter on a creature of an opponent's for each age counter: payable only while one exists, 118.3), Jotun Grunt
(a graveyard chosen for each age counter), Thought Lash / Karplusan Minotaur / Herald of Leshrac (the cost is a library exile, a coin flip and a control change, and each card has
other lines unread), Hibernation's End / Heart of Bogardan / Balduvian Fallen ("whenever you pay / a player doesn't pay its cumulative upkeep" has no event), The Unagi of Kyoshi
Island ("Ward—Waterbend {4}": tapping permanents to help pay is a casting-time choice), Minthara ("ward {X}" granted by a static ability). Ordinary banding is covered by test_rules_banding.py; bands-with-other forms remain manual.
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
from app.rules import coverage
from app.rules.mana_units import visible_pool
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave34b_activated import settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave43c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w43c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
SOULGORGER, DARKNESS, SPHINX, KRAKEN, NISHOBA, GOO = ("Phyrexian Soulgorger", "Infernal Darkness", "Vexing Sphinx", "Polar Kraken", "Arctic Nishoba", "Earthen Goo")
VORTEX, BRAID, HEADLINER, IMP, SURGER = "Psychic Vortex", "Braid of Fire", "Rakdos Headliner", "Deepcavern Imp", "Skizzik Surger"
ABOROTH, WALL, WARRIORS, OWL = "Aboroth", "Wall of Shards", "Varchild's War-Riders", "Jötun Owl Keeper"
RAUBAHN, FLESHGORGER, TITANIA, SERPENT, SAURON = ("Raubahn, Bull of Ala Mhigo", "Phyrexian Fleshgorger", "Titania, Rugged Rumbler", "The Serpent Society",
                                                  "Sauron, the Dark Lord")
FULL = [SOULGORGER, DARKNESS, SPHINX, KRAKEN, NISHOBA, GOO, VORTEX, BRAID, HEADLINER, IMP, SURGER, RAUBAHN, FLESHGORGER, TITANIA, SERPENT, SAURON,
        "Jötun Owl Keeper", "Krovikan Whispers", ABOROTH, WALL, WARRIORS]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def lands(s, name, n, pid="p1"):
    """The first n cards of this name still in the library, onto the battlefield."""
    ids = [c.id for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]
    act(s, pid, type="move", card_ids=ids, to={"player": pid, "zone": "battlefield"})
    return ids


def prompt(s, name, pid="p1", limit=400):
    """Pass priority (no attackers, no blockers, discarding as the cleanup step asks) until ``pid`` is asked something about ``name``."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.player == pid and d.prompt.startswith(f"{name}:"):
            return d
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"{pid} was never asked about {name}")


def answer(s, d, *option_ids):
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(option_ids))


def drain(s, limit=60):
    """Resolve what is on the stack, answering nothing (a decision stops it)."""
    for _ in range(limit):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def age(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].counters.get("age", 0)


# ---- cumulative upkeep (702.24a) ---------------------------------------------------------------------------------------------------------------------------
def test_cumulative_upkeep_of_mana_and_life_is_paid_twice_then_declined_and_sacrificed(cards):
    """Infernal Darkness: "Cumulative upkeep—Pay {B} and 1 life." — {B} and 1 life for the first age counter, {B}{B} and 2 life for the second, and the
    third is declined: it is sacrificed (the ruling 2008-10-01: paying is always optional, and a partial payment can't be made)."""
    s = build(cards, [DARKNESS, "Swamp", "Swamp", "Swamp"])
    dark = put(s, DARKNESS)
    swamps = lands(s, "Swamp", 3)
    d = prompt(s, DARKNESS)
    assert age(s, DARKNESS) == 1 and {o.id for o in d.options} == {"pay", "decline"} and "{B}" in d.prompt and "1 life" in d.prompt
    answer(s, d, "pay")
    assert life(s) == 39 and sum(s.state.cards[c].tapped for c in swamps) == 1  # {B} and 1 life, once
    d = prompt(s, DARKNESS)
    assert age(s, DARKNESS) == 2 and "{B}{B}" in d.prompt and "2 life" in d.prompt  # once for each of the two age counters, at once
    answer(s, d, "pay")
    assert life(s) == 37 and sum(s.state.cards[c].tapped for c in swamps) == 2
    d = prompt(s, DARKNESS)
    assert age(s, DARKNESS) == 3 and "{B}{B}{B}" in d.prompt and "3 life" in d.prompt
    answer(s, d, "decline")
    drain(s)
    assert zone_of(s, DARKNESS) == "p1:graveyard" and life(s) == 37 and s.state.cards[dark.id].counters.get("age", 0) in (0, 3)
    check(s)


def test_cumulative_upkeep_that_cant_be_paid_in_full_is_not_offered(cards):
    """118.3: no partial payment — with two Swamps for a {B}{B}{B} cost the option to pay isn't there, and the permanent is sacrificed."""
    s = build(cards, [DARKNESS, "Swamp", "Swamp"])
    put(s, DARKNESS)
    swamps = lands(s, "Swamp", 2)
    answer(s, prompt(s, DARKNESS), "pay")  # age 1: {B}, 1 life
    answer(s, prompt(s, DARKNESS), "pay")  # age 2: {B}{B}, 2 life
    assert life(s) == 37 and all(s.state.cards[c].tapped for c in swamps)
    # the third: {B}{B}{B} and 3 life with two Swamps — can't be paid, so nothing is asked (it is just sacrificed)
    to_phase(s, "main1", turn=s.state.turn.number + 2)
    assert zone_of(s, DARKNESS) == "p1:graveyard" and life(s) == 37
    check(s)


def test_cumulative_upkeep_sacrifice_a_creature_once_for_each_age_counter_even_itself(cards):
    """Phyrexian Soulgorger: "Cumulative upkeep—Sacrifice a creature." — one creature for the first counter; two different ones for the second (it may be
    one of them: ruling 2006-07-15); a payment of two with only one creature around can't be made."""
    s = build(cards, [SOULGORGER, "Grizzly Bears", "Llanowar Elves"])
    gorger, bears, elves = put(s, SOULGORGER), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    d = prompt(s, SOULGORGER)
    assert age(s, SOULGORGER) == 1 and ": sacrifice a creature?" in d.prompt
    answer(s, d, "pay")
    d = prompt(s, SOULGORGER)  # which creature to sacrifice: the payer chooses among their permanents
    assert {o.id for o in d.options} == {gorger.id, bears.id, elves.id}
    answer(s, d, elves.id)
    drain(s)
    assert zone_of(s, "Llanowar Elves") == "p1:graveyard" and zone_of(s, SOULGORGER) == "p1:battlefield" and age(s, SOULGORGER) == 1
    d = prompt(s, SOULGORGER)
    assert age(s, SOULGORGER) == 2 and "sacrifice a creature, sacrifice a creature" in d.prompt
    answer(s, d, "pay")
    d = prompt(s, SOULGORGER)  # two different creatures: the Bears and the Soulgorger itself are the only two left
    assert {o.id for o in d.options} == {gorger.id, bears.id}
    answer(s, d, bears.id)  # (the second is the only one left: nothing to ask, it is sacrificed as part of paying its own upkeep)
    drain(s)
    assert zone_of(s, "Grizzly Bears") == zone_of(s, SOULGORGER) == "p1:graveyard"
    check(s)


def test_cumulative_upkeep_discard_hidden_choice_and_the_sacrifice_trigger_reads_the_age_counters(cards):
    """Vexing Sphinx: "Cumulative upkeep—Discard a card." / "When this creature dies, draw a card for each age counter on it." — the discards are the
    payer's private choice (118.3: with an empty hand it can't be paid at all); declining sacrifices it, and it draws one card for each of its three age
    counters as it last existed."""
    names = ["Lightning Bolt", "Opt", "Sol Ring", "Arcane Signet", "Rampant Growth", "Giant Growth"]
    s = build(cards, [SPHINX, *names])
    put(s, SPHINX)
    for n in names:
        to_hand(s, n)
    d = prompt(s, SPHINX)
    assert age(s, SPHINX) == 1
    answer(s, d, "pay")
    d = prompt(s, SPHINX)
    assert d.kind == "choose_cards" and {o.id for o in d.options} == set(s.state.zones["p1:hand"])  # the hand is the options, shown to the payer
    assert not s.view("p2")["rules"]["decision"].get("options")  # (the opponent is told only that someone is choosing: 101.4a, 402.3)
    first = d.options[0].id
    answer(s, d, first)
    drain(s)
    assert s.state.cards[first].zone == "p1:graveyard" and zone_of(s, SPHINX) == "p1:battlefield"
    d = prompt(s, SPHINX)  # the second age counter: two cards, one pick for each
    assert age(s, SPHINX) == 2 and "discard a card, discard a card" in d.prompt
    answer(s, d, "pay")
    for _ in range(2):
        d = prompt(s, SPHINX)
        answer(s, d, d.options[0].id)
    drain(s)
    assert len(s.state.zones["p1:graveyard"]) == 3
    d = prompt(s, SPHINX)
    assert age(s, SPHINX) == 3
    hand = len(s.state.zones["p1:hand"])
    answer(s, d, "decline")
    drain(s)
    assert zone_of(s, SPHINX) == "p1:graveyard"
    to_phase(s, "main1", turn=s.state.turn.number)
    assert len(s.state.zones["p1:hand"]) == hand + 3 + 1  # three age counters, three cards (and the card of the draw step)
    check(s)


def test_cumulative_upkeep_a_hybrid_cost_is_one_hybrid_symbol_for_each_age_counter(cards):
    """Arctic Nishoba: "Cumulative upkeep {G} or {W}" — each age counter is paid with either, so two counters are {G/W}{G/W}."""
    s = build(cards, [NISHOBA, "Forest", "Forest"])
    put(s, NISHOBA)
    forests = lands(s, "Forest", 2)
    d = prompt(s, NISHOBA)
    assert "{G/W}" in d.prompt and age(s, NISHOBA) == 1
    answer(s, d, "pay")
    d = prompt(s, NISHOBA)
    assert "{G/W}{G/W}" in d.prompt and age(s, NISHOBA) == 2
    answer(s, d, "pay")
    drain(s)
    assert zone_of(s, NISHOBA) == "p1:battlefield" and all(s.state.cards[c].tapped for c in forests)
    d = prompt(s, NISHOBA)
    assert age(s, NISHOBA) == 3
    answer(s, d, "sacrifice")
    drain(s)
    assert zone_of(s, NISHOBA) == "p1:graveyard" and life(s) == 46  # "When this creature dies, you gain 2 life for each age counter on it": 3 counters
    check(s)


def test_cumulative_upkeep_draw_a_card_is_paid_by_drawing_once_for_each_counter(cards):
    """Psychic Vortex: "Cumulative upkeep—Draw a card." — you choose to draw (even from a short library, the ruling 2008-04-01), once for each age counter."""
    s = build(cards, [VORTEX])
    put(s, VORTEX)
    d = prompt(s, VORTEX)
    assert age(s, VORTEX) == 1
    hand = len(s.state.zones["p1:hand"])
    answer(s, d, "pay")
    to_phase(s, "main1", turn=s.state.turn.number)
    assert len(s.state.zones["p1:hand"]) == hand + 1 + 1  # the cost, and the draw step's card
    d = prompt(s, VORTEX)
    assert age(s, VORTEX) == 2
    hand = len(s.state.zones["p1:hand"])
    answer(s, d, "pay")
    to_phase(s, "main1", turn=s.state.turn.number)
    assert len(s.state.zones["p1:hand"]) == hand + 2 + 1  # two draws for two age counters, and the draw step's card
    d = prompt(s, VORTEX)
    answer(s, d, "decline")
    drain(s)
    assert zone_of(s, VORTEX) == "p1:graveyard"
    check(s)


def test_cumulative_upkeep_add_mana_is_paid_by_adding_it(cards):
    """Braid of Fire: "Cumulative upkeep—Add {R}." — an odd cost: {R} for each age counter goes to the pool (ruling 2009-10-01: it does nothing but add
    increasing amounts of mana during your upkeep), and it is gone before the draw step (106.4)."""
    s = build(cards, [BRAID])
    stops(s)  # (a stop at every step: the mana can be seen in the pool)
    put(s, BRAID)
    d = prompt(s, BRAID)
    answer(s, d, "pay")
    assert zone_of(s, BRAID) == "p1:battlefield" and visible_pool(s.state, "p1").get("R", 0) == 1
    to_phase(s, "main1", turn=s.state.turn.number)
    assert not visible_pool(s.state, "p1") and not s.state.players["p1"].mana_units
    d = prompt(s, BRAID)
    assert age(s, BRAID) == 2
    answer(s, d, "pay")
    assert visible_pool(s.state, "p1").get("R", 0) == 2
    to_phase(s, "main1", turn=s.state.turn.number)
    d = prompt(s, BRAID)
    answer(s, d, "decline")
    drain(s)
    assert zone_of(s, BRAID) == "p1:graveyard" and not s.state.players["p1"].mana
    check(s)


def test_cumulative_upkeep_put_a_counter_on_itself_as_a_cost(cards):
    """Aboroth: "Cumulative upkeep—Put a -1/-1 counter on this creature." — one -1/-1 counter for the first age counter, two for the second (a cost is not an
    effect: no counter doubling, 614.16); declined, it is sacrificed."""
    s = build(cards, [ABOROTH])
    put(s, ABOROTH)
    d = prompt(s, ABOROTH)
    assert age(s, ABOROTH) == 1
    answer(s, d, "pay")
    assert s.state.cards[card_named(s, ABOROTH).id].counters.get("-1/-1", 0) == 1
    d = prompt(s, ABOROTH)
    assert age(s, ABOROTH) == 2 and "put a -1/-1 counter on this creature, put a -1/-1 counter on this creature" in d.prompt
    answer(s, d, "pay")
    assert s.state.cards[card_named(s, ABOROTH).id].counters.get("-1/-1", 0) == 3
    answer(s, prompt(s, ABOROTH), "decline")
    drain(s)
    assert zone_of(s, ABOROTH) == "p1:graveyard"
    check(s)


def test_two_cumulative_upkeeps_each_count_every_age_counter(cards):
    """702.24b: Earthen Goo has its own "Cumulative upkeep {R} or {G}" and Mana Chains gives it "Cumulative upkeep {1}": the two trigger separately, each
    puts an age counter, and the one that resolves second counts both (so it asks for two of its cost)."""
    s = build(cards, [GOO, "Mana Chains", "Forest", "Forest", "Forest", "Forest", "Forest"])
    goo, chains = put(s, GOO), to_hand(s, "Mana Chains")
    lands(s, "Forest", 5)
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=chains.id, targets=[goo.id])
    settle(s)
    assert s.state.cards[chains.id].attached_to == goo.id
    asked = []
    for _ in range(2):
        d = prompt(s, GOO)
        asked.append((age(s, GOO), d.prompt))
        answer(s, d, "pay")
        drain(s)
    assert [a for a, _ in asked] == [1, 2]  # the second one saw both age counters
    assert "pay {1} or" in asked[0][1] and "pay {R/G}{R/G} or" in asked[1][1], asked  # (Mana Chains' instance resolved first: one {1}; Goo's own then asks for two hybrids)
    assert zone_of(s, GOO) == "p1:battlefield" and age(s, GOO) == 2
    check(s)


def test_cumulative_upkeep_an_opponent_gains_life_for_each_age_counter(cards):
    """Wall of Shards: "Cumulative upkeep—An opponent gains 1 life." — one life for the first age counter, two for the second; with one opponent there is
    nothing to choose; declined, it is sacrificed."""
    s = build(cards, [WALL])
    put(s, WALL)
    d = prompt(s, WALL)
    assert age(s, WALL) == 1
    answer(s, d, "pay")
    drain(s)
    assert life(s, "p2") == 41 and life(s) == 40
    d = prompt(s, WALL)
    assert age(s, WALL) == 2
    answer(s, d, "pay")
    drain(s)
    assert life(s, "p2") == 43 and life(s) == 40
    answer(s, prompt(s, WALL), "decline")
    drain(s)
    assert zone_of(s, WALL) == "p1:graveyard" and life(s, "p2") == 43
    check(s)


def test_cumulative_upkeep_an_opponent_is_chosen_for_each_age_counter_in_a_multiplayer_game(cards):
    """Ruling 2006-07-15 (Wall of Shards): "you may choose a different opponent for each age counter, or you can choose the same opponent multiple
    times" — with three opponents, each of the two payments asks, and nobody is targeted."""
    names = ["Krenko, Mob Boss", "Atraxa, Praetors' Voice", "Karador, Ghost Chieftain", "Kess, Dissident Mage"]
    decks = [deck(cards, c, [(1, WALL), (9, "Forest")] if i == 0 else [(10, "Island")]) for i, c in enumerate(names)]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Cara", "Dan"), decks, strict=True)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    put(s, WALL)
    d = prompt(s, WALL)
    answer(s, d, "pay")
    d = prompt(s, WALL)
    assert d.kind == "choose_one" and {o.id for o in d.options} == {"p2", "p3", "p4"} and "choose an opponent" in d.prompt
    answer(s, d, "p3")
    drain(s)
    assert [life(s, p) for p in ("p1", "p2", "p3", "p4")] == [40, 40, 41, 40]
    d = prompt(s, WALL)
    assert age(s, WALL) == 2
    answer(s, d, "pay")
    for chosen in ("p2", "p2"):  # two payments, each its own choice (the same opponent twice is fine)
        d = prompt(s, WALL)
        assert "choose an opponent" in d.prompt
        answer(s, d, chosen)
    drain(s)
    assert [life(s, p) for p in ("p1", "p2", "p3", "p4")] == [40, 42, 41, 40]
    check(s)


def test_cumulative_upkeep_an_opponent_creates_a_token_for_each_age_counter(cards):
    """Varchild's War-Riders: "Cumulative upkeep—Have an opponent create a 1/1 red Survivor creature token." — the token is the opponent's."""
    s = build(cards, [WARRIORS])
    put(s, WARRIORS)
    answer(s, prompt(s, WARRIORS), "pay")
    drain(s)
    survivors = [c for c in s.state.cards.values() if c.name == "Survivor"]
    assert [c.controller for c in survivors] == ["p2"]
    answer(s, prompt(s, WARRIORS), "pay")
    drain(s)
    assert sorted(c.controller for c in s.state.cards.values() if c.name == "Survivor") == ["p2", "p2", "p2"]  # one for the first counter, two for the second
    check(s)


def test_cumulative_upkeep_sacrifice_a_land_and_a_hybrid_cost_whose_creature_leaves_birds(cards):
    """Polar Kraken: "Cumulative upkeep—Sacrifice a land." (one land for each age counter, 118.3: with none to sacrifice it is just sacrificed), and Jotun
    Owl Keeper: "Cumulative upkeep {W} or {U}" / "When this creature dies, create a 1/1 white Bird creature token with flying for each age counter on it."."""
    s = build(cards, [KRAKEN, "Mountain", "Mountain"])
    put(s, KRAKEN)
    ids = lands(s, "Mountain", 2)
    d = prompt(s, KRAKEN)
    answer(s, d, "pay")
    d = prompt(s, KRAKEN)  # which land (two Mountains: a real choice)
    assert {o.id for o in d.options} == set(ids)
    answer(s, d, ids[0])
    drain(s)
    assert s.state.cards[ids[0]].zone == "p1:graveyard" and zone_of(s, KRAKEN) == "p1:battlefield"
    to_phase(s, "main1", turn=s.state.turn.number + 2)  # the second age counter: two lands needed, one is left
    assert zone_of(s, KRAKEN) == "p1:graveyard" and s.state.cards[ids[1]].zone == "p1:battlefield"
    check(s)

    s = build(cards, [OWL, "Island"])
    put(s, OWL)
    lands(s, "Island", 1)
    d = prompt(s, OWL)
    assert "{W/U}" in d.prompt
    answer(s, d, "pay")
    d = prompt(s, OWL)
    assert age(s, OWL) == 2 and "{W/U}{W/U}" in d.prompt
    answer(s, d, "sacrifice")  # one Island for a two-symbol cost: it can't be paid
    drain(s)
    assert zone_of(s, OWL) == "p1:graveyard"
    assert [c.controller for c in s.state.cards.values() if c.name == "Bird"] == ["p1", "p1"]  # two age counters, two Birds
    check(s)


def test_you_may_put_a_counter_on_it_if_you_do_is_a_cost_paid_as_it_resolves(cards):
    """118.12: "[A player] may [do something]. If [that player] does, [effect]. The action is a cost, paid when the spell or ability resolves." — Sphinx-Bone
    Wand's "you may put a charge counter on this artifact. If you do, it deals damage equal to the number of charge counters on it" asks first, and the counter
    is put as a cost (it is not an effect, so a counter-doubling replacement doesn't touch it, the way a planeswalker's loyalty cost isn't doubled)."""
    s = build(cards, ["Sphinx-Bone Wand", "Lightning Bolt", "Lightning Bolt"])
    wand = put(s, "Sphinx-Bone Wand")
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt"]
    act(s, "p1", type="move", card_ids=[b.id for b in bolts], to={"zone": "hand"})
    for bolt, pay in zip(bolts, ("pay", "pay"), strict=True):
        mana(s, "p1", R=1)
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
        answer(s, prompt(s, "Sphinx-Bone Wand"), "p2")  # (the trigger's own target: any target)
        d = prompt(s, "Sphinx-Bone Wand")
        assert {o.id for o in d.options} == {"pay", "decline"}
        answer(s, d, pay)
        drain(s)
    assert s.state.cards[wand.id].counters == {"charge": 2}
    assert life(s, "p2") == 40 - 1 - 3 - 2 - 3  # the first Bolt's trigger: 1; the Bolt: 3; the second trigger: 2; the second Bolt: 3
    check(s)


# ---- echo (702.30a) ----------------------------------------------------------------------------------------------------------------------------------------
def test_echo_discard_a_card_is_paid_once_or_it_is_sacrificed(cards):
    """Deepcavern Imp: "Echo—Discard a card." — asked once (at the first upkeep after it came under your control), and the payment is a private choice from
    the hand (118.12a); it is due only that once."""
    s = build(cards, [IMP, "Lightning Bolt", "Opt"])
    put(s, IMP)
    to_hand(s, "Lightning Bolt"), to_hand(s, "Opt")
    d = prompt(s, IMP)
    assert {o.id for o in d.options} == {"pay", "decline"} and ": discard a card?" in d.prompt
    answer(s, d, "pay")
    d = prompt(s, IMP)
    assert d.kind == "choose_cards" and {s.state.cards[o.id].name for o in d.options} >= {"Lightning Bolt", "Opt"}
    assert not s.view("p2")["rules"]["decision"].get("options")  # (the opponent is told only that someone is choosing)
    pick = next(o.id for o in d.options if s.state.cards[o.id].name == "Opt")
    answer(s, d, pick)
    drain(s)
    assert s.state.cards[pick].zone == "p1:graveyard" and zone_of(s, IMP) == "p1:battlefield"
    to_phase(s, "main1", turn=s.state.turn.number + 2)  # the next upkeep of Alice's: nothing is asked
    assert zone_of(s, IMP) == "p1:battlefield"
    check(s)


def test_echo_not_paid_sacrifices_it_and_an_empty_hand_cant_pay(cards):
    """Rakdos Headliner: "Echo—Discard a card." — declined, it is sacrificed; with no card in hand (118.3) the cost can't be paid and nothing is asked."""
    s = build(cards, [HEADLINER, "Opt"])
    put(s, HEADLINER)
    to_hand(s, "Opt")
    answer(s, prompt(s, HEADLINER), "decline")
    drain(s)
    assert zone_of(s, HEADLINER) == "p1:graveyard" and zone_of(s, "Opt") == "p1:hand"
    check(s)

    s = build(cards, [HEADLINER])
    put(s, HEADLINER)
    to_phase(s, "main1", turn=3)
    assert zone_of(s, HEADLINER) == "p1:graveyard"
    check(s)


def test_echo_sacrifice_two_lands_paid_and_not_offered_with_one_land(cards):
    """Skizzik Surger: "Echo—Sacrifice two lands." — two lands are the cost; with a single land it can't be paid (118.3) and nothing is asked."""
    s = build(cards, [SURGER, "Mountain", "Mountain"])
    put(s, SURGER)
    ids = lands(s, "Mountain", 2)
    d = prompt(s, SURGER)
    assert ": sacrifice two lands?" in d.prompt
    answer(s, d, "pay")
    drain(s)
    assert zone_of(s, SURGER) == "p1:battlefield" and all(s.state.cards[c].zone == "p1:graveyard" for c in ids)
    check(s)

    s = build(cards, [SURGER, "Mountain"])
    put(s, SURGER)
    lands(s, "Mountain", 1)
    to_phase(s, "main1", turn=3)
    assert zone_of(s, SURGER) == "p1:graveyard"
    check(s)


def test_echo_is_due_again_to_a_new_controller(cards):
    """702.30a: "if this permanent came under your control since the beginning of your last upkeep" — Alice paid at her first upkeep; Bob takes the Imp
    with Mind Control; at Bob's next upkeep Bob is asked (and Bob discards from his own hand); not paying, it is sacrificed into its owner's graveyard."""
    s = build(cards, [IMP, "Lightning Bolt", "Opt"], ["Mind Control"], islands=12)
    imp = put(s, IMP)
    to_hand(s, "Lightning Bolt"), to_hand(s, "Opt")
    answer(s, prompt(s, IMP), "pay")
    d = prompt(s, IMP)
    answer(s, d, d.options[0].id)
    drain(s)
    to_hand(s, "Mind Control", "p2")
    lands(s, "Island", 5, "p2")
    to_phase(s, "main1", turn=4)
    mana(s, "p2", U=5)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Mind Control", "p2").id, targets=[imp.id])
    for _ in range(10):
        if s.state.rules.decision is None and not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[imp.id].controller == "p2" and s.state.cards[imp.id].owner == "p1"
    d = prompt(s, IMP, "p2")  # Bob's upkeep, two turns later
    assert d.player == "p2" and s.state.turn.number == 6 and {o.id for o in d.options} == {"pay", "decline"}
    answer(s, d, "decline")
    drain(s)
    assert zone_of(s, IMP) == "p1:graveyard"
    check(s)


# ---- ward (702.21a) ----------------------------------------------------------------------------------------------------------------------------------------
def bolt_at(cards, ward_creature, mine=(), mana_added=None, respond=False):
    """Alice (with ``mine`` in her hand) casts Lightning Bolt at Bob's ward creature; the table stops once the ward trigger has been put on the stack."""
    s = build(cards, ["Lightning Bolt", *mine], [ward_creature])
    target = put(s, ward_creature, "p2")
    bolt = to_hand(s, "Lightning Bolt")
    for n in mine:
        to_hand(s, n)
    mana(s, "p1", R=1, **(mana_added or {}))
    if respond:
        stops(s)  # (Bob gets priority with the ward trigger on the stack)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[target.id])
    return s, bolt, target


def resolved(s, bolt, target):
    """Whether Lightning Bolt resolved (3 damage on the creature, or the creature died) rather than being countered by the ward."""
    return s.state.cards[target.id].damage == 3 or s.state.cards[target.id].zone == "p2:graveyard"


def test_ward_pay_life_equal_to_its_power_paid_and_not_paid(cards):
    """Raubahn, Bull of Ala Mhigo: "Ward—Pay life equal to Raubahn's power." — sized when the ward trigger resolves (608.2h); paying lets Lightning Bolt
    resolve, declining counters it."""
    power = int(cards.resolve(RAUBAHN)["power"])
    s, bolt, target = bolt_at(cards, RAUBAHN)
    d = prompt(s, RAUBAHN, "p1")
    assert {o.id for o in d.options} == {"pay", "decline"} and f"Pay {power} life" in d.options[0].label
    answer(s, d, "pay")
    drain(s)
    assert life(s) == 40 - power and s.state.cards[bolt.id].zone == "p1:graveyard" and resolved(s, bolt, target)
    check(s)

    s, bolt, target = bolt_at(cards, RAUBAHN)
    answer(s, prompt(s, RAUBAHN, "p1"), "decline")
    drain(s)
    assert life(s) == 40 and s.state.cards[bolt.id].zone == "p1:graveyard" and not resolved(s, bolt, target)  # countered: 702.21a
    check(s)


def test_ward_life_is_sized_when_the_ward_trigger_resolves_not_when_it_triggers(cards):
    """Rulings 2025-06-06 (Raubahn) and 2022-10-14 (Phyrexian Fleshgorger), 702.21b: "Use Raubahn's power at the time the ward ability resolves" — two
    +1/+1 counters put on it while the trigger is on the stack make it cost two more life."""
    power = int(cards.resolve(RAUBAHN)["power"])
    s, bolt, target = bolt_at(cards, RAUBAHN, respond=True)
    assert len(s.state.zones["stack"]) == 2  # Lightning Bolt and the ward trigger
    act(s, "p2", type="counter", card_ids=[target.id], kind="+1/+1", delta=2)
    d = prompt(s, RAUBAHN, "p1")
    assert f"Pay {power + 2} life" in d.options[0].label
    answer(s, d, "pay")
    drain(s)
    assert life(s) == 40 - power - 2
    check(s)


def test_ward_pay_life_equal_to_this_creatures_power(cards):
    """Phyrexian Fleshgorger: "Ward—Pay life equal to this creature's power." — the same ward, worded for a prototype card (its power is the one it has)."""
    power = int(cards.resolve(FLESHGORGER)["power"])
    s, bolt, target = bolt_at(cards, FLESHGORGER)
    d = prompt(s, FLESHGORGER, "p1")
    assert f"Pay {power} life" in d.options[0].label
    answer(s, d, "pay")
    drain(s)
    assert life(s) == 40 - power and resolved(s, bolt, target)
    check(s)


def test_ward_discard_a_card_or_pay_two(cards):
    """Titania, Rugged Rumbler: "Ward—Discard a card or pay {2}." — both are offered while both can be paid (118.12); either lets the spell resolve."""
    s, bolt, target = bolt_at(cards, TITANIA, mine=["Opt"], mana_added={"C": 2})
    d = prompt(s, TITANIA, "p1")
    assert {o.id for o in d.options} == {"pay:0", "pay:1", "decline"}
    answer(s, d, "pay:0")  # the discard (the only card in hand is Opt)
    drain(s)
    assert zone_of(s, "Opt") == "p1:graveyard" and resolved(s, bolt, target) and s.state.players["p1"].mana.get("C", 0) == 2
    check(s)

    s, bolt, target = bolt_at(cards, TITANIA, mine=["Opt"], mana_added={"C": 2})
    answer(s, prompt(s, TITANIA, "p1"), "pay:1")  # the {2}
    drain(s)
    assert zone_of(s, "Opt") == "p1:hand" and resolved(s, bolt, target) and not s.state.players["p1"].mana.get("C", 0)
    check(s)


def test_ward_discard_a_card_or_pay_two_declined_or_only_one_cost_available(cards):
    s, bolt, target = bolt_at(cards, TITANIA, mine=["Opt"])  # no mana beyond the Bolt's: only the discard can be paid
    d = prompt(s, TITANIA, "p1")
    assert {o.id for o in d.options} == {"pay:0", "decline"}
    answer(s, d, "decline")
    drain(s)
    assert zone_of(s, "Opt") == "p1:hand" and not resolved(s, bolt, target)  # countered
    check(s)

    s, bolt, target = bolt_at(cards, TITANIA)  # an empty hand and no mana: neither can be paid, so nothing is asked and the Bolt is countered
    drain(s)
    assert not resolved(s, bolt, target) and s.state.rules.decision is None
    check(s)


def test_ward_sacrifice_a_legendary_artifact_or_legendary_creature(cards):
    """Sauron, the Dark Lord: "Ward—Sacrifice a legendary artifact or legendary creature." — a Grizzly Bears is neither (118.3: nothing to pay with, so the
    Bolt is countered without a question); Raubahn, a legendary creature, pays it."""
    s, bolt, target = bolt_at(cards, SAURON, mine=["Grizzly Bears"])
    put(s, "Grizzly Bears")
    settle(s)  # (Bob orders the ward trigger and "amass Orcs 1")
    assert not resolved(s, bolt, target) and s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)

    s = build(cards, ["Lightning Bolt", RAUBAHN], [SAURON])
    sauron, bolt = put(s, SAURON, "p2"), to_hand(s, "Lightning Bolt")
    put(s, RAUBAHN)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[sauron.id])
    d = prompt(s, SAURON, "p1")
    assert {o.id for o in d.options} == {"pay", "decline"}
    answer(s, d, "pay")
    settle(s)
    assert zone_of(s, RAUBAHN) == "p1:graveyard" and resolved(s, bolt, sauron)
    check(s)


def test_ward_get_five_poison_counters_is_the_payers_not_the_controllers(cards):
    """The Serpent Society: "Ward—Get five poison counters." — the player who targeted it may get them (Alice, not Bob) or the spell is countered."""
    s, bolt, target = bolt_at(cards, SERPENT)
    d = prompt(s, SERPENT, "p1")
    assert {o.id for o in d.options} == {"pay", "decline"}
    answer(s, d, "pay")
    drain(s)
    assert s.state.players["p1"].resources["poison"] == 5 and s.state.players["p2"].resources["poison"] == 0 and resolved(s, bolt, target)
    check(s)

    s, bolt, target = bolt_at(cards, SERPENT)
    answer(s, prompt(s, SERPENT, "p1"), "decline")
    drain(s)
    assert s.state.players["p1"].resources["poison"] == 0 and not resolved(s, bolt, target)
    check(s)
