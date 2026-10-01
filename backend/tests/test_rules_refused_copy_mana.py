"""Forms of the copy and mana families that used to be left manual (wave 3R3), researched against
CR 2026-09-25: magecraft "cast or copy" triggers (707.10), "copy that spell" in a cast trigger,
token copies of double-faced permanents (707.8a), general "Spend this mana only to …"
restrictions (106.6), mana abilities whose cost chooses objects (Ashnod's Altar, 605.3a / 602.2b),
"Put a -0/-1 counter on this creature" (Wall of Roots, 122.1a), the Urza lands, "Choose a color.
Add …" (Nykthos, 700.5), "you don't lose this mana" (106.4, 500.4) and Cabal Ritual's threshold
line (207.2c, 614.1a).

Every card below is a real Commander-legal card; its Oracle text is transcribed from the card
database (the 2026-09-30 snapshot)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.rules import mana as M
from app.rules import scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, ch, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches, rules
from tests.test_rules_trigger_context import responsive


def _card(name: str, number: str, cost: str, type_line: str, text: str, colors: list[str], **extra: object) -> dict:
    cmc = float(sum(int(s) if s.isdigit() else 1 for s in cost.replace("}", "").split("{")[1:] if s != "X"))
    return card(name, set_code="trc", number=number, mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text,
                colors=colors, color_identity=colors, **extra)


EXTRA = [
    # Archmage Emeritus
    _card("Archmage Emeritus", "R1", "{2}{U}{U}", "Creature — Human Wizard",
          "Magecraft — Whenever you cast or copy an instant or sorcery spell, draw a card.", ["U"], power="2", toughness="2"),
    # Deekah, Fractal Theorist
    _card("Deekah, Fractal Theorist", "R2", "{4}{U}", "Legendary Creature — Human Wizard",
          "Magecraft — Whenever you cast or copy an instant or sorcery spell, create a 0/0 green and blue Fractal creature "
          "token. Put X +1/+1 counters on it, where X is that spell's mana value.\n{3}{U}: Target creature token can't be "
          "blocked this turn.", ["U"], power="3", toughness="3"),
    # The Twelfth Doctor
    _card("The Twelfth Doctor", "R3", "{3}{U}{R}", "Legendary Creature — Time Lord Doctor",
          "The first spell you cast from anywhere other than your hand each turn has demonstrate. (When you cast that spell, "
          "you may copy it. If you do, choose an opponent to also copy it. A copy of a permanent spell becomes a token.)\n"
          "Whenever you copy a spell, put a +1/+1 counter on The Twelfth Doctor.", ["R", "U"], power="4", toughness="4"),
    # Reverberate
    _card("Reverberate", "R4", "{R}{R}", "Instant",
          "Copy target instant or sorcery spell. You may choose new targets for the copy.", ["R"]),
    # Swarm Intelligence
    _card("Swarm Intelligence", "R5", "{6}{U}", "Enchantment",
          "Whenever you cast an instant or sorcery spell, you may copy that spell. You may choose new targets for the copy.", ["U"]),
    # Cackling Counterpart
    _card("Cackling Counterpart", "R6", "{1}{U}{U}", "Instant",
          "Create a token that's a copy of target creature you control.\nFlashback {5}{U}{U} (You may cast this card from "
          "your graveyard for its flashback cost. Then exile it.)", ["U"]),
    # Castle Garenbrig
    _card("Castle Garenbrig", "R7", "", "Land",
          "This land enters tapped unless you control a Forest.\n{T}: Add {G}.\n{2}{G}{G}, {T}: Add six {G}. Spend this mana "
          "only to cast creature spells or activate abilities of creatures.", []),
    # Unclaimed Territory
    _card("Unclaimed Territory", "R8", "", "Land",
          "As this land enters, choose a creature type.\n{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only "
          "to cast a creature spell of the chosen type.", []),
    # Ashnod's Altar
    _card("Ashnod's Altar", "R9", "{3}", "Artifact", "Sacrifice a creature: Add {C}{C}.", []),
    # Phyrexian Altar
    _card("Phyrexian Altar", "R10", "{3}", "Artifact", "Sacrifice a creature: Add one mana of any color.", []),
    # Wall of Roots
    _card("Wall of Roots", "R11", "{1}{G}", "Creature — Plant Wall",
          "Defender\nPut a -0/-1 counter on this creature: Add {G}. Activate only once each turn.", ["G"], power="0", toughness="5"),
    # Urza's Tower
    _card("Urza's Tower", "R12", "", "Land — Urza's Tower",
          "{T}: Add {C}. If you control an Urza's Mine and an Urza's Power-Plant, add {C}{C}{C} instead.", []),
    # Urza's Mine
    _card("Urza's Mine", "R13", "", "Land — Urza's Mine",
          "{T}: Add {C}. If you control an Urza's Power-Plant and an Urza's Tower, add {C}{C} instead.", []),
    # Urza's Power Plant
    _card("Urza's Power Plant", "R14", "", "Land — Urza's Power-Plant",
          "{T}: Add {C}. If you control an Urza's Mine and an Urza's Tower, add {C}{C} instead.", []),
    # Nykthos, Shrine to Nyx
    _card("Nykthos, Shrine to Nyx", "R15", "", "Legendary Land",
          "{T}: Add {C}.\n{2}, {T}: Choose a color. Add an amount of mana of that color equal to your devotion to that color. "
          "(Your devotion to a color is the number of mana symbols of that color in the mana costs of permanents you control.)", []),
    # Su-Chi Cave Guard
    _card("Su-Chi Cave Guard", "R16", "{8}", "Artifact Creature — Construct",
          "Vigilance\nWard {4} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it "
          "unless that player pays {4}.)\nWhen this creature dies, add eight {C}. Until end of turn, you don't lose this mana as "
          "steps and phases end.", [], power="8", toughness="8"),
    # Cabal Ritual
    _card("Cabal Ritual", "R17", "{1}{B}", "Instant",
          "Add {B}{B}{B}.\nThreshold — Add {B}{B}{B}{B}{B} instead if there are seven or more cards in your graveyard.", ["B"]),
    # Grizzly Bears
    _card("Grizzly Bears", "R18", "{1}{G}", "Creature — Bear", "", ["G"], power="2", toughness="2"),
    # Huntmaster of the Fells // Ravager of the Fells
    card("Huntmaster of the Fells // Ravager of the Fells", set_code="trc", number="R19", layout="transform",
         mana_cost=None, cmc=4.0, type_line="Creature — Human Werewolf // Creature — Werewolf", colors=["G", "R"],
         color_identity=["G", "R"], image_uris=None,
         card_faces=[
             {"object": "card_face", "name": "Huntmaster of the Fells", "mana_cost": "{2}{R}{G}",
              "type_line": "Creature — Human Werewolf",
              "oracle_text": "Whenever this creature enters or transforms into Huntmaster of the Fells, create a 2/2 green Wolf "
                             "creature token and you gain 2 life.\nAt the beginning of each upkeep, if no spells were cast last "
                             "turn, transform this creature.",
              "power": "2", "toughness": "2", "colors": ["G", "R"]},
             {"object": "card_face", "name": "Ravager of the Fells", "mana_cost": "", "type_line": "Creature — Werewolf",
              "oracle_text": "Trample\nWhenever this creature transforms into Ravager of the Fells, it deals 2 damage to target "
                             "opponent or planeswalker and 2 damage to up to one target creature that player or that "
                             "planeswalker's controller controls.\nAt the beginning of each upkeep, if a player cast two or more "
                             "spells last turn, transform this creature.",
              "power": "4", "toughness": "4", "colors": ["G", "R"]},
         ]),
    # Jeska's Will
    _card("Jeska's Will", "R20", "{2}{R}", "Sorcery",
          "Choose one. If you control a commander as you cast this spell, you may choose both instead.\n• Add {R} for each card in "
          "target opponent's hand.\n• Exile the top three cards of your library. You may play them this turn.", ["R"]),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- helpers -------------------------------------------------------------------------------------------
def decision(s):
    return s.state.rules.decision


def choose(s, *options):
    d = decision(s)
    assert d is not None, "no decision is pending"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(options))


def pay(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def pool(s, pid="p1"):
    return dict(s.state.players[pid].mana)


def on_battlefield(s, name, pid="p1"):
    c = named(s, name)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def hand_size(s, pid="p1"):
    return len(zone(s.state, pid, "hand"))


def index_of(s, c, start):
    return next(a.index for a in ch(s, c).abilities if a.text.startswith(start))


def resolve_top(s):
    top = s.state.zones["stack"][-1]
    for _ in range(4):
        if decision(s) is not None or top not in s.state.zones.get("stack", []):
            return
        act(s, rules(s).priority, type="pass_priority")


# -- magecraft: "Whenever you cast or copy an instant or sorcery spell" (707.10) ---------------------------
def test_magecraft_triggers_on_casting_and_on_copying(cards):
    """Archmage Emeritus draws for Reverberate (cast) and for Reverberate's copy of the Bolt (707.10:
    copying a spell puts a copy on the stack under your control; it isn't cast, but "or copy" sees it)."""
    s = build(cards, "Archmage Emeritus", "Reverberate", "Lightning Bolt")
    on_battlefield(s, "Archmage Emeritus")
    responsive(s)
    bolt, rev = to_hand(s, "Lightning Bolt"), to_hand(s, "Reverberate")
    before = hand_size(s)
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # magecraft: one trigger
    resolve_top(s)  # (the draw trigger resolves; the Bolt waits)
    pay(s, R=2)
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[bolt.id])  # a second trigger
    resolve_top(s)
    assert hand_size(s) == before - 2 + 2
    resolve_top(s)  # Reverberate resolves: the copy (keep the target)
    if decision(s) is not None:
        choose(s, "keep")
    resolve_top(s)  # magecraft for the copy
    assert hand_size(s) == before - 2 + 3
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 34
    replay_matches(s)


def test_that_spells_mana_value_is_the_copy_after_a_token_is_created(cards):
    """Deekah: "create a … Fractal token. Put X +1/+1 counters on it, where X is that spell's mana
    value" — X is the spell's (the cast trigger's event), not the token's (0)."""
    s = build(cards, "Deekah, Fractal Theorist", "Lightning Bolt")
    on_battlefield(s, "Deekah, Fractal Theorist")
    responsive(s)
    bolt = to_hand(s, "Lightning Bolt")
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    resolve_top(s)
    fractal = next(c for c in s.state.cards.values() if c.name == "Fractal")
    assert fractal.counters.get("+1/+1") == 1
    pass_until_stack_empty(s)
    replay_matches(s)


def test_whenever_you_copy_a_spell_ignores_casting(cards):
    """The Twelfth Doctor's "Whenever you copy a spell": not the cast Reverberate, only its copy."""
    s = build(cards, "The Twelfth Doctor", "Reverberate", "Lightning Bolt")
    doctor = on_battlefield(s, "The Twelfth Doctor")
    responsive(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    bolt, rev = to_hand(s, "Lightning Bolt"), to_hand(s, "Reverberate")
    pay(s, R=3)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[bolt.id])
    assert len(s.state.zones["stack"]) == 2  # (no trigger for casting)
    resolve_top(s)
    if decision(s) is not None:
        choose(s, "keep")
    pass_until_stack_empty(s)
    assert s.state.cards[doctor.id].counters.get("+1/+1") == 1
    assert s.state.players["p2"].life == 34
    replay_matches(s)


def test_magecraft_wording_parses_as_a_cast_or_copy_condition():
    from app.rules import events

    cond = events.parse_condition("you cast or copy an instant or sorcery spell")
    assert cond is not None and cond["copy"] == "or" and cond["event"] == "cast"
    assert events.parse_condition("you copy a spell")["copy"] == "only"
    # (a cast-only detail with a copy: refused)
    assert events.parse_condition("you cast or copy your second spell each turn") is None


# -- "copy that spell" in a cast trigger -------------------------------------------------------------
def test_swarm_intelligence_copies_the_cast_spell(cards):
    s = build(cards, "Swarm Intelligence", "Lightning Bolt")
    on_battlefield(s, "Swarm Intelligence")
    responsive(s)
    bear = token(s, "p2", "Bear", "2/2")
    bolt = to_hand(s, "Lightning Bolt")
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    resolve_top(s)  # the trigger: "you may copy that spell"
    if decision(s) is not None and decision(s).kind != "choose_one":
        choose(s, decision(s).options[0].id)  # (yes)
    d = decision(s)
    assert d is not None and "Copy of Lightning Bolt" in d.prompt
    choose(s, bear.id)
    pass_until_stack_empty(s)
    assert bear.id not in s.state.cards and s.state.players["p2"].life == 37
    replay_matches(s)


def test_copy_it_must_be_the_first_instruction_of_a_cast_trigger():
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import parse_abilities

    def defs(text):
        c = Characteristics(name="Test", types=frozenset({"Enchantment"}), oracle_text=text,
                            abilities=tuple(parse_abilities(text, spell=False)))
        return scripts.definitions(c)

    assert defs("Whenever you cast an instant or sorcery spell, copy it.")  # (the spell cast)
    assert not defs("Whenever a creature dies, copy that spell.")  # (no spell: refused)


# -- token copies of double-faced permanents (707.8a) ------------------------------------------------
def test_token_copy_of_a_transformed_permanent_is_double_faced_with_the_back_face_up(cards):
    s = build(cards, "Huntmaster of the Fells // Ravager of the Fells", "Cackling Counterpart")
    hunt = on_battlefield(s, "Huntmaster of the Fells // Ravager of the Fells")
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)  # (its enters trigger: a Wolf)
    act(s, "p1", type="set_face", card_id=hunt.id, face=1)  # transformed (by hand): Ravager of the Fells
    wolves = sum(1 for c in s.state.cards.values() if c.name == "Wolf")
    spell = to_hand(s, "Cackling Counterpart")
    pay(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[hunt.id])
    pass_until_stack_empty(s)
    tok = next(c for c in s.state.cards.values() if c.is_token and c.id != hunt.id and c.name != "Wolf"
               and c.zone == "p1:battlefield")
    tch = ch(s, tok)
    assert tok.face == 1 and tch.name == "Ravager of the Fells" and tch.pt == (4, 4) and "trample" in tch.keywords
    assert sum(1 for c in s.state.cards.values() if c.name == "Wolf") == wolves  # (no enters trigger on the back face)
    act(s, "p1", type="set_face", card_id=tok.id, face=0)  # 707.8a: its front face is Huntmaster's
    assert ch(s, tok).name == "Huntmaster of the Fells" and ch(s, tok).pt == (2, 2)
    replay_matches(s)


# -- "Spend this mana only to …" (106.6) --------------------------------------------------------------
def test_restriction_grammar():
    q = M.parse_spend("Spend this mana only to cast creature spells or activate abilities of creatures")
    assert q is not None and q.startswith("q:")
    assert M.parse_spend("Spend this mana only to cast Vampire, Cleric, and/or Demon spells") is not None
    assert M.parse_spend("Spend this mana only to cast a Time Lord or Alien spell or activate an ability of a Time Lord or Alien")
    # refused: what the payer can't check
    for text in ("Spend this mana only to cast spells from exile", "Spend this mana only to pay cumulative upkeep costs",
                 "Spend this mana only to cast kicked spells", "Spend this mana only to cast spells you don't own"):
        assert M.parse_spend(text) is None
    assert M.parse_mana_ability("{T}: Add one mana of any color. Spend this mana only to cast a legendary spell, "
                                "and that spell can't be countered.") is None  # (a rider: manual)


def test_castle_garenbrig_pays_for_creatures_only(cards):
    from app.rules.casting import Purpose, spend_allowed

    s = build(cards, "Castle Garenbrig", "Grizzly Bears", "Lightning Bolt")
    castle = on_battlefield(s, "Castle Garenbrig")
    parsed = M.parse_mana_ability(ch(s, castle).abilities[2].text)
    assert parsed is not None and parsed.options == (("G",) * 6,)
    bears, bolt = ch(s, named(s, "Grizzly Bears")), ch(s, named(s, "Lightning Bolt"))
    assert spend_allowed(parsed.spend_only, Purpose(spell=bears))
    assert not spend_allowed(parsed.spend_only, Purpose(spell=bolt))
    assert spend_allowed(parsed.spend_only, Purpose(ability_of=bears))


def test_unclaimed_territory_needs_the_chosen_type(cards):
    from app.rules.casting import Purpose, mana_abilities, spend_allowed

    s = build(cards, "Unclaimed Territory", "Grizzly Bears", "Archmage Emeritus")
    land = on_battlefield(s, "Unclaimed Territory")
    if decision(s) is not None:  # "As this land enters, choose a creature type"
        choose(s, next(o.id for o in decision(s).options if o.label == "Bear" or o.id == "Bear"))
    else:
        act(s, "p1", type="set_choice", card_id=land.id, key="Chosen creature type", value="Bear")
    found = dict(mana_abilities(s.state, s.state.cards[land.id], s.cards))
    restricted = [ab for ab in found.values() if ab.spend_only]
    assert restricted
    q = restricted[0].spend_only
    assert spend_allowed(q, Purpose(spell=ch(s, named(s, "Grizzly Bears"))))
    assert not spend_allowed(q, Purpose(spell=ch(s, named(s, "Archmage Emeritus"))))


# -- mana abilities whose cost chooses objects (Ashnod's Altar) ------------------------------------------
def test_ashnods_altar_asks_what_to_sacrifice_then_adds_two(cards):
    s = build(cards, "Ashnod's Altar")
    altar = on_battlefield(s, "Ashnod's Altar")
    a, b = token(s, "p1", "Goblin", "1/1"), token(s, "p1", "Elf", "1/1")
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0)
    d = decision(s)
    assert d is not None and d.kind == "choose_cards" and {o.id for o in d.options} == {a.id, b.id}
    choose(s, b.id)
    assert pool(s) == {"C": 2} and b.id not in s.state.cards and a.id in s.state.cards
    replay_matches(s)


def test_ashnods_altar_is_never_used_by_the_auto_payer(cards):
    from app.rules.casting import mana_sources

    s = build(cards, "Ashnod's Altar")
    altar = on_battlefield(s, "Ashnod's Altar")
    token(s, "p1", "Goblin", "1/1")
    assert all(src.card_id != altar.id for src in mana_sources(s.state, "p1", s.cards))


def test_phyrexian_altar_color_is_chosen_after_the_sacrifice(cards):
    s = build(cards, "Phyrexian Altar")
    altar = on_battlefield(s, "Phyrexian Altar")
    gob = token(s, "p1", "Goblin", "1/1")
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0, cost_choices=[{"component": 0, "cards": [gob.id]}])
    assert gob.id not in s.state.cards  # (the cost is paid; the color is chosen as it resolves)
    d = decision(s)
    assert d is not None and d.kind == "choose_one"
    choose(s, next(o.id for o in d.options if o.label == "{B}"))
    assert pool(s) == {"B": 1}
    replay_matches(s)


# -- Wall of Roots (122.1a) ------------------------------------------------------------------------------
def test_wall_of_roots_puts_a_minus_zero_minus_one_counter_once_each_turn(cards):
    s = build(cards, "Wall of Roots")
    wall = on_battlefield(s, "Wall of Roots")
    k = index_of(s, wall, "Put a -0/-1")
    act(s, "p1", type="activate_ability", card_id=wall.id, ability=k)
    assert pool(s) == {"G": 1} and s.state.cards[wall.id].counters == {"-0/-1": 1}
    assert ch(s, wall).pt == (0, 4)  # (613.4c: the counter counts)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=wall.id, ability=k)  # once each turn
    replay_matches(s)


# -- the Urza lands ----------------------------------------------------------------------------------------
def test_urza_lands_add_more_with_the_set(cards):
    from app.rules.casting import mana_abilities

    s = build(cards, "Urza's Tower", "Urza's Mine", "Urza's Power Plant")
    tower = on_battlefield(s, "Urza's Tower")
    assert dict(mana_abilities(s.state, s.state.cards[tower.id], s.cards))[0].options == (("C",),)
    mine = on_battlefield(s, "Urza's Mine")
    assert dict(mana_abilities(s.state, s.state.cards[tower.id], s.cards))[0].options == (("C",),)
    on_battlefield(s, "Urza's Power Plant")
    assert dict(mana_abilities(s.state, s.state.cards[tower.id], s.cards))[0].options == (("C", "C", "C"),)
    assert dict(mana_abilities(s.state, s.state.cards[mine.id], s.cards))[0].options == (("C", "C"),)
    act(s, "p1", type="activate_ability", card_id=tower.id, ability=0)
    assert pool(s) == {"C": 3}
    replay_matches(s)


# -- Nykthos: "Choose a color. Add …" (700.5) ----------------------------------------------------------------
def test_nykthos_adds_devotion_to_the_chosen_color(cards):
    from app.rules.casting import mana_abilities

    s = build(cards, "Nykthos, Shrine to Nyx", "Archmage Emeritus", "Grizzly Bears")
    nyk = on_battlefield(s, "Nykthos, Shrine to Nyx")
    on_battlefield(s, "Archmage Emeritus")  # {2}{U}{U}: devotion to blue 2
    on_battlefield(s, "Grizzly Bears")  # {1}{G}: devotion to green 1
    found = dict(mana_abilities(s.state, s.state.cards[nyk.id], s.cards))
    assert set(found[1].options) == {("U", "U"), ("G",)}
    pay(s, C=2)
    act(s, "p1", type="activate_ability", card_id=nyk.id, ability=1, mana_choice=None)
    d = decision(s)
    assert d is not None
    choose(s, next(o.id for o in d.options if o.label == "{U}{U}"))
    assert pool(s) == {"U": 2}
    replay_matches(s)


# -- "Until end of turn, you don't lose this mana as steps and phases end" (106.4, 500.4) --------------------
def test_kept_mana_survives_steps_until_the_cleanup_step(cards):
    s = build(cards, "Su-Chi Cave Guard", "Grizzly Bears")
    guard = on_battlefield(s, "Su-Chi Cave Guard")
    act(s, "p1", type="counter", card_ids=[guard.id], kind="-1/-1", delta=8)
    act(s, "p1", type="pass_priority")  # 704.5f: it dies; its trigger
    pass_until_stack_empty(s)
    assert pool(s) == {"C": 8}
    pay(s, C=1, G=1)  # one {C} more that isn't kept: spending uses it first
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    pass_until_stack_empty(s)
    assert pool(s) == {"C": 8}
    for _ in range(4):  # the main phase ends: the mana stays
        if s.state.turn.phase != "main1":
            break
        act(s, rules(s).priority, type="pass_priority")
    assert s.state.turn.phase != "main1" and pool(s) == {"C": 8}
    replay_matches(s)


def test_kept_mana_is_spent_last_and_ends_with_the_turn(cards):
    from app.rules import kept_mana

    s = build(cards, "Su-Chi Cave Guard")
    guard = on_battlefield(s, "Su-Chi Cave Guard")
    act(s, "p1", type="counter", card_ids=[guard.id], kind="-1/-1", delta=8)
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    pay(s, C=1)  # one more {C}, not kept
    assert kept_mana.kept(s.state, "p1") == {"C": 8}
    s.state.rules.kept_mana[0]["turn"] = s.state.turn.number  # (unchanged: the record is this turn's)
    for _ in range(40):  # to the next turn
        if s.state.turn.number > 1 and s.state.turn.active_player == "p2":
            break
        d = decision(s)
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            break
        else:
            act(s, rules(s).priority, type="pass_priority")
    assert pool(s) == {}  # 514.2 / 500.4: the effect ended in the cleanup step, then the pool emptied
    assert s.state.rules.kept_mana == []


# -- Cabal Ritual / Jeska's Will ---------------------------------------------------------------------------
def test_jeskas_will_mode_targets_an_opponent_and_counts_their_hand():
    found = scripts.parse_effects("Add {R} for each card in target opponent's hand.")
    assert found is not None and found[1] == "opponent" and found[0][0]["n"] == {"hand": "target"}
