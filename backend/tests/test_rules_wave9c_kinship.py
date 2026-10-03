"""Wave 9C: kinship ("At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature
type with this creature, you may reveal it. If you do, …"), researched against CR 2026-09-25.

* 701.20e: looking shows the card to the looking player alone; 701.20a-b: revealing shows it to everyone and leaves it
  where it is. Both questions are asked whatever the top card is (a question that appeared only for a matching card
  would tell the table what the hidden card is).
* 205.3m / 702.73a: creature types; a changeling is every creature type, so it shares with any card that has one.
* 207.2c: "Kinship" is an ability word with no rules meaning.

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
from tests.wave9c_kit import build, card_named, check, life

EXTRA = [
    card('Wolf-Skull Shaman', set_code='tst', number='E01', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf Shaman', oracle_text='Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with this creature, you may reveal it. If you do, create a 2/2 green Wolf creature token.', colors=['G'], color_identity=['G'], keywords=['Kinship'], power='2', toughness='2'),  # noqa: E501
    card('Pyroclast Consul', set_code='tst', number='E02', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Creature — Elemental Shaman', oracle_text='Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with this creature, you may reveal it. If you do, this creature deals 2 damage to each creature.', colors=['R'], color_identity=['R'], keywords=['Kinship'], power='3', toughness='3'),  # noqa: E501
    card('Squeaking Pie Grubfellows', set_code='tst', number='E03', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Goblin Shaman', oracle_text='Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with this creature, you may reveal it. If you do, each opponent discards a card.', colors=['B'], color_identity=['B'], keywords=['Kinship'], power='3', toughness='2'),  # noqa: E501
    card('Winnower Patrol', set_code='tst', number='E04', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Elf Warrior', oracle_text='Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with this creature, you may reveal it. If you do, put a +1/+1 counter on this creature.', colors=['G'], color_identity=['G'], keywords=['Kinship'], power='3', toughness='2'),  # noqa: E501
    card('Leaf-Crowned Elder', set_code='tst', number='E05', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Treefolk Shaman', oracle_text='Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with this creature, you may reveal it. If you do, you may play that card without paying its mana cost.', colors=['G'], color_identity=['G'], keywords=['Kinship'], power='3', toughness='5'),  # noqa: E501
    card('Sensation Gorger', set_code='tst', number='E06', mana_cost='{1}{R}{R}', cmc=3.0, type_line='Creature — Goblin Shaman', oracle_text='Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with this creature, you may reveal it. If you do, each player discards their hand, then draws four cards.', colors=['R'], color_identity=['R'], keywords=['Kinship'], power='2', toughness='2'),  # noqa: E501
    card('Wandering Graybeard', set_code='tst', number='E07', mana_cost='{3}{W}{W}', cmc=5.0, type_line='Creature — Giant Wizard', oracle_text='Kinship — At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type with this creature, you may reveal it. If you do, you gain 4 life.', colors=['W'], color_identity=['W'], keywords=['Kinship'], power='4', toughness='4'),  # noqa: E501
    card('Elf Scout', set_code='tst', number='E10', mana_cost='{G}', cmc=1.0, type_line='Creature — Elf Scout', oracle_text='', power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Goblin Raider', set_code='tst', number='E11', mana_cost='{R}', cmc=1.0, type_line='Creature — Goblin Warrior', oracle_text='', power='1', toughness='1', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Shifty Changeling', set_code='tst', number='E12', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Shapeshifter', oracle_text='Changeling (This card is every creature type.)', power='1', toughness='1', colors=['G'], color_identity=['G'], keywords=['Changeling']),  # noqa: E501
    card('Plain Idol', set_code='tst', number='E13', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='', colors=[], color_identity=[], keywords=[]),  # noqa: E501
]
FULL = ["Wolf-Skull Shaman", "Pyroclast Consul", "Squeaking Pie Grubfellows", "Winnower Patrol", "Sensation Gorger",
        "Wandering Graybeard"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def to_upkeep(s):
    """Play on to Alice's next upkeep: the kinship question (every other decision is answered plainly)."""
    for _ in range(300):
        d = s.state.rules.decision
        if d is not None and d.player == "p1" and (d.prompt or "").startswith("Look at the top card"):
            return d
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            answer(s, first(d))
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def finish(s):
    """Let the upkeep resolve (whatever else is asked is answered plainly)."""
    for _ in range(10):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            return
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            answer(s, first(d))


def setup(cards, name, top, **kw):
    s = build(cards, (name, top, "Elf Scout", "Goblin Raider", "Shifty Changeling", "Plain Idol"), **kw)
    move(s, name, "battlefield")
    return s


def tokens_named(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.owner == pid and c.zone.endswith("battlefield")]


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", c["name"]


def test_the_free_play_variant_and_other_wordings_stay_manual():
    from tests.test_rules_scripts import ch as characteristics

    for name in ("Leaf-Crowned Elder",):
        c = next(c for c in EXTRA if c["name"] == name)
        assert coverage.of_characteristics(characteristics(c["name"], c["type_line"], c["oracle_text"])).level != "FULL"
    for text in ("At the beginning of your upkeep, you may look at the top card of your library. If it shares a creature type "
                 "with this creature, you may reveal it. If you do, destroy target creature.",
                 "At the beginning of your upkeep, you may look at the top card of your library. If it shares a color "
                 "with this creature, you may reveal it. If you do, you gain 4 life."):
        assert coverage.of_characteristics(characteristics("Test", "Creature — Elf", text)).level != "FULL", text


def test_a_card_sharing_a_type_can_be_revealed_for_the_wolf(cards):
    s = setup(cards, "Wolf-Skull Shaman", "Elf Scout")
    elf = move(s, "Elf Scout", "library", "top")
    d = to_upkeep(s)
    assert [o.id for o in d.options] == ["look"] and d.min_choices == 0
    answer(s, ["look"])
    d = s.state.rules.decision
    assert d.player == "p1" and [o.id for o in d.options] == [elf.id]
    assert "options" not in s.view("p2")["rules"]["decision"]  # (the top card is private)
    assert "Elf Scout" not in json.dumps(s.view("p2")["rules"]["decision"])
    answer(s, [elf.id])
    finish(s)
    assert len(tokens_named(s, "Wolf")) == 1
    log = json.dumps(s.view("p2")["log"])
    assert "Elf Scout" in log  # revealed to everyone
    check(s)
    roundtrip(s)


def test_a_card_that_shares_nothing_cannot_be_revealed_but_the_question_is_still_asked(cards):
    s = setup(cards, "Wolf-Skull Shaman", "Goblin Raider")
    gob = move(s, "Goblin Raider", "library", "top")
    to_upkeep(s)
    answer(s, ["look"])
    d = s.state.rules.decision
    assert d.player == "p1" and d.options == [] and d.max_choices == 0  # asked all the same (701.20e)
    assert "Goblin Raider" not in json.dumps(s.view("p2")["rules"]["decision"])
    answer(s, [])
    finish(s)
    assert not tokens_named(s, "Wolf")
    assert "Goblin Raider" not in json.dumps(s.view("p2")["log"])  # (never shown to the table)
    assert s.state.cards[gob.id].zone == "p1:hand"  # (still on top: drawn in the draw step)
    check(s)


def test_a_changeling_shares_a_type_with_any_creature(cards):
    s = setup(cards, "Winnower Patrol", "Shifty Changeling")
    ch = move(s, "Shifty Changeling", "library", "top")
    to_upkeep(s)
    answer(s, ["look"])
    d = s.state.rules.decision
    assert [o.id for o in d.options] == [ch.id]
    answer(s, [ch.id])
    finish(s)
    assert s.state.cards[card_named(s, "Winnower Patrol").id].counters.get("+1/+1") == 1
    check(s)


def test_a_noncreature_card_shares_no_creature_type(cards):
    s = setup(cards, "Winnower Patrol", "Plain Idol")
    move(s, "Plain Idol", "library", "top")
    to_upkeep(s)
    answer(s, ["look"])
    assert s.state.rules.decision.options == []
    answer(s, [])
    assert s.state.cards[card_named(s, "Winnower Patrol").id].counters.get("+1/+1") is None
    check(s)


def test_declining_to_look_does_nothing_and_shows_nothing(cards):
    s = setup(cards, "Wandering Graybeard", "Elf Scout")
    move(s, "Elf Scout", "library", "top")
    before = life(s)
    to_upkeep(s)
    answer(s, [])
    finish(s)
    assert life(s) == before
    check(s)


def test_revealing_a_sharing_card_gains_the_life(cards):
    s = setup(cards, "Wandering Graybeard", "Elf Scout")
    # (a Giant Wizard: the Changeling shares with it)
    ch = move(s, "Shifty Changeling", "library", "top")
    before = life(s)
    to_upkeep(s)
    answer(s, ["look"])
    answer(s, [ch.id])
    finish(s)
    assert life(s) == before + 4
    check(s)
