"""Actual waterbend alternate payments preserve colored costs, ceilings and X."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/waterbend102_cards.json").read_text())
NAMES = ["Benevolent River Spirit", "Water Whip", "Waterbender's Restoration", "Katara, Water Tribe's Hope"]


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="w02", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    ns = [c["name"] for c in DATA] * 7
    s = table(cards, ns, ns, ns)
    to_phase(s, "main1", 4)
    return s


def take(s, name, zone="hand", pid="p1"):
    c = next(
        c
        for c in s.state.cards.values()
        if c.owner == pid and c.name == name and c.zone in [pid + ":library", pid + ":hand"]
    )
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})
    return s.state.cards[c.id]


def helpers(s, n=5):
    return [take(s, "Memnite", "battlefield").id for _ in range(n)]


def pick(s, ids):
    d = s.state.rules.decision
    assert d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def cast(s, name, pool, **kwargs):
    c = take(s, name)
    wait_priority(s, "p1")
    if pool:
        act(s, "p1", type="add_mana", player="p1", mana=pool)
    act(s, "p1", type="cast_spell", card_id=c.id, sources=[], **kwargs)
    return c


@pytest.mark.parametrize("name", NAMES)
def test_waterbend_candidates_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_actual_water_whip_taps_five_and_pays_both_printed_blue_mana(cards):
    s = setup(cards)
    ids = helpers(s)
    source = cast(s, "Water Whip", {"U": 2}, target_counts=[0])
    assert s.state.rules.decision.kind == "choose_cards"
    assert all(not s.state.cards[c].tapped for c in ids)
    pick(s, ids)
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.total_cost == "{5}{U}{U}" and record.mana_spent == {"U": 2}
    assert len(record.contributions) == 5 and {c.kind for c in record.contributions} == {"waterbend"}
    assert set(record.tapped_for_cost) == set(ids) and record.waterbend_paid102 is True
    assert all(s.state.cards[c].tapped for c in ids)
    settle(s)
    assert source.zone == "p1:graveyard"
    roundtrip(s)


def test_actual_waterbend_mana_only_is_still_a_paid_waterbend(cards):
    s = setup(cards)
    source = cast(s, "Water Whip", {"C": 5, "U": 2}, target_counts=[0])
    assert s.state.rules.decision is None
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert (
        record.mana_spent == {"C": 5, "U": 2}
        and record.waterbend_paid102 is True
        and not record.contributions
    )
    settle(s)
    roundtrip(s)


def test_katara_announced_x_can_be_fully_paid_by_tapping_newly_entered_creatures(cards):
    s = setup(cards)
    katara = cast(s, NAMES[3], {"C": 2, "W": 1, "U": 2})
    settle(s)
    ids = helpers(s, 3)
    wait_priority(s, "p1")
    index = next(
        a.index for a in Plan.view(s.state, "p1", s.cards).ch(katara).abilities if a.kind == "activated"
    )
    act(s, "p1", type="activate_ability", card_id=katara.id, ability=index, x_value=3, sources=[])
    pick(s, ids)
    assert s.state.rules.decision is None and all(s.state.cards[c].tapped for c in ids)
    settle(s)
    assert all(Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c]).pt == (3, 3) for c in ids)
    roundtrip(s)


def test_waterbend_cannot_overpay_after_final_activation_reduction(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    katara = cast(s, NAMES[3], {"C": 2, "W": 1, "U": 2})
    settle(s)
    take(s, "Zirda, the Dawnwaker", "battlefield")
    ids = helpers(s, 3)
    wait_priority(s, "p1")
    index = next(
        a.index for a in Plan.view(s.state, "p1", s.cards).ch(katara).abilities if a.kind == "activated"
    )
    act(s, "p1", type="activate_ability", card_id=katara.id, ability=index, x_value=3, sources=[])
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        pick(s, ids)
    assert before == s.state.model_dump(mode="json") and all(not s.state.cards[c].tapped for c in ids)
    pick(s, ids[:1])
    settle(s)
    assert s.state.cards[ids[0]].tapped and all(not s.state.cards[c].tapped for c in ids[1:])
    roundtrip(s)


def test_variable_spell_blinks_exact_x_and_returns_next_end_step(cards):
    s = setup(cards)
    ids = helpers(s, 2)
    source = cast(s, "Waterbender's Restoration", {"U": 2}, x_value=2, targets=ids, target_counts=[2])
    pick(s, ids)
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.total_cost == "{2}{U}{U}" and record.x == 2
    settle(s)
    assert all(s.state.cards[cid].zone == "p1:exile" for cid in ids)
    to_phase(s, "end", s.state.turn.number)
    settle(s)
    assert all(s.state.cards[cid].zone == "p1:battlefield" for cid in ids)
    assert source.zone == "p1:graveyard"
    roundtrip(s)


def test_spell_taps_do_not_pay_generic_tax_beyond_waterbend_amount(cards):
    from app.game.errors import ActionError

    s = setup(cards)
    take(s, "Sphere of Resistance", "battlefield")
    ids = helpers(s, 6)
    cast(s, "Water Whip", {"U": 2}, target_counts=[0])
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        pick(s, ids)
    assert s.state.model_dump(mode="json") == before
    with pytest.raises(ActionError):
        pick(s, ids[:5])
    assert s.state.model_dump(mode="json") == before
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    pick(s, ids[:5])
    assert all(s.state.cards[c].tapped for c in ids[:5]) and not s.state.cards[ids[5]].tapped
    settle(s)
    roundtrip(s)


def test_true_cold_paused_waterbend_choice_preserves_receipt(cards, tmp_path):
    from tests.test_rules_cost_statics101_extra import cold

    s = setup(cards)
    ids = helpers(s)
    source = cast(s, "Water Whip", {"U": 2}, target_counts=[0])
    cold(
        s,
        tmp_path,
        f"d=s.state.rules.decision\nact(s,d.player,type='choose',decision_id=d.id,option_ids={ids!r})\n"
        f"r=s.state.rules.payments[s.state.rules.object_id({source.id!r})]\n"
        "assert r.waterbend_paid102 and r.mana_spent=={'U':2} and len(r.contributions)==5\n"
        "settle(s);roundtrip(s)",
    )


def test_benevolent_spirit_cast_uses_waterbend_and_resolves_native_scry(cards):
    s = setup(cards)
    ids = helpers(s)
    source = cast(s, "Benevolent River Spirit", {"U": 2})
    pick(s, ids)
    settle(s)
    d = s.state.rules.decision
    assert source.zone == "p1:battlefield"
    assert d and "scry" in d.prompt.lower()
    assert Plan.view(s.state, "p1", s.cards).ch(source).power == "4"
