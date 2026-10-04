"""Wave 17B: activated-ability wordings (CR 2026-09-25).

* "Target opponent may draw a card." (Phelddagrif): the other player decides as the ability resolves (608.2d).
* "gets -2/+2 and loses flying", "gains flying and loses trample", "loses defender and gains flying" (613.1f: one layer-6 effect).
* "has base power 4 and gains trample" (613.4b: layer 7b, power only).

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import build, on_field
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"17B-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real('Phelddagrif', '{1}{G}{W}{U}', 4, 'Legendary Creature — Phelddagrif',
         "{G}: Phelddagrif gains trample until end of turn. Target opponent creates a 1/1 green Hippo creature token.\n{W}: Phelddagrif gains flying until end of turn. Target opponent gains 2 life.\n{U}: Return Phelddagrif to its owner's hand. Target opponent may draw a card.", ('4', '4'), 'GUW'),
    real('Leering Gargoyle', '{1}{W}{U}', 3, 'Creature — Gargoyle',
         'Flying\n{T}: This creature gets -2/+2 and loses flying until end of turn.', ('2', '2'), 'UW'),
    real('Canopy Dragon', '{4}{G}{G}', 6, 'Creature — Dragon',
         'Trample\n{1}{G}: This creature gains flying and loses trample until end of turn.', ('4', '4'), 'G'),
    real('Turtle-Duck', '{G}', 1, 'Creature — Turtle Bird',
         '{3}: Until end of turn, this creature has base power 4 and gains trample.', ('0', '4'), 'G'),
    real('Gargoyle Sentinel', '{3}', 3, 'Artifact Creature — Gargoyle',
         "Defender (This creature can't attack.)\n{3}: Until end of turn, this creature loses defender and gains flying.", ('3', '3'), ''),
    real('Singing Tree', '{3}{G}', 4, 'Creature — Plant',
         '{T}: Target attacking creature has base power 0 until end of turn.', ('0', '3'), 'G'),
    real('Island of Wak-Wak', '', 0, 'Land',
         '{T}: Target creature with flying has base power 0 until end of turn.', None, ''),
    real("Grizzly Bears", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]
FULL = ["Phelddagrif", "Leering Gargoyle", "Canopy Dragon", "Turtle-Duck", "Gargoyle Sentinel", "Singing Tree", "Island of Wak-Wak"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def settle(s, pick=None, limit=30):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [pick] if pick and pick in [o.id for o in d.options] else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def ability(s, c, start):
    return next(i for i, a in enumerate(s.cards.resolve(c.name).get("oracle_text", "").split("\n")) if a.startswith(start))


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize("name", FULL)
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_target_opponent_may_draw_a_card(cards, answer):
    s = build(cards, "Phelddagrif", p2=("Grizzly Bears",))
    phel = on_field(s, "Phelddagrif")
    mana(s, "p1", U=1)
    before = len(zone(s.state, "p2", "hand"))
    act(s, "p1", type="activate_ability", card_id=phel.id, ability=ability(s, phel, "{U}"), targets=["p2"])
    settle(s, pick=answer)
    assert s.state.cards[phel.id].zone == "p1:hand"  # (returned to its owner's hand first)
    assert len(zone(s.state, "p2", "hand")) == before + (1 if answer == "yes" else 0)
    roundtrip(s)


def test_gets_and_loses_flying(cards):
    s = build(cards, "Leering Gargoyle")
    c = on_field(s, "Leering Gargoyle")
    s.state.rules.controlled_since[c.id].turn = 0  # (it has been there since before this turn began: 302.6)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{T}"))
    settle(s)
    ch = chars(s, c)
    assert ch.pt == (0, 4) and "flying" not in ch.keywords
    roundtrip(s)


def test_gains_flying_and_loses_trample(cards):
    s = build(cards, "Canopy Dragon")
    c = on_field(s, "Canopy Dragon")
    mana(s, "p1", G=2)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{1}{G}"))
    settle(s)
    ch = chars(s, c)
    assert "flying" in ch.keywords and "trample" not in ch.keywords
    roundtrip(s)


def test_loses_defender_and_gains_flying(cards):
    s = build(cards, "Gargoyle Sentinel")
    c = on_field(s, "Gargoyle Sentinel")
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{3}"))
    settle(s)
    ch = chars(s, c)
    assert "flying" in ch.keywords and "defender" not in ch.keywords
    roundtrip(s)


def test_base_power_only_and_gains_trample(cards):
    s = build(cards, "Turtle-Duck")
    c = on_field(s, "Turtle-Duck")
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability(s, c, "{3}"))
    settle(s)
    ch = chars(s, c)
    assert ch.pt == (4, 4) and "trample" in ch.keywords  # (base toughness stays 4)
    roundtrip(s)
