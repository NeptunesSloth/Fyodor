"""Permanent spell entry retains its own live effects, without following later objects."""

from app.rules import layers
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_contextual_mana_triggers import answer, cast, domri_mana
from tests.test_rules_contextual_mana_triggers import cards as cards
from tests.test_rules_designations import put, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


def test_native_domri_riot_grant_does_not_follow_blinked_new_permanent(cards):
    s = table(cards, ["Domri, Chaos Bringer", "Grizzly Bears", "Cloudshift"], [], [])
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "main1", 4)
    domri_mana(s)
    c = cast(s, "Grizzly Bears", {"G": 1})
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume["what"] == "riot"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["counter"])
    answer(s)
    old = s.state.rules.object_id(c.id)
    assert s.state.cards[c.id].counters["+1/+1"] == 1
    wait_priority(s, "p1")
    spell = put(s, "Cloudshift", "hand")
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[c.id], sources=[])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[c.id].zone == "p1:battlefield" and s.state.rules.object_id(c.id) != old
    assert "riot" not in Plan(s.state, "p1", cards, None).ch(s.state.cards[c.id]).keywords
    assert not s.state.cards[c.id].counters


def test_instant_spell_is_not_eligible_for_permanent_spell_entry_effects(cards):
    s = table(cards, ["Lightning Bolt"], [], [])
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "main1", 4)
    wait_priority(s, "p1")
    c = cast(s, "Lightning Bolt", {"R": 1}, targets=["p2"])
    assert s.state.rules.stack[c.id].kind == "spell"
    incoming = s.state.cards[c.id].model_copy(update={"zone": "p1:battlefield"})
    assert not layers.spell_entry(s.state, incoming, cards)


def test_real_activated_ability_placeholder_is_not_an_entering_permanent_spell(cards):
    s = table(cards, ["Domri, Chaos Bringer"], [], [])
    act(s, "p1", type="set_prefs", hold_priority=True)
    to_phase(s, "main1", 4)
    source = cast(s, "Domri, Chaos Bringer", {"C": 2, "R": 1, "G": 1})
    answer(s)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0)
    cid = next(cid for cid, e in s.state.rules.stack.items() if e.kind == "activated")
    assert s.state.cards[cid].ability is not None
    incoming = s.state.cards[cid].model_copy(update={"zone": "p1:battlefield"})
    assert not layers.spell_entry(s.state, incoming, cards)
