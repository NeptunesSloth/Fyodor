"""Wave 9C: parley ("Each player reveals the top card of their library. For each nonland card revealed this way, …. Then
each player draws a card."), researched against CR 2026-09-25.

* 701.20a-b: each player reveals their top card to everyone and it stays on top, so the draw takes the revealed card;
  a player with an empty library reveals nothing.
* 608.2c / 608.2h: the instruction after "for each … revealed this way" is carried out once per card revealed, in order
  with the sentences around it (Phabine's pump sees the tokens made before it).
* 207.2c: "Parley" is an ability word with no rules meaning.

Every scenario uses real Oracle text and checks the replay and a save and a load.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave5i_top_escape import answer, first, move, roundtrip
from tests.wave9c_kit import build, card_named, cast, check, mana, put, to_hand

EXTRA = [
    card('Rousing of Souls', set_code='wp', number='E01', mana_cost='{2}{W}', cmc=3.0, type_line='Sorcery', oracle_text='Parley — Each player reveals the top card of their library. For each nonland card revealed this way, you create a 1/1 white Spirit creature token with flying. Then each player draws a card.', colors=['W'], color_identity=['W'], keywords=['Parley']),  # noqa: E501
    card("Phabine, Boss's Confidant", set_code='wp', number='E02', mana_cost='{3}{R}{G}{W}', cmc=6.0, type_line='Legendary Creature — Cat Advisor', oracle_text='Creature tokens you control have haste.\nParley — At the beginning of combat on your turn, each player reveals the top card of their library. For each land card revealed this way, you create a 1/1 green and white Citizen creature token. Then creatures you control get +1/+1 until end of turn for each nonland card revealed this way. Then each player draws a card.', colors=['G', 'R', 'W'], color_identity=['G', 'R', 'W'], keywords=['Parley'], power='3', toughness='6'),  # noqa: E501
    card("Selvala's Enforcer", set_code='wp', number='E03', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Elf Warrior', oracle_text='Parley — When this creature enters, each player reveals the top card of their library. For each nonland card revealed this way, put a +1/+1 counter on this creature. Then each player draws a card.', colors=['G'], color_identity=['G'], keywords=['Parley'], power='2', toughness='2'),  # noqa: E501
    card('Cutthroat Negotiator', set_code='wp', number='E04', mana_cost='{2}{U}{R}', cmc=4.0, type_line='Creature — Orc Pirate', oracle_text='Parley — Whenever this creature attacks, each player reveals the top card of their library. For each nonland card revealed this way, you create a tapped Treasure token. Then each player draws a card.', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Treasure', 'Parley'], power='4', toughness='3'),  # noqa: E501
    card('Woodvine Elemental', set_code='wp', number='E05', mana_cost='{4}{G}{W}', cmc=6.0, type_line='Creature — Elemental', oracle_text='Trample\nParley — Whenever this creature attacks, each player reveals the top card of their library. For each nonland card revealed this way, attacking creatures you control get +1/+1 until end of turn. Then each player draws a card.', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Trample', 'Parley'], power='4', toughness='4'),  # noqa: E501
    card('Selvala, Explorer Returned', set_code='wp', number='E06', mana_cost='{1}{G}{W}', cmc=3.0, type_line='Legendary Creature — Elf Scout', oracle_text='Parley — {T}: Each player reveals the top card of their library. For each nonland card revealed this way, add {G} and you gain 1 life. Then each player draws a card. (Activate only as an instant.)', colors=['G', 'W'], color_identity=['G', 'W'], keywords=['Parley'], power='2', toughness='4'),  # noqa: E501
    card('Plain Idol', set_code='wp', number='E10', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Second Idol', set_code='wp', number='E11', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('Quiet Bear', set_code='wp', number='E12', mana_cost='{2}', cmc=2.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=[], color_identity=[], keywords=[]),  # noqa: E501
]
FULL = ["Rousing of Souls", "Phabine, Boss's Confidant", "Selvala's Enforcer", "Cutthroat Negotiator", "Woodvine Elemental",
        "Selvala, Explorer Returned"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def finish(s):
    for _ in range(40):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and not s.state.rules.pending_triggers:
            return
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            answer(s, first(d))


def tops(s, alice, bob):
    """Put the named card on top of each library."""
    move(s, alice, "library", "top")
    if bob is not None:
        move(s, bob, "library", "top", pid="p2")


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.owner == pid and c.zone.endswith("battlefield")]


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", c["name"]


def test_other_wordings_stay_manual():
    from tests.test_rules_scripts import ch as characteristics

    for text in ("Each player reveals the top card of their library. For each nonland card revealed this way, you may create "
                 "a Map token. Then each player draws a card.",
                 "Each player reveals the top card of their library. For each nonland card revealed this way, destroy target "
                 "creature. Then each player draws a card.",
                 "Each player reveals the top card of their library. For each nonland card revealed this way, you create a Map "
                 "token."):
        assert coverage.of_characteristics(characteristics("Test", "Sorcery", text)).level != "FULL", text


@pytest.mark.parametrize(("alice", "bob", "spirits"), [("Plain Idol", "Second Idol", 2), ("Plain Idol", "Island", 1),
                                                        ("Forest", "Island", 0), ("Forest", "Second Idol", 1)])
def test_rousing_of_souls_makes_a_spirit_for_each_nonland_card_revealed(cards, alice, bob, spirits):
    s = build(cards, ("Rousing of Souls", "Plain Idol", "Second Idol"), ("Second Idol",))
    to_hand(s, "Rousing of Souls")
    top_a = move(s, alice, "library", "top")
    top_b = move(s, bob, "library", "top", pid="p2")
    mana(s, W=3)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Rousing of Souls")
    assert len(tokens(s, "Spirit")) == spirits
    assert top_a.id in s.state.zones["p1:hand"] and top_b.id in s.state.zones["p2:hand"]  # (each drew the revealed card)
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 1
    log = json.dumps(s.view("p2")["log"])
    assert alice in log  # (revealed to everyone)
    check(s)
    roundtrip(s)


def test_a_player_with_an_empty_library_reveals_nothing(cards):
    s = build(cards, ("Rousing of Souls", "Plain Idol"), ("Second Idol",))
    to_hand(s, "Rousing of Souls")
    move(s, "Plain Idol", "library", "top")
    act(s, "p2", type="move", card_ids=list(s.state.zones["p2:library"]), to={"player": "p2", "zone": "graveyard"})
    mana(s, W=3)
    cast(s, "Rousing of Souls")
    assert len(tokens(s, "Spirit")) == 1  # (only Alice's nonland card; Bob had none to reveal, and draws nothing)
    check(s)


def test_phabine_counts_lands_and_nonlands_separately_in_order(cards):
    """Land → Citizen token; each nonland → +1/+1 for creatures you control, the new token included."""
    s = build(cards, ("Phabine, Boss's Confidant", "Plain Idol", "Quiet Bear"), ("Second Idol",))
    put(s, "Phabine, Boss's Confidant")
    move(s, "Forest", "library", "top")  # (Alice reveals a land, Bob a nonland)
    move(s, "Second Idol", "library", "top", pid="p2")
    for _ in range(80):
        d = s.state.rules.decision
        if tokens(s, "Citizen"):
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            answer(s, first(d))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    cit = tokens(s, "Citizen")
    assert len(cit) == 1
    from tests.wave9c_kit import pt

    assert pt(s, "Phabine, Boss's Confidant") == (4, 7)
    c = s.state.cards[cit[0].id]
    from app.rules import sba
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(c)
    assert (sba.power(c, ch), sba.toughness(c, ch)) == (2, 2)  # the token, made first, gets the +1/+1 too
    check(s)


def test_selvala_s_enforcer_gets_a_counter_for_each_nonland_card(cards):
    s = build(cards, ("Selvala's Enforcer", "Plain Idol"), ("Second Idol",))
    to_hand(s, "Selvala's Enforcer")
    move(s, "Plain Idol", "library", "top")
    move(s, "Island", "library", "top", pid="p2")
    mana(s, G=4)
    cast(s, "Selvala's Enforcer")
    finish(s)
    assert s.state.cards[card_named(s, "Selvala's Enforcer").id].counters.get("+1/+1") == 1
    check(s)
    roundtrip(s)
