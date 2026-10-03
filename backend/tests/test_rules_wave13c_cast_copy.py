"""Casting a copy of a card (wave 13C), against the stored Comprehensive Rules (2026-09-25): 707.12 (an effect that
instructs a player to cast a copy of an object follows 601.2a-h, the copy created in the zone the object is in and cast
while another ability is resolving; once cast it is a spell that can resolve or be countered), 707.12a (several copies:
each one is cast or not individually), 704.5e (a copy of a card outside the stack and battlefield ceases to exist),
608.3f / 707.10f (a copy of a permanent spell becomes a token as it resolves), 118.9 / 107.3b (without paying its mana
cost). Real Oracle text of Mnemonic Deluge, Renegade Bull and Shiko, Paragon of the Way."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.characteristics import printed_from_data
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches

REAL = [
    card("Mnemonic Deluge", set_code="tst", number="R1301", mana_cost="{6}{U}{U}{U}", cmc=9.0, type_line="Sorcery", colors=["U"],
         color_identity=["U"], oracle_text="Exile target instant or sorcery card from a graveyard. Copy that card three times. You "
         "may cast the copies without paying their mana costs. Exile Mnemonic Deluge."),
    card("Renegade Bull", set_code="tst", number="R1302", mana_cost="{4}{R}", cmc=5.0, type_line="Creature — Ox", colors=["R"],
         color_identity=["R"], power="0", toughness="5", keywords=["Trample"], oracle_text="Trample\nWhenever you cast an instant or "
         "sorcery spell, this creature gets +X/+0 until end of turn, where X is that spell's mana value.\nWhenever this creature "
         "attacks, exile up to one target instant or sorcery card from your graveyard and copy it. You may cast the copy without "
         "paying its mana cost."),
    card("Shiko, Paragon of the Way", set_code="tst", number="R1303", mana_cost="{2}{U}{R}{W}", cmc=5.0,
         type_line="Legendary Creature — Spirit Dragon", colors=["R", "U", "W"], color_identity=["R", "U", "W"], power="4",
         toughness="5", keywords=["Flying", "Vigilance"], oracle_text="Flying, vigilance\nWhen Shiko enters, exile target nonland card "
         "with mana value 3 or less from your graveyard. Copy it, then you may cast the copy without paying its mana cost. (A copy "
         "of a permanent spell becomes a token.)"),
]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, c["name"]) for c in REAL] + [(2, "Lightning Bolt"), (2, "Grizzly Bears"), (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Grizzly Bears"), (20, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def put(s, name, where, pid="p1", nth=0):
    c = [c for c in s.state.cards.values() if c.name == name and c.owner == pid][nth]
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": where, "player": pid})
    return s.state.cards[c.id]


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def step(s):
    d = s.state.rules.decision
    return (d.resume or {}).get("step") if d is not None else None


def test_wordings_are_full():
    for c in REAL:
        feats = coverage.features_of(printed_from_data(c, 0))
        assert all(f.supported for f in feats), (c["name"], [f.label for f in feats if not f.supported])


def test_mnemonic_deluge_casts_each_copy_individually_and_the_copies_cease_to_exist(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    deluge = put(s, "Mnemonic Deluge", "hand")
    mana(s, U=9)
    act(s, "p1", type="cast_spell", card_id=deluge.id, targets=[bolt.id])
    pass_until_stack_empty(s)
    assert step(s) == "free_cast_pick"
    assert s.state.cards[bolt.id].zone == "p1:exile"
    copies = [c for c in s.state.cards.values() if c.is_token and c.copy_of is not None and c.zone == "p1:exile"]
    assert len(copies) == 3 and {c.name for c in copies} == {"Lightning Bolt"}  # 707.12: made in the card's zone
    first = copies[0]
    choose(s, [first.id])
    choose(s, ["p2"])  # Bolt's target
    assert s.state.cards[first.id].zone == "stack" and step(s) == "free_cast_pick"  # 707.12: a spell on the stack, the next copy next
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {c.id for c in copies[1:]}
    choose(s, [])  # 707.12a: the second copy isn't cast
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37
    assert not [c for c in s.state.cards.values() if c.is_token and c.copy_of is not None]  # 704.5e: none left anywhere
    assert s.state.cards[deluge.id].zone == "p1:exile"
    assert s.state.cards[bolt.id].zone == "p1:exile"
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def test_shiko_copy_of_a_permanent_spell_becomes_a_token(cards):
    s = build(cards)
    bears = put(s, "Grizzly Bears", "graveyard")
    shiko = put(s, "Shiko, Paragon of the Way", "hand")
    mana(s, U=1, R=1, W=1, G=2)
    act(s, "p1", type="cast_spell", card_id=shiko.id)
    pass_until_stack_empty(s)
    if step(s) not in ("free_cast_pick", None):
        choose(s, [bears.id])
        pass_until_stack_empty(s)
    assert step(s) == "free_cast_pick"
    copy = next(c for c in s.state.cards.values() if c.is_token and c.copy_of is not None)
    assert s.state.cards[bears.id].zone == "p1:exile" and copy.zone == "p1:exile"
    choose(s, [copy.id])
    pass_until_stack_empty(s)
    made = s.state.cards[copy.id]
    assert made.zone == "p1:battlefield" and made.is_token and made.name == "Grizzly Bears"  # 608.3f
    replay_matches(s)
    replay_matches(GameSession(s.history.rebuild(), cards=s.cards))


def test_a_copy_not_cast_ceases_to_exist(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    deluge = put(s, "Mnemonic Deluge", "hand")
    mana(s, U=9)
    act(s, "p1", type="cast_spell", card_id=deluge.id, targets=[bolt.id])
    pass_until_stack_empty(s)
    choose(s, [])
    pass_until_stack_empty(s)
    assert not [c for c in s.state.cards.values() if c.copy_of is not None]
    assert s.state.players["p2"].life == 40
    replay_matches(s)
