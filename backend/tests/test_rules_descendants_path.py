"""Descendants' Path: card eligibility, native free casting, and exact-object cleanup."""

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
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = "Descendants' Path"


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures/descendants_path_cards.json").read_text())):
        base[c["name"]] = card(
            c["name"], set_code="dsp", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, top="Grizzly Bears", matching="Universal Automaton", enemy=()):
    s = table(cards, [NAME, top, *([matching] if matching else [])], enemy, [])
    to_phase(s, "main1", turn=1)
    source = put(s, NAME, "battlefield")
    held = put(s, matching, "battlefield") if matching else None
    candidate = put(s, top, "hand")
    act(s, "p1", type="move", card_ids=[candidate.id], to={"player": "p1", "zone": "library"}, position="top")
    to_phase(s, "upkeep", turn=4)
    return s, source, held, candidate


def offer(s):
    until(
        s,
        lambda s: (
            s.state.rules.decision is not None and s.state.rules.decision.resume.get("step") == "suspend_cast"
        ),
    )
    d = s.state.rules.decision
    roundtrip(s)
    return d


def answer(s, option):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])
    settle(s)


def test_descendants_path_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


@pytest.mark.parametrize("accept", [False, True])
def test_matching_card_is_cast_or_bottomed_during_original_resolution(cards, accept):
    s, _, _, candidate = setup(cards)
    d = offer(s)
    assert d.resume["card"] == candidate.id
    answer(s, "yes" if accept else "no")
    assert s.state.cards[candidate.id].zone == ("p1:battlefield" if accept else "p1:library")
    if not accept:
        assert s.state.zones["p1:library"][-1] == candidate.id
    assert s.state.rules.free_cast_then is None
    roundtrip(s)


@pytest.mark.parametrize(
    "top,matching",
    [
        ("Elvish Mystic", "Grizzly Bears"),
        ("Tormenting Voice", "Universal Automaton"),
        ("Grizzly Bears", None),
        ("Dryad Arbor", "Universal Automaton"),
    ],
)
def test_nonmatching_noncreature_or_uncastable_land_card_goes_bottom(cards, top, matching):
    s, _, _, candidate = setup(cards, top=top, matching=matching)
    settle(s)
    assert s.state.zones["p1:library"][-1] == candidate.id
    assert s.state.rules.decision is None
    roundtrip(s)


def test_source_departure_does_not_prevent_casting(cards):
    s, source, _, candidate = setup(cards)
    act(s, "p1", type="move", card_ids=[source.id], to={"player": "p1", "zone": "graveyard"})
    offer(s)
    answer(s, "yes")
    assert s.state.cards[candidate.id].zone == "p1:battlefield"
    roundtrip(s)


def test_matching_creature_removed_before_resolution_changes_match(cards):
    s, _, held, candidate = setup(cards)
    act(s, "p1", type="move", card_ids=[held.id], to={"player": "p1", "zone": "graveyard"})
    settle(s)
    assert s.state.zones["p1:library"][-1] == candidate.id
    roundtrip(s)


def test_grist_uses_off_battlefield_insect_creature_characteristics(cards):
    s, _, _, candidate = setup(cards, top="Grist, the Hunger Tide")
    offer(s)
    answer(s, "yes")
    assert s.state.cards[candidate.id].zone == "p1:battlefield"
    roundtrip(s)


def test_adventure_target_cancellation_finishes_bottom_cleanup(cards):
    s, _, _, candidate = setup(cards, top="Bonecrusher Giant // Stomp")
    d = offer(s)
    assert any(o.id == "yes@1" for o in d.options)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes@1"])
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "cast_target"
    roundtrip(s)
    answer(s, "cancel")
    assert s.state.zones["p1:library"][-1] == candidate.id
    assert not s.state.rules.free_casts and s.state.rules.free_cast_then is None
    roundtrip(s)




def test_trigger_keeps_original_controller_after_source_changes_control(cards):
    s, source, _, candidate = setup(cards)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    offer(s)
    answer(s, 'yes')
    assert s.state.cards[candidate.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_changeling_on_revealed_card_shares_type(cards):
    s, _, _, candidate = setup(cards, top='Universal Automaton', matching='Grizzly Bears')
    offer(s)
    answer(s, 'yes')
    assert s.state.cards[candidate.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_live_maskwood_nexus_changes_card_and_creature_types(cards):
    s = table(cards, [NAME, 'Elvish Mystic', 'Grizzly Bears', 'Maskwood Nexus'], [], [])
    to_phase(s, 'main1', turn=1)
    put(s, NAME, 'battlefield')
    put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Maskwood Nexus', 'battlefield')
    candidate = put(s, 'Elvish Mystic', 'hand')
    act(s, 'p1', type='move', card_ids=[candidate.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    to_phase(s, 'upkeep', turn=4)
    offer(s)
    answer(s, 'yes')
    assert s.state.cards[candidate.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_qualifying_creature_card_may_cast_noncreature_mdfc_face(cards):
    s, _, _, candidate = setup(cards, top='Valki, God of Lies // Tibalt, Cosmic Impostor')
    d = offer(s)
    assert any(o.id == 'yes@1' for o in d.options)
    answer(s, 'yes@1')
    assert s.state.cards[candidate.id].zone == 'p1:battlefield'
    assert s.state.cards[candidate.id].face == 1
    roundtrip(s)


def test_unpayable_additional_cost_is_bottomed(cards):
    s, _, _, candidate = setup(cards, top='Skaab Ruinator')
    settle(s)
    assert s.state.zones['p1:library'][-1] == candidate.id
    assert s.state.rules.decision is None
    roundtrip(s)


def test_free_x_zero_creature_dies_without_being_bottomed(cards):
    s, _, _, candidate = setup(cards, top='Endless One')
    offer(s)
    answer(s, 'yes')
    assert s.state.cards[candidate.id].zone == 'p1:graveyard'
    assert candidate.id not in s.state.zones['p1:library']
    roundtrip(s)


def test_empty_library_does_not_draw_or_lose(cards):
    s = table(cards, [NAME], [], [])
    to_phase(s, 'main1', turn=1)
    put(s, NAME, 'battlefield')
    act(s, 'p1', type='move', card_ids=list(s.state.zones['p1:library']), to={'player': 'p1', 'zone': 'graveyard'})
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    assert 'p1' not in s.state.rules.lost
    assert not s.state.rules.decision
    roundtrip(s)


def test_later_counterspell_puts_cast_card_in_graveyard_without_bottoming(cards):
    from tests.test_rules_bandmate_references import mana, wait_priority

    s, _, _, candidate = setup(cards, enemy=['Essence Scatter'])
    d = offer(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    assert s.state.cards[candidate.id].zone == 'stack'
    assert s.state.rules.free_cast_then is None
    assert len(s.state.zones['stack']) == 1
    counter = put(s, 'Essence Scatter', 'hand', 'p2')
    wait_priority(s, 'p2')
    mana(s, pid='p2', C=1, U=1)
    act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[candidate.id])
    settle(s)
    assert s.state.cards[candidate.id].zone == 'p1:graveyard'
    assert candidate.id not in s.state.zones['p1:library']
    roundtrip(s)


@pytest.mark.parametrize('cancel', [True, False])
def test_free_cast_still_requires_additional_sacrifice_or_bottoms_if_cancelled(cards, cancel):
    s = table(cards, [NAME, 'Demon of Catastrophes', 'Grinning Demon', 'Grizzly Bears'], [], [])
    to_phase(s, 'main1', turn=1)
    put(s, NAME, 'battlefield')
    held = put(s, 'Grinning Demon', 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    candidate = put(s, 'Demon of Catastrophes', 'hand')
    act(s, 'p1', type='move', card_ids=[candidate.id], to={'player': 'p1', 'zone': 'library'}, position='top')
    to_phase(s, 'upkeep', turn=4)
    d = offer(s)
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['yes'])
    d = s.state.rules.decision
    assert d is not None and any(o.card_id == bear.id for o in d.options)
    roundtrip(s)
    if cancel:
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
        settle(s)
    else:
        answer(s, bear.id)
    assert s.state.cards[held.id].zone == 'p1:battlefield'
    assert s.state.cards[bear.id].zone == ('p1:battlefield' if cancel else 'p1:graveyard')
    assert s.state.cards[candidate.id].zone == ('p1:library' if cancel else 'p1:battlefield')
    if cancel:
        assert s.state.zones['p1:library'][-1] == candidate.id
    assert s.state.rules.free_cast_then is None
    roundtrip(s)
