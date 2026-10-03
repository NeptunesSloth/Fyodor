"""Wave 9B: a static worded over several sentences — "Otherwise, it gets …", "It gets … instead as long as …", "As long as it's …, it gets
an additional …" (Phyrexian Boon, Nyx Infusion, Gift of Fangs, Tahngarth's Rage, Mind Carver, Tenza, Elenda), researched against CR 2026-09-25.

* 604.1, 611.3a: each sentence is a static ability that applies at any moment its condition is true ("Otherwise" and "instead" are
  the other side of the sentence before); 613.4c: all the +N/+N changes of layer 7c apply together ("an additional" adds).
* The condition is read now, never locked in (604.2): the enchanted creature changing color or the opponent's graveyard filling up
  changes the result at once.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage, static_pairs
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch
from tests.test_rules_wave9b_exile_permission import build, put, roundtrip

EXTRA = [
    card('Phyrexian Boon', set_code='tst', number='Q1', mana_cost='{2}{B}', cmc=3.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nEnchanted creature gets +2/+1 as long as it's black. Otherwise, it gets -1/-2.", colors=['B'], color_identity=['B'], keywords=['Enchant']),  # noqa: E501
    card('Mind Carver', set_code='tst', number='Q2', mana_cost='{B}', cmc=1.0, type_line='Artifact — Equipment', oracle_text='When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +1/+0. It gets +3/+1 instead as long as an opponent has eight or more cards in their graveyard.\nEquip {2}{B}', colors=['B'], color_identity=['B'], keywords=['Equip']),  # noqa: E501
    card('Elenda, Saint of Dusk', set_code='tst', number='Q3', mana_cost='{2}{W}{B}', cmc=4.0, type_line='Legendary Creature — Vampire Knight', oracle_text='Lifelink, hexproof from instants\nAs long as your life total is greater than your starting life total, Elenda gets +1/+1 and has menace. Elenda gets an additional +5/+5 as long as your life total is at least 10 greater than your starting life total.', power='4', toughness='4', colors=['B', 'W'], color_identity=['B', 'W'], keywords=['Lifelink', 'Hexproof from', 'Hexproof']),  # noqa: E501
    card("Tenza, Godo's Maul", set_code='tst', number='Q4', mana_cost='{3}', cmc=3.0, type_line='Legendary Artifact — Equipment', oracle_text="Equipped creature gets +1/+1. As long as it's legendary, it gets an additional +2/+2. As long as it's red, it has trample.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)", keywords=['Equip']),  # noqa: E501
    card("Tahngarth's Rage", set_code='tst', number='Q5', mana_cost='{R}', cmc=1.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nEnchanted creature gets +3/+0 as long as it's attacking. Otherwise, it gets -2/-1.", colors=['R'], color_identity=['R'], keywords=['Enchant']),  # noqa: E501
    card('Gift of Fangs', set_code='tst', number='Q6', mana_cost='{B}', cmc=1.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nEnchanted creature gets +2/+2 as long as it's a Vampire. Otherwise, it gets -2/-2.", colors=['B'], color_identity=['B'], keywords=['Enchant']),  # noqa: E501
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_wording_is_exact():
    ok = static_pairs.definition("Enchanted creature gets +2/+1 as long as it's black. Otherwise, it gets -1/-2.")
    assert ok is not None and len(ok["also"]) == 1 and ok["also"][0]["conditions"][0]["static"] == "not"
    assert static_pairs.definition("Equipped creature gets +1/+0. It gets +3/+1 instead as long as an opponent has eight or more "
                                   "cards in their graveyard.")["conditions"][0]["static"] == "not"
    for text in ("Enchanted creature gets +1/+1. Otherwise, it gets -1/-1.",  # (nothing for "Otherwise" to be the other side of)
                 "Enchanted creature gets +2/+1 as long as it's black. Otherwise, it gets -1/-2. Draw a card.",
                 "Enchanted creature gets +2/+1 as long as it's black. Otherwise, it gets -1/-2 until end of turn.",
                 "Enchanted creature gets +2/+1 as long as it's blue-ish. Otherwise, it gets -1/-2.",
                 "Enchanted creature gets +1/+1 as long as it's black. It gets +3/+3 instead as long as it's red.",  # (instead of a conditional one)
                 "Creatures you control get +1/+1. It gets +3/+1 instead as long as you control a Dragon.",
                 "Enchanted creature gets +2/+2 as long as it's a Vampire. Enchanted creature gets -2/-2. Otherwise, it gets 4/4."):
        assert static_pairs.definition(text) is None, text


def pt(s, c):
    return ch(s, c).pt


def aura(s, name, host):
    a = put(s, name, "battlefield")
    act(s, "p1", type="attach", card_ids=[a.id], to=host.id)
    return a


def tok(s, pid, name, pt_, colors=(), type_line="Token Creature — Test", text=""):
    p, t = pt_.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t,
                                                       "colors": list(colors), "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def test_phyrexian_boon_gives_one_or_the_other(cards):
    s = build(cards, p1=("Phyrexian Boon",))
    black = tok(s, "p1", "Shade", "2/2", colors="B")
    green = tok(s, "p1", "Brute", "3/3", colors="G")
    boon = aura(s, "Phyrexian Boon", black)
    assert pt(s, black) == (4, 3)
    act(s, "p1", type="attach", card_ids=[boon.id], to=green.id)
    assert pt(s, green) == (2, 1) and pt(s, black) == (2, 2)  # the condition is read now, for the creature it's on (611.3a)
    roundtrip(s)


def test_gift_of_fangs_and_the_creature_type(cards):
    s = build(cards, p1=("Gift of Fangs",))
    vamp = tok(s, "p1", "Count", "2/2", type_line="Token Creature — Vampire")
    other = tok(s, "p1", "Brute", "3/3")
    gift = aura(s, "Gift of Fangs", vamp)
    assert pt(s, vamp) == (4, 4)
    act(s, "p1", type="attach", card_ids=[gift.id], to=other.id)
    assert pt(s, other) == (1, 1)
    roundtrip(s)


def test_tahngarths_rage_follows_the_creature_into_combat(cards):
    s = build(cards, p1=("Tahngarth's Rage",))
    runner = tok(s, "p1", "Runner", "2/2", text="Haste")
    aura(s, "Tahngarth's Rage", runner)
    assert pt(s, runner) == (0, 1)  # not attacking: -2/-1
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority") if d is None else act(
            s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    tok(s, "p2", "Wall", "0/4")  # (a creature to block: Bob is asked, with the attack still declared)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": runner.id, "target": "p2"}])
    assert s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers"
    assert pt(s, runner) == (5, 2)  # attacking: +3/+0
    roundtrip(s)
    act(s, "p2", type="declare_blockers", blocks=[])
    for _ in range(30):
        if s.state.turn.phase == "main2" and s.state.rules.decision is None:
            break
        act(s, s.state.rules.priority, type="pass_priority") if s.state.rules.decision is None else act(
            s, s.state.rules.decision.player, type="choose", decision_id=s.state.rules.decision.id,
            option_ids=[o.id for o in s.state.rules.decision.options][:1])
    assert pt(s, runner) == (0, 1)  # no longer attacking
    roundtrip(s)


def test_mind_carver_instead_when_the_graveyard_fills(cards):
    s = build(cards, p1=("Mind Carver",), p2=())
    bear = tok(s, "p1", "Bear", "2/2")
    carver = put(s, "Mind Carver", "battlefield")
    act(s, "p1", type="attach", card_ids=[carver.id], to=bear.id)
    assert pt(s, bear) == (3, 2)  # +1/+0
    islands = [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:8]
    for i, isl in enumerate(islands):
        act(s, "p2", type="move", card_ids=[isl.id], to={"player": "p2", "zone": "graveyard"})
        assert pt(s, bear) == ((3, 2) if i < 7 else (5, 3))  # +3/+1 instead, not as well (611.3a)
    act(s, "p2", type="move", card_ids=[islands[0].id], to={"player": "p2", "zone": "hand"})
    assert pt(s, bear) == (3, 2)
    roundtrip(s)


def test_tenza_adds_for_each_property(cards):
    s = build(cards, p1=("Tenza, Godo's Maul",))
    red_legend = tok(s, "p1", "Lord", "2/2", colors="R", type_line="Token Legendary Creature — Test")
    plain = tok(s, "p1", "Grunt", "2/2")
    tenza = put(s, "Tenza, Godo's Maul", "battlefield")
    act(s, "p1", type="attach", card_ids=[tenza.id], to=red_legend.id)
    assert pt(s, red_legend) == (5, 5) and "trample" in ch(s, red_legend).keywords
    act(s, "p1", type="attach", card_ids=[tenza.id], to=plain.id)
    assert pt(s, plain) == (3, 3) and "trample" not in ch(s, plain).keywords and pt(s, red_legend) == (2, 2)
    roundtrip(s)


def test_elenda_grows_with_the_life_total(cards):
    s = build(cards, p1=("Elenda, Saint of Dusk",))
    elenda = put(s, "Elenda, Saint of Dusk", "battlefield")
    assert pt(s, elenda) == (4, 4) and "menace" not in ch(s, elenda).keywords  # 40 life: not greater than the starting total
    act(s, "p1", type="life", player="p1", delta=1)
    assert pt(s, elenda) == (5, 5) and "menace" in ch(s, elenda).keywords
    act(s, "p1", type="life", player="p1", delta=8)
    assert pt(s, elenda) == (5, 5)  # 49: nine greater
    act(s, "p1", type="life", player="p1", delta=1)
    assert pt(s, elenda) == (10, 10)  # 50: at least 10 greater than the starting 40: both apply (+1/+1 and +5/+5)
    act(s, "p1", type="life", player="p1", delta=-10)
    assert pt(s, elenda) == (4, 4)  # back to 40: neither
    roundtrip(s)
