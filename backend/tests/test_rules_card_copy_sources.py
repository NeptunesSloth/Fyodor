"""Actual canonical original-card copy/cast sequences and saved cost authority."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_linked_aggregates import cast, ch
from tests.test_rules_linked_return_family import choose
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/card_copy_sources_cards.json").read_text())
NAMES = [c["name"] for c in DATA[:10]]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"],
            set_code="lor",
            number=str(i),
            **{k: v for k, v in c.items() if k not in ("name", "set_code")},
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, name, *, hand=False):
    support = [c["name"] for c in DATA[10:]] + ["Grizzly Bears", "Llanowar Elves"]
    s = table(cards, [name, *support], support, support)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True)
    return s, put(s, name, "hand" if hand else "battlefield")


def copy_decision(s):
    until(
        s,
        lambda s: (
            s.state.rules.decision is not None
            and s.state.rules.decision.kind not in ("declare_attackers", "declare_blockers")
        ),
    )
    d = s.state.rules.decision
    assert d.resume.get("step") == "free_cast_pick", (d.kind, d.prompt, d.resume)
    return d


def cast_copy(s, name, targets=None):
    d = copy_decision(s)
    chosen = next(o.id for o in d.options if s.state.cards[o.card_id or o.id.split("@")[0]].name == name)
    choose(s, [chosen])
    if targets is not None:
        choose(s, targets)
    return chosen.split("@")[0]


@pytest.mark.parametrize("name", NAMES)
def test_canonical_copy_card_definitions_are_full(cards, name):
    got = coverage.of_card_data(cards.resolve(name))
    assert got.level == "FULL", (name, got.manual_parts)


def test_panoptic_native_x_hand_imprint_then_upkeep_copy(cards):
    s, src = setup(cards, "Panoptic Mirror")
    original = put(s, "Divination", "hand")
    mana(s, C=3)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, x_value=3)
    choose(s, [original.id])
    settle(s)
    assert s.state.cards[original.id].zone == "p1:exile"
    to_phase(s, "upkeep", turn=4)
    choose(s, [original.id])
    cid = cast_copy(s, "Divination")
    assert s.state.cards[cid].zone == "stack" and s.state.cards[cid].is_token
    before = len(s.state.zones["p1:hand"])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before + 2
    assert s.state.cards[original.id].zone == "p1:exile"
    roundtrip(s)


def test_eye_native_original_card_exile_cast_copy_does_not_retrigger(cards):
    s, src = setup(cards, "Eye of the Storm")
    original = put(s, "Lightning Bolt", "hand", "p2")
    mana(s, "p2", R=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=original.id, targets=["p3"])
    cid = cast_copy(s, "Lightning Bolt", ["p3"])
    assert s.state.cards[cid].controller == "p2" and s.state.cards[cid].owner == "p2"
    settle(s)
    assert s.state.cards[original.id].zone == "p2:exile"
    assert not s.state.zones["stack"] and s.state.rules.decision is None
    assert s.state.rules.exiled_with[s.state.rules.object_id(src.id)] == [
        s.state.rules.object_id(original.id)
    ]
    roundtrip(s)


def test_zethi_native_kicker_exile_then_attack_paid_copy(cards):
    s, src = setup(cards, "Zethi, Arcane Blademaster", hand=True)
    original = put(s, "Raise the Alarm", "graveyard")
    cast(s, src, kicker=1, targets=[original.id], target_counts=[1])
    settle(s)
    assert (
        s.state.cards[original.id].zone == "p1:exile" and s.state.cards[original.id].counters.get("kick") == 1
    )
    to_phase(s, "declare_attackers", turn=4)
    mana(s, W=1, C=1)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": src.id, "target": "p2"}])
    cast_copy(s, "Raise the Alarm")
    settle(s)
    assert (
        len(
            [
                c
                for c in s.state.cards.values()
                if c.is_token and c.zone == "p1:battlefield" and "Soldier" in ch(s, c).subtypes
            ]
        )
        == 2
    )
    assert s.state.cards[original.id].zone == "p1:exile"
    roundtrip(s)


def test_wildfire_native_random_player_chooses_original_controller_casts(cards):
    s, src = setup(cards, "Wildfire Devils", hand=True)
    originals = [put(s, "Lightning Bolt", "graveyard", p) for p in ["p1", "p2", "p3"]]
    cast(s, src)
    cid = cast_copy(s, "Lightning Bolt", ["p3"])
    settle(s)
    assert s.state.players["p3"].life == 37
    assert len([c for c in originals if s.state.cards[c.id].zone.endswith(":exile")]) == 1
    assert cid not in s.state.cards
    roundtrip(s)


def test_spelltwine_native_two_originals_mandatory_sequential_casts(cards):
    s, src = setup(cards, "Spelltwine", hand=True)
    a = put(s, "Divination", "graveyard")
    b = put(s, "Raise the Alarm", "graveyard", "p2")
    cast(s, src, targets=[a.id, b.id], target_counts=[1, 1])
    d = copy_decision(s)
    assert d.min_choices == 1
    first = cast_copy(s, "Divination")
    d = copy_decision(s)
    assert d.min_choices == 1 and s.state.cards[first].zone == "stack"
    cast_copy(s, "Raise the Alarm")
    settle(s)
    assert s.state.cards[src.id].zone == "p1:exile"
    assert s.state.cards[a.id].zone == "p1:exile" and s.state.cards[b.id].zone == "p2:exile"
    assert (
        len(
            [
                c
                for c in s.state.cards.values()
                if c.is_token and c.zone == "p1:battlefield" and "Soldier" in ch(s, c).subtypes
            ]
        )
        == 2
    )
    roundtrip(s)


def test_hellraiser_native_random_exile_chosen_noncreature_copy(cards):
    s, src = setup(cards, "Capricious Hellraiser", hand=True)
    original = put(s, "Divination", "graveyard")
    put(s, "Grizzly Bears", "graveyard")
    put(s, "Llanowar Elves", "graveyard")
    cast(s, src)
    cast_copy(s, "Divination")
    settle(s)
    assert s.state.cards[original.id].zone == "p1:exile"
    roundtrip(s)


@pytest.mark.parametrize("roll", [5, 15, 20])
def test_spellbook_actual_all_three_native_die_rows(cards, roll):
    s, src = setup(cards, "Wizard's Spellbook")
    original = put(s, "Divination", "graveyard", "p2")
    mana(s, U=1, C=2 if roll == 5 else 1 if roll == 15 else 0)
    wait_priority(s, "p1")
    with patch("app.game.resolve._rng_int", lambda rng, lo, hi: roll if (lo, hi) == (1, 20) else lo):
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[original.id])
        copy_decision(s)
    cid = cast_copy(s, "Divination")
    assert s.state.cards[cid].zone == "stack"
    rec = s.state.rules.payments[s.state.rules.object_id(cid)]
    assert rec.total_cost == ("{2}{U}" if roll == 5 else "{1}" if roll == 15 else "")
    settle(s)
    assert s.state.cards[original.id].zone == "p2:exile"
    roundtrip(s)


def test_jacob_native_assassin_combat_exile_and_paid_permanent_copy(cards):
    s, src = setup(cards, "Jacob Frye")
    original = put(s, "Royal Assassin", "graveyard")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": src.id, "target": "p2"}])
    until(
        s,
        lambda s: (
            s.state.rules.decision is not None
            and s.state.rules.decision.kind not in ("declare_attackers", "declare_blockers")
        ),
    )
    d = s.state.rules.decision
    assert original.id in [o.id for o in d.options], (d.kind, d.resume, [(o.id, o.label) for o in d.options])
    choose(s, [original.id])
    mana(s, B=2, C=1)
    cast_copy(s, "Royal Assassin")
    settle(s)
    copied = [
        c
        for c in s.state.cards.values()
        if c.is_token and c.zone == "p1:battlefield" and c.name == "Royal Assassin"
    ]
    assert len(copied) == 1 and copied[0].copy_of is not None
    assert s.state.cards[original.id].zone == "p1:exile"
    roundtrip(s)


def test_cane_native_equipped_attack_defender_graveyard_fixed_cost(cards):
    s, src = setup(cards, "Blue Mage's Cane")
    host = put(s, "Grizzly Bears", "battlefield")
    original = put(s, "Divination", "graveyard", "p2")
    mana(s, C=2)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=src.id, ability=2, targets=[host.id])
    settle(s)
    to_phase(s, "declare_attackers", turn=4)
    mana(s, C=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": host.id, "target": "p2"}])
    choose(s, [original.id])
    cid = cast_copy(s, "Divination")
    assert s.state.rules.payments[s.state.rules.object_id(cid)].total_cost == "{3}"
    settle(s)
    assert s.state.cards[original.id].zone == "p2:exile"
    roundtrip(s)


def test_surge_native_team_pump_then_exact_original_copy_from_damage(cards):
    s, src = setup(cards, "Surge to Victory", hand=True)
    host = put(s, "Grizzly Bears", "battlefield")
    original = put(s, "Lightning Bolt", "graveyard")
    to_phase(s, "main1", turn=4)
    cast(s, src, targets=[original.id])
    settle(s)
    assert ch(s, host).pt == (3, 2)
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": host.id, "target": "p2"}])
    cid = cast_copy(s, "Lightning Bolt", ["p2"])
    settle(s)
    assert s.state.players["p2"].life == 34
    assert cid not in s.state.cards and s.state.cards[original.id].zone == "p1:exile"
    roundtrip(s)


def test_spellbook_fixed_alternative_cold_preserves_cost_modifiers(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, src = setup(cards, "Wizard's Spellbook")
    original = put(s, "Divination", "graveyard", "p2")
    put(s, "Thalia, Guardian of Thraben", "battlefield", "p2")
    put(s, "Baral, Chief of Compliance", "battlefield")
    mana(s, C=1)
    wait_priority(s, "p1")
    with patch("app.game.resolve._rng_int", lambda rng, lo, hi: 15 if (lo, hi) == (1, 20) else lo):
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[original.id])
        d = copy_decision(s)
    cid = next(o.card_id for o in d.options if o.card_id)
    s = cold_choose(s, cards, tmp_path, [cid])
    receipt = s.state.rules.payments[s.state.rules.object_id(cid)]
    assert receipt.total_cost == "{1}"
    assert s.state.cards[cid].zone == "stack"
    settle(s)
    assert s.state.cards[original.id].zone == "p2:exile"
    roundtrip(s)


def test_spellbook_table_merge_keeps_unsupported_extra_timing_manual(cards):
    from app.rules import oracle, scripts
    from app.rules.coverage import printed_from_data

    actual = dict(cards.resolve("Wizard's Spellbook"))
    actual["oracle_text"] = actual["oracle_text"].replace(
        "Activate only as a sorcery.", "Activate only as a sorcery and only if you attacked this turn."
    )
    actual["oracle_id"] = "unsupported-spellbook-timing"
    actual["id"] = "unsupported-spellbook-timing"
    ch_ = printed_from_data(actual, 0)
    assert len(oracle.parse_abilities(actual["oracle_text"])) == 4
    assert any(scripts.define(a, ch_) is None for a in ch_.abilities)


@pytest.mark.parametrize("both_illegal", [False, True])
def test_spelltwine_actual_removed_originals_only_copies_remaining_legal_targets(cards, both_illegal):
    s, src = setup(cards, "Spelltwine", hand=True)
    a = put(s, "Divination", "graveyard")
    b = put(s, "Raise the Alarm", "graveyard", "p2")
    cast(s, src, targets=[a.id, b.id], target_counts=[1, 1])
    removal = put(s, "Cling to Dust", "hand")
    cast(s, removal, targets=[a.id])
    if both_illegal:
        # Counterpart player has their own actual second copy of the exiler.
        removal2 = put(s, "Cling to Dust", "hand", "p2")
        mana(s, "p2", B=1)
        wait_priority(s, "p2")
        act(s, "p2", type="cast_spell", card_id=removal2.id, targets=[b.id])
    if both_illegal:
        settle(s)
        assert s.state.cards[src.id].zone == "p1:graveyard"
        assert not [c for c in s.state.cards.values() if c.copy_of is not None]
    else:
        d = copy_decision(s)
        assert len(d.options) == 1 and s.state.cards[d.options[0].card_id].name == "Raise the Alarm"
        cast_copy(s, "Raise the Alarm")
        settle(s)
        assert s.state.cards[src.id].zone == "p1:exile"
    roundtrip(s)


def test_panoptic_departed_source_pending_upkeep_retains_old_exact_link(cards):
    s, src = setup(cards, "Panoptic Mirror")
    original = put(s, "Divination", "hand")
    mana(s, C=3)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, x_value=3)
    choose(s, [original.id])
    settle(s)
    to_phase(s, "upkeep", turn=4)
    removal = put(s, "Naturalize", "hand")
    cast(s, removal, targets=[src.id])
    choose(s, [original.id])
    cast_copy(s, "Divination")
    settle(s)
    assert s.state.cards[src.id].zone == "p1:graveyard"
    assert s.state.cards[original.id].zone == "p1:exile"
    roundtrip(s)


def fixed_spellbook(cards, name, *, creatures=False):
    s, src = setup(cards, "Wizard's Spellbook")
    actual = next(
        c.name
        for c in s.state.cards.values()
        if c.owner == "p2" and (c.name == name or c.name.startswith(name + " //"))
    )
    original = put(s, actual, "graveyard", "p2")
    if creatures:
        put(s, "Grizzly Bears", "battlefield")
        put(s, "Llanowar Elves", "battlefield")
    mana(s, C=1)
    wait_priority(s, "p1")
    with patch("app.game.resolve._rng_int", lambda rng, lo, hi: 15 if (lo, hi) == (1, 20) else lo):
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[original.id])
        copy_decision(s)
    return s, src, original


def test_fixed_copy_additional_sacrifice_cost_pauses_and_resumes_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, src, original = fixed_spellbook(cards, "Fling", creatures=True)
    bear = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield")
    cid = cast_copy(s, "Fling", ["p3"])
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "ability_cost"
    assert "options" not in s.view("p2")["rules"]["decision"]
    s = cold_choose(s, cards, tmp_path, [bear.id])
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    assert s.state.rules.payments[s.state.rules.object_id(cid)].total_cost == "{1}"
    settle(s)
    assert s.state.players["p3"].life == 38
    assert s.state.cards[original.id].zone == "p2:exile"
    roundtrip(s)


def test_fixed_copy_x_is_zero_and_land_face_is_not_castable(cards):
    s, src, original = fixed_spellbook(cards, "Shatterskull Smashing")
    d = copy_decision(s)
    assert len(d.options) == 1
    cid = d.options[0].card_id
    choose(s, [d.options[0].id])
    if s.state.rules.decision is not None:
        choose(s, [])
    assert s.state.cards[cid].zone == "stack"
    assert s.state.rules.stack[cid].x == 0
    assert s.state.rules.payments[s.state.rules.object_id(cid)].total_cost == "{1}"
    settle(s)
    assert s.state.cards[original.id].zone == "p2:exile"
    roundtrip(s)


def test_panoptic_saved_original_selection_and_copy_cast_both_resume_cold(cards, tmp_path):
    from tests.test_rules_linked_return_family import cold_choose

    s, src = setup(cards, "Panoptic Mirror")
    original = put(s, "Divination", "hand")
    mana(s, C=3)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0, x_value=3)
    choose(s, [original.id])
    settle(s)
    to_phase(s, "upkeep", turn=4)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.resume["step"] == "select_copy_originals"
    s = cold_choose(s, cards, tmp_path, [original.id])
    d = copy_decision(s)
    cid = d.options[0].card_id
    s = cold_choose(s, cards, tmp_path, [d.options[0].id])
    assert s.state.cards[cid].zone == "stack"
    settle(s)
    assert s.state.cards[original.id].zone == "p1:exile"
    roundtrip(s)


def test_jacob_freerunning_card_branch_and_native_paid_alternative(cards):
    s, src = setup(cards, "Jacob Frye")
    original = put(s, "Eagle Vision", "graveyard")
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": src.id, "target": "p2"}])
    until(
        s,
        lambda s: (
            s.state.rules.decision is not None
            and s.state.rules.decision.kind not in ("declare_attackers", "declare_blockers")
        ),
    )
    assert original.id in [o.id for o in s.state.rules.decision.options]
    choose(s, [original.id])
    mana(s, U=1, C=1)
    d = copy_decision(s)
    cid = d.options[0].card_id
    choose(s, [d.options[0].id])
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "paid_effect_cost"
    alternative = next(o.id for o in d.options if o.id not in ("normal", "cancel") and "{1}{U}" in o.label)
    choose(s, [alternative])
    assert s.state.rules.payments[s.state.rules.object_id(cid)].total_cost == "{1}{U}"
    before = len(s.state.zones["p1:hand"])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before + 3
    assert s.state.cards[original.id].zone == "p1:exile"
    roundtrip(s)


@pytest.mark.parametrize("roll", [5, 15])
def test_spellbook_no_mana_cost_card_requires_the_specified_alternative(cards, roll):
    s, src = setup(cards, "Wizard's Spellbook")
    original = put(s, "Ancestral Vision", "graveyard", "p2")
    mana(s, C=1)
    wait_priority(s, "p1")
    with patch("app.game.resolve._rng_int", lambda rng, lo, hi: roll if (lo, hi) == (1, 20) else lo):
        act(s, "p1", type="activate_ability", card_id=src.id, ability=0, targets=[original.id])
        if roll == 15:
            copy_decision(s)
        else:
            settle(s)
    if roll == 15:
        cid = cast_copy(s, "Ancestral Vision", ["p1"])
        assert s.state.rules.payments[s.state.rules.object_id(cid)].total_cost == "{1}"
        before = len(s.state.zones["p1:hand"])
        settle(s)
        assert len(s.state.zones["p1:hand"]) == before + 3
    assert s.state.cards[original.id].zone == "p2:exile"
    assert not [c for c in s.state.cards.values() if c.copy_of is not None]
    roundtrip(s)
