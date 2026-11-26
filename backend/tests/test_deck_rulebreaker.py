"""-- rulebreaker -- Mystery Booster 2 commanders' "Rulebreaker —" deck-construction exceptions (app/decks/rulebreaker.py)."""

from __future__ import annotations

from app.decks import rulebreaker


def card(name, type_line, identity=(), oracle="", power=None, cmc=0):
    return {"name": name, "type_line": type_line, "color_identity": list(identity), "oracle_text": oracle, "power": power, "cmc": cmc}


EVERFORGER = card("The Everforger", "Legendary Artifact Creature — Construct", oracle="Rulebreaker — A deck with this commander can have "
                  "artifact creature and Equipment cards of any color identity and any basic land cards.")
ARVAD = card("Arvad of the Weatherlight", "Legendary Creature — Human Knight", "WU", "Rulebreaker — If Arvad of the Weatherlight is your "
             "Commander, you may include legendary permanents of any color in your deck regardless of color identity.")
HADRAN = card("Hadran, Naya Sunseeder", "Legendary Creature — Cat Warrior", "G", "Rulebreaker — If Hadran, Naya Sunseeder is your Commander, "
              "you may include creature cards of power 4 or greater of any color in your deck regardless of color identity.")
MAULAR = card("Maular, the Next Evolution", "Legendary Creature — Lizard", "G", "Rulebreaker — A deck with this commander can have creature "
              "cards with mana value 7 or greater of any color identity and any basic land cards.")
WHTZ = card("Whtz, the Bibliophile", "Legendary Creature — Homunculus", "U", "Rulebreaker — A deck with this commander has no maximum deck size.")
GRIZZ = card("Grizzlegom, Hurloon Hero", "Legendary Creature — Minotaur Warrior", "R", "Rulebreaker — A deck with this commander can have any land cards.")
VALKO = card("Valko Indorian, Researcher", "Legendary Creature — Human Wizard", "U", "Rulebreaker — If Valko Indorian, Researcher is your "
             "Commander, you may include all artifacts and enchantments in your deck regardless of color identity.")
TOLABOW = card("Tolabow, Loch Rascal", "Legendary Creature — Otter", "U", "Rulebreaker — If Tolabow, Loch Rascal is your commander, the color "
               "identity of instant and sorcery cards in your deck can include one color of your choice not in your commander's color "
               "identity, and your deck can have any basic land cards.")

SWORD = card("Sword of Fire and Ice", "Artifact — Equipment", "RU")
BOLT = card("Lightning Bolt", "Instant", "R")
SWAMP = card("Swamp", "Basic Land — Swamp", "B")
TEMPLE = card("Temple of Malice", "Land", "BR")
SOL_RING = card("Sol Ring", "Artifact")
ANGEL = card("Baneslayer Angel", "Creature — Angel", "W", power="5", cmc=5)
ULAMOG = card("Ulamog, the Ceaseless Hunger", "Legendary Creature — Eldrazi", power="10", cmc=10)
OMNATH = card("Omnath, Locus of Creation", "Legendary Creature — Elemental", "WURG", power="4", cmc=4)
LEGENDARY_ARTIFACT = card("Mox Amber", "Legendary Artifact")
RHYSTIC = card("Rhystic Study", "Enchantment", "U")


def test_everforger_any_artifact_creature_equipment_and_basics():
    allow = rulebreaker.allowance([EVERFORGER])
    assert allow.free(SWORD) and allow.free(SWAMP) and allow.free(card("Myr", "Artifact Creature — Myr", "B"))
    assert not allow.free(BOLT) and not allow.free(TEMPLE) and not allow.free(SOL_RING)


def test_arvad_legendary_permanents_only():
    allow = rulebreaker.allowance([ARVAD])
    assert allow.free(OMNATH) and allow.free(LEGENDARY_ARTIFACT)
    assert not allow.free(ANGEL) and not allow.free(card("Legendary sorcery", "Legendary Sorcery", "R"))


def test_power_and_mana_value_limits():
    hadran, maular = rulebreaker.allowance([HADRAN]), rulebreaker.allowance([MAULAR])
    assert hadran.free(ANGEL) and hadran.free(OMNATH) and not hadran.free(card("Bears", "Creature — Bear", "R", power="2"))
    assert maular.free(ULAMOG) and not maular.free(ANGEL) and maular.free(SWAMP)


def test_valko_artifacts_and_enchantments_whtz_size_grizzlegom_lands():
    assert rulebreaker.allowance([VALKO]).free(RHYSTIC) and rulebreaker.allowance([VALKO]).free(SWORD)
    assert rulebreaker.allowance([WHTZ]).no_max_size and not rulebreaker.allowance([WHTZ]).free(BOLT)
    assert rulebreaker.allowance([GRIZZ]).free(TEMPLE) and not rulebreaker.allowance([GRIZZ]).free(BOLT)


def test_tolabow_one_extra_color_for_instants_and_sorceries():
    allow = rulebreaker.allowance([TOLABOW])
    assert allow.extra(BOLT) and not allow.free(BOLT) and not allow.extra(ANGEL) and allow.free(SWAMP)


def test_no_rulebreaker_no_allowance():
    allow = rulebreaker.allowance([card("Krenko, Mob Boss", "Legendary Creature — Goblin Warrior", "R", "{T}: Create goblins.")])
    assert not allow.free(SWORD) and not allow.no_max_size and not allow.free(SWAMP)
