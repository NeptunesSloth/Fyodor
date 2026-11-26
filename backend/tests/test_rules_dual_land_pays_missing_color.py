"""-- playtest (nov 18) -- a land with a choice of mana ("{T}: Add {R} or {G}.") tapped from the table while paying adds the color the
payment still needs. Mana already tapped for the payment sits in remembered pool units (app/rules/mana_units.py), and the color pick
(casting._best_option_index) looked only at the plain pool: with {R}{R}{R}{R} tapped and {G} left to pay, Rockfall Vale added {R}."""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, mana_pool


@pytest.fixture()
def cards(settings):
    base = {c["name"]: c for c in fixture_cards()}
    base["Rockfall Vale"] = card("Rockfall Vale", set_code="sdc", number="1", type_line="Land", mana_cost="",
                                 oracle_text="Rockfall Vale enters the battlefield tapped unless you control two or more other lands.\n{T}: Add {R} or {G}.")
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_the_vale_adds_the_green_still_owed(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Bloodbraid Elf"), (1, "Rockfall Vale"), (4, "Mountain"), (5, "Island")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    state = enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False))
    for prefs in state.rules.prefs.values():
        prefs.payment = "self"  # (players tap their own mana: the table default)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")
    lands = [c.id for c in s.state.cards.values() if c.owner == "p1" and c.name in ("Rockfall Vale", "Mountain")]
    act(s, "p1", type="move", card_ids=lands, to={"zone": "battlefield"})
    vale = next(c for c in s.state.cards.values() if c.name == "Rockfall Vale")
    vale.tapped = False
    elf = next(c for c in s.state.cards.values() if c.name == "Bloodbraid Elf")
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=elf.id)
    for m in [c for c in s.state.cards.values() if c.name == "Mountain"]:
        act(s, "p1", type="activate_ability", card_id=m.id, ability=0, tap_for_mana=True)
    assert s.state.rules.decision is not None and s.state.rules.decision.display["remaining"] == "{G}"
    act(s, "p1", type="activate_ability", card_id=vale.id, ability=0, tap_for_mana=True)
    assert s.state.rules.decision is None  # paid: the Vale added {G}
    assert elf.zone != "p1:hand"
    assert mana_pool(s, "p1") == {"R": 1}  # (the fourth Mountain's {R} is left over)
