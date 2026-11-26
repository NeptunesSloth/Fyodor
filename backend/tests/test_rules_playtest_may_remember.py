"""A remembered answer to a "you may" (603.5) sticks for that ability: Niv-Mizzet, Parun with Curiosity attached (break-it playtest B2).
"Always" keeps the answer given (yes or no) for every later trigger of the same ability; "Same answer this turn" keeps a No as a No.
The key is the source card's ability (its index), not one trigger's data. Real Oracle text (Scryfall); replay and a save and a load."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

NIV = "Niv-Mizzet, Parun"
CURIOSITY = "Curiosity"
EXTRA = [
    real(NIV, "{U}{U}{U}{R}{R}{R}", 6, "Legendary Creature — Dragon Wizard", "This spell can't be countered.\nFlying\nWhenever you draw a "
         "card, Niv-Mizzet deals 1 damage to any target.\nWhenever a player casts an instant or sorcery spell, you draw a card.", ("5", "5"), "UR"),
    real(CURIOSITY, "{U}", 1, "Enchantment — Aura", "Enchant creature\nWhenever enchanted creature deals damage to an opponent, you may draw a card.",
         None, "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _loop(s, answer, remember, rounds=4):
    """Bolt Bob; aim each Niv-Mizzet ping at Bob; answer the first Curiosity prompt with ``answer`` (and ``remember``). Returns how many
    Curiosity prompts were asked over ``rounds`` damage events."""
    niv = put(s, NIV)
    cur = put(s, CURIOSITY)
    act(s, "p1", type="attach", card_ids=[cur.id], to=niv.id)
    to_phase(s, "main1", turn=3)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    bolt = card_named(s, "Lightning Bolt")
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    asked, pings = 0, 0
    for _ in range(200):
        d = s.state.rules.decision
        if d is not None:
            if d.prompt.startswith(CURIOSITY):
                asked += 1
                pings += 1
                if pings > rounds:
                    act(s, d.player, type="choose", decision_id=d.id, option_ids=["no"])
                    continue
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer], **({"remember": remember} if asked == 1 else {}))
                continue
            bob = next((o.id for o in d.options if o.id == "p2" or o.label == "Bob"), None)
            if bob is not None:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[bob])
                continue
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            if pings > rounds:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return asked, pings


def test_always_yes_sticks_across_the_loop(cards):
    s = build(cards, [NIV, CURIOSITY, "Lightning Bolt"])
    hand = len(s.state.zones["p1:hand"])
    asked, _ = _loop(s, "yes", "always_yield")
    assert asked == 1  # (one question; every later Curiosity trigger draws on its own)
    assert len(s.state.zones["p1:hand"]) > hand + 2
    check(s)


def test_same_answer_this_turn_keeps_a_no(cards):
    s = build(cards, [NIV, CURIOSITY, "Lightning Bolt"])
    asked, _ = _loop(s, "no", "yes_this_turn")
    assert asked == 1
    prefs = s.state.rules.prefs_for("p1")
    assert any(y.kind == "no_this_turn" for y in prefs.yields)
    check(s)


def test_the_key_is_the_ability_not_the_trigger(cards):
    from app.rules import effects

    s = build(cards, [NIV, CURIOSITY, "Lightning Bolt"])
    _loop(s, "yes", "always_yield", rounds=2)
    keys = {y.key for y in s.state.rules.prefs_for("p1").yields}
    cur = card_named(s, CURIOSITY)
    assert keys == {f"may:{cur.id}:1"}
    assert effects.may_key  # (the helper the prompt and the memory share)
