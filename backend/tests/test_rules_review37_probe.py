"""Review 37 probes (scratch)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.rules_state import turn_log_now
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "review37_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r37", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


@pytest.fixture()
def cards42c(settings):
    from tests import test_rules_wave42c_activated as w
    settings.ensure_dirs()
    build_database([*fixture_cards(), *w.EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_probe_varragoth_hidden_after(cards42c):
    from app.game.visibility import SPECTATOR
    from tests import test_rules_wave42c_activated as w
    s, varragoth = w.varragoth_table(cards42c)
    w.attack(s, varragoth)
    mana(s, B=1, C=1)
    w.activate(s, "p1", varragoth, targets=["p2"])
    d = w.ask(s)
    pick = next(o.id for o in d.options if o.label == "Counterspell")
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[pick])
    w.settle(s)
    print([" ".join(p.get("t") or (p.get("card") or {}).get("name") or "" for p in e["parts"]) for e in s.view("p1")["log"]][-6:])
    for v in ("p1", SPECTATOR):
        blob = json.dumps(s.view(v))
        assert "Counterspell" not in blob, v


@pytest.fixture()
def cards44a(settings):
    from tests import test_rules_wave44a_if_you_do as w
    settings.ensure_dirs()
    build_database([*fixture_cards(), *w.EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_probe_auntie_ool_creature_dies(cards44a):
    from tests import test_rules_wave44a_if_you_do as w
    s = build(cards44a, [w.OOL, w.SCAR, "Llanowar Elves"], ["Llanowar Elves"])
    put(s, w.OOL)
    elf = put(s, "Llanowar Elves")
    to_hand(s, w.SCAR)
    hand0, life0 = hand(s), s.state.players["p1"].life
    w.scar(s, elf.id)
    print("elf zone", s.state.cards[elf.id].zone, "hand delta", hand(s) - hand0, "life", s.state.players["p1"].life - life0)
    assert s.state.cards[elf.id].zone == "p1:graveyard"
    assert hand(s) - hand0 == 0 and s.state.players["p1"].life == life0  # Scar left, a card drawn (608.2h: it was Alice's as it last existed)
    elf2 = put(s, "Llanowar Elves", "p2")
    to_hand(s, w.SCAR)  # (back from the graveyard)
    life2 = s.state.players["p2"].life
    w.scar(s, elf2.id)
    print("p2 life delta", s.state.players["p2"].life - life2)
    assert s.state.players["p2"].life == life2 - 1


def test_probe_dredged_first_draw_lets_the_second_draw_happen(cards):
    s = build(cards, ["Spirit of the Labyrinth", "Divination", "Darkblast"])
    put(s, "Spirit of the Labyrinth")
    act(s, "p1", type="move", card_ids=[card_named(s, "Darkblast").id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Divination")
    log = turn_log_now(s.state)
    print("drew so far", log.drew if log else None)
    before = hand(s)
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Divination").id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            print("decision", d.kind, d.player, [o.id for o in d.options], d.prompt)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["o0"] if "o0" in [o.id for o in d.options] else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    print("hand delta", hand(s) - before, "darkblast", s.state.cards[card_named(s, "Darkblast").id].zone)
    # -1 Divination, +1 Darkblast, +1 second draw
    assert hand(s) - before == 1


def test_probe_replacement_draw_two_is_capped(cards):
    s = build(cards, ["Spirit of the Labyrinth", "Divination", "Thought Reflection"])
    put(s, "Spirit of the Labyrinth")
    put(s, "Thought Reflection")
    to_hand(s, "Divination")
    before = hand(s)
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Divination").id)
    settle(s)
    print("hand delta", hand(s) - before)
    assert hand(s) - before == 0  # -1 Divination, +1 card: the replacement's second draw is not allowed
