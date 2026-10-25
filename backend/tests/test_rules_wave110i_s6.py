"""Wave 110I (session 6): real Oracle text; every scenario checks the replay and a save and a load.

* Confession Dial: the legendary creature card gains escape this turn only (702.138a, 611.2a): mana cost plus three other cards exiled.
* Dermoplasm: only a creature card with a morph ability may come from the hand; returns to hand only if one was put (603.4, 702.37b).
* Infinite Authority: destroys the other creature (toughness 3 or less) at end of combat; the counter comes only if that destroy did it (701.8a).
* The Pandorica: the permanent stays phased out while The Pandorica remains tapped, and phases in when it untaps or leaves (611.2b, 610.3).
* Bloodthirsty Adversary: pays {2}{R} N times, N counters, exiles up to N cheap instants/sorceries and may cast any number of the copies free (707.12, 608.2g).
* Grifter's Blade: chosen as it enters (303.4f), attached on entry; only a legal host; none to choose: unattached.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import activate
from tests.wave9c_kit import card_named, pt, to_hand
from tests.wave110a_kit import answer
from tests.wave110c_kit import build, cast, check, make_db, mana, put

EXTRA = [
    real("Grifter's Blade", "{1}{R}", 2, "Artifact — Equipment",
         "Flash\nAs this Equipment enters, choose a creature you control it could be attached to. If you do, it enters attached to that creature.\nEquipped creature gets +1/+1.\nEquip {1}",
         None, "R"),
    real("Confession Dial", "{2}", 2, "Artifact",
         "When this artifact enters, surveil 3.\n{T}: Target legendary creature card in your graveyard gains escape until end of turn. The escape cost is equal to its mana cost plus exile three other cards from your graveyard. (You may cast it from your graveyard for its escape cost this turn.)",
         None, ""),
    real("Probe Legend", "{1}{G}", 2, "Legendary Creature — Elf", "", ("2", "2"), "G"),
    real("Dermoplasm", "{1}{U}{U}", 3, "Creature — Shapeshifter",
         "Flying\nMorph {2}{U}{U} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)\nWhen this creature is turned face up, you may put a creature card with a morph ability from your hand onto the battlefield face up. If you do, return this creature to its owner's hand.",
         ("1", "1"), "U"),
    real("Probe Morpher", "{3}{G}", 4, "Creature — Beast", "Morph {2}{G}", ("3", "3"), "G"),
    real("Infinite Authority", "{2}{W}", 3, "Enchantment — Aura",
         "Enchant creature\nWhenever enchanted creature blocks or becomes blocked by a creature with toughness 3 or less, destroy the other creature at end of combat. At the beginning of the next end step, if that creature was destroyed this way, put a +1/+1 counter on the first creature.",
         None, "W"),
    real("The Pandorica", "{3}", 3, "Artifact",
         "You may choose not to untap The Pandorica during your untap step.\n{1}{W}, {T}: Untap another target nonland permanent, then it phases out. It can't phase in for as long as The Pandorica remains tapped. When The Pandorica becomes untapped or leaves the battlefield, that permanent phases in. Activate only as a sorcery.",
         None, ""),
    real("Naturalize", "{1}{G}", 2, "Instant", "Destroy target artifact or enchantment.", None, "G"),
    real("Bloodthirsty Adversary", "{1}{R}", 2, "Creature — Vampire Knight",
         "Haste\nWhen this creature enters, you may pay {2}{R} any number of times. When you pay this cost one or more times, put that many +1/+1 counters on this creature, then exile up to that many target instant and/or sorcery cards with mana value 3 or less from your graveyard and copy them. You may cast any number of the copies without paying their mana costs.",
         ("2", "2"), "R"),
    real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R"),
    real("Shock", "{R}", 1, "Instant", "Shock deals 2 damage to any target.", None, "R"),
    real("Probe Big Sorcery", "{4}{R}", 5, "Sorcery", "Probe Big Sorcery deals 9 damage to any target.", None, "R"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Shivan Dragon", "{4}{R}{R}", 6, "Creature — Dragon", "", ("5", "5"), "R"),
]
BLADE = "Grifter's Blade"


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_blade_enters_attached_to_the_chosen_creature(cards):
    """303.4f: the chosen creature is the host as it enters; the other one is not."""
    s = build(cards, [BLADE, "Grizzly Bears", "Shivan Dragon"])
    put(s, "Grizzly Bears")
    giant = put(s, "Shivan Dragon")
    mana(s, R=1, C=1)
    cast(s, BLADE)
    answer(s, giant.id)
    blade = card_named(s, BLADE)
    assert s.state.cards[blade.id].attached_to == giant.id
    assert pt(s, "Shivan Dragon") == (6, 6) and pt(s, "Grizzly Bears") == (2, 2)
    check(s)


def test_blade_without_a_creature_enters_unattached(cards):
    s = build(cards, [BLADE])
    mana(s, R=1, C=1)
    cast(s, BLADE)
    answer(s)
    assert s.state.cards[card_named(s, BLADE).id].attached_to is None
    check(s)


@pytest.mark.parametrize("others,ok", [(3, True), (2, False)])
def test_dial_escape_needs_three_other_cards(cards, others, ok):
    s = build(cards, ["Confession Dial", "Probe Legend"])
    from tests.wave110c_kit import to_graveyard

    act(s, "p1", type="move", card_ids=[card_named(s, "Probe Legend").id], to={"player": "p1", "zone": "graveyard"})
    to_graveyard(s, others)
    dial = put(s, "Confession Dial")
    legend = card_named(s, "Probe Legend")
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=legend.id)  # no escape before the Dial
    activate(s, "p1", s.state.cards[dial.id], "escape", targets=[legend.id])
    answer(s)
    if not ok:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=legend.id)
        return
    act(s, "p1", type="cast_spell", card_id=legend.id)
    answer(s)
    assert s.state.cards[legend.id].zone == "p1:battlefield"
    assert len(s.state.zones["p1:exile"]) == 3
    check(s)


def test_dial_escape_ends_with_the_turn(cards):
    from tests.wave110a_kit import next_turn
    from tests.wave110c_kit import to_graveyard

    s = build(cards, ["Confession Dial", "Probe Legend"])
    act(s, "p1", type="move", card_ids=[card_named(s, "Probe Legend").id], to={"player": "p1", "zone": "graveyard"})
    to_graveyard(s, 3)
    dial = put(s, "Confession Dial")
    legend = card_named(s, "Probe Legend")
    activate(s, "p1", s.state.cards[dial.id], "escape", targets=[legend.id])
    answer(s)
    next_turn(s)
    next_turn(s)
    mana(s, G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=legend.id)
    check(s)


@pytest.mark.parametrize("morpher", [True, False])
def test_dermoplasm_puts_only_a_morph_creature_and_then_returns_itself(cards, morpher):
    s = build(cards, ["Dermoplasm", "Probe Morpher", "Grizzly Bears"])
    to_hand(s, "Grizzly Bears")
    if morpher:
        to_hand(s, "Probe Morpher")
    derm = to_hand(s, "Dermoplasm")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=derm.id, face_down=True)
    answer(s)
    mana(s, U=2, C=2)
    act(s, "p1", type="turn_face_up", card_id=derm.id)
    answer(s)
    z = {n: s.state.cards[card_named(s, n).id].zone for n in ("Probe Morpher", "Grizzly Bears")}
    assert z["Grizzly Bears"] == "p1:hand"
    assert z["Probe Morpher"] == ("p1:battlefield" if morpher else "p1:library")
    assert s.state.cards[derm.id].zone == ("p1:hand" if morpher else "p1:battlefield")
    if morpher:
        assert not s.state.cards[card_named(s, "Probe Morpher").id].face_down
    check(s)


@pytest.mark.parametrize("raider,blocker,gone,counters", [
    ("0/3", "1/1", True, 1),   # survives the damage, destroyed at end of combat: the counter
    ("0/4", "1/1", False, 0),  # toughness 4: no trigger
    ("1/3", "3/3", True, 0),   # dies in combat damage first: nothing is destroyed at end of combat, no counter
])
def test_infinite_authority_counter_only_when_its_destroy_did_it(cards, raider, blocker, gone, counters):
    from tests.wave53c_kit import (
        bob_swings,
        combat_step,
        creature,
        on_field,
        sandbox,
        settle,
        to_postcombat,
        until,
    )

    s = sandbox(cards, "Infinite Authority")
    guard = creature(s, "p1", "Guard", blocker)
    aura = on_field(s, "Infinite Authority")
    act(s, "p1", type="attach", card_ids=[aura.id], to=guard.id)
    r = creature(s, "p2", "Raider", raider)
    combat_step(s)
    to_postcombat(s)
    bob_swings(s, [r], [(guard, r)])
    settle(s)
    until(s, lambda s: s.state.turn.phase == "end")
    settle(s)
    assert (r.id not in s.state.cards or s.state.cards[r.id].zone != "p2:battlefield") == gone
    assert s.state.cards[guard.id].counters.get("+1/+1", 0) == counters
    check(s)


def _pandorica(cards):
    s = build(cards, ["The Pandorica", "Grizzly Bears", "Naturalize"])
    pand, bears = put(s, "The Pandorica"), put(s, "Grizzly Bears")
    mana(s, W=1, C=1)
    activate(s, "p1", s.state.cards[pand.id], "phases out", targets=[bears.id])
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:phased"
    return s, pand, bears


def test_pandorica_target_phases_in_when_it_leaves(cards):
    s, pand, bears = _pandorica(cards)
    mana(s, G=1, C=1)
    cast(s, "Naturalize", [pand.id])
    answer(s)
    assert s.state.cards[pand.id].zone == "p1:graveyard" and s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("keep_tapped", [True, False])
def test_pandorica_held_while_tapped_and_released_on_untap(cards, keep_tapped):
    from tests.test_rules_wave34b_activated import to_phase

    s, pand, bears = _pandorica(cards)
    to_phase(s, "untap", turn=3)
    d = s.state.rules.decision
    assert d is not None and d.resume.get("step") == "untap_keep"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[pand.id] if keep_tapped else [])
    if keep_tapped:  # "You may choose not to untap": it stays tapped, so the permanent stays phased out through the untap step
        answer(s)
        to_phase(s, "main1", turn=3)
        assert s.state.cards[pand.id].tapped and s.state.cards[bears.id].zone == "p1:phased"
    else:
        answer(s)
        to_phase(s, "main1", turn=3)
        assert not s.state.cards[pand.id].tapped and s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def _adversary(cards, pool):
    s = build(cards, ["Bloodthirsty Adversary", "Lightning Bolt", "Shock", "Probe Big Sorcery"])
    bolts = [put_gy(s, "Lightning Bolt"), put_gy(s, "Shock")]
    big = put_gy(s, "Probe Big Sorcery")
    mana(s, **pool)
    cast(s, "Bloodthirsty Adversary")
    return s, bolts, big


def put_gy(s, name):
    c = to_hand(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    return c


def test_adversary_pays_twice_and_casts_both_copies_free(cards):
    s, bolts, big = _adversary(cards, {"R": 3, "C": 6})
    answer(s, "x:2", [b.id for b in bolts], "Lightning Bolt", "p2", "Shock", "p2")
    adv = card_named(s, "Bloodthirsty Adversary")
    assert s.state.cards[adv.id].counters.get("+1/+1") == 2 and s.state.players["p2"].life == 40 - 5
    assert all(s.state.cards[b.id].zone == "p1:exile" for b in bolts) and s.state.cards[big.id].zone == "p1:graveyard"
    check(s)


def test_adversary_pays_once_exiles_one_and_may_leave_the_copy_uncast(cards):
    s, bolts, big = _adversary(cards, {"R": 3, "C": 6})
    answer(s, "x:1", [bolts[0].id], [])
    adv = card_named(s, "Bloodthirsty Adversary")
    assert s.state.cards[adv.id].counters.get("+1/+1") == 1 and s.state.players["p2"].life == 40
    assert s.state.cards[bolts[0].id].zone == "p1:exile" and s.state.cards[bolts[1].id].zone == "p1:graveyard"
    check(s)


def test_adversary_only_offers_cheap_instants_and_sorceries(cards):
    s, bolts, big = _adversary(cards, {"R": 3, "C": 6})
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["x:2"])
    ids = [o.id for o in s.state.rules.decision.options]  # the target choice: mana value 5 is not offered
    assert big.id not in ids and set(ids) == {b.id for b in bolts}
