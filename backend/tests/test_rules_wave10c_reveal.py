"""Wave 10C: "Reveal any number of green cards in your hand. … the number of cards revealed this way" (Scent of Ivy, Ivy Seer, Scent of
Jasmine, Scent of Nightshade, Nightshade Seer, Jasmine Seer), researched against CR 2026-09-25.

* 701.20a: to reveal a card is to show it to every player; revealing doesn't move it (the hand keeps it).
* 608.2d: "any number" is the controller's choice as the spell or ability resolves (none is allowed; only matching cards qualify).
* 608.2h: "the number of cards revealed this way" is what this instruction revealed, read as the later instruction is carried out.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip

EXTRA = [
    card('Scent of Ivy', set_code='tst', number='R01', mana_cost='{G}', cmc=1.0, type_line='Instant', oracle_text='Reveal any number of green cards in your hand. Target creature gets +X/+X until end of turn, where X is the number of cards revealed this way.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Ivy Seer', set_code='tst', number='R02', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Elf Wizard', oracle_text='{2}{G}, {T}: Reveal any number of green cards in your hand. Target creature gets +X/+X until end of turn, where X is the number of cards revealed this way.', power='1', toughness='1', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Scent of Jasmine', set_code='tst', number='R03', mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text='Reveal any number of white cards in your hand. You gain 2 life for each card revealed this way.', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Scent of Nightshade', set_code='tst', number='R04', mana_cost='{1}{B}', cmc=2.0, type_line='Instant', oracle_text='Reveal any number of black cards in your hand. Target creature gets -X/-X until end of turn, where X is the number of cards revealed this way.', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Nightshade Seer', set_code='tst', number='R05', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Human Wizard', oracle_text='{2}{B}, {T}: Reveal any number of black cards in your hand. Target creature gets -X/-X until end of turn, where X is the number of cards revealed this way.', power='1', toughness='1', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Jasmine Seer', set_code='tst', number='R06', mana_cost='{3}{W}', cmc=4.0, type_line='Creature — Human Wizard', oracle_text='{2}{W}, {T}: Reveal any number of white cards in your hand. You gain 2 life for each card revealed this way.', power='1', toughness='1', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Mending Hands', set_code='tst', number='R07', mana_cost='{W}', cmc=1.0, type_line='Instant', oracle_text='Prevent the next 4 damage that would be dealt to any target this turn.', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Rofellos\'s Gift', set_code='tst', number='R08', mana_cost='{G}', cmc=1.0, type_line='Sorcery', oracle_text='Reveal any number of green cards in your hand. Return an enchantment card from your graveyard to your hand for each card revealed this way.', colors=['G'], color_identity=['G']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA[:6]]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_a_count_limited_return_stays_manual(cards):
    # "Return an enchantment card … for each card revealed this way" needs a choice limited by the count: not read
    assert coverage.of_card_data(cards.resolve("Rofellos's Gift")).level != "FULL"


def token(s, name, pt, pid="p1"):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": p,
                                                        "toughness": t, "text": ""})
    return find(s, name, pid)


def pt(s, card):
    from tests.test_rules_attachments import ch

    return ch(s, card).pt


def settle(s, limit=20):
    for _ in range(limit):
        if s.state.rules.decision is not None:
            return
        if not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def cast(s, name, targets=None, **m):
    c = find(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    settle(s)
    return s.state.rules.decision


def answer_all(s, d):
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    settle(s)


def test_scent_of_ivy_counts_the_green_cards_revealed(cards):
    s = build(cards, p1=("Scent of Ivy", "Grizzly Bears", "Scent of Jasmine", "Sol Ring", "Ivy Seer"))
    brute = token(s, "Brute", "2/2")
    bears, seer, ring = (put(s, n, "hand") for n in ("Grizzly Bears", "Ivy Seer", "Sol Ring"))
    d = cast(s, "Scent of Ivy", [brute.id], G=1)
    assert d is not None and d.player == "p1" and d.min_choices == 0
    assert {o.card_id for o in d.options} == {bears.id, seer.id}  # the colorless Sol Ring can't be revealed
    answer_all(s, d)
    assert pt(s, brute) == (4, 4)  # +2/+2: two cards revealed
    assert s.state.cards[bears.id].zone == "p1:hand" and "*" in s.state.cards[bears.id].revealed_to  # shown to all, not moved
    assert "*" not in s.state.cards[ring.id].revealed_to
    roundtrip(s)


def test_revealing_none_gives_zero(cards):
    s = build(cards, p1=("Scent of Ivy", "Grizzly Bears"))
    brute = token(s, "Brute", "2/2")
    put(s, "Grizzly Bears", "hand")
    d = cast(s, "Scent of Ivy", [brute.id], G=1)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert pt(s, brute) == (2, 2)
    roundtrip(s)


def test_the_question_is_asked_even_with_nothing_to_reveal(cards):
    s = build(cards, p1=("Scent of Ivy",))
    brute = token(s, "Brute", "2/2")
    d = cast(s, "Scent of Ivy", [brute.id], G=1)
    assert d is not None and d.options == [] and d.max_choices == 0  # (whether it is asked says nothing about the hand)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert pt(s, brute) == (2, 2)
    roundtrip(s)


def test_scent_of_jasmine_gains_two_life_for_each_white_card(cards):
    s = build(cards, p1=("Scent of Jasmine", "Mending Hands", "Sol Ring"))
    mending, _ring = (put(s, n, "hand") for n in ("Mending Hands", "Sol Ring"))
    d = cast(s, "Scent of Jasmine", None, W=1)
    assert [o.card_id for o in d.options] == [mending.id]
    answer_all(s, d)
    assert s.state.players["p1"].life == 42
    roundtrip(s)


def test_scent_of_nightshade_shrinks_by_the_black_cards_revealed(cards):
    s = build(cards, p1=("Scent of Nightshade", "Nightshade Seer"), p2=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    put(s, "Nightshade Seer", "hand")
    d = cast(s, "Scent of Nightshade", [bears.id], B=2)
    answer_all(s, d)
    assert pt(s, bears) == (1, 1)  # -1/-1: one black card revealed
    roundtrip(s)


def test_ivy_seer_reveals_as_an_activated_ability(cards):
    s = build(cards, p1=("Ivy Seer", "Grizzly Bears"))
    brute = token(s, "Brute", "2/2")
    seer = put(s, "Ivy Seer", "battlefield")
    put(s, "Grizzly Bears", "hand")
    s.state.rules.controlled_since[seer.id].turn = s.state.rules.turn_started["p1"] - 1  # (it has been there since before this turn began)
    mana(s, G=3)
    act(s, "p1", type="activate_ability", card_id=seer.id, ability=0, targets=[brute.id])
    settle(s)
    d = s.state.rules.decision
    answer_all(s, d)
    assert pt(s, brute) == (3, 3)
    roundtrip(s)
