"""Review 37 (false-FULL probe of waves 41A-44A), CR 2026-09-25, real Oracle text (tests/fixtures/review37_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 101.2, 121.2, 614.6 (Narset, Parter of Veils; Spirit of the Labyrinth; the Narset and Leovold rulings): "can't draw more than one card each turn" is read one
  draw at a time. "If an opponent's first draw is replaced (by a dredge ability, for example), that draw didn't happen and Leovold won't stop the next draw";
  "replacement effects can't be used to replace draws that Narset disallows". Wave 43B capped the instruction up front, so a dredged first draw used up the
  allowance (the second card was lost) and a "draw two cards instead" replacement drew both cards.
* 603.2d, 110.1 (Elesh Norn, Mother of Machines): "Permanents entering don't cause abilities of permanents your opponents control to trigger." stops the
  abilities of permanents only: Bloodghast's landfall works from its owner's graveyard and still triggers.
* Pins: Auntie Ool's "if you control that creature" reads a creature the -1/-1 counters killed as it last existed (608.2h); Varragoth's found card stays hidden
  after the ability resolves (701.23a).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.visibility import SPECTATOR
from tests import test_rules_wave42c_activated as w42c
from tests import test_rules_wave44a_if_you_do as w44a
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "review37_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r37", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def repo_of(settings, extra):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *extra], settings.cards_db_path, meta={"bulk_type": "test"})
    return CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))


@pytest.fixture()
def cards(settings):
    repo = repo_of(settings, EXTRA)
    yield repo
    repo.close()


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def to_graveyard(s, name, pid="p1"):
    act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"player": pid, "zone": "graveyard"})


def cast_divination(s):
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Divination").id)


# ---- the draw limit, one draw at a time ---------------------------------------------------------------------------------------------------------------
def test_a_dredged_first_draw_was_not_drawn_so_the_second_draw_is_allowed(cards):
    s = build(cards, ["Spirit of the Labyrinth", "Divination", "Darkblast"])
    put(s, "Spirit of the Labyrinth")
    to_graveyard(s, "Darkblast")
    to_hand(s, "Divination")
    before = hand(s)
    cast_divination(s)
    settle(s, answer="o0")  # Alice dredges the first draw (702.52a), then draws the second card
    assert zone_of(s, "Darkblast") == "p1:hand"
    assert hand(s) == before + 1  # (Divination left the hand; Darkblast and one drawn card came)
    check(s)


def test_a_replacement_that_draws_two_cards_draws_only_the_one_allowed(cards):
    s = build(cards, ["Spirit of the Labyrinth", "Divination", "Thought Reflection"])
    put(s, "Spirit of the Labyrinth")
    put(s, "Thought Reflection")
    to_hand(s, "Divination")
    before = hand(s)
    cast_divination(s)
    settle(s)
    assert hand(s) == before  # one card: Thought Reflection's second draw and Divination's second card are not allowed
    assert any("can't draw more than 1 card each turn" in " ".join(p.t or p.name or "" for p in line.parts) for line in s.state.log)
    check(s)


def test_without_a_replacement_the_limit_still_stops_the_second_card(cards):
    s = build(cards, ["Spirit of the Labyrinth", "Divination"])
    put(s, "Spirit of the Labyrinth")
    to_hand(s, "Divination")
    before = hand(s)
    cast_divination(s)
    settle(s)
    assert hand(s) == before  # (Divination left, one card drawn)
    check(s)


# ---- Elesh Norn stops the abilities of permanents only --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("norn", [False, True])
def test_elesh_norn_does_not_stop_an_opponents_graveyard_landfall(cards, norn):
    s = build(cards, ["Bloodghast"], ["Elesh Norn, Mother of Machines"])
    if norn:
        put(s, "Elesh Norn, Mother of Machines", "p2")
    to_graveyard(s, "Bloodghast")
    forest = next(c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest")
    act(s, "p1", type="move", card_ids=[forest], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest)
    settle(s)
    assert zone_of(s, "Bloodghast") == "p1:battlefield"  # Bloodghast's landfall is a graveyard card's ability, not a permanent's
    check(s)


def test_elesh_norn_still_stops_an_opponents_permanent(cards):
    s = build(cards, ["Elvish Visionary"], ["Elesh Norn, Mother of Machines"])
    put(s, "Elesh Norn, Mother of Machines", "p2")
    to_hand(s, "Elvish Visionary")
    before = hand(s)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Elvish Visionary").id)
    settle(s)
    assert zone_of(s, "Elvish Visionary") == "p1:battlefield" and hand(s) == before - 1  # its enters ability didn't trigger
    check(s)


# ---- pins ---------------------------------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def cards44a(settings):
    repo = repo_of(settings, w44a.EXTRA)
    yield repo
    repo.close()


def test_auntie_ool_reads_a_creature_the_counters_killed_as_it_last_existed(cards44a):
    s = build(cards44a, [w44a.OOL, w44a.SCAR, "Llanowar Elves"], ["Llanowar Elves"])
    put(s, w44a.OOL)
    elf = put(s, "Llanowar Elves")
    to_hand(s, w44a.SCAR)
    before, life = hand(s), s.state.players["p1"].life
    w44a.scar(s, elf.id)
    assert s.state.cards[elf.id].zone == "p1:graveyard"  # 704.5f
    assert hand(s) == before and s.state.players["p1"].life == life  # Scar left the hand, a card was drawn: Alice controlled it (608.2h)
    theirs = put(s, "Llanowar Elves", "p2")
    to_hand(s, w44a.SCAR)
    bob = s.state.players["p2"].life
    w44a.scar(s, theirs.id)
    assert s.state.players["p2"].life == bob - 1  # its controller as it last existed loses 1 life
    check(s)


@pytest.fixture()
def cards42c(settings):
    repo = repo_of(settings, w42c.EXTRA)
    yield repo
    repo.close()


def test_varragoths_found_card_stays_hidden_after_it_resolves(cards42c):
    s, varragoth = w42c.varragoth_table(cards42c)
    w42c.attack(s, varragoth)
    mana(s, B=1, C=1)
    w42c.activate(s, "p1", varragoth, targets=["p2"])
    d = w42c.ask(s)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Counterspell")])
    w42c.settle(s)
    assert s.state.zones["p2:library"][0] == card_named(s, "Counterspell", "p2").id
    for viewer in ("p1", SPECTATOR):
        assert "Counterspell" not in json.dumps(s.view(viewer)), viewer
    check(s)
