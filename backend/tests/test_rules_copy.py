"""The copy system (CR 707, 613.2 layer 1), app/rules/copying.py: copies of spells and abilities
(707.10: modes, X, kicker, targets and their division copied; not cast; "you may choose new
targets", 707.10c / 115.7d), storm (702.40), token copies with exceptions (707.9), entering as a
copy (707.5-707.6), becoming a copy (707.4), copiable values (707.2: not counters or other
effects; a copy of a copy, 707.3), "can't be copied" (113.6g), copies of spells ceasing to exist
off the stack (704.5d-e, 707.10a) and a permanent spell's copy becoming a token (608.3f).

Every card below is a real Commander-legal card; its Oracle text is transcribed from the card
database (the 2026-09-30 snapshot) and named in the comment above it."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.session import GameSession
from app.rules import coverage, scripts
from app.rules.characteristics import Characteristics, parse_type_line
from app.rules.oracle import parse_abilities
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, ch, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_trigger_context import responsive


def _card(name: str, number: str, cost: str, type_line: str, text: str, colors: list[str], **extra: object) -> dict:
    cmc = float(sum(int(s) if s.isdigit() else 1 for s in cost.replace("}", "").split("{")[1:] if s != "X"))
    return card(name, set_code="tcp", number=number, mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text,
                colors=colors, color_identity=colors, **extra)


EXTRA = [
    # Reverberate
    _card("Reverberate", "C1", "{R}{R}", "Instant",
          "Copy target instant or sorcery spell. You may choose new targets for the copy.", ["R"]),
    # Fork
    _card("Fork", "C2", "{R}{R}", "Instant",
          "Copy target instant or sorcery spell, except that the copy is red. You may choose new targets for the copy.", ["R"]),
    # Twincast
    _card("Twincast", "C3", "{U}{U}", "Instant",
          "Copy target instant or sorcery spell. You may choose new targets for the copy.", ["U"]),
    # Dualcaster Mage
    _card("Dualcaster Mage", "C4", "{1}{R}{R}", "Creature — Human Wizard",
          "Flash\nWhen this creature enters, copy target instant or sorcery spell. You may choose new targets for the copy.",
          ["R"], power="2", toughness="2"),
    # Strionic Resonator
    _card("Strionic Resonator", "C5", "{2}", "Artifact",
          "{2}, {T}: Copy target triggered ability you control. You may choose new targets for the copy. "
          "(A triggered ability uses the words \"when,\" \"whenever,\" or \"at.\")", []),
    # Clone
    _card("Clone", "C6", "{3}{U}", "Creature — Shapeshifter",
          "You may have this creature enter as a copy of any creature on the battlefield.", ["U"], power="0", toughness="0"),
    # Quicksilver Gargantuan
    _card("Quicksilver Gargantuan", "C7", "{5}{U}{U}", "Creature — Shapeshifter",
          "You may have this creature enter as a copy of any creature on the battlefield, except it's 7/7.", ["U"],
          power="7", toughness="7"),
    # Phantasmal Image
    _card("Phantasmal Image", "C8", "{1}{U}", "Creature — Illusion",
          "You may have this creature enter as a copy of any creature on the battlefield, except it's an Illusion in addition "
          "to its other types and it has \"When this creature becomes the target of a spell or ability, sacrifice it.\"",
          ["U"], power="0", toughness="0"),
    # Kiki-Jiki, Mirror Breaker
    _card("Kiki-Jiki, Mirror Breaker", "C9", "{2}{R}{R}{R}", "Legendary Creature — Goblin Shaman",
          "Haste\n{T}: Create a token that's a copy of target nonlegendary creature you control, except it has haste. "
          "Sacrifice it at the beginning of the next end step.", ["R"], power="2", toughness="2"),
    # The Jolly Balloon Man
    _card("The Jolly Balloon Man", "C10", "{1}{R}{W}", "Legendary Creature — Human Clown",
          "Haste\n{1}, {T}: Create a token that's a copy of another target creature you control, except it's a 1/1 red "
          "Balloon creature in addition to its other colors and types and it has flying and haste. Sacrifice it at the "
          "beginning of the next end step. Activate only as a sorcery.", ["R", "W"], power="1", toughness="4"),
    # Cackling Counterpart
    _card("Cackling Counterpart", "C11", "{1}{U}{U}", "Instant",
          "Create a token that's a copy of target creature you control.\nFlashback {5}{U}{U} (You may cast this card "
          "from your graveyard for its flashback cost. Then exile it.)", ["U"]),
    # Mirage Mirror
    _card("Mirage Mirror", "C12", "{3}", "Artifact",
          "{2}: This artifact becomes a copy of target artifact, creature, enchantment, or land until end of turn.", []),
    # Glorious Anthem
    _card("Glorious Anthem", "C13", "{1}{W}{W}", "Enchantment", "Creatures you control get +1/+1.", ["W"]),
    # Benalish Marshal
    _card("Benalish Marshal", "C14", "{W}{W}{W}", "Creature — Human Knight", "Other creatures you control get +1/+1.",
          ["W"], power="3", toughness="3"),
    # Arc Trail
    _card("Arc Trail", "C15", "{1}{R}", "Sorcery",
          "Arc Trail deals 2 damage to any target and 1 damage to any other target.", ["R"]),
    # Electrolyze
    _card("Electrolyze", "C16", "{1}{U}{R}", "Instant",
          "Electrolyze deals 2 damage divided as you choose among one or two targets.\nDraw a card.", ["R", "U"]),
    # Blaze
    _card("Blaze", "C17", "{X}{R}", "Sorcery", "Blaze deals X damage to any target.", ["R"]),
    # Boros Charm
    _card("Boros Charm", "C18", "{R}{W}", "Instant",
          "Choose one —\n• Boros Charm deals 4 damage to target player or planeswalker.\n• Permanents you control gain "
          "indestructible until end of turn.\n• Target creature gains double strike until end of turn.", ["R", "W"]),
    # Hurloon Battle Hymn
    _card("Hurloon Battle Hymn", "C19", "{2}{R}", "Instant",
          "Kicker {W} (You may pay an additional {W} as you cast this spell.)\nHurloon Battle Hymn deals 4 damage to target "
          "creature or planeswalker. If this spell was kicked, you gain 4 life.", ["R"]),
    # Angelic Chorus
    _card("Angelic Chorus", "C20", "{3}{W}{W}", "Enchantment",
          "Whenever a creature you control enters, you gain life equal to its toughness.", ["W"]),
    # Crusader of Odric
    _card("Crusader of Odric", "C21", "{2}{W}", "Creature — Human Soldier",
          "Crusader of Odric's power and toughness are each equal to the number of creatures you control.", ["W"],
          power="*", toughness="*"),
    # Choreographed Sparks
    _card("Choreographed Sparks", "C22", "{R}{R}", "Instant",
          "This spell can't be copied.\nChoose one or both —\n• Copy target instant or sorcery spell you control. You may "
          "choose new targets for the copy.\n• Copy target creature spell you control. The copy gains haste and \"At the "
          "beginning of the end step, sacrifice this token.\"", ["R"]),
    # Wall of Omens
    _card("Wall of Omens", "C23", "{1}{W}", "Creature — Wall", "Defender\nWhen this creature enters, draw a card.", ["W"],
          power="0", toughness="4"),
    # Solemn Simulacrum
    _card("Solemn Simulacrum", "C24", "{4}", "Artifact Creature — Golem",
          "When this creature enters, you may search your library for a basic land card, put that card onto the battlefield "
          "tapped, then shuffle.\nWhen this creature dies, you may draw a card.", [], power="2", toughness="2"),
    # Lithoform Engine
    _card("Lithoform Engine", "C25", "{4}", "Legendary Artifact",
          "{2}, {T}: Copy target activated or triggered ability you control. You may choose new targets for the copy.\n"
          "{3}, {T}: Copy target instant or sorcery spell you control. You may choose new targets for the copy.\n"
          "{4}, {T}: Copy target permanent spell you control. (The copy becomes a token.)", []),
    # Spark Double (its exception is an additional effect, 707.9e: refused)
    _card("Spark Double", "C26", "{3}{U}", "Creature — Illusion",
          "You may have this creature enter as a copy of a creature or planeswalker you control, except it enters with an "
          "additional +1/+1 counter on it if it's a creature, it enters with an additional loyalty counter on it if it's a "
          "planeswalker, and it isn't legendary.", ["U"], power="0", toughness="0"),
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


def prompt(s):
    d = decision(s)
    return d.prompt if d is not None else ""


def on_stack(s):
    return list(s.state.zones.get("stack", []))


def copies(s):
    """Spell copies on the stack (707.10: a copy of a spell is a spell with no card: shown as a token)."""
    return [c for c in on_stack(s) if s.state.cards[c].is_token and s.state.cards[c].ability is None]


def hold(s, pid="p1"):
    act(s, pid, type="set_prefs", hold_priority=True)


def pay(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def life(s, pid):
    return s.state.players[pid].life


def pass_once(s):
    act(s, s.state.rules.priority, type="pass_priority")


def resolve_top(s):
    """Everyone passes once: the top object resolves (or a decision opens)."""
    top = on_stack(s)[-1]
    for _ in range(4):
        if decision(s) is not None or top not in on_stack(s):
            return
        pass_once(s)


def on_battlefield(s, name, pid="p1"):
    c = named(s, name)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


# -- copies of spells (707.10) ----------------------------------------------------------------------------
def test_reverberate_copies_a_bolt_with_a_new_target(cards):
    s = build(cards, "Reverberate", "Lightning Bolt")
    responsive(s)
    hold(s)
    ogre = token(s, "p2", "Ogre", "3/3")
    bolt, rev = to_hand(s, "Lightning Bolt"), to_hand(s, "Reverberate")
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pay(s, R=2)
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[bolt.id])
    cast = s.state.rules.spells_this_turn("p1", s.state.turn.number)
    resolve_top(s)  # Reverberate resolves: the copy asks for its target (707.10c)
    assert prompt(s).startswith("Copy of Lightning Bolt")
    options = {o.id for o in decision(s).options}
    assert "keep" in options and ogre.id in options and "p2" not in options  # (the current target is "keep")
    choose(s, ogre.id)
    [copy] = copies(s)
    entry = s.state.rules.stack[copy]
    assert entry.copy_of is not None and entry.source_card == copy and [t.id for t in entry.targets] == [ogre.id]
    assert s.state.cards[copy].owner == "p1" and s.state.cards[copy].controller == "p1"  # 707.10
    assert s.state.rules.spells_this_turn("p1", s.state.turn.number) == cast  # 707.10: a copy isn't cast
    pass_until_stack_empty(s)
    assert ogre.id not in s.state.cards and life(s, "p2") == 37  # the copy killed the Ogre, the Bolt hit Bob
    assert copy not in s.state.cards  # (it ceased to exist as it left the stack, 707.10a)
    replay_matches(s)


def test_keeping_an_illegal_target_fizzles_a_new_legal_target_resolves(cards):
    """707.10c: a kept target stays even if illegal; 608.2b: a copy whose targets are all illegal
    doesn't resolve, one with a new legal target does."""
    s = build(cards, "Reverberate", "Twincast", "Lightning Bolt")
    responsive(s)
    hold(s)
    ogre, bear = token(s, "p2", "Ogre", "4/4"), token(s, "p2", "Bear", "2/2")
    bolt, rev, twin = to_hand(s, "Lightning Bolt"), to_hand(s, "Reverberate"), to_hand(s, "Twincast")
    pay(s, R=3, U=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[ogre.id])
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[bolt.id])
    act(s, "p1", type="cast_spell", card_id=twin.id, targets=[bolt.id])
    resolve_top(s)  # Twincast resolves: its copy keeps the Ogre as its target
    choose(s, "keep")
    [kept] = copies(s)
    assert [t.id for t in s.state.rules.stack[kept].targets] == [ogre.id]
    act(s, "p2", type="move", card_ids=[ogre.id], to={"zone": "exile"})  # the Ogre is gone (a token: it ceases to exist)
    resolve_top(s)  # the copy's only target is illegal: it does nothing (608.2b)
    assert kept not in s.state.cards and bear.id in s.state.cards
    resolve_top(s)  # Reverberate resolves: its copy gets a new target, the Bear
    choose(s, bear.id)
    pass_until_stack_empty(s)
    assert bear.id not in s.state.cards  # the new, legal target was hit
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and life(s, "p2") == 40  # the original did nothing
    replay_matches(s)
