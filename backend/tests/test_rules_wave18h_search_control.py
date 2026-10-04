"""Wave 18H: Opposition Agent (CR 723.2): "You control your opponents while they're searching their libraries." and "While an
opponent is searching their library, they exile each card they find. You may play those cards for as long as they remain
exiled, and you may spend mana as though it were mana of any color to cast them." Built on the same mechanism as the
Mindslaver family (app/game/control.py): the search choice is the controller's, what the searcher sees is the controller's
for as long as the choice is pending (723.4), and nothing flows after it."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.visibility import SPECTATOR
from app.rules import coverage
from app.rules.view import rules_view
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import to_hand
from tests.test_rules_effects import mana
from tests.test_rules_wave18h_player_control import EXTRA, drive, roundtrip, seen_by

AGENT = [
    card("Opposition Agent", set_code="tst", number="C04", mana_cost="{2}{B}", cmc=3.0, type_line="Creature — Human Rogue", power="3", toughness="2", oracle_text="Flash\nYou control your opponents while they're searching their libraries.\nWhile an opponent is searching their library, they exile each card they find. You may play those cards for as long as they remain exiled, and you may spend mana as though it were mana of any color to cast them.", colors=["B"], color_identity=["B"], keywords=["Flash"]),  # noqa: E501
    card("Gem Tutor", set_code="tst", number="C05", mana_cost="{1}", cmc=1.0, type_line="Sorcery", oracle_text="Search your library for an artifact card, reveal it, put it into your hand, then shuffle."),  # noqa: E501
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *AGENT], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def agent_table(cards):
    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(1, "Opposition Agent"), (10, "Island")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(1, "Hidden Gem"), (1, "Gem Tutor"), (10, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(10, "Island")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_opposition_agent_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Opposition Agent")).level == "FULL"


def test_the_search_is_the_agents_controllers_the_find_is_exiled_and_playable_by_them(cards):
    s = agent_table(cards)
    agent = to_hand(s, "Opposition Agent", "p1")
    act(s, "p1", type="move", card_ids=[agent.id], to={"player": "p1", "zone": "battlefield"})
    drive(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    tutor, gem = to_hand(s, "Gem Tutor", "p2"), next(c for c in s.state.cards.values() if c.name == "Hidden Gem")
    act(s, "p2", type="move", card_ids=[gem.id], to={"player": "p2", "zone": "library"})
    own = to_hand(s, "Island", "p2")
    mana(s, "p2", C=1)
    assert own.id not in seen_by(s, "p1")
    act(s, "p2", type="cast_spell", card_id=tutor.id)  # Bob casts it himself: Alice controls him only for the search
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p2" and d.decider == "p1" and d.kind == "choose_cards"
    mine = rules_view(s.state, "p1", s.cards)["decision"]
    assert [o["label"] for o in mine["options"]] == ["Hidden Gem"] and mine["for_player"] == "p2"
    assert own.id in seen_by(s, "p1")  # 723.4: Alice sees Bob's hand while she makes his search choice ...
    for who in ("p2", "p3", SPECTATOR):  # ... and nobody else learns what is on offer
        v = rules_view(s.state, who, s.cards)["decision"]
        assert v["kind"] == "waiting" and not v.get("options")
    assert gem.id not in seen_by(s, "p3") and gem.id not in seen_by(s, SPECTATOR) and own.id not in seen_by(s, "p3")
    with pytest.raises(ActionError):
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[gem.id])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[gem.id])
    drive(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None)
    assert s.state.cards[gem.id].zone == "p2:exile" and gem.id in seen_by(s, "p3")  # exiled, not put into the hand (and public)
    assert [(p.player, p.spend, p.play, p.cast) for p in s.state.rules.permissions] == [("p1", "color", True, True)]
    assert own.id not in seen_by(s, "p1")  # the search is over: nothing flows to Alice any more
    drive(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1")  # Alice's next turn
    mana(s, "p1", C=1)
    act(s, "p1", type="cast_spell", card_id=gem.id)  # she plays Bob's exiled card (a 400.7 object that stayed there)
    drive(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[gem.id].zone == "p1:battlefield" and s.state.cards[gem.id].controller == "p1"
    assert s.state.rules.permissions == []  # it left exile: the permission is spent
    roundtrip(s)
