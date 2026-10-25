"""Crashing Wave combines X tapping with an untargeted resolving stun distribution."""

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
from tests.test_rules_waterbend102 import pick, take
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/counter_cost105_cards.json").read_text())
NAME = "Ion Storm"


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


def test_ion_storm_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def prepare(cards, kind="charge"):
    from app.rules.plan import Plan

    s = setup(cards)
    own = take(s, "Island", "battlefield")
    enemy = take(s, "Island", "battlefield", pid="p2")
    act(s, "p1", type="counter", card_ids=[own.id], kind=kind, delta=2)
    if kind in ("charge", "+1/+1"):
        other = "+1/+1" if kind == "charge" else "charge"
        act(s, "p1", type="counter", card_ids=[own.id], kind=other, delta=1)
    act(s, "p1", type="counter", card_ids=[own.id], kind="shield", delta=1)
    act(s, "p2", type="counter", card_ids=[enemy.id], kind="charge", delta=3)
    source = take(s, NAME)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 1})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "R": 1})
    index = next(
        a.index for a in Plan.view(s.state, "p1", s.cards).ch(source).abilities if a.kind == "activated"
    )
    return s, source, own, enemy, index


@pytest.mark.parametrize("kind", ["charge", "+1/+1"])
def test_actual_ion_storm_pays_exact_allowed_counter_kind(cards, kind):
    s, source, own, enemy, index = prepare(cards, kind)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index, targets=["p2"], sources=[])
    d = s.state.rules.decision
    assert d and len(d.options) == 3 and all(o.id.startswith(own.id + ":") for o in d.options)
    from app.rules import cost_payment

    pick(s, [cost_payment._token(own.id, kind, 0)])
    settle(s)
    assert s.state.cards[own.id].counters == {"charge": 1, "+1/+1": 1, "shield": 1}
    assert s.state.cards[enemy.id].counters == {"charge": 3}
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_wrong_counter_kind_cannot_be_substituted_or_partially_pay(cards):
    from app.game.errors import ActionError
    from app.rules import cost_payment

    s, source, own, enemy, index = prepare(cards)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index, targets=["p2"], sources=[])
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        pick(s, [cost_payment._token(own.id, "shield", 0)])
    assert s.state.model_dump(mode="json") == before
    with pytest.raises(ActionError):
        pick(s, [cost_payment._token(enemy.id, "charge", 0)])
    assert s.state.model_dump(mode="json") == before


def test_only_other_counter_types_do_not_allow_activation(cards):
    from app.game.errors import ActionError

    s, source, own, enemy, index = prepare(cards, "oil")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=source.id, ability=index, targets=["p2"], sources=[])
    assert s.state.model_dump(mode="json") == before


def test_true_cold_selected_counter_kind_removes_only_that_counter(cards, tmp_path):
    from tests.test_rules_cost_statics101_extra import cold

    s, source, own, enemy, index = prepare(cards)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=index, targets=["p2"], sources=[])
    from app.rules import cost_payment

    token = cost_payment._token(own.id, "charge", 0)
    cold(
        s,
        tmp_path,
        f"d=s.state.rules.decision\nact(s,d.player,type='choose',decision_id=d.id,option_ids=[{token!r}])\nsettle(s)\n"
        f"assert s.state.cards[{own.id!r}].counters=={{'charge':1,'+1/+1':1,'shield':1}}\n"
        "assert s.state.players['p2'].life==38\nroundtrip(s)",
    )
