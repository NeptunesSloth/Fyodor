"""Review 28C (CR 2026-09-25): spell grants and abilities activated from the hand. Real Oracle text; replay and save/load checked.

* 702.49b / 602.2a / 701.20a: ninjutsu's card is revealed once, as the ability is announced, and stays revealed while the ability is on
  the stack (it used to be revealed, hidden and revealed again).
* 611.2f / 601.2a: "the next spell you cast this turn" applies to the next spell put on the stack; a cast cancelled before it is put
  there (nothing paid) leaves the grant waiting.
* 702.40a-b: two "next instant or sorcery spell has storm" effects give that spell two storm triggers, each copying it for every
  other spell cast before it this turn; 707.10: the copies are spells its controller controls, so "Instant and sorcery spells you
  control have lifelink" reaches their damage too (702.15b).
"""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of, until
from tests.test_rules_wave5b_stack_interaction import roundtrip
from tests.test_rules_wave6e_statics import attack_with
from tests.test_rules_wave28c_hand_abilities import EXTRA as HAND_EXTRA
from tests.test_rules_wave28c_hand_abilities import stack_ability
from tests.test_rules_wave28c_spell_grants import EXTRA as GRANT_EXTRA
from tests.test_rules_wave28c_spell_grants import build, field, run, to_hand
from tests.wave9c_kit import build as kit_build
from tests.wave9c_kit import check, mana


@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *GRANT_EXTRA, *HAND_EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def answer_all(s):
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            return
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices] if d.min_choices else [])


def test_ninjutsu_reveals_its_card_once(cards):
    s = kit_build(cards, ["Ninja of the Deep Hours", "Tarmogoyf"])
    ninja = to_hand(s, "Ninja of the Deep Hours")
    to_hand(s, "Tarmogoyf")
    rat = token_of(s, "p1", "Rat", "Token Creature — Rat", "1/1")
    token_of(s, "p2", "Wall", "Token Creature — Wall", "0/4")
    act(s, "p1", type="set_prefs", stops_my_turn=["main1", "declare_blockers", "main2"], hold_priority=True)
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")
    attack_with(s, rat)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    mana(s, U=1, C=1)
    act(s, "p2", type="declare_blockers", blocks=[])
    seen = len(s.state.log)
    act(s, "p1", type="activate_ability", card_id=ninja.id, ability=0)
    d = s.state.rules.decision
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[rat.id])
    words = ["".join(p.t or "" for p in e.parts) for e in s.state.log[seen:]]
    assert sum(" revealed " in w for w in words) == 1 and not any("stopped revealing" in w for w in words), words
    assert s.state.cards[ninja.id].revealed_to == ["*"] and stack_ability(s)["source_name"] == "Ninja of the Deep Hours"
    check(s)


def test_a_cancelled_cast_keeps_the_next_spell_grant(cards):
    s = build(cards, p1=("Wand of the Worldsoul", "Centaur Courser"))
    wand = field(s, "Wand of the Worldsoul")
    elves = [token_of(s, "p1", f"Elf {i}", "Token Creature — Elf", "1/1") for i in range(2)]
    courser = to_hand(s, "Centaur Courser")
    field(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=wand.id, ability=2)
    run(s)
    act(s, "p1", type="set_prefs", payment="self")  # (asks to tap: the cast waits, nothing paid yet)
    act(s, "p1", type="cast_spell", card_id=courser.id)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["cancel"])
    assert s.state.cards[courser.id].zone == "p1:hand" and [g.keyword for g in s.state.rules.next_spell_grants] == ["convoke"]
    roundtrip(s)
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=courser.id, contributions=[{"card": e.id, "kind": "convoke"} for e in elves])
    assert s.state.rules.next_spell_grants == [] and all(s.state.cards[e.id].tapped for e in elves)
    run(s)
    assert s.state.cards[courser.id].zone == "p1:battlefield"
    roundtrip(s)


def test_two_storm_grants_and_lifelink_on_the_copies(cards):
    s = build(cards, p1=("Crackling Spellslinger", "Crackling Spellslinger", "Radiant Scrollwielder", "Lightning Bolt"))
    field(s, "Radiant Scrollwielder")
    for c in [c for c in s.state.cards.values() if c.name == "Crackling Spellslinger"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
        mana(s, R=2, C=3)
        act(s, "p1", type="cast_spell", card_id=c.id)
        run(s)
    assert [g.keyword for g in s.state.rules.next_spell_grants] == ["storm", "storm"]
    life = s.state.players["p1"].life
    b = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
    pending = [t for t in s.state.rules.pending_triggers if any(x.get("do") == "storm" for x in t.ability["effects"])]
    assert [x["n"] for t in pending for x in t.ability["effects"]] == [2, 2]  # 702.40b: each triggers; two spells before it
    assert s.state.rules.next_spell_grants == []
    answer_all(s)
    run(s)
    answer_all(s)
    run(s)
    assert s.state.players["p2"].life == 40 - 3 * 5 and s.state.players["p1"].life == life + 3 * 5  # the Bolt and four copies
    roundtrip(s)
