"""Review 40: cards waves 46C-49A made FULL that played wrong (CR 2026-09-25), real Oracle text (tests/fixtures/review40_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 111.7, 608.2h: a token an instruction exiled (or destroyed) went there, then ceased to exist; "if a Pirate was exiled this way" and "the number of
  creatures exiled this way" still count it (Siren's Ruse ruling 2017-09-29: "You'll draw a card if the creature was a Pirate as it was exiled, even if
  it doesn't return to the battlefield (most likely because it's a token)"). Siren's Ruse drew nothing for a Pirate token and Overwrite the Multiverse
  left exiled tokens out of X.
* 113.6m: "{U}{B}: Exile five target cards from an opponent's graveyard. Return this card from your graveyard to your hand." (Lochmere Serpent) moves the
  card out of the graveyard, so the ability works only there. It was offered on the battlefield (exiling five cards for nothing) and refused from the
  graveyard: the "return this card from your graveyard" was looked for only at the start of the effect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "review40_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r40", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FOES = ("Opt", "Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Counterspell")


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


# ---- 111.7, 608.2h: a token exiled this way is counted -------------------------------------------------------------------------------------------
def test_sirens_ruse_draws_for_a_pirate_token_it_exiled(cards):
    s = build(cards, ["Siren's Ruse"])
    pirate = token_of(s, "p1", "Pirate", "Token Creature — Human Pirate")
    to_hand(s, "Siren's Ruse")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Siren's Ruse").id, targets=[pirate.id])
    settle(s)
    assert pirate.id not in s.state.cards  # (exiled, then it ceased to exist: it doesn't come back)
    assert hand(s) == 1  # (Siren's Ruse left the hand; the card drawn is in it)
    check(s)


def test_sirens_ruse_draws_nothing_for_a_token_that_is_no_pirate(cards):
    s = build(cards, ["Siren's Ruse"])
    soldier = token_of(s, "p1", "Soldier", "Token Creature — Human Soldier")
    to_hand(s, "Siren's Ruse")
    mana(s, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Siren's Ruse").id, targets=[soldier.id])
    settle(s)
    assert hand(s) == 0
    check(s)


def test_overwrite_the_multiverse_counts_the_tokens_it_exiled(cards):
    s = build(cards, ["Overwrite the Multiverse", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    token_of(s, "p2", "Spirit", "Token Creature — Spirit", "1/1")
    token_of(s, "p1", "Soldier", "Token Creature — Soldier", "1/1")
    to_hand(s, "Overwrite the Multiverse")
    mana(s, B=2, U=2, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Overwrite the Multiverse").id)
    settle(s)
    jace = [c for c in s.state.cards.values() if c.name == "Jace" and c.zone == "p1:battlefield"]
    assert len(jace) == 1 and jace[0].counters.get("loyalty") == 3  # (the Bears and both tokens: empower Jace 3)
    check(s)


# ---- 113.6m: Lochmere Serpent's last ability works only from the graveyard ----------------------------------------------------------------------
def lochmere_table(cards):
    s = build(cards, ["Lochmere Serpent"], FOES)
    gone = []
    for name in FOES:
        c = card_named(s, name, "p2")
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "graveyard"})
        gone.append(c.id)
    return s, gone


def test_lochmere_serpent_exiles_five_cards_from_an_opponents_graveyard_and_returns_from_yours(cards):
    s, gone = lochmere_table(cards)
    serpent = card_named(s, "Lochmere Serpent")
    act(s, "p1", type="move", card_ids=[serpent.id], to={"zone": "graveyard"})
    mana(s, U=1, B=1)
    act(s, "p1", type="activate_ability", card_id=serpent.id, ability=3, targets=gone, target_counts=[5])
    settle(s)
    assert zone_of(s, "Lochmere Serpent") == "p1:hand"
    assert all(s.state.cards[c].zone == "p2:exile" for c in gone)
    check(s)


def test_lochmere_serpent_cannot_use_that_ability_on_the_battlefield(cards):
    s, gone = lochmere_table(cards)
    serpent = put(s, "Lochmere Serpent")
    mana(s, U=1, B=1)
    with pytest.raises(ActionError, match="only be activated from your graveyard"):
        act(s, "p1", type="activate_ability", card_id=serpent.id, ability=3, targets=gone, target_counts=[5])
    assert zone_of(s, "Lochmere Serpent") == "p1:battlefield" and all(s.state.cards[c].zone == "p2:graveyard" for c in gone)
    check(s)
