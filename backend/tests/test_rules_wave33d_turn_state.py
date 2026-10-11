"""Wave 33D: conditions and counts about what happened this turn, researched against CR 2026-09-25, real Oracle text
(tests/fixtures/wave33d_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 120.3, 608.2i: damage dealt this turn is read from the log of the damage that was dealt (not prevented): a player's total ("if you were
  dealt 4 or more damage this turn", Boarded Window), one permanent's ("if this creature was dealt damage this turn", Wall of Resistance;
  "if 4 or more damage was dealt to it this turn" as it dies, Rushing-Tide Zubera), found by its object id (400.7, 603.10a).
* 603.4: an intervening "if" is checked as the trigger triggers and again as it resolves; 500.8 / 514.2: a new turn starts a new history.
* 508.6, 400.1, 601.2i, 702.122c: opponents attacked (Rose), cards put into exile (Ennis), the greatest mana value among the spells cast
  (Rootha), the creature that crewed a Vehicle as it was tapped (Adrestia).
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
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import creature, settle, through_combat, until
from tests.wave9c_kit import build, cast, check, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave33d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w33d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA]
# (the wording of Hidetsugu Consumes All's back face on a body that can be put onto the battlefield without turning a Saga over)
EXTRA += [card(f"Test Devourer {p}", set_code="w33d", number=f"S{p}", mana_cost="{3}", cmc=3.0, type_line="Creature — Ogre Shaman", power=str(p),
               toughness=str(p), oracle_text="Double strike\nWhenever this creature deals damage to a player, if it has dealt 10 or more damage "
                                             "to that player this turn, they lose the game.") for p in (4, 5)]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def zone(s, name, pid="p1"):
    return s.state.cards[named(s, name, pid).id].zone


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def to_main1(s, turn):
    until(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def to_end_step(s):
    until(s, lambda s: s.state.turn.phase == "end")


def finish_turn(s):
    """Play on to the next turn's first main phase (this turn's end-step triggers resolve on the way)."""
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def attack(s, *pairs):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, s.state.rules.decision.player, type="declare_attackers",
        attackers=[{"card_id": a.id, "target": t} for a, t in pairs])


def block(s, *pairs):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, s.state.rules.decision.player, type="declare_blockers",
        blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_this_turn_state_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    faces = c.get("card_faces")
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, faces, coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text", [
    "At the beginning of your end step, if you didn't play a card from exile this turn, create a tapped Powerstone token.",  # (a land played from exile isn't recorded)
    "Whenever one or more counters are put on a creature you control, if it's the first time counters have been put on that creature this turn, draw a card.",  # (first time: anchored to the event, not read)
    "At the beginning of your end step, if you attacked with a Hero this turn or a Hero entered the battlefield under your control this turn, draw a card.",
    "At the beginning of your end step, if a creature or planeswalker an opponent controlled was dealt excess damage this turn, draw a card.",  # (excess damage isn't recorded)
    "At the beginning of your end step, if a modified creature died under your control this turn, draw a card.",
])
def test_the_state_shapes_that_are_not_recorded_stay_manual(text):
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Test Enchantment", "Enchantment", text)
    assert coverage.of_characteristics(chs).level != "FULL"


@pytest.mark.parametrize("text, expected", [
    ("you were dealt 4 or more damage this turn", {"history": "damage", "who": "you", "n": 4}),
    ("a player was dealt combat damage by a Zombie this turn",
     {"history": "damage", "who": "any", "n": 1, "combat": True, "source": {"types": [], "supertypes": [], "subtypes": ["Zombie"]}}),
    ("~ was dealt damage this turn", {"history": "object", "object": "self", "what": "damaged", "n": 1}),
    ("that creature wasn't dealt damage this turn", {"history": "object", "object": "it", "what": "damaged", "n": 1, "negate": True}),
    ("4 or more damage was dealt to it this turn", {"history": "object", "object": "it", "what": "damaged", "n": 4}),
    ("it was dealt noncombat damage this turn", {"history": "object", "object": "it", "what": "damaged", "n": 1, "combat": False}),
    ("it has dealt 10 or more damage to that player this turn",
     {"history": "object", "object": "it", "what": "dealt_player", "n": 10, "to": "event"}),
    ("it was blocked this turn", {"history": "object", "object": "it", "what": "blocked"}),
    ("~ attacked or blocked this turn", {"history": "object", "object": "self", "what": "attacked_or_blocked"}),
    ("that creature entered this turn", {"history": "object", "object": "it", "what": "entered"}),
    ("it was the second spell you cast this turn", {"history": "cast_nth", "object": "it", "who": "you", "sel": 'sel:{"zones":["stack"]}', "n": 2}),
    ("you've drawn more than one card this turn", {"history": "drew", "n": 2}),
    ("you put a counter on ~ this turn",
     {"history": "facts", "kind": "counters", "who": "any", "self": True, "by": "you", "n": 1}),
    ("one or more cards were put into exile this turn", {"history": "facts", "kind": "exile", "who": "any", "n": 1}),
    ("an Assassin crewed it this turn",
     {"history": "facts", "kind": "crew", "who": "any", "sel": 'sel:{"subtypes":["Assassin"]}', "of_self": True, "n": 1}),
])
def test_wordings(text, expected):
    from app.rules import conditions

    assert conditions.parse(text, objects=True) == expected


@pytest.mark.parametrize("text", [
    "it's the first time counters have been put on that creature this turn",  # (anchored to its event: not read)
    "that creature was dealt excess damage this turn",  # (the log doesn't keep excess damage)
    "~ didn't attack or come under your control this turn",  # (control changes aren't recorded)
    "you didn't play a card from exile this turn",
    "an Assassin of your choice crewed it this turn",
])
def test_unrecorded_wordings_are_not_read(text):
    from app.rules import conditions

    assert conditions.parse(text, objects=True) is None


def bolt(s, target, pid="p1"):
    """Lightning Bolt at ``target``: a copy of the card, wherever it is (the table has two), is moved to the hand and cast."""
    c = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == pid and not c.zone.endswith(("hand", "stack")))
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=c.id, targets=[target])
    settle(s)


# -- "At the beginning of each end step, if you were dealt 4 or more damage this turn, exile this artifact." (Boarded Window) --------
def test_boarded_window_leaves_only_after_four_damage_in_one_turn(cards):
    """120.3: the total dealt to you this turn counts, not one source's: two Lightning Bolts (3 + 3) exile it, one Bolt (3) does not, and
    the 3 from the turn before is gone with that turn (500.8). A save between the damage and the end step keeps the log."""
    s = build(cards, ["Boarded Window", "Lightning Bolt", "Lightning Bolt"], forests=20)
    window = put(s, "Boarded Window")
    bolt(s, "p1")  # turn 1: one Bolt at yourself (3 damage): the Window stays
    assert s.state.players["p1"].life == 40 - 3
    s = reloaded(s)
    finish_turn(s)
    assert s.state.cards[window.id].zone == "p1:battlefield"
    check(s)
    to_main1(s, 3)  # turn 3: one Bolt again; 3 + 3 over two turns is not 4 in one: it stays
    bolt(s, "p1")
    finish_turn(s)
    assert s.state.cards[window.id].zone == "p1:battlefield"
    check(s)
    to_main1(s, 5)  # turn 5: two Bolts, 6 damage this turn
    bolt(s, "p1")
    bolt(s, "p1")
    s = reloaded(s)
    assert s.state.cards[window.id].zone == "p1:battlefield"
    finish_turn(s)
    assert s.state.cards[window.id].zone == "p1:exile"
    check(s)


# -- permanents dealt damage this turn: Wall of Resistance, the Zuberas -----------------------------------------------------------
def test_damage_dealt_to_a_permanent_this_turn_is_counted_where_it_died_and_it_resets_next_turn(cards):
    """120.3: Bob's 5/5 deals 5 to Rushing-Tide Zubera (4 or more: draws three as it dies), his 3/3 deals 3 to Burning-Eye Zubera (a
    3/3: it dies, but 3 is not 4: nothing), his 2/2 deals 2 to Wall of Resistance (+0/+1 at the end step). Next turn the Wall was dealt
    no damage, so no second counter (500.8). Saved with the Zubera trigger on the stack, and again before the end step."""
    s = build(cards, ["Wall of Resistance", "Rushing-Tide Zubera", "Burning-Eye Zubera"], forests=20)
    wall, rt, be = put(s, "Wall of Resistance"), put(s, "Rushing-Tide Zubera"), put(s, "Burning-Eye Zubera")
    big, small, tiny = token(s, "p2", "Big", "5/5"), token(s, "p2", "Small", "3/3"), token(s, "p2", "Tiny", "2/2")
    to_main1(s, 2)
    attack(s, (big, "p1"), (small, "p1"), (tiny, "p1"))
    s = reloaded(s)  # (saved with the attack declared)
    before = hand(s)
    block(s, (rt, big), (be, small), (wall, tiny))  # (combat damage is dealt, the dies triggers resolve on the way)
    assert zone(s, "Rushing-Tide Zubera") == "p1:graveyard" and zone(s, "Burning-Eye Zubera") == "p1:graveyard"
    assert hand(s) == before + 3  # (only the one that was dealt 5)
    check(s)
    s = reloaded(s)  # (saved after the damage, before the end step)
    assert s.state.turn.phase == "main2"
    finish_turn(s)
    assert s.state.cards[wall.id].counters.get("+0/+1") == 1
    check(s)
    to_main1(s, 3)
    finish_turn(s)  # (turn 3, nothing damaged the Wall)
    assert s.state.cards[wall.id].counters.get("+0/+1") == 1
    check(s)


# -- "Whenever a creature you control deals combat damage to a player, if that creature entered this turn, draw a card." (Samut) ------
def test_samut_draws_only_for_creatures_that_entered_this_turn(cards):
    """400.7, 603.4: each creature that deals the damage is asked whether it entered the battlefield this turn — by its object, so the
    creature that came last turn (or was created before) draws nothing, and the next turn starts a new history (500.8)."""
    s = build(cards, ["Samut, Vizier of Naktamun"], forests=20)
    samut = put(s, "Samut, Vizier of Naktamun")
    fresh = token(s, "p1", "Fresh", "2/2", "Haste")
    s = reloaded(s)  # (saved after they entered)
    before = hand(s)
    attack(s, (samut, "p2"), (named(s, "Fresh"), "p2"))
    through_combat(s)
    assert hand(s) == before + 2 and s.state.players["p2"].life == 40 - 2 - 2  # (both entered this turn)
    check(s)
    to_main1(s, 3)
    newer = token(s, "p1", "Newer", "2/2", "Haste")
    before = hand(s)
    attack(s, (samut, "p2"), (named(s, "Fresh"), "p2"), (newer, "p2"))
    through_combat(s)
    assert hand(s) == before + 1 and s.state.players["p2"].life == 40 - 4 - 6  # (only the one created this turn)
    check(s)
    assert fresh.id in s.state.cards


# -- "At the beginning of your end step, if one or more cards were put into exile this turn, put a +1/+1 counter on Ennis." (Ennis) ---
@pytest.mark.parametrize("target_is_a_token, counters", [(False, 1), (True, 0)])
def test_ennis_grows_only_when_a_card_was_put_into_exile_this_turn(cards, target_is_a_token, counters):
    """400.1, 111.7: Ennis exiling a creature CARD of yours puts a card into exile (the blink returns it at the end step): the counter; a
    token ceases to exist in exile and is no card: none. The next turn's history is empty again (500.8)."""
    s = build(cards, ["Ennis, Debate Moderator", "Llanowar Elves"], forests=20)
    friend = token(s, "p1", "Friend", "1/1") if target_is_a_token else put(s, "Llanowar Elves")
    to_hand(s, "Ennis, Debate Moderator")
    mana(s, W=1, G=1)
    cast(s, "Ennis, Debate Moderator")
    if s.state.rules.decision is not None:
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        settle(s)
    s = reloaded(s)  # (saved after the exile, before the end step)
    exiled = s.state.cards[friend.id].zone if friend.id in s.state.cards else "gone"
    assert exiled in ("p1:exile", "gone"), exiled
    ennis = named(s, "Ennis, Debate Moderator")
    finish_turn(s)
    assert s.state.cards[ennis.id].counters.get("+1/+1", 0) == counters
    if not target_is_a_token:
        assert s.state.cards[friend.id].zone == "p1:battlefield"  # (returned at the end step)
    check(s)
    to_main1(s, 3)
    finish_turn(s)  # (turn 3: nothing was exiled)
    assert s.state.cards[ennis.id].counters.get("+1/+1", 0) == counters
    check(s)


def build3(cards, mine=(), forests=9):
    """Alice, Bob and Carol (the turn order is p1, p2, p3)."""
    def deck_of(commander, spells, lands):
        return deck(cards, commander, [*((1, n) for n in spells), *lands])

    s = GameSession(enable(new_game([
        PlayerSetup("Alice", cards=deck_of("Krenko, Mob Boss", mine, [(forests, "Forest")])),
        PlayerSetup("Bob", cards=deck_of("Atraxa, Praetors' Voice", (), [(12, "Island")])),
        PlayerSetup("Carol", cards=deck_of("Atraxa, Praetors' Voice", (), [(12, "Island")]))], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def junk(s):
    return [c for c in s.state.cards.values() if c.name == "Junk" and c.owner == "p1" and c.zone == "p1:battlefield"]


# -- "Raid — At end of combat on your turn, if you attacked this turn, create a Junk token for each opponent you attacked." (Rose) ----
def test_rose_makes_a_junk_for_each_opponent_attacked_not_for_each_attacker(cards):
    """508.6: a player "has attacked [a player]" if they declared creatures attacking that player. Two creatures at Bob and Carol: two Junk
    tokens; two creatures at Bob alone: one more; no attack: none. (Saved before the end of combat.)"""
    s = build3(cards, ["Rose, Cutthroat Raider"])
    put(s, "Rose, Cutthroat Raider")
    one, two = token(s, "p1", "One", "2/2", "Haste"), token(s, "p1", "Two", "2/2", "Haste")
    attack(s, (one, "p2"), (two, "p3"))
    s = reloaded(s)
    through_combat(s)
    assert len(junk(s)) == 2
    check(s)
    to_main1(s, 4)  # (Alice's second turn in a three-player game)
    attack(s, (named(s, "One"), "p2"), (named(s, "Two"), "p2"))
    through_combat(s)
    assert len(junk(s)) == 3  # (two attackers, one opponent)
    check(s)
    to_main1(s, 7)
    until(s, lambda s: s.state.turn.phase == "main2")  # (nobody attacked this turn)
    assert len(junk(s)) == 3
    check(s)


def elementals(s):
    from app.rules import sba
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", s.cards, None)
    return sorted((sba.power(c, plan.ch(c)), sba.toughness(c, plan.ch(c))) for c in s.state.cards.values()
                  if c.name == "Elemental" and c.zone == "p1:battlefield")


# -- "…create an X/X … Elemental creature token …, where X is the greatest mana value among instant and sorcery spells you've cast this turn." (Rootha)
def test_rootha_makes_a_token_as_big_as_the_greatest_spell_cast_this_turn(cards):
    """601.2i: the notes of the spells cast this turn, as they were cast (even when they have resolved): Lightning Bolt (1) and Lava Axe (5)
    make a 5/5; the next turn only a Bolt, a 1/1 — this turn's history is new (500.8); a turn with no instant or sorcery makes none."""
    s = build(cards, ["Rootha, Mastering the Moment", "Lightning Bolt", "Lava Axe"], forests=20)
    put(s, "Rootha, Mastering the Moment")
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Lava Axe")
    mana(s, R=6)
    cast(s, "Lightning Bolt", targets=["p2"])
    cast(s, "Lava Axe", targets=["p2"])
    s = reloaded(s)  # (saved after the spells resolved, before combat)
    until(s, lambda s: s.state.turn.phase == "combat" or s.state.rules.decision is not None)
    until(s, lambda s: s.state.turn.phase == "main2")
    assert elementals(s) == [(5, 5)]
    check(s)
    to_main1(s, 3)
    c = named(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=["p2"])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert elementals(s) == [(1, 1), (5, 5)]
    check(s)
    to_main1(s, 5)
    until(s, lambda s: s.state.turn.phase == "main2")  # (no instant or sorcery cast: no trigger)
    assert elementals(s) == [(1, 1), (5, 5)]
    check(s)


# -- "Whenever Adrestia attacks, if an Assassin crewed it this turn, draw a card." (Adrestia) ----------------------------------
def test_adrestia_draws_only_when_an_assassin_crewed_it_this_turn(cards):
    """702.122c, Adrestia's ruling: the creature that was tapped to pay its crew cost, as it was then. Crewed by an Assassin: a card;
    next time by a plain creature: none (the Assassin that crewed it last turn doesn't count: 500.8). Saved after the crew."""
    s = build(cards, ["Adrestia"], forests=20)
    adrestia = put(s, "Adrestia")
    assassin = creature(s, "p1", "Assassin Pilot", "1/1", "Token Creature — Assassin")
    plain = creature(s, "p1", "Plain Pilot", "1/1")
    to_main1(s, 3)  # (no longer summoning sick)
    act(s, "p1", type="activate_ability", card_id=adrestia.id, ability=2, crew=[assassin.id])
    settle(s)
    s = reloaded(s)
    before = hand(s)
    attack(s, (adrestia, "p2"))
    through_combat(s)
    assert hand(s) == before + 1 and s.state.players["p2"].life == 40 - 4
    check(s)
    to_main1(s, 5)
    act(s, "p1", type="activate_ability", card_id=adrestia.id, ability=2, crew=[plain.id])
    settle(s)
    before = hand(s)
    attack(s, (adrestia, "p2"))
    through_combat(s)
    assert hand(s) == before and s.state.players["p2"].life == 40 - 4 - 4  # (crewed by a creature that is no Assassin)
    check(s)


def bobs_island(s):
    return next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone == "p2:library")


# -- "Whenever a land enters under an opponent's control, if that player had another land enter the battlefield under their control this
# turn, this creature deals 3 damage to that player." (Tunnel Ignus) ---------------------------------------------------------------
def test_tunnel_ignus_hurts_only_for_the_second_land_in_a_turn(cards):
    """603.4, the ruling: another land entered under that player's control earlier this turn (it doesn't matter if it is still there). Bob's
    first land of a turn does nothing and his second does; the next turn's first land does nothing again (500.8). Saved in between."""
    s = build(cards, ["Tunnel Ignus"], theirs=["Explore"], forests=20)
    put(s, "Tunnel Ignus")
    to_main1(s, 2)
    to_hand(s, "Explore", "p2")
    mana(s, "p2", G=1, U=1)
    cast(s, "Explore", "p2")  # (an additional land this turn)
    first = bobs_island(s)
    act(s, "p2", type="move", card_ids=[first.id], to={"zone": "hand"})
    act(s, "p2", type="play_land", card_id=first.id)
    settle(s)
    assert s.state.players["p2"].life == 40  # (no other land entered this turn)
    s = reloaded(s)
    second = bobs_island(s)
    act(s, "p2", type="move", card_ids=[second.id], to={"zone": "hand"})
    act(s, "p2", type="play_land", card_id=second.id)
    settle(s)
    assert s.state.players["p2"].life == 37  # (another land had entered under their control)
    check(s)
    to_main1(s, 4)
    third = bobs_island(s)
    act(s, "p2", type="move", card_ids=[third.id], to={"zone": "hand"})
    act(s, "p2", type="play_land", card_id=third.id)
    settle(s)
    assert s.state.players["p2"].life == 37  # (this turn's first land)
    check(s)


def answer(s):
    """Choose the first option of whatever decision is open (a target for a trigger, an order)."""
    while (d := s.state.rules.decision) is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        settle(s)


def cast_card(s, card, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card.id, **kw)
    settle(s)
    answer(s)


# -- "When this creature enters, if it was the second spell you cast this turn, put a +1/+1 counter on target creature." (Codespell Cleric) --
def test_codespell_cleric_counts_the_spells_cast_in_the_order_they_were_cast(cards):
    """601.2i, 608.3: the creature was the second spell Alice cast when it was cast after a Lightning Bolt; a Cleric cast first on another
    turn was not, and a spell cast after it doesn't change that. Saved between the cast and the resolution."""
    s = build(cards, ["Codespell Cleric", "Codespell Cleric", "Lightning Bolt"], forests=20)
    first, second = [c for c in s.state.cards.values() if c.name == "Codespell Cleric" and c.owner == "p1"]
    bolt_card = named(s, "Lightning Bolt")
    for c in (first, second, bolt_card):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, R=1, W=1)
    cast_card(s, bolt_card, targets=["p2"])  # the first spell this turn
    cast_card(s, first)  # the second: it enters and gets the counter on a creature (itself: the only one)
    assert s.state.cards[first.id].counters.get("+1/+1") == 1
    check(s)
    to_main1(s, 3)
    mana(s, W=1)
    cast_card(s, second)  # the first spell this turn: nothing
    assert s.state.cards[second.id].counters.get("+1/+1", 0) == 0 and s.state.cards[first.id].counters.get("+1/+1") == 1
    check(s)


def clues(s):
    return [c for c in s.state.cards.values() if c.name == "Clue" and c.owner == "p1" and c.zone == "p1:battlefield"]


# -- "Exile target creature. If it was dealt damage this turn, create a Clue token." (Sold Out) -----------------------------------
def test_sold_out_reads_the_damage_of_the_creature_it_exiled(cards):
    """608.2h, 400.7: the creature is gone (exiled) when "it was dealt damage this turn" is asked, so it is asked of the object that was
    there — damaged by a Lightning Bolt: a Clue. The same damage a turn later is gone (500.8): no Clue."""
    s = build(cards, ["Sold Out", "Lightning Bolt", "Lightning Bolt"], forests=20)
    hurt, fine = token(s, "p2", "Hurt", "4/4"), token(s, "p2", "Fine", "4/4")
    sold = named(s, "Sold Out")
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    for c in (sold, *bolts):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, R=2, B=4)
    cast_card(s, bolts[0], targets=[hurt.id])
    cast_card(s, bolts[1], targets=[fine.id])
    s = reloaded(s)  # (saved with both creatures damaged)
    cast_card(s, sold, targets=[hurt.id])
    assert hurt.id not in s.state.cards and len(clues(s)) == 1  # (a token exiled ceases to exist, 111.7)
    check(s)
    to_main1(s, 3)
    act(s, "p1", type="move", card_ids=[sold.id], to={"zone": "hand"})
    mana(s, B=4)
    cast_card(s, sold, targets=[fine.id])  # (it healed at the cleanup step, and the log is of another turn)
    assert fine.id not in s.state.cards and len(clues(s)) == 1
    check(s)


# -- "Whenever a creature deals combat damage to you, if Hixus entered this turn, exile that creature until Hixus leaves the battlefield." --
def test_hixus_exiles_the_attacker_only_in_the_turn_it_entered(cards):
    """603.4: asked as the damage is dealt and again as the trigger resolves. Hixus put onto the battlefield during Bob's first attack:
    the attacker is exiled (610.3: until Hixus leaves). On Bob's next attack Hixus did not enter this turn: the attacker is not."""
    s = build(cards, ["Hixus, Prison Warden"], ["Monastery Swiftspear"], forests=20)
    second = token(s, "p2", "Raider Two", "3/3")
    to_main1(s, 2)
    hixus = put(s, "Hixus, Prison Warden")  # (flashed in before blockers; its entering is in this turn's history)
    first = put(s, "Monastery Swiftspear", "p2")  # (haste)
    s = reloaded(s)
    attack(s, (first, "p1"))
    block(s)
    through_combat(s)
    assert s.state.players["p1"].life == 40 - 1 and s.state.cards[first.id].zone == "p2:exile"
    check(s)
    to_main1(s, 4)
    attack(s, (second, "p1"))
    block(s)
    through_combat(s)
    assert s.state.players["p1"].life == 40 - 1 - 3 and s.state.cards[second.id].zone == "p2:battlefield"
    assert s.state.cards[hixus.id].zone == "p1:battlefield"
    check(s)


# -- "When this creature dies, if it dealt combat damage to a player this turn, return it to the battlefield under its owner's control." --
def test_wave_of_rats_returns_only_if_it_dealt_combat_damage_to_a_player_this_turn(cards):
    """603.10a, 608.2i: asked of the creature as it died (its object, not the card in the graveyard): Rats A died before it dealt damage
    (stays dead); Rats B hit Bob in combat and died after it (comes back)."""
    s = build(cards, ["Wave of Rats", "Wave of Rats", "Lightning Bolt", "Lightning Bolt"], forests=20)
    a, b = [c for c in s.state.cards.values() if c.name == "Wave of Rats" and c.owner == "p1"]
    for c in (a, b):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    bolt(s, a.id)  # (it dealt no damage: dies for good)
    assert s.state.cards[a.id].zone == "p1:graveyard"
    to_main1(s, 3)
    attack(s, (b, "p2"))
    s = reloaded(s)
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 4
    bolt(s, b.id)  # (after its combat damage this turn)
    assert s.state.cards[b.id].zone == "p1:battlefield" and s.state.cards[a.id].zone == "p1:graveyard"
    check(s)


# -- "Whenever this creature deals damage to a player, if it has dealt 10 or more damage to that player this turn, they lose the game." --
@pytest.mark.parametrize("power, loses", [(5, True), (4, False)])
def test_ten_damage_to_one_player_in_one_turn_ends_the_game_not_over_two_turns(cards, power, loses):
    """The wording of Hidetsugu Consumes All's back face on a double striker (stand-in body): 5 + 5 in one combat is 10 and Bob loses as the
    second damage is dealt; 4 + 4 on each of two turns is 16 in all, never 10 in one turn (500.8)."""
    s = build(cards, [f"Test Devourer {power}"], forests=20)
    devourer = put(s, f"Test Devourer {power}")
    to_main1(s, 3)
    attack(s, (devourer, "p2"))
    s = reloaded(s)
    until(s, lambda s: s.state.turn.phase == "main2" or s.state.rules.winner is not None)
    assert (s.state.rules.winner == "p1") == loses
    if not loses:
        assert s.state.players["p2"].life == 40 - 2 * power
        to_main1(s, 5)
        attack(s, (devourer, "p2"))
        until(s, lambda s: s.state.turn.phase == "main2")
        assert s.state.players["p2"].life == 40 - 4 * power and s.state.rules.winner is None
    check(s)


# -- "At the beginning of your second main phase, if a player was dealt combat damage by a Zombie this turn, mill three cards, …" --
def test_lost_monarch_of_ifnir_mills_only_after_a_zombie_hit_a_player(cards):
    """510.2, 608.2i: the source's creature types as it dealt the damage (Zombie token: three cards milled; a plain 2/2 on the next turn: none)."""
    s = build(cards, ["Lost Monarch of Ifnir"], forests=20)
    put(s, "Lost Monarch of Ifnir")
    zombie = creature(s, "p1", "Zed", "2/2", "Token Creature — Zombie", "Haste")
    plain = creature(s, "p1", "Plain", "2/2", "Token Creature — Test", "Haste")
    library = len(s.state.zones["p1:library"])
    attack(s, (zombie, "p2"))
    s = reloaded(s)
    until(s, lambda s: s.state.turn.phase == "main2")
    answer(s)
    assert len(s.state.zones["p1:library"]) == library - 3
    check(s)
    to_main1(s, 3)
    library = len(s.state.zones["p1:library"])
    attack(s, (plain, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    answer(s)
    assert len(s.state.zones["p1:library"]) == library  # (a player was dealt combat damage, but not by a Zombie)
    check(s)


# -- "At the beginning of combat on your turn, if you've drawn more than one card this turn, put X +1/+1 counters on target creature you
# control, where X is the number of cards you've drawn this turn minus one." (Proft's Eidetic Memory) --------------------------------
def test_profts_eidetic_memory_counts_the_cards_drawn_this_turn_less_one(cards):
    """121.1: turn 3: the draw step and the enters trigger are two cards, one counter; turn 5: one card drawn, no counters."""
    s = build(cards, ["Proft's Eidetic Memory"], forests=20)
    cub = token(s, "p1", "Cub", "1/1")
    to_main1(s, 3)
    hand_card = to_hand(s, "Proft's Eidetic Memory")
    mana(s, U=1, G=1)
    act(s, "p1", type="cast_spell", card_id=hand_card.id)
    settle(s)
    answer(s)
    s = reloaded(s)
    until(s, lambda s: s.state.turn.phase == "main2")
    answer(s)
    assert s.state.cards[cub.id].counters.get("+1/+1") == 1
    check(s)
    to_main1(s, 5)
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.cards[cub.id].counters.get("+1/+1") == 1  # (turn 5: only the draw step)
    check(s)


def test_grasping_giant_still_exiles_the_creature_that_blocked_it(cards):
    """The "that creature" of a block event is the creature on the other side (509.3d), not the event's own: wave 33D reads Hixus's "exile
    that creature" as the event's creature only where no creature is on the other side."""
    s = build(cards, ["Grasping Giant"], forests=20)
    giant = put(s, "Grasping Giant")
    blocker = token(s, "p2", "Blocker", "1/1")
    to_main1(s, 3)
    attack(s, (giant, "p2"))
    block(s, (blocker, giant))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert blocker.id not in s.state.cards and s.state.cards[giant.id].zone == "p1:battlefield"  # (a token exiled ceases to exist)
    check(s)


@pytest.mark.parametrize("attacked, knights", [(("p2", "p3"), 2), (("p3",), 1), ((), 0)])
def test_militant_angel_makes_a_knight_for_each_opponent_attacked(cards, attacked, knights):
    """508.6, 608.2h: counted as the enters trigger resolves, from the attacks declared this turn (one opponent attacked twice counts once)."""
    s = build3(cards, ["Militant Angel"])
    angel = to_hand(s, "Militant Angel")
    runners = [token(s, "p1", f"Runner {i}", "2/2", "Haste") for i in range(len(attacked))]
    if attacked:
        attack(s, *[(r, p) for r, p in zip(runners, attacked, strict=True)])
        s = reloaded(s)
        through_combat(s)
    else:
        until(s, lambda s: s.state.turn.phase == "main2")
    mana(s, W=6, G=6)
    cast_card(s, s.state.cards[angel.id])
    assert len([c for c in s.state.cards.values() if c.name == "Knight" and c.owner == "p1"]) == knights
    check(s)


@pytest.mark.parametrize("attacked, castable", [(("p2", "p3"), True), ((), False)])
def test_fast_forward_costs_one_less_for_each_opponent_attacked(cards, attacked, castable):
    """601.2f: the cost is worked out as the spell is cast: {4}{R} less {1} for each opponent attacked this turn — three mana pay for it
    after attacking two opponents, not before any attack."""
    from app.game.errors import ActionError

    s = build3(cards, ["Fast Forward"])
    spell = to_hand(s, "Fast Forward")
    if attacked:
        runners = [token(s, "p1", f"Runner {i}", "2/2", "Haste") for i in range(len(attacked))]
        attack(s, *[(r, p) for r, p in zip(runners, attacked, strict=True)])
        s = reloaded(s)
        through_combat(s)
    else:
        until(s, lambda s: s.state.turn.phase == "main2")
    mana(s, R=1, G=2)
    if castable:
        cast_card(s, s.state.cards[spell.id])
        assert s.state.cards[spell.id].zone == "p1:graveyard"
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=spell.id)
    check(s)


def flies(s, card):
    from app.rules.plan import Plan

    return "flying" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id]).keywords


# -- "As long as you've put one or more +1/+1 counters on Beast this turn, he has flying." (Beast, Erudite Aerialist) ---------------
def test_beast_flies_for_the_turn_a_counter_was_put_on_it(cards):
    """122.6 (the player who puts them) and 611.3: flying from the counter you put on it, until that turn ends — the log of the turn, so a
    counter put in an earlier turn (it still has it) gives nothing now. Saved after the counter."""
    s = build(cards, ["Beast, Erudite Aerialist", "Battlegrowth"], forests=20)
    beast = put(s, "Beast, Erudite Aerialist")
    assert not flies(s, beast)
    to_hand(s, "Battlegrowth")
    mana(s, G=1)
    cast(s, "Battlegrowth", targets=[beast.id])
    assert s.state.cards[beast.id].counters.get("+1/+1") == 1 and flies(s, beast)
    s = reloaded(s)
    assert flies(s, beast)
    check(s)
    to_main1(s, 3)
    assert s.state.cards[beast.id].counters.get("+1/+1") == 1 and not flies(s, beast)  # (the counter is still there; this turn none was put)
    check(s)


# -- "When this creature dies, if it was blocked this turn, you gain 4 life." (Fyndhorn Druid) -----------------------------------------
def test_fyndhorn_druid_gains_life_only_if_it_was_blocked(cards):
    """509.1g, 603.10a: a creature that dies is read as it was: Druid A attacked and was blocked by a 4/4 (+4 life as it dies); Druid B
    blocked a 5/5 and died, but was never blocked itself (nothing). Saved between the combats."""
    s = build(cards, ["Fyndhorn Druid", "Fyndhorn Druid"], forests=20)
    a, b = [c for c in s.state.cards.values() if c.name == "Fyndhorn Druid" and c.owner == "p1"]
    for c in (a, b):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    wall, rhino = token(s, "p2", "Wall", "4/4"), token(s, "p2", "Rhino", "5/5")
    to_main1(s, 3)
    attack(s, (a, "p2"))
    block(s, (wall, a))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.cards[a.id].zone == "p1:graveyard" and s.state.players["p1"].life == 40 + 4
    s = reloaded(s)
    check(s)
    to_main1(s, 4)
    attack(s, (rhino, "p1"))
    block(s, (b, rhino))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.cards[b.id].zone == "p1:graveyard" and s.state.players["p1"].life == 40 + 4
    check(s)


# -- "At the beginning of your end step, if Kaito entered this turn, he phases out." (Kaito Shizuki) ----------------------------------
def test_kaito_shizuki_phases_out_only_at_the_end_of_the_turn_he_entered(cards):
    """The card names itself "Kaito" (201.5c). Entered on turn 1: phased out at its end step; it phases in during the untap step of turn 3
    (702.26b) and does not phase out again at that turn's end step: it did not enter this turn."""
    s = build(cards, ["Kaito Shizuki"], forests=20)
    kaito = to_hand(s, "Kaito Shizuki")
    mana(s, U=1, B=1, G=1)
    cast(s, "Kaito Shizuki")  # (it enters with its loyalty counters)
    s = reloaded(s)
    finish_turn(s)
    assert s.state.cards[kaito.id].zone == "p1:phased"
    check(s)
    to_main1(s, 3)
    assert s.state.cards[kaito.id].zone == "p1:battlefield"
    finish_turn(s)
    assert s.state.cards[kaito.id].zone == "p1:battlefield"
    check(s)


# -- "At the beginning of each end step, if this creature attacked or blocked this turn, its owner shuffles it into their library." ------
def test_inferno_hellion_shuffles_away_only_after_fighting(cards):
    """508.1, 509.1g: the 7/3 that stayed home is still there; the one that blocked is shuffled into its owner's library at the end step."""
    s = build(cards, ["Inferno Hellion", "Inferno Hellion"], forests=20)
    home, fighter = [c for c in s.state.cards.values() if c.name == "Inferno Hellion" and c.owner == "p1"]
    for c in (home, fighter):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    scout = token(s, "p2", "Scout", "1/1")
    finish_turn(s)  # (turn 1: neither attacked nor blocked)
    assert s.state.cards[home.id].zone == "p1:battlefield" and s.state.cards[fighter.id].zone == "p1:battlefield"
    attack(s, (scout, "p1"))
    block(s, (fighter, scout))
    s = reloaded(s)
    finish_turn(s)
    where = sorted(c.zone for c in s.state.cards.values() if c.name == "Inferno Hellion")  # (a card shuffled into a library is a new object, 400.7)
    assert where == ["p1:battlefield", "p1:library"] and s.state.cards[home.id].zone == "p1:battlefield"
    check(s)
