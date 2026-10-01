"""Wave 4J: leftovers that were manual on purpose (docs/CURRENT_STATE.md). Researched against CR 2026-09-25.

* Reflexive triggers that read the sacrificed object (603.12, 608.2h, 113.7a): "you may sacrifice another creature.
  When you do, ~ deals damage equal to that creature's power to any target" — the sacrificed creature's last known
  information is the reflexive trigger's event object.

Every scenario uses real Oracle text and checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, life, to_hand
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card("Heart-Piercer Manticore", set_code="tst", number="J401", mana_cost="{2}{R}{R}", cmc=4.0,
         type_line="Creature — Manticore",
         oracle_text="When this creature enters, you may sacrifice another creature. When you do, this creature deals "
                     "damage equal to that creature's power to any target.\nEmbalm {5}{R} ({5}{R}, Exile this card from "
                     "your graveyard: Create a token that's a copy of it, except it's a white Zombie Manticore with no "
                     "mana cost. Embalm only as a sorcery.)",
         power="4", toughness="3", colors=["R"], color_identity=["R"], keywords=["Embalm"]),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def creature(s, pid, name, power="2", toughness="2"):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Bear",
                                                        "power": power, "toughness": toughness, "text": ""})
    return named(s, name, pid)


def answer(s, ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)


def roundtrip(s):
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def drive(s, pick, limit=40):
    """Pass priority and answer decisions with ``pick(decision)`` until the stack is empty and nothing waits."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack") and not s.state.rules.pending_triggers:
            return
        if d is not None:
            answer(s, pick(d))
        else:
            act(s, s.state.rules.priority, type="pass_priority")


# -- reflexive triggers reading the sacrificed object (603.12, 608.2h) ----------------------------------------
@pytest.mark.parametrize("pay", [True, False])
def test_reflexive_reads_the_sacrificed_creatures_power(cards, pay):
    """Heart-Piercer Manticore: Alice sacrifices a 5/1 — the reflexive ability, put on the stack afterwards, deals 5
    (the creature's power as it last existed on the battlefield) to Bob. Declined: nothing triggers."""
    s = build(cards, "Heart-Piercer Manticore")
    fodder = creature(s, "p1", "Fodder", power="5", toughness="1")
    manticore = to_hand(s, "Heart-Piercer Manticore")
    mana(s, R=4)
    act(s, "p1", type="cast_spell", card_id=manticore.id)

    def pick(d):
        ids = [o.id for o in d.options]
        if "pay" in ids:
            return ["pay" if pay else "decline"]
        if fodder.id in ids:
            return [fodder.id]
        if "p2" in ids:
            return ["p2"]
        return ids[: max(1, d.min_choices)]

    drive(s, pick)
    assert life(s, "p2") == (35 if pay else 40)
    assert (s.state.cards[fodder.id].zone.endswith("battlefield") if fodder.id in s.state.cards else False) is not pay
    replay_matches(s)
    roundtrip(s)


def test_reflexive_lki_wording_scope():
    """Only the stat phrases about the one sacrificed object are read; another mention of it stays manual."""
    from app.rules import scripts

    ok = scripts.parse_effects("You may sacrifice another creature. When you do, ~ deals damage equal to the sacrificed "
                               "creature's power to target creature.")
    assert ok is not None and ok[0][-1]["lki"] == "pay0"
    assert ok[0][-1]["ability"]["effects"][0]["n"] == {"power": "event"}
    # Surtland Flinger: "If the sacrificed creature was a Giant, … instead" — not read
    assert scripts.parse_effects("You may sacrifice another creature. When you do, ~ deals damage equal to the "
                                 "sacrificed creature's power to any target. If the sacrificed creature was a Giant, ~ "
                                 "deals twice that much damage instead.") is None
    # several objects: not one creature's power
    assert scripts.parse_effects("You may sacrifice two creatures. When you do, ~ deals damage equal to that creature's "
                                 "power to any target.") is None
