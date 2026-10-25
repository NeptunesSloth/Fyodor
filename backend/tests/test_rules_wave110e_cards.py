"""Wave 110E: single-card builds on real Oracle text; every scenario checks the replay and a save and a load.

* Garruk, Savage Herald: -7 grants the 510.1c permission to creatures for the turn (a quoted static the granting layer now reads).
* Spin into Myth: 701.29a fateseal 2 (look at the top two cards of an opponent's library, any to the bottom, the rest back on top in any order).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_designations import put as put3
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, mana, put, to_hand

EXTRA = [
    real("Garruk, Savage Herald", "{4}{G}{G}", 6, "Legendary Planeswalker — Garruk",
         "+1: Reveal the top card of your library. If it's a creature card, put it into your hand. Otherwise, put it on the bottom of your library.\n"
         "−2: Target creature you control deals damage equal to its power to another target creature.\n"
         "−7: Until end of turn, creatures you control gain \"You may have this creature assign its combat damage as though it weren't blocked.\"", None, "G"),
    real("Spin into Myth", "{3}{U}", 4, "Instant",
         "Put target creature on top of its owner's library, then fateseal 2. (To fateseal 2, look at the top two cards of an opponent's library, then put any number of them on the bottom of that player's library and the rest on top in any order.)", None, "U"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA.append(real("Shivan Dragon", "{4}{R}{R}", 6, "Creature — Dragon", "Flying\n{R}: Shivan Dragon gets +1/+0 until end of turn.", ("5", "5"), "R"))


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def test_spin_into_myth_fateseals_two(cards):
    s = build(cards, ["Spin into Myth", "Shivan Dragon"])
    elf = put(s, "Shivan Dragon")
    lib = list(s.state.zones["p2:library"])
    mana(s, U=1, C=3)
    cast(s, "Spin into Myth", [elf.id])
    seen = []
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        assert d.player == "p1"  # only the fatesealing player is asked (and sees the cards)
        ids = [o.id for o in d.options]
        seen.append(d.kind)
        pick = [lib[0]] if lib[0] in ids and "bottom" not in seen else ids[: max(1, d.min_choices)]
        act(s, "p1", type="choose", decision_id=d.id, option_ids=pick)
    assert s.state.cards[elf.id].zone == "p1:library" and s.state.zones["p1:library"][0] == elf.id  # 701.29a, top of its owner's library
    assert sorted(s.state.zones["p2:library"]) == sorted(lib)  # same cards, only reordered
    assert s.state.zones["p2:library"][-1] == lib[0]  # first card went to the bottom
    check(s)


@pytest.mark.parametrize("grant", [True, False])
def test_garruk_minus_seven_lets_blocked_creatures_assign_as_unblocked(cards, grant):
    from tests.test_rules_group_unblocked import finish_combat, start_combat
    from tests.test_rules_shared_damage_choices import table
    from tests.test_rules_wave30m_durations import to_phase

    s = table(cards, ["Garruk, Savage Herald", "Grizzly Bears"])
    to_phase(s, "main1", turn=1)
    bears = put3(s, "Grizzly Bears", "battlefield")
    to_phase(s, "main1", turn=4)  # (no longer summoning sick)
    garruk = put3(s, "Garruk, Savage Herald", "battlefield")
    act(s, "p1", type="set_counter", card_id=garruk.id, kind="loyalty", value=7)
    if grant:
        act(s, "p1", type="activate_ability", card_id=garruk.id, ability=2)
        while s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    before = set(s.state.cards)
    act(s, "p2", type="create_token", player="p2", token={"name": "Wall", "type_line": "Token Creature — Wall", "power": "0", "toughness": "10"})
    wall = next(c for cid, c in s.state.cards.items() if cid not in before)
    start_combat(s, [bears], [wall])
    assert finish_combat(s) == ([bears.id] if grant else [])  # 510.1c: asked only while the grant lasts
    assert s.state.players["p2"].life == (38 if grant else 40)
    check(s)
