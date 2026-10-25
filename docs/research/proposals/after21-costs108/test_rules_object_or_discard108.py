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

DATA = json.loads((Path(__file__).parent / "fixtures/object_or_discard108_cards.json").read_text())
NAME = "Bullseye, Death Dealer"


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


def test_bullseye_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def prepare(cards, tax=False, mature=True, etb_pay=False):
    from app.rules.plan import Plan
    from tests.test_rules_waterbend102 import pick

    s = setup(cards)
    artifact = take(s, "Memnite", "battlefield")
    body = take(s, "Grizzly Bears", "battlefield")
    hand = take(s, "Grizzly Bears")
    land = take(s, "Forest")
    source = take(s, NAME)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2, "R": 1})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    assert s.state.rules.decision
    pick(s, ["pay:0" if etb_pay else "decline"])
    settle(s)
    if etb_pay:
        assert s.state.rules.decision
        pick(s, ["p2"])
        settle(s)
    if mature:
        to_phase(s, "main1", 7)
    if tax:
        take(s, "Suppression Field", "battlefield")
    wait_priority(s, "p1")
    index = next(
        a.index for a in Plan.view(s.state, "p1", s.cards).ch(source).abilities if a.kind == "activated"
    )
    return s, source, artifact, hand, land, body, index


def activate(s, source, index, side=None, payment=None):
    from app.rules import costs

    choices = [{"component": costs.EITHER_SLOT, "cards": [f"either:{side}"]}] if side is not None else []
    if payment is not None:
        choices.append({"component": 2, "cards": [payment]})
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=index,
        targets=["p2"],
        sources=[],
        cost_choices=choices,
    )


@pytest.mark.parametrize("tax", [False, True])
@pytest.mark.parametrize("side", [0, 1])
def test_bullseye_alternative_keeps_common_mana_tap_and_chosen_verb(cards, side, tax):
    from tests.game_helpers import mana_pool

    s, source, artifact, hand, land, body, index = prepare(cards, tax)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 5 if tax else 3})
    activate(s, source, index, side, artifact.id if side == 0 else hand.id)
    assert s.state.cards[source.id].tapped and not mana_pool(s, "p1")
    assert s.state.cards[artifact.id].zone == ("p1:graveyard" if side == 0 else "p1:battlefield")
    assert s.state.cards[hand.id].zone == ("p1:hand" if side == 0 else "p1:graveyard")
    settle(s)
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_alternative_verbs_cannot_use_land_discard_or_nonartifact_sacrifice(cards):
    from app.game.errors import ActionError

    s, source, artifact, hand, land, body, index = prepare(cards)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    before = s.state.model_dump(mode="json")
    for side, payment in [(0, body.id), (1, land.id)]:
        with pytest.raises(ActionError):
            activate(s, source, index, side, payment)
        assert s.state.model_dump(mode="json") == before


def test_both_alternatives_retain_tap_summoning_sickness_cost(cards):
    from app.game.errors import ActionError

    s, source, artifact, hand, land, body, index = prepare(cards, mature=False)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    before = s.state.model_dump(mode="json")
    for side, payment in [(0, artifact.id), (1, hand.id)]:
        with pytest.raises(ActionError):
            activate(s, source, index, side, payment)
        assert s.state.model_dump(mode="json") == before


def test_existing_optional_etb_alternative_remains_native_and_reflexive(cards):
    s, source, artifact, hand, land, body, index = prepare(cards, etb_pay=True)
    assert s.state.cards[artifact.id].zone == "p1:graveyard"
    assert s.state.cards[hand.id].zone == "p1:hand" and s.state.players["p2"].life == 38
    roundtrip(s)


def test_true_cold_object_cost_branch_resumes_same_mana_tap_and_sacrifice(cards, tmp_path):
    from tests.test_rules_cost_statics101_extra import cold

    s, source, artifact, hand, land, body, index = prepare(cards)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    activate(s, source, index)
    assert s.state.rules.decision
    cold(
        s,
        tmp_path,
        "d=s.state.rules.decision\nact(s,'p1',type='choose',decision_id=d.id,option_ids=['either:0'])\n"
        f"assert s.state.cards[{artifact.id!r}].zone=='p1:graveyard' and s.state.cards[{source.id!r}].tapped\n"
        "assert not mana_pool(s,'p1')\nsettle(s)\nassert s.state.players['p2'].life==38\nroundtrip(s)",
    )
