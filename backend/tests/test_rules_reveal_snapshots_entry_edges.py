"""Library reveal instructions retain their consequences when native entry is prohibited."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_reveal_snapshots import DATA, mana
from tests.test_rules_reveal_snapshots import cards as root_cards  # noqa: F401
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase


@pytest.fixture()
def cards(root_cards, settings):  # noqa: F811
    # Extend a separate database; the parent fixture and its metadata remain untouched.
    base = {c["name"]: c for c in fixture_cards()}
    extra = json.loads(
        (Path(__file__).parent / "fixtures/reveal_snapshots_entry_edges_cards.json").read_text()
    )
    for i, c in enumerate([*DATA, *extra]):
        base[c["name"]] = card(
            c["name"], set_code="rve34", number=str(i), **{k: v for k, v in c.items() if k != "name"}
        )
    path = settings.cards_db_path.with_name("reveal-entry-edges.sqlite")
    build_database(base.values(), path)
    repo = CardRepository(path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_dissector_cage_blocks_artifact_creature_but_source_sacrificed(cards):
    s = table(cards, ["Thought Dissector", "Grafdigger's Cage"], ["Ornithopter"])
    source = put(s, "Thought Dissector", "battlefield")
    put(s, "Grafdigger's Cage", "battlefield")
    found = put(s, "Ornithopter", "library", "p2")
    mana(s)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0, x_value=2, targets=["p2"])
    settle(s)
    roundtrip(s)
    assert s.state.cards[found.id].zone == "p2:library"
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert not s.state.cards[found.id].revealed_to


def test_raid_cage_blocks_entry_without_haste_or_sacrifice_watch(cards):
    s = table(cards, ["Impromptu Raid", "Grafdigger's Cage", "Grizzly Bears"])
    source = put(s, "Impromptu Raid", "battlefield")
    put(s, "Grafdigger's Cage", "battlefield")
    found = put(s, "Grizzly Bears", "library")
    before = [d.model_dump(mode="json") for d in s.state.rules.delayed]
    mana(s)
    act(s, "p1", type="activate_ability", card_id=source.id, ability=0)
    settle(s)
    roundtrip(s)
    assert s.state.cards[found.id].zone == "p1:library"
    assert "haste" not in Plan(s.state, "p1", cards, None).ch(s.state.cards[found.id]).keywords
    assert [d.model_dump(mode="json") for d in s.state.rules.delayed] == before
    to_phase(s, "end")
    settle(s)
    roundtrip(s)
    assert s.state.cards[found.id].zone == "p1:library"


@pytest.mark.parametrize("cage", [False, True])
def test_preserve_grist_is_creature_in_library_and_cage_blocks_batch(cards, cage):
    s = table(
        cards,
        ["Game Preserve", "Grafdigger's Cage", "Grist, the Hunger Tide"],
        ["Grizzly Bears"],
        ["Storm Crow"],
    )
    put(s, "Game Preserve", "battlefield")
    if cage:
        put(s, "Grafdigger's Cage", "battlefield")
    to_phase(s, "upkeep", turn=4)
    grist = put(s, "Grist, the Hunger Tide", "library")
    bear = put(s, "Grizzly Bears", "library", "p2")
    crow = put(s, "Storm Crow", "library", "p3")
    settle(s)
    roundtrip(s)
    for c in [grist, bear, crow]:
        assert s.state.cards[c.id].zone == c.owner + (":library" if cage else ":battlefield")
    if not cage:
        p = Plan(s.state, "p1", cards, None)
        assert "Creature" not in p.ch(s.state.cards[grist.id]).types
