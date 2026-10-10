"""Review 30 (head, round 2): waves 30L / 30M / 30N / 30O falsification (CR 2026-09-25). Real Oracle text (tests/fixtures/review30b_cards.json,
from data/cards.sqlite); every scenario checks the replay and a save and a load.

* 603.4 / 603.12: "When you do, if …" — an intervening "if" on a reflexive ability gates all of it; not read (Earthbender Ascension went FULL
  through 30L's counter counts with "it" read as the land that entered, and trample granted ungated).
* 712.9: a modal double-faced card transforms too (CR 2026-09-25; Gwen Stacy's ruling: "a change from previous rules"); the engine refused it,
  so the transform abilities of six FULL commanders did nothing (Gwen Stacy, Peter Parker, Norman Osborn, King T'Challa, Monica Rambeau,
  Jennifer Walters).
* 107.1b: "its power plus its toughness" sums a negative power as it is; only the result is at least 0 (Phthisis's 2021-03-19 ruling).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, settle
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "review30b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r30b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_earthbender_ascension_reflexive_intervening_if_is_not_automated(cards):
    """Earthbender Ascension: "Landfall — Whenever a land you control enters, put a quest counter on this enchantment. When you do, if it has four
    or more quest counters on it, put a +1/+1 counter on target creature you control. It gains trample until end of turn." Wave 30L made "it has
    four or more quest counters on it" readable, and the reflexive ability went FULL reading "it" as the land that entered (never four counters)
    and gating only the +1/+1 counter (trample was granted anyway). An intervening "if" gates the whole reflexive ability, as it would trigger
    and as it resolves (603.4, 603.12): not read, the ability stays manual (as wave 30G's other reflexive builders already refuse it)."""
    assert coverage.of_card_data(cards.resolve("Earthbender Ascension")).level != "FULL"
    s = build(cards, ["Earthbender Ascension", "Grizzly Bears", "Forest"], [])
    asc = put(s, "Earthbender Ascension")
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[asc.id], kind="quest", delta=2)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest.id)
    settle(s)
    assert "trample" not in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bears.id]).keywords  # (three counters: nothing granted)
    check(s)


def test_gwen_stacy_a_modal_double_faced_card_transforms_and_her_exiled_card_stays_playable(cards):
    """Gwen Stacy // Ghost-Spider (modal double-faced): "When Gwen Stacy enters, exile the top card of your library. You may play that card for as
    long as you control this creature. {2}{U}{R}{W}: Transform Gwen Stacy. Activate only as a sorcery." 712.9 (CR 2026-09-25): any double-faced
    card that isn't a meld card can transform — a modal one too (the 2025-09-19 ruling: "This is a change from previous rules"); the engine still
    refused it, so the activation did nothing. Transforming isn't leaving the battlefield (the same object, 712.18; the ruling): the exiled card
    stays playable (611.2b), and Ghost-Spider has only its back face's characteristics (712.8f)."""
    s = build(cards, ["Gwen Stacy // Ghost-Spider", "Grizzly Bears"], [])
    gwen = to_hand(s, "Gwen Stacy // Ghost-Spider")
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=gwen.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:exile"
    mana(s, U=1, R=1, W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=gwen.id, ability=1)
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[gwen.id])
    assert ch.name == "Ghost-Spider" and {"flying", "vigilance", "haste"} <= set(ch.keywords) and pt(s, "Gwen Stacy // Ghost-Spider") == (4, 4)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize("stats,lost", [("-1/3", 2), ("-4/3", 0), ("3/4", 7)])
def test_phthisis_adds_a_negative_power_as_it_is(cards, stats, lost):
    """Phthisis: "Destroy target creature. Its controller loses life equal to its power plus its toughness." 107.1b: the calculation uses a
    negative power (the 2021-03-19 ruling: a -1/3 creature costs 2 life, a -4/3 one none); each stat was read as at least 0, so a -1/3
    creature cost 3 life and a -4/3 one 3. The creature as it last existed (608.2h: a token that is gone)."""
    s = build(cards, ["Phthisis"], [])
    victim = creature(s, "p2", "Victim", stats)
    to_hand(s, "Phthisis")
    mana(s, B=4, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Phthisis").id, targets=[victim.id])
    settle(s)
    assert victim.id not in s.state.cards or not s.state.cards[victim.id].zone.endswith(":battlefield")
    assert life(s, "p2") == 40 - lost
    check(s)
