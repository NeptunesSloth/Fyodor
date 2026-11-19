"""-- keyword help -- the card-text glossary: reminder text made generic, ability words from their usual opening, engine overrides."""

import json

from app.cards import glossary


def row(kws, text):
    return (json.dumps(kws), text, None)


def test_reminders_ability_words_and_overrides():
    g = glossary.build([
        row(["Kicker"], "Kicker {2}{R} (You may pay an additional {2}{R} as you cast this spell.)"),
        row(["Kicker"], "Kicker {1} (You may pay an additional {1} as you cast this spell.)"),
        row(["Mill"], "Mill three cards. (Put the top three cards of your library into your graveyard.)"),
        row(["Haste"], "Haste (This creature can attack and {T} as soon as it comes under your control.)"),
        row(["Landfall"], "Landfall — Whenever a land you control enters, draw a card."),
        row(["Offspring"], "Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)"),
    ])
    assert g["kicker"] == "You may pay an additional [cost] as you cast this spell."
    assert g["mill"] == "Put the top N cards of your library into your graveyard."
    assert g["haste"] == "This creature can attack and tap as soon as it comes under your control."
    assert "Whenever a land you control enters" in g["landfall"] and g["landfall"].startswith("Ability word")
    assert "1/1 token copy" in g["offspring"]
    assert g["dive"].startswith("It can't be blocked")
