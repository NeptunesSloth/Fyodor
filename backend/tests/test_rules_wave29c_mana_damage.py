"""Wave 29C: the damage a mana ability deals ("{T}: Add {U} or {R}. This land deals 1 damage to you.") is damage like any other (CR 120, 605.3b:
a mana ability resolves immediately, as it is activated): replacement effects (614: Furnace of Rath's "double that damage") and prevention
effects (615: Urza's Armor, a "next 2 damage" shield) change it, and the life it makes the player lose goes through the life-loss replacements
(120.3a). A mana ability can't pause for a choice (605.3a), so when two effects both apply and their order matters (616.1), the engine applies
neither's guess and says in the log that the players must apply them by hand — it never skips an effect without saying.

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_mana_abilities import named, table
from tests.test_rules_replacements2 import FURNACE_OF_RATH, URZAS_ARMOR, permanent
from tests.wave9c_kit import reloaded

SHIELD = "{1}: Prevent the next 2 damage that would be dealt to you this turn."  # (Esper Battlemage, its cost as {1} here)


def log_text(s):
    return " | ".join("".join(p.t or "" for p in e.parts) for e in s.state.log)


def bolt_from_the_reef(s):
    """Lightning Bolt at Bob, paid with {R} from Shivan Reef: "Shivan Reef deals 1 damage to you." (the only source of red mana)."""
    act(s, "p1", type="cast_spell", card_id=named(s, "Lightning Bolt").id, targets=["p2"])


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def test_furnace_of_rath_doubles_the_damage_of_a_mana_ability(cards):
    s = table(cards, "Shivan Reef")
    permanent(s, "p2", "Furnace of Rath", "Enchantment", FURNACE_OF_RATH)
    bolt_from_the_reef(s)
    assert s.state.players["p1"].life == 40 - 2  # 614.1a: 1 damage doubled, 120.3a: 2 life lost
    assert s.state.players["p2"].life == 40 - 3 * 2  # (the Bolt's 3 doubled too)
    assert s.state.rules.damaged.get("p1") == s.state.turn.number  # (it was dealt damage this turn: "if you were dealt damage")
    check(s)


def test_a_prevention_effect_prevents_the_damage_of_a_mana_ability(cards):
    s = table(cards, "Shivan Reef")
    permanent(s, "p1", "Urza's Armor", "Artifact", URZAS_ARMOR)
    bolt_from_the_reef(s)
    assert s.state.players["p1"].life == 40  # 615.10: "prevent 1 of that damage": the land's 1 damage is none
    assert "prevented" in log_text(s)
    assert s.state.rules.damaged.get("p1") != s.state.turn.number  # (no damage was dealt)
    check(s)


def test_a_shield_is_used_up_by_the_damage_of_a_mana_ability(cards):
    s = table(cards, "Shivan Reef")
    battlemage = permanent(s, "p1", "Esper Battlemage", "Creature", SHIELD)
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1})
    act(s, "p1", type="activate_ability", card_id=battlemage.id, ability=0)
    assert s.state.rules.prevention.get("p1") == 2
    bolt_from_the_reef(s)
    assert s.state.players["p1"].life == 40 and s.state.rules.prevention.get("p1") == 1  # 615.7: each 1 damage prevented reduces the shield by 1
    check(s)


def test_two_effects_whose_order_matters_are_left_to_the_players_not_skipped(cards):
    s = table(cards, "Shivan Reef")
    permanent(s, "p1", "Urza's Armor", "Artifact", URZAS_ARMOR)
    permanent(s, "p2", "Furnace of Rath", "Enchantment", FURNACE_OF_RATH)
    bolt_from_the_reef(s)
    assert s.state.rules.decision is None  # (605.3a: nothing could be asked)
    text = log_text(s)
    assert "Urza's Armor" in text and "Furnace of Rath" in text and "apply them by hand" in text  # said, with both names (616.1)
    check(s)


def test_a_mana_ability_without_a_damage_effect_in_play_is_unchanged(cards):
    s = table(cards, "Shivan Reef")
    bolt_from_the_reef(s)
    assert s.state.players["p1"].life == 39 and s.state.rules.damaged.get("p1") == s.state.turn.number
    check(s)
