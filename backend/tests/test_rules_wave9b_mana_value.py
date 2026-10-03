"""Wave 9B: damage equal to the mana value of the card a cost (or an optional payment) discarded, researched against CR 2026-09-25.

* 118.8, 601.2h: the cost is paid first; the ability's effect reads the card it discarded (701.9a): as a discarded card it is
  in the graveyard, its mana value what it printed (202.3).
* "2 plus the sacrificed permanent's mana value" (Broadside Bombardiers): the permanent as it last existed (608.2h).
* "Discard a card at random" is the table's randomness, recorded as the move: a replay repeats it.

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
from tests.test_rules_wave4h_activation_costs import activate
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip

EXTRA = [
    card("Wolf of Devil's Breach", set_code='tst', number='M1', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Creature — Elemental Wolf', oracle_text="Whenever this creature attacks, you may pay {1}{R} and discard a card. If you do, this creature deals damage to target creature or planeswalker equal to the discarded card's mana value.", power='5', toughness='5', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Mercurial Chemister', set_code='tst', number='M2', mana_cost='{3}{U}{R}', cmc=5.0, type_line='Creature — Human Wizard', oracle_text="{U}, {T}: Draw two cards.\n{R}, {T}, Discard a card: This creature deals damage to target creature equal to the discarded card's mana value.", power='2', toughness='3', colors=['R', 'U'], color_identity=['R', 'U']),  # noqa: E501
    card('Pyromancy', set_code='tst', number='M3', mana_cost='{2}{R}{R}', cmc=4.0, type_line='Enchantment', oracle_text='{3}, Discard a card at random: This enchantment deals damage to any target equal to the mana value of the discarded card.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Broadside Bombardiers', set_code='tst', number='M4', mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Goblin Pirate', oracle_text="Menace, haste\nBoast — Sacrifice another creature or artifact: This creature deals damage equal to 2 plus the sacrificed permanent's mana value to any target. (Activate only if this creature attacked this turn and only once each turn.)", power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=['Boast', 'Haste', 'Menace']),  # noqa: E501
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
    from app.rules import scripts

    assert scripts.parse_effects("~ deals damage to target creature equal to the discarded card's mana value.") is not None
    # a discard that is neither the cost nor an instruction before it names no card (the ability stays manual)
    from app.rules.characteristics import Characteristics, parse_abilities

    for text in ("{T}: Draw a card. ~ deals damage to target creature equal to the discarded card's mana value.",
                 "{T}, Discard two cards: ~ deals damage to target creature equal to the discarded card's mana value.",
                 "Whenever you cast a spell, ~ deals damage to any target equal to the discarded card's mana value."):
        ch = Characteristics(name="X", types=frozenset({"Enchantment"}), oracle_text=text, abilities=tuple(parse_abilities(text)))
        assert scripts.definitions(ch) == {}, text


def tok(s, pid, name, pt_, type_line="Token Creature — Test", text=""):
    p, t = pt_.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t, "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def test_pyromancy_deals_the_mana_value_of_the_card_discarded_at_random(cards):
    s = build(cards, p1=("Pyromancy", "Lightning Bolt"))
    put(s, "Pyromancy", "battlefield")
    for c in list(s.state.zones["p1:hand"]):  # (only the Bolt stays in hand: the random choice has one answer)
        act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "library"})
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=3)
    activate(s, find(s, "Pyromancy"), "{3}, Discard", targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and s.state.players["p2"].life == 40 - 1  # Lightning Bolt: mana value 1
    roundtrip(s)


def test_mercurial_chemister_reads_the_card_it_was_paid_with(cards):
    s = build(cards, p1=("Mercurial Chemister", "Bonecrusher Giant", "Lightning Bolt"))
    chem = put(s, "Mercurial Chemister", "battlefield")
    big = tok(s, "p2", "Ogre", "9/9")
    giant = put(s, "Bonecrusher Giant", "hand")
    put(s, "Lightning Bolt", "hand")
    # a creature that just came under control can't use {T}: play on to Alice's next turn
    for _ in range(300):
        d = s.state.rules.decision
        if s.state.turn.number >= 3 and s.state.turn.phase == "main1" and d is None:
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    mana(s, R=1)
    activate(s, chem, "{R}, {T}, Discard", targets=[big.id])
    answer(s, pick=giant.id)  # the card to discard (a choice: 601.2b)
    pass_until_stack_empty(s)
    assert s.state.cards[giant.id].zone == "p1:graveyard"
    assert s.state.cards[big.id].damage == 3  # Bonecrusher Giant: mana value 3 (a split-style card, its whole mana value)
    roundtrip(s)


def attack_with(s, attackers, blocker=True):
    """On to Alice's declare-attackers decision, declare, and stop at Bob's blockers (he has a wall to be asked with)."""
    for _ in range(300):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])


def test_broadside_bombardiers_boast_adds_two_to_the_sacrificed_mana_value(cards):
    s = build(cards, p1=("Broadside Bombardiers", "Grizzly Bears"))
    ship = put(s, "Broadside Bombardiers", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield")  # mana value 2
    wall = tok(s, "p2", "Wall", "0/9")
    attack_with(s, [ship])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker": wall.id, "attacker": ship.id}]) if False else None
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_blockers"
    act(s, "p2", type="declare_blockers", blocks=[])
    for _ in range(20):
        if s.state.rules.decision is None and s.state.rules.priority == "p1":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    activate(s, ship, "Boast", targets=["p2"])
    answer(s, pick=bears.id)
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert s.state.players["p2"].life <= 40 - 4  # 2 + the Bears' mana value 2 (combat damage may add to it)
    roundtrip(s)
