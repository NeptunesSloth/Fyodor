"""A board wipe under Blood Artist and Falkenrath Noble (with Teysa Karlov doubling death triggers): every trigger targets a player
(603.3d: chosen as it is put on the stack). Break-it playtest B3: 136 one-by-one prompts. Each prompt now also offers the same target
for all the identical triggers of that ability waiting with it ("Bob — same for all N"); a plain answer still answers just the one.
Real Oracle text (Scryfall); each scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

EXTRA = [
    real("Teysa Karlov", "{2}{W}{B}", 4, "Legendary Creature — Human Advisor", "If a creature dying causes a triggered ability of a permanent you control "
         "to trigger, that ability triggers an additional time.\nCreature tokens you control have vigilance and lifelink.", ("2", "4"), "WB"),
    real("Blood Artist", "{1}{B}", 2, "Creature — Vampire", "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.",
         ("0", "1"), "B"),
    real("Zulaport Cutthroat", "{1}{B}", 2, "Creature — Human Rogue Ally", "Whenever this creature or another creature you control dies, each opponent loses 1 "
         "life and you gain 1 life.", ("1", "1"), "B"),
    real("Falkenrath Noble", "{3}{B}", 4, "Creature — Vampire Noble", "Flying\nWhenever this creature or another creature dies, target player loses 1 life "
         "and you gain 1 life.", ("2", "2"), "B"),
]
MINE = ["Teysa Karlov", "Blood Artist", "Zulaport Cutthroat", "Falkenrath Noble", "Wrath of God"]
GOBLINS = 1  # (Bob, at 40 life, survives the drain: 34)


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _wrath(cards):
    s = build(cards, MINE, ["Grizzly Bears"])
    for name in MINE[:-1]:
        put(s, name)
    put(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="create_token", player="p1", count=GOBLINS,
        token={"name": "Goblin", "type_line": "Token Creature — Goblin", "power": "1", "toughness": "1", "colors": ["R"]})
    to_hand(s, "Wrath of God")
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Wrath of God").id)
    return s


def _play_out(s, pick):
    """Resolve everything; ``pick(decision)`` answers each target prompt. Returns the target prompts asked."""
    asked = []
    for _ in range(400):
        d = s.state.rules.decision
        if d is not None and d.prompt.endswith("choose a target"):
            asked.append(d)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick(d)])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


def test_same_target_for_all_asks_once_per_ability(cards):
    s = _wrath(cards)
    life = s.state.players["p2"].life
    asked = _play_out(s, lambda d: next(o.id for o in d.options if o.id == "all:p2"))
    assert [d.prompt for d in asked] == ["Blood Artist: choose a target", "Falkenrath Noble: choose a target"] \
        or sorted(d.prompt for d in asked) == ["Blood Artist: choose a target", "Falkenrath Noble: choose a target"]
    first = asked[0]
    assert [o.id for o in first.options][:2] == ["p1", "p2"]  # (the plain answers first)
    deaths = 4 + GOBLINS + 1  # (Alice's four creatures, the Goblins, Bob's Grizzly Bears)
    mine = 4 + GOBLINS
    per_ability = 2 * deaths  # (Teysa Karlov: a death triggers each ability an additional time)
    assert any(o.label == f"Bob — same for all {per_ability}" for o in first.options)
    # Blood Artist and Falkenrath Noble (each death, twice) and Zulaport Cutthroat (Alice's creatures, twice): all at Bob
    assert s.state.players["p2"].life == life - 2 * per_ability - 2 * mine
    check(s)


def test_the_turn_clock_never_aims_the_drain_at_the_timed_out_player(cards):
    # stage 3 turn clock (final fix C1): Alice timed out; the clock answers her target prompts, "same for all" ones included
    from app.game.clock_defaults import answers

    s = _wrath(cards)
    life = s.state.players["p1"].life
    picked = []
    asked = _play_out(s, lambda d: picked.append(answers(s.state, d.player, s.cards)[0]["option_ids"][0]) or picked[-1])
    assert "all:p1" in {o.id for o in asked[0].options}  # (several copies waiting: the same-for-all answers were offered)
    assert picked and not {"p1", "all:p1"} & set(picked)
    deaths, mine = 4 + GOBLINS + 1, 4 + GOBLINS
    assert s.state.players["p1"].life == life + 2 * (2 * deaths) + 2 * mine  # (every drain gains, none aimed at herself)
    check(s)


def test_a_plain_answer_still_answers_one_trigger(cards):
    s = _wrath(cards)
    asked = _play_out(s, lambda d: "p2")
    assert len(asked) == 2 * 2 * (4 + GOBLINS + 1)  # (each trigger asked on its own, as before)
    check(s)
