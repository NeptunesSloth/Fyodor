"""Wave 18D: merged permanents - mutate (CR 702.140, 730) and meld (CR 701.42, 712.4, 712.21), real Oracle text, CR 2026-09-25.

Every scenario checks the replay and a save/load round trip; the privacy test builds every viewer's table mid-decision.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave6c_tokens_pumps import chars, mana, pt, put, reloaded, to_hand
from tests.wave9c_kit import build, check, life


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"18D-{name[:9]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), keywords=[], **extra)


MUTATE_REMINDER = " (If you cast this spell for its mutate cost, put it over or under target non-Human creature you own. They mutate into the creature on top plus all abilities from under it.)"
EXTRA = [
    real("Gemrazer", "{3}{G}", 4, "Creature — Beast Mutant",
         "Mutate {1}{G}{G}" + MUTATE_REMINDER + "\nReach, trample\nWhenever this creature mutates, destroy target artifact or enchantment an opponent controls.", ("4", "4"), "G"),
    real("Glowstone Recluse", "{2}{G}", 3, "Creature — Spider Mutant",
         "Mutate {3}{G}" + MUTATE_REMINDER + "\nReach\nWhenever this creature mutates, put two +1/+1 counters on it.", ("2", "2"), "G"),
    real("Huntmaster Liger", "{3}{W}", 4, "Creature — Cat Mutant",
         "Mutate {2}{W}" + MUTATE_REMINDER + "\nWhenever this creature mutates, other creatures you control get +X/+X until end of turn, where X is the number of times this creature has mutated.", ("4", "4"), "W"),
    real("Insatiable Hemophage", "{3}{B}", 4, "Creature — Vampire Mutant",
         "Mutate {2}{B}" + MUTATE_REMINDER + "\nDeathtouch\nWhenever this creature mutates, each opponent loses X life and you gain X life, where X is the number of times this creature has mutated.", ("3", "3"), "B"),
    real("Probe Bear", "{1}{G}", 2, "Creature — Bear", "Vigilance", ("2", "2"), "G"),
    real("Probe Human", "{1}{W}", 2, "Creature — Human Soldier", "", ("2", "2"), "W"),
    real("Probe Altar", "{2}", 2, "Artifact", "", None),
    real("Probe Bolt", "{R}", 1, "Instant", "Probe Bolt deals 3 damage to any target.", None, "R"),
    real("Probe Counterspell", "{U}{U}", 2, "Instant", "Counter target spell.", None, "U"),
]
NAMES = ["Gemrazer", "Glowstone Recluse", "Huntmaster Liger", "Insatiable Hemophage"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_mutate_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def mutate_key(s, c, pid="p1"):
    from app.rules import alt_costs
    from app.rules.plan import Plan

    plan = Plan(s.state, pid, s.cards, None)
    found = [o.key for o in alt_costs.offers(s.state, pid, c, plan.ch(c), s.cards) if o.tag == "mutate"]
    return found[0] if found else None


def mutate(s, name, onto, over="over", pid="p1", **m):
    spell = to_hand(s, name, pid)
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=spell.id, targets=[onto.id], alt_cost=mutate_key(s, spell, pid))
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [over] if d.resume and d.resume.get("step") == "mutate_choice" else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return spell


def test_mutate_over_merges_and_triggers(cards):
    s = build(cards, ["Gemrazer", "Probe Bear", "Probe Altar"], ["Probe Altar"])
    bear = put(s, "Probe Bear")
    altar = put(s, "Probe Altar", "p2")
    assert mutate_key(s, to_hand(s, "Gemrazer")) is not None
    g = mutate(s, "Gemrazer", bear, G=3)
    host = s.state.cards[bear.id]
    assert g.id not in s.state.cards and host.name == "Gemrazer" and [p.name for p in host.merged] == ["Gemrazer", "Probe Bear"]
    ch = chars(s, host)
    assert pt(s, host) == (4, 4) and {"reach", "trample", "vigilance"} <= ch.keywords  # 702.140e: every ability, the top's characteristics
    assert altar.id not in s.state.zones["p2:battlefield"]  # 702.140d: the trigger destroyed it
    check(s)
