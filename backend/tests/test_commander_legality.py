"""Commander legality follows the card data (``legalities.commander``), never Oracle-text guesses;
objects that can't be deck cards are never legal; without stored legalities the printing's other
Scryfall fields decide (digital-only, Alchemy "A-" rebalances, Un-sets without the oval stamp,
acorn stamp, silver/gold borders, the banned list)."""

from __future__ import annotations

import pytest

from app.rules import commander as C
from tests.fixtures.cards import card


def legal(name, **extra):
    return card(name, **extra)


def no_legalities(name, **extra):
    data = card(name, **extra)
    del data["legalities"]
    return data


# --- stored legalities decide -----------------------------------------------------------------

def test_stored_legalities_decide():
    assert C.legality(legal("Sol Ring")) == "legal"
    assert C.legality(legal("Mana Crypt", legalities={"commander": "banned"})) == "banned"
    assert C.legality(legal("Kiora, the Tide's Fury", legalities={"commander": "not_legal"})) == "not_legal"
    assert C.legality(legal("Weird", legalities={"commander": "restricted"})) == "not_legal"  # no such status in Commander
    assert C.legality(legal("Unknown", legalities={"commander": ""})) == "not_legal"
    assert C.legal_in_commander(legal("Sol Ring")) and not C.legal_in_commander(legal("Nope", legalities={"commander": "not_legal"}))


def test_stored_legalities_beat_every_heuristic():
    """Digital default printings (Masters Edition, MTGO Treasure Chest), Unfinity eternal-legal cards
    (stickers, Attractions, d20 rolls, "prepared", teamwork wordings) are legal because Scryfall
    says so; Oracle wording never makes a card illegal."""
    assert C.legal_in_commander(legal("Force of Will", set_code="me2", set_type="masters", digital=True, games=["mtgo"]))
    assert C.legal_in_commander(legal("Vengeant Vampire", set_code="pz2", set_type="treasure_chest", digital=True))
    assert C.legal_in_commander(legal("Sword-Swallowing Seraph", set_code="unf", set_type="funny", security_stamp="oval",
                                      oracle_text="Flying\nWhen this creature enters, put a sticker on it."))
    assert C.legal_in_commander(legal("Complaints Clerk", set_code="unf", set_type="funny", security_stamp="oval",
                                      type_line="Artifact — Attraction", oracle_text="Visit — Create a Treasure token."))
    assert C.legal_in_commander(legal("Earth-Cult Elemental", set_code="afr", oracle_text="Roll a d20."))
    assert C.legal_in_commander(legal("Go Nuts!", set_code="msh", oracle_text="Teamwork — Draw a card."))
    assert C.legal_in_commander(legal("Have a Bite", set_code="sos", oracle_text="Prepare {1}. Prepared creatures get +1/+1."))
    assert C.legal_in_commander(legal("Clever Conjurer", set_code="afr", oracle_text="{T}: Untap another target permanent."))
    assert C.legality(legal("Very Legal Card", legalities={"commander": "legal"}, security_stamp="acorn")) == "legal"


def test_commander_legal_override_still_wins():
    assert C.legality({"name": "X", "commander_legal": "banned", "legalities": {"commander": "legal"}}) == "banned"
    assert C.legality({"name": "X", "commander_legal": None}) == "not_legal"


# --- objects that are never deck cards ---------------------------------------------------------

@pytest.mark.parametrize("type_line", [
    "Stickers",  # Unfinity sticker sheets: the bulk data marks them "legal", but they are not cards (123.1)
    "Emblem — Elspeth", "Token Creature — Goblin", "Dungeon", "Plane — Ravnica", "Phenomenon", "Scheme",
    "Ongoing Scheme", "Vanguard", "Conspiracy", "Hero",
])
def test_non_deck_objects_are_never_legal(type_line):
    assert C.legality(legal("Playable Delusionary Hydra", set_code="sunf", set_type="funny", type_line=type_line)) == "not_legal"


def test_banned_non_deck_objects_stay_banned_as_the_data_says():
    assert C.legality(legal("Backup Plan", type_line="Conspiracy", legalities={"commander": "banned"})) == "banned"


def test_non_deck_type_check_needs_a_whole_supertype():
    assert C.legal_in_commander(legal("Teferi, Hero of Dominaria", type_line="Legendary Planeswalker — Teferi"))
    assert C.legal_in_commander(legal("Hero of Bladehold", type_line="Creature — Human Knight"))
    assert C.legal_in_commander(legal("Tokens Maker", type_line="Enchantment — Aura", oracle_text="Create a token."))
    assert C.legal_in_commander(legal("Urza's Saga", type_line="Legendary Enchantment Land — Urza's Saga"))
    assert C.legal_in_commander(legal("Delver // Aberration", layout="transform", type_line="Creature — Human // Creature — Insect",
                                      card_faces=[{"type_line": "Creature — Human"}, {"type_line": "Creature — Insect"}]))


# --- no stored legalities: the printing's other fields -----------------------------------------

def test_fallback_banned_list():
    assert C.legality(no_legalities("Mana Crypt")) == "banned"
    assert C.legality(no_legalities("Erayo, Soratami Ascendant // Erayo's Essence", layout="flip")) == "banned"
    assert C.legality(no_legalities("Sol Ring")) == "legal"


def test_fallback_digital_only_printings():
    assert C.legality(no_legalities("Kiora, the Tide's Fury", set_type="alchemy", digital=True, games=["arena"])) == "not_legal"
    assert C.legality(no_legalities("Vengeant Vampire", set_type="treasure_chest", digital=True, games=["mtgo"])) == "not_legal"
    assert C.legality(no_legalities("Digital, Games Unknown", digital=True)) == "not_legal"
    # a digital printing of a card that also exists on paper is fine
    assert C.legality(no_legalities("Force of Will", set_type="masters", digital=True, games=["paper", "mtgo"])) == "legal"
    assert C.legality(no_legalities("Paper Card", digital=False, games=["paper", "arena", "mtgo"])) == "legal"


def test_fallback_alchemy_rebalanced_a_cards():
    assert C.legality(no_legalities("A-Omnath, Locus of Creation", set_type="expansion", digital=True, games=["arena"])) == "not_legal"
    assert C.legality(no_legalities("A-Omnath, Locus of Creation", set_type="expansion")) == "not_legal"
    assert C.legality(no_legalities("Omnath, Locus of Creation", set_type="expansion")) == "legal"
    assert C.legality(no_legalities("A-Front // Back", card_faces=[{"name": "A-Front"}, {"name": "Back"}])) == "not_legal"


@pytest.mark.parametrize("set_type", sorted(C.UNSANCTIONED_SET_TYPES))
def test_fallback_unsanctioned_set_types(set_type):
    assert C.legality(no_legalities("Odd Card", set_type=set_type)) == "not_legal"


def test_fallback_unfinity_oval_stamp_is_eternal_legal_but_acorn_is_not():
    assert C.legality(no_legalities("Myra the Magnificent", set_code="unf", set_type="funny", security_stamp="oval")) == "legal"
    assert C.legality(no_legalities("Vorthos, Steward of Myth", set_code="unf", set_type="funny", security_stamp="acorn")) == "not_legal"
    assert C.legality(no_legalities("Old Un-card", set_code="und", set_type="funny")) == "not_legal"  # no stamp: silver-border era
    assert C.legality(no_legalities("Acorn Elsewhere", set_type="expansion", security_stamp="acorn")) == "not_legal"


def test_fallback_borders():
    assert C.legality(no_legalities("Chaos Confetti", border_color="silver")) == "not_legal"
    assert C.legality(no_legalities("Tournament Deck Card", border_color="gold", set_type="memorabilia")) == "not_legal"
    assert C.legality(no_legalities("Regular", border_color="black")) == "legal"
    assert C.legality(no_legalities("Borderless", border_color="borderless")) == "legal"


# --- real Commander-legal cards stay legal ----------------------------------------------------

WELL_KNOWN = [
    # staples and precon-only cards
    dict(name="Sol Ring", set_code="frc", set_type="commander"),
    dict(name="Arcane Signet", set_code="frc", set_type="commander"),
    dict(name="Command Tower", set_code="frc", set_type="commander"),
    dict(name="The Ur-Dragon", set_code="cmm", set_type="masters", type_line="Legendary Creature — Dragon Avatar"),
    dict(name="Atraxa, Praetors' Voice", set_code="2xm", set_type="masters"),
    dict(name="Jodah, the Unifier", set_code="dmu", set_type="expansion"),
    dict(name="Kenrith, the Returned King", set_code="plst", set_type="masters"),
    # Universes Beyond
    dict(name="Abaddon the Despoiler", set_code="40k", set_type="commander", security_stamp="triangle"),
    dict(name="The Tenth Doctor", set_code="who", set_type="commander", security_stamp="triangle"),
    dict(name="Sephiroth, Fabled SOLDIER // Sephiroth, One-Winged Angel", set_code="fin", set_type="expansion", layout="transform"),
    dict(name="Ezio Auditore da Firenze", set_code="acr", set_type="draft_innovation"),
    dict(name="Iron Man, Tony Stark", set_code="msc", set_type="commander"),
    dict(name="Spider-Man, Miles Morales", set_code="spe", set_type="eternal"),
    dict(name="Aang, the Last Airbender", set_code="tla", set_type="expansion"),
    dict(name="Optimus Prime, Hero // Optimus Prime, Autobot Leader", set_code="bot", set_type="eternal"),
    # Unfinity eternal-legal (oval stamp), incl. stickers and Attractions
    dict(name="Myra the Magnificent", set_code="unf", set_type="funny", security_stamp="oval"),
    dict(name="Comet, Stellar Pup", set_code="unf", set_type="funny", security_stamp="oval"),
    dict(name="Complaints Clerk", set_code="unf", set_type="funny", security_stamp="oval", type_line="Artifact — Attraction"),
    # Secret Lair only
    dict(name="The Fourteenth Doctor", set_code="sld", set_type="box"),
    dict(name="Shadow the Hedgehog", set_code="sld", set_type="box"),
    dict(name="Kibo, Uktabi Prince", set_code="sld", set_type="box"),
    # digital default printings of paper cards
    dict(name="Raging Goblin", set_code="oana", set_type="starter", digital=True),
    dict(name="Windseeker Centaur", set_code="prm", set_type="promo", digital=True, promo=True),
]


@pytest.mark.parametrize("spec", WELL_KNOWN, ids=[s["name"] for s in WELL_KNOWN])
def test_well_known_legal_cards_stay_legal(spec):
    spec = dict(spec)
    name = spec.pop("name")
    data = card(name, **spec)  # legalities.commander == "legal", as in the bulk data
    assert C.legality(data) == "legal", name
