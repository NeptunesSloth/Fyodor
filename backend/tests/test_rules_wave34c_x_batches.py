"""Wave 34C: an X that the objects of a "one or more" trigger, or a count of this turn, define (CR 2026-09-25), real Oracle text
(tests/fixtures/wave34c_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 603.2c, 508.1: "Whenever you attack with one or more Wraiths, exile the top X cards …, where X is their total power" (Witch-king, Sky
  Scourge) and "Whenever one or more artifact creatures you control attack, discover X, where X is the greatest power among them" (Aloy):
  the attackers the trigger counted, read as they last existed if one left before it resolved (608.2h).
* 107.3c, 608.2h: "put X +1/+1 counters …, where X is the number of permanents you've sacrificed this turn. If X is three or more, …"
  (Obsessive Pursuit): one X for the counters and the condition.
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
from tests.test_rules_conditionals import creature, through_combat, until
from tests.test_rules_conditionals import settle as settle_stack
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave34c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w34c", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Witch-king, Sky Scourge", "Aloy, Savior of Meridian", "Obsessive Pursuit"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def attack(s, *attackers):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2"} for a in attackers])


def exiled(s, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones.get(f"{pid}:exile", [])]


def test_witch_king_exiles_as_many_cards_as_the_attacking_wraiths_total_power(cards):
    s = build(cards, ["Witch-king, Sky Scourge"])
    put(s, "Witch-king, Sky Scourge")
    a = creature(s, "p1", "Wraith A", "2/2", "Token Creature — Wraith", "Haste")
    b = creature(s, "p1", "Wraith B", "3/3", "Token Creature — Wraith", "Haste")
    bear = creature(s, "p1", "Bear", "4/4", text="Haste")  # (not a Wraith: its power is not counted)
    library = len(s.state.zones["p1:library"])
    attack(s, a, b, bear)
    settle_stack(s)
    assert len(exiled(s)) == 5 and len(s.state.zones["p1:library"]) == library - 5  # 2 + 3 (603.2c: the Wraiths the trigger counted)
    through_combat(s)
    check(s)


def test_witch_king_reads_a_wraith_that_left_as_it_last_existed(cards):
    s = build(cards, ["Witch-king, Sky Scourge"])
    put(s, "Witch-king, Sky Scourge")
    a = creature(s, "p1", "Wraith A", "2/2", "Token Creature — Wraith", "Haste")
    b = creature(s, "p1", "Wraith B", "3/3", "Token Creature — Wraith", "Haste")
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    attack(s, a, b)
    assert s.state.zones.get("stack")  # (the trigger waits)
    act(s, "p1", type="move", card_ids=[b.id], to={"zone": "graveyard"})  # the 3/3 is gone before it resolves
    settle_stack(s)
    assert len(exiled(s)) == 5  # 608.2h: its power as it last existed on the battlefield
    check(s)


def test_aloy_discovers_the_greatest_power_among_the_attacking_artifact_creatures(cards):
    s = build(cards, ["Aloy, Savior of Meridian", "Solemn Simulacrum"])
    put(s, "Aloy, Savior of Meridian")
    small = creature(s, "p1", "Pawn", "2/2", "Token Artifact Creature — Construct", "Haste")
    big = creature(s, "p1", "Rook", "4/4", "Token Artifact Creature — Construct", "Haste")
    solemn = card_named(s, "Solemn Simulacrum")
    act(s, "p1", type="move", card_ids=[solemn.id], to={"player": "p1", "zone": "library"}, position="top")
    attack(s, small, big)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            pick = ["no"] if (d.resume or {}).get("step") == "suspend_cast" else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[solemn.id].zone == "p1:hand"  # discover 4 (the 4/4): the mana value 4 card is found; discover 2 would have buried it
    check(s)


def test_obsessive_pursuit_gives_lifelink_from_three_sacrifices(cards):
    s = build(cards, ["Obsessive Pursuit"])
    put(s, "Obsessive Pursuit")
    runner = creature(s, "p1", "Runner", "1/1", text="Haste")
    for i in range(3):
        fodder = creature(s, "p1", f"Fodder {i}", "1/1", text="{0}, Sacrifice this creature: You gain 1 life.")
        act(s, "p1", type="activate_ability", card_id=fodder.id, ability=0)
        settle_stack(s)
    attack(s, runner)
    settle_stack(s)
    assert s.state.cards[runner.id].counters == {"+1/+1": 3}  # X = the three permanents sacrificed this turn
    from app.rules.plan import Plan

    assert "lifelink" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[runner.id]).keywords  # X is three or more
    through_combat(s)
    check(s)


def test_hurska_pumps_by_the_life_that_was_gained(cards):
    s = build(cards, ["Hurska Sweet-Tooth"])
    put(s, "Hurska Sweet-Tooth")
    bear = creature(s, "p1", "Bear", "2/2")
    mana(s, G=1)
    healer = creature(s, "p1", "Healer", "1/1", text="{0}: You gain 4 life.")
    act(s, "p1", type="activate_ability", card_id=healer.id, ability=0)
    for _ in range(30):  # (the trigger asks whether to pay {G/W}, then for the target)
        d = s.state.rules.decision
        if d is not None:
            pick = ["yes"] if "yes" in [o.id for o in d.options] else [bear.id] if bear.id in [o.id for o in d.options] else [o.id for o in d.options][:1]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert pt(s, "Bear") == (6, 6)  # X = the 4 life gained (the reflexive ability still has the trigger's event: 603.12)
    check(s)


def test_felisa_makes_a_token_for_each_counter_the_creature_had(cards):
    s = build(cards, ["Felisa, Fang of Silverquill", "Grizzly Bears", "Llanowar Elves"])
    put(s, "Felisa, Fang of Silverquill")
    grown, plain = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    act(s, "p1", type="counter", card_ids=[grown.id], kind="+1/+1", delta=3)
    pinger = creature(s, "p1", "Pinger", "1/1", text="{0}: This creature deals 9 damage to target creature.")
    for victim, tokens in ((plain, 0), (grown, 3)):  # (no counters on it: the trigger doesn't happen)
        before = len(on_battlefield(s, "Inkling"))
        act(s, "p1", type="activate_ability", card_id=pinger.id, ability=0, targets=[victim.id])
        settle_stack(s)
        assert s.state.cards[victim.id].zone == "p1:graveyard"
        assert len(on_battlefield(s, "Inkling")) - before == tokens  # X = the counters it had on it, as it last existed (608.2h)
    check(s)


def on_battlefield(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:battlefield"]


def pt(s, name, pid="p1"):
    from app.rules import sba
    from app.rules.plan import Plan

    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    ch = Plan(s.state, "p1", s.cards, None).ch(c)
    return sba.power(c, ch), sba.toughness(c, ch)


def test_flesh_puts_counters_equal_to_the_power_of_the_card_it_exiled(cards):
    s = build(cards, ["Flesh // Blood", "Grizzly Bears", "Llanowar Elves"], theirs=["Grizzly Bears"])
    act(s, "p2", type="move", card_ids=[card_named(s, "Grizzly Bears", "p2").id], to={"zone": "graveyard"})
    elf = put(s, "Llanowar Elves")
    spell = to_hand(s, "Flesh // Blood")
    mana(s, B=1, G=4)
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p1", type="cast_spell", card_id=spell.id, face=0, targets=[bears.id, elf.id], target_counts=[1, 1])
    settle_stack(s)
    assert s.state.cards[bears.id].zone == "p2:exile"
    assert s.state.cards[elf.id].counters == {"+1/+1": 2}  # X = the power of the card it exiled (a 2/2 Bears): 608.2h
    check(s)


def test_bishop_of_binding_pumps_by_the_power_of_the_creature_it_exiled(cards):
    s = build(cards, ["Bishop of Binding"], theirs=["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    bishop = to_hand(s, "Bishop of Binding")
    mana(s, W=4)
    act(s, "p1", type="cast_spell", card_id=bishop.id, targets=[card_named(s, "Grizzly Bears", "p2").id])
    settle_stack(s)
    assert card_named(s, "Grizzly Bears", "p2").zone == "p2:exile"
    before = pt(s, "Bishop of Binding")
    until(s, lambda s: s.state.turn.number >= 3 and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bishop.id, "target": "p2"}])
    settle_stack(s)
    after = pt(s, "Bishop of Binding")
    assert (after[0] - before[0], after[1] - before[1]) == (2, 2)  # X = the power of the exiled Bears, 2
    check(s)


def test_obsessive_pursuit_gives_no_lifelink_below_three(cards):
    s = build(cards, ["Obsessive Pursuit"])
    put(s, "Obsessive Pursuit")
    runner = creature(s, "p1", "Runner", "1/1", text="Haste")
    fodder = creature(s, "p1", "Fodder", "1/1", text="{0}, Sacrifice this creature: You gain 1 life.")
    act(s, "p1", type="activate_ability", card_id=fodder.id, ability=0)
    settle_stack(s)
    attack(s, runner)
    settle_stack(s)
    from app.rules.plan import Plan

    assert s.state.cards[runner.id].counters == {"+1/+1": 1}
    assert "lifelink" not in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[runner.id]).keywords
    through_combat(s)
    check(s)
