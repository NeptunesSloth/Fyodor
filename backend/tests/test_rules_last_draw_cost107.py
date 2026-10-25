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

DATA = json.loads((Path(__file__).parent / "fixtures/last_draw_cost107_cards.json").read_text())
NAME = "Jandor's Ring"


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
    ns = [NAME, "Grizzly Bears"] * 3
    s = table(cards, ns, ns, ns)
    to_phase(s, "main1", 4)
    return s


def test_jandors_ring_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def prepare(cards):
    from app.rules import costs as C
    from app.rules.plan import Plan

    s = setup(cards)
    source = take(s, NAME)
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 6})
    act(s, "p1", type="cast_spell", card_id=source.id, sources=[])
    settle(s)
    act(s, "p1", type="draw", count=2)
    drawn = s.state.rules.turn_log.drawn["p1"][-2:]
    ids = [oid.rsplit(".", 1)[0] for oid in drawn]
    wait_priority(s, "p1")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 2})
    ability = next(a for a in Plan.view(s.state, "p1", s.cards).ch(source).abilities if a.kind == "activated")
    cost = C.parse_ability_cost(ability.cost)
    component = next(i for i, c in enumerate(cost.components) if c.kind == C.DISCARD)
    return s, source, ids, ability.index, component


def activate(s, source, cid, index, component):
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=index,
        sources=[],
        cost_choices=[{"component": component, "cards": [cid]}],
    )


def test_actual_group_draw_last_card_pays_and_ring_draws_replacement(cards):
    s, source, ids, index, component = prepare(cards)
    before = len(s.state.zones["p1:hand"])
    activate(s, source, ids[-1], index, component)
    assert s.state.cards[source.id].tapped and s.state.cards[ids[-1]].zone == "p1:graveyard"
    assert s.state.cards[ids[0]].zone == "p1:hand"
    settle(s)
    assert len(s.state.zones["p1:hand"]) == before
    assert s.state.rules.turn_log.drawn["p1"][-1].rsplit(".", 1)[0] not in ids
    roundtrip(s)


def test_previous_drawn_card_is_not_last_even_while_both_remain_in_hand(cards):
    from app.game.errors import ActionError

    s, source, ids, index, component = prepare(cards)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        activate(s, source, ids[0], index, component)
    assert s.state.model_dump(mode="json") == before


@pytest.mark.parametrize("returned", [False, True])
def test_last_card_leaving_hand_never_falls_back_or_accepts_returned_incarnation(cards, returned):
    from app.game.errors import ActionError

    s, source, ids, index, component = prepare(cards)
    act(s, "p1", type="move", card_ids=[ids[-1]], to={"player": "p1", "zone": "graveyard"})
    if returned:
        act(s, "p1", type="move", card_ids=[ids[-1]], to={"player": "p1", "zone": "hand"})
    before = s.state.model_dump(mode="json")
    for cid in ids:
        with pytest.raises(ActionError):
            activate(s, source, cid, index, component)
        assert s.state.model_dump(mode="json") == before


def test_true_cold_last_drawn_discard_uses_exact_hand_object(cards, tmp_path):
    from tests.test_rules_cost_statics101_extra import cold

    s, source, ids, index, component = prepare(cards)
    cold(
        s,
        tmp_path,
        f"act(s,'p1',type='activate_ability',card_id={source.id!r},ability={index},sources=[],cost_choices=[{{'component':{component},'cards':[{ids[-1]!r}]}}])\n"
        f"assert s.state.cards[{ids[-1]!r}].zone=='p1:graveyard' and s.state.cards[{source.id!r}].tapped\n"
        "settle(s);roundtrip(s)",
    )


def test_true_cold_legacy_missing_draw_history_does_not_invent_last_card(cards, tmp_path):
    from tests.test_rules_cost_statics101_extra import cold

    s, source, ids, index, component = prepare(cards)
    cold(
        s,
        tmp_path,
        "from app.game.errors import ActionError\ndoc=s.state.model_dump(mode='json')\ndoc['rules']['turn_log'].pop('drawn')\n"
        "s=GameSession(GameState.model_validate(doc),cards=repo)\nbefore=s.state.model_dump(mode='json')\n"
        "try:\n"
        f" act(s,'p1',type='activate_ability',card_id={source.id!r},ability={index},sources=[],cost_choices=[{{'component':{component},'cards':[{ids[-1]!r}]}}])\n"
        "except ActionError: pass\nelse: raise AssertionError('unknown history was treated as paid')\n"
        "assert s.state.model_dump(mode='json')==before",
    )
