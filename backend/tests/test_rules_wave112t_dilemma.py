"""Wave 112T: facing a dilemma (Star Trek), from the Star Trek release notes (https://magic.wizards.com/en/news/feature/star-trek-release-notes):
the Comprehensive Rules (2026-09-25) don't define it yet. Real Oracle text (Scryfall, 2026-10-30); every scenario checks the replay and a
save and a load.
# Star Trek release notes (2026-11): re-check against the CR when it defines face a dilemma

* A player faces a dilemma "whenever that player chooses one or more modes for a spell or ability": a cast modal spell (601.2b), an activated
  modal ability (602.2b), a modal triggered ability put on the stack (603.3c); once however many modes; not with no mode chosen; not for a
  copy ("you didn't choose a mode for the copy and this doesn't count as facing a dilemma").
* The trigger "will resolve before the spell or ability that caused it to trigger", "even if that spell or ability is countered".
* "for each dilemma you've faced this turn" (Captain Benjamin Sisko) and "if you faced a dilemma this turn" (The Caretaker, checked as the end
  step starts: its ruling) read the turn's log.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, put

EXTRA = [
    real('Elim Garak, Simple Tailor', '{2}{B}', 3, 'Legendary Creature — Cardassian Rogue',
         'Menace\nWhenever you face a dilemma, each opponent loses 2 life and you gain 2 life. (You face a dilemma as you choose one or more modes for a spell or ability.)', ("3", "3"), 'B'),
    real('Melkotian Adjudicator', '{2}{U}', 3, 'Creature — Melkotian Advisor',
         'Flying, vigilance\nWhenever you face a dilemma, put a +1/+1 counter on this creature. (You face a dilemma as you choose one or more modes for a spell or ability.)', ("2", "1"), 'U'),
    real('Obsidian Order Operative', '{3}{B}', 4, 'Creature — Cardassian Officer Spy',
         'Whenever you face a dilemma, each opponent loses 1 life and you gain 1 life. (You face a dilemma as you choose one or more modes for a spell or ability.)', ("2", "5"), 'B'),
    real('Seven of Nine', '{2}{U}{B}', 4, 'Legendary Artifact Creature — Human Scientist',
         'Whenever you face a dilemma, draw a card. (You face a dilemma as you choose one or more modes for a spell or ability.)', ("2", "4"), 'UB'),
    real('Tell Me What You See', '{1}{B}', 2, 'Enchantment',
         "When this enchantment enters, target opponent may have you draw a card. If they don't, they lose 4 life and you surveil 1.\nWhenever you face a dilemma, you may return this enchantment to its owner's hand. (You face a dilemma as you choose one or more modes for a spell or ability.)", None, 'B'),
    real('Gabriel Lorca, Mirror Menace', '{4}{B}', 5, 'Legendary Creature — Human Rogue Officer',
         'Menace\nWhenever you face a dilemma, you may pay {B}. If you do, return this card from your graveyard to your hand. (You face a dilemma as you choose one or more modes for a spell or ability.)', ("5", "4"), 'B'),
    real('Captain Benjamin Sisko', '{1}{W}', 2, 'Legendary Creature — Human Officer',
         "At the beginning of your end step, create a 1/1 red Officer creature token for each dilemma you've faced this turn.\n{2}{W}{U}{B}{R}{G}, {T}: Exile the top five cards of your library. You may cast any number of spells with mana value less than or equal to the number of Officers you control from among those cards without paying their mana costs.", ("2", "2"), 'W'),
    real('The Caretaker', '{5}{U}', 6, 'Legendary Creature — Elemental',
         'Vigilance, ward {2}\nAt the beginning of each end step, if you faced a dilemma this turn, target opponent exiles cards from the top of their library until they exile a nonland card. You may cast that card without paying its mana cost. (You face a dilemma as you choose one or more modes for a spell or ability.)', ("5", "6"), 'U'),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Abzan Charm", "{W}{B}{G}", 3, "Instant",
         "Choose one —\n• Exile target creature with power 3 or greater.\n• You draw two cards and you lose 2 life.\n• Distribute two +1/+1 counters among one or two target creatures.", None, "WBG"),
    real("Cryptic Command", "{1}{U}{U}{U}", 4, "Instant",
         "Choose two —\n• Counter target spell.\n• Return target permanent to its owner's hand.\n• Tap all creatures your opponents control.\n• Draw a card.", None, "U"),
    real("Reverberate", "{R}{R}", 2, "Instant", "Copy target instant or sorcery spell. You may choose new targets for the copy.", None, "R"),
    real("Cankerbloom", "{1}{G}", 2, "Creature — Phyrexian Fungus",
         "{1}, Sacrifice this creature: Choose one —\n• Destroy target artifact.\n• Destroy target enchantment.\n• Proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)", ("3", "2"), "G"),
    real("Sawblade Slinger", "{3}{G}", 4, "Creature — Human Archer",
         "When this creature enters, choose up to one —\n• Destroy target artifact an opponent controls.\n• This creature fights target Zombie an opponent controls.", ("4", "3"), "G"),
    # Jett Reno as the release notes print it: Scryfall's Oracle text of 2026-10-30 says "+1/1 counter" (a typo the card database keeps until release)
    real("Jett Reno, Problem Solver", "{1}{U}", 2, "Legendary Creature — Human Artificer",
         "Whenever Jett Reno becomes tapped, surveil 1. If her power is 4 or greater, instead draw a card.\nWhenever you face a dilemma, put a +1/+1 counter on Jett Reno. (You face a dilemma as you choose one or more modes for a spell or ability.)", ("1", "2"), "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [*NAMES, "Jett Reno, Problem Solver"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            if any(i not in {o.id for o in d.options} for i in ids):
                raise AssertionError(f"{d.prompt}: {[(o.id, o.label) for o in d.options]}")
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_hand(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def zone(s, c):
    return s.state.cards[c.id].zone


def dilemmas(s, pid="p1"):
    return sum(1 for f in s.state.rules.turn_log.facts if f.kind == "dilemma" and f.player == pid)


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


# -- the event --------------------------------------------------------------------------------------------------------------------------
def test_elim_garak_triggers_on_a_modal_spell_and_resolves_first(cards):
    s = build(cards, ["Elim Garak, Simple Tailor", "Abzan Charm"], ["Counterspell"])
    put(s, "Elim Garak, Simple Tailor")
    charm = to_hand(s, "Abzan Charm")
    to_hand(s, "Counterspell", "p2")
    mana(s, W=1, B=1, G=1)
    mana(s, "p2", U=2)  # (Bob could respond: priority stops)
    act(s, "p1", type="cast_spell", card_id=charm.id, modes=[1])  # "You draw two cards and you lose 2 life."
    assert dilemmas(s) == 1
    top = s.state.zones["stack"][-1]
    assert top != charm.id and s.state.rules.stack[top].kind == "trigger"  # the trigger is above the spell: it resolves first
    act(s, s.state.rules.priority, type="pass_priority")
    assert life(s, "p2") == 38 and life(s) == 42 and zone(s, charm) == "stack"
    answer(s)
    assert life(s) == 40 and zone(s, charm) == "p1:graveyard"
    check(s)


def test_two_modes_are_one_dilemma_and_a_countered_spell_still_counts(cards):
    s = build(cards, ["Obsidian Order Operative", "Cryptic Command"], ["Cryptic Command"])
    put(s, "Obsidian Order Operative")
    mine = to_hand(s, "Cryptic Command")
    theirs = to_hand(s, "Cryptic Command", "p2")
    mana(s, U=3, C=1)
    mana(s, "p2", U=3, C=1)
    act(s, "p1", type="cast_spell", card_id=mine.id, modes=[2, 3])  # tap their creatures, draw a card
    assert dilemmas(s) == 1  # "If a player chooses more than one mode …, that player still faced only one dilemma."
    while s.state.rules.priority != "p2":
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=theirs.id, modes=[0, 3], targets=[mine.id])  # counter it, draw
    answer(s)
    assert zone(s, mine) == "p1:graveyard"  # countered
    assert dilemmas(s) == 1 and dilemmas(s, "p2") == 1
    assert life(s, "p2") == 39 and life(s) == 41  # Obsidian Order Operative's trigger resolved anyway
    check(s)


def test_a_copy_of_a_modal_spell_is_no_dilemma(cards):
    s = build(cards, ["Seven of Nine", "Abzan Charm", "Reverberate"])
    put(s, "Seven of Nine")
    charm, reverb = to_hand(s, "Abzan Charm"), to_hand(s, "Reverberate")
    mana(s, W=1, B=1, G=1, R=2)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=charm.id, modes=[1])
    act(s, "p1", type="cast_spell", card_id=reverb.id, targets=[charm.id])  # held priority: Reverberate copies the charm (707.10)
    answer(s)
    assert dilemmas(s) == 1  # the copy's mode was copied, not chosen
    assert hand(s) == before - 2 + 1 + 2 + 2  # one Seven of Nine draw; the charm and its copy draw two each
    check(s)


def test_an_activated_modal_ability_is_a_dilemma(cards):
    s = build(cards, ["Melkotian Adjudicator", "Cankerbloom"])
    adj = put(s, "Melkotian Adjudicator")
    bloom = put(s, "Cankerbloom")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bloom.id, ability=0, modes=[2])  # proliferate
    answer(s)
    assert dilemmas(s) == 1
    assert s.state.cards[adj.id].counters.get("+1/+1") == 2  # the dilemma's counter, then proliferate
    check(s)


@pytest.mark.parametrize("modes", [[], ["0:0"]])
def test_a_modal_trigger_is_a_dilemma_only_with_a_mode_chosen(cards, modes):
    s = build(cards, ["Obsidian Order Operative", "Sawblade Slinger"], ["Sol Ring"])
    put(s, "Obsidian Order Operative")
    put(s, "Sol Ring", "p2")
    slinger = to_hand(s, "Sawblade Slinger")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=slinger.id)
    answer(s, modes)  # "choose up to one —": none, or "Destroy target artifact an opponent controls."
    assert dilemmas(s) == len(modes)
    assert life(s, "p2") == 40 - len(modes)
    assert zone(s, card_named(s, "Sol Ring", "p2")) == ("p2:graveyard" if modes else "p2:battlefield")
    check(s)


# -- the cards --------------------------------------------------------------------------------------------------------------------------
def test_jett_reno_gets_a_counter(cards):
    s = build(cards, ["Jett Reno, Problem Solver", "Abzan Charm"])
    jett = put(s, "Jett Reno, Problem Solver")
    charm = to_hand(s, "Abzan Charm")
    mana(s, W=1, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=charm.id, modes=[1])
    answer(s)
    assert s.state.cards[jett.id].counters.get("+1/+1") == 1
    check(s)


@pytest.mark.parametrize("pay", [False, True])
def test_gabriel_lorca_returns_from_the_graveyard(cards, pay):
    s = build(cards, ["Gabriel Lorca, Mirror Menace", "Abzan Charm"])
    lorca = card_named(s, "Gabriel Lorca, Mirror Menace")
    act(s, "p1", type="move", card_ids=[lorca.id], to={"player": "p1", "zone": "graveyard"})
    charm = to_hand(s, "Abzan Charm")
    mana(s, W=1, B=2 if pay else 1, G=1)
    act(s, "p1", type="cast_spell", card_id=charm.id, modes=[1])
    answer(s, "pay" if pay else "decline")
    assert zone(s, lorca) == ("p1:hand" if pay else "p1:graveyard")
    check(s)


@pytest.mark.parametrize("draw", [True, False])
def test_tell_me_what_you_see_enters_and_returns_on_a_dilemma(cards, draw):
    s = build(cards, ["Tell Me What You See", "Abzan Charm"])
    tell = to_hand(s, "Tell Me What You See")
    mana(s, B=1, C=1)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=tell.id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.player == "p2":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p2"  # the target opponent decides as it resolves (608.2d)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay" if draw else "decline"])
    answer(s)
    if draw:
        assert hand(s) == before and life(s, "p2") == 40  # (Tell Me left the hand, one card drawn)
    else:
        assert hand(s) == before - 1 and life(s, "p2") == 36
    charm = to_hand(s, "Abzan Charm")
    mana(s, W=1, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=charm.id, modes=[1])
    answer(s, "yes")
    assert zone(s, tell) == "p1:hand"
    check(s)


def test_captain_sisko_makes_an_officer_for_each_dilemma(cards):
    s = build(cards, ["Captain Benjamin Sisko", "Abzan Charm", "Cryptic Command"])
    put(s, "Captain Benjamin Sisko")
    charm, cryptic = to_hand(s, "Abzan Charm"), to_hand(s, "Cryptic Command")
    mana(s, W=1, B=1, G=1, U=3, C=1)
    act(s, "p1", type="cast_spell", card_id=charm.id, modes=[1])
    answer(s)
    act(s, "p1", type="cast_spell", card_id=cryptic.id, modes=[2, 3])
    answer(s)
    assert dilemmas(s) == 2
    until(s, lambda s: s.state.turn.active_player == "p2")  # (through Alice's end step)
    assert sum(1 for c in s.state.cards.values() if c.name == "Officer" and c.zone == "p1:battlefield") == 2
    check(s)


@pytest.mark.parametrize("faced", [False, True])
def test_the_caretaker_needs_a_dilemma_this_turn(cards, faced):
    s = build(cards, ["The Caretaker", "Abzan Charm"], ["Lightning Bolt"])
    put(s, "The Caretaker")
    bolt = card_named(s, "Lightning Bolt", "p2")
    lib = s.state.zones["p2:library"]
    lib.remove(bolt.id)
    lib.insert(0, bolt.id)  # Bob's top card: Lightning Bolt (the islands below are lands)
    if faced:
        charm = to_hand(s, "Abzan Charm")
        mana(s, W=1, B=1, G=1)
        act(s, "p1", type="cast_spell", card_id=charm.id, modes=[1])
        answer(s)
    until(s, lambda s: s.state.turn.active_player == "p2" or s.state.rules.decision is not None)
    if not faced:  # the ability didn't trigger at all (its ruling): nothing exiled, Bob drew his Lightning Bolt in his own turn
        assert s.state.turn.active_player == "p2" and zone(s, bolt) in ("p2:library", "p2:hand") and life(s, "p2") == 40
    else:
        assert s.state.turn.phase == "end" and [o.id for o in s.state.rules.decision.options] == ["p2"]
        answer(s, "p2", bolt.id, "p2")
        assert zone(s, bolt) == "p2:graveyard" and life(s, "p2") == 37  # cast without paying its mana cost
    check(s)
