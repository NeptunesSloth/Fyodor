"""Wave 110C: Chaos Mutation. 115.1d / 601.2c: "any number of target creatures controlled by different players" (at most one per controller); each exiled creature's controller
(as it last existed, 608.2h) reveals until a creature card, puts it onto the battlefield and the rest on the bottom in a random order (701.20, 701.24)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.game_helpers import act, deck, enable
from tests.test_rules_designations import put
from tests.test_rules_library_packets101 import advance, cast
from tests.test_rules_library_polymorph102 import top
from tests.test_rules_wave30m_durations import to_phase
from tests.wave9c_kit import check

CHAOS = ("Exile any number of target creatures controlled by different players. For each creature exiled this way, its controller reveals cards from the top of their library until "
         "they reveal a creature card, puts that card onto the battlefield, then puts the rest on the bottom of their library in a random order.")


@pytest.fixture
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import fixture_cards
    from tests.test_rules_library_polymorph102 import DATA, card

    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c["name"]] = card(c["name"], set_code="lpoly102", number=str(i), **{k: v for k, v in c.items() if k not in {"name", "set_code", "number", "id"}})
    base["Chaos Mutation"] = card("Chaos Mutation", set_code="w110c", number="CM1", mana_cost="{3}{R}{R}", cmc=5.0, type_line="Sorcery", oracle_text=CHAOS, colors=["R"], color_identity=["R"])
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Chaos Mutation")).level == "FULL"


def setup(cards):
    decks = [deck(cards, "Krenko, Mob Boss", [(2, n) for n in ("Chaos Mutation", "Walking Corpse", "Hill Giant", "Grizzly Bears", "Lightning Bolt")] + [(40, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [(2, n) for n in ("Hill Giant", "Grizzly Bears", "Champion of the Perished", "Lightning Bolt")] + [(40, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=decks[0]), PlayerSetup("Bob", cards=decks[1])], shuffle=False)), cards=cards)
    to_phase(s, "main1", 1)
    act(s, "p1", type="set_stops", own=["main1", "end"], others=["main1", "end"], smart_pass=False)
    act(s, "p1", type="add_mana", player="p1", mana={c: 50 for c in ["C", "W", "U", "B", "R", "G"]})
    return s


def test_each_exiled_creatures_controller_reveals_to_a_creature_and_the_rest_go_to_the_bottom(cards):
    s = setup(cards)
    a, b = put(s, "Walking Corpse", "battlefield"), put(s, "Grizzly Bears", "battlefield", "p2")
    mine = top(s, ["Forest", "Hill Giant", "Lightning Bolt"])
    theirs = top(s, ["Island", "Champion of the Perished", "Lightning Bolt"], "p2")
    cast(s, "Chaos Mutation", targets=[a.id, b.id], target_counts=[2])
    advance(s)
    assert s.state.cards[a.id].zone == "p1:exile" and s.state.cards[b.id].zone == "p2:exile"
    assert s.state.cards[mine[1]].zone == "p1:battlefield" and s.state.cards[theirs[1]].zone == "p2:battlefield"
    assert mine[0] in s.state.zones["p1:library"][-2:] and theirs[0] in s.state.zones["p2:library"][-2:]  # (the rest of the reveal: on the bottom, 701.24)
    assert s.state.zones["p1:library"][0] == mine[2] and s.state.zones["p2:library"][0] == theirs[2]
    check(s)


def test_zero_targets_is_allowed_and_two_of_one_controller_is_not(cards):
    s = setup(cards)
    a, b = put(s, "Walking Corpse", "battlefield"), put(s, "Grizzly Bears", "battlefield")
    with pytest.raises(ActionError):
        cast(s, "Chaos Mutation", targets=[a.id, b.id], target_counts=[2])
    cast(s, "Chaos Mutation", targets=[], target_counts=[0])
    advance(s)
    assert s.state.cards[a.id].zone == "p1:battlefield"
