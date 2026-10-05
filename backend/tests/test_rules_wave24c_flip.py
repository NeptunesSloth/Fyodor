"""Wave 24C: flip cards (CR 710, 110.5, 201.4c) — "At the beginning of the end step, if there are two or more ki counters on this creature,
you may flip it." (Callow Jushi), "When you have 30 or more life, flip Rune-Tail." (Rune-Tail, Kitsune Ascendant), "Whenever this creature
deals damage to an opponent, flip it." (Akki Lavarunner).

* 710.2: a flipped permanent has the alternative name, text box, type line and power and toughness; 710.1c: its color and mana cost don't change.
* 710.4 / 110.5: flipping is one-way, and a permanent that leaves the battlefield forgets it was flipped.
* 707 / 110.5: copying a flip card isn't automated (the copy's own status, the alternative characteristics a copy has too).

Every scenario uses real Oracle text (tests/fixtures/wave24c_flip_cards.json, from data/cards.sqlite) and checks that replaying the recorded history
reproduces the table and that a save/load round trip keeps it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, settle, to_hand
from tests.test_rules_effects import replay_matches
from tests.test_rules_suspend import until

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave24c_flip_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t24f", number=f"F{i:02d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]
JUSHI, AKKI, RUNE_TAIL = DATA[0]["name"], DATA[1]["name"], DATA[2]["name"]
STUDENT = next(c["name"] for c in DATA if c["name"].startswith("Student of Elements"))


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


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def test_a_flipped_permanent_has_the_alternative_characteristics_but_keeps_color_and_cost(cards):
    s = build(cards, JUSHI)
    jushi = on_field(s, JUSHI)
    act(s, "p1", type="counter", card_ids=[jushi.id], kind="ki", delta=2)
    until(s, lambda s: s.state.rules.decision is not None and "flip" in (s.state.rules.decision.prompt or "").lower() or s.state.cards[jushi.id].flipped,
          limit=400)
    if not s.state.cards[jushi.id].flipped:  # (a "you may": say yes)
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if "yes" in [o.id for o in d.options] else [d.options[0].id])
        settle(s)
    now = ch(s, jushi)
    assert s.state.cards[jushi.id].flipped
    assert now.name == "Jaraku the Interloper" and "Legendary" in now.supertypes and now.subtypes == frozenset({"Spirit"})  # 710.2
    assert (now.power, now.toughness) == ("3", "4")
    assert now.colors == frozenset({"U"}) and now.mana_value == 3 and now.mana_cost == "{1}{U}{U}"  # 710.1c
    assert any("ki counter" in a.text for a in now.abilities)  # the flipped half's ability, not the front's trigger
    assert not any("Whenever you cast a Spirit or Arcane" in a.text for a in now.abilities)
    check(s)
    act(s, "p1", type="move", card_ids=[jushi.id], to={"player": "p1", "zone": "graveyard"})  # 110.5: no memory of being flipped
    assert not s.state.cards[jushi.id].flipped and ch(s, jushi).name.startswith("Callow Jushi")
    check(s)


def test_rune_tail_flips_as_soon_as_its_controller_has_thirty_life(cards):
    s = build(cards, RUNE_TAIL)
    tail = on_field(s, RUNE_TAIL)
    until(s, lambda s: s.state.cards[tail.id].flipped or s.state.turn.number > 1, limit=100)
    settle(s)
    now = ch(s, tail)
    assert s.state.cards[tail.id].flipped and now.name == "Rune-Tail's Essence" and "Enchantment" in now.types and "Creature" not in now.types
    settle(s)
    assert s.state.cards[tail.id].flipped  # one-way (710.4): it doesn't flip again, and nothing turns it back
    check(s)


def test_student_of_elements_flips_once_it_has_flying(cards):
    from tests.test_rules_effects import mana

    s = build(cards, STUDENT, "Jump")
    student = on_field(s, STUDENT)
    settle(s)
    assert not s.state.cards[student.id].flipped  # no flying yet: the state trigger (603.8) waits
    jump = to_hand(s, "Jump")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=jump.id, targets=[student.id])
    settle(s)
    assert s.state.cards[student.id].flipped and ch(s, student).name == "Tobita, Master of Winds"
    check(s)


def test_a_flip_card_is_not_copied_automatically(cards):
    from app.rules import copying

    s = build(cards, JUSHI)
    jushi = on_field(s, JUSHI)
    assert "flip card" in (copying.supported_source(Plan(s.state, "p1", s.cards, None), s.state.cards[jushi.id]) or "")


def test_akki_lavarunner_flips_when_it_deals_damage_to_an_opponent(cards):
    from tests.test_rules_wave23c_values import attack, unready

    s = build(cards, AKKI)
    akki = on_field(s, AKKI)
    unready(s, akki)
    attack(s, akki)
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.cards[akki.id].flipped and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[akki.id].flipped and ch(s, akki).name == "Tok-Tok, Volcano Born"
    assert ch(s, akki).colors == frozenset({"R"})  # 710.1c: the color doesn't change
    check(s)
