"""Native optional waterbend declaration, payment and real conditional outcomes."""

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
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import roundtrip, settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_waterbend102 import helpers, pick, take
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/waterbend103_cards.json").read_text())
NAMES = ["Spirit Water Revival", "Ruinous Waterbending", "Katara, Seeking Revenge"]


@pytest.fixture
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(
            c["name"], set_code="w03", number=str(i), **{k: v for k, v in c.items() if k != "name"}
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


def cast(s, name, pool, paid=False):
    c = take(s, name)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana=pool)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=c.id,
        sources=[],
        optional_costs=[c.id + ":waterbend103"] if paid else [],
    )
    return c


@pytest.mark.parametrize("name", NAMES)
def test_optional_waterbend_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("paid", [False, True])
def test_spirit_water_revival_draws_two_or_shuffles_seven_and_no_hand_limit(cards, paid):
    s = setup(cards)
    ids = helpers(s, 6) if paid else []
    grave = take(s, "Island", "graveyard")
    before = len(s.state.zones["p1:hand"])
    source = cast(s, NAMES[0], {"C": 1, "U": 2}, paid)
    if paid:
        pick(s, ids)
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert record.waterbend_paid102 is True if paid else record.waterbend_paid102 is not True
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before + (7 if paid else 2)
    assert source.zone == "p1:exile"
    assert (grave.zone != "p1:graveyard") == paid
    assert ("p1" in s.state.rules.no_max_hand) == paid
    roundtrip(s)


@pytest.mark.parametrize("paid", [False, True])
def test_ruinous_waterbend_death_watch_catches_same_spell_sba(cards, paid):
    s = setup(cards)
    dead = take(s, "Memnite", "battlefield")
    before = s.state.players["p1"].life
    source = cast(s, NAMES[1], {"C": 5 if paid else 1, "B": 2}, paid)
    if paid:
        pick(s, [])
    settle(s)
    assert dead.zone == "p1:graveyard"
    assert s.state.players["p1"].life == before + (1 if paid else 0)
    assert source.zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("paid", [False, True])
def test_katara_declared_waterbend_changes_etb_discard_without_kicker(cards, paid):
    s = setup(cards)
    ids = helpers(s, 2) if paid else []
    before = len(s.state.zones["p1:hand"])
    source = cast(s, NAMES[2], {"C": 3, "U": 1}, paid)
    if paid:
        pick(s, ids)
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before + 1
    record = s.state.rules.payments[s.state.rules.object_id(source.id)]
    assert not record.kicked
    if paid:
        assert s.state.rules.decision is None and record.waterbend_paid102 is True
    else:
        d = s.state.rules.decision
        assert d and "discard" in d.prompt.lower()
        pick(s, [d.options[0].id])
        settle(s)
        assert len(s.state.zones["p1:hand"]) == before
    roundtrip(s)


def test_true_cold_optional_waterbend_choice_resolves_paid_branch(cards, tmp_path):
    from tests.test_rules_cost_statics101_extra import cold

    s = setup(cards)
    ids = helpers(s, 6)
    source = cast(s, NAMES[0], {"C": 1, "U": 2}, True)
    before = len(s.state.zones["p1:hand"])
    cold(
        s,
        tmp_path,
        f"d=s.state.rules.decision\nact(s,d.player,type='choose',decision_id=d.id,option_ids={ids!r})\n"
        f"r=s.state.rules.payments[s.state.rules.object_id({source.id!r})]\n"
        "assert r.waterbend_paid102 is True and not r.kicked\nsettle(s)\n"
        f"assert len(s.state.zones['p1:hand'])=={before + 6}\n"
        "assert 'p1' in s.state.rules.no_max_hand\nroundtrip(s)",
    )


@pytest.mark.parametrize("paid", [False, True])
def test_actual_spell_copy_inherits_waterbend_decision_even_without_cast_origin(cards, paid):
    s = setup(cards)
    ids = helpers(s, 6) if paid else []
    before = len(s.state.zones["p1:hand"])
    before2 = len(s.state.zones["p2:hand"])
    echo = take(s, "Reverberate", pid="p2")
    source = cast(s, NAMES[0], {"C": 1, "U": 2}, paid)
    if paid:
        pick(s, ids)
    assert source.id in s.state.zones["stack"]
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="add_mana", player="p2", mana={"R": 2})
    act(s, "p2", type="cast_spell", card_id=echo.id, targets=[source.id], sources=[])
    settle(s)
    assert s.state.rules.decision is None
    assert len(s.state.zones["p1:hand"]) == before + (7 if paid else 2)
    assert len(s.state.zones["p2:hand"]) == before2 + (7 if paid else 2)
    roundtrip(s)
