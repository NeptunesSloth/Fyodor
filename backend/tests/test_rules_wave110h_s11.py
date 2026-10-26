"""Wave 110H session 11: real Oracle text, each scenario checks replay and a save/load round trip.

* Ultra Magnus, Tactician: the put creature enters tapped and attacking; "If you do" it converts (701.28, transform) at end of combat.
* Ultra Magnus, Armored Carrier: Formidable reads the attacking creatures' total power (8 or greater) as the trigger resolves.
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, put, to_hand
from tests.wave110b_kit import attack
from tests.wave110j_kit import ch, now

FRONT = ("More Than Meets the Eye {2}{R}{G}{W} (You may cast this card converted for {2}{R}{G}{W}.)\nWard {2}\nWhenever Ultra Magnus attacks, you may put an "
         "artifact creature card from your hand onto the battlefield tapped and attacking. If you do, convert Ultra Magnus at end of combat.")
BACK = ("Living metal (During your turn, this Vehicle is also a creature.)\nHaste\nFormidable — Whenever Ultra Magnus attacks, attacking creatures you control "
        "gain indestructible until end of turn. If those creatures have total power 8 or greater, convert Ultra Magnus.")
MAGNUS = card("Ultra Magnus, Tactician // Ultra Magnus, Armored Carrier", set_code="tst", number="110H-um", layout="transform", mana_cost="{4}{R}{G}{W} // ", cmc=7.0,
              type_line="Legendary Artifact Creature — Robot // Legendary Artifact — Vehicle", power="7", toughness="7", colors=["G", "R", "W"],
              color_identity=["G", "R", "W"], keywords=["Living metal", "Haste", "Convert", "More Than Meets the Eye", "Ward", "Formidable"],
              oracle_text=FRONT + "\n//\n" + BACK,
              card_faces=[{"name": "Ultra Magnus, Tactician", "mana_cost": "{4}{R}{G}{W}", "type_line": "Legendary Artifact Creature — Robot", "oracle_text": FRONT,
                           "power": "7", "toughness": "7", "colors": ["G", "R", "W"]},
                          {"name": "Ultra Magnus, Armored Carrier", "mana_cost": "", "type_line": "Legendary Artifact — Vehicle", "oracle_text": BACK,
                           "power": "4", "toughness": "7", "colors": ["G", "R", "W"]}])
NAME = MAGNUS["name"]
EXTRA = [MAGNUS, real("Test Golem", "{3}", 3, "Artifact Creature — Golem", "", ("3", "3"), ""), real("Test Brute", "{4}{R}", 5, "Creature — Ogre", "", ("4", "4"), "R")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_full():
    assert coverage.of_card_data({**MAGNUS, "faces": MAGNUS["card_faces"]}).level == "FULL"


def _drain(s):
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_blockers":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif d is not None:
            act(s, d.player, type="declare_blockers", blocks=[])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


@pytest.mark.parametrize("put_it", [True, False])
def test_tactician_converts_only_if_a_creature_was_put(cards, put_it):
    """508.4 / 603.12 / 701.28: the artifact creature enters tapped and attacking; Magnus converts at end of combat only if one entered."""
    s = build(cards, [NAME, "Test Golem"])
    magnus = put(s, NAME)
    golem = to_hand(s, "Test Golem") if put_it else None
    attack(s, magnus)
    _drain(s)
    assert (now(s, magnus).face == 1) == put_it
    if put_it:
        assert now(s, golem).zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize(("extra_power", "converts"), [(True, True), (False, False)])
def test_formidable_converts_at_eight_total_power(cards, extra_power, converts):
    """Formidable: attacking creatures gain indestructible; at total power 8 or greater (the 4/7 Vehicle and a 4/4) it converts."""
    s = build(cards, [NAME, "Test Brute"])
    magnus = put(s, NAME)
    act(s, "p1", type="set_face", card_id=magnus.id, face=1)
    attackers = [magnus]
    if extra_power:
        attackers.append(put(s, "Test Brute"))
    attack(s, *attackers)
    _drain(s)
    assert (now(s, magnus).face == 0) == converts
    assert "indestructible" in ch(s, magnus).keywords
    check(s)
