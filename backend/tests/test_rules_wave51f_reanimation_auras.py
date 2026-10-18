"""Wave 51F: the reanimation Auras (CR 2026-09-25), real Oracle text (tests/fixtures/wave51f_reanimation_auras_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* Animate Dead, Dance of the Dead: "Enchant creature card in a graveyard" - the Aura spell targets a creature card in any graveyard (303.4a, 115.1b) and enters enchanting it
  (608.3c). Its enters trigger ("if it's on the battlefield", 603.4) swaps the enchant ability, puts the card onto the battlefield under the Aura controller's control and attaches
  the Aura to it; it creates a delayed trigger: when the Aura leaves the battlefield that creature's controller sacrifices it (603.7).
* Necromancy: an enchantment (flash if the controller wishes: sacrificed at cleanup when cast at instant speed) whose enters trigger targets a creature card in a graveyard and
  makes it an Aura with the same restricted enchant ability.
* An Aura attached to an illegal object goes to the graveyard (704.5m, 303.4c): protection from black on the returned creature, or the creature card gone from the graveyard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51f_reanimation_auras_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51f", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def bury(s, name, pid):
    """The card (in the player's deck) goes to that player's graveyard."""
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def game(cards, aura, mine=(), theirs=()):
    """Alice has the Aura in hand and plenty of Forests; every named card is a deck card of Alice / Bob. Alice has priority in her main phase."""
    s = build(cards, [aura, *mine], theirs)
    mana(s, B=4, G=4, U=4)
    return s, to_hand(s, aura)


def cast_on(s, aura, target):
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[target.id])


def resolve_spell(s):
    """Both pass: the Aura spell resolves (its enters trigger goes on the stack and is not yet resolved)."""
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="pass_priority")


def test_the_three_are_full(cards):
    for name in ("Animate Dead", "Dance of the Dead", "Necromancy"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_animate_dead_returns_an_opponents_creature_under_your_control(cards):
    s, ad = game(cards, "Animate Dead", theirs=["Grizzly Bears"])
    bears = bury(s, "Grizzly Bears", "p2")
    cast_on(s, ad, bears)
    settle(s)
    now = s.state.cards[bears.id]
    assert (now.zone, now.controller, now.owner) == ("p1:battlefield", "p1", "p2")  # returned under Alice's control
    assert s.state.cards[ad.id].attached_to == bears.id and zone_of(s, "Animate Dead") == "p1:battlefield"
    assert pt(s, "Grizzly Bears", "p2") == (1, 2)  # Enchanted creature gets -1/-0
    texts = {a.text.lower().rstrip(".") for a in ch(s, ad).abilities}
    assert "enchant creature put onto the battlefield with animate dead" in texts and "enchant creature card in a graveyard" not in texts
    check(s)
