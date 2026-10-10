"""Wave 29C: no silent cap on the number of targets of a spell or an activated ability (CR 601.2c, 115.1, 107.3c).

"Up to X target …, where X is …" (Recantation), "any number of target …" (Rolling Thunder, Twinflame) and "one or more target …" (Dwarven
Song) were clamped to 20 targets: the cast and activate intents accepted at most 20, and the parser read 20 as "any number". Review 28D
lifted the cap for triggers (a decision answers with up to 250 options); casts and activations now do the same, with the intents' target
lists, the target counts, the division of a divided spell and the arrows all taking the same number (``actions.MAX_TARGETS``).
Every scenario checks the replay and a save/load round trip (wave9c_kit.check)."""

from __future__ import annotations

import pytest

from app.game import actions as A
from app.game.errors import ActionError
from app.rules import coverage, language, scripts, targets
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

REAL = [
    ("Recantation", "{3}{U}{U}", "Enchantment", "U",
     "At the beginning of your upkeep, you may put a verse counter on this enchantment.\n"
     "{U}, Sacrifice this enchantment: Return up to X target permanents to their owners' hands, where X is the number of verse counters on this enchantment."),
    ("Dwarven Song", "{R}", "Instant", "R", "One or more target creatures become red until end of turn."),
    ("Rolling Thunder", "{X}{R}{R}", "Sorcery", "R", "Rolling Thunder deals X damage divided as you choose among any number of targets."),
    ("Twinflame", "{1}{R}", "Sorcery", "R",
     "Strive — This spell costs {2}{R} more to cast for each target beyond the first.\n"
     "Choose any number of target creatures you control. For each of them, create a token that's a copy of that creature, except it has haste. "
     "Exile those tokens at the beginning of the next end step."),
]
EXTRA = [card(n, set_code="t29c", number=f"T{i:02d}", mana_cost=mc, cmc=float(sum(int(x) if x.isdigit() else 1 for x in mc.strip("{}").split("}{") if x != "X")),
              type_line=tl, oracle_text=text, colors=list(c), color_identity=list(c), keywords=[])
         for i, (n, mc, tl, c, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def foes(s, n, **kw):
    return [creature(s, "p2", f"Foe {i:02d}", **kw) for i in range(n)]


def colors_of(s, cid):
    return set(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[cid]).colors)


def test_the_intents_and_the_parser_share_one_target_limit():
    assert A.MAX_TARGETS == 250 and language.MAX_TARGETS == A.MAX_TARGETS
    ok = [f"c{i}" for i in range(A.MAX_TARGETS)]
    A.parse_action({"type": "cast_spell", "card_id": "x", "targets": ok, "target_counts": [A.MAX_TARGETS], "division": [1] * A.MAX_TARGETS})
    A.parse_action({"type": "activate_ability", "card_id": "x", "ability": 0, "targets": ok, "target_counts": [A.MAX_TARGETS]})
    A.parse_action({"type": "choose", "decision_id": "d", "option_ids": ok, "amounts": [1] * A.MAX_TARGETS})
    with pytest.raises(ValueError):
        A.parse_action({"type": "cast_spell", "card_id": "x", "targets": [*ok, "one-too-many"]})
    for text in ("Tap any number of target creatures.", "Tap one or more target creatures."):
        found = scripts.parse_effects(text)
        assert found is not None and found[1][0]["max"] == A.MAX_TARGETS, text


@pytest.mark.parametrize("name", [r[0] for r in REAL])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_recantation_asks_for_all_the_targets_its_counters_allow(cards):
    # 107.3c / 601.2c: "up to X target permanents, where X is the number of verse counters": 25 counters, 25 targets (not 20)
    s = build(cards, ["Recantation"])
    put(s, "Recantation")
    rec = card_named(s, "Recantation").id
    bears = foes(s, 25)
    act(s, "p1", type="counter", card_ids=[rec], kind="verse", delta=25)
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=rec, ability=1)
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 25 and d.min_choices == 0 and len(d.options) >= 25
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[b.id for b in bears])
    answer(s)
    assert all(b.id not in s.state.cards or not s.state.cards[b.id].zone.endswith("battlefield") for b in bears)
    check(s)


def test_arrows_to_many_targets_come_in_chunks_of_twenty(cards):
    s = build(cards, ["Recantation"])
    put(s, "Recantation")
    bears = foes(s, 45)
    plan = Plan(s.state, "p1", s.cards, None)
    plan.target_arrows(card_named(s, "Recantation").id, [b.id for b in bears])
    assert [len(a.targets) for a in plan.state.arrows] == [20, 20, 5]


def test_an_activation_may_carry_more_than_twenty_targets_and_no_more_than_x(cards):
    s = build(cards, ["Recantation"])
    put(s, "Recantation")
    rec = card_named(s, "Recantation").id
    bears = foes(s, 26)
    act(s, "p1", type="counter", card_ids=[rec], kind="verse", delta=24)
    mana(s, U=2)
    with pytest.raises(ActionError):  # (X = 24: twenty-five targets are too many)
        act(s, "p1", type="activate_ability", card_id=rec, ability=1, targets=[b.id for b in bears[:25]], target_counts=[25])
    act(s, "p1", type="activate_ability", card_id=rec, ability=1, targets=[b.id for b in bears[:24]], target_counts=[24])
    answer(s)
    assert bears[24].id in s.state.cards and s.state.cards[bears[24].id].zone.endswith("battlefield")
    assert bears[0].id not in s.state.cards or not s.state.cards[bears[0].id].zone.endswith("battlefield")
    check(s)


def test_one_or_more_target_creatures_takes_every_one_chosen(cards):
    # 115.1 / 601.2c: "one or more target creatures" has no upper bound but the legal targets
    s = build(cards, ["Dwarven Song"])
    song = to_hand(s, "Dwarven Song")
    bears = foes(s, 30)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=song.id, targets=[b.id for b in bears[:28]], target_counts=[28])
    answer(s)
    assert all("R" in colors_of(s, b.id) for b in bears[:28]) and not colors_of(s, bears[29].id)
    check(s)


def test_a_divided_spell_divides_among_more_than_twenty_targets(cards):
    # 601.2d: Rolling Thunder: X damage divided as you choose among any number of targets: 30 damage among 25 creatures
    s = build(cards, ["Rolling Thunder"])
    thunder = to_hand(s, "Rolling Thunder")
    bears = foes(s, 25, pt="1/1")
    mana(s, R=32)
    act(s, "p1", type="cast_spell", card_id=thunder.id, x_value=30, targets=[b.id for b in bears], target_counts=[25])
    d = s.state.rules.decision
    assert d is not None and d.kind == "divide" and len(d.options) == 25
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[], amounts=[2] * 5 + [1] * 20)  # (601.2d: at least 1 each, 30 in all)
    answer(s)
    assert all(b.id not in s.state.cards or not s.state.cards[b.id].zone.endswith("battlefield") for b in bears)
    check(s)


def test_a_divided_spell_given_its_division_up_front(cards):
    s = build(cards, ["Rolling Thunder"])
    thunder = to_hand(s, "Rolling Thunder")
    bears = foes(s, 22, pt="1/1")
    mana(s, R=24)
    act(s, "p1", type="cast_spell", card_id=thunder.id, x_value=22, targets=[b.id for b in bears], target_counts=[22], division=[1] * 22)
    answer(s)
    assert all(b.id not in s.state.cards or not s.state.cards[b.id].zone.endswith("battlefield") for b in bears)
    check(s)


def test_twinflame_chooses_more_than_twenty_creatures(cards):
    s = build(cards, ["Twinflame"])
    spell = to_hand(s, "Twinflame")
    mine = [creature(s, "p1", f"Mine {i:02d}") for i in range(22)]
    mana(s, R=22, C=43)  # ({1}{R} and {2}{R} more for each of the 21 targets beyond the first)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[c.id for c in mine], target_counts=[22])
    answer(s)
    assert len([c for c in s.state.cards.values() if c.zone.endswith(":battlefield") and c.name.startswith("Mine")]) == 44
    check(s)


def test_a_limit_the_engine_cannot_lift_is_said_not_hidden(cards, monkeypatch):
    # (an "up to X" with X over the limit: the prompt says what the engine takes, and why it is fewer than X)
    monkeypatch.setattr(targets, "MAX_TARGETS", 6)
    s = build(cards, ["Recantation"])
    put(s, "Recantation")
    rec = card_named(s, "Recantation").id
    foes(s, 9)
    act(s, "p1", type="counter", card_ids=[rec], kind="verse", delta=8)
    mana(s, U=1)
    act(s, "p1", type="activate_ability", card_id=rec, ability=1)
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 6
    assert "allow up to 8" in d.prompt and "at most 6" in d.prompt
    check(s)


def test_an_exact_x_over_the_limit_is_refused_not_shortened(cards, monkeypatch):
    # ("X target creatures" with X announced: fewer targets than X would be a different spell — 601.2c, 107.3a)
    monkeypatch.setattr(targets, "MAX_TARGETS", 6)
    assert targets.group_limits({"what": "any", "min": 1, "max": 250, "x_count": "exact"}, 5) == (5, 5)
    with pytest.raises(ActionError, match="at most 6"):
        targets.group_limits({"what": "any", "min": 1, "max": 250, "x_count": "exact"}, 9)
    assert targets.group_limits({"what": "any", "min": 0, "max": 250, "x_count": "upto"}, 9) == (0, 6)
