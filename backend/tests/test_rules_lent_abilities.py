"""Abilities one permanent borrows from another (Marvin, Murderous Mimic: "has all activated abilities of creatures you control …"; Koh, the Face
Stealer: "all activated and triggered abilities of the last chosen card"; CR 113.10, 613.1f). Real Oracle text (tests/fixtures/lent_abilities_cards.json,
from data/cards.sqlite).

* 607.5: a lent ability that refers to cards "exiled with" its object is linked only to an exiling ability lent by the same effect. Marvin lends
  Quintorius, Loremaster's activated ability alone, so on Marvin it refers to no card (nothing is exiled with Marvin by a linked ability): it has no
  legal target. The same text on an object with neither its exiling half nor a lending path is refused (manual), never an engine error.

Each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave100f_attached import to_phase
from tests.wave9c_kit import build, mana, put

DATA = json.loads((Path(__file__).parent / "fixtures" / "lent_abilities_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="lab", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
MARVIN = "Marvin, Murderous Mimic"
QUINTORIUS = "Quintorius, Loremaster"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump() == s.state.model_dump()


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def lent(s, c, start):
    """Marvin's (``c``'s) borrowed ability whose text starts with ``start``."""
    return next(a for a in chars(s, c).abilities if a.borrowed_origin and a.text.startswith(start))


def alice_next_turn(s):
    """Alice's next main phase: what she controls has been hers since her turn began ({T} abilities, 302.6)."""
    to_phase(s, "main1", turn=s.state.turn.number + 2)


def test_marvin_borrows_quintorius_ability_linked_to_nothing(cards):
    s = build(cards, [QUINTORIUS, MARVIN, "Kami of Ancient Law"])
    put(s, QUINTORIUS)
    marvin = put(s, MARVIN)
    put(s, "Kami of Ancient Law")  # (a Spirit to sacrifice)
    alice_next_turn(s)
    mana(s, R=1, W=1, C=1)
    borrowed = lent(s, marvin, "{1}{R}{W}, {T}, Sacrifice a Spirit: Choose target card exiled with this permanent.")
    with pytest.raises(ActionError, match="target"):  # 607.5: no card is exiled with Marvin by a linked ability — no legal target
        act(s, "p1", type="activate_ability", card_id=marvin.id, ability=borrowed.index)
    # -- the same text with neither its exiling half nor a lending path (607.2a: nothing to link to): refused, not an engine error
    bare = replace(borrowed, borrowed_origin=(), borrowed_scope=None)
    assert scripts.define(bare, chars(s, marvin)) is None
    roundtrip(s)
