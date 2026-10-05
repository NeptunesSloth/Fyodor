"""Review of wave 24C — regressions for what the review fixed and the promoted cards the wave left untested.

* 122.2 / 903.9a: counters never follow a card to another zone — Suspend on a commander puts two time counters on it in exile, the
  commander goes to the command zone as a state-based action and must not keep them (cast later, it would enter with them).
* 707.3 / 110.5c: a copy of a flip card copies both halves and uses its own flipped status (Clone copying a flipped Tobita is a
  Student of Elements, which then flips itself once Tobita gives it flying).
* 113.6m: Tetzimoc's "{B}, Reveal this card from your hand" works from the hand (listed in the hints for the hand menu), any number of
  times during your turn; the reveal ends at once.
* Thought Gorger, Floodgate, Systems Override, Wishing Well (603.12 / 608.2c "If you do" / "When you do" after putting counters, 614.17
  Solemnity; 603.8 "When this creature has flying").

Real Oracle text (tests/fixtures/review24c_cards.json and the wave 24C fixtures, from data/cards.sqlite); replay + save/load each time."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.session import GameSession
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, settle, to_hand, token_of
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_wave7b_activation import ability_index

_F = Path(__file__).parent / "fixtures"
_DATA = {c["name"]: c for f in [*sorted(_F.glob("wave24c_*.json")), _F / "review24c_cards.json"] for c in json.loads(f.read_text("utf-8"))}
EXTRA = [card(n, set_code="r24c", number=f"R{i:03d}", **{k: v for k, v in c.items() if k != "name"}) for i, (n, c) in enumerate(_DATA.items())]
STUDENT = next(n for n in _DATA if n.startswith("Student of Elements"))


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def check(s):
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def on_field(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def counters(s, c):
    return {k: v for k, v in s.state.cards[c.id].counters.items() if v}


def run(s, pick=lambda d, ids: ids[: max(1, d.min_choices)], limit=30):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick(d, [o.id for o in d.options]))
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def test_time_counters_dont_follow_a_commander_to_the_command_zone(cards):
    s = build(cards, "Suspend")
    atraxa = next(c for c in s.state.cards.values() if c.name == "Atraxa, Praetors' Voice")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"player": "p2", "zone": "battlefield"})
    spell = to_hand(s, "Suspend")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[atraxa.id])
    run(s, lambda d, ids: ["yes"] if "yes" in ids else ids[:1])  # (903.9a: Bob moves his commander to the command zone)
    assert s.state.cards[atraxa.id].zone == "p2:command"
    assert counters(s, atraxa) == {}  # 122.2: the time counters stayed behind with the exiled object
    check(s)


def test_a_suspended_card_that_leaves_exile_loses_its_time_counters(cards):
    s = build(cards, "Suspend", p2=("Grizzly Bears",))
    bears = on_field(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Suspend")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])
    settle(s)
    assert counters(s, bears) == {"time": 2}
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "hand"})
    assert counters(s, bears) == {}  # 122.2, 400.7
    check(s)


def test_a_copy_of_a_flip_card_uses_its_own_flipped_status(cards):
    s = build(cards, STUDENT, "Jump", "Clone")
    student = on_field(s, STUDENT)
    jump = to_hand(s, "Jump")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=jump.id, targets=[student.id])
    settle(s)
    assert s.state.cards[student.id].flipped and ch(s, student).name == "Tobita, Master of Winds"
    clone = to_hand(s, "Clone")
    mana(s, "p1", U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=clone.id)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and "copy" in (d.prompt or ""):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[student.id])
        elif d is not None and "Legend rule" in (d.prompt or ""):
            assert s.state.cards[clone.id].flipped and ch(s, clone).name == "Tobita, Master of Winds"  # its own flip (Tobita gave it flying)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[student.id])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    # 707.3: the copy entered unflipped (Student of Elements, the normal half) and flipped itself: two flips in the log
    assert sum(any(p.t == " flipped " for p in e.parts) for e in s.state.log) == 2
    assert s.state.cards[clone.id].zone == "p1:graveyard" and s.state.cards[student.id].zone == "p1:battlefield"
    check(s)


def test_tetzimoc_reveals_itself_from_the_hand(cards):
    from app.rules.casting import activatable

    s = build(cards, "Tetzimoc, Primal Death")
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    tetz = to_hand(s, "Tetzimoc, Primal Death")
    idx = ability_index(s, tetz, "prey")
    for _ in range(2):  # (no "once each turn")
        mana(s, "p1", B=1)
        assert {"card_id": tetz.id, "ability": idx} in activatable(s.state, "p1", Plan(s.state, "p1", s.cards, None).info)
        act(s, "p1", type="activate_ability", card_id=tetz.id, ability=idx, targets=[bear.id])
        settle(s)
    assert counters(s, bear) == {"prey": 2}
    assert s.state.cards[tetz.id].zone == "p1:hand" and not s.state.cards[tetz.id].revealed_to
    check(s)


@pytest.mark.parametrize("solemnity", [False, True])
def test_thought_gorger_discards_only_if_counters_were_put(cards, solemnity):
    s = build(cards, "Thought Gorger", "Lightning Bolt", "Brainstorm", "Solemnity")
    if solemnity:
        on_field(s, "Solemnity")
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Brainstorm")
    gorger = to_hand(s, "Thought Gorger")
    mana(s, "p1", B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=gorger.id)
    settle(s)
    if solemnity:  # 614.17: no counter put, so "If you do" is false (608.2c)
        assert counters(s, gorger) == {} and len(s.state.zones["p1:hand"]) == 2
    else:
        assert counters(s, gorger) == {"+1/+1": 2} and s.state.zones["p1:hand"] == []
    check(s)


def test_systems_override_puts_no_charge_counters_on_a_non_spacecraft(cards):
    s = build(cards, "Systems Override")
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    spell = to_hand(s, "Systems Override")
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[bear.id].controller == "p1" and counters(s, bear) == {}
    check(s)


@pytest.mark.parametrize("solemnity", [False, True])
def test_wishing_well_casts_only_when_the_coin_counter_is_put(cards, solemnity):
    s = build(cards, "Wishing Well", "Lightning Bolt", "Solemnity")
    if solemnity:
        on_field(s, "Solemnity")
    well = on_field(s, "Wishing Well")
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="activate_ability", card_id=well.id, ability=ability_index(s, well, "coin"))
    run(s, lambda d, ids: ["p2"] if "p2" in ids else ["yes"] if "yes" in ids else ids[:1])
    if solemnity:
        assert counters(s, well) == {} and s.state.cards[bolt.id].zone == "p1:graveyard"
    else:  # mana value 1 = one coin counter: cast free, exiled instead of the graveyard
        assert counters(s, well) == {"coin": 1} and s.state.cards[bolt.id].zone == "p1:exile" and s.state.players["p2"].life == 37
    check(s)


def test_floodgate_is_sacrificed_once_it_has_flying(cards):
    s = build(cards, "Floodgate", "Jump")
    gate = on_field(s, "Floodgate")
    settle(s)
    assert s.state.cards[gate.id].zone == "p1:battlefield"
    jump = to_hand(s, "Jump")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=jump.id, targets=[gate.id])
    settle(s)
    assert s.state.cards[gate.id].zone == "p1:graveyard"
    check(s)
