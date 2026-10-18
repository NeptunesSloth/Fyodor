"""Review 53 (head review of waves 53A-D, CR 2026-09-25): pins for behaviors the wave changed that its own tests didn't play, with real Oracle text
(tests/fixtures/review53_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import language
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave34b_activated import activate
from tests.wave9c_kit import build, card_named, check, mana, put

DATA = json.loads((Path(__file__).parent / "fixtures" / "review53_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r53", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


# -- 115.1, 601.2c: wave 53A reads "any number of target players' graveyards" as the whole target group (graveyard_of:target:0): every target's graveyard goes
def test_stonespeaker_crystal_exiles_every_target_players_graveyard(cards):
    s = build(cards, ["Stonespeaker Crystal", "Grizzly Bears"], ["Lightning Bolt"])
    crystal = put(s, "Stonespeaker Crystal")
    for pid, name in (("p1", "Grizzly Bears"), ("p2", "Lightning Bolt")):
        act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"zone": "graveyard"})
    mana(s, "p1", C=2)
    activate(s, "p1", crystal, "Exile any number", targets=["p1", "p2"], target_counts=[2])
    settle(s)
    assert card_named(s, "Grizzly Bears").zone == "p1:exile" and card_named(s, "Lightning Bolt", "p2").zone == "p2:exile"
    check(s)


# -- review 53 -- 115.1: an amount naming two different "target …" is not one target: refused (wave 53C took every target selector out of the amount)
def test_an_amount_with_two_different_targets_is_not_read():
    with pytest.raises(language._Fail):
        language._value_target([{"target_sel": "sel:a"}, {"target_sel": "sel:b"}], None)
    assert language._value_target([{"target_sel": "sel:a"}, {"target_sel": "sel:a"}], None) == "sel:a"


def test_a_game_saved_inside_an_old_pile_split_still_resumes():
    """Wave 53D moved face-up piles (700.3: Fact or Fiction) to pile_groups; a game saved with a pending "piles" effect or a
    "piles_opponent" / "piles_split" / "piles_pick" question answers through the old routines (piles_legacy)."""
    from app.rules import effects, engine, piles_legacy

    assert effects.PRIMITIVES["piles"] is piles_legacy.piles
    assert engine.RESUME["piles_opponent"] is piles_legacy.resume_opponent
    assert engine.RESUME["piles_split"] is piles_legacy.resume_split
    assert engine.RESUME["piles_pick"] is piles_legacy.resume_pick
