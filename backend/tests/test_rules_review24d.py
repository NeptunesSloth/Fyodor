"""Review of wave 24D. Cancelling a cast (601.2 rewind) is the caster's take-back of an announcement; a spell cast for free as an
effect resolves (cascade, suspend, rebound, madness, discover, ripple: 608.2g) can't be cancelled — that resolution is already over,
so a cancel stranded the card in exile with its free-cast grant kept for later (review 29B: unless the cast's end is recorded, which
sends a cancelled card where a card not cast goes). Also: a cancel after a save/load, a flashback cast
from the graveyard and an activated ability with a sacrifice cost (nothing moved, nothing paid); "You may X. Y." (Sephiroth,
Fallen Hero) still does Y when X is declined. Real Oracle text; replay and save/load."""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.game.session import GameSession
from app.game.state import GameState
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch, token
from tests.test_rules_conditionals import attack, build, on_field, pick
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_suspend import PlayerSetup, deck, enable, new_game, until
from tests.test_rules_wave4l_attached import equip, to_attack
from tests.test_rules_wave24d_bugs import EXTRA as W24D

EXTRA = [*W24D,
         card("Sephiroth, Fallen Hero", set_code="tst", number="R24D-1", mana_cost="{3}{R}{W}", cmc=5.0,
              type_line="Legendary Creature — Human Avatar Soldier", power="5", toughness="5",
              oracle_text="Jenova Cells — Whenever Sephiroth attacks, you may put a cell counter on target creature. Until end of turn, each modified creature you control has base power and toughness 7/5. (Equipment, Auras you control, and counters are modifications.)\nThe Reunion — {3}, Sacrifice a modified creature: Return this card from your graveyard to the battlefield tapped.",
              colors=["R", "W"], color_identity=["R", "W"])]

@pytest.fixture()
def card_db(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path

def reloaded(s):
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")
    return loaded

def test_a_free_cast_during_cascade_cancelled_is_a_card_not_cast(cards):
    """-- review (wave 29B) -- the cascade cast's end is recorded now (RulesState.free_cast_then): a cancel no longer strands the card, it
    goes to the bottom of the library as a card not cast (702.85a), with no grant left; so the target choice may be cancelled (the way out of
    a cast whose cost turns out not to be payable)."""
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Bloodbraid Elf"), (1, "Lightning Bolt"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    elf = next(c for c in s.state.cards.values() if c.name == "Bloodbraid Elf")
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[elf.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, R=1, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=elf.id)
    until(s, lambda s: s.state.rules.decision is not None and "Cascade" in s.state.rules.decision.prompt)
    pick(s, "yes")
    assert s.state.rules.decision.resume["step"] == "cast_target"
    assert s.view("p1")["rules"]["decision"]["cancelable"] is True
    cast = reloaded(s)
    pick(cast, "p2")
    until(cast, lambda s: not s.state.zones.get("stack"))
    assert cast.state.cards[bolt.id].zone == "p1:graveyard" and not cast.state.rules.free_casts
    s = reloaded(s)
    pick(s, "cancel")  # (before wave 29B's review: Bolt would have stayed in exile, castable for free whenever)
    assert s.state.cards[bolt.id].zone == "p1:library" and s.state.zones["p1:library"][-1] == bolt.id
    assert not s.state.rules.free_casts and s.state.rules.free_cast_then is None and s.state.rules.decision is None
    replay_matches(s)

def test_cancel_a_flashback_cast_after_a_reload(cards):
    s = build(cards, "Firebolt")
    fb = next(c for c in s.state.cards.values() if c.name == "Firebolt")
    act(s, "p1", type="move", card_ids=[fb.id], to={"zone": "graveyard"})
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=fb.id)
    assert s.view("p1")["rules"]["decision"]["cancelable"] is True
    assert "cancelable" not in s.view("p2")["rules"]["decision"]  # (the others only see that Alice is deciding)
    s = reloaded(s)
    pick(s, "cancel")
    assert s.state.cards[fb.id].zone == "p1:graveyard" and s.state.rules.decision is None and s.state.rules.priority == "p1"
    assert s.state.players["p1"].mana.get("R") == 1 and s.state.players["p1"].mana.get("C") == 4
    replay_matches(s)

def test_cancel_an_activated_ability_with_a_sacrifice_cost(cards):
    s = build(cards, "Insidious Fungus")
    fungus = on_field(s, "Insidious Fungus")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=fungus.id, ability=0)
    assert s.state.rules.decision.resume["step"] == "cast_modes"
    pick(s, "cancel")
    assert s.state.cards[fungus.id].zone == "p1:battlefield" and s.state.players["p1"].mana.get("C") == 2
    assert not s.state.zones.get("stack")
    replay_matches(s)
    reloaded(s)

@pytest.mark.parametrize("answer", ["yes", "no"])
def test_sephiroth_declining_the_counter_keeps_the_base_7_5(cards, answer):
    """Jenova Cells: "you may put a cell counter on target creature" is the only optional part; "Until end of turn, each modified
    creature you control has base power and toughness 7/5" applies either way (608.2c)."""
    s = build(cards, "Sephiroth, Fallen Hero", "Bonesplitter")
    seph = on_field(s, "Sephiroth, Fallen Hero")
    bear = token(s, "p1", "Bear")
    equip(s, "Bonesplitter", bear)  # modified (equipped)
    other = token(s, "p1", "Cub")
    to_attack(s)
    attack(s, (seph, "p2"))
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "confirm":
            pick(s, answer)
            break
        if d is not None:
            pick(s, other.id if any(o.id == other.id for o in d.options) else d.options[0].id)
            continue
        act(s, s.state.rules.priority, type="pass_priority")
    until(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None or
          (s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers"))
    assert ch(s, bear).pt == (9, 5)  # base 7/5, +2/+0 from Bonesplitter
    assert ch(s, other).pt == ((7, 5) if answer == "yes" else (2, 2))  # the cell counter makes it modified
    replay_matches(s)
    reloaded(s)
