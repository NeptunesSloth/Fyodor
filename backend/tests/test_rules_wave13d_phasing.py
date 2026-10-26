"""Wave 13D: phasing (CR 702.26, researched against CR 2026-09-25): "phase out" effects (Reality Ripple, Haystack, Clever
Concealment-style mass wording) and the phasing keyword (Merfolk Raiders, Teferi's Drake).

* 702.26b: a phased-out permanent is treated as though it doesn't exist (it isn't on the battlefield for any query, can't be
  targeted) and leaves combat; 702.26d: no zone change (same object, counters and tokens stay, no leave / enter triggers).
* 702.26a/g: it phases in before its controller untaps; Auras / Equipment phase out and in with it.
* 702.26a: with phasing, the controller's phased-in permanents phase out in their untap step.
Every scenario uses real Oracle text and checks the replay and a save and a load.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_animation import build
from tests.test_rules_effects import mana, pass_until_stack_empty, run_until, token
from tests.wave9c_kit import check

HAYSTACK = "{2}, {T}: Target creature you control phases out. (Treat it and anything attached to it as though they don't exist until your next turn.)"  # noqa: E501
RIPPLE = "Target artifact, creature, or land phases out. (While it's phased out, it's treated as though it doesn't exist. It phases in before its controller untaps during their next untap step.)"  # noqa: E501
RAIDERS = "Islandwalk (This creature can't be blocked as long as defending player controls an Island.)\nPhasing (This phases in or out before you untap during each of your untap steps. While it's phased out, it's treated as though it doesn't exist.)"  # noqa: E501
CONCEALMENT = "Any number of target nonland permanents you control phase out. (Treat them and anything attached to them as though they don't exist until your next turn.)"  # noqa: E501
CRYSTAL = "At the beginning of your end step, this creature phases out. (While it's phased out, it's treated as though it doesn't exist. It phases in before you untap during your next untap step.)"  # noqa: E501


@pytest.mark.parametrize("kind,line", [("Sorcery", RIPPLE), ("Creature", HAYSTACK), ("Creature", RAIDERS),
                                       ("Sorcery", CONCEALMENT), ("Creature", CRYSTAL)])
def test_the_lines_are_supported(kind, line):
    from tests.test_rules_scripts import ch as characteristics

    assert coverage.of_characteristics(characteristics("Test", kind, line)).level == "FULL"


@pytest.mark.parametrize("line", [
    "Target creature phases out until this enchantment leaves the battlefield.",
    # ("Permanents can't phase in." is read since wave 110O: Disciple of Caelus Nin, tests/test_rules_wave110o_b.py)
    "Target creature phases out. It can't phase in for as long as this remains tapped."])
def test_other_wordings_stay_manual(line):
    from tests.test_rules_scripts import ch as characteristics

    assert coverage.of_characteristics(characteristics("Test", "Creature", line)).level != "FULL"


def on_bf(s, cid):
    return s.state.cards[cid].zone.endswith(":battlefield")


def test_phase_out_and_in_with_attachments_counters_and_no_zone_change(cards):
    s = build(cards)
    src = token(s, "p1", "Haystack", "1/1", HAYSTACK)
    bear = token(s, "p1", "Bear", "2/2")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    act(s, "p1", type="create_token", player="p1", token={"name": "Gear", "type_line": "Token Artifact — Equipment", "text": ""})
    gear = next(c for c in s.state.cards.values() if c.name == "Gear")
    act(s, "p1", type="attach", card_ids=[gear.id], to=bear.id)
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[bear.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].zone == "p1:phased" and not on_bf(s, bear.id)  # 702.26b
    assert s.state.cards[gear.id].zone == "p1:phased" and s.state.cards[gear.id].phased_indirect  # 702.26g
    assert s.state.cards[bear.id].counters == {"+1/+1": 1}  # 702.26d
    oid = s.state.rules.object_id(bear.id)
    check(s)
    run_until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1")  # past her next untap step
    assert on_bf(s, bear.id) and on_bf(s, gear.id) and s.state.cards[gear.id].attached_to == bear.id
    assert s.state.rules.object_id(bear.id) == oid and s.state.cards[bear.id].counters == {"+1/+1": 1}
    assert not s.state.cards[gear.id].phased_indirect
    check(s)


def test_phasing_keyword_alternates_each_untap_step(cards):
    s = build(cards)
    raiders = token(s, "p1", "Merfolk Raiders", "2/2", RAIDERS)
    assert on_bf(s, raiders.id)
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.cards[raiders.id].zone == "p1:phased"  # her first untap step: phases out (a token persists, 702.26d)
    run_until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1")
    assert on_bf(s, raiders.id)
    check(s)


def test_vaporous_djinn_phases_out_unless_its_controller_pays(cards):
    s = build(cards)
    djinn = token(s, "p1", "Vaporous Djinn", "3/4",
                  "Flying\nAt the beginning of your upkeep, this creature phases out unless you pay {U}{U}. (While it's phased out, it's "
                  "treated as though it doesn't exist. It phases in before you untap during your next untap step.)")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # {U}{U} can't be paid: it phases out
    assert s.state.cards[djinn.id].zone == "p1:phased"
    check(s)
