"""Canonical token-producing/flying-loss spells and actual graveyard return costs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_conditionals import settle
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_linked_aggregates import cast, ch
from tests.test_rules_linked_return_family import cold_choose
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Summon the School", "Whiteout"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/school_whiteout_collateral_cards.json").read_text())
    ):
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


def setup(cards, name):
    support = [
        "Reverberate",
        "Merfolk of the Pearl Trident",
        "Wind Drake",
        "Snow-Covered Forest",
        "Snow-Covered Island",
        "Forest",
        "Llanowar Elves",
    ]
    s = table(cards, [name, *support], support, support)
    for p in ["p1", "p2", "p3"]:
        act(s, p, type="set_prefs", hold_priority=True)
    return s, put(s, name, "hand")


@pytest.mark.parametrize("name", NAMES)
def test_canonical_graveyard_return_collateral_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_school_actual_spell_copy_tokens_and_four_merfolk_cost_cold(cards, tmp_path):
    s, src = setup(cards, "Summon the School")
    cast(s, src)
    reverberate = put(s, "Reverberate", "hand")
    cast(s, reverberate, targets=[src.id])
    settle(s)
    tokens = [
        c
        for c in s.state.cards.values()
        if c.is_token and c.zone == "p1:battlefield" and "Merfolk" in ch(s, c).subtypes
    ]
    assert len(tokens) == 4
    assert all(
        ch(s, c).pt == (1, 1) and ch(s, c).colors == frozenset({"U"}) and "Wizard" in ch(s, c).subtypes
        for c in tokens
    )
    fresh = put(s, "Merfolk of the Pearl Trident", "hand")
    cast(s, fresh)
    settle(s)
    elf = put(s, "Llanowar Elves", "battlefield")
    opponent = put(s, "Merfolk of the Pearl Trident", "battlefield", "p2")
    assert s.state.cards[src.id].zone == "p1:graveyard"
    for bad in [
        [t.id for t in tokens[:3]],
        [t.id for t in tokens[:3]] + [elf.id],
        [t.id for t in tokens[:3]] + [opponent.id],
    ]:
        wait_priority(s, "p1")
        before = s.state.model_dump_json()
        with pytest.raises(ActionError):
            act(
                s,
                "p1",
                type="activate_ability",
                card_id=src.id,
                ability=1,
                cost_choices=[{"component": 0, "cards": bad}],
            )
        assert s.state.model_dump_json() == before
    act(s, "p1", type="activate_ability", card_id=src.id, ability=1)
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "ability_cost"
    assert {o.id for o in d.options} == {t.id for t in tokens} | {fresh.id}
    chosen = [t.id for t in tokens[:3]] + [fresh.id]
    s = cold_choose(s, cards, tmp_path, chosen)
    assert all(s.state.cards[cid].tapped for cid in chosen)
    assert not s.state.cards[tokens[-1].id].tapped
    assert s.state.cards[src.id].zone == "p1:graveyard"
    settle(s)
    assert s.state.cards[src.id].zone == "p1:hand"
    roundtrip(s)


def test_whiteout_actual_global_flying_loss_expiry_and_snow_cost_cold(cards, tmp_path):
    s, src = setup(cards, "Whiteout")
    a = put(s, "Wind Drake", "battlefield")
    b = put(s, "Wind Drake", "battlefield", "p2")
    snow = put(s, "Snow-Covered Forest", "battlefield")
    other_snow = put(s, "Snow-Covered Island", "battlefield")
    ordinary = put(s, "Forest", "battlefield")
    assert "flying" in ch(s, a).keywords and "flying" in ch(s, b).keywords
    cast(s, src)
    settle(s)
    assert "flying" not in ch(s, a).keywords and "flying" not in ch(s, b).keywords
    wait_priority(s, "p1")
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="activate_ability",
            card_id=src.id,
            ability=1,
            cost_choices=[{"component": 0, "cards": [ordinary.id]}],
        )
    assert s.state.model_dump_json() == before
    act(s, "p1", type="activate_ability", card_id=src.id, ability=1)
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "ability_cost"
    assert {o.id for o in d.options} == {snow.id, other_snow.id}
    s = cold_choose(s, cards, tmp_path, [snow.id])
    assert s.state.cards[snow.id].zone == "p1:graveyard"
    assert s.state.cards[ordinary.id].zone == "p1:battlefield"
    assert s.state.cards[src.id].zone == "p1:graveyard"
    settle(s)
    assert s.state.cards[src.id].zone == "p1:hand"
    to_phase(s, "main1", turn=2)
    assert "flying" in ch(s, s.state.cards[a.id]).keywords and "flying" in ch(s, s.state.cards[b.id]).keywords
    roundtrip(s)
