"""Wave 30J: trigger-event coverage, part 2 (CR 2026-09-25). Real Oracle text (tests/fixtures/wave30j_triggers_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 208.4b: effects that check a creature's base power and/or toughness see its characteristics after characteristic-defining abilities (613.4a) and
  the effects that set power and/or toughness (613.4b), ignoring effects and counters that modify without setting (613.4c): "a creature with
  power greater than its base power" (Kutzil, Ms. Marvel), "with base power 0" (Primo), "with base power and toughness 1/1" (Bess, Duskana).
  The base power of an animated land is the 2/2 its animation set (Mutavault), not a printed power it never had.
* 505.1a: only the first main phase of the turn is precombat, every other main phase is postcombat: "each of your postcombat main phases"
  (Kirri, Neheb, Tymna, Florian) triggers again for an additional main phase.
* 601.2i: the Nth spell a player has cast this turn — counted per player, of the kind and from the zone the wording names (Geralf, The
  Fantasticar, Sevinne); a copy is not cast (707.10).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage, events
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, mana_pool
from tests.test_rules_conditionals import settle, token_of, until
from tests.wave9c_kit import card_named, check, life, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30j_triggers_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t30j", number=f"J{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Kutzil, Malamet Exemplar", "Ms. Marvel, Elastic Ally", "Primo, the Unbounded", "Bess, Soul Nourisher", "Duskana, the Rage Mother",
        "Rapid Augmenter", "Neheb, the Eternal", "Tymna the Weaver", "Kirri, Talented Sprout", "Florian, Voldaren Scion",
        "Geralf, the Fleshwright", "The Fantasticar", "Sevinne, the Chronoclasm", "Thurid, Mare of Destiny", "Baird, Argivian Recruiter",
        "Thwart the Grave", "Vance's Blasting Cannons // Spitfire Bastion"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def pod(cards, mine=(), theirs=(), commander="Krenko, Mob Boss", players=2):
    """Alice (``commander`` and ``mine`` in her library), Bob (and Carol): rules automation on, Alice's first main phase."""
    setups = [PlayerSetup("Alice", cards=deck(cards, commander, [*((1, n) for n in mine), (20, "Forest")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (20, "Island")]))]
    if players == 3:
        setups.append(PlayerSetup("Carol", cards=deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")])))
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def to_attack(s, attacks=lambda s: [], stops=("main1", "declare_blockers", "main2")):
    """Alice's next turn (the first one her permanents can attack in): at her declare attackers step ``attacks(s)`` — (creature, defender) pairs —
    are declared; everyone then declares no blocks; she has priority in the declare blockers step."""
    act(s, "p1", type="set_prefs", stops_my_turn=list(stops))
    until(s, lambda s: s.state.turn.number >= 3 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
          and s.state.turn.active_player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in attacks(s)])
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1":
            return
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got to the declare blockers step")


def through_damage(s, phase="main2"):
    """Play on from the declare blockers step to ``phase`` (combat damage and every trigger resolved)."""
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.phase == phase and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never got to {phase}")


def hand(s, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.zone == f"{pid}:hand")


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_wordings_are_read():
    cond = events.parse_condition
    base = cond("a creature you control with power greater than its base power deals combat damage to a player")
    assert base is not None and base["event"] == "deal_combat_damage_player" and not base["aggregate"] and "power_gt_base" in base["sel"]
    each = cond("one or more creatures you control each with power greater than its base power deals combat damage to a player")
    assert each is not None and each["aggregate"] and "power_gt_base" in each["sel"]
    assert cond("one or more creatures you control with base power 0 deal combat damage to a player")["sel"].count("base_power") == 1  # type: ignore[index]
    pair = cond("a creature you control with base power and toughness 2/2 attacks")
    assert pair is not None and "base_power" in pair["sel"] and "base_toughness" in pair["sel"]
    # (the spell wordings: the Nth, of a kind, from a place, on your own turn; a list of three creature types)
    assert cond("you cast your first spell during each of your turns") == {
        "event": "cast", "subject": "player", "player": "you", "during": "you", "nth": 1, "spell": 'sel:{"zones":["stack"]}'}
    other = cond("you cast a spell during your turn other than your first spell that turn")
    assert other is not None and other["during"] == "you" and other["nth_min"] == 2
    fourth = cond("you cast your fourth noncreature spell each turn")
    assert fourth is not None and fourth["nth_note"] == 4 and "note_from" not in fourth
    grave = cond("you cast your first instant or sorcery spell from your graveyard each turn")
    assert grave is not None and grave["nth_note"] == 1 and grave["note_from"] == "graveyard"
    assert cond("you cast your third spell in a turn") == cond("you cast your third spell each turn")
    horses = cond("you cast a Pegasus, Unicorn, or Horse creature spell")
    assert horses is not None and "Pegasus" in horses["spell"] and "Horse" in horses["spell"] and "Unicorn" in horses["spell"]
    # (not read: an Nth spell of a kind with a condition the cast log doesn't record, or on someone else's turn)
    assert cond("you cast your second spell from exile each turn") is None
    assert cond("you cast your second creature spell with flying each turn") is None


# == base power: Kutzil, Malamet Exemplar (and Ms. Marvel, Elastic Ally) ==
def kutzil_table(cards, *mine):
    s = pod(cards, ["Kutzil, Malamet Exemplar", "Grizzly Bears", *mine])
    put(s, "Kutzil, Malamet Exemplar")
    bear = put(s, "Grizzly Bears")
    return s, bear


def next_attack(s, attacks, before=None):
    """The next of Alice's turns: ``before(s)`` in her first main phase, then she attacks as ``attacks`` (creature, defender); no blocks; she has
    priority in the declare blockers step."""
    n = s.state.turn.number
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"])
    if before is not None:
        until(s, lambda s: s.state.turn.number > n and s.state.turn.phase == "main1" and s.state.rules.decision is None
              and s.state.rules.priority == "p1" and not s.state.zones.get("stack"))
        before(s)
    until(s, lambda s: s.state.turn.number > n and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
          and s.state.turn.active_player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in attacks])
    for _ in range(20):
        d = s.state.rules.decision
        if d is None and s.state.turn.phase == "declare_blockers" and s.state.rules.priority == "p1":
            return
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got to the declare blockers step")


def test_kutzil_draws_when_a_pumped_creature_deals_combat_damage_not_a_plain_one(cards):
    """Kutzil: "Whenever one or more creatures you control each with power greater than its base power deals combat damage to a player, draw a
    card." The bears are a plain 2/2 (no card), then Giant Growth makes one a 5/5 (one card). (208.4b, 613.4c)"""
    s, bear = kutzil_table(cards, "Giant Growth")
    growth = to_hand(s, "Giant Growth")
    to_attack(s, lambda s: [(bear, "p2")])
    drawn = hand(s)
    through_damage(s)
    assert hand(s) == drawn and life(s, "p2") == 38  # unpumped: power 2 is its base power
    check(s)
    next_attack(s, [(bear, "p2")])  # the same bears next turn, pumped as the blockers are declared
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[bear.id])
    settle(s)
    assert pt(s, "Grizzly Bears") == (5, 5)
    drawn = hand(s)
    through_damage(s)
    assert life(s, "p2") == 33 and hand(s) == drawn + 1
    check(s)
    next_attack(s, [(bear, "p2")])  # the pump ended with the turn (514.2): a plain 2/2 again
    assert pt(s, "Grizzly Bears") == (2, 2)
    drawn = hand(s)
    through_damage(s)
    assert life(s, "p2") == 31 and hand(s) == drawn
    check(s)


def test_kutzil_draws_once_for_the_group_and_only_counts_the_creatures_over_their_base_power(cards):
    """Counters modify power without setting it (613.4c), so a bear with a +1/+1 counter is over its base power (208.4b). "One or more … deals
    combat damage" triggers once for the batch (603.2c): two bears with counters and a plain one are one card, not two or three."""
    s = pod(cards, ["Kutzil, Malamet Exemplar", "Grizzly Bears"])
    put(s, "Kutzil, Malamet Exemplar")
    one = put(s, "Grizzly Bears")
    two = token_of(s, "p1", "Bear B", "Token Creature — Bear", "2/2")
    plain = token_of(s, "p1", "Bear C", "Token Creature — Bear", "2/2")
    for c in (one, two):
        act(s, "p1", type="counter", card_ids=[c.id], kind="+1/+1", delta=1)
    to_attack(s, lambda s: [(one, "p2"), (two, "p2"), (plain, "p2")])
    drawn = hand(s)
    through_damage(s)
    assert life(s, "p2") == 40 - 3 - 3 - 2 and hand(s) == drawn + 1
    check(s)


def test_the_base_power_of_an_animated_land_is_the_2_2_that_set_it_not_a_printed_power(cards):
    """Mutavault: "{1}: Until end of turn, this land becomes a 2/2 creature with all creature types. It's still a land." (613.4b: layer 7b sets
    its base power and toughness to 2/2, whatever the card printed.) Attacking as that plain 2/2 draws nothing for Kutzil; a Giant Growth does."""
    s = pod(cards, ["Kutzil, Malamet Exemplar", "Mutavault", "Giant Growth"])
    put(s, "Kutzil, Malamet Exemplar")
    vault = put(s, "Mutavault")
    growth = to_hand(s, "Giant Growth")

    def animate(s):
        mana(s, C=1)
        act(s, "p1", type="activate_ability", card_id=vault.id, ability=1)
        settle(s)

    next_attack(s, [(vault, "p2")], before=animate)
    assert pt(s, "Mutavault") == (2, 2)
    drawn = hand(s)
    through_damage(s)
    assert life(s, "p2") == 38 and hand(s) == drawn
    check(s)
    next_attack(s, [(vault, "p2")], before=animate)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[vault.id])
    settle(s)
    drawn = hand(s)
    through_damage(s)
    assert life(s, "p2") == 33 and hand(s) == drawn + 1
    check(s)


def test_ms_marvel_draws_for_a_creature_over_its_base_power_once_each_turn(cards):
    """Ms. Marvel: "Whenever a creature you control with power greater than its base power deals combat damage to a player, draw a card. This
    ability triggers only once each turn." A plain bear that deals damage does not use up the turn's trigger; of the two bears with counters
    only one draws (the ability's own once-each-turn limit, app/rules/restrictions.py, not 603.2c's group); the next turn draws again."""
    s = pod(cards, ["Ms. Marvel, Elastic Ally", "Grizzly Bears"])
    put(s, "Ms. Marvel, Elastic Ally")
    one = put(s, "Grizzly Bears")
    two = token_of(s, "p1", "Bear B", "Token Creature — Bear", "2/2")
    plain = token_of(s, "p1", "Bear C", "Token Creature — Bear", "2/2")
    for c in (one, two):
        act(s, "p1", type="counter", card_ids=[c.id], kind="+1/+1", delta=1)
    to_attack(s, lambda s: [(plain, "p2"), (one, "p2"), (two, "p2")])
    drawn = hand(s)
    through_damage(s)
    assert life(s, "p2") == 40 - 8 and hand(s) == drawn + 1
    check(s)
    next_attack(s, [(two, "p2")])
    drawn = hand(s)
    through_damage(s)
    assert hand(s) == drawn + 1
    check(s)


# == base power: Primo, Bess, Duskana ==
def test_primo_counts_only_the_damage_of_the_creatures_with_base_power_0(cards):
    """Primo: "Trample / Primo enters with twice X +1/+1 counters on it. / Whenever one or more creatures you control with base power 0 deal
    combat damage to a player, create a 0/0 green and blue Fractal creature token. Put a number of +1/+1 counters on it equal to the damage
    dealt." Primo is 0/0 with two counters (base power 0): his 2 damage is dealt, the bears' (base power 2) is not part of it (603.2c)."""
    s = pod(cards, ["Primo, the Unbounded", "Grizzly Bears"])
    primo = to_hand(s, "Primo, the Unbounded")
    mana(s, G=2, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=primo.id, x_value=1)
    settle(s)
    assert zone_of(s, "Primo, the Unbounded") == "p1:battlefield" and pt(s, "Primo, the Unbounded") == (2, 2)
    bear = put(s, "Grizzly Bears")
    to_attack(s, lambda s: [(primo, "p2"), (bear, "p2")])
    through_damage(s)
    assert life(s, "p2") == 40 - 4
    (fractal,) = [c for c in s.state.cards.values() if c.name == "Fractal" and c.zone == "p1:battlefield"]
    assert fractal.counters == {"+1/+1": 2} and pt(s, "Fractal") == (2, 2)
    check(s)


def test_bess_counts_other_creatures_that_enter_with_base_power_and_toughness_1_1(cards):
    """Bess: "Whenever one or more other creatures you control with base power and toughness 1/1 enter, put a +1/+1 counter on Bess." Bess
    herself (a 1/1) is not "other"; Llanowar Elves (1/1) is; Grizzly Bears (2/2) is not."""
    s = pod(cards, ["Bess, Soul Nourisher", "Llanowar Elves", "Grizzly Bears"])
    bess = to_hand(s, "Bess, Soul Nourisher")
    mana(s, G=2, W=1)
    act(s, "p1", type="cast_spell", card_id=bess.id)
    settle(s)
    assert s.state.cards[bess.id].counters == {}
    elves = to_hand(s, "Llanowar Elves")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=elves.id)
    settle(s)
    assert s.state.cards[bess.id].counters == {"+1/+1": 1}
    check(s)
    bears = to_hand(s, "Grizzly Bears")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and s.state.cards[bess.id].counters == {"+1/+1": 1}
    check(s)


def test_duskana_reads_the_base_power_and_toughness_not_the_printed_ones_or_the_counters(cards):
    """Duskana: "Whenever a creature you control with base power and toughness 2/2 attacks, it gets +3/+3 until end of turn." A bear with a +1/+1
    counter is still base 2/2 (613.4c: a counter modifies) and attacks as a 6/6; the same bear turned into a 1/1 Frog (Turn to Frog sets the base,
    613.4b) is no longer base 2/2: it attacks as the 2/2 its counter makes it."""
    s = pod(cards, ["Duskana, the Rage Mother", "Grizzly Bears", "Turn to Frog"])
    put(s, "Duskana, the Rage Mother")
    bear = put(s, "Grizzly Bears")
    frog = to_hand(s, "Turn to Frog")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    to_attack(s, lambda s: [(bear, "p2")])
    assert pt(s, "Grizzly Bears") == (6, 6)
    through_damage(s)
    assert life(s, "p2") == 34
    check(s)

    def turn_to_frog(s):
        mana(s, U=2)
        act(s, "p1", type="cast_spell", card_id=frog.id, targets=[bear.id])
        settle(s)

    next_attack(s, [(bear, "p2")], before=turn_to_frog)
    assert pt(s, "Grizzly Bears") == (2, 2)
    through_damage(s)
    assert life(s, "p2") == 32
    check(s)


# == "each of your postcombat main phases": Kirri, Neheb, Tymna, Florian ==
def next_main2(s, pick=None):
    """Pass on until the next postcombat main phase has begun and what it triggered has resolved (a decision: the first options offered, or
    the option naming card ``pick``)."""
    left = s.state.turn.phase != "main2"
    for _ in range(120):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            chosen = [o.id for o in d.options if pick and o.card_id == pick] or ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen[: max(1, d.max_choices or 1)])
            continue
        left = left or s.state.turn.phase != "main2"
        if left and s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got to the postcombat main phase")


def bolt(s, target):
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[target])
    settle(s)


def test_kirri_returns_a_land_at_each_postcombat_main_phase_including_an_additional_one(cards):
    """Kirri: "At the beginning of each of your postcombat main phases, return target Plant, Treefolk, or land card from your graveyard to your
    hand." (505.1a: every main phase but the first is a postcombat one.) Relentless Assault ("After this main phase, there is an additional
    combat phase followed by an additional main phase.") makes two of them this turn: two lands come back; none on Bob's turn."""
    s = pod(cards, ["Kirri, Talented Sprout", "Relentless Assault"])
    put(s, "Kirri, Talented Sprout")
    lands = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:3]
    act(s, "p1", type="move", card_ids=[c.id for c in lands], to={"zone": "graveyard"})
    assault = to_hand(s, "Relentless Assault")
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=assault.id)
    settle(s)
    in_hand = lambda: sum(1 for c in lands if s.state.cards[c.id].zone == "p1:hand")  # noqa: E731
    assert in_hand() == 0
    next_main2(s)  # the additional main phase, after the additional combat
    assert in_hand() == 1
    check(s)
    next_main2(s)  # the turn's own second main phase
    assert in_hand() == 2
    check(s)
    for _ in range(80):  # Bob's turn: his postcombat main phase is not "your"
        if s.state.turn.active_player == "p2" and s.state.turn.phase == "main2":
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.turn.active_player == "p2" and in_hand() == 2 and s.state.cards[lands[2].id].zone == "p1:graveyard"
    check(s)


def test_neheb_adds_a_red_mana_for_each_life_your_opponents_lost_this_turn(cards):
    """Neheb: "At the beginning of each of your postcombat main phases, add {R} for each 1 life your opponents have lost this turn." Lightning
    Bolt (3) and an unblocked bear (2) are 5 life; the mana is there in the postcombat main phase."""
    s = pod(cards, ["Neheb, the Eternal", "Grizzly Bears", "Lightning Bolt"])
    put(s, "Neheb, the Eternal")
    bear = put(s, "Grizzly Bears")
    to_attack(s, lambda s: [(bear, "p2")])
    bolt(s, "p2")
    through_damage(s, phase="main2")
    assert life(s, "p2") == 35 and mana_pool(s) == {"R": 5}
    check(s)


def test_neheb_ignores_the_life_you_lost_yourself(cards):
    s = pod(cards, ["Neheb, the Eternal", "Lightning Bolt"])
    put(s, "Neheb, the Eternal")
    bolt(s, "p1")
    assert life(s, "p1") == 37
    next_main2(s)
    assert mana_pool(s) == {}
    check(s)


def test_tymna_pays_life_for_each_opponent_dealt_combat_damage_this_turn(cards):
    """Tymna the Weaver: "At the beginning of each of your postcombat main phases, you may pay X life, where X is the number of opponents that
    were dealt combat damage this turn. If you do, draw X cards." Bob is dealt combat damage by the bear (Carol is not: X is 1, not 2); a Bolt
    on Carol is no combat damage."""
    s = pod(cards, ["Tymna the Weaver", "Grizzly Bears", "Lightning Bolt"], players=3)
    put(s, "Tymna the Weaver")
    bear = put(s, "Grizzly Bears")
    to_attack(s, lambda s: [(bear, "p2")])
    bolt(s, "p3")
    drawn, mine = hand(s), life(s)
    through_damage(s, phase="main2")
    assert life(s, "p2") == 38 and life(s, "p3") == 37
    assert life(s) == mine - 1 and hand(s) == drawn + 1
    check(s)


def test_tymna_pays_nothing_when_no_opponent_was_dealt_combat_damage(cards):
    s = pod(cards, ["Tymna the Weaver", "Lightning Bolt"])
    put(s, "Tymna the Weaver")
    bolt(s, "p2")  # noncombat damage
    drawn, mine = hand(s), life(s)
    next_main2(s)
    assert life(s) == mine and hand(s) == drawn and life(s, "p2") == 37
    check(s)


def test_florian_looks_at_as_many_cards_as_the_life_your_opponents_lost_and_exiles_one_to_play(cards):
    """Florian: "At the beginning of each of your postcombat main phases, look at the top X cards of your library, where X is the total amount of
    life your opponents lost this turn. Exile one of those cards and put the rest on the bottom of your library in a random order. You may play
    the exiled card this turn." A Bolt is X = 3: the card exiled is one of the top three, and as a land it is played from exile."""
    s = pod(cards, ["Florian, Voldaren Scion", "Lightning Bolt"])
    put(s, "Florian, Voldaren Scion")
    bolt(s, "p2")
    library = [c for c in s.state.zones["p1:library"]]
    top3 = library[:3]
    next_main2(s)
    (exiled,) = [c for c in s.state.cards.values() if c.zone == "p1:exile" and c.owner == "p1"]
    after = list(s.state.zones["p1:library"])
    assert exiled.id in top3 and len(after) == len(library) - 1
    assert set(after[-2:]) == set(top3) - {exiled.id}  # the other two are on the bottom
    act(s, "p1", type="play_land", card_id=exiled.id)
    assert s.state.cards[exiled.id].zone == "p1:battlefield"
    check(s)


# == the Nth spell: Geralf, The Fantasticar, Sevinne; a list of creature types: Thurid ==
def zombies(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Zombie Rogue" and c.controller == pid and c.zone == f"{pid}:battlefield"]


def cast_now(s, name, pid="p1", *targets, **mana_):
    c = to_hand(s, name, pid)
    mana(s, pid, **mana_)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets))
    return c


def test_geralf_makes_a_zombie_for_each_of_your_spells_after_the_first_each_turn_counted_per_player(cards):
    """Geralf: "Whenever you cast a spell during your turn other than your first spell that turn, create a 2/2 blue and black Zombie Rogue creature
    token." Bob casts a Lightning Bolt in Alice's upkeep: that is Bob's spell, so Alice's first spell afterwards is still her first (601.2i: counted
    per player), and only her second makes the token."""
    s = pod(cards, ["Geralf, the Fleshwright", "Giant Growth", "Lightning Bolt", "Opt"], theirs=["Lightning Bolt"])
    geralf = put(s, "Geralf, the Fleshwright")
    act(s, "p1", type="set_prefs", stops_my_turn=["upkeep", "main1", "main2"])
    act(s, "p2", type="set_prefs", stops_their_turn=["upkeep"])  # (Bob stops in Alice's upkeep)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "upkeep" and s.state.rules.priority == "p2" and s.state.rules.decision is None)
    cast_now(s, "Lightning Bolt", "p2", "p1", R=1)
    settle(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None and not s.state.zones.get("stack"))
    assert life(s) == 37 and not zombies(s)
    cast_now(s, "Giant Growth", "p1", geralf.id, G=1)  # Alice's first spell this turn
    settle(s)
    assert not zombies(s)
    check(s)
    cast_now(s, "Lightning Bolt", "p1", "p2", R=1)  # her second
    settle(s)
    (first,) = zombies(s)
    assert first.counters == {}  # (its own entering does not count: "each other Zombie")
    cast_now(s, "Opt", "p1", U=1)  # her third
    settle(s)
    assert len(zombies(s)) == 2
    second = next(z for z in zombies(s) if z.id != first.id)
    assert second.counters == {"+1/+1": 1} and s.state.cards[first.id].counters == {}  # the second counts the first, not itself
    check(s)


def constructs(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Construct" and c.controller == pid and c.zone == f"{pid}:battlefield"]


def test_the_fantasticar_counts_your_noncreature_spells_not_bobs(cards):
    """The Fantasticar: "Whenever you cast your fourth noncreature spell each turn, you may sacrifice The Fantasticar. If you do, create four
    4/4 colorless Construct artifact creature tokens with flying and haste." Bob answers Alice's third noncreature spell with a Lightning Bolt of
    his own: Bob's spell is not one of hers, so her fourth is the next one, not that."""
    s = pod(cards, ["The Fantasticar", "Sol Ring", "Opt", "Bonesplitter", "Lightning Bolt"], theirs=["Lightning Bolt"])
    put(s, "The Fantasticar")
    act(s, "p2", type="set_prefs", response="on")  # (Bob stops to respond to every spell)
    for name, cost in (("Sol Ring", {"C": 1}), ("Opt", {"U": 1})):
        cast_now(s, name, "p1", **cost)
        settle(s)
    cast_now(s, "Bonesplitter", "p1", C=1)  # her third
    for _ in range(6):  # Alice passes (the Fantasticar's own "become a creature?" is answered the plain way) until Bob has priority
        if (d := s.state.rules.decision) is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.rules.priority == "p1" and s.state.zones.get("stack"):
            act(s, "p1", type="pass_priority")
        else:
            break
    assert s.state.rules.priority == "p2" and s.state.zones.get("stack")
    cast_now(s, "Lightning Bolt", "p2", "p1", R=1)  # Bob's first
    settle(s)
    assert zone_of(s, "The Fantasticar") == "p1:battlefield" and not constructs(s)
    check(s)
    cast_now(s, "Lightning Bolt", "p1", "p2", R=1)  # her fourth
    settle(s)
    assert zone_of(s, "The Fantasticar") != "p1:battlefield" and len(constructs(s)) == 4 and pt(s, "Construct") == (4, 4)
    check(s)


def test_the_fantasticar_is_kept_by_a_player_who_casts_three_noncreature_spells(cards):
    s = pod(cards, ["The Fantasticar", "Sol Ring", "Opt", "Bonesplitter"])
    put(s, "The Fantasticar")
    for name, cost in (("Sol Ring", {"C": 1}), ("Opt", {"U": 1}), ("Bonesplitter", {"C": 1})):
        cast_now(s, name, "p1", **cost)
        settle(s)
    assert zone_of(s, "The Fantasticar") == "p1:battlefield" and not constructs(s)
    check(s)


def test_sevinne_copies_the_first_instant_or_sorcery_you_cast_from_your_graveyard_each_turn(cards):
    """Sevinne: "Whenever you cast your first instant or sorcery spell from your graveyard each turn, copy that spell. You may choose new targets
    for the copy." A Lightning Bolt from the hand is not from the graveyard (601.2a); Firebolt's flashback is the first one (the copy is not
    cast, 707.10: so no second copy); Think Twice's flashback is the second one this turn: no copy."""
    s = pod(cards, ["Sevinne, the Chronoclasm", "Firebolt", "Think Twice", "Lightning Bolt"])
    put(s, "Sevinne, the Chronoclasm")
    act(s, "p1", type="move", card_ids=[card_named(s, "Firebolt").id, card_named(s, "Think Twice").id], to={"zone": "graveyard"})
    cast_now(s, "Lightning Bolt", "p1", "p2", R=1)
    settle(s)
    assert life(s, "p2") == 37
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Firebolt").id, targets=["p2"])  # flashback {4}{R}
    settle(s)
    assert life(s, "p2") == 33 and zone_of(s, "Firebolt") == "p1:exile"  # 37 - 2 - 2 (the copy)
    check(s)
    drawn = hand(s)
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Think Twice").id)  # flashback {2}{U}
    settle(s)
    assert hand(s) == drawn + 1 and zone_of(s, "Think Twice") == "p1:exile"  # one card, not two
    check(s)


def test_thurid_copies_a_pegasus_unicorn_or_horse_creature_spell(cards):
    """Thurid: "Whenever you cast a Pegasus, Unicorn, or Horse creature spell, copy it." Pegasus Courser is copied (the copy is a token); a
    Grizzly Bears is not."""
    s = pod(cards, ["Thurid, Mare of Destiny", "Pegasus Courser", "Grizzly Bears"])
    put(s, "Thurid, Mare of Destiny")
    cast_now(s, "Grizzly Bears", "p1", G=2)
    settle(s)
    assert [c.name for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield"] == ["Grizzly Bears"]
    check(s)
    cast_now(s, "Pegasus Courser", "p1", W=1, C=2)
    settle(s)
    coursers = [c for c in s.state.cards.values() if c.name == "Pegasus Courser" and c.zone == "p1:battlefield"]
    assert len(coursers) == 2 and sorted(c.is_token for c in coursers) == [False, True]
    assert pt(s, "Pegasus Courser") == (2, 4)  # (Thurid: other Pegasi, Unicorns, and Horses get +1/+1)
    check(s)


# == what the same wordings gave other cards ==
def test_baird_makes_a_soldier_only_while_you_control_a_creature_over_its_base_power(cards):
    """Baird, Argivian Recruiter: "At the beginning of your end step, if you control a creature with power greater than its base power, create a
    1/1 white Soldier creature token." (603.4: checked as the end step begins.) A plain 2/2 bear is no such creature; with a +1/+1 counter it is."""
    s = pod(cards, ["Baird, Argivian Recruiter", "Grizzly Bears"])
    put(s, "Baird, Argivian Recruiter")
    bear = put(s, "Grizzly Bears")

    def soldiers():
        return sum(1 for c in s.state.cards.values() if c.name == "Soldier" and c.zone == "p1:battlefield")

    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert soldiers() == 0
    check(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")
    assert soldiers() == 1
    check(s)


def test_thwart_the_grave_returns_a_creature_card_and_a_cleric_rogue_warrior_or_wizard_card(cards):
    """Thwart the Grave: "Return target creature card and up to one target Cleric, Rogue, Warrior, or Wizard creature card from your graveyard to
    the battlefield." A list of four kinds is read like one of two: Tymna (a Cleric) is a legal second target, Llanowar Elves (an Elf Druid) is not."""
    s = pod(cards, ["Thwart the Grave", "Grizzly Bears", "Tymna the Weaver", "Llanowar Elves"])
    act(s, "p1", type="move", card_ids=[card_named(s, n).id for n in ("Grizzly Bears", "Tymna the Weaver", "Llanowar Elves")], to={"zone": "graveyard"})
    thwart = to_hand(s, "Thwart the Grave")
    mana(s, B=2, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=thwart.id, targets=[card_named(s, "Grizzly Bears").id, card_named(s, "Llanowar Elves").id], target_counts=[1, 1])
    act(s, "p1", type="cast_spell", card_id=thwart.id, targets=[card_named(s, "Grizzly Bears").id, card_named(s, "Tymna the Weaver").id], target_counts=[1, 1])
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, "Tymna the Weaver") == "p1:battlefield"
    assert zone_of(s, "Llanowar Elves") == "p1:graveyard"
    check(s)


def test_vances_blasting_cannons_transforms_on_the_third_spell_of_a_turn(cards):
    """Vance's Blasting Cannons: "Whenever you cast your third spell in a turn, you may transform Vance's Blasting Cannons." Two spells do not."""
    s = pod(cards, ["Vance's Blasting Cannons // Spitfire Bastion", "Sol Ring", "Opt", "Bonesplitter"])
    cannons = put(s, "Vance's Blasting Cannons // Spitfire Bastion")
    for name, cost in (("Sol Ring", {"C": 1}), ("Opt", {"U": 1})):
        cast_now(s, name, "p1", **cost)
        settle(s)
    assert s.state.cards[cannons.id].face == 0
    check(s)
    cast_now(s, "Bonesplitter", "p1", C=1)
    settle(s)
    assert s.state.cards[cannons.id].face == 1
    check(s)


def test_rakdos_makes_creature_spells_cost_less_for_each_life_your_opponents_lost_not_you(cards):
    """Rakdos, Lord of Riots: "Creature spells you cast cost {1} less to cast for each 1 life your opponents have lost this turn." Firebolt at
    Alice herself is no reduction; Lightning Bolt at Bob (3) makes Mulldrifter ({4}{U}) cost {1}{U}."""
    s = pod(cards, ["Rakdos, Lord of Riots", "Mulldrifter", "Lightning Bolt", "Firebolt"])
    put(s, "Rakdos, Lord of Riots")
    cast_now(s, "Firebolt", "p1", "p1", R=1)
    settle(s)
    assert life(s) == 38
    drifter = to_hand(s, "Mulldrifter")
    mana(s, U=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=drifter.id)
    bolt(s, "p2")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=drifter.id)
    settle(s)
    assert zone_of(s, "Mulldrifter") == "p1:battlefield" and life(s, "p2") == 37
    check(s)


def test_zinnia_gets_power_for_each_other_creature_with_base_power_1(cards):
    """Zinnia, Valley's Voice: "Zinnia gets +X/+0, where X is the number of other creatures you control with base power 1." Llanowar Elves counts,
    pumped or not (the pump modifies, 613.4c); Grizzly Bears counts once Turn to Frog has set its base power to 1 (613.4b); Zinnia herself does not."""
    s = pod(cards, ["Zinnia, Valley's Voice", "Llanowar Elves", "Grizzly Bears", "Giant Growth", "Turn to Frog"])
    put(s, "Zinnia, Valley's Voice")
    elves = put(s, "Llanowar Elves")
    bears = put(s, "Grizzly Bears")
    assert pt(s, "Zinnia, Valley's Voice") == (2, 3)  # 1 + 1 (the Elves)
    cast_now(s, "Giant Growth", "p1", elves.id, G=1)
    settle(s)
    assert pt(s, "Llanowar Elves") == (4, 4) and pt(s, "Zinnia, Valley's Voice") == (2, 3)
    cast_now(s, "Turn to Frog", "p1", bears.id, U=2)
    settle(s)
    assert pt(s, "Grizzly Bears") == (1, 1) and pt(s, "Zinnia, Valley's Voice") == (3, 3)
    check(s)


def test_the_base_power_of_a_creature_that_left_is_kept_as_it_last_existed(cards):
    """608.2h, 208.4b: a creature that left the battlefield is read as it last existed there, base power included (a +1/+1 counter and Turn to
    Frog's 1/1: power 2, base power 1) — the snapshot a "deals combat damage" trigger falls back on once the source is gone."""
    s = pod(cards, ["Grizzly Bears", "Turn to Frog", "Lightning Bolt"])
    bear = put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    cast_now(s, "Turn to Frog", "p1", bear.id, U=2)
    settle(s)
    assert pt(s, "Grizzly Bears") == (2, 2)
    oid = s.state.rules.object_id(bear.id)
    cast_now(s, "Lightning Bolt", "p1", bear.id, R=1)  # (the rules engine moves it: last known information is recorded then)
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard"
    snap = s.state.rules.lki[oid]
    assert (snap.power, snap.toughness, snap.base_power, snap.base_toughness) == (2, 2, 1, 1)
    check(s)
