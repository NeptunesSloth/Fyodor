"""Linked exile abilities grant native exact-object play permissions."""

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
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_conditionals import settle, until
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_linked_aggregates import cast, choose
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAMES = ["Smirking Spelljacker"]


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(
        json.loads((Path(__file__).parent / "fixtures/smirking_spelljacker_cards.json").read_text())
    ):
        base[c["name"]] = card(
            c["name"], set_code="lor", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_canonical_smirk_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Smirking Spelljacker")).level == "FULL"


def imprison(cards, name="Lightning Bolt", targets=None):
    support = [
        "Lightning Bolt",
        "Cloudshift",
        "Counterspell",
        "Unsummon",
        "Pull from Eternity",
        "Naturalize",
        "Grizzly Bears",
        "Memnite",
    ]
    s = table(cards, ["Smirking Spelljacker", *support], support, support)
    for pid in ["p1", "p2", "p3"]:
        act(s, pid, type="set_prefs", hold_priority=True)
    src = put(s, "Smirking Spelljacker", "hand")
    spell = put(s, name, "hand", "p2")
    mana(s, "p2", W=20, U=20, B=20, R=20, G=20, C=20)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=spell.id, targets=targets if targets is not None else ["p3"])
    cast(s, src)
    choose(s, [spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone == "p2:exile"
    assert s.state.players["p3"].life == 40
    assert s.state.rules.exiled_with[s.state.rules.object_id(src.id)] == [s.state.rules.object_id(spell.id)]
    return s, src, spell


def attack(s, src):
    to_phase(s, "declare_attackers", turn=4)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": src.id, "target": "p2"}])


@pytest.mark.parametrize("accept", [False, True])
def test_actual_exile_then_attack_cast_or_decline_cold(cards, tmp_path, accept):
    from app.game.errors import ActionError
    from app.game.visibility import SPECTATOR, can_see
    from tests.test_rules_linked_return_family import cold_choose

    s, src, spell = imprison(cards)
    for viewer in ["p1", "p2", "p3", SPECTATOR]:
        assert can_see(s.state, s.state.cards[spell.id], viewer)
    attack(s, src)
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1"
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes"])
    assert s.state.model_dump_json() == before
    # Generic linked free-cast first selects the card, then its legal spell face.
    selected = next((o.id for o in d.options if o.card_id == spell.id or o.id == spell.id), None)
    if selected is not None:
        s = cold_choose(s, cards, tmp_path, [selected] if accept else [])
    else:
        s = cold_choose(s, cards, tmp_path, ["yes" if accept else "no"])
    settle(s)
    assert s.state.cards[spell.id].zone == ("p2:graveyard" if accept else "p2:exile")
    roundtrip(s)


def test_pending_attack_survives_source_return_to_hand(cards):
    s, src, spell = imprison(cards)
    attack(s, src)
    removal = put(s, "Unsummon", "hand", "p2")
    mana(s, "p2", U=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=removal.id, targets=[src.id])
    settle(s)
    assert s.state.cards[src.id].zone == "p1:hand"
    assert s.state.cards[spell.id].zone == "p2:graveyard"
    assert s.state.rules.turn_log.casts[-1].player == "p1"
    roundtrip(s)


def test_intervening_if_rechecks_exact_exile_at_resolution(cards):
    s, src, spell = imprison(cards)
    attack(s, src)
    removal = put(s, "Pull from Eternity", "hand", "p2")
    mana(s, "p2", W=1)
    wait_priority(s, "p2")
    act(s, "p2", type="cast_spell", card_id=removal.id, targets=[spell.id])
    settle(s)
    assert s.state.cards[spell.id].zone == "p2:graveyard"
    assert not s.state.rules.free_casts
    assert s.state.rules.turn_log.casts[-1].player == "p2"
    roundtrip(s)


def test_source_blink_uses_new_empty_link_namespace(cards):
    s, src, spell = imprison(cards)
    original = s.state.rules.object_id(src.id)
    blink = put(s, "Cloudshift", "hand")
    cast(s, blink, targets=[src.id])
    settle(s)
    assert s.state.rules.object_id(src.id) != original
    assert s.state.cards[spell.id].zone == "p2:exile"
    attack(s, src)
    settle(s)
    assert s.state.cards[spell.id].zone == "p2:exile"
    assert not s.state.rules.free_casts
    roundtrip(s)


def test_exiled_card_has_no_cast_permission_before_attack_trigger(cards):
    from app.game.errors import ActionError

    s, src, spell = imprison(cards)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p3"], free=True)
    assert s.state.model_dump_json() == before
    assert s.state.cards[spell.id].zone == "p2:exile"
