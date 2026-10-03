"""Wave 10C: the other users of the same grammar — a mandatory pick ("put all Elf cards from among them"), a pick gated by a
payment (Ripples of Undeath), and the revealed-card count as an amount of damage (Scent of Cinder, Cinder Seer), researched against
CR 2026-09-25 (701.17 mill, 608.2c order of instructions, 118.12 optional costs, 701.20 reveal).

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
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card('Cantankerous Keepers', set_code='tst', number='M01', mana_cost='{5}{G}', cmc=6.0, type_line='Creature — Elf Soldier', oracle_text='Affinity for Elves (This spell costs {1} less to cast for each Elf you control.)\nWhen this creature enters, mill four cards, then put all Elf cards from among them into your hand.', power='4', toughness='3', colors=['G'], color_identity=['G'], keywords=['Affinity', 'Mill']),  # noqa: E501
    card('Ripples of Undeath', set_code='tst', number='M02', mana_cost='{1}{B}', cmc=2.0, type_line='Enchantment', oracle_text='At the beginning of your first main phase, mill three cards. Then you may pay {1} and 3 life. If you do, put a card from among those cards into your hand.', colors=['B'], color_identity=['B'], keywords=['Mill']),  # noqa: E501
    card('Scent of Cinder', set_code='tst', number='M03', mana_cost='{1}{R}', cmc=2.0, type_line='Sorcery', oracle_text='Reveal any number of red cards in your hand. Scent of Cinder deals X damage to any target, where X is the number of cards revealed this way.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Cinder Seer', set_code='tst', number='M04', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Human Wizard', oracle_text='{2}{R}, {T}: Reveal any number of red cards in your hand. This creature deals X damage to any target, where X is the number of cards revealed this way.', power='1', toughness='1', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Shock', set_code='tst', number='M05', mana_cost='{R}', cmc=1.0, type_line='Instant', oracle_text='Shock deals 2 damage to any target.', colors=['R'], color_identity=['R']),  # noqa: E501
]
NAMES = [c["name"] for c in EXTRA[:4]]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def zone_of(s, name, zone, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:{zone}"]


def test_cantankerous_keepers_puts_every_milled_elf_into_hand(cards):
    s = build(cards, p1=("Cantankerous Keepers", "Elvish Visionary", "Grizzly Bears"))
    put(s, "Grizzly Bears", "library", position="top")
    put(s, "Elvish Visionary", "library", position="top")
    c = find(s, "Cantankerous Keepers")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, G=6)
    act(s, "p1", type="cast_spell", card_id=c.id)
    pass_until_stack_empty(s)
    answer(s)
    assert zone_of(s, "Elvish Visionary", "hand") and not zone_of(s, "Elvish Visionary", "graveyard")  # an Elf: "put all"
    assert zone_of(s, "Grizzly Bears", "graveyard") and len(zone_of(s, "Forest", "graveyard")) == 2  # four milled, one taken
    roundtrip(s)


def to_main_and_pay(s, pay):
    """Pass to Alice's next first main phase and answer the payment."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and [o.id for o in d.options][:2] == ["pay", "decline"]:
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    else:
        raise AssertionError("no payment asked")
    if pay:
        mana(s, G=1)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"])


@pytest.mark.parametrize("pay", [True, False])
def test_ripples_of_undeath_takes_a_milled_card_only_if_you_paid(cards, pay):
    s = build(cards, p1=("Ripples of Undeath",))
    c = find(s, "Ripples of Undeath")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    pass_until_stack_empty(s)
    assert s.state.cards[c.id].zone == "p1:battlefield"
    put(s, "Forest", "battlefield")  # (the {1} is paid by tapping it while the question is open)
    to_main_and_pay(s, pay)
    life = s.state.players["p1"].life
    if pay:
        d = s.state.rules.decision
        assert d is not None and d.kind == "choose_cards" and d.min_choices == d.max_choices == 1 and len(d.options) == 3
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    graveyard = len([c for c in s.state.cards.values() if c.zone == "p1:graveyard"])
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand" and c.name == "Forest"])
    assert (graveyard, hand) == ((2, 2) if pay else (3, 1))  # (one Forest was drawn for the turn)
    assert life == (37 if pay else 40)
    roundtrip(s)


def test_scent_of_cinder_deals_damage_equal_to_the_red_cards_revealed(cards):
    s = build(cards, p1=("Scent of Cinder", "Shock", "Sol Ring"))
    put(s, "Shock", "hand")
    put(s, "Sol Ring", "hand")
    c = find(s, "Scent of Cinder")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None and [o.card_id for o in d.options] == [find(s, "Shock").id]  # only the red card
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    assert s.state.players["p2"].life == 39  # one red card revealed: 1 damage
    roundtrip(s)


def test_cinder_seer_with_nothing_revealed_deals_no_damage(cards):
    s = build(cards, p1=("Cinder Seer",))
    seer = put(s, "Cinder Seer", "battlefield")
    s.state.rules.controlled_since[seer.id].turn = s.state.rules.turn_started["p1"] - 1
    mana(s, R=3)
    act(s, "p1", type="activate_ability", card_id=seer.id, ability=0, targets=["p2"])
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert s.state.players["p2"].life == 40
    roundtrip(s)
