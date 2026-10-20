"""Wave 42B: this-turn state, second pass (commanders first), researched against CR 2026-09-25, real Oracle text
(tests/fixtures/wave42b_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 603.2, 400.7: "a creature you control becomes tapped for the first time each turn" (Captain America), "counters are put on a creature you control
  for the first time each turn" (Stalwart Successor, Botanical Brawler): the first such event of THAT object this turn, kept at the event choke point
  (once-a-turn marks / the turn's log), so a new turn starts over and an object that left and came back (a new object) starts over too.
* 608.2i, 201.2a, 700.4: "a creature not named Ebondeath, Dracolich died this turn" reads the name the creature had as it last existed (a copy of
  Ebondeath that died was named so), whether or not it is still anywhere.
* 120.3, 608.2i: "a source you controlled dealt 5 or more damage this turn" is ONE source's total over every recipient and every damage event, it need only
  have been under your control as it dealt it (the ruling for Dragon Cultist); a source that has left still counts.
* 119.3: "the amount of life you gained this turn or the amount of life you lost this turn, whichever is greater" (Willowdusk).
* 603.7, 400.3: "When target creature is put into your graveyard this turn" (Saffi) watches the object the target was, into its owner's graveyard.
* 508.3a, 725.1: "attacks the monarch" is an attack on the player who is the monarch (Okoye).
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
from tests.game_helpers import act, mana_pool
from tests.test_rules_attachments import token
from tests.test_rules_conditionals import settle, through_combat, until
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave42b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w42b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Captain America, Living Legend", "Stalwart Successor", "Botanical Brawler", "Ebondeath, Dracolich", "Dragon Cultist",
        "Willowdusk, Essence Seer", "Saffi Eriksdotter", "Okoye, Mighty and Adored", "Gimli, Mournful Avenger"]


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


def to_main1(s, turn):
    until(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def finish_turn(s):
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > turn and s.state.turn.phase == "main1" and s.state.rules.decision is None)


def tapped(s, c):
    return s.state.cards[c.id].tapped


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_this_turn_state_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


@pytest.mark.parametrize("text, expected", [
    ("a creature not named ~ died this turn",
     {"history": "departed", "sel": 'sel:{"types":["Creature"]}', "n": 1, "op": ">=", "died": True, "not_named": True}),
    ("a source you controlled dealt 5 or more damage this turn", {"history": "source_damage", "who": "you", "n": 5}),
])
def test_wordings(text, expected):
    from app.rules import conditions

    assert conditions.parse(text, objects=True) == expected


@pytest.mark.parametrize("text", [
    "a source an opponent controlled dealt 5 or more damage this turn",  # (only what you controlled as it dealt it is recorded by source)
    "it's the first time counters have been put on that creature this turn",  # (anchored to its event: only read as the trigger's own "if", scripts._first_time_gate)
])
def test_unread_wordings_are_not_read(text):
    from app.rules import conditions

    assert conditions.parse(text, objects=True) is None


def test_literal_history_name_does_not_rebind_to_its_differently_named_source(cards):
    from app.rules import conditions
    from app.rules.plan import Plan

    s = build(cards, ['Ebondeath, Dracolich', 'Lightning Bolt', 'Lightning Bolt'], forests=20)
    source = card_named(s, 'Ebondeath, Dracolich')
    act(s, 'p1', type='move', card_ids=[source.id], to={'zone': 'graveyard'})
    named = token(s, 'p2', 'Krenko', '2/2')
    bolt(s, named.id)
    condition = conditions.parse('a creature not named Krenko died this turn', objects=True)
    assert condition is not None
    context = {'controller': 'p1', 'source_card': source.id, 'source_object': s.state.rules.object_id(source.id)}
    assert not conditions.holds(Plan(s.state, 'p1', cards, None), context, condition)
    other = token(s, 'p2', 'Bear Token', '2/2')
    bolt(s, other.id)
    assert conditions.holds(Plan(s.state, 'p1', cards, None), context, condition)
    check(s)


@pytest.mark.parametrize("text", [
    "Whenever a creature you control becomes tapped, if it's the first time counters have been put on that creature this turn, draw a card.",  # (another event)
    "Whenever one or more +1/+1 counters are put on a creature you control, if it's the first time counters have been put on that creature this turn, draw a card.",  # (another kind)
    "Whenever you gain life, if it's the first time that creature has become tapped this turn, draw a card.",
])
def test_first_time_wordings_that_do_not_match_their_event_stay_manual(text):
    from tests.test_rules_scripts import ch as characteristics

    chs = characteristics("Test Enchantment", "Enchantment", text)
    assert coverage.of_characteristics(chs).level != "FULL"


# -- "Whenever a creature you control becomes tapped during your turn, if it's the first time that creature has become tapped this turn, untap it." --------
def test_captain_america_untaps_a_creature_only_the_first_time_it_becomes_tapped_each_turn(cards):
    """603.2, 400.7: Llanowar Elves taps for mana (the first time this turn: Captain America untaps it), taps again (the second: it stays tapped);
    the next turn it is the first again (500.8). Saved between the two taps."""
    s = build(cards, ["Captain America, Living Legend", "Llanowar Elves"], forests=20)
    put(s, "Captain America, Living Legend")
    elves = put(s, "Llanowar Elves")
    to_main1(s, 3)  # (both have been under Alice's control since the turn began)
    act(s, "p1", type="activate_ability", card_id=elves.id, ability=0)
    settle(s)
    assert not tapped(s, elves) and mana_pool(s) == {"G": 1}  # (the first time this turn: untapped)
    s = reloaded(s)
    act(s, "p1", type="activate_ability", card_id=elves.id, ability=0)  # the second time this turn
    settle(s)
    assert tapped(s, elves) and mana_pool(s) == {"G": 2}
    check(s)
    finish_turn(s)  # Alice's turn 3 and Bob's turn 4 are over
    to_main1(s, 5)
    act(s, "p1", type="activate_ability", card_id=elves.id, ability=0)
    settle(s)
    assert not tapped(s, elves)  # (the first time in a new turn)
    check(s)


# -- "Whenever one or more counters are put on a creature you control, if it's the first time counters have been put on that creature this turn, …" ------
def counters(s, c, kind="+1/+1"):
    return s.state.cards[c.id].counters.get(kind, 0)


def test_stalwart_successor_adds_one_counter_the_first_time_counters_are_put_on_a_creature_each_turn(cards):
    """603.2, 122.6: Walking Ballista's own counter is the first put on it this turn (Stalwart Successor adds one more: the counter it puts is the
    second time, so no loop), its next activation is not the first; the next turn the first counter is again rewarded. Saved after each step."""
    s = build(cards, ["Stalwart Successor", "Walking Ballista"], forests=20)
    put(s, "Stalwart Successor")
    ballista = to_hand(s, "Walking Ballista")
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=ballista.id, x_value=1)
    settle(s)
    to_main1(s, 3)  # (what happened as it entered is turn 1's)
    start = counters(s, ballista)
    mana(s, G=8)
    act(s, "p1", type="activate_ability", card_id=ballista.id, ability=1)  # {4}: put a +1/+1 counter on it
    settle(s)
    assert counters(s, ballista) == start + 2  # (its own, and the one Stalwart Successor added)
    s = reloaded(s)
    act(s, "p1", type="activate_ability", card_id=ballista.id, ability=1)
    settle(s)
    assert counters(s, ballista) == start + 3  # (the second time this turn: nothing more)
    check(s)
    finish_turn(s)
    to_main1(s, 5)
    mana(s, G=4)
    act(s, "p1", type="activate_ability", card_id=ballista.id, ability=1)
    settle(s)
    assert counters(s, ballista) == start + 5  # (a new turn: the first time again)
    check(s)


def test_botanical_brawler_counts_the_counters_put_before_it_arrived(cards):
    """603.2, 400.7, the ruling: turn 3 — Ballista A gets a counter, then Botanical Brawler is cast, then A gets another: not the first time (the earlier
    one counts although the Brawler wasn't there): nothing. Ballista B's first counter does: the Brawler grows by one; B's second does not. Saved
    after each step."""
    s = build(cards, ["Botanical Brawler", "Walking Ballista", "Walking Ballista"], forests=20)
    a, b = [c for c in s.state.cards.values() if c.name == "Walking Ballista" and c.owner == "p1"]
    for ballista in (a, b):
        act(s, "p1", type="move", card_ids=[ballista.id], to={"zone": "hand"})
        mana(s, G=2)
        act(s, "p1", type="cast_spell", card_id=ballista.id, x_value=1)
        settle(s)
    to_main1(s, 3)
    mana(s, G=4)
    act(s, "p1", type="activate_ability", card_id=a.id, ability=1)  # A's first counters of the turn (the Brawler isn't here yet)
    settle(s)
    brawler = to_hand(s, "Botanical Brawler")
    mana(s, G=1, W=1)
    act(s, "p1", type="cast_spell", card_id=brawler.id)
    settle(s)
    assert counters(s, brawler) == 2
    s = reloaded(s)
    mana(s, G=4)
    act(s, "p1", type="activate_ability", card_id=a.id, ability=1)  # A again: not the first time this turn
    settle(s)
    assert counters(s, brawler) == 2
    check(s)
    mana(s, G=8)
    act(s, "p1", type="activate_ability", card_id=b.id, ability=1)  # B's first counters of the turn
    settle(s)
    assert counters(s, brawler) == 3
    s = reloaded(s)
    act(s, "p1", type="activate_ability", card_id=b.id, ability=1)  # B again
    settle(s)
    assert counters(s, brawler) == 3
    check(s)


# -- "You may cast this card from your graveyard if a creature not named Ebondeath, Dracolich died this turn." --------------------------------------------
def bolt(s, target, pid="p1"):
    """Lightning Bolt at ``target`` (a card id or a player): a copy of the card, wherever it is (the table may have several), cast from the hand."""
    c = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == pid and not c.zone.endswith(("hand", "stack", "battlefield")))
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=c.id, targets=[target])
    settle(s)


def test_ebondeath_is_cast_from_the_graveyard_after_a_creature_with_another_name_died_this_turn(cards):
    """608.2i, 201.2a, 700.4: a token named Ebondeath, Dracolich dying is not "a creature not named Ebondeath" (the name it had on the battlefield); a
    token named otherwise dying is, though it has long ceased to exist (the ruling); the creature that died on turn 1 doesn't count on turn 3 (500.8).
    Saved after the first death, after the second, and in the next turn."""
    s = build(cards, ["Ebondeath, Dracolich", "Lightning Bolt", "Lightning Bolt"], forests=20)
    ebon = card_named(s, "Ebondeath, Dracolich")
    act(s, "p1", type="move", card_ids=[ebon.id], to={"zone": "graveyard"})
    act(s, "p1", type="create_token", player="p1", token={"name": "Ebondeath, Dracolich", "type_line": "Token Creature — Zombie Dragon", "power": "2",
                                                          "toughness": "2", "text": ""})
    namesake = next(c for c in s.state.cards.values() if c.is_token and c.name == "Ebondeath, Dracolich")
    bolt(s, namesake.id)
    s = reloaded(s)
    mana(s, B=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=ebon.id)
    bear = token(s, "p2", "Bear Token", "2/2")
    bolt(s, bear.id)
    assert bear.id not in s.state.cards
    s = reloaded(s)
    check(s)
    act(s, "p1", type="cast_spell", card_id=ebon.id)  # (the token that died is gone; the fact stays)
    settle(s)
    assert s.state.cards[ebon.id].zone == "p1:battlefield" and s.state.cards[ebon.id].tapped
    check(s)
    # the next turn: the death of turn 1 is history
    act(s, "p1", type="move", card_ids=[ebon.id], to={"zone": "graveyard"})
    finish_turn(s)
    to_main1(s, 3)
    mana(s, B=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=ebon.id)
    check(s)


def attack(s, *pairs):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, s.state.rules.decision.player, type="declare_attackers",
        attackers=[{"card_id": a.id, "target": t} for a, t in pairs])


def dragons(s):
    return [c for c in s.state.cards.values() if c.name == "Dragon" and c.zone == "p1:battlefield"]


# -- "Commander creatures you own have "At the beginning of your end step, if a source you controlled dealt 5 or more damage this turn, create a 4/4 red Dragon …"" ----
def test_dragon_cultist_counts_one_sources_total_damage_even_after_it_left(cards):
    """120.3, 608.2i, the ruling: turn 1 — two Bolts (3 + 3) and a 3/3 attacker (3) hurt Bob for 9, but no ONE source dealt 5: nothing. Turn 3 — a 3/3
    with double strike deals 3 and 3 in two damage steps (6 from one source), then leaves the game before the end step: a Dragon anyway. Turn 5 — no
    damage, none (500.8). Saved after combat damage, and again after the end step."""
    s = build(cards, ["Dragon Cultist", "Lightning Bolt", "Lightning Bolt"], forests=20)
    put(s, "Dragon Cultist")
    put(s, "Krenko, Mob Boss")
    bolt(s, "p2")
    bolt(s, "p2")
    plain = token(s, "p1", "Plain", "3/3", "Haste")
    attack(s, (plain, "p2"))
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 9
    s = reloaded(s)
    finish_turn(s)
    assert dragons(s) == []
    check(s)
    to_main1(s, 3)
    striker = token(s, "p1", "Striker", "3/3", "Haste, double strike")
    attack(s, (striker, "p2"))
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 9 - 6
    s = reloaded(s)
    act(s, "p1", type="move", card_ids=[striker.id], to={"zone": "graveyard"})  # (the source is gone before the end step)
    finish_turn(s)
    assert len(dragons(s)) == 1
    check(s)
    to_main1(s, 5)
    finish_turn(s)
    assert len(dragons(s)) == 1
    check(s)


# -- "{1}, {T}: Choose another target creature. Put a number of +1/+1 counters on it equal to the amount of life you gained this turn or the amount of life you lost this turn, whichever is greater." --
def swords(s, victim, pid="p1"):
    """Swords to Plowshares at ``victim``: its controller gains life equal to its power."""
    c = next(c for c in s.state.cards.values() if c.name == "Swords to Plowshares" and c.owner == pid and not c.zone.endswith(("hand", "stack", "battlefield")))
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, pid, W=1)
    act(s, pid, type="cast_spell", card_id=c.id, targets=[victim.id])
    settle(s)


def test_willowdusk_puts_counters_equal_to_the_greater_of_life_gained_and_life_lost_this_turn(cards):
    """119.3, 608.2h: turn 3 — Alice gained 2 (Swords to Plowshares on her own 2/2) and lost 3 (a Bolt at herself): 3 counters. Turn 5 — she gained 4
    (Swords on a 4/4) and lost 3: 4 more. Neither is the net change. Saved between the life changes and the activation, and after it."""
    s = build(cards, ["Willowdusk, Essence Seer", "Swords to Plowshares", "Swords to Plowshares", "Lightning Bolt", "Lightning Bolt"], forests=20)
    willow = put(s, "Willowdusk, Essence Seer")
    pal = token(s, "p1", "Pal", "1/1")
    to_main1(s, 3)
    swords(s, token(s, "p1", "Small", "2/2"))
    bolt(s, "p1")
    assert life(s) == 40 + 2 - 3
    s = reloaded(s)
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=willow.id, ability=0, targets=[pal.id])
    settle(s)
    assert counters(s, pal) == 3
    check(s)
    to_main1(s, 5)
    swords(s, token(s, "p1", "Large", "4/4"))
    bolt(s, "p1")
    assert life(s) == 40 + 2 - 3 + 4 - 3
    s = reloaded(s)
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=willow.id, ability=0, targets=[pal.id])
    settle(s)
    assert counters(s, pal) == 3 + 4
    check(s)


# -- "Sacrifice Saffi Eriksdotter: When target creature is put into your graveyard this turn, return that card to the battlefield." --------------------
def saffi_table(cards, theirs=()):
    s = build(cards, ["Saffi Eriksdotter", "Grizzly Bears", "Swords to Plowshares", "Lightning Bolt", "Lightning Bolt"], theirs=theirs, forests=20)
    return s, put(s, "Saffi Eriksdotter"), put(s, "Grizzly Bears")


def test_saffi_returns_the_target_when_it_goes_to_your_graveyard_once(cards):
    """603.7, 400.3, 400.7: the Bears die (Bolt) and come back; the card that returned is a new object, so it dying again stays dead (the ruling: the effect
    works only once). Saved with the delayed trigger waiting, and after the return."""
    s, saffi, bears = saffi_table(cards)
    act(s, "p1", type="activate_ability", card_id=saffi.id, ability=0, targets=[bears.id])
    settle(s)
    assert zone(s, "Saffi Eriksdotter") == "p1:graveyard" and len(s.state.rules.delayed) == 1
    s = reloaded(s)
    bolt(s, bears.id)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and not s.state.rules.delayed
    s = reloaded(s)
    bolt(s, bears.id)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    check(s)


def test_saffi_does_not_return_a_creature_that_goes_to_another_players_graveyard(cards):
    """400.3: Bob's Grizzly Bears (Alice targets it) die into Bob's graveyard, not hers: nothing returns it. Saved after."""
    s, saffi, _ = saffi_table(cards, theirs=["Grizzly Bears"])
    theirs = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=saffi.id, ability=0, targets=[theirs.id])
    settle(s)
    bolt(s, theirs.id)
    assert s.state.cards[theirs.id].zone == "p2:graveyard"
    s = reloaded(s)
    check(s)


def test_saffi_does_not_return_a_creature_that_was_exiled_instead(cards):
    """700.4: exile is not "put into a graveyard": the Bears sent away by Swords to Plowshares are not returned (and the watch stays, it was not
    triggered)."""
    s, saffi, bears = saffi_table(cards)
    act(s, "p1", type="activate_ability", card_id=saffi.id, ability=0, targets=[bears.id])
    settle(s)
    swords(s, bears)
    assert s.state.cards[bears.id].zone == "p1:exile" and len(s.state.rules.delayed) == 1
    s = reloaded(s)
    check(s)


def test_saffi_watches_only_this_turn(cards):
    """514.2, 603.7b: "this turn" — the Bears that die in Alice's next turn stay in the graveyard."""
    s, saffi, bears = saffi_table(cards)
    act(s, "p1", type="activate_ability", card_id=saffi.id, ability=0, targets=[bears.id])
    settle(s)
    finish_turn(s)
    to_main1(s, 3)
    assert not s.state.rules.delayed
    bolt(s, bears.id)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    s = reloaded(s)
    check(s)


# -- "Whenever that creature attacks the monarch this turn, it gains double strike and trample until end of turn." (Okoye, Mighty and Adored) ----------------
def test_okoye_grants_double_strike_only_when_the_creature_attacks_the_player_who_is_the_monarch(cards):
    """508.3a, 725.1, 603.7: turn 3 — Bob is the monarch: Okoye (4/4, a +1/+1 counter at the beginning of combat) attacks him and deals 5 + 5. Turn 5 —
    Alice is the monarch: the same attack, now with two counters, deals 6 once. Saved with the attack declared."""
    s = build(cards, ["Okoye, Mighty and Adored"], forests=20)
    okoye = put(s, "Okoye, Mighty and Adored")
    act(s, "p1", type="set_monarch", player="p2")
    to_main1(s, 3)
    attack(s, (okoye, "p2"))
    s = reloaded(s)
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 10
    check(s)
    to_main1(s, 5)
    act(s, "p1", type="set_monarch", player="p1")
    attack(s, (named(s, "Okoye, Mighty and Adored"), "p2"))
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 10 - 6
    s = reloaded(s)
    check(s)


# -- "Whenever another creature you control dies, put a +1/+1 counter on Gimli. When this ability resolves for the third time this turn, Gimli fights up to one target creature …" --
def test_gimli_fights_when_the_counter_ability_resolves_for_the_third_time_this_turn(cards):
    """603.12, 603.7c: Alice's three tokens die to three Bolts: the third time the counter ability resolves, a reflexive ability goes on the stack and
    Gimli fights Bob's Victim (chosen then); a fourth death does not fight again. The next turn the count starts over: two deaths, no fight (500.8).
    Saved after the second resolution (the count is kept) and with the reflexive ability waiting."""
    s = build(cards, ["Gimli, Mournful Avenger", *["Lightning Bolt"] * 5], forests=20)
    gimli = put(s, "Gimli, Mournful Avenger")
    fodder = [token(s, "p1", f"Fodder {i}", "1/1") for i in range(4)]
    victim = token(s, "p2", "Victim", "2/2")
    start = counters(s, gimli)
    bolt(s, fodder[0].id)
    bolt(s, fodder[1].id)
    assert counters(s, gimli) == start + 2 and victim.id in s.state.cards
    s = reloaded(s)
    bolt(s, fodder[2].id)  # the third resolution: the fight is a trigger of its own
    assert counters(s, gimli) == start + 3 and victim.id not in s.state.cards
    check(s)
    bolt(s, fodder[3].id)  # the fourth: counted, but not "the third time"
    assert counters(s, gimli) == start + 4
    finish_turn(s)
    to_main1(s, 3)
    others = [token(s, "p1", f"Late {i}", "1/1") for i in range(2)]
    survivor = token(s, "p2", "Survivor", "2/2")
    bolt(s, others[0].id)
    bolt(s, others[1].id)
    assert counters(s, gimli) == start + 6 and survivor.id in s.state.cards
    s = reloaded(s)
    check(s)
