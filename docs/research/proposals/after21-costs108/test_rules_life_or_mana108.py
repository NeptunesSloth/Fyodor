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
from tests.test_rules_waterbend102 import take
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / "fixtures/life_or_mana108_cards.json").read_text())
NAME = "Tidal Control"


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
    ns = [c["name"] for c in DATA] * 3
    s = table(cards, ns, ns, ns)
    to_phase(s, "main1", 4)
    return s


def test_tidal_control_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def prepare(cards, tax=False, spell_name="Shock"):
    from app.rules.plan import Plan

    s = setup(cards)
    source = take(s, NAME)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 2})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    if tax:
        take(s, "Suppression Field", "battlefield")
    spell = take(s, spell_name, pid="p2")
    wait_priority(s, "p2")
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1} if spell_name == "Shock" else {"U": 1})
    act(
        s,
        "p2",
        type="cast_spell",
        card_id=spell.id,
        sources=[],
        targets=["p1"] if spell_name == "Shock" else [],
    )
    assert s.state.rules.priority == "p3"
    index = next(
        a.index for a in Plan.view(s.state, "p3", s.cards).ch(source).abilities if a.kind == "activated"
    )
    return s, source, spell, index


def activate(s, source, spell, index, side=None):
    from app.rules import costs

    extra = (
        {"cost_choices": [{"component": costs.EITHER_SLOT, "cards": [f"either:{side}"]}]}
        if side is not None
        else {}
    )
    act(
        s,
        "p3",
        type="activate_ability",
        card_id=source.id,
        ability=index,
        targets=[spell.id],
        sources=[],
        **extra,
    )


@pytest.mark.parametrize("tax", [False, True])
@pytest.mark.parametrize("side", [0, 1])
def test_any_player_pays_own_chosen_life_or_mana_plus_independent_tax(cards, side, tax):
    from tests.game_helpers import mana_pool

    s, source, spell, index = prepare(cards, tax)
    due = (2 if tax else 0) + (2 if side == 1 else 0)
    if due:
        act(s, "p3", type="add_mana", player="p3", mana={"C": due})
    activate(s, source, spell, index, side)
    assert s.state.players["p3"].life == (38 if side == 0 else 40)
    assert not mana_pool(s, "p3") and s.state.players["p1"].life == 40
    settle(s)
    assert s.state.cards[spell.id].zone == "p2:graveyard" and s.state.players["p1"].life == 40
    roundtrip(s)


def test_ineligible_spell_target_never_pays_either_cost(cards):
    from app.game.errors import ActionError

    s, source, spell, index = prepare(cards, spell_name="Opt")
    act(s, "p3", type="add_mana", player="p3", mana={"C": 2})
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        activate(s, source, spell, index, 1)
    assert s.state.model_dump(mode="json") == before


def test_unpayable_life_branch_cannot_activate_or_partially_pay(cards):
    from app.game.errors import ActionError

    s, source, spell, index = prepare(cards)
    act(s, "p3", type="set_life", player="p3", value=1)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        activate(s, source, spell, index, 0)
    assert s.state.model_dump(mode="json") == before


def test_true_cold_cost_branch_prompt_preserves_foreign_actor_and_mana(cards, tmp_path):
    from tests.test_rules_cost_statics101_extra import cold

    s, source, spell, index = prepare(cards)
    act(s, "p3", type="add_mana", player="p3", mana={"C": 2})
    activate(s, source, spell, index)
    assert s.state.rules.decision and s.state.rules.decision.player == "p3"
    cold(
        s,
        tmp_path,
        "d=s.state.rules.decision\nact(s,'p3',type='choose',decision_id=d.id,option_ids=['either:0'])\n"
        "assert s.state.players['p3'].life==38 and mana_pool(s,'p3')=={'C':2}\nsettle(s)\n"
        f"assert s.state.cards[{spell.id!r}].zone=='p2:graveyard' and s.state.players['p1'].life==40\nroundtrip(s)",
    )
