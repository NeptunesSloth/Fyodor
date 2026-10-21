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
    # Diregraf Ghoul
    _card("Diregraf Ghoul", "C27", "{B}", "Creature — Zombie", "This creature enters tapped.", ["B"], power="2", toughness="2"),
    # Quirion Elves
    _card("Quirion Elves", "C28", "{1}{G}", "Creature — Elf Druid",
          "As this creature enters, choose a color.\n{T}: Add {G}.\n{T}: Add one mana of the chosen color.", ["G"],
          power="1", toughness="1"),
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


def game(cards, alice=(), bob=()):
    """Alice (Krenko) and Bob (Atraxa) with these cards in their decks; Alice's main phase."""
    from app.game.factory import PlayerSetup, new_game
    from tests.game_helpers import deck, enable

    a = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in alice), (9, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def hand_of(s, pid, name):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
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


def test_storm_copies_choose_new_targets_per_copy(cards):
    """702.40a: storm's copies are real spell copies; "choose new targets for each copy": one copy
    keeps Bob, the other goes to a creature."""
    s = build(cards, "Grapeshot", "Lightning Bolt", "Blaze")
    ogre = token(s, "p2", "Ogre", "1/1")
    bolt, blaze, grapeshot = to_hand(s, "Lightning Bolt"), to_hand(s, "Blaze"), to_hand(s, "Grapeshot")
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # two spells before it this turn
    pass_until_stack_empty(s)
    pay(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=blaze.id, targets=["p2"], x_value=1)
    pass_until_stack_empty(s)
    pay(s, R=1, C=1)
    responsive(s)
    act(s, "p1", type="cast_spell", card_id=grapeshot.id, targets=["p2"])
    pass_once(s)
    resolve_top(s)  # the storm trigger resolves
    assert "Storm: 2 copies of Grapeshot" in prompt(s)
    choose(s, "choose")
    choose(s, "keep")  # the first copy keeps Bob
    first = copies(s)
    choose(s, ogre.id)  # the second one goes to the Ogre
    assert len(copies(s)) == 2 and first[0] in copies(s)
    assert [t.id for t in s.state.rules.stack[copies(s)[1]].targets] == [ogre.id]
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 - 3 - 1 - 1 - 1 and ogre.id not in s.state.cards
    replay_matches(s)


def test_new_targets_per_target_group_and_the_final_set_must_be_legal(cards):
    """Arc Trail has two words "target" (the second "any other target", 115.3): the copy keeps one
    and changes the other; changing a target to the other one's object is refused and asked again
    (115.7d: the new targets must not make the unchanged ones illegal)."""
    s = build(cards, "Arc Trail", "Reverberate")
    responsive(s)
    hold(s)
    ogre, bear = token(s, "p2", "Ogre", "5/5"), token(s, "p2", "Bear", "5/5")
    trail, rev = to_hand(s, "Arc Trail"), to_hand(s, "Reverberate")
    pay(s, R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=trail.id, targets=[ogre.id, "p2"], target_counts=[1, 1])
    pay(s, R=2)
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[trail.id])
    resolve_top(s)
    assert "(1 of 2)" in prompt(s)
    choose(s, "p2")  # 2 damage: Bob instead of the Ogre …
    choose(s, "keep")  # … and 1 damage: still Bob — the same object for "any other target": refused
    assert "(1 of 2)" in prompt(s)  # asked again (115.7d)
    choose(s, "keep")  # 2 damage: still the Ogre
    assert ogre.id not in {o.id for o in decision(s).options}  # ("any other target": not the Ogre again)
    choose(s, bear.id)  # 1 damage: the Bear instead of Bob
    [copy] = copies(s)
    entry = s.state.rules.stack[copy]
    assert [[t.id for t in g] for g in entry.groups] == [[ogre.id], [bear.id]]
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 4 and s.state.cards[bear.id].damage == 1 and life(s, "p2") == 39
    replay_matches(s)


def test_a_copy_keeps_the_division_of_divided_damage(cards):
    """601.2d / 115.7f: Electrolyze's 1 + 1 stays as announced on the copy; each copy draws too."""
    s = build(cards, "Electrolyze", "Reverberate")
    responsive(s)
    hold(s)
    ogre = token(s, "p2", "Ogre", "5/5")
    zap, rev = to_hand(s, "Electrolyze"), to_hand(s, "Reverberate")
    hand = len(zone(s.state, "p1", "hand"))
    pay(s, U=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=zap.id, targets=[ogre.id, "p2"], target_counts=[2], division=[1, 1])
    pay(s, R=2)
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[zap.id])
    resolve_top(s)
    choose(s, "keep")
    choose(s, "keep")
    [copy] = copies(s)
    assert s.state.rules.stack[copy].division == [[1, 1]]
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 2 and life(s, "p2") == 38
    assert len(zone(s.state, "p1", "hand")) == hand - 2 + 2  # both spells left the hand; each drew a card
    replay_matches(s)


def test_a_modal_spells_copy_keeps_its_mode(cards):
    """700.2g: the copy has the mode chosen for the original (and it can't be changed)."""
    s = build(cards, "Boros Charm", "Reverberate")
    responsive(s)
    hold(s)
    charm, rev = to_hand(s, "Boros Charm"), to_hand(s, "Reverberate")
    pay(s, R=1, W=1)
    act(s, "p1", type="cast_spell", card_id=charm.id, modes=[0], targets=["p2"])
    pay(s, R=2)
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[charm.id])
    resolve_top(s)
    assert {o.id for o in decision(s).options} >= {"keep", "p1"}  # (the mode's target: a player or planeswalker)
    choose(s, "keep")
    [copy] = copies(s)
    assert s.state.rules.stack[copy].modes == [0]
    pass_until_stack_empty(s)
    assert life(s, "p2") == 32
    replay_matches(s)


def test_an_x_spells_copy_keeps_x(cards):
    s = build(cards, "Blaze", "Reverberate")
    responsive(s)
    hold(s)
    ogre = token(s, "p2", "Ogre", "5/5")
    blaze, rev = to_hand(s, "Blaze"), to_hand(s, "Reverberate")
    pay(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=blaze.id, targets=["p2"], x_value=3)
    pay(s, R=2)
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[blaze.id])
    resolve_top(s)
    choose(s, ogre.id)
    [copy] = copies(s)
    assert s.state.rules.stack[copy].x == 3 and s.state.cards[copy].stack_info.x == 3
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 3 and life(s, "p2") == 37
    replay_matches(s)


def test_a_kicked_spells_copy_is_kicked(cards):
    """707.10: a copy has the original's additional costs — kicked (702.33d)."""
    s = build(cards, "Hurloon Battle Hymn", "Reverberate")
    responsive(s)
    hold(s)
    ogre, bear = token(s, "p2", "Ogre", "5/5"), token(s, "p2", "Bear", "5/5")
    hymn, rev = to_hand(s, "Hurloon Battle Hymn"), to_hand(s, "Reverberate")
    pay(s, R=1, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=hymn.id, targets=[ogre.id], kicker=1)
    pay(s, R=2)
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[hymn.id])
    resolve_top(s)
    choose(s, bear.id)
    [copy] = copies(s)
    assert s.state.rules.stack[copy].kicked == 1
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 4 and s.state.cards[bear.id].damage == 4
    assert life(s, "p1") == 48  # each gained 4
    replay_matches(s)


def test_fork_makes_a_red_copy_and_a_copy_of_that_copy_is_red_too(cards):
    """707.9b: Fork's "except that the copy is red" is part of the copy's copiable values, so a
    copy of the copy is red as well (707.3); the original stays blue."""
    s = build(cards, "Opt", "Fork", "Twincast")
    responsive(s)
    hold(s)
    opt, fork, twin = to_hand(s, "Opt"), to_hand(s, "Fork"), to_hand(s, "Twincast")
    pay(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    pay(s, R=2)
    act(s, "p1", type="cast_spell", card_id=fork.id, targets=[opt.id])
    resolve_top(s)
    [red] = copies(s)
    assert ch(s, s.state.cards[red]).colors == frozenset({"R"}) and ch(s, opt).colors == frozenset({"U"})
    pay(s, U=2)
    act(s, "p1", type="cast_spell", card_id=twin.id, targets=[red])
    resolve_top(s)
    second = [c for c in copies(s) if c != red]
    assert len(second) == 1 and ch(s, s.state.cards[second[0]]).colors == frozenset({"R"})
    assert ch(s, s.state.cards[second[0]]).name == "Opt"
    replay_matches(s)


def test_a_copy_can_be_countered_and_ceases_to_exist(cards):
    """A copy of a spell is a spell (707.10): Counterspell can target it; countered, it ceases to
    exist (704.5e / 707.10a) — it is in no graveyard."""
    s = game(cards, alice=("Lightning Bolt", "Reverberate"), bob=("Counterspell",))
    responsive(s)
    hold(s)
    bolt, rev = to_hand(s, "Lightning Bolt"), to_hand(s, "Reverberate")
    counter = hand_of(s, "p2", "Counterspell")
    pay(s, R=3)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[bolt.id])
    resolve_top(s)
    choose(s, "keep")
    [copy] = copies(s)
    pass_once(s)  # Alice passes; Bob counters the copy
    pay(s, "p2", U=2)
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[copy])
    pass_until_stack_empty(s)
    assert copy not in s.state.cards and life(s, "p2") == 37  # the copy is gone, the original still hit
    assert all(copy not in ids for ids in s.state.zones.values())
    replay_matches(s)


def test_a_spell_that_cant_be_copied_isnt(cards):
    """113.6g: "This spell can't be copied." functions on the stack: Reverberate does nothing."""
    s = build(cards, "Choreographed Sparks", "Reverberate", "Lightning Bolt")
    responsive(s)
    hold(s)
    sparks, rev = to_hand(s, "Choreographed Sparks"), to_hand(s, "Reverberate")
    bolt = to_hand(s, "Lightning Bolt")
    pay(s, R=5)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=sparks.id, modes=[0], targets=[bolt.id])
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[sparks.id])
    resolve_top(s)
    assert not copies(s) and on_stack(s) == [bolt.id, sparks.id]
    replay_matches(s)


def test_dualcaster_mage_copies_a_spell_as_it_enters(cards):
    s = build(cards, "Dualcaster Mage", "Lightning Bolt")
    responsive(s)
    hold(s)
    bolt, mage = to_hand(s, "Lightning Bolt"), to_hand(s, "Dualcaster Mage")
    pay(s, R=3, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=mage.id)
    resolve_top(s)  # the Mage enters (flash); its trigger targets the Bolt
    d = decision(s)
    if d is not None and d.resume.get("step") == "trigger_target":
        choose(s, bolt.id)
    resolve_top(s)  # the trigger resolves: a copy, keeping Bob or choosing Alice
    choose(s, "keep")
    pass_until_stack_empty(s)
    assert life(s, "p2") == 34
    replay_matches(s)


# -- copies of abilities (707.10b) -------------------------------------------------------------------------
def test_strionic_resonator_copies_a_trigger_with_its_event(cards):
    """A copied triggered ability keeps what it triggered on (603.2, 608.2k): Angelic Chorus's copy
    gains life equal to the same creature's toughness; it has the same source (707.10b)."""
    s = build(cards, "Strionic Resonator", "Angelic Chorus", "Grizzly Bears")
    responsive(s)
    hold(s)
    on_battlefield(s, "Strionic Resonator")
    on_battlefield(s, "Angelic Chorus")
    bears = to_hand(s, "Grizzly Bears")
    pay(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    resolve_top(s)  # the Bears enter: Angelic Chorus triggers
    for _ in range(3):
        if any(e.kind == "trigger" for e in s.state.rules.stack.values()):
            break
        pass_once(s)
    trigger = next(c for c, e in s.state.rules.stack.items() if e.kind == "trigger")
    pay(s, C=2)
    resonator = named(s, "Strionic Resonator")
    act(s, "p1", type="activate_ability", card_id=resonator.id, ability=0, targets=[trigger])
    resolve_top(s)  # the Resonator's ability: a copy of the trigger
    copy = next(c for c, e in s.state.rules.stack.items() if e.copy_of is not None)
    original, copied = s.state.rules.stack[trigger], s.state.rules.stack[copy]
    assert copied.source_card == original.source_card and copied.event == original.event  # 707.10b, 603.2
    assert s.state.cards[copy].ability is not None
    pass_until_stack_empty(s)
    assert life(s, "p1") == 44  # 2 + 2: the Bears' toughness, twice
    replay_matches(s)


# -- a permanent spell's copy becomes a token (608.3f) ------------------------------------------------------
def test_a_copy_of_a_permanent_spell_becomes_a_token(cards):
    s = build(cards, "Lithoform Engine", "Wall of Omens")
    responsive(s)
    hold(s)
    engine = on_battlefield(s, "Lithoform Engine")
    wall = to_hand(s, "Wall of Omens")
    hand = len(zone(s.state, "p1", "hand"))
    pay(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=wall.id)
    pay(s, C=4)
    act(s, "p1", type="activate_ability", card_id=engine.id, ability=2, targets=[wall.id])
    resolve_top(s)  # a copy of the Wall spell (707.10f)
    [copy] = copies(s)
    pass_until_stack_empty(s)
    token_wall = s.state.cards[copy]
    assert token_wall.is_token and token_wall.zone == "p1:battlefield" and ch(s, token_wall).name == "Wall of Omens"
    assert s.state.cards[wall.id].zone == "p1:battlefield"
    assert len(zone(s.state, "p1", "hand")) == hand - 1 + 2  # both Walls' "draw a card" (it entered: 608.3f)
    replay_matches(s)


# -- entering as a copy (707.5, 707.6) --------------------------------------------------------------------
def cast_clone(s, name="Clone", pick=None, **mana):
    clone = to_hand(s, name)
    pay(s, **(mana or {"U": 1, "C": 3}))
    act(s, "p1", type="cast_spell", card_id=clone.id)
    for _ in range(6):
        d = decision(s)
        if d is not None and d.prompt.endswith("to copy"):
            choose(s, pick or d.options[0].id)
            break
        if not on_stack(s):
            break
        pass_once(s)
    return clone


def test_clone_copies_a_creature_but_not_its_counters_and_its_enters_ability_triggers(cards):
    """707.2: counters aren't copied; 707.5: the copied "When this creature enters" triggers."""
    s = build(cards, "Clone", "Wall of Omens")
    wall = on_battlefield(s, "Wall of Omens")
    act(s, "p1", type="counter", card_ids=[wall.id], kind="+1/+1", delta=2)
    hand = len(zone(s.state, "p1", "hand"))
    clone = cast_clone(s, pick=wall.id)  # (to the hand, then cast)
    pass_until_stack_empty(s)
    c = ch(s, s.state.cards[clone.id])
    assert c.name == "Wall of Omens" and c.pt == (0, 4) and "defender" in c.keywords
    assert ch(s, wall).pt == (2, 6)
    assert len(zone(s.state, "p1", "hand")) == hand + 1  # the copied enters ability drew a card
    replay_matches(s)


def test_clone_of_a_lord_has_its_static_ability(cards):
    """Static abilities are read from copiable values (613.2c): two Marshals pump each other."""
    s = build(cards, "Clone", "Benalish Marshal")
    marshal = on_battlefield(s, "Benalish Marshal")
    bear = token(s, "p1", "Bear", "2/2")
    clone = cast_clone(s, pick=marshal.id)
    pass_until_stack_empty(s)
    assert ch(s, s.state.cards[clone.id]).pt == (4, 4) and ch(s, marshal).pt == (4, 4)
    assert ch(s, bear).pt == (4, 4)
    replay_matches(s)


def test_clone_may_copy_nothing_and_a_dying_clone_has_the_copied_dies_ability(cards):
    s = build(cards, "Clone", "Solemn Simulacrum")
    solemn = on_battlefield(s, "Solemn Simulacrum")
    clone = cast_clone(s, pick=solemn.id)
    pass_until_stack_empty(s)
    for _ in range(4):  # (Solemn's own "you may search" enters trigger, copied: decline it)
        d = decision(s)
        if d is None:
            break
        choose(s, "no" if any(o.id == "no" for o in d.options) else d.options[0].id)
        pass_until_stack_empty(s)
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="set_damage", card_ids=[clone.id], value=2)
    pass_once(s)  # state-based actions: the Clone (a 2/2 Solemn) dies; its copied dies trigger (603.10a)
    for _ in range(6):
        d = decision(s)
        if d is not None:
            choose(s, "yes" if any(o.id == "yes" for o in d.options) else d.options[0].id)
        elif on_stack(s):
            pass_once(s)
        else:
            break
    assert s.state.cards[clone.id].zone == "p1:graveyard"
    assert len(zone(s.state, "p1", "hand")) == hand + 1
    replay_matches(s)


def test_clone_uses_the_copied_entry_replacements_and_makes_its_own_choices(cards):
    """707.5: the copied "This creature enters tapped" applies as the Clone enters; 707.6: the
    copied "As this creature enters, choose a color" is the Clone controller's own choice."""
    s = build(cards, "Clone", "Diregraf Ghoul", "Quirion Elves")
    ghoul = on_battlefield(s, "Diregraf Ghoul")
    first = cast_clone(s, pick=ghoul.id)
    pass_until_stack_empty(s)
    assert ch(s, s.state.cards[first.id]).name == "Diregraf Ghoul" and s.state.cards[first.id].tapped
    elves = to_hand(s, "Quirion Elves")
    pay(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=elves.id)
    for _ in range(4):
        if decision(s) is not None:
            break
        pass_once(s)
    choose(s, "Blue")
    pass_until_stack_empty(s)
    act(s, "p1", type="move", card_ids=[first.id], to={"zone": "hand"})
    second = cast_clone(s, name="Clone", pick=elves.id)
    for _ in range(4):
        d = decision(s)
        if d is not None and "choose a color" in d.prompt:
            break
        pass_once(s)
    choose(s, "Red")
    pass_until_stack_empty(s)
    assert s.state.cards[elves.id].choices == {"Chosen color": "Blue"}
    assert s.state.cards[second.id].choices == {"Chosen color": "Red"}
    assert not s.state.cards[second.id].tapped
    replay_matches(s)


def test_clone_declining_enters_as_itself(cards):
    s = build(cards, "Clone", "Grizzly Bears")
    on_battlefield(s, "Grizzly Bears")
    clone = cast_clone(s, pick="none")
    pass_until_stack_empty(s)
    assert s.state.cards[clone.id].zone == "p1:graveyard"  # a 0/0 (704.5f)
    replay_matches(s)


def test_quicksilver_gargantuan_is_7_7_without_the_copied_cda(cards):
    """707.9b / 707.9d: "except it's 7/7" — Crusader of Odric's P/T-defining ability isn't copied."""
    s = build(cards, "Quicksilver Gargantuan", "Crusader of Odric")
    crusader = on_battlefield(s, "Crusader of Odric")
    token(s, "p1", "Bear", "2/2")
    big = cast_clone(s, "Quicksilver Gargantuan", pick=crusader.id, U=2, C=5)
    pass_until_stack_empty(s)
    c = ch(s, s.state.cards[big.id])
    assert c.name == "Crusader of Odric" and c.pt == (7, 7)
    assert ch(s, crusader).pt == (3, 3)  # (three creatures: the Crusader's own ability)
    replay_matches(s)


def test_phantasmal_image_is_an_illusion_that_dies_when_targeted(cards):
    """707.9a-b: the exceptions join the copiable values: an Illusion with the quoted ability."""
    s = build(cards, "Phantasmal Image", "Grizzly Bears", "Lightning Bolt")
    bears = on_battlefield(s, "Grizzly Bears")
    image = cast_clone(s, "Phantasmal Image", pick=bears.id, U=1, C=1)
    pass_until_stack_empty(s)
    c = ch(s, s.state.cards[image.id])
    assert c.name == "Grizzly Bears" and {"Bear", "Illusion"} <= c.subtypes
    assert "Illusion" not in ch(s, bears).subtypes
    bolt = to_hand(s, "Lightning Bolt")
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[image.id])  # it becomes the target: sacrificed
    pass_until_stack_empty(s)
    assert s.state.cards[image.id].zone == "p1:graveyard" and s.state.cards[bolt.id].zone == "p1:graveyard"
    assert s.state.cards[image.id].damage == 0  # (sacrificed before the Bolt resolved: the Bolt did nothing)
    replay_matches(s)


def test_a_clone_put_onto_the_battlefield_by_an_effect_chooses_too(cards):
    """614.12a on every path onto the battlefield: Cloudshift blinks the Clone; it may copy anew."""
    s = build(cards, "Clone", "Grizzly Bears", "Wall of Omens", "Cloudshift")
    bears = on_battlefield(s, "Grizzly Bears")
    wall = on_battlefield(s, "Wall of Omens")
    clone = cast_clone(s, pick=bears.id)
    pass_until_stack_empty(s)
    assert ch(s, s.state.cards[clone.id]).name == "Grizzly Bears"
    shift = to_hand(s, "Cloudshift")
    pay(s, W=1)
    act(s, "p1", type="cast_spell", card_id=shift.id, targets=[clone.id])
    for _ in range(6):
        d = decision(s)
        if d is not None and d.prompt.endswith("to copy"):
            break
        pass_once(s)
    assert {o.id for o in decision(s).options} >= {bears.id, wall.id, "none"}
    choose(s, wall.id)
    pass_until_stack_empty(s)
    c = ch(s, s.state.cards[clone.id])
    assert c.name == "Wall of Omens" and c.pt == (0, 4)
    replay_matches(s)


# -- token copies (707.9 exceptions) ------------------------------------------------------------------------
def test_kiki_jiki_copy_has_haste_and_is_sacrificed_at_the_end_step(cards):
    s = build(cards, "Kiki-Jiki, Mirror Breaker", "Grizzly Bears")
    kiki = on_battlefield(s, "Kiki-Jiki, Mirror Breaker")
    bears = on_battlefield(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    act(s, "p1", type="activate_ability", card_id=kiki.id, ability=1, targets=[bears.id])
    pass_until_stack_empty(s)
    [tok] = [c for c in s.state.cards.values() if c.is_token and c.name == "Grizzly Bears"]
    c = ch(s, tok)
    assert c.name == "Grizzly Bears" and "haste" in c.keywords and c.pt == (2, 2)  # (not the counter: 707.2)
    assert tok.card_id == bears.card_id  # its base is the copied card's printing (111.4 example: its name too)
    assert len(s.state.rules.delayed) == 1  # "Sacrifice it at the beginning of the next end step"
    from tests.test_rules_suspend import until

    until(s, lambda s: tok.id not in s.state.cards, limit=60)
    assert s.state.turn.number <= 2 and not s.state.rules.delayed  # (gone at turn 1's end step)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    replay_matches(s)


def test_a_1_1_red_balloon_copy_with_flying_and_haste(cards):
    """707.9b: "except it's a 1/1 red Balloon creature in addition to its other colors and types and
    it has flying and haste" — P/T set, red and Balloon added (the copied colors and types stay)."""
    s = build(cards, "The Jolly Balloon Man", "Benalish Marshal")
    man = on_battlefield(s, "The Jolly Balloon Man")
    marshal = on_battlefield(s, "Benalish Marshal")
    pay(s, C=1)
    act(s, "p1", type="activate_ability", card_id=man.id, ability=1, targets=[marshal.id])
    pass_until_stack_empty(s)
    [tok] = [c for c in s.state.cards.values() if c.is_token and c.card_id == marshal.card_id]
    c = ch(s, tok)
    assert c.name == "Benalish Marshal" and c.colors == frozenset({"W", "R"})
    assert {"Human", "Knight", "Balloon"} <= c.subtypes and {"flying", "haste"} <= c.keywords
    assert c.pt == (2, 2)  # 1/1, and +1/+1 from the real Marshal …
    assert ch(s, marshal).pt == (4, 4)  # … which gets +1/+1 from the copy's copied ability
    replay_matches(s)


def test_a_token_copy_of_a_clone_copies_what_the_clone_copies(cards):
    """707.3: the Clone's copiable values are the copied creature's: a copy of the Clone is a Wall."""
    s = build(cards, "Clone", "Wall of Omens", "Cackling Counterpart")
    wall = on_battlefield(s, "Wall of Omens")
    clone = cast_clone(s, pick=wall.id)
    pass_until_stack_empty(s)
    counterpart = to_hand(s, "Cackling Counterpart")
    pay(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=counterpart.id, targets=[clone.id])
    pass_until_stack_empty(s)
    [tok] = [c for c in s.state.cards.values() if c.is_token]
    assert ch(s, tok).name == "Wall of Omens" and ch(s, tok).pt == (0, 4)
    assert tok.card_id == wall.card_id
    replay_matches(s)


# -- becoming a copy (707.4) -------------------------------------------------------------------------------
def test_mirage_mirror_becomes_an_anthem_until_end_of_turn(cards):
    """707.4 / 613.2c: the Mirror has the copied static ability while it's a copy; it ends at cleanup."""
    s = build(cards, "Mirage Mirror", "Glorious Anthem")
    mirror = on_battlefield(s, "Mirage Mirror")
    anthem = on_battlefield(s, "Glorious Anthem")
    bear = token(s, "p1", "Bear", "2/2")
    assert ch(s, bear).pt == (3, 3)
    pay(s, C=2)
    act(s, "p1", type="activate_ability", card_id=mirror.id, ability=0, targets=[anthem.id])
    pass_until_stack_empty(s)
    assert ch(s, s.state.cards[mirror.id]).name == "Glorious Anthem" and ch(s, bear).pt == (4, 4)
    from tests.test_rules_suspend import until

    until(s, lambda s: s.state.turn.number == 2, limit=60)
    assert ch(s, s.state.cards[mirror.id]).name == "Mirage Mirror" and ch(s, bear).pt == (3, 3)
    replay_matches(s)


# -- saves, undo and redo with a copy choice pending ------------------------------------------------------
def test_a_pending_copy_choice_survives_save_load_and_undo_redo(cards):
    s = build(cards, "Reverberate", "Lightning Bolt")
    responsive(s)
    hold(s)
    ogre = token(s, "p2", "Ogre", "3/3")
    bolt, rev = to_hand(s, "Lightning Bolt"), to_hand(s, "Reverberate")
    pay(s, R=3)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=rev.id, targets=[bolt.id])
    resolve_top(s)
    assert decision(s).resume["step"] == "copy_target"
    s = GameSession(s.history.rebuild(), cards=s.cards)  # a save and load
    assert decision(s).resume["step"] == "copy_target"
    act(s, "p1", type="create_token", player="p1", token={"name": "Extra", "type_line": "Token Creature — Test"})
    s.undo("p1")
    s.redo("p1")
    s.undo("p1")
    choose(s, ogre.id)
    pass_until_stack_empty(s)
    assert ogre.id not in s.state.cards and life(s, "p2") == 37
    replay_matches(s)


def test_an_older_saved_storm_question_is_answered_through_the_copy_system(cards):
    """A game saved by an older version while storm's "same target / choose" question was open."""
    from app.game.rules_state import Decision, DecisionOption

    s = build(cards, "Grapeshot")
    grapeshot = to_hand(s, "Grapeshot")
    responsive(s)
    hold(s)
    pay(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=grapeshot.id, targets=["p2"])
    ctx = {"controller": "p1", "source_card": "", "source_object": "", "name": "Grapeshot", "targets": [],
           "stack_id": grapeshot.id, "kind": "trigger", "effects": [], "next": 0, "x": None, "event": None}
    s.state.rules.decision = Decision(
        id="old", player="p1", kind="choose_one", prompt="Storm: 2 copies of Grapeshot",
        options=[DecisionOption(id="same", label="Same target for every copy"),
                 DecisionOption(id="choose", label="Choose a target for each copy")],
        resume={"step": "storm", "ctx": {**ctx, "stack_id": "gone"}, "spell": grapeshot.id, "left": 2, "mode": None})
    s.state.rules.priority = None
    act(s, "p1", type="choose", decision_id="old", option_ids=["same"])
    assert len(copies(s)) == 2
    assert all([t.id for t in s.state.rules.stack[c].targets] == ["p2"] for c in copies(s))


# -- state-based actions (704.5d) --------------------------------------------------------------------------
def test_a_token_moved_onto_the_stack_ceases_to_exist(cards):
    s = build(cards)
    bear = token(s, "p1", "Bear", "2/2")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "stack"})  # (by hand: not a copy of a spell)
    act(s, "p1", type="pass_priority")
    assert bear.id not in s.state.cards


# -- grammar and coverage -----------------------------------------------------------------------------------
def characteristics(name, type_line, text, spell=False):
    supertypes, types, subtypes = parse_type_line(type_line)
    return Characteristics(name=name, supertypes=supertypes, types=types, subtypes=subtypes, oracle_text=text,
                           abilities=tuple(parse_abilities(text, spell=spell)))


@pytest.mark.parametrize("name", ["Reverberate", "Fork", "Twincast", "Dualcaster Mage", "Strionic Resonator", "Clone",
                                  "Quicksilver Gargantuan", "Phantasmal Image", "Kiki-Jiki, Mirror Breaker",
                                  "The Jolly Balloon Man", "Cackling Counterpart", "Mirage Mirror", "Lithoform Engine"])
def test_copy_cards_are_fully_automated(name):
    data = next(c for c in EXTRA if c["name"] == name)
    ch_ = characteristics(name, data["type_line"], data["oracle_text"], spell="Instant" in data["type_line"])
    assert coverage.of_characteristics(ch_).level == "FULL"


@pytest.mark.parametrize("text", [
])
def test_unsupported_enter_as_a_copy_wordings_stay_manual(text):
    ch_ = characteristics("Probe", "Creature — Shapeshifter", text)
    assert scripts.definitions(ch_) == {}


@pytest.mark.parametrize("text", [
    "Create a token that's a copy of it.",  # (no antecedent)
    "Create a token that's a copy of target creature, except it's a 1/1 green Forest.",  # (not a creature type; the Frog form: wave 5J)
    "Copy target instant or sorcery spell for each creature you control.",  # (707.10d-like: not read)
    "Copy target activated ability you control, except it has flying.",
])
def test_unsupported_copy_wordings_stay_manual(text):
    assert scripts.parse_effects(text) is None


def test_copy_grammar():
    assert scripts.parse_effects("Copy target instant or sorcery spell, except that the copy is red. You may choose new "
                                 "targets for the copy.")[0] == [
        {"do": "copy_spell", "who": "target", "excepts": [{"set_colors": ["R"]}]},
        {"do": "copy_new_targets", "optional": True}]
    effects, target, _ = scripts.parse_effects("Create two tokens that are copies of target creature you control, except "
                                               "they're 1/1 and they have haste.")
    assert effects == [{"do": "token_copy", "n": 2, "who": "target",
                        "excepts": [{"power": "1", "toughness": "1", "add_text": ["Haste"]}]}]
    assert scripts.parse_effects("~ becomes a copy of target creature until end of turn.")[0] == [
        {"do": "become_copy", "who": "self", "with": "target", "duration": "end_of_turn"}]


def test_a_different_copy_choice_after_undo_is_not_served_from_the_static_cache(cards):
    """Review (Codex, PR #9): after an undo, a new copy choice can reuse the same object id and
    timestamp; the static-ability cache must key on the copied values, not just the timestamp."""
    s = build(cards, "Mirage Mirror", "Glorious Anthem")
    mirror = on_battlefield(s, "Mirage Mirror")
    anthem = on_battlefield(s, "Glorious Anthem")
    bear = token(s, "p1", "Bear", "2/2")
    act(s, "p1", type="move", card_ids=[anthem.id], to={"zone": "graveyard"})
    anthem2 = on_battlefield(s, "Glorious Anthem")
    pay(s, C=2)
    act(s, "p1", type="activate_ability", card_id=mirror.id, ability=0, targets=[anthem2.id])
    pass_until_stack_empty(s)
    assert ch(s, bear).pt == (4, 4)  # two anthems: the real one and the Mirror as a copy
    while s.state.cards[mirror.id].zone.endswith("battlefield") and ch(s, s.state.cards[mirror.id]).name != "Mirage Mirror":
        s.undo("p1")
    pay(s, C=2)
    act(s, "p1", type="activate_ability", card_id=mirror.id, ability=0, targets=[bear.id])
    pass_until_stack_empty(s)
    assert ch(s, s.state.cards[mirror.id]).name == "Bear" and ch(s, bear).pt == (3, 3)  # only the real anthem
    replay_matches(s)
