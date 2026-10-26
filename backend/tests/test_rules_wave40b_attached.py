"""Wave 40B: attached events (Auras, Equipment), real Oracle text (tests/fixtures/wave40b_cards.json, from data/cards.sqlite). Every scenario checks
the replay and a save and a load (tests/wave9c_kit.check).

* 603.10a, 603.6c, 400.7: "Whenever equipped creature dies" / "When enchanted creature dies" look back at what the Equipment / Aura was attached to as the creature
  left the battlefield; an Equipment moved to another creature follows the new creature, an unattached one triggers nothing (301.5, 303.4b).
* 303.4f, 303.4g, 603.7: an Aura that returns by "When enchanted creature dies, return this card to the battlefield [transformed] [at the beginning of the next end
  step]" chooses what it enchants as it enters (Ghoulish Impetus, Skin Invasion, Journey to Eternity).
* 603.4: an intervening "if" about what the Aura is attached to ("if enchanted creature is a Wolf", "if enchanted permanent is tapped") is checked as it triggers and
  as it resolves; "it" / "that creature" after it are the enchanted object, not the Aura.
* 602.2, 118.3: "Tap enchanted land: …" (Earthlore, Krovikan Plague, Tourach's Gate, Nature's Chosen) taps the permanent the Aura is attached to as the cost (these
  all enchant something you control) and "Activate only if enchanted land is untapped".
* 701.21a: "Sacrifice enchanted creature: …" (Betrothed of Fire) — only a creature you control.
* 111.4, 702.6, 205.3g: Equipment tokens made with quoted abilities and equip (Moira Brown's Book Equipment, Nahiri's Stoneforged Blade, Icingdeath).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch, token
from tests.test_rules_copy import choose, decision, pay
from tests.test_rules_effects import pass_until_stack_empty
from tests.wave9c_kit import build, card_named, check, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave40b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t40b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
EXTRA.append(card("Probe Chill", set_code="t40b", number="B90", mana_cost="{U}", cmc=1.0, type_line="Instant", oracle_text="Tap target creature.",
                  colors=["U"], color_identity=["U"]))


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, limit=40):
    """Resolve everything on the stack, taking the first option of every decision."""
    for _ in range(limit):
        d = decision(s)
        if d is not None:
            choose(s, d.options[0].id)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_phase(s, phase, turn=None, limit=300):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} (at {s.state.turn.phase})")


def equip(s, equipment, creature, ability, **mana):
    """Activate the Equipment's equip ability (702.6a; its Oracle line ``ability``) on ``creature`` and let it resolve."""
    pay(s, **mana)
    act(s, "p1", type="activate_ability", card_id=equipment.id, ability=ability, targets=[creature.id])
    pass_until_stack_empty(s)


def cast_on(s, name, target, **mana):
    c = to_hand(s, name)
    pay(s, **mana)
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target.id])
    settle(s)
    return c


def kill(s, creature):
    """The creature dies (704.5g): lethal damage marked on it, state-based actions checked as priority passes."""
    act(s, "p1", type="set_damage", card_ids=[creature.id], value=99)
    act(s, "p1", type="pass_priority")
    settle(s)


def hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def on_table(s, name, pid=None):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield") and (pid is None or c.controller == pid)]


def zone_names(s, zone, pid="p1"):
    return sorted(s.state.cards[c].name for c in s.state.zones.get(f"{pid}:{zone}", []))


@pytest.mark.parametrize("name", [c["name"] for c in DATA if c["name"] not in ("Angelic Destiny", "Skullclamp")])
def test_the_cards_are_full(name):
    data = next(c for c in EXTRA if c["name"] == name)  # (with an id of its own: the printed characteristics are cached by it)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


MANUAL = [card(c["name"], set_code="t40m", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
          for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / "wave40b_manual.json").read_text("utf-8")))]


# -- block events (wave 53C) -- Radiant Grace (the Aura returns attached to a target opponent, 303.4f, 712.14a) and Hedron Blade ("becomes blocked by one or more colorless creatures"
# for equipped creature, 509.3c) are read now, and so is Scriv (the Aura token "Contract" made attached to a target, with its own enchant ability: roles.NAMED) (tests/test_rules_wave53c_block_events.py)
LIFTED_53C = ("Gift of Immortality", "Radiant Grace // Radiant Restraints", "Hedron Blade", "Scriv, the Obligator")
LIFTED_100F = ("Glimmer Lens", "Observed Stasis")  # -- attached (wave 100F) -- read now (tests/test_rules_wave100f_control.py)
# -- wave 110 -- read now: Rhuk (the Equipment attached as the creature died, 603.10a: tests/test_rules_wave110i_more.py) and Preston Garvey (the Settlement
# Aura token with its own enchant ability: tests/test_rules_wave110d_auras.py)
LIFTED_110 = ("Rhuk, Hexgold Nabber", "Preston Garvey, Minuteman")


@pytest.mark.parametrize("name", [c["name"] for c in json.loads((Path(__file__).parent / "fixtures" / "wave40b_manual.json").read_text("utf-8"))])
def test_the_once_manual_cards_are_read_now(name):
    """This wave left them manual (their attached-object wording needed more than it read); later waves read each one (LIFTED_*)."""
    assert name in (*LIFTED_53C, *LIFTED_100F, *LIFTED_110)
    if name in LIFTED_110:
        data = next(c for c in MANUAL if c["name"] == name)
        assert coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def level_of(oracle: str, type_line: str = "Enchantment — Aura") -> str:
    name = f"Probe Aura {abs(hash(oracle))}"  # (coverage is kept per oracle id, which is the name's)
    data = card(name, set_code="t40b", number="B91", type_line=type_line, oracle_text=oracle, mana_cost="{1}", cmc=1.0)
    return coverage.of_card_data({**data, "faces": [], "legalities": {"commander": "legal"}}).level


@pytest.mark.parametrize(("text", "full"), [
    ("When this Aura enters, if enchanted creature is tapped, untap it.", True),
    ("When this Aura enters, if enchanted creature is tapped, its controller loses 2 life.", False),  # whose "its" is not guessed
    ("When this Aura enters, if enchanted creature was tapped, untap it.", False),  # (the past tense is about what it was)
    ("When this Aura enters, untap it if enchanted creature is tapped.", True),
    ("{1}: Draw a card. Activate only if enchanted creature's power is 4 or greater.", True),
    ("{1}: Draw a card. Activate only if enchanted creature is a creature with the greatest power among creatures on the battlefield.", True),  # (wave 49C: ties count, 115.1)
    ("Tap enchanted creature: Draw a card. Activate only if enchanted creature is untapped.", True),
    ("Enchanted creature gets +X/+1, where X is the number of artifacts you control.", True),
    ("Enchanted creature gets +X/+Y, where X is the number of artifacts you control.", False),
])
def test_the_new_wordings_read_exactly_what_they_say(text, full):
    assert (level_of("Enchant creature\n" + text) == "FULL") is full


# -- the look-back and the follow-the-Equipment tests (existing machinery, pinned) -------------------------------------------------


def test_skullclamp_draws_when_the_equipped_creature_dies_to_its_own_toughness(cards):
    """603.10a: Skullclamp's -1 toughness kills the 2/1 as it is equipped (704.5f); the Equipment was attached as it died, so it triggers."""
    s = build(cards, ["Skullclamp"])
    clamp, bear = put(s, "Skullclamp"), token(s, "p1", "Bear", "2/1")
    before = hand_size(s)
    equip(s, clamp, bear, 2, C=1)
    settle(s)
    assert hand_size(s) == before + 2
    assert s.state.cards[clamp.id].attached_to is None  # 704.5n: it stays, equipping nothing
    check(s)


def test_an_equipment_moved_to_another_creature_triggers_for_the_new_one_only(cards):
    s = build(cards, ["Skullclamp"])
    clamp, a, b = put(s, "Skullclamp"), token(s, "p1", "Ape", "3/3"), token(s, "p1", "Boar", "3/3")
    equip(s, clamp, a, 2, C=1)
    equip(s, clamp, b, 2, C=1)  # 301.5: it now equips the Boar
    assert s.state.cards[clamp.id].attached_to == b.id
    before = hand_size(s)
    kill(s, a)
    settle(s)
    assert hand_size(s) == before  # the Ape no longer carries it
    kill(s, b)
    settle(s)
    assert hand_size(s) == before + 2
    check(s)


def test_an_unattached_equipment_triggers_nothing(cards):
    s = build(cards, ["Skullclamp"])
    put(s, "Skullclamp")
    bear = token(s, "p1", "Bear", "2/2")
    before = hand_size(s)
    kill(s, bear)
    settle(s)
    assert hand_size(s) == before
    check(s)


def test_an_aura_and_its_creature_leave_together_and_the_trigger_looks_back(cards):
    """603.10a: Angelic Destiny goes to the graveyard with the Angel it enchants (704.5m, at the same time) and still triggers; "this card" is the new object in the
    graveyard (400.7f): it returns to its owner's hand."""
    s = build(cards, ["Angelic Destiny"])
    bear = token(s, "p1", "Bear", "2/2")
    aura = cast_on(s, "Angelic Destiny", bear, W=2, C=2)
    assert s.state.cards[aura.id].attached_to == bear.id
    kill(s, bear)
    settle(s)
    assert s.state.cards[aura.id].zone == "p1:hand"
    check(s)


# -- an Aura that returns itself when its creature dies (it left with the creature; 603.10a, 303.4f) -----------------------------------


def test_ghoulish_impetus_returns_at_the_next_end_step_and_chooses_a_new_creature(cards):
    """"When enchanted creature dies, return this card to the battlefield at the beginning of the next end step." The Aura went to the graveyard with its
    creature (704.5m) and the trigger still happened (603.10a); at the end step the card in the graveyard (the same object, 400.7f) returns and its
    controller chooses what it enchants (303.4f)."""
    s = build(cards, ["Ghoulish Impetus"])
    bear, goat = token(s, "p1", "Bear", "2/2"), token(s, "p2", "Goat", "2/2")
    aura = cast_on(s, "Ghoulish Impetus", bear, B=1, C=2)
    assert s.state.cards[aura.id].attached_to == bear.id
    kill(s, bear)
    assert s.state.cards[aura.id].zone == "p1:graveyard"  # it left with the Bear
    to_phase(s, "end")
    settle(s)
    back = s.state.cards[aura.id]
    assert back.zone == "p1:battlefield" and back.attached_to == goat.id  # the only creature left to enchant
    assert ch(s, goat).pt == (3, 3) and "deathtouch" in ch(s, goat).keywords
    check(s)


def test_ghoulish_impetus_stays_in_the_graveyard_with_nothing_to_enchant(cards):
    """303.4g: no legal object to enchant at the end step: the Aura remains in the graveyard."""
    s = build(cards, ["Ghoulish Impetus"])
    bear = token(s, "p1", "Bear", "2/2")
    aura = cast_on(s, "Ghoulish Impetus", bear, B=1, C=2)
    kill(s, bear)
    to_phase(s, "end")
    settle(s)
    assert s.state.cards[aura.id].zone == "p1:graveyard"
    check(s)


def test_skin_invasion_returns_transformed_at_once(cards):
    """"When enchanted creature dies, return this card to the battlefield transformed under your control." (712.14a): the back face is a creature."""
    s = build(cards, ["Skin Invasion // Skin Shedder"])
    bear = token(s, "p1", "Bear", "2/2")
    aura = cast_on(s, "Skin Invasion // Skin Shedder", bear, R=1)
    assert s.state.cards[aura.id].attached_to == bear.id
    kill(s, bear)
    back = s.state.cards[aura.id]
    assert back.zone == "p1:battlefield" and back.attached_to is None
    assert ch(s, back).is_creature and ch(s, back).name == "Skin Shedder"
    check(s)


def test_journey_to_eternity_brings_the_creature_back_and_turns_into_a_land(cards):
    """"return it to the battlefield under your control, then return this card to the battlefield transformed under your control": Atzal, a land."""
    s = build(cards, ["Journey to Eternity // Atzal, Cave of Eternity", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    aura = cast_on(s, "Journey to Eternity // Atzal, Cave of Eternity", bears, B=1, G=1, C=1)
    assert s.state.cards[aura.id].attached_to == bears.id
    kill(s, bears)
    assert s.state.cards[bears.id].zone == "p1:battlefield"  # (a new object: it died and came back)
    land = s.state.cards[aura.id]
    assert land.zone == "p1:battlefield" and land.attached_to is None
    assert ch(s, land).name == "Atzal, Cave of Eternity" and "Land" in ch(s, land).types
    check(s)


# -- the attached object in an intervening "if" (603.4) ----------------------------------------------------------------------------------


def make(s, pid, name, kind, pt="2/2", text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token Creature — {kind}", "power": p, "toughness": t, "text": text})
    return next(c for c in s.state.cards.values() if c.name == name)


def colored(s, name, color):
    act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": f"Token Creature — {name}", "power": "2", "toughness": "2",
                                                         "colors": [color], "text": ""})
    return next(c for c in s.state.cards.values() if c.name == name)


def tap(s, c, tapped=True):
    act(s, "p1", type="tap", card_ids=[c.id], tapped=tapped)


def test_howl_of_the_hunt_untaps_the_enchanted_wolf_not_the_aura(cards):
    """"When this Aura enters, if enchanted creature is a Wolf or Werewolf, untap that creature." — "that creature" is the Wolf (303.4b)."""
    s = build(cards, ["Howl of the Hunt"])
    wolf = make(s, "p1", "Grey Wolf", "Wolf")
    tap(s, wolf)
    cast_on(s, "Howl of the Hunt", wolf, G=1, C=2)
    assert not s.state.cards[wolf.id].tapped
    assert ch(s, wolf).pt == (4, 4)
    check(s)


def test_howl_of_the_hunt_does_nothing_for_another_creature_type(cards):
    """603.4: not a Wolf as it would trigger: the ability doesn't trigger at all."""
    s = build(cards, ["Howl of the Hunt"])
    bear = make(s, "p1", "Brown Bear", "Bear")
    tap(s, bear)
    cast_on(s, "Howl of the Hunt", bear, G=1, C=2)
    assert s.state.cards[bear.id].tapped
    check(s)


def test_volition_reins_untaps_a_tapped_permanent_and_takes_it(cards):
    s = build(cards, ["Volition Reins"])
    ox = make(s, "p2", "Ox", "Ox")
    tap(s, ox)
    cast_on(s, "Volition Reins", ox, U=3, C=3)
    assert not s.state.cards[ox.id].tapped and s.state.cards[ox.id].controller == "p1"
    check(s)


def test_volition_reins_leaves_an_untapped_permanent_alone(cards):
    """The "if" is false: nothing happens to the Ox, and (the bug this guards against) nothing happens to the Aura either."""
    s = build(cards, ["Volition Reins"])
    ox = make(s, "p2", "Ox", "Ox")
    aura = cast_on(s, "Volition Reins", ox, U=3, C=3)
    assert not s.state.cards[ox.id].tapped and s.state.cards[ox.id].controller == "p1" and s.state.cards[aura.id].zone == "p1:battlefield"
    check(s)


def test_maze_mantle_gives_hexproof_to_the_enchanted_creature_with_toxic(cards):
    s = build(cards, ["Maze's Mantle"])
    viper = make(s, "p1", "Viper", "Snake", text="Toxic 1")
    cast_on(s, "Maze's Mantle", viper, G=1, C=2)
    assert "hexproof" in ch(s, viper).keywords
    plain = make(s, "p1", "Plain", "Snake")
    cast_on(s, "Maze's Mantle", plain, G=1, C=2)
    assert "hexproof" not in ch(s, plain).keywords
    check(s)


def test_domestication_is_sacrificed_when_the_creature_gets_big(cards):
    """"At the beginning of your end step, if enchanted creature's power is 4 or greater, sacrifice this Aura." — checked as the step begins and again as it resolves."""
    s = build(cards, ["Domestication"])
    ox = make(s, "p2", "Ox", "Ox", "3/3")
    aura = cast_on(s, "Domestication", ox, U=2, C=2)
    assert s.state.cards[ox.id].controller == "p1"
    to_phase(s, "end")
    settle(s)
    assert s.state.cards[aura.id].zone == "p1:battlefield"  # 3 power: it stays
    act(s, "p1", type="counter", card_ids=[ox.id], kind="+1/+1", delta=1)
    to_phase(s, "end", turn=s.state.turn.number + 2)  # (Alice's next end step)
    settle(s)
    assert s.state.cards[aura.id].zone == "p1:graveyard" and s.state.cards[ox.id].controller == "p2"
    check(s)


def test_blade_of_the_bloodchief_puts_two_counters_on_an_equipped_vampire(cards):
    """"If equipped creature is a Vampire, put two +1/+1 counters on it instead." — the condition and "it" are the equipped creature, not the Equipment."""
    s = build(cards, ["Blade of the Bloodchief"])
    blade = put(s, "Blade of the Bloodchief")
    ape, bat, goat = make(s, "p1", "Ape", "Ape"), make(s, "p1", "Bat", "Vampire"), make(s, "p1", "Goat", "Goat")
    equip(s, blade, ape, 1, C=1)
    kill(s, goat)
    assert s.state.cards[ape.id].counters.get("+1/+1") == 1 and not s.state.cards[blade.id].counters
    equip(s, blade, bat, 1, C=1)
    other = make(s, "p1", "Boar", "Boar")
    kill(s, other)
    assert s.state.cards[bat.id].counters.get("+1/+1") == 2 and s.state.cards[ape.id].counters.get("+1/+1") == 1
    check(s)


def test_narcolepsy_taps_the_enchanted_creature_every_upkeep(cards):
    s = build(cards, ["Narcolepsy"])
    ox = make(s, "p2", "Ox", "Ox")
    cast_on(s, "Narcolepsy", ox, U=1, C=1)
    assert not s.state.cards[ox.id].tapped
    to_phase(s, "upkeep", turn=s.state.turn.number + 1)
    settle(s)
    assert s.state.cards[ox.id].tapped
    check(s)


def test_the_intervening_if_grammar_reads_the_enchanted_object():
    """The condition vocabulary behind those cards: the object an Aura / Equipment is attached to (301.5, 303.4b)."""
    from app.rules import conditions

    assert conditions.parse("enchanted creature is tapped", objects=True) == {"object": "host", "test": "tapped"}
    assert conditions.parse("enchanted creature's power is 4 or greater", objects=True) == {"object": "host", "stat": "power", "op": ">=", "n": 4}
    assert conditions.parse("enchanted creature has toxic", objects=True) == {"object": "host", "has": "toxic"}
    both = conditions.parse("equipped creature is white and untapped", objects=True)  # (Nature's Chosen: one subject, two adjectives)
    assert both is not None and [c["object"] for c in both["all"]] == ["host", "host"]
    # not outside an ability that has such an object, and not in the past tense ("it was attacking" is about what it was)
    assert conditions.parse("enchanted creature is tapped") is None
    assert conditions.parse("enchanted creature was tapped", objects=True) is None


# -- "Tap / Sacrifice enchanted creature" as a cost (602.2, 118.3, 701.21a) --------------------------------------------------------------


def ability_index(s, c, contains):
    return next(a.index for a in ch(s, c).abilities if a.kind in ("activated", "loyalty") and contains in a.text)


def activate(s, c, contains, pay_mana=None, **kw):
    if pay_mana:
        pay(s, **pay_mana)
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability_index(s, c, contains), **kw)
    settle(s)


def life(s, pid):
    return s.state.players[pid].life


def test_krovikan_plague_taps_the_enchanted_creature_to_pay_and_needs_it_untapped(cards):
    s = build(cards, ["Krovikan Plague"])
    rat = make(s, "p1", "Rat", "Rat", "2/2")
    plague = cast_on(s, "Krovikan Plague", rat, B=1, C=2)
    assert ability_index(s, plague, "Tap enchanted creature")
    activate(s, plague, "Tap enchanted creature", targets=["p2"])
    assert s.state.cards[rat.id].tapped and life(s, "p2") == 39  # the Aura dealt 1 damage
    assert s.state.cards[rat.id].counters.get("-0/-1") == 1 and ch(s, rat).pt == (2, 1)
    with pytest.raises(ActionError):  # the cost can't be paid again: 118.3, and "Activate only if enchanted creature is untapped"
        act(s, "p1", type="activate_ability", card_id=plague.id, ability=ability_index(s, plague, "Tap enchanted creature"), targets=["p2"])
    check(s)


def test_tourach_gate_needs_the_land_untapped(cards):
    s = build(cards, ["Tourach's Gate"])
    forest = put(s, "Forest")
    gate = cast_on(s, "Tourach's Gate", forest, B=2, C=1)
    tap(s, forest)
    with pytest.raises(ActionError):  # "Activate only if enchanted land is untapped"
        act(s, "p1", type="activate_ability", card_id=gate.id, ability=ability_index(s, gate, "Tap enchanted land"))
    tap(s, forest, False)
    activate(s, gate, "Tap enchanted land")
    assert s.state.cards[forest.id].tapped
    check(s)


def test_betrothed_of_fire_sacrifices_only_a_creature_you_control(cards):
    """701.21a: you can't sacrifice what you don't control, so the cost can't be paid for an opponent's creature."""
    s = build(cards, ["Betrothed of Fire"])
    ox = make(s, "p2", "Ox", "Ox", "2/2")
    aura = cast_on(s, "Betrothed of Fire", ox, R=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=aura.id, ability=ability_index(s, aura, "Sacrifice enchanted creature"))
    assert ox.id in s.state.cards and s.state.cards[ox.id].zone == "p2:battlefield"
    check(s)


def test_natures_chosen_wants_a_white_untapped_creature_and_taps_it_once_a_turn(cards):
    """"Activate only if enchanted creature is white and untapped and only once each turn." — one subject, two adjectives; the cost taps the creature."""
    s = build(cards, ["Nature's Chosen"])
    angel = colored(s, "Angel", "W")
    forest = put(s, "Forest")
    tap(s, forest)
    chosen = cast_on(s, "Nature's Chosen", angel, G=1)
    index = ability_index(s, chosen, "Tap enchanted creature")
    activate(s, chosen, "Tap enchanted creature", targets=[forest.id])
    assert s.state.cards[angel.id].tapped and not s.state.cards[forest.id].tapped
    tap(s, angel, False)  # (untapped again by other means: only the once-a-turn limit is left to stop the second activation)
    tap(s, forest)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=chosen.id, ability=index, targets=[forest.id])
    check(s)


def test_natures_chosen_is_refused_for_a_creature_that_is_not_white(cards):
    s = build(cards, ["Nature's Chosen"])
    ape = colored(s, "Ape", "R")
    forest = put(s, "Forest")
    tap(s, forest)
    chosen = cast_on(s, "Nature's Chosen", ape, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=chosen.id, ability=ability_index(s, chosen, "Tap enchanted creature"), targets=[forest.id])
    assert not s.state.cards[ape.id].tapped
    check(s)


def test_betrothed_of_fire_sacrifice_pumps_your_creatures(cards):
    s = build(cards, ["Betrothed of Fire"])
    mine, goat = make(s, "p1", "Ape", "Ape", "2/2"), make(s, "p1", "Goat", "Goat", "1/1")
    aura = cast_on(s, "Betrothed of Fire", mine, R=1, C=1)
    activate(s, aura, "Sacrifice enchanted creature")
    assert mine.id not in s.state.cards and s.state.cards[aura.id].zone == "p1:graveyard"  # (704.5m: the Aura fell off)
    assert ch(s, goat).pt == (3, 1)
    check(s)


# -- what an Aura / Equipment does to the object it is attached to (the verbs that took only a target) ------------------------------------


def cast_spell(s, name, **mana):
    c = to_hand(s, name)
    pay(s, **mana)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    return c


def test_dramatic_accusation_shuffles_the_enchanted_creature_into_its_owners_library(cards):
    """"{U}{U}: Shuffle enchanted creature into its owner's library." — the owner's, not the Aura controller's (701.24); the Aura falls off (704.5m)."""
    s = build(cards, ["Dramatic Accusation"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    aura = cast_on(s, "Dramatic Accusation", bears, U=1, C=2)
    assert s.state.cards[bears.id].tapped  # "When this Aura enters, tap enchanted creature."
    activate(s, aura, "Shuffle enchanted creature", pay_mana={"U": 2})
    assert card_named(s, "Grizzly Bears", "p2").zone == "p2:library" and s.state.cards[aura.id].zone == "p1:graveyard"
    check(s)


def test_shattered_ego_puts_the_enchanted_creature_third_from_the_top(cards):
    s = build(cards, ["Shattered Ego"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    aura = cast_on(s, "Shattered Ego", bears, U=1)
    assert ch(s, bears).pt == (-1, 2)
    activate(s, aura, "Put enchanted creature", pay_mana={"U": 2, "C": 3})
    moved = card_named(s, "Grizzly Bears", "p2")
    assert s.state.zones["p2:library"].index(moved.id) == 2  # 401.4: two cards above it
    check(s)


def test_wellspring_takes_the_enchanted_land_for_the_turn(cards):
    """"When this Aura enters, gain control of enchanted land until end of turn." — the land goes back when the turn ends (611.2b)."""
    s = build(cards, ["Wellspring"], [], )
    island = put(s, "Island", "p2")
    cast_on(s, "Wellspring", island, G=1, W=1, C=1)
    assert s.state.cards[island.id].controller == "p1"
    to_phase(s, "main1", turn=s.state.turn.number + 1)
    assert s.state.cards[island.id].controller == "p2"
    check(s)


def test_wellspring_untaps_and_takes_the_land_again_at_your_upkeep(cards):
    """"At the beginning of your upkeep, untap enchanted land. You gain control of that land until end of turn." — "that land" is the enchanted land."""
    s = build(cards, ["Wellspring"])
    island = put(s, "Island", "p2")
    cast_on(s, "Wellspring", island, G=1, W=1, C=1)
    tap(s, island)
    to_phase(s, "upkeep", turn=s.state.turn.number + 2)  # Alice's next upkeep: the land is Bob's again until the trigger resolves
    settle(s)
    assert s.state.cards[island.id].controller == "p1" and not s.state.cards[island.id].tapped
    check(s)


def test_arachnus_web_destroys_itself_at_the_end_step_when_the_creature_is_big(cards):
    """"At the beginning of the end step, if enchanted creature's power is 4 or greater, destroy this Aura." — each end step, the creature as it is then."""
    s = build(cards, ["Arachnus Web"])
    ape = make(s, "p2", "Ape", "Ape", "3/3")
    aura = cast_on(s, "Arachnus Web", ape, G=1, C=2)
    to_phase(s, "end")
    settle(s)
    assert s.state.cards[aura.id].zone == "p1:battlefield"  # 3 power: it stays
    act(s, "p1", type="counter", card_ids=[ape.id], kind="+1/+1", delta=1)
    to_phase(s, "end", turn=s.state.turn.number + 1)  # Bob's end step: "the end step", any player's
    settle(s)
    assert s.state.cards[aura.id].zone == "p1:graveyard"
    check(s)


def test_frenzied_fugue_takes_untaps_and_hastes_the_enchanted_permanent(cards):
    """"gain control of enchanted permanent until end of turn. Untap that permanent. It gains haste until end of turn." — "that permanent" and "it" are the
    enchanted permanent."""
    s = build(cards, ["Frenzied Fugue"])
    ox = make(s, "p2", "Ox", "Ox")
    tap(s, ox)
    cast_on(s, "Frenzied Fugue", ox, R=1, C=3)
    assert s.state.cards[ox.id].controller == "p1" and not s.state.cards[ox.id].tapped and "haste" in ch(s, ox).keywords
    check(s)


def test_sword_of_the_paruns_taps_or_untaps_its_creature(cards):
    """"{3}: You may tap or untap equipped creature." (701.26a): the choice is made as it resolves."""
    s = build(cards, ["Sword of the Paruns"])
    sword, ape = put(s, "Sword of the Paruns"), make(s, "p1", "Ape", "Ape", "2/2")
    equip(s, sword, ape, 3, C=3)
    pay(s, C=3)
    act(s, "p1", type="activate_ability", card_id=sword.id, ability=ability_index(s, sword, "tap or untap"))
    pass_until_stack_empty(s)
    d = decision(s)
    assert d is not None and {o.id for o in d.options} >= {"tap", "untap"}
    choose(s, "tap")
    settle(s)
    assert s.state.cards[ape.id].tapped and ch(s, ape).pt == (4, 2)  # "As long as equipped creature is tapped, tapped creatures you control get +2/+0"
    check(s)


def test_cranial_ram_counts_artifacts_for_power_and_adds_one_toughness(cards):
    """"Equipped creature gets +X/+1, where X is the number of artifacts you control." (613.4c): X on one side, a fixed amount on the other — read as it changes."""
    s = build(cards, ["Cranial Ram", "Sol Ring"])
    cast_spell(s, "Cranial Ram", B=1, R=1)
    germ = next(iter(on_table(s, "Phyrexian Germ", "p1")))
    assert ch(s, germ).pt == (1, 1)  # one artifact (the Ram): 0/0 + 1/+1
    put(s, "Sol Ring")
    assert ch(s, germ).pt == (2, 1)
    check(s)


def test_junk_jet_doubles_its_creatures_power(cards):
    s = build(cards, ["Junk Jet"])
    jet = cast_spell(s, "Junk Jet", R=1, C=1)
    ape = make(s, "p1", "Ape", "Ape", "2/2")
    equip(s, jet, ape, 2, C=1)
    activate(s, jet, "Double equipped creature", pay_mana={"C": 3})
    assert ch(s, ape).pt == (4, 2)
    check(s)


def test_reality_acid_makes_the_enchanted_permanents_controller_sacrifice_it(cards):
    """"When this Aura leaves the battlefield, enchanted permanent's controller sacrifices it." — what it enchanted as it left (603.10a), its controller then."""
    s = build(cards, ["Reality Acid"])
    ox = make(s, "p2", "Ox", "Ox")
    aura = cast_on(s, "Reality Acid", ox, U=1, C=2)
    assert s.state.cards[aura.id].attached_to == ox.id and s.state.cards[aura.id].counters.get("time") == 3
    act(s, "p1", type="counter", card_ids=[aura.id], kind="time", delta=-2)  # (vanishing: the last time counter comes off at Alice's next upkeep)
    to_phase(s, "upkeep", turn=s.state.turn.number + 2)
    settle(s)
    assert s.state.cards[aura.id].zone == "p1:graveyard"  # sacrificed as the last counter was removed
    assert ox.id not in s.state.cards  # (a token that was sacrificed has ceased to exist)
    check(s)


def test_parasitic_implant_sacrifices_it_and_you_get_a_myr(cards):
    s = build(cards, ["Parasitic Implant"])
    ox = make(s, "p2", "Ox", "Ox")
    cast_on(s, "Parasitic Implant", ox, B=1, C=3)
    to_phase(s, "upkeep", turn=s.state.turn.number + 2)  # Alice's next upkeep
    settle(s)
    assert ox.id not in s.state.cards and len(on_table(s, "Phyrexian Myr", "p1")) == 1
    check(s)


# -- "When enchanted creature becomes tapped or is dealt damage" (603.2, 303.4b) ---------------------------------------------------------------


def test_cryoshatter_destroys_the_creature_when_it_becomes_tapped(cards):
    s = build(cards, ["Cryoshatter", "Probe Chill"])
    ape = make(s, "p1", "Ape", "Ape", "6/6")
    other = make(s, "p1", "Goat", "Goat", "6/6")
    cast_on(s, "Cryoshatter", ape, U=1, C=1)
    assert ch(s, ape).pt == (1, 6)
    cast_on(s, "Probe Chill", other, U=1)  # another creature becomes tapped: nothing
    assert other.id in s.state.cards and s.state.cards[other.id].tapped
    cast_on(s, "Probe Chill", ape, U=1)
    assert ape.id not in s.state.cards and other.id in s.state.cards
    check(s)


def test_cryoshatter_destroys_the_creature_when_it_is_dealt_damage(cards):
    s = build(cards, ["Cryoshatter", "Lightning Bolt"])
    ape = make(s, "p1", "Ape", "Ape", "6/6")
    cast_on(s, "Cryoshatter", ape, U=1, C=1)
    cast_on(s, "Lightning Bolt", ape, R=1)  # 3 damage to a 6/6: the Aura's trigger finishes it
    assert ape.id not in s.state.cards
    check(s)


# -- "an enchanted creature or enchantment creature you control" (Kestia, the Cultivator; 700.9, 303.4) -------------------------------------


def test_kestia_draws_for_enchanted_and_enchantment_creatures_only(cards):
    s = build(cards, ["Kestia, the Cultivator", "Maze's Mantle"])
    kestia = put(s, "Kestia, the Cultivator")  # an enchantment creature
    ape, goat = make(s, "p1", "Ape", "Ape", "2/2"), make(s, "p1", "Goat", "Goat", "2/2")
    cast_on(s, "Maze's Mantle", ape, G=1, C=2)  # the Ape is enchanted; the Goat is neither
    to_phase(s, "declare_attackers", turn=s.state.turn.number + 2)  # (Alice's next turn: the Ape and the Goat have lost their summoning sickness)
    before = hand_size(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (kestia, ape, goat)])
    pass_until_stack_empty(s)
    assert hand_size(s) == before + 2  # Kestia and the Ape, not the Goat
    check(s)


# -- Equipment tokens made with quoted abilities and equip (111.4, 702.6, 205.3g) -----------------------------------------------------------


def test_moira_brown_makes_a_book_equipment_that_counts_quest_counters(cards):
    s = build(cards, ["Moira Brown, Guide Author"])
    moira = cast_spell(s, "Moira Brown, Guide Author", R=1, W=1, C=1)
    book = next(iter(on_table(s, "Wasteland Survival Guide", "p1")))
    assert {"Book", "Equipment"} <= set(ch(s, book).subtypes) and "Artifact" in ch(s, book).types and book.token is not None
    equip(s, book, moira, 1, C=1)  # its own "equip {1}"
    assert s.state.cards[book.id].attached_to == moira.id and ch(s, moira).pt == (2, 3)  # no quest counter yet
    act(s, "p1", type="counter", card_ids=[moira.id], kind="quest", delta=2)
    assert ch(s, moira).pt == (4, 5)  # +1/+1 for each quest counter among permanents you control
    check(s)


def test_nahiris_ultimate_is_an_indestructible_equipment_with_equip_zero(cards):
    s = build(cards, ["Nahiri, the Lithomancer"])
    nahiri = put(s, "Nahiri, the Lithomancer")
    act(s, "p1", type="counter", card_ids=[nahiri.id], kind="loyalty", delta=10)  # (a card moved onto the table has none: enough for the −10)
    activate(s, nahiri, "Stoneforged Blade")
    blade = next(iter(on_table(s, "Stoneforged Blade", "p1")))
    assert "Equipment" in ch(s, blade).subtypes and "indestructible" in ch(s, blade).keywords
    ape = make(s, "p1", "Ape", "Ape", "2/2")
    equip(s, blade, ape, next(a.index for a in ch(s, blade).abilities if a.text.startswith("Equip {")))  # equip {0}: nothing to pay
    assert ch(s, ape).pt == (7, 7) and "double strike" in ch(s, ape).keywords
    check(s)


def test_icingdeath_leaves_a_legendary_equipment_when_it_dies(cards):
    s = build(cards, ["Icingdeath, Frost Tyrant"])
    drake = put(s, "Icingdeath, Frost Tyrant")
    kill(s, drake)
    tongue = next(iter(on_table(s, "Icingdeath, Frost Tongue", "p1")))
    assert "Legendary" in ch(s, tongue).supertypes and "Equipment" in ch(s, tongue).subtypes
    ape = make(s, "p1", "Ape", "Ape", "2/2")
    equip(s, tongue, ape, 2, W=1, C=1)
    assert ch(s, ape).pt == (4, 2)
    check(s)
