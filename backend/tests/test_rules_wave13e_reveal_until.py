"""Wave 13E: reveal-until wordings the wave 3R5 look/reveal grammar didn't read: "you may reveal cards from the top of your
library until you reveal a land card. If you do, put that card onto the battlefield and put all other cards revealed this way into
your graveyard." (Avenging Druid) and "…, then shuffle the rest into your library" / "shuffle all other cards revealed this way
into your library" (Aspiring Champion, Thicket Elemental). Researched against CR 2026-09-25: 701.20b the revealed cards stay in the
library, so shuffling "the rest into your library" is a shuffle of it.
"""

from __future__ import annotations

import pytest

from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import attack, combat_step, sandbox, to_hand
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave9b_exile_permission import roundtrip

EXTRA = [
    card('Avenging Druid', set_code="tst", number="R02", mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Human Druid', oracle_text="Whenever this creature deals damage to an opponent, you may reveal cards from the top of your library until you reveal a land card. If you do, put that card onto the battlefield and put all other cards revealed this way into your graveyard.", power='2', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Aspiring Champion', set_code="tst", number="R03", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Human Warrior', oracle_text="Ruinous Ascension — When this creature deals combat damage to a player, sacrifice it. If you do, reveal cards from the top of your library until you reveal a creature card. Put that card onto the battlefield, then shuffle the rest into your library.", power='3', toughness='3', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Thicket Elemental', set_code="tst", number="R04", mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Elemental', oracle_text="Kicker {3}{G}\nWhen this creature enters, if it was kicked, you may reveal cards from the top of your library until you reveal a creature card. If you do, put that card onto the battlefield and shuffle all other cards revealed this way into your library.", power='4', toughness='4', colors=['G'], color_identity=['G'], keywords=['Kicker']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_wording_is_exact():
    ok = scripts.parse_effects("Reveal cards from the top of your library until you reveal a creature card. Put that card onto the "
                               "battlefield, then shuffle the rest into your library.")
    assert ok is not None and [e["do"] for e in ok[0]] == ["look_top", "pick_looked", "shuffle_library"]
    for text in ("Reveal cards from the top of your library until you reveal a creature card. If you do, put that card onto the "
                 "battlefield.",  # ("if you do" with no optional reveal before it: not read)
                 "Reveal cards from the top of your library until you reveal a creature card. Put that card onto the battlefield, "
                 "then shuffle the rest into your graveyard."):
        assert scripts.parse_effects(text) is None, text


def druid_attacks(cards, answer_yes):
    s = sandbox(cards, "Avenging Druid")
    druid = to_hand(s, "Avenging Druid")
    act(s, "p1", type="move", card_ids=[druid.id], to={"player": "p1", "zone": "battlefield"})
    top = s.state.zones["p1:library"][:2]
    combat_step(s)
    attack(s, (druid, "p2"))
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[ids[0] if answer_yes else ids[-1]])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return s, top


def test_avenging_druid_puts_the_land_onto_the_battlefield(cards):
    s, top = druid_attacks(cards, True)
    assert s.state.cards[top[0]].zone == "p1:battlefield" and s.state.cards[top[0]].name == "Forest"
    assert s.state.cards[top[1]].zone == "p1:library"  # (revealing stopped at the first land)
    replay_matches(s)
    roundtrip(s)


def test_avenging_druid_declined_reveals_nothing(cards):
    s, top = druid_attacks(cards, False)
    assert all(s.state.cards[c].zone == "p1:library" for c in top)
    replay_matches(s)
