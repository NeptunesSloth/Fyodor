"""Canonical relative tutor qualifiers and ordered Aura/Equipment entry proofs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.conftest import claim_host
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import answer, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave4h_activation_costs import ability
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    data = json.loads((Path(__file__).parent / "fixtures/ordered_tutor_continuation_cards.json").read_text())
    for i, c in enumerate(data):
        base[c["name"]] = card(
            c["name"], set_code="sec", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


NAMES = [
    c["name"]
    for c in json.loads(
        (Path(__file__).parent / "fixtures/ordered_tutor_continuation_cards.json").read_text()
    )
][:14]


@pytest.mark.parametrize("name", NAMES)
def test_canonical_full(cards, name):
    got = coverage.of_card_data(cards.resolve(name))
    assert got.level == "FULL", got


def setup(cards):
    names = [
        c["name"]
        for c in json.loads(
            (Path(__file__).parent / "fixtures/ordered_tutor_continuation_cards.json").read_text()
        )
    ]
    assert all(cards.resolve(n) is not None for n in names), [n for n in names if cards.resolve(n) is None]
    s = table(
        cards,
        [
            *names,
            "Plains",
            "Island",
            "Grizzly Bears",
            "Grizzly Bears",
            "Shivan Dragon",
            "Elfhame Sanctuary",
        ],
        names,
        names,
    )
    to_phase(s, "main1", turn=1)
    return s


def cast(s, name, **kw):
    source = put(s, name, "hand")
    mana(s, C=50, W=20, U=20, B=20, R=20, G=20)
    act(s, "p1", type="cast_spell", card_id=source.id, **kw)
    settle(s)
    return source


def choose_named(s, name):
    return next(o.id for o in s.state.rules.decision.options if s.state.cards[o.id].name == name)


def find(s, name):
    cid = choose_named(s, name)
    answer(s, [cid])
    return cid


def search_yes(s):
    if s.state.rules.decision.resume["step"] == "search_may":
        answer(s, ["yes"])


def activate(s, source, start):
    mana(s, C=50, W=20, U=20, B=20, R=20, G=20)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, start))
    settle(s)


def test_myr_incubator_actual_exile_count(cards):
    s = setup(cards)
    source = put(s, "Myr Incubator", "battlefield")
    activate(s, source, "{6}")
    ids = [choose_named(s, n) for n in ["Sol Ring", "Memnite"]]
    answer(s, ids)
    assert all(s.state.cards[c].zone == "p1:exile" for c in ids)
    tokens = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Myr"]
    assert len(tokens) == 2
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def test_yavimaya_recipient_preserves_owner(cards):
    s = setup(cards)
    cast(s, "Yavimaya Dryad")
    assert s.state.rules.decision is not None
    answer(s, ["p2"])
    search_yes(s)
    cid = choose_named(s, "Forest")
    answer(s, [cid])
    c = s.state.cards[cid]
    assert c.zone == "p2:battlefield" and c.controller == "p2" and c.owner == "p1" and c.tapped
    roundtrip(s)


def test_thawing_delayed_cleanup_actual_return(cards):
    s = setup(cards)
    source = put(s, "Thawing Glaciers", "battlefield")
    activate(s, source, "{1}")
    cid = choose_named(s, "Forest")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield" and s.state.cards[cid].tapped
    to_phase(s, "cleanup", turn=1)
    settle(s)
    assert s.state.cards[source.id].zone == "p1:hand"
    roundtrip(s)


def test_elfhame_search_then_skip_this_turn_draw(cards):
    s = setup(cards)
    put(s, "Elfhame Sanctuary", "battlefield")
    to_phase(s, "upkeep", turn=4)
    settle(s)
    before = len(s.state.zones["p1:hand"])
    search_yes(s)
    cid = choose_named(s, "Forest")
    answer(s, [cid])
    to_phase(s, "main1", turn=4)
    assert len(s.state.zones["p1:hand"]) == before + 1
    assert s.state.cards[cid].zone == "p1:hand"
    roundtrip(s)


def test_distant_memories_opponents_choose_in_order(cards):
    s = setup(cards)
    cast(s, "Distant Memories")
    cid = choose_named(s, "Sol Ring")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:exile"
    assert s.state.rules.decision.player == "p2"
    answer(s, ["no"])
    assert s.state.rules.decision.player == "p3"
    answer(s, ["yes"])
    assert s.state.cards[cid].zone == "p1:hand"
    roundtrip(s)


def test_hithlain_search_then_transfer_right(cards):
    s = setup(cards)
    source = put(s, "Hithlain Rope", "battlefield")
    activate(s, source, "{1}")
    cid = choose_named(s, "Forest")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    assert s.state.cards[source.id].controller == "p3"
    roundtrip(s)


def test_fervent_paid_alternative_then_search(cards):
    s = setup(cards)
    discarded = put(s, "Sol Ring", "hand", "p2")
    source = put(s, "Fervent Mastery", "hand")
    mana(s, C=50, R=10)
    act(s, "p1", type="cast_spell", card_id=source.id, alt_cost=f"{source.id}:0")
    settle(s)
    answer(s, ["p2"])
    answer(s, [discarded.id])
    cid = choose_named(s, "Grizzly Bears")
    answer(s, [cid])
    assert s.state.cards[cid].zone in ("p1:hand", "p1:graveyard")
    assert s.state.cards[discarded.id].zone == "p2:graveyard"
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def test_omenpath_linked_random_land_entry(cards):
    s = setup(cards)
    source = cast(s, "Omenpath Journey")
    ids = [choose_named(s, n) for n in ["Plains", "Forest"]]
    answer(s, ids)
    assert all(s.state.cards[c].zone == "p1:exile" for c in ids)
    to_phase(s, "end", turn=1)
    settle(s)
    arrived = [c for c in ids if s.state.cards[c].zone == "p1:battlefield"]
    assert len(arrived) == 1 and s.state.cards[arrived[0]].tapped
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_doomsday_five_from_both_zones_in_chosen_order(cards):
    s = setup(cards)
    grave = put(s, "Sol Ring", "graveyard")
    before = s.state.players["p1"].life
    cast(s, "Doomsday")
    ids = [grave.id, *[choose_named(s, n) for n in ["Plains", "Forest", "Island", "Grizzly Bears"]]]
    answer(s, ids)
    d = s.state.rules.decision
    assert d.kind == "order"
    answer(s, list(reversed(ids)))
    assert s.state.players["p1"].life == before - (before + 1) // 2
    assert len(s.state.zones["p1:library"]) == 5
    assert [s.state.cards[c].name for c in s.state.zones["p1:library"]] == [
        "Grizzly Bears",
        "Island",
        "Forest",
        "Plains",
        "Sol Ring",
    ]
    roundtrip(s)


def test_prishe_reflexive_target_after_search(cards):
    s = setup(cards)
    host = put(s, "Grizzly Bears", "battlefield")
    source = cast(s, "Prishe's Wanderings")
    assert s.state.rules.decision.resume["step"] == "search"
    cid = choose_named(s, "Second City")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    assert s.state.cards[source.id].zone == "p1:graveyard"
    answer(s, [host.id])
    assert s.state.cards[host.id].counters.get("+1/+1") == 1
    roundtrip(s)


def test_disorient_choices_then_simultaneous_exile_and_tutor(cards):
    s = setup(cards)
    a = put(s, "Sol Ring", "battlefield", "p2")
    b = put(s, "Memnite", "battlefield", "p3")
    cast(s, "Disorienting Choice", targets=[a.id, b.id], target_counts=[1, 1])
    assert s.state.rules.decision.player == "p2"
    answer(s, ["yes"])
    assert s.state.cards[a.id].zone == "p2:battlefield"
    assert "chose to exile" in json.dumps(s.view("p3"))
    answer(s, ["no"])
    assert s.state.cards[a.id].zone == "p2:exile"
    cid = choose_named(s, "Forest")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield" and s.state.cards[cid].tapped
    assert s.state.cards[b.id].zone == "p3:battlefield"
    roundtrip(s)


def test_hawk_damage_returns_then_tutors(cards):
    from tests.test_rules_qualified_attached_tutors import attack_one

    s = setup(cards)
    source = put(s, "Cartographer's Hawk", "battlefield")
    put(s, "Island", "battlefield", "p2")
    attack_one(s, source)
    for _ in range(80):
        d = s.state.rules.decision
        if d and d.resume.get("step") == "search_may":
            break
        if d and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d:
            raise AssertionError(d)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[source.id].zone == "p1:hand", (
        s.state.turn,
        s.state.players["p2"].life,
        s.state.rules.decision,
        s.state.cards[source.id].attacking,
        s.state.rules.turn_log,
    )
    search_yes(s)
    cid = choose_named(s, "Plains")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield" and s.state.cards[cid].tapped
    roundtrip(s)


def test_grim_as_cast_opponent_name_and_own_grave_activation(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = setup(cards)
    to_phase(s, "main1", turn=2)
    ring = put(s, "Sol Ring", "hand", "p2")
    mana(s, pid="p2", C=1)
    act(s, "p2", type="cast_spell", card_id=ring.id)
    settle(s)
    wait_priority(s, "p1")
    before = s.state.players["p2"].life
    source = cast(s, "Grim Reminder")
    cid = choose_named(s, "Sol Ring")
    answer(s, [cid])
    assert s.state.players["p2"].life == before - 6
    assert s.state.cards[source.id].zone == "p1:graveyard"
    to_phase(s, "upkeep", turn=4)
    mana(s, B=2)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, s.state.cards[source.id], "{B}{B}"),
    )
    settle(s)
    assert s.state.cards[source.id].zone == "p1:hand"
    roundtrip(s)


def test_sift_uses_named_casts_even_countered_peer(cards):
    s = setup(cards)
    peer = put(s, "Peer Through Depths", "hand")
    counter = put(s, "Counterspell", "hand")
    mana(s, C=10, U=10)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=peer.id)
    act(s, "p1", type="cast_spell", card_id=counter.id, targets=[peer.id])
    settle(s)
    cast(s, "Reach Through Mists")
    cast(s, "Sift Through Sands")
    d = s.state.rules.decision
    answer(s, [d.options[0].id])
    search_yes(s)
    cid = choose_named(s, "The Unspeakable")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    roundtrip(s)


def test_unsupported_grave_activation_stays_partial():
    data = card(
        "Unsupported graveyard activation boundary",
        type_line="Instant",
        oracle_text="Scry 1.\nSacrifice an idea: Return this card from your graveyard to your hand.",
    )
    assert coverage.of_card_data(data).level != "FULL"


def test_doomsday_agent_combined_grave_and_library_cold(cards):
    from tests.test_rules_qualified_attached_tutors import cold

    s = setup(cards)
    put(s, "Opposition Agent", "battlefield", "p2")
    grave = put(s, "Sol Ring", "graveyard")
    cast(s, "Doomsday")
    assert s.state.rules.decision.decider == "p2"
    ids = [grave.id, *[choose_named(s, n) for n in ["Plains", "Forest", "Island", "Grizzly Bears"]]]
    s = cold(s, cards)
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=ids)
    settle(s)
    assert all(s.state.cards[c].zone == "p1:exile" for c in ids)
    assert all(any(g.card == c and g.player == "p2" for g in s.state.rules.permissions) for c in ids)
    assert not s.state.zones["p1:library"]
    assert s.state.rules.decision is None
    roundtrip(s)


def test_agent_found_card_is_not_hoarding_dragon_link(cards):
    s = setup(cards)
    put(s, "Opposition Agent", "battlefield", "p2")
    source = cast(s, "Hoarding Dragon")
    for _ in range(4):
        d = s.state.rules.decision
        if {o.id for o in d.options} != {"yes", "no"}:
            break
        answer(s, ["yes"])
    cid = choose_named(s, "Sol Ring")
    d = s.state.rules.decision
    assert d.decider == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[cid])
    settle(s)
    assert all(
        not any(oid.startswith(cid + ".") for oid in links) for links in s.state.rules.exiled_with.values()
    )
    cast(s, "Murder", targets=[source.id])
    while s.state.rules.decision and {o.id for o in s.state.rules.decision.options} == {"yes", "no"}:
        answer(s, ["yes"])
    assert s.state.cards[cid].zone == "p1:exile"
    assert s.state.rules.decision is None
    roundtrip(s)


def test_agent_distant_memories_does_not_see_diverted_card(cards):
    s = setup(cards)
    put(s, "Opposition Agent", "battlefield", "p2")
    source = put(s, "Distant Memories", "hand")
    before = len(s.state.zones["p1:hand"])
    mana(s, C=10, U=10)
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    cid = choose_named(s, "Sol Ring")
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[cid])
    settle(s)
    assert s.state.cards[cid].zone == "p1:exile"
    assert len(s.state.zones["p1:hand"]) == before - 1 + 3
    assert s.state.rules.decision is None
    roundtrip(s)


def test_agent_name_search_permissions_cover_hand_and_grave_no_draw(cards):
    s = setup(cards)
    put(s, "Opposition Agent", "battlefield", "p2")
    hand = put(s, "Grizzly Bears", "hand")
    others = [
        c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Grizzly Bears" and c.id != hand.id
    ]
    grave = others[0]
    act(s, "p1", type="move", card_ids=[grave.id], to={"player": "p1", "zone": "graveyard"})
    source = put(s, "Lost Legacy", "hand")
    before = len(s.state.zones["p1:hand"])
    mana(s, C=10, B=10)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=["p1"])
    settle(s)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, name="Grizzly Bears")
    settle(s)
    d = s.state.rules.decision
    assert d.decider == "p2"
    ids = [o.id for o in d.options]
    assert hand.id in ids and grave.id in ids
    act(s, "p2", type="choose", decision_id=d.id, option_ids=ids)
    settle(s)
    assert all(s.state.cards[c].zone == "p1:exile" for c in ids)
    assert all(any(g.card == c and g.player == "p2" for g in s.state.rules.permissions) for c in ids)
    assert len(s.state.zones["p1:hand"]) == before - 2
    roundtrip(s)


def test_distant_all_opponents_decline_draws_three(cards):
    s = setup(cards)
    source = put(s, "Distant Memories", "hand")
    before = len(s.state.zones["p1:hand"])
    cast(s, "Distant Memories")
    cid = choose_named(s, "Sol Ring")
    answer(s, [cid])
    answer(s, ["no"])
    answer(s, ["no"])
    assert s.state.cards[cid].zone == "p1:exile"
    assert len(s.state.zones["p1:hand"]) == before - 1 + 3
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def test_hithlain_draw_then_transfer_right(cards):
    s = setup(cards)
    source = put(s, "Hithlain Rope", "battlefield")
    before = len(s.state.zones["p1:hand"])
    activate(s, source, "{2}")
    assert len(s.state.zones["p1:hand"]) == before + 1
    assert s.state.cards[source.id].controller == "p3"
    roundtrip(s)


def test_two_sanctuaries_find_zero_skip_only_current_turn(cards):
    s = setup(cards)
    first = put(s, "Elfhame Sanctuary", "battlefield")
    other = next(
        c
        for c in s.state.cards.values()
        if c.owner == "p1" and c.name == "Elfhame Sanctuary" and c.id != first.id
    )
    act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "battlefield"})
    to_phase(s, "upkeep", turn=4)
    settle(s)
    before = len(s.state.zones["p1:hand"])
    for _ in range(2):
        search_yes(s)
        answer(s, [])
    to_phase(s, "main1", turn=4)
    assert len(s.state.zones["p1:hand"]) == before
    to_phase(s, "upkeep", turn=7)
    settle(s)
    for _ in range(2):
        answer(s, ["no"])
    to_phase(s, "main1", turn=7)
    assert len(s.state.zones["p1:hand"]) == before + 1
    roundtrip(s)


def test_thawing_blinked_new_land_not_returned_by_old_delay(cards):
    s = setup(cards)
    source = put(s, "Thawing Glaciers", "battlefield")
    ring = put(s, "Sol Ring", "battlefield")
    activate(s, source, "{1}")
    cid = choose_named(s, "Forest")
    answer(s, [cid])
    cast(s, "Ghostly Flicker", targets=[source.id, ring.id], target_counts=[2])
    to_phase(s, "cleanup", turn=1)
    settle(s)
    assert s.state.cards[source.id].zone == "p1:battlefield"
    roundtrip(s)


def test_paid_mastery_decision_retained_on_actual_spell_copy(cards):
    s = setup(cards)
    source = put(s, "Fervent Mastery", "hand")
    copy = put(s, "Twincast", "hand")
    put(s, "Sol Ring", "hand", "p2")
    mana(s, C=30, R=10, U=10)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=source.id, alt_cost=f"{source.id}:0")
    act(s, "p1", type="cast_spell", card_id=copy.id, targets=[source.id])
    settle(s)
    for is_copy in [True, False]:
        d = s.state.rules.decision
        assert d.resume["step"] == "ordered_player"
        record = s.state.rules.payments[d.resume["ctx"]["source_object"]]
        assert record.alternative == "alternative"
        if is_copy:
            assert record.cast_from is None
        answer(s, ["p2"])
        answer(s, [])
        assert s.state.rules.decision.resume["step"] == "search"
        answer(s, [])
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


def test_distant_multi_opponent_choice_new_cold_session(cards):
    from tests.test_rules_qualified_attached_tutors import cold

    s = setup(cards)
    cast(s, "Distant Memories")
    cid = choose_named(s, "Sol Ring")
    answer(s, [cid])
    answer(s, ["no"])
    s = cold(s, cards)
    assert s.state.rules.decision.player == "p3"
    answer(s, ["yes"])
    assert s.state.cards[cid].zone == "p1:hand"
    roundtrip(s)


def test_grim_old_save_unknown_public_name_is_restored(cards):
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_qualified_attached_tutors import cold

    s = setup(cards)
    to_phase(s, "main1", turn=2)
    ring = put(s, "Sol Ring", "hand", "p2")
    mana(s, pid="p2", C=1)
    act(s, "p2", type="cast_spell", card_id=ring.id)
    settle(s)
    note = next(n for n in s.state.rules.turn_log.casts if n.player == "p2")
    note.names = None
    s = cold(s, cards)
    wait_priority(s, "p1")
    before = s.state.players["p2"].life
    cast(s, "Grim Reminder")
    cid = choose_named(s, "Sol Ring")
    answer(s, [cid])
    d = s.state.rules.decision
    assert d.player == "p2" and d.resume["step"] == "name_history_restore"
    s = cold(s, cards)
    act(s, "p2", type="choose", decision_id=s.state.rules.decision.id, name="Sol Ring")
    settle(s)
    assert s.state.players["p2"].life == before - 6
    roundtrip(s)


def test_grim_actual_activation_wrong_phase_and_zone_atomic(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    source = put(s, "Grim Reminder", "graveyard")
    mana(s, B=2)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{B}{B}"))
    assert s.state.model_dump(mode="json") == before
    source = put(s, "Grim Reminder", "hand")
    to_phase(s, "upkeep", turn=4)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=ability(s, source, "{B}{B}"))
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def test_banned_library_search_no_agent_for_doomsday_grave_finds(cards):
    s = setup(cards)
    put(s, "Opposition Agent", "battlefield", "p2")
    put(s, "Stranglehold", "battlefield", "p2")
    a = put(s, "Sol Ring", "graveyard")
    b = put(s, "Memnite", "graveyard")
    cast(s, "Doomsday")
    d = s.state.rules.decision
    assert d.decider is None and {o.id for o in d.options} == {a.id, b.id}
    assert d.min_choices == d.max_choices == 2
    answer(s, [a.id, b.id])
    answer(s, [b.id, a.id])
    assert len(s.state.zones["p1:library"]) == 2
    assert not any(g.player == "p2" and g.card in (a.id, b.id) for g in s.state.rules.permissions)
    roundtrip(s)


def test_doomsday_mindcensor_five_is_top_four_plus_grave(cards):
    from tests.test_rules_refused_look import stack_library, thin_library

    s = setup(cards)
    source = put(s, "Doomsday", "hand")
    grave = put(s, "Sol Ring", "graveyard")
    put(s, "Aven Mindcensor", "battlefield", "p2")
    keep = ["Plains", "Forest", "Island", "Memnite", "Ghalta, Primal Hunger"]
    thin_library(s, keep)
    stack_library(s, keep)
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=source.id)
    settle(s)
    ids = [grave.id, *[choose_named(s, n) for n in keep[:4]]]
    d = s.state.rules.decision
    assert d.min_choices == d.max_choices == 5 and len(d.options) == 5
    answer(s, ids)
    answer(s, ids)
    assert any(c.name == "Ghalta, Primal Hunger" and c.zone == "p1:exile" for c in s.state.cards.values())
    assert len(s.state.zones["p1:library"]) == 5
    roundtrip(s)


def combat_to_hawk_trigger(s, source):
    from tests.test_rules_qualified_attached_tutors import attack_one

    act(s, "p1", type="set_prefs", hold_priority=True)
    attack_one(s, source)
    for _ in range(80):
        d = s.state.rules.decision
        if s.state.rules.stack and not d:
            return
        if d and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d:
            raise AssertionError(d)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("No combat trigger")


def test_hawk_land_qualification_only_at_damage_not_intervening_if(cards):
    s = setup(cards)
    source = put(s, "Cartographer's Hawk", "battlefield")
    land = put(s, "Dryad Arbor", "battlefield", "p2")
    combat_to_hawk_trigger(s, source)
    cast(s, "Pongify", targets=[land.id])
    assert not any(
        c.controller == "p2" and c.zone.endswith(":battlefield") and c.name == "Dryad Arbor"
        for c in s.state.cards.values()
    )
    assert s.state.cards[source.id].zone == "p1:hand"
    search_yes(s)
    cid = choose_named(s, "Plains")
    answer(s, [cid])
    assert s.state.cards[cid].zone == "p1:battlefield"
    roundtrip(s)


def test_hawk_blinked_source_old_trigger_cannot_return_new_object(cards):
    s = setup(cards)
    source = put(s, "Cartographer's Hawk", "battlefield")
    put(s, "Island", "battlefield", "p2")
    combat_to_hawk_trigger(s, source)
    cast(s, "Cloudshift", targets=[source.id])
    assert s.state.cards[source.id].zone == "p1:battlefield"
    assert s.state.rules.decision is None
    roundtrip(s)


def test_doomsday_private_selection_and_order_rest_ws(cards, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = setup(cards)
    cast(s, "Doomsday")
    selected = [choose_named(s, n) for n in ["Plains", "Forest", "Island", "Grizzly Bears", "Sol Ring"]]
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        deck_id = client.post(
            "/api/decks", json={"text": "Commander\n1 Krenko, Mob Boss\nDeck\n20 Forest"}
        ).json()["id"]
        game = client.post(
            "/api/games",
            json={"mode": "lan", "players": [
                {"name": "Alice", "deck_id": deck_id},
                {"name": "Bob", "deck_id": deck_id},
            ]},
        ).json()
        gid = game["game"]["id"]
        bob = client.post("/api/join", json={"code": game["game"]["code"], "name": "Bob"}).json()["token"]
        spec = client.post("/api/join", json={"code": game["game"]["code"], "spectate": True}).json()["token"]
        client.app.state.services.hub.get(gid).game = s
        for stage in range(3):
            if stage == 1:
                answer(s, selected)
                assert s.state.rules.decision.kind == "order"
            elif stage == 2:
                answer(s, list(reversed(selected)))
                assert s.state.zones["p1:library"] == list(reversed(selected))
            for token in [bob, spec]:
                response = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": token})
                assert response.status_code == 200
                with client.websocket_connect(f"/ws/games/{gid}?token={token}") as ws:
                    frame = ws.receive_json()
                    assert frame["type"] == "state"
                for raw in [response.text, json.dumps(frame)]:
                    assert all(cid not in raw for cid in selected)
    roundtrip(s)


def test_roads_go_ever_all_four_chapters_linked_pool_and_post_saga_attack(cards):
    from app.rules.plan import Plan
    from tests.test_rules_qualified_attached_tutors import cold

    data = cards.resolve("Roads Go Ever, Ever On")
    assert coverage.of_card_data(data).level == "FULL"
    s = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    unrelated = put(s, "Island", "exile")
    before = s.state.players["p1"].life
    source = cast(s, "Roads Go Ever, Ever On")
    assert s.state.rules.decision.resume["step"] == "search"
    options = [o.id for o in s.state.rules.decision.options]
    assert options and all(s.state.cards[c].name == "Plains" for c in options)
    selected = options[:2]
    assert len(selected) == 2
    answer(s, selected)
    assert s.state.players["p1"].life == before + 2
    assert all(s.state.cards[c].zone == "p1:exile" for c in selected)
    assert s.state.cards[source.id].counters["lore"] == 1
    to_phase(s, "main1", turn=4)
    settle(s)
    assert {o.id for o in s.state.rules.decision.options} == set(selected)
    answer(s, [selected[0]])
    assert s.state.cards[selected[0]].zone == "p1:hand"
    assert s.state.cards[selected[1]].zone == "p1:exile"
    s = cold(s, cards)
    to_phase(s, "main1", turn=7)
    settle(s)
    if s.state.rules.decision is not None:
        assert {o.id for o in s.state.rules.decision.options} == {selected[1]}
        answer(s, [selected[1]])
    assert all(s.state.cards[c].zone == "p1:hand" for c in selected)
    assert s.state.cards[unrelated.id].zone == "p1:exile"
    to_phase(s, "main1", turn=10)
    settle(s)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    act(s, "p1", type="play_land", card_id=selected[0])
    s = cold(s, cards)
    to_phase(s, "declare_attackers", turn=10)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    settle(s)
    assert bear.id in {o.id for o in s.state.rules.decision.options}
    answer(s, [bear.id])
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).pt == (3, 3)
    assert s.state.cards[source.id].zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("found", [0, 1])
def test_roads_go_ever_optional_count_does_not_return_unlinked_exile(cards, found):
    s = setup(cards)
    unrelated = put(s, "Island", "exile")
    before = s.state.players["p1"].life
    source = cast(s, "Roads Go Ever, Ever On")
    chosen = [o.id for o in s.state.rules.decision.options][:found]
    answer(s, chosen)
    assert s.state.players["p1"].life == before + 2
    for turn in [4, 7]:
        to_phase(s, "main1", turn=turn)
        settle(s)
        if turn == 4 and chosen and s.state.rules.decision is not None:
            assert {o.id for o in s.state.rules.decision.options} == set(chosen)
            answer(s, chosen)
        else:
            assert s.state.rules.decision is None
        assert s.state.cards[unrelated.id].zone == "p1:exile"
    assert s.state.cards[source.id].counters["lore"] == 3
    assert all(s.state.cards[c].zone == "p1:hand" for c in chosen)
    roundtrip(s)
