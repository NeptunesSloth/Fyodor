"""Wave 29C: the damage a mana ability deals ("{T}: Add {U} or {R}. This land deals 1 damage to you.") is damage like any other (CR 120, 605.3b:
a mana ability resolves immediately, as it is activated): replacement effects (614: Furnace of Rath's "double that damage") and prevention
effects (615: Urza's Armor, a "next 2 damage" shield) change it, and the life it makes the player lose goes through the life-loss replacements
(120.3a). The live mana-payment continuation saves replacement choices (616.1) without granting priority or replaying the activation.
Immediate prevention riders finish before the pending spell is committed.

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_effects import replay_matches
from tests.test_rules_mana_abilities import named, table
from tests.test_rules_refused_grants import _choose
from tests.test_rules_replacements2 import FURNACE_OF_RATH, URZAS_ARMOR, activate, permanent
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


def _first(s, name):
    d = s.state.rules.decision
    source = next(c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield"))
    prefix = f"s:{source.id}."
    answer = next(k for k, value in d.resume['map'].items() if value.startswith(prefix))
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[answer])


@pytest.mark.parametrize('first,life', [("Urza's Armor", 40), ('Furnace of Rath', 39)])
def test_two_damage_effects_pause_mana_payment_for_native_order(cards, first, life):
    s = table(cards, "Shivan Reef")
    permanent(s, "p1", "Urza's Armor", "Artifact", URZAS_ARMOR)
    permanent(s, "p2", "Furnace of Rath", "Enchantment", FURNACE_OF_RATH)
    bolt_from_the_reef(s)
    assert s.state.rules.decision is not None
    assert s.state.players['p1'].life == 40 and s.state.players['p2'].life == 40
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 0
    s = reloaded(s)
    _first(s, first)
    assert s.state.players['p1'].life == life
    assert s.state.players['p2'].life == 34
    assert s.state.rules.decision is None
    check(s)


def test_a_mana_ability_without_a_damage_effect_in_play_is_unchanged(cards):
    s = table(cards, "Shivan Reef")
    bolt_from_the_reef(s)
    assert s.state.players["p1"].life == 39 and s.state.rules.damaged.get("p1") == s.state.turn.number
    check(s)


# -- review 30 -- 615.5: a prevention effect's additional effect ("You gain life equal to the damage prevented this way.") happens immediately
# after the damage it prevented — inside the mana ability here, which can't pause (605.3a). A rider runs without a continuation
# (source_shields.run_rider): the choke points it reaches can't ask, so when carrying it out needs a choice (two life-gain replacements whose
# order matters, 616.1) the result is applied as it is and the log names the effects the players must apply by hand — never a decision opened
# mid-payment, never skipped silently.
PURITY = ("If noncombat damage would be dealt to you, prevent that damage. You gain life equal to the damage prevented this way.")  # Purity
BOON_REFLECTION = "If you would gain life, you gain twice that much life instead."  # Boon Reflection
ANGEL_OF_VITALITY = "If you would gain life, you gain that much life plus 1 instead."  # Angel of Vitality (its first replacement line)
PALM = ("{1}: The next time a source of your choice would deal damage to you this turn, prevent that damage. If damage is "
        "prevented this way, Palm deals that much damage to that source's controller.")  # Deflecting Palm (as an activated ability)


def test_a_prevention_rider_runs_right_after_the_damage_of_a_mana_ability(cards):
    s = table(cards, "Shivan Reef")
    permanent(s, "p1", "Purity", "Enchantment", PURITY)
    bolt_from_the_reef(s)
    assert s.state.rules.decision is None
    assert s.state.players["p1"].life == 41  # 615.5: the 1 damage prevented, then 1 life gained
    check(s)


def test_deflecting_palm_against_a_pain_land(cards):
    """The source chosen is the land: its 1 damage is prevented and Palm deals 1 damage to the land's controller (the caster, 615.5);
    nothing pauses the payment."""
    s = table(cards, "Shivan Reef")
    palm = permanent(s, "p1", "Palm", "Enchantment", PALM)
    activate(s, palm)
    _choose(s, "Shivan Reef")
    bolt_from_the_reef(s)
    assert s.state.rules.decision is None
    assert s.state.players["p1"].life == 39 and s.state.players["p2"].life == 37
    assert "prevented" in log_text(s)
    check(s)


@pytest.mark.parametrize('first,life', [('Boon Reflection', 43), ('Angel of Vitality', 44)])
def test_prevention_rider_choice_resumes_real_mana_payment(cards, first, life):
    s = table(cards, "Shivan Reef")
    permanent(s, "p1", "Purity", "Enchantment", PURITY)
    permanent(s, "p1", "Boon Reflection", "Enchantment", BOON_REFLECTION)
    permanent(s, "p1", "Angel of Vitality", "Enchantment", ANGEL_OF_VITALITY)
    bolt_from_the_reef(s)
    assert s.state.rules.decision is not None
    assert s.state.players['p1'].life == 40 and s.state.players['p2'].life == 40
    assert s.state.rules.spells_this_turn('p1', s.state.turn.number) == 0
    s = reloaded(s)
    _first(s, first)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == life
    assert s.state.players['p2'].life == 37
    check(s)
