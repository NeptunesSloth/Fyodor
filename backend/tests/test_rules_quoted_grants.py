"""Temporary quoted grants (wave 2D: app/rules/granted.py), researched against CR 2026-09-25.

"Until end of turn, target creature gets +2/+0 and gains "When this creature dies, return it to the
battlefield tapped under its owner's control."" (Supernatural Stamina), "Until end of turn, creatures
you control gain "{T}: This creature deals 1 damage to any target."" (Lightning Volley), "… becomes a
3/3 … creature with "Whenever this creature attacks, put a +1/+1 counter on it." It's still a land."
(Raging Ravine): a resolving spell or ability gives objects an ability, for the duration it states
(611.2a) — keywords and quoted abilities in one layer-6 effect (613.1f, 613.7b), to the objects it
names as it begins (611.2c; 109.3: abilities are characteristics), which keep it through a change of
control and lose it as a new object (400.7). An ability that triggers as its object leaves looks back
at the abilities it had (603.10a). Every card below is real Commander-legal Oracle text, transcribed
from the card database into the fixture set (named in a comment); every scenario checks that replay
reproduces the table.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import oracle, scripts
from app.rules.characteristics import Characteristics, parse_type_line
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, turn_on
from tests.test_rules_attachments import build, ch, named, token
from tests.test_rules_delayed import next_end_step, on_battlefield, reloaded
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def real(name: str, type_line: str, text: str, cost: str = "", pt: tuple[str, str] | None = None,
         colors: tuple[str, ...] = (), number: str = "Q1") -> dict:
    """A card of this module's fixture set: the real Oracle text of the Commander-legal card."""
    cmc = float(sum(int(s) if s.isdigit() else 1 for s in __import__("re").findall(r"\{([^}]+)\}", cost) if s != "X"))
    return card(name, set_code="tst", number=number, mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **({"power": pt[0], "toughness": pt[1]} if pt else {}))


EXTRA = [
    real("Lightning Volley", "Instant", 'Until end of turn, creatures you control gain "{T}: This creature deals 1 damage to any target."',
         "{3}{R}", colors=("R",), number="Q1"),
    real("Supernatural Stamina", "Instant",
         'Until end of turn, target creature gets +2/+0 and gains "When this creature dies, return it to the battlefield tapped under its owner\'s control."',
         "{B}", colors=("B",), number="Q2"),
    real("Run Wild", "Instant", 'Until end of turn, target creature gains trample and "{G}: Regenerate this creature."', "{G}",
         colors=("G",), number="Q3"),
    real("Divergent Growth", "Instant", 'Until end of turn, lands you control gain "{T}: Add one mana of any color."', "{G}",
         colors=("G",), number="Q4"),
    real("Can't Stay Away", "Sorcery",
         'Return target creature card with mana value 3 or less from your graveyard to the battlefield. It gains "If this creature would die, exile it instead."\n'
         "Flashback {3}{W}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
         "{W}{B}", colors=("W", "B"), number="Q5"),
    real("Hellish Rebuke", "Instant",
         'Until end of turn, permanents your opponents control gain "When this permanent deals damage to the player who cast Hellish Rebuke, sacrifice this permanent. You lose 2 life."',
         "{2}{B}", colors=("B",), number="Q6"),
    real("Hunter's Prowess", "Sorcery",
         'Until end of turn, target creature gets +3/+3 and gains trample and "Whenever this creature deals combat damage to a player, draw that many cards."',
         "{4}{G}", colors=("G",), number="Q7"),
    real("Armor of Shadows", "Instant",
         'Until end of turn, target creature gets +1/+0 and gains indestructible. (Damage and effects that say "destroy" don\'t destroy it.)',
         "{B}", colors=("B",), number="Q8"),
    real("Quicksmith Spy", "Creature — Human Artificer",
         'When this creature enters, target artifact you control gains "{T}: Draw a card" for as long as you control this creature.',
         "{3}{U}", pt=("2", "3"), colors=("U",), number="Q9"),
    real("Raging Ravine", "Land",
         "This land enters tapped.\n{T}: Add {R} or {G}.\n{2}{R}{G}: Until end of turn, this land becomes a 3/3 red and green Elemental creature "
         'with "Whenever this creature attacks, put a +1/+1 counter on it." It\'s still a land.', colors=("R", "G"), number="Q10"),
    real("Restless Spire", "Land",
         "This land enters tapped.\n{T}: Add {U} or {R}.\n{U}{R}: Until end of turn, this land becomes a 2/1 blue and red Elemental creature "
         'with "During your turn, this creature has first strike." It\'s still a land.\nWhenever this land attacks, scry 1.',
         colors=("U", "R"), number="Q11"),
    real("Lavaclaw Reaches", "Land",
         "This land enters tapped.\n{T}: Add {B} or {R}.\n{1}{B}{R}: Until end of turn, this land becomes a 2/2 black and red Elemental creature "
         'with "{X}: This creature gets +X/+0 until end of turn." It\'s still a land.', colors=("B", "R"), number="Q12"),
    real("Titanic Ultimatum", "Sorcery", "Until end of turn, creatures you control get +5/+5 and gain first strike, trample, and lifelink.",
         "{R}{R}{G}{G}{G}{W}{W}", colors=("R", "G", "W"), number="Q13"),
    real("Touch of Vitae", "Instant",
         'Until end of turn, target creature gains haste and "{0}: Untap this creature. Activate only once."\nDraw a card at the beginning of the next turn\'s upkeep.',
         "{2}{G}", colors=("G",), number="Q14"),
    real("Shackles of Treachery", "Sorcery",
         'Gain control of target creature until end of turn. Untap that creature. Until end of turn, it gains haste and "Whenever this creature deals damage, destroy target Equipment attached to it."',
         "{2}{R}", colors=("R",), number="Q15"),
    real("Spawning Pool", "Land",
         'This land enters tapped.\n{T}: Add {B}.\n{1}{B}: This land becomes a 1/1 black Skeleton creature with "{B}: Regenerate this creature" until end of turn. It\'s still a land.',
         colors=("B",), number="Q16"),
]


@pytest.fixture()
def cards(settings, card_db) -> Iterator[CardRepository]:
    """The fixture card set plus this module's real cards."""
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def rules(s):
    return s.state.rules


def definition(name: str, type_line: str, text: str) -> dict | None:
    """What the engine reads of a card's (only) ability line, or of the whole spell."""
    sup, types, sub = parse_type_line(type_line)
    c = Characteristics(name=name, supertypes=sup, types=types, subtypes=sub, oracle_text=text,
                        abilities=tuple(oracle.parse_abilities(text, spell=bool(types & {"Instant", "Sorcery"}))))
    if c.is_instant_or_sorcery:
        return scripts.spell_definition(c)
    defs = scripts.definitions(c)
    return next(iter(defs.values()), None) if len(defs) == 1 else defs or None


def cast(s, name, targets=(), pid="p1", **m):
    """Cast a card from the hand of ``pid`` (mana added first)."""
    card_ = named(s, name)
    if card_.zone != f"{pid}:hand":
        act(s, pid, type="move", card_ids=[card_.id], to={"zone": "hand"})
    act(s, pid, type="add_mana", player=pid, mana=m)
    act(s, pid, type="cast_spell", card_id=card_.id, targets=list(targets))
    return card_


def grants(s, c):
    """The abilities a permanent has beyond its printed ones (the layer-6 grants)."""
    return [a for a in ch(s, c).abilities if a.index >= 100]


def old_table(cards, *names):
    """A sandbox table whose creatures are set up by hand (``creature``), then automation on
    (``start``): what is there before is not summoning sick (302.6)."""
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    return GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)


def creature(s, pid, name, pt="2/2", text=""):
    return token(s, pid, name, pt, text)


def start(s):
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main phase


# -- the wording ------------------------------------------------------------------------------------
def test_wordings_of_real_cards():
    stamina = definition("Supernatural Stamina", "Instant", EXTRA[1]["oracle_text"])
    assert stamina is not None and [e["do"] for e in stamina["effects"]] == ["pump", "grant"]
    grant = stamina["effects"][1]
    assert grant["who"] == "target" and grant["keywords"] == []
    assert grant["abilities"] == ["When this permanent dies, return it to the battlefield tapped under its owner's control."]
    volley = definition("Lightning Volley", "Instant", EXTRA[0]["oracle_text"])
    assert volley is not None and volley["effects"][0]["abilities"] == ["{T}: This permanent deals 1 damage to any target."]
    wild = definition("Run Wild", "Instant", EXTRA[2]["oracle_text"])
    assert wild is not None and wild["effects"][0]["keywords"] == ["trample"]  # keywords and the quote: one grant
    assert wild["effects"][0]["abilities"] == ["{G}: Regenerate this permanent."]


# -- 603.10a: a granted "When this creature dies" looks back at the abilities it had --------------------
def test_granted_dies_trigger_fires_from_last_known_information(cards):
    """Supernatural Stamina: the creature is destroyed, and the ability it had just before (granted
    until end of turn) returns it — the verified gap this module closes (the trigger collector read
    printed text only)."""
    s = build(cards, "Supernatural Stamina", "Murder", "Grizzly Bears")
    bears = on_battlefield(s, "Grizzly Bears")
    cast(s, "Supernatural Stamina", [bears.id], B=1)
    pass_until_stack_empty(s)
    assert ch(s, bears).pt == (4, 2)
    (granted,) = grants(s, bears)
    assert granted.kind == "triggered" and granted.text.startswith("When this permanent dies")
    old = rules(s).object_id(bears.id)
    cast(s, "Murder", [bears.id], B=3)
    pass_until_stack_empty(s)
    now = s.state.cards[bears.id]
    assert now.zone == "p1:battlefield" and now.tapped  # returned tapped under its owner's control
    assert rules(s).object_id(bears.id) != old and ch(s, bears).pt == (2, 2) and grants(s, bears) == []  # 400.7: a new object
    replay_matches(s)


# -- Lightning Volley: the set is locked (611.2c), a {T} ability obeys 302.6, the index is stable ---------
def test_lightning_volley_grants_an_activated_ability_to_the_creatures_there_now(cards):
    s = old_table(cards, "Lightning Volley")
    bear = creature(s, "p1", "Old Bear")
    wolf = creature(s, "p2", "Their Wolf")
    start(s)
    fresh = creature(s, "p1", "Fresh Cub")  # arrived this turn: summoning sick
    cast(s, "Lightning Volley", R=4)
    pass_until_stack_empty(s)
    (g,) = grants(s, bear)
    assert g.kind == "activated" and g.index >= 10_000 and grants(s, wolf) == []  # "creatures you control"
    late = creature(s, "p1", "Late Pup")
    assert grants(s, late) == [] and len(grants(s, fresh)) == 1  # 611.2c: the set was fixed as it began
    # 302.6: a {T} ability of a creature that hasn't been under its controller's control since the turn began
    with pytest.raises(ActionError, match="summoning sickness"):
        act(s, "p1", type="activate_ability", card_id=fresh.id, ability=grants(s, fresh)[0].index, targets=["p2"])
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=g.index, targets=["p2"])
    assert s.state.cards[bear.id].tapped  # the cost is paid as it's activated
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 39
    with pytest.raises(ActionError):  # tapped
        act(s, "p1", type="activate_ability", card_id=bear.id, ability=g.index, targets=["p2"])
    replay_matches(s)
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")  # save / load


def test_the_ability_number_survives_another_grant_ending(cards):
    """113.10c: each grant is its own ability; a number that shifted when an earlier grant ended would
    point a click (or a save) at the wrong one."""
    s = old_table(cards, "Lightning Volley", "Run Wild")
    bear = creature(s, "p1", "Old Bear")
    start(s)
    cast(s, "Run Wild", [bear.id], G=1)
    pass_until_stack_empty(s)
    (regen,) = grants(s, bear)
    cast(s, "Lightning Volley", R=4)
    pass_until_stack_empty(s)
    both = grants(s, bear)
    assert [a.text for a in both] == ["{G}: Regenerate this permanent.", "{T}: This permanent deals 1 damage to any target."]
    assert both[0].index == regen.index and both[1].index > both[0].index
    volley_index = both[1].index
    # the earlier grant ends (its effect is removed): the later one keeps its number
    rules(s).effects = [e for e in rules(s).effects if not e.add_keywords]
    (left,) = grants(s, bear)
    assert left.index == volley_index and left.text.startswith("{T}")
    act(s, "p1", type="activate_ability", card_id=bear.id, ability=volley_index, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 39
    replay_matches(s)


def test_grants_end_at_cleanup_and_the_marker_with_them(cards):
    s = old_table(cards, "Lightning Volley")
    bear = creature(s, "p1", "Old Bear")
    start(s)
    cast(s, "Lightning Volley", R=4)
    pass_until_stack_empty(s)
    assert any(m.value == "Ability" for m in s.state.cards[bear.id].effects)  # the visible marker
    next_end_step(s)
    assert grants(s, bear) == [] and rules(s).effects == []  # 514.2
    assert not any(m.value == "Ability" for m in s.state.cards[bear.id].effects)
    replay_matches(s)


def test_a_granted_ability_stays_through_a_change_of_control_and_not_a_zone_change(cards):
    s = old_table(cards, "Lightning Volley", "Grizzly Bears")
    bears = on_battlefield(s, "Grizzly Bears")
    start(s)
    cast(s, "Lightning Volley", R=4)
    pass_until_stack_empty(s)
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p2")  # the same object (400.7 doesn't apply)
    assert len(grants(s, bears)) == 1  # 611.2c: the effect's set of objects doesn't change with control
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p1")
    assert len(grants(s, bears)) == 1
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "battlefield"})
    assert grants(s, bears) == []  # 400.7: a new object has none of it
    replay_matches(s)
