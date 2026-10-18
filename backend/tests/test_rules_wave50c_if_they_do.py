"""Wave 50C: "if you do" / "when you do" after an opponent gains control of a permanent, and after "you may transform" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave50c_extra.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load. Cards these made FULL besides the
commanders: Iroh, Tea Master and Soul Seizer // Ghastly Haunting.

* 118.12 / 603.12: Iroh - "you may have target opponent gain control of target permanent you control. When you do, create a 1/1 white Ally creature token. Put a +1/+1
  counter on that token for each permanent you own that your opponents control." (ruling 2025-10-02: the choice is made as the ability resolves).
* 701.27a / 603.12: Soul Seizer - "you may transform it. If you do, attach it to target creature that player controls" (ruling 2011-01-22: transform is chosen as the
  ability resolves; the Aura side says "You control enchanted creature.").
"""

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
from tests.test_rules_wave34b_activated import attack, next_turn, stops, to_phase
from tests.wave9c_kit import build, check, put, reloaded

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50c_extra.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50c", number=f"X{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
IROH, SEIZER = (c["name"] for c in DATA)


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [IROH, SEIZER])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def allies(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Ally" and c.zone == "p1:battlefield"]


def iroh_combat(cards, answer):
    s = build(cards, [IROH, "Grizzly Bears"], forests=30, islands=30)
    put(s, IROH)
    bears = put(s, "Grizzly Bears")
    stops(s)
    to_phase(s, "begin_combat", turn=1)
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        if d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind in ("choose_cards", "choose_one", "confirm"):
            ids = [o.id for o in d.options]
            pick = [bears.id] if bears.id in ids else [answer] if answer in ids else ids[:1]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        else:
            break
    return s, bears


def test_iroh_gives_a_permanent_away_and_the_when_you_do_token_counts_it(cards):
    s, bears = iroh_combat(cards, "yes")
    assert s.state.cards[bears.id].controller == "p2" and s.state.cards[bears.id].owner == "p1"
    made = allies(s)
    assert len(made) == 1 and made[0].counters.get("+1/+1") == 1  # one permanent Alice owns that her opponent controls
    check(s)


def test_iroh_declined_gives_nothing_and_makes_no_token(cards):
    s, bears = iroh_combat(cards, "no")
    assert s.state.cards[bears.id].controller == "p1" and not allies(s)
    check(s)


def seizer_hits(cards, answer):
    s = build(cards, [SEIZER], ["Grizzly Bears"], forests=30, islands=30)
    seizer = put(s, SEIZER)
    bears = put(s, "Grizzly Bears", "p2")
    stops(s)
    next_turn(s)
    attack(s, seizer)
    for _ in range(40):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack") and s.state.turn.phase in ("end_combat", "main2", "end"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        if d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears.id] if bears.id in ids else [answer] if answer in ids else ids[:1])
    return s, seizer, bears


def test_soul_seizer_transforms_and_attaches_so_you_control_the_creature(cards):
    s, seizer, bears = seizer_hits(cards, "yes")
    assert s.state.cards[seizer.id].face == 1 and s.state.cards[seizer.id].attached_to == bears.id
    assert s.state.cards[bears.id].controller == "p1"  # "You control enchanted creature."
    check(s)
    assert reloaded(s).state.cards[bears.id].controller == "p1"


def test_soul_seizer_declined_stays_a_creature(cards):
    s, seizer, bears = seizer_hits(cards, "no")
    assert s.state.cards[seizer.id].face == 0 and s.state.cards[seizer.id].attached_to is None
    assert s.state.cards[bears.id].controller == "p2"
    check(s)
