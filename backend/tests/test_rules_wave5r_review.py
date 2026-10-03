"""Wave 5R: the independent review of wave 5 (CR 2026-09-25): regressions for what it found, and the seams where
wave-5 features meet. Cards carry their real Oracle text from the card database (made-up cards are named "Probe")."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import creature, life, on_field, pick, settle, to_hand, until_asked
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    # (no real spell has this exact wording yet; Hypothesizzle's "Then you may discard a nonland card." stays manual)
    card('Probe Reflexive Spell', set_code="tst", number="R1", mana_cost='{1}{R}', cmc=2.0, type_line='Sorcery',
         oracle_text='Draw a card. You may sacrifice a creature. When you do, Probe Reflexive Spell deals 4 damage to target creature.',
         colors=['R'], color_identity=['R']),
    card('Hypothesizzle', set_code="tst", number="R2", mana_cost='{3}{U}{R}', cmc=5.0, type_line='Instant',
         oracle_text='Draw two cards. Then you may discard a nonland card. When you do, Hypothesizzle deals 4 damage to target creature.',
         colors=['R', 'U'], color_identity=['R', 'U']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (12, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (12, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def roundtrip(s):
    replay_matches(s)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


# -- 5G: a reflexive trigger with a target inside a spell (603.12) ------------------------------------------------------
def test_reflexive_target_in_a_spell_no_longer_crashes_coverage(cards):
    # (an IndexError: the reflexive ability's "target" was renumbered as one of the spell's own target groups)
    assert coverage.of_card_data(cards.resolve("Probe Reflexive Spell")).level == "FULL"
    assert coverage.of_card_data(cards.resolve("Hypothesizzle")).level != "FULL"


def test_reflexive_target_in_a_spell_chooses_its_target_when_it_triggers(cards):
    s = build(cards, p1=("Probe Reflexive Spell",))
    spell = to_hand(s, "Probe Reflexive Spell")
    mine = creature(s, "p1", "Fodder")
    theirs = creature(s, "p2", "Victim", pt="4/4")
    mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    roundtrip(s)
    assert [o.id for o in d.options] == ["pay", "decline"]
    pick(s, "pay")
    steps = []
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        steps.append((d.kind, [o.id for o in d.options]))
        ids = [o.id for o in d.options]
        pick(s, mine.id if mine.id in ids else theirs.id if theirs.id in ids else ids[0])
    assert steps == [("choose_one", [theirs.id])]  # (the only creature to sacrifice; the target asked as it triggers)
    assert mine.id not in s.state.cards and theirs.id not in s.state.cards  # (tokens: gone)
    roundtrip(s)


def test_reflexive_spell_declined_deals_no_damage(cards):
    s = build(cards, p1=("Probe Reflexive Spell",))
    spell = to_hand(s, "Probe Reflexive Spell")
    mine = creature(s, "p1", "Fodder")
    theirs = creature(s, "p2", "Victim", pt="4/4")
    mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    until_asked(s)
    pick(s, "decline")
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:battlefield" and s.state.cards[theirs.id].zone == "p2:battlefield"
    roundtrip(s)
