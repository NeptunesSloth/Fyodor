"""Wave 31D: copies of spells and abilities on the stack (CR 707.10), real Oracle text (tests/fixtures/wave31d_cards.json, from data/cards.sqlite).

Researched against CR 2026-09-25: to copy a spell or ability is to put a copy of it onto the stack, not cast, not activated (707.10); the copy keeps
every decision made for the original (targets, modes, X) and its controller may choose new targets, leaving any unchanged even if illegal (707.10c,
115.7); a copy ceases to exist off the stack (707.10a); a triggered ability's count is read as it resolves (608.2h, Storm cycle ruling).

* "When you cast this spell, copy it [for each time you've cast your commander from the command zone this game / for each other instant and sorcery
  spell you've cast this turn / if you gained life this turn]" (Empyrial Storm, Show of Confidence, Lumaret's Favor, Mentor's Guidance, Fury Storm,
  Skull Storm: a trigger of the spell itself, 601.2i, on an instant or sorcery).
* "Whenever you cast an instant or sorcery spell, copy it for each other instant and sorcery spell you've cast before it this turn" (Thousand-Year Storm).
* "flip a coin. If you lose the flip, return that spell to its owner's hand. If you win the flip, copy that spell, and you may choose new targets for
  the copy" (Krark, the Thumbless: the spell leaves the stack without being countered).
* "{X}{X}, {T}: Copy target activated or triggered ability you control X times. … This ability can't be copied and X can't be 0." (Gogo).
* "Copy target instant or sorcery spell, then return it to its owner's hand." (Narset's Reversal); "… that targets only a single creature you control,
  copy that spell" (Leyline of Resonance, 115.9c).

Every scenario checks that replaying the recorded history reproduces the table and that a save and a load keep it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, sba
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_copy import characteristics, copies
from tests.test_rules_wave30o_layers import attack, to_phase
from tests.wave9c_kit import build, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave31d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w31d", number=f"S{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, pick=None, limit=120):
    """Resolve everything. A copy question is answered "same" / "keep" (the targets stay) unless ``pick`` names an option; any other choice with its first."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = next((p for p in (pick or ()) if p in ids), None) or next((p for p in ("same", "keep", "yes") if p in ids), None)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[want] if want else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def hold(s):
    """Both players stop at every object on the stack, and Alice keeps priority after casting (so spells pile up)."""
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="set_prefs", hold_priority=True)


def hand(s, name, n=1, pid="p1"):
    found = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(":library")][:n]
    for c in found:
        act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return found


def on_table(s, name, n=2, pid="p1"):
    """``n`` different cards of this name onto the battlefield."""
    found = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith(":library")][:n]
    for c in found:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return found


def stack_names(s):
    return [s.state.cards[c].name for c in s.state.zones.get("stack", [])]


def resolve_one(s):
    """Both players pass once: the top object resolves (or a question opens)."""
    if not s.state.zones.get("stack"):
        return
    top = s.state.zones["stack"][-1]
    for _ in range(4):
        if s.state.rules.decision is not None or top not in s.state.zones.get("stack", []):
            return
        act(s, s.state.rules.priority, type="pass_priority")


# -- Thousand-Year Storm: a copy for each instant and sorcery spell cast BEFORE the one that triggered it ------------------------------
def test_thousand_year_storm_counts_only_the_spells_cast_before_the_one_that_triggered(cards):
    s = build(cards, ["Thousand-Year Storm", "Lightning Bolt", "Lightning Bolt", "Lightning Bolt"])
    put(s, "Thousand-Year Storm")
    bolts = hand(s, "Lightning Bolt", 3)
    hold(s)
    mana(s, R=3)
    for b in bolts:  # the three Bolts and their three triggers pile up on the stack, none has resolved
        act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
    assert stack_names(s).count("Lightning Bolt") == 3 and len(s.state.zones["stack"]) == 6
    resolve_one(s)  # the third trigger: 2 spells were cast before the third Bolt — 2 copies (707.10, 608.2h)
    assert s.state.rules.decision is not None and "2 copies of Lightning Bolt" in s.state.rules.decision.prompt
    settle(s, pick=("same",))
    check(s)
    # the second trigger copied once (one Bolt before it), the first none (spells cast after it don't count): 3 + 3 Bolts of 3 damage
    assert life(s, "p2") == 40 - 18


def test_a_copy_may_choose_a_new_target_and_a_copy_whose_target_became_illegal_does_nothing(cards):
    s = build(cards, ["Thousand-Year Storm", "Lightning Bolt", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Thousand-Year Storm")
    bears = put(s, "Grizzly Bears", "p2")
    first, second = hand(s, "Lightning Bolt", 2)
    hold(s)
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"])
    settle(s)  # the first Bolt: no spell before it, no copy
    assert life(s, "p2") == 37
    act(s, "p1", type="cast_spell", card_id=second.id, targets=[bears.id])
    resolve_one(s)  # the trigger: one copy, which may choose a new target (707.10c)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith("Copy of Lightning Bolt")
    assert {"keep", "p1", "p2"} <= {o.id for o in d.options} and bears.id not in {o.id for o in d.options}  # ("keep" is the Bears)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])  # … Bob instead of the Bears
    [copy] = copies(s)
    assert [t.id for t in s.state.rules.stack[copy].targets] == ["p2"]
    check(s)
    settle(s)
    assert life(s, "p2") == 37 - 3 and s.state.cards[bears.id].zone == "p2:graveyard"  # the copy hit Bob, the original the Bears
    check(s)


def test_a_copy_keeping_a_target_that_became_illegal_fizzles(cards):
    s = build(cards, ["Thousand-Year Storm", "Lightning Bolt", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Thousand-Year Storm")
    bears = put(s, "Grizzly Bears", "p2")
    first, second = hand(s, "Lightning Bolt", 2)
    hold(s)
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=first.id, targets=["p2"])
    settle(s)
    act(s, "p1", type="cast_spell", card_id=second.id, targets=[bears.id])
    resolve_one(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["keep"])  # the copy keeps the Bears (707.10c)
    [copy] = copies(s)
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "graveyard"})  # … which is gone by the time it resolves
    settle(s)
    assert copy not in s.state.cards and life(s, "p2") == 37  # 608.2b: both Bolts fizzled, the copy ceased to exist (707.10a)
    check(s)


# -- the Storm cycle: "When you cast this spell, copy it for each time you've cast your commander from the command zone" ----------------------
def cast_commander(s):
    krenko = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    mana(s, R=2, C=6)
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    settle(s)
    return krenko


def test_empyrial_storm_copies_for_each_commander_cast_and_a_copy_is_not_cast(cards):
    s = build(cards, ["Empyrial Storm"])
    krenko = cast_commander(s)
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "command"})
    cast_commander(s)
    assert s.state.players["p1"].commander_casts[krenko.commander_key] == 2
    storm = to_hand(s, "Empyrial Storm")
    mana(s, W=2, C=4)
    act(s, "p1", type="cast_spell", card_id=storm.id)
    settle(s)
    angels = [c for c in s.state.cards.values() if c.is_token and c.name == "Angel" and c.zone == "p1:battlefield"]
    assert len(angels) == 3  # the spell and one copy for each of the two casts (the copies aren't cast: no further trigger)
    assert s.state.players["p1"].commander_casts[krenko.commander_key] == 2
    check(s)


def test_skull_storm_without_a_commander_cast_makes_no_copy(cards):
    s = build(cards, ["Skull Storm"], ["Grizzly Bears", "Grizzly Bears"])
    for c in hand(s, "Grizzly Bears", 2, "p2"):
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    storm = to_hand(s, "Skull Storm")
    mana(s, B=2, C=7)
    act(s, "p1", type="cast_spell", card_id=storm.id)
    settle(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p2:battlefield") == 1  # one sacrifice, no copy
    check(s)


# -- Show of Confidence / Lumaret's Favor / Mentor's Guidance: the count, and an "if" ------------------------------------------------------------
def test_show_of_confidence_copies_once_for_the_one_other_instant_and_may_choose_a_new_target(cards):
    s = build(cards, ["Show of Confidence", "Lightning Bolt", "Grizzly Bears", "Grizzly Bears"])
    a, b = on_table(s, "Grizzly Bears")
    bolt, show = to_hand(s, "Lightning Bolt"), to_hand(s, "Show of Confidence")
    hold(s)
    mana(s, R=1, W=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    act(s, "p1", type="cast_spell", card_id=show.id, targets=[a.id])
    resolve_one(s)  # the copy trigger: one other instant or sorcery was cast this turn — one copy (the Show itself isn't "other")
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith("Copy of Show of Confidence")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[b.id])
    settle(s)
    assert s.state.cards[a.id].counters.get("+1/+1") == 1 and s.state.cards[b.id].counters.get("+1/+1") == 1
    check(s)


def test_show_of_confidence_cast_first_makes_no_copy(cards):
    s = build(cards, ["Show of Confidence", "Grizzly Bears"])
    a = put(s, "Grizzly Bears")
    show = to_hand(s, "Show of Confidence")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=show.id, targets=[a.id])
    settle(s)
    assert s.state.cards[a.id].counters.get("+1/+1") == 1
    check(s)


@pytest.mark.parametrize("gained", [True, False])
def test_lumarets_favor_copies_only_if_you_gained_life_this_turn(cards, gained):
    s = build(cards, ["Lumaret's Favor", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Soul Warden"])
    a, b = on_table(s, "Grizzly Bears")
    if gained:  # Soul Warden: a creature enters, you gain 1 life (a third Bears, cast)
        put(s, "Soul Warden")
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:library")],
            to={"zone": "hand"})
        mana(s, G=1, C=1)
        act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:hand"))
        settle(s)
    assert life(s, "p1") == (41 if gained else 40)
    favor = to_hand(s, "Lumaret's Favor")
    hold(s)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=favor.id, targets=[a.id])
    resolve_one(s)
    d = s.state.rules.decision
    if gained:  # 707.10c: the copy may choose a new target
        assert d is not None and d.prompt.startswith("Copy of Lumaret's Favor")
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[b.id])
    else:
        assert d is None
    for _ in range(3):  # (the spells resolve one after the other; stop with the +2/+4 on the table)
        if s.state.zones.get("stack"):
            resolve_one(s)
    assert (power(s, a), power(s, b)) == ((4, 4) if gained else (4, 2))  # +2/+4 on the target, and on the copy's new one
    check(s)


def power(s, c):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return sba.power(s.state.cards[c.id], ch)


# -- Krark, the Thumbless -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("heads", [True, False])
def test_krark_copies_a_won_flip_and_returns_a_lost_one_to_hand(cards, monkeypatch, heads):
    monkeypatch.setattr("app.game.resolve._rng_int", lambda rng, lo, hi: 1 if heads else 0)
    s = build(cards, ["Krark, the Thumbless", "Lightning Bolt"])
    put(s, "Krark, the Thumbless")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    if heads:  # a copy (707.10) and the original: 3 damage each
        assert life(s, "p2") == 34 and s.state.cards[bolt.id].zone == "p1:graveyard"
    else:  # the spell left the stack without being countered (and never resolved)
        assert life(s, "p2") == 40 and s.state.cards[bolt.id].zone == "p1:hand"
    check(s)


# -- Gogo, Master of Mimicry --------------------------------------------------------------------------------------------------------------------
def gogo_ready(cards):
    s = build(cards, ["Gogo, Master of Mimicry", "Wall of Omens"])
    gogo = put(s, "Gogo, Master of Mimicry")
    s.state.rules.controlled_since[gogo.id].turn = 0  # (long on the table: {T} abilities are allowed)
    return s, gogo


def test_gogo_copies_a_triggered_ability_x_times(cards):
    s, gogo = gogo_ready(cards)
    hold(s)
    wall = to_hand(s, "Wall of Omens")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=wall.id)
    resolve_one(s)  # the Wall enters: its "draw a card" trigger goes on the stack
    for _ in range(3):
        if any(e.kind == "trigger" for e in s.state.rules.stack.values()):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    trigger = next(c for c, e in s.state.rules.stack.items() if e.kind == "trigger")
    hand_before = len(s.state.zones["p1:hand"])
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=gogo.id, ability=0, x_value=2, targets=[trigger])
    resolve_one(s)  # {X}{X} with X = 2: two copies, which may choose new targets (none to choose: no targets)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand_before + 3  # the original and two copies drew a card each (707.10b)
    check(s)


def test_gogos_x_cant_be_0(cards):
    s, gogo = gogo_ready(cards)
    hold(s)
    wall = to_hand(s, "Wall of Omens")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=wall.id)
    resolve_one(s)
    for _ in range(3):
        if any(e.kind == "trigger" for e in s.state.rules.stack.values()):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    trigger = next(c for c, e in s.state.rules.stack.items() if e.kind == "trigger")
    with pytest.raises(ActionError, match="X can't be 0"):
        act(s, "p1", type="activate_ability", card_id=gogo.id, ability=0, x_value=0, targets=[trigger])
    check(s)


def test_lair_of_the_hydras_x_cant_be_0(cards):
    s = build(cards, ["Lair of the Hydra"])
    lair = put(s, "Lair of the Hydra")
    index = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[lair.id]).abilities if "{X}{G}" in a.text)
    mana(s, G=3)
    with pytest.raises(ActionError, match="X can't be 0"):
        act(s, "p1", type="activate_ability", card_id=lair.id, ability=index, x_value=0)
    act(s, "p1", type="activate_ability", card_id=lair.id, ability=index, x_value=2)
    settle(s)
    assert power(s, lair) == 2  # an X/X Hydra creature until end of turn
    check(s)


def test_marath_cant_choose_x_0_and_with_x_1_deals_that_much(cards):
    s = build(cards, ["Marath, Will of the Wild"])
    marath = put(s, "Marath, Will of the Wild")
    act(s, "p1", type="counter", card_ids=[marath.id], kind="+1/+1", delta=3)
    index = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[marath.id]).abilities if "Remove X" in a.text)
    with pytest.raises(ActionError, match="X can't be 0"):
        act(s, "p1", type="activate_ability", card_id=marath.id, ability=index, x_value=0, modes=[1], targets=["p2"])
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=marath.id, ability=index, x_value=2, modes=[1], targets=["p2"])
    settle(s)
    assert life(s, "p2") == 38 and s.state.cards[marath.id].counters.get("+1/+1") == 1  # X damage, X counters removed as a cost
    check(s)


def test_odds_ends_copies_the_spell_on_tails_and_counters_it_on_heads(cards, monkeypatch):
    for heads in (True, False):
        monkeypatch.setattr("app.game.resolve._rng_int", lambda rng, lo, hi, heads=heads: 1 if heads else 0)
        s = build(cards, ["Odds // Ends", "Lightning Bolt"])
        bolt, odds = to_hand(s, "Lightning Bolt"), to_hand(s, "Odds // Ends")
        hold(s)
        mana(s, R=2, U=1)
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
        act(s, "p1", type="cast_spell", card_id=odds.id, face=0, targets=[bolt.id])
        settle(s)
        # heads (a win, 705.2): the Bolt is countered; tails: it's copied (the copy may choose a new target), so Bob takes 3 twice
        assert life(s, "p2") == (40 if heads else 34)
        check(s)


# -- Narset's Reversal ------------------------------------------------------------------------------------------------------------------------
def test_narsets_reversal_copies_the_spell_and_returns_the_original_to_its_owners_hand(cards):
    s = build(cards, ["Narset's Reversal", "Lightning Bolt", "Grizzly Bears"])
    ogre = put(s, "Grizzly Bears")
    bolt, reversal = to_hand(s, "Lightning Bolt"), to_hand(s, "Narset's Reversal")
    hold(s)
    mana(s, R=1, U=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=reversal.id, targets=[bolt.id])
    resolve_one(s)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith("Copy of Lightning Bolt")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ogre.id])
    settle(s)
    assert s.state.cards[bolt.id].zone == "p1:hand"  # the original never resolved: it is back in its owner's hand
    assert life(s, "p2") == 40 and ogre.id in s.state.cards and s.state.cards[ogre.id].zone.endswith("graveyard")  # the copy hit the Bears
    check(s)


# -- Leyline of Resonance: "that targets only a single creature you control" (115.9c) ------------------------------------------------------------
def test_leyline_of_resonance_copies_a_spell_that_targets_only_one_creature_you_control(cards):
    s = build(cards, ["Leyline of Resonance", "Giant Growth", "Grizzly Bears", "Grizzly Bears"])
    put(s, "Leyline of Resonance")
    a, b = on_table(s, "Grizzly Bears")
    grow = to_hand(s, "Giant Growth")
    hold(s)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=grow.id, targets=[a.id])
    resolve_one(s)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith("Copy of Giant Growth")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[b.id])
    settle(s)
    assert (power(s, a), power(s, b)) == (5, 5)  # +3/+3 on the Bears it targeted and on the other one, for the copy
    check(s)


@pytest.mark.parametrize("target", ["p2", "their creature"])
def test_leyline_of_resonance_ignores_spells_that_target_a_player_or_an_opponents_creature(cards, target):
    s = build(cards, ["Leyline of Resonance", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Leyline of Resonance")
    theirs = put(s, "Grizzly Bears", "p2")
    bolt = to_hand(s, "Lightning Bolt")
    hold(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2" if target == "p2" else theirs.id])
    resolve_one(s)
    assert s.state.rules.decision is None and not copies(s)  # 115.9c: not "a single creature you control"
    settle(s)
    check(s)


# -- Increasing Vengeance: "If this spell was cast from a graveyard, copy that spell twice instead" ------------------------------------------------
def test_increasing_vengeance_copies_once_from_hand_and_twice_from_the_graveyard(cards):
    s = build(cards, ["Increasing Vengeance", "Lightning Bolt", "Lightning Bolt"])
    bolt, bolt2 = hand(s, "Lightning Bolt", 2)
    vengeance = to_hand(s, "Increasing Vengeance")
    hold(s)
    mana(s, R=4)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=vengeance.id, targets=[bolt.id])
    resolve_one(s)  # from the hand: one copy, which may choose a new target (707.10c)
    d = s.state.rules.decision
    assert d is not None and d.prompt.startswith("Copy of Lightning Bolt") and "copies" not in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["keep"])
    settle(s)
    assert life(s, "p2") == 40 - 6 and s.state.cards[vengeance.id].zone == "p1:graveyard"
    check(s)
    act(s, "p1", type="cast_spell", card_id=bolt2.id, targets=["p2"])  # the Bolt on the stack again, and the flashback cast ({3}{R}{R})
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=vengeance.id, targets=[bolt2.id])
    resolve_one(s)
    d = s.state.rules.decision
    assert d is not None and "2 copies of Lightning Bolt" in d.prompt  # from a graveyard: twice instead (not three copies)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["same"])
    settle(s)
    assert life(s, "p2") == 40 - 6 - 9
    check(s)


# -- Mentor's Guidance / Howl of the Horde ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("wizard", [True, False])
def test_mentors_guidance_copies_only_if_you_control_a_cleric_or_the_like(cards, wizard):
    s = build(cards, ["Mentor's Guidance", "Soul Warden"])
    if wizard:
        put(s, "Soul Warden")  # a Human Cleric
    guidance = to_hand(s, "Mentor's Guidance")
    before = len(s.state.zones["p1:hand"])
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=guidance.id)
    settle(s)
    assert len(s.state.zones["p1:hand"]) - before + 1 == (2 if wizard else 1)  # the spell left the hand: one card drawn, two with the copy
    check(s)


@pytest.mark.parametrize("attacked", [True, False])
def test_howl_of_the_horde_raid_copies_the_next_spell_an_additional_time(cards, attacked):
    s = build(cards, ["Howl of the Horde", "Lightning Bolt", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    if attacked:
        attack(s, bears)
        to_phase(s, "main2")
    howl, bolt = to_hand(s, "Howl of the Horde"), to_hand(s, "Lightning Bolt")
    mana(s, R=4)
    act(s, "p1", type="cast_spell", card_id=howl.id)
    settle(s)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 40 - (2 if attacked else 0) - (9 if attacked else 6)  # the Bolt, a copy, and with raid one more
    check(s)


# -- Fire Lord Azula: "Whenever you cast a spell while ~ is attacking, copy that spell" ----------------------------------------------------------
@pytest.mark.parametrize("attacking", [True, False])
def test_fire_lord_azula_copies_a_spell_cast_while_she_is_attacking(cards, attacking):
    s = build(cards, ["Fire Lord Azula", "Lightning Bolt"])
    azula = put(s, "Fire Lord Azula")
    bolt = to_hand(s, "Lightning Bolt")
    if attacking:
        hold(s)  # (stop in the declare attackers step, with her attack trigger on the stack)
        attack(s, azula)
        assert s.state.turn.phase == "declare_attackers"
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    assert life(s, "p2") == (34 if attacking else 37)  # the copy (not cast: no further trigger) dealt 3 too
    check(s)


# -- what stays manual ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("type_line", "text"), [
    # X is the spell's, announced as it was cast: read in a cast trigger? Not yet (Photon Blast Barrage, Hydroid Krasis' half X)
    ("Instant", "When you cast this spell, copy it X times. You may choose new targets for the copies."),
    # a count of kinds of counters among permanents (Storm of Forms): no such amount
    ("Instant", "When you cast this spell, copy it for each kind of counter among permanents you control. You may choose new targets for the copies."),
    # two conditional copies, then one sentence about all the copies (Banish into Fable)
    ("Instant", "When you cast this spell from your hand, copy it if you control an artifact, then copy it if you control an enchantment. "
                "You may choose new targets for the copies."),
    # "before it" names the spell a cast trigger is about: nothing else has one
    ("Creature — Human", "Whenever a creature enters, draw a card for each other instant and sorcery spell you've cast before it this turn."),
    # "it" in a spell outside a cast trigger names nothing (no earlier target)
    ("Instant", "Draw a card. Copy that spell."),
    # a delayed trigger that must flip, then judge the flip, then give an opponent (their choice) the creature (Fickle Efreet)
    ("Creature — Efreet", "Whenever this creature attacks or blocks, flip a coin at end of combat. If you lose the flip, an opponent gains control of "
                          "this creature."),
    # two objects returned to different owners (Contempt); (Basalt Golem's delayed sacrifice answered by "If the player does": read since wave 53C,
    # tests/test_rules_wave53c_block_events.py)
    ("Enchantment — Aura", "Enchant creature\nWhen enchanted creature attacks, return it and this Aura to their owners' hands at end of combat."),
    # "attacked or blocked this combat" is no condition yet (Daredevil Dragster, the Clockwork creatures)
    ("Artifact — Vehicle", "At end of combat, if this Vehicle attacked or blocked this combat, put a velocity counter on it."),
])
def test_unread_wordings_stay_manual(type_line, text):
    ch_ = characteristics("Probe", type_line, text, spell="Instant" in type_line)
    assert coverage.of_characteristics(ch_).level != "FULL"


@pytest.mark.parametrize("name", ["Fire Lord Azula", "Gogo, Master of Mimicry", "Krark, the Thumbless", "Thousand-Year Storm", "Narset's Reversal",
                                  "Leyline of Resonance", "Increasing Vengeance", "Show of Confidence", "Lumaret's Favor", "Mentor's Guidance",
                                  "Empyrial Storm", "Skull Storm", "Howl of the Horde", "Odds // Ends", "Marath, Will of the Wild",
                                  "Lair of the Hydra"])
def test_spell_copy_cards_are_fully_automated(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name
