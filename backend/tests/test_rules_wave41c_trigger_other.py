"""Wave 41C: the trigger_other family, second pass (commanders first). Real Oracle text (tests/fixtures/wave41c_cards.json, from data/cards.sqlite). Every scenario
checks the replay and a save and a load (tests/wave9c_kit.check).

* 613.1d, 205.1b, 611.2a: "Vehicles you control become artifact creatures until end of turn" (The Thanos-Copter) and "Treasures you control become 3/3 Construct
  Assassin artifact creatures in addition to their other types until end of turn" (Vihaan): the plural of the wording read for one permanent, a group fixed as it resolves.
* 110.2a, 701.20a, 401.4: "… until they reveal a land card. Put that card onto the battlefield tapped under your control and the rest into their graveyard"
  (Sméagol), "You put that card onto the battlefield under your control and lose life equal to that permanent's mana value. That player puts the rest of the revealed
  cards on the bottom of their library in a random order" (Jhoira): put by you it is yours either way; the words add nothing to "Put that card onto the battlefield".
* 508.4, 400.7j: "exile up to one target creature you own, then return it to the battlefield under your control tapped and attacking" (The Neutrinos): a new object that
  enters again (its enters triggers), tapped, attacking, never declared as an attacker.
* 603.4, 113.6m: "if this card is in your graveyard, you may return it to the battlefield tapped and attacking" (Jocasta): "it" is the card in the graveyard.
* 701.21a, 701.9b, 118.12: "That player sacrifices a creature of their choice. If the player can't, you create …" (Wasitora), "That player discards a card at random.
  If the player can't, you draw a card" (Urgoros): the same probe as "If you don't" after a mandatory instruction (a permanent left / a card left the hand).
* 701.10b: "double the toughness of each creature you control" gives each +0/+X (X its toughness as it resolves); "Those creatures gain vigilance" are the ones doubled.
* 508.4, 110.2a: "It enters tapped and attacking and gains indestructible until end of turn" after a creature put onto the battlefield from the hand (Nick Fury).
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
from tests.test_rules_attachments import ch
from tests.test_rules_conditionals import settle, through_combat, until
from tests.test_rules_copy import choose, decision
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave41c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w41c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA if c["name"] != "Fire Shrine Keeper"]  # (Keeper is only a target for Thunderkin Awakener)


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)  # (with an id of its own: the printed characteristics are cached by it)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


def on_field(s, name, pid=None):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield") and (pid is None or c.controller == pid)]


def to_main1(s, turn):
    until(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def finish_turn(s):
    """Play on to the next turn's first main phase (this turn's end-step triggers resolve on the way)."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def attack(s, *pairs):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, s.state.rules.decision.player, type="declare_attackers", attackers=[{"card_id": a.id, "target": t} for a, t in pairs])


def cast_it(s, name, pid="p1", stop=False, **m):
    """The named card cast from the hand (moved there first) with the mana given; everything it starts resolves (``stop``: up to the first question asked)."""
    c = to_hand(s, name, pid)
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=c.id)
    asked(s) if stop else settle(s)
    return s.state.cards[c.id]


def resolve_stack(s, limit=40):
    """Resolve what is on the stack, answering the other questions the first way, and stop at the combat declarations."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def asked(s, limit=40):
    """Pass priority until a decision is pending (returned) or the stack is empty (None)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            return d
        if not s.state.zones.get("stack"):
            return None
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


# -- The Thanos-Copter: "When ~ enters, Vehicles you control become artifact creatures until end of turn." ------------------------------
def test_thanos_copter_makes_your_vehicles_creatures_until_end_of_turn_and_not_theirs(cards):
    """613.1d, 611.2a: Alice's Sky-Skiff and the Copter itself become artifact creatures; Sol Ring (not a Vehicle) and Bob's Sky-Skiff do not. At the end of the turn
    they are Vehicles again. Saved with the effect running."""
    s = build(cards, ["The Thanos-Copter", "Sky-Skiff", "Sol Ring"], theirs=["Sky-Skiff"])
    mine = put(s, "Sky-Skiff")
    ring = put(s, "Sol Ring")
    theirs = put(s, "Sky-Skiff", "p2")
    assert not ch(s, mine).is_creature  # (before: a Vehicle is no creature until crewed)
    copter = cast_it(s, "The Thanos-Copter", C=6)
    assert ch(s, mine).is_creature and ch(s, copter).is_creature and "Artifact" in ch(s, mine).types and "Vehicle" in ch(s, mine).subtypes
    assert not ch(s, ring).is_creature and not ch(s, theirs).is_creature
    s = reloaded(s)
    check(s)
    finish_turn(s)
    assert not ch(s, card_named(s, "Sky-Skiff")).is_creature and not ch(s, card_named(s, "The Thanos-Copter")).is_creature
    check(s)


def test_a_vehicle_entering_later_is_not_changed_by_an_earlier_copter(cards):
    """The group is fixed as the ability resolves (611.2c): a Vehicle that comes in afterwards stays a Vehicle."""
    s = build(cards, ["The Thanos-Copter", "Sky-Skiff"])
    cast_it(s, "The Thanos-Copter", C=6)
    late = put(s, "Sky-Skiff")
    settle(s)
    assert not ch(s, late).is_creature
    check(s)


# -- Vihaan, Goldwaker: "At the beginning of combat on your turn, you may have Treasures you control become 3/3 Construct Assassin artifact creatures in addition to
# their other types until end of turn." -----------------------------------------------------------------------------------------------
def treasure(s, pid="p1"):
    act(s, pid, type="create_token", player=pid, token={"name": "Treasure", "type_line": "Token Artifact — Treasure",
                                                         "text": "{T}, Sacrifice this token: Add one mana of any color."})
    return [c for c in s.state.cards.values() if c.name == "Treasure" and c.controller == pid][-1]


def test_vihaan_turns_your_treasures_into_creatures_in_addition_to_their_types_when_you_say_yes(cards):
    """205.1b, 613.1d-e, 611.2c: the Treasure tokens Alice controls become 3/3 Construct Assassin artifact creatures (still Treasures); Bob's does not. The question is
    asked at the beginning of combat (saved while it waits). They are plain Treasures again from the next turn."""
    s = build(cards, ["Vihaan, Goldwaker"])
    put(s, "Vihaan, Goldwaker")
    mine = treasure(s)
    treasure(s, "p2")
    until(s, lambda s: s.state.rules.decision is not None)
    assert s.state.turn.phase == "begin_combat" and not ch(s, mine).is_creature
    s = reloaded(s)
    mine = card_named(s, "Treasure")
    choose(s, "yes")
    asked(s)  # (the stack is empty: the declare attackers step is next)
    c = ch(s, mine)
    assert c.is_creature and {"Construct", "Assassin", "Treasure"} <= c.subtypes and {"Artifact", "Creature"} <= c.types
    assert pt(s, "Treasure") == (3, 3) and not ch(s, card_named(s, "Treasure", "p2")).is_creature
    check(s)
    finish_turn(s)
    assert not ch(s, card_named(s, "Treasure")).is_creature and ch(s, card_named(s, "Treasure")).subtypes == {"Treasure"}
    check(s)


def test_vihaan_does_nothing_when_you_say_no(cards):
    s = build(cards, ["Vihaan, Goldwaker"])
    put(s, "Vihaan, Goldwaker")
    mine = treasure(s)
    until(s, lambda s: s.state.rules.decision is not None)
    choose(s, "no")
    asked(s)
    assert not ch(s, mine).is_creature
    check(s)


# -- Sméagol, Helpful Guide: "Whenever the Ring tempts you, target opponent reveals cards from the top of their library until they reveal a land card. Put that card
# onto the battlefield tapped under your control and the rest into their graveyard." ---------------------------------------------------------
def kill(s, creature):
    """The creature dies (704.5g): lethal damage marked on it, state-based actions checked as priority passes."""
    act(s, "p1", type="set_damage", card_ids=[creature.id], value=99)
    act(s, "p1", type="pass_priority")
    settle(s)


def names(s, zone, pid):
    return [s.state.cards[c].name for c in s.state.zones.get(f"{pid}:{zone}", [])]


def test_smeagol_takes_the_first_land_of_their_library_tapped_and_the_rest_go_to_their_graveyard(cards):
    """701.20a, 110.2a, 400.3: a creature of Alice's died, so at her end step the Ring tempts her; Bob reveals Giant Growth, Lightning Bolt and Mountain. The Mountain
    (Bob's card) enters tapped under Alice's control, the two nonlands go to Bob's graveyard (the owner's, 404.1); the cards below stay in his library. Saved with the
    trigger on the stack."""
    s = build(cards, ["Sméagol, Helpful Guide", "Grizzly Bears"], theirs=["Giant Growth", "Lightning Bolt", "Mountain"])
    below = len(s.state.zones["p2:library"]) - 3
    put(s, "Sméagol, Helpful Guide")
    kill(s, put(s, "Grizzly Bears"))
    until(s, lambda s: s.state.turn.phase == "end" and s.state.rules.decision is not None)  # (the target of the Ring's trigger: the one opponent)
    s = reloaded(s)
    check(s)
    choose(s, "p2")
    asked(s)  # (it resolves at Alice's end step; the game has gone on to Bob's turn, where he drew the Island that was on top of what was left)
    (land,) = on_field(s, "Mountain")
    assert land.controller == "p1" and land.owner == "p2" and land.tapped
    assert sorted(names(s, "graveyard", "p2")) == ["Giant Growth", "Lightning Bolt"]
    assert names(s, "library", "p2") + names(s, "hand", "p2") == ["Island"] * below  # (the revealed cards left it, the ones below stay)
    check(s)


def test_smeagol_does_nothing_when_no_creature_died_under_your_control(cards):
    """603.4: the end step ability needs a creature that died under Alice's control this turn; none did, so the Ring does not tempt her and Bob's library is untouched."""
    s = build(cards, ["Sméagol, Helpful Guide", "Grizzly Bears"], theirs=["Giant Growth", "Lightning Bolt", "Mountain"])
    put(s, "Sméagol, Helpful Guide")
    put(s, "Grizzly Bears")
    finish_turn(s)  # (Bob's turn: he draws the top card, Giant Growth, as always)
    assert names(s, "graveyard", "p2") == [] and on_field(s, "Mountain") == []
    assert names(s, "hand", "p2") == ["Giant Growth"] and names(s, "library", "p2")[:2] == ["Lightning Bolt", "Mountain"]
    check(s)


# -- Jhoira, Weatherlight Corsair: "Whenever Jhoira enters or attacks, target opponent reveals cards from the top of their library until they reveal a historic permanent
# card. You put that card onto the battlefield under your control and lose life equal to that permanent's mana value. That player puts the rest of the revealed cards on
# the bottom of their library in a random order." ----------------------------------------------------------------------------------------
def test_jhoira_takes_the_first_historic_permanent_loses_life_for_its_mana_value_and_the_rest_go_to_the_bottom(cards):
    """701.20a, 110.2a, 119.4, 401.4: Bob reveals Grizzly Bears, Lightning Bolt and Ruby Medallion (an artifact, so historic, mana value 2). Alice puts the Medallion onto
    the battlefield under her control and loses 2 life; Bears and Bolt go to the bottom of Bob's library in a random order (replay is deterministic)."""
    s = build(cards, ["Jhoira, Weatherlight Corsair"], theirs=["Grizzly Bears", "Lightning Bolt", "Ruby Medallion"])
    size = len(s.state.zones["p2:library"])
    cast_it(s, "Jhoira, Weatherlight Corsair", stop=True, B=2, C=4)
    d = decision(s)
    assert d is not None and d.kind == "choose_one" and [o.id for o in d.options] == ["p2"]  # (target opponent)
    s = reloaded(s)
    choose(s, "p2")
    asked(s)
    (medallion,) = on_field(s, "Ruby Medallion")
    assert medallion.controller == "p1" and medallion.owner == "p2"
    assert life(s) == 40 - 2 and life(s, "p2") == 40
    library = names(s, "library", "p2")
    assert len(library) == size - 1 and sorted(library[-2:]) == ["Grizzly Bears", "Lightning Bolt"] and library[0] == "Island"
    assert names(s, "graveyard", "p2") == []
    check(s)


def test_jhoira_does_not_trigger_for_other_creatures_entering(cards):
    s = build(cards, ["Jhoira, Weatherlight Corsair", "Grizzly Bears"], theirs=["Grizzly Bears", "Lightning Bolt", "Ruby Medallion"])
    put(s, "Jhoira, Weatherlight Corsair")
    size = len(s.state.zones["p2:library"])
    cast_it(s, "Grizzly Bears", G=1, C=1)
    assert asked(s) is None and len(s.state.zones["p2:library"]) == size and on_field(s, "Ruby Medallion") == [] and life(s) == 40
    check(s)


def test_jhoira_attacking_with_no_historic_permanent_left_reveals_the_library_and_loses_nothing(cards):
    """701.20b: a library with no historic permanent card is revealed to the end; no card is put onto the battlefield, so no life is lost (there is no permanent), and the
    whole library goes back to the bottom of itself in a random order."""
    s = build(cards, ["Jhoira, Weatherlight Corsair"], theirs=["Grizzly Bears"])
    put(s, "Jhoira, Weatherlight Corsair")
    finish_turn(s)
    to_main1(s, 3)
    before = sorted(names(s, "library", "p2"))
    attack(s, (card_named(s, "Jhoira, Weatherlight Corsair"), "p2"))
    d = asked(s)
    assert d is not None
    choose(s, "p2")
    asked(s)
    assert sorted(names(s, "library", "p2")) == before and life(s) == 40
    through_combat(s)
    assert life(s, "p2") == 40 - 4  # (Jhoira's 4 combat damage, nothing else)
    check(s)


# -- The Neutrinos: "Whenever The Neutrinos attack, exile up to one target creature you own, then return it to the battlefield under your control tapped and attacking." --
def test_the_neutrinos_blink_a_creature_back_tapped_and_attacking_and_it_enters_again(cards):
    """508.4, 400.7, 603.6a: Mulldrifter (which did not attack) is exiled and returns as a new object tapped and attacking — never declared as an attacker; its enters
    ability draws two cards, The Neutrinos' Alliance gives them +1/+0, and both deal combat damage (3 + 2). Saved with the attack trigger waiting for its target."""
    s = build(cards, ["The Neutrinos", "Mulldrifter"], theirs=["Grizzly Bears"])
    put(s, "The Neutrinos")
    old = put(s, "Mulldrifter")
    put(s, "Grizzly Bears", "p2")  # (a creature that could block: the game stops at the declare blockers step)
    finish_turn(s)
    to_main1(s, 3)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (card_named(s, "The Neutrinos"), "p2"))
    d = asked(s)
    assert d is not None and old.id in [o.id for o in d.options]  # (up to one target creature you own)
    s = reloaded(s)
    choose(s, old.id)
    resolve_stack(s)  # (two triggers of the new Mulldrifter's entering: the draw and Alliance, in either order)
    (back,) = on_field(s, "Mulldrifter")
    assert back.tapped and back.attacking is not None and back.attacking.id == "p2"
    assert len(s.state.zones["p1:hand"]) == hand + 2  # (it entered again: "When this creature enters, draw two cards")
    assert pt(s, "The Neutrinos") == (3, 4)  # (Alliance — another creature entered)
    through_combat(s)
    assert life(s, "p2") == 40 - 3 - 2
    check(s)


def test_the_neutrinos_do_nothing_when_they_stay_home(cards):
    """Only The Neutrinos' own attack triggers it: Grizzly Bears attacking alone leaves Mulldrifter untouched (the same object, untapped, not attacking)."""
    s = build(cards, ["The Neutrinos", "Mulldrifter", "Grizzly Bears"])
    put(s, "The Neutrinos")
    old = put(s, "Mulldrifter")
    bears = put(s, "Grizzly Bears")
    finish_turn(s)
    to_main1(s, 3)
    attack(s, (bears, "p2"))
    assert asked(s) is None
    same = s.state.cards[old.id]
    assert same.zone == "p1:battlefield" and not same.tapped and same.attacking is None
    through_combat(s)
    assert life(s, "p2") == 40 - 2
    check(s)


# -- Jocasta, Automaton Avenger: "Whenever you attack with your commander, if this card is in your graveyard, you may return it to the battlefield tapped and attacking." --
def jocasta_table(cards):
    s = build(cards, ["Jocasta, Automaton Avenger", "Grizzly Bears"], theirs=["Grizzly Bears"])
    krenko = put(s, "Krenko, Mob Boss")  # (Alice's commander)
    bears = put(s, "Grizzly Bears")
    jocasta = card_named(s, "Jocasta, Automaton Avenger")
    act(s, "p1", type="move", card_ids=[jocasta.id], to={"player": "p1", "zone": "graveyard"})
    put(s, "Grizzly Bears", "p2")  # (a creature that could block: the game stops at the declare blockers step)
    finish_turn(s)
    to_main1(s, 3)
    return s, krenko, bears, jocasta


def test_jocasta_comes_back_from_the_graveyard_tapped_and_attacking_when_your_commander_attacks(cards):
    """603.4, 113.6m, 508.4: Krenko, Alice's commander, attacks; Jocasta is in her graveyard, so she may return it — tapped and attacking Bob, never declared as an
    attacker. Saved with the question waiting."""
    s, krenko, bears, jocasta = jocasta_table(cards)
    attack(s, (krenko, "p2"))
    d = asked(s)
    assert d is not None and d.kind == "confirm" and "Jocasta" in d.prompt
    s = reloaded(s)
    choose(s, "yes")
    resolve_stack(s)
    back = s.state.cards[jocasta.id]
    assert back.zone == "p1:battlefield" and back.tapped and back.attacking is not None and back.attacking.id == "p2"
    through_combat(s)
    check(s)


def test_jocasta_stays_in_the_graveyard_when_you_say_no_or_a_creature_that_is_not_your_commander_attacks(cards):
    s, krenko, bears, jocasta = jocasta_table(cards)
    attack(s, (bears, "p2"))  # (not a commander: no trigger, no question)
    assert asked(s).kind == "declare_blockers" and s.state.cards[jocasta.id].zone == "p1:graveyard"
    through_combat(s)
    finish_turn(s)
    to_main1(s, 5)
    attack(s, (krenko, "p2"))
    choose(s, "no")
    resolve_stack(s)
    assert s.state.cards[jocasta.id].zone == "p1:graveyard"
    check(s)


# -- Wasitora / Urgoros: "If the player can't, …" ---------------------------------------------------------------------------------------
def ready(cards, mine, theirs=(), board=False, empty_hand=False):
    """Alice's flyer is on the battlefield since turn 1; it is her turn 3, first main phase. Bob's ``theirs`` are on his battlefield (``board``) or in his hand (the
    Island he drew on turn 2 is there too; ``empty_hand`` exiles his hand)."""
    s = build(cards, mine, theirs=[*theirs])
    flyer = put(s, mine[0])
    for name in theirs:
        put(s, name, "p2") if board else to_hand(s, name, "p2")
    finish_turn(s)
    to_main1(s, 3)
    if empty_hand:
        for c in list(s.state.zones["p2:hand"]):
            act(s, "p2", type="move", card_ids=[c], to={"player": "p2", "zone": "exile"})
    return s, flyer


def swing(s, flyer, board=False):
    """The flyer attacks Bob and connects (a creature of his that could block is asked, and doesn't: it couldn't block a flyer); the combat damage trigger resolves."""
    attack(s, (flyer, "p2"))
    if board:
        until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
        act(s, "p2", type="declare_blockers", blocks=[])
    resolve_stack(s)


def test_wasitora_makes_them_sacrifice_a_creature_and_makes_no_token_when_they_had_one(cards):
    """701.21a: Bob has one creature, so he sacrifices it (the chosen one) and the 'can't' branch does not happen: no Cat Dragon token."""
    s, flyer = ready(cards, ["Wasitora, Nekoru Queen"], ["Grizzly Bears"], board=True)
    swing(s, flyer, board=True)
    assert on_field(s, "Grizzly Bears") == [] and zone(s, "Grizzly Bears", "p2") == "p2:graveyard"
    assert on_field(s, "Cat Dragon") == []
    check(s)
    s = reloaded(s)
    through_combat(s)
    check(s)


def test_wasitora_makes_a_cat_dragon_when_they_have_no_creature_to_sacrifice(cards):
    """701.21a, 118.12: Bob has no creature, nothing is sacrificed, so Alice creates a 3/3 black, red and green Cat Dragon creature token with flying."""
    s, flyer = ready(cards, ["Wasitora, Nekoru Queen"])
    swing(s, flyer)
    (token_,) = on_field(s, "Cat Dragon")
    assert token_.controller == "p1" and token_.is_token
    c = ch(s, token_)
    assert pt(s, "Cat Dragon") == (3, 3) and set(c.colors) == {"B", "R", "G"} and "flying" in {k.lower() for k in c.keywords}
    s = reloaded(s)
    through_combat(s)
    check(s)


def test_urgoros_makes_them_discard_at_random_and_draws_nothing_when_they_had_a_card(cards):
    s, flyer = ready(cards, ["Urgoros, the Empty One"], ["Giant Growth"])
    assert sorted(names(s, "hand", "p2")) == ["Giant Growth", "Island"]  # (the Growth, and the Island he drew)
    mine = len(s.state.zones["p1:hand"])
    swing(s, flyer)
    gone, kept = names(s, "graveyard", "p2"), names(s, "hand", "p2")  # (one of the two, at random: the replay and the save keep the same one)
    assert len(gone) == 1 and sorted(gone + kept) == ["Giant Growth", "Island"] and len(s.state.zones["p1:hand"]) == mine
    check(s)
    s = reloaded(s)
    through_combat(s)
    check(s)


def test_urgoros_draws_a_card_when_they_have_none_to_discard(cards):
    """701.9b, 118.12: Bob's hand is empty — nothing was discarded — so Alice draws a card."""
    s, flyer = ready(cards, ["Urgoros, the Empty One"], empty_hand=True)
    assert not s.state.zones["p2:hand"]
    mine = len(s.state.zones["p1:hand"])
    s = reloaded(s)
    swing(s, card_named(s, "Urgoros, the Empty One"))
    assert len(s.state.zones["p1:hand"]) == mine + 1 and names(s, "graveyard", "p2") == []
    check(s)


# -- God-Eternal Rhonas: "When God-Eternal Rhonas enters, double the power of each other creature you control until end of turn. Those creatures gain vigilance until end of turn." --
def ptc(s, c):
    """(power, toughness) of this very card."""
    from app.rules import sba
    from app.rules.plan import Plan

    card = s.state.cards[c.id]
    return sba.power(card, Plan(s.state, "p1", s.cards, None).ch(card)), sba.toughness(card, Plan(s.state, "p1", s.cards, None).ch(card))


def test_rhonas_doubles_the_power_of_your_other_creatures_and_those_gain_vigilance(cards):
    """701.10b, 613.4c: Grizzly Bears 2/2 becomes 4/2 and Llanowar Elves 1/1 becomes 2/1, both with vigilance; Rhonas himself (5/5) and Bob's Bears are not changed. A Bears that
    enters later is not one of "those creatures"."""
    s = build(cards, ["God-Eternal Rhonas", "Grizzly Bears", "Llanowar Elves", "Grizzly Bears"], theirs=["Grizzly Bears"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    theirs = put(s, "Grizzly Bears", "p2")
    rhonas = cast_it(s, "God-Eternal Rhonas", G=2, C=3)
    assert ptc(s, bears) == (4, 2) and ptc(s, elves) == (2, 1) and ptc(s, rhonas) == (5, 5) and ptc(s, theirs) == (2, 2)
    vigilant = lambda c: "vigilance" in {k.lower() for k in ch(s, c).keywords}  # noqa: E731
    assert vigilant(bears) and vigilant(elves) and not vigilant(rhonas) and not vigilant(theirs)
    s = reloaded(s)
    late = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[late.id], to={"player": "p1", "zone": "battlefield"})
    assert ptc(s, late) == (2, 2) and not vigilant(late)
    check(s)
    finish_turn(s)
    assert ptc(s, bears) == (2, 2) and ptc(s, elves) == (1, 1) and not vigilant(bears)  # (until end of turn)
    check(s)


# -- Rasaad yn Bashir: "Whenever Rasaad yn Bashir attacks, if you have the initiative, double the toughness of each creature you control until end of turn." --
def rasaad(cards, initiative):
    s = build(cards, ["Rasaad yn Bashir", "Grizzly Bears"], theirs=["Grizzly Bears"])
    boss = put(s, "Rasaad yn Bashir")
    bears = put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    if initiative:
        act(s, "p1", type="set_initiative", player="p1")  # (by hand: no trigger, no venture)
    finish_turn(s)
    to_main1(s, 3)
    attack(s, (boss, "p2"))
    resolve_stack(s)
    return s, boss, bears


def test_rasaad_doubles_the_toughness_of_your_creatures_when_you_have_the_initiative(cards):
    """701.10b: +0/+X with X the toughness as it resolves: Rasaad 0/3 becomes 0/6, Grizzly Bears 2/2 becomes 2/4 (the power is not doubled). He assigns combat damage equal to
    his toughness rather than his power: 6 to Bob."""
    s, boss, bears = rasaad(cards, True)
    assert ptc(s, boss) == (0, 6) and ptc(s, bears) == (2, 4)
    check(s)
    s = reloaded(s)
    act(s, "p2", type="declare_blockers", blocks=[])
    through_combat(s)
    assert life(s, "p2") == 40 - 6
    check(s)


def test_rasaad_without_the_initiative_changes_nothing(cards):
    s, boss, bears = rasaad(cards, False)
    assert ptc(s, boss) == (0, 3) and ptc(s, bears) == (2, 2)
    check(s)


# -- Nick Fury, Spymaster: "Whenever a creature you control attacks alone, draw a card. Then you may put a creature card with mana value 3 or less from your hand onto the
# battlefield. It enters tapped and attacking and gains indestructible until end of turn." -----------------------------------------------------------
def fury(cards):
    s = build(cards, ["Nick Fury, Spymaster", "Grizzly Bears", "Llanowar Elves", "Mulldrifter"], theirs=["Grizzly Bears"])
    boss = put(s, "Nick Fury, Spymaster")
    bears = put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")  # (a creature that could block: the game stops at the declare blockers step)
    elves, big = to_hand(s, "Llanowar Elves"), to_hand(s, "Mulldrifter")
    finish_turn(s)
    to_main1(s, 3)
    return s, boss, bears, elves, big


def test_nick_fury_draws_and_puts_a_cheap_creature_in_attacking_and_indestructible(cards):
    """508.4, 110.2a: Grizzly Bears attacks alone; Alice draws, then may put a creature card of mana value 3 or less from her hand (Mulldrifter, mana value 5, is not
    offered): Llanowar Elves enters tapped and attacking Bob with indestructible. Saved with the choice waiting."""
    s, boss, bears, elves, big = fury(cards)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (bears, "p2"))
    d = asked(s)
    assert d is not None and d.kind == "choose_cards" and [o.id for o in d.options] == [elves.id]
    assert len(s.state.zones["p1:hand"]) == hand + 1  # (the draw came first)
    s = reloaded(s)
    choose(s, elves.id)
    resolve_stack(s)
    e = s.state.cards[elves.id]
    assert e.zone == "p1:battlefield" and e.tapped and e.attacking is not None and e.attacking.id == "p2"
    assert "indestructible" in {k.lower() for k in ch(s, e).keywords} and s.state.cards[big.id].zone == "p1:hand"
    assert len(s.state.zones["p1:hand"]) == hand  # (+1 drawn, -1 put onto the battlefield)
    check(s)
    act(s, "p2", type="declare_blockers", blocks=[])
    through_combat(s)
    assert life(s, "p2") == 40 - 2 - 1
    check(s)
    finish_turn(s)
    assert "indestructible" not in {k.lower() for k in ch(s, s.state.cards[elves.id]).keywords}  # (until end of turn)


def test_nick_fury_may_decline_and_does_nothing_when_two_creatures_attack(cards):
    s, boss, bears, elves, big = fury(cards)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (bears, "p2"), (boss, "p2"))  # (not alone: no trigger, no draw)
    d = asked(s)
    assert d.kind == "declare_blockers" and len(s.state.zones["p1:hand"]) == hand
    check(s)
    s, boss, bears, elves, big = fury(cards)
    attack(s, (bears, "p2"))
    choose(s, *[])  # (declined: none put)
    resolve_stack(s)
    assert s.state.cards[elves.id].zone == "p1:hand" and len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


# -- collateral: the same readings, on cards the commanders share them with --------------------------------------------------------------------
def test_woebringer_demon_is_sacrificed_only_when_the_player_has_no_creature_to_sacrifice(cards):
    """701.21a, 118.12 (the same edict as Wasitora): at Bob's upkeep he sacrifices his creature and the Demon stays; with no creature at his next upkeep the Demon is sacrificed."""
    s = build(cards, ["Woebringer Demon"], theirs=["Grizzly Bears"])
    put(s, "Woebringer Demon")
    put(s, "Grizzly Bears", "p2")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert on_field(s, "Grizzly Bears") == [] and len(on_field(s, "Woebringer Demon")) == 1
    check(s)
    s = reloaded(s)
    finish_turn(s)  # (Alice's upkeep: she sacrifices a creature of her choice — the Demon is the only one)
    assert on_field(s, "Woebringer Demon") == []
    check(s)
    s = build(cards, ["Woebringer Demon"])
    put(s, "Woebringer Demon")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1" and s.state.rules.decision is None)
    assert on_field(s, "Woebringer Demon") == []  # (Bob had no creature: "If the player can't, sacrifice this creature")
    check(s)


def test_kruphixs_insight_puts_the_rest_of_the_revealed_cards_into_the_graveyard(cards):
    """701.20a, 404.1: the top six are revealed; Alice puts up to three enchantment cards from among them into her hand and the rest of the revealed cards into her graveyard."""
    s = build(cards, ["Kruphix's Insight", "Pacifism", "Arrest", "Grizzly Bears", "Giant Growth", "Lightning Bolt", "Sol Ring"])
    below = len(s.state.zones["p1:library"]) - 1 - 6
    c = to_hand(s, "Kruphix's Insight")
    mana(s, G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = asked(s)
    assert d is not None and d.kind == "choose_cards" and sorted(o.label for o in d.options) == ["Arrest", "Pacifism"]
    s = reloaded(s)
    choose(s, *[o.id for o in decision(s).options])
    resolve_stack(s)
    assert sorted(names(s, "hand", "p1")) == ["Arrest", "Pacifism"]
    assert sorted(names(s, "graveyard", "p1")) == ["Giant Growth", "Grizzly Bears", "Kruphix's Insight", "Lightning Bolt", "Sol Ring"]
    assert len(s.state.zones["p1:library"]) == below
    check(s)


def test_thunderkin_awakener_returns_the_chosen_card_tapped_and_attacking_and_sacrifices_it_at_the_next_end_step(cards):
    """508.4, 603.7: "Return that card to the battlefield tapped and attacking" — the card chosen as the ability's target, from the graveyard. Fire Shrine Keeper (toughness 1,
    less than the Awakener's 2) is the only legal target; it attacks Bob and is sacrificed at the beginning of the next end step."""
    s = build(cards, ["Thunderkin Awakener", "Fire Shrine Keeper"], theirs=["Grizzly Bears"])
    boss = put(s, "Thunderkin Awakener")
    keeper = card_named(s, "Fire Shrine Keeper")
    act(s, "p1", type="move", card_ids=[keeper.id], to={"player": "p1", "zone": "graveyard"})
    put(s, "Grizzly Bears", "p2")
    finish_turn(s)
    to_main1(s, 3)
    attack(s, (boss, "p2"))
    d = asked(s)
    assert d is not None and [o.id for o in d.options] == [keeper.id]
    s = reloaded(s)
    choose(s, keeper.id)
    resolve_stack(s)
    back = s.state.cards[keeper.id]
    assert back.zone == "p1:battlefield" and back.tapped and back.attacking is not None and back.attacking.id == "p2"
    act(s, "p2", type="declare_blockers", blocks=[])
    through_combat(s)
    assert life(s, "p2") == 40 - 1 - 1
    check(s)
    until(s, lambda s: s.state.turn.phase == "cleanup" or s.state.turn.number > 3)
    assert s.state.cards[keeper.id].zone == "p1:graveyard"
    check(s)


# -- near misses stay manual ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    # 506.3b: returned under its owner's control tapped and attacking — not read (only "under your control", the attacking player's)
    "Whenever ~ attacks, exile target creature you control, then return it to the battlefield under its owner's control tapped and attacking.",
    # "the player" is one player: several players' edicts, and an edict of two creatures (all or nothing, 118.3), are not read
    "At the beginning of your upkeep, each opponent sacrifices a creature of their choice. If the player can't, you draw a card.",
    "Whenever ~ deals combat damage to a player, that player sacrifices two creatures. If the player can't, you draw a card.",
    # a plural without a type word has no power and toughness to become (a Treasure would be 0/0)
    "When ~ enters, Treasures you control become creatures until end of turn.",
])
def test_near_misses_stay_manual(text):
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Probe Creature", "Creature — Test", text)
    assert coverage.of_characteristics(chs).level != "FULL", text
