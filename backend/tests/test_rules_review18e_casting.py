"""Review of wave 18E (casting extras): regressions for the bugs found. Real Oracle text, replay and save/load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_wave18e_casting import EXTRA

MORE = [
    card("Rust Goliath", set_code="tst", number="R01", mana_cost="{10}", cmc=10.0, type_line="Artifact Creature — Construct", power="10",
         toughness="10", oracle_text="Prototype {3}{G}{G} — 3/5 (You may cast this spell with different mana cost, color, and size. It keeps "
         "its abilities and types.)\nReach, trample", keywords=["Reach", "Trample", "Prototype"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *MORE], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_assist_with_an_asked_payment_takes_the_helpers_mana_off_once(cards):
    s = build(cards, p1=("Fan Favorite",))
    s.state.rules.prefs["p1"].payment = "ask"
    fav = put(s, "Fan Favorite", "hand")
    mana(s, "p1", B=1, C=2)  # {3}{B}: the helper pays one, the caster {2}{B}
    mana(s, "p2", C=1)
    act(s, "p1", type="cast_spell", card_id=fav.id)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["p2"])
    act(s, "p2", type="choose", decision_id=s.state.rules.decision.id, option_ids=["1"])
    d = s.state.rules.decision
    assert d.player == "p1" and "{2}{B}" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    answer(s)
    assert s.state.cards[fav.id].zone == "p1:battlefield"
    assert s.state.players["p1"].mana.get("C", 0) == 0 and s.state.players["p2"].mana.get("C", 0) == 0
    roundtrip(s)


def test_reconfigure_abilities_come_after_the_printed_lines():
    """702.151a: the two abilities reconfigure stands for are numbered after every printed line, so a printed line's ability number
    is its line number (the card menu's mapping) even when a line follows the keyword."""
    from app.rules.oracle import parse_abilities

    abs_ = parse_abilities("Reconfigure {2}\n{1}: This creature gets +1/+0 until end of turn.")
    assert [a.text for a in abs_[:2]] == ["Reconfigure {2}", "{1}: This creature gets +1/+0 until end of turn."]
    assert abs_[2].text.startswith("{2}: Attach ~ to another target creature") and abs_[3].text.startswith("{2}: Unattach ~.")


def test_a_prototyped_permanent_that_becomes_a_copy_has_the_copied_values(cards):
    """718.3b / 707.2: the prototype's values are copiable values; a copy effect on the permanent replaces them (layer 1)."""
    from app.rules import copying
    from app.rules.plan import Plan
    from tests.test_rules_attachments import ch

    s = build(cards, p1=("Skitterbeam Battalion", "Rust Goliath"))
    sk = put(s, "Skitterbeam Battalion", "hand")
    goliath = put(s, "Rust Goliath", "battlefield")  # (not cast: not prototyped)
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=sk.id, prototype=True)
    answer(s)
    assert ch(s, s.state.cards[sk.id]).pt == (2, 2)
    plan = Plan(s.state, "p1", s.cards, None)
    copying.add_copy_effect(plan, [plan.oid(sk.id)], copying.base_recipe(s.state.cards[goliath.id]), "p1")
    now = plan.ch(plan.state.cards[sk.id])
    assert now.name == "Rust Goliath" and now.pt == (10, 10) and now.mana_value == 10  # (not Rust Goliath's prototype 3/5)


def _ready_counter(s, caster="p2"):
    cs = put(s, "Counterspell", "hand", pid=caster)
    mana(s, caster, U=2)
    return cs


def _counter_top(s, cs, caster="p2"):
    spell = s.state.zones["stack"][-1]
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, caster, type="cast_spell", card_id=cs.id, targets=[spell])
    answer(s)


def test_probe_disturb_countered_is_exiled(cards):
    name = "Lunarch Veteran // Luminous Phantom"
    s = build(cards, p1=(name,), p2=("Counterspell",))
    vet = put(s, name, "graveyard")
    mana(s, W=2)
    cs = _ready_counter(s)
    act(s, "p1", type="cast_spell", card_id=vet.id, alt_cost=f"{vet.id}:1")
    _counter_top(s, cs)
    assert s.state.cards[vet.id].zone == "p1:exile"


def test_probe_jump_start_countered_is_exiled(cards):
    s = build(cards, p1=("Radical Idea", "Test Bear"), p2=("Counterspell",))
    idea = put(s, "Radical Idea", "graveyard")
    put(s, "Test Bear", "hand")
    mana(s, U=1, C=1)
    cs = _ready_counter(s)
    act(s, "p1", type="cast_spell", card_id=idea.id)
    _counter_top(s, cs)
    assert s.state.cards[idea.id].zone == "p1:exile"


def test_miracle_cast_is_offered_only_as_its_trigger_resolves(cards):
    s = build(cards, p1=("Elvish Visionary", "Thunderous Wrath"), p2=("Counterspell",))
    wrath = put(s, "Thunderous Wrath", "library", position="top")
    viz = put(s, "Elvish Visionary", "hand")
    mana(s, G=1, C=1)
    _ready_counter(s)  # (p2 could respond: each stack object waits for them)
    act(s, "p1", type="cast_spell", card_id=viz.id)  # "When this creature enters, draw a card."
    answer(s)
    assert s.state.rules.miracle == [wrath.id]
    mana(s, R=1)
    act(s, "p1", type="miracle_reveal", card_id=wrath.id)
    assert s.state.zones["stack"] and s.state.rules.decision is None  # the reflexive trigger (603.11), not yet resolved
    with pytest.raises(ActionError):  # no cast for {R} while it is on the stack (it could still be countered)
        act(s, "p1", type="cast_spell", card_id=wrath.id, free=True, targets=["p2"])
    assert wrath.id not in s.state.rules.free_casts and wrath.id not in s.state.rules.alt_costs
    roundtrip(s)
