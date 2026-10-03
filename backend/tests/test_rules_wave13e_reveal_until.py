"""Wave 13E: "Reveal cards from the top of your library until you reveal a creature card. Put that card onto the battlefield
and put all other cards revealed this way into your graveyard." (Gamekeeper, Avenging Druid, Aspiring Champion, Thicket
Elemental), researched against CR 2026-09-25 (701.20: revealed cards stay in the library until moved; revealed to everyone).
"""

from __future__ import annotations

import pytest

from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import attack, combat_step, sandbox, through_combat, to_hand
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip

EXTRA = [
    card('Gamekeeper', set_code="tst", number="R01", mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Elf Druid', oracle_text="When this creature dies, you may exile it. If you do, reveal cards from the top of your library until you reveal a creature card. Put that card onto the battlefield and put all other cards revealed this way into your graveyard.", power='3', toughness='3', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Avenging Druid', set_code="tst", number="R02", mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Human Druid', oracle_text="Whenever this creature deals damage to an opponent, you may reveal cards from the top of your library until you reveal a land card. If you do, put that card onto the battlefield and put all other cards revealed this way into your graveyard.", power='2', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Aspiring Champion', set_code="tst", number="R03", mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Human Warrior', oracle_text="Ruinous Ascension — When this creature deals combat damage to a player, sacrifice it. If you do, reveal cards from the top of your library until you reveal a creature card. Put that card onto the battlefield, then shuffle the rest into your library.", power='3', toughness='3', colors=['G'], color_identity=['G']),  # noqa: E501
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
    ok = scripts.parse_effects("Reveal cards from the top of your library until you reveal a land card. Put that card onto the "
                               "battlefield and the rest on the bottom of your library in a random order.")
    assert ok is not None and ok[0][0]["do"] == "reveal_until" and ok[0][0]["rest"] == "bottom"
    for text in ("Reveal cards from the top of your library until you reveal X creature cards. Put those cards onto the battlefield.",
                 "Reveal cards from the top of your library until you reveal a creature card. Put that card onto the battlefield "
                 "and the rest on the bottom of your library in any order.",
                 "Reveal cards from the top of your library until you reveal a creature card. Put that card into your hand. "
                 "~ deals damage to you equal to the number of cards revealed this way."):
        assert scripts.parse_effects(text) is None, text


def test_gamekeeper_reveals_until_a_creature_and_the_rest_go_to_the_graveyard(cards):
    s = build(cards, p1=("Gamekeeper", "Ambush Viper", "Soul Warden"))
    keeper = put(s, "Gamekeeper", "battlefield")
    put(s, "Soul Warden", "library", position="top")
    put(s, "Forest", "library", position="top")
    top = list(s.state.zones["p1:library"][:3])
    forest, warden = top[0], top[1]
    act(s, "p1", type="set_damage", card_ids=[keeper.id], value=10)  # it dies (state-based actions)
    act(s, s.state.rules.priority, type="pass_priority")
    answer(s, pick=None)  # "you may exile it": yes
    assert s.state.cards[keeper.id].zone == "p1:exile"
    assert s.state.cards[forest].zone == "p1:graveyard"  # revealed, not a creature: the rest go to the graveyard
    assert s.state.cards[warden].zone == "p1:battlefield"  # the first creature card revealed
    replay_matches(s)
    roundtrip(s)


def druid_attacks(cards, answer_id):
    s = sandbox(cards, "Avenging Druid")
    druid = to_hand(s, "Avenging Druid")
    act(s, "p1", type="move", card_ids=[druid.id], to={"player": "p1", "zone": "battlefield"})
    top = s.state.zones["p1:library"][0]
    combat_step(s)
    attack(s, (druid, "p2"))
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            assert "reveal" in d.prompt.lower()
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer_id])
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    through_combat(s)
    replay_matches(s)
    return s, top


def test_avenging_druid_asks_before_revealing_and_a_no_reveals_nothing(cards):
    s, top = druid_attacks(cards, "no")
    assert s.state.cards[top].zone == "p1:library"  # nothing was revealed or moved


def test_avenging_druid_puts_the_land_onto_the_battlefield(cards):
    s, top = druid_attacks(cards, "yes")
    assert s.state.cards[top].zone == "p1:battlefield" and s.state.cards[top].name == "Forest"
    roundtrip(s)
