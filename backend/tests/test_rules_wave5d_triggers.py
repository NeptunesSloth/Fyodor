"""Wave 5D: triggered abilities — trigger multipliers (603.2d), death and draw triggers. Researched against CR
2026-09-25 and the Wizards rulings of the cards named.

* 603.2d: "that ability triggers an additional time" — each multiplier adds one instance; each instance is a separate
  triggered ability with its own targets (rulings). Which multipliers count: those there right after the event, or
  right before it for an ability that looks back in time (603.10, 603.10a: Teysa dying with the creatures).

Every scenario uses real Oracle text and checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, trigger_multipliers
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, life, settle, to_hand
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card('Panharmonicon', set_code='tst', number='T5D1', mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='If an artifact or creature entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.'),
    card('Teysa Karlov', set_code='tst', number='T5D2', mana_cost='{2}{W}{B}', cmc=4.0, type_line='Legendary Creature — Human Advisor', oracle_text='If a creature dying causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.\nCreature tokens you control have vigilance and lifelink.', power='2', toughness='4', colors=['B', 'W'], color_identity=['B', 'W']),
    card('Harmonic Prodigy', set_code='tst', number='T5D3', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Wizard', oracle_text='Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nIf a triggered ability of a Shaman or another Wizard you control triggers, that ability triggers an additional time.', power='1', toughness='3', colors=['R'], color_identity=['R'], keywords=['Prowess']),
    card('Veyran, Voice of Duality', set_code='tst', number='T5D4', mana_cost='{1}{U}{R}', cmc=3.0, type_line='Legendary Creature — Efreet Wizard', oracle_text='Magecraft — Whenever you cast or copy an instant or sorcery spell, Veyran gets +1/+1 until end of turn.\nIf you casting or copying an instant or sorcery spell causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.', power='2', toughness='2', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Magecraft']),
    card('Delney, Streetwise Lookout', set_code='tst', number='T5D5', mana_cost='{2}{W}', cmc=3.0, type_line='Legendary Creature — Human Scout', oracle_text="Creatures you control with power 2 or less can't be blocked by creatures with power 3 or greater.\nIf a triggered ability of a creature you control with power 2 or less triggers, that ability triggers an additional time.", power='2', toughness='2', colors=['W'], color_identity=['W']),
    card('Ancient Greenwarden', set_code='tst', number='T5D6', mana_cost='{4}{G}{G}', cmc=6.0, type_line='Creature — Elemental', oracle_text='Reach (This creature can block creatures with flying.)\nYou may play lands from your graveyard.\nIf a land entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.', power='5', toughness='7', colors=['G'], color_identity=['G'], keywords=['Reach']),
    card('Yarok, the Desecrated', set_code='tst', number='T5D7', mana_cost='{2}{B}{G}{U}', cmc=5.0, type_line='Legendary Creature — Elemental Horror', oracle_text='Deathtouch, lifelink\nIf a permanent entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.', power='3', toughness='5', colors=['B', 'G', 'U'], color_identity=['B', 'G', 'U'], keywords=['Lifelink', 'Deathtouch']),
    card('Krang, the All-Powerful', set_code='tst', number='T5D8', mana_cost='{4}{U}', cmc=5.0, type_line='Legendary Artifact Creature — Utrom Robot', oracle_text='If a player drawing a card causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.\nWhenever a player draws their second card each turn, put a +1/+1 counter on Krang.', power='3', toughness='3', colors=['U'], color_identity=['U']),
    card('Isshin, Two Heavens as One', set_code='tst', number='T5D9', mana_cost='{R}{W}{B}', cmc=3.0, type_line='Legendary Creature — Human Samurai', oracle_text='If a creature attacking causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.', power='3', toughness='4', colors=['B', 'R', 'W'], color_identity=['B', 'R', 'W']),
    card('Echoes of Eternity', set_code='tst', number='T5D10', mana_cost='{3}{C}{C}{C}', cmc=6.0, type_line='Kindred Enchantment — Eldrazi', oracle_text='If a triggered ability of a colorless spell you control or another colorless permanent you control triggers, that ability triggers an additional time.\nWhenever you cast a colorless spell, copy it. You may choose new targets for the copy. (A copy of a permanent spell becomes a token.)'),
    card('Sanctum of All', set_code='tst', number='T5D11', mana_cost='{W}{U}{B}{R}{G}', cmc=5.0, type_line='Legendary Enchantment — Shrine', oracle_text='At the beginning of your upkeep, you may search your library and/or graveyard for a Shrine card and put it onto the battlefield. If you search your library this way, shuffle.\nIf a triggered ability of another Shrine you control triggers while you control six or more Shrines, that ability triggers an additional time.', colors=['B', 'G', 'R', 'U', 'W'], color_identity=['B', 'G', 'R', 'U', 'W']),
    card('Flametongue Kavu', set_code='tst', number='T5D13', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Kavu', oracle_text='When this creature enters, it deals 4 damage to target creature.', power='4', toughness='2', colors=['R'], color_identity=['R']),
    card('Evolution Sage', set_code='tst', number='T5D14', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Elf Druid', oracle_text='Landfall — Whenever a land you control enters, proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)', power='3', toughness='2', colors=['G'], color_identity=['G'], keywords=['Proliferate', 'Landfall']),
    card('Annie Joins Up', set_code='tst', number='T5D15', mana_cost='{1}{R}{G}{W}', cmc=4.0, type_line='Legendary Enchantment', oracle_text='When Annie Joins Up enters, it deals 5 damage to target creature or planeswalker an opponent controls.\nIf a triggered ability of a legendary creature you control triggers, that ability triggers an additional time.', colors=['G', 'R', 'W'], color_identity=['G', 'R', 'W']),
    card('Naban, Dean of Iteration', set_code='tst', number='T5D16', mana_cost='{1}{U}', cmc=2.0, type_line='Legendary Creature — Human Wizard', oracle_text='If a Wizard you control entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.', power='2', toughness='1', colors=['U'], color_identity=['U']),
    # -- draw and death triggers --
    card('Sheoldred, the Apocalypse', set_code='tst', number='T5D20', mana_cost='{2}{B}{B}', cmc=4.0, type_line='Legendary Creature — Phyrexian Praetor', oracle_text='Deathtouch\nWhenever you draw a card, you gain 2 life.\nWhenever an opponent draws a card, they lose 2 life.', power='4', toughness='5', colors=['B'], color_identity=['B'], keywords=['Deathtouch']),
    card('Massacre Wurm', set_code='tst', number='T5D21', mana_cost='{3}{B}{B}{B}', cmc=6.0, type_line='Creature — Phyrexian Wurm', oracle_text='When this creature enters, creatures your opponents control get -2/-2 until end of turn.\nWhenever a creature an opponent controls dies, that player loses 2 life.', power='6', toughness='5', colors=['B'], color_identity=['B']),
    card('Howling Mine', set_code='tst', number='T5D22', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text="At the beginning of each player's draw step, if this artifact is untapped, that player draws an additional card."),
    card('Loran of the Third Path', set_code='tst', number='T5D23', mana_cost='{2}{W}', cmc=3.0, type_line='Legendary Creature — Human Artificer', oracle_text='Vigilance\nWhen Loran enters, destroy up to one target artifact or enchantment.\n{T}: You and target opponent each draw a card.', power='2', toughness='1', colors=['W'], color_identity=['W'], keywords=['Vigilance']),
    card('Secret Rendezvous', set_code='tst', number='T5D24', mana_cost='{1}{W}{W}', cmc=3.0, type_line='Sorcery', oracle_text='You and target opponent each draw three cards.', colors=['W'], color_identity=['W']),
    card('Goldvein Hydra', set_code='tst', number='T5D25', mana_cost='{X}{G}', cmc=1.0, type_line='Creature — Hydra', oracle_text='Vigilance, trample, haste\nThis creature enters with X +1/+1 counters on it.\nWhen this creature dies, create a number of tapped Treasure tokens equal to its power.', power='0', toughness='0', colors=['G'], color_identity=['G'], keywords=['Vigilance', 'Treasure', 'Haste', 'Trample']),
    card('Lifeblood Hydra', set_code='tst', number='T5D26', mana_cost='{X}{G}{G}{G}', cmc=3.0, type_line='Creature — Hydra', oracle_text='Trample\nThis creature enters with X +1/+1 counters on it.\nWhen this creature dies, you gain life and draw cards equal to its power.', power='0', toughness='0', colors=['G'], color_identity=['G'], keywords=['Trample']),
    card('Murderous Rider // Swift End', set_code='tst', number='T5D27', layout='adventure', mana_cost='{1}{B}{B} // {1}{B}{B}', cmc=3.0, type_line='Creature — Zombie Knight // Instant — Adventure', colors=['B'], color_identity=['B'], keywords=['Lifelink'],
         card_faces=[
             {"object": "card_face", "name": "Murderous Rider", "mana_cost": "{1}{B}{B}", "type_line": "Creature — Zombie Knight", "oracle_text": "Lifelink\nWhen this creature dies, put it on the bottom of its owner's library.", "power": "2", "toughness": "3"},
             {"object": "card_face", "name": "Swift End", "mana_cost": "{1}{B}{B}", "type_line": "Instant — Adventure", "oracle_text": "Destroy target creature or planeswalker. You lose 2 life. (Then exile this card. You may cast the creature later from exile.)"},
         ]),
    card('Ichor Wellspring', set_code='tst', number='T5D28', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='When this artifact enters or is put into a graveyard from the battlefield, draw a card.'),
    card('Wurmcoil Engine', set_code='tst', number='T5D29', mana_cost='{6}', cmc=6.0, type_line='Artifact Creature — Phyrexian Wurm', oracle_text='Deathtouch, lifelink\nWhen this creature dies, create a 3/3 colorless Phyrexian Wurm artifact creature token with deathtouch and a 3/3 colorless Phyrexian Wurm artifact creature token with lifelink.', power='6', toughness='6', keywords=['Lifelink', 'Deathtouch']),
    card('Brainstorm', set_code='tst', number='T5D30', mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='Draw three cards, then put two cards from your hand on top of your library in any order.', colors=['U'], color_identity=['U']),
    card('Kederekt Parasite', set_code='tst', number='T5D31', mana_cost='{B}', cmc=1.0, type_line='Creature — Horror', oracle_text='Whenever an opponent draws a card, if you control a red permanent, you may have this creature deal 1 damage to that player.', power='1', toughness='1', colors=['B'], color_identity=['B']),
    card('Disciple of the Vault', set_code='tst', number='T5D32', mana_cost='{B}', cmc=1.0, type_line='Creature — Human Cleric', oracle_text='Whenever an artifact is put into a graveyard from the battlefield, you may have target opponent lose 1 life.', power='1', toughness='1', colors=['B'], color_identity=['B']),
    card('Suture Priest', set_code='tst', number='T5D33', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Phyrexian Cleric', oracle_text='Whenever another creature you control enters, you may gain 1 life.\nWhenever a creature an opponent controls enters, you may have that player lose 1 life.', power='1', toughness='1', colors=['W'], color_identity=['W']),
    card('Conch Horn', set_code='tst', number='T5D34', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='{1}, {T}, Sacrifice this artifact: Draw two cards, then put a card from your hand on top of your library.'),
    card('Fecundity', set_code='tst', number='T5D36', mana_cost='{2}{G}', cmc=3.0, type_line='Enchantment', oracle_text="Whenever a creature dies, that creature's controller may draw a card.", colors=['G'], color_identity=['G']),
    card('Dark Revenant', set_code='tst', number='T5D43', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Spirit', oracle_text="Flying\nWhen this creature dies, put it on top of its owner's library.", power='2', toughness='2', colors=['B'], color_identity=['B'], keywords=['Flying']),
    card('Orcish Bowmasters', set_code='tst', number='T5D44', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Orc Archer', oracle_text='Flash\nWhen this creature enters and whenever an opponent draws a card except the first one they draw in each of their draw steps, this creature deals 1 damage to any target. Then amass Orcs 1.', power='1', toughness='1', colors=['B'], color_identity=['B'], keywords=['Amass', 'Flash']),
    card('Mirkwood Bats', set_code='tst', number='T5D45', mana_cost='{3}{B}', cmc=4.0, type_line='Creature — Bat', oracle_text='Flying\nWhenever you create or sacrifice a token, each opponent loses 1 life.', power='2', toughness='3', colors=['B'], color_identity=['B'], keywords=['Flying']),
    card('Shatter', set_code='tst', number='T5D40', mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text='Destroy target artifact.', colors=['R'], color_identity=['R']),
    card('Triplicate Titan', set_code='tst', number='T5D42', mana_cost='{9}', cmc=9.0, type_line='Artifact Creature — Golem', oracle_text='Flying, vigilance, trample\nWhen this creature dies, create a 3/3 colorless Golem artifact creature token with flying, a 3/3 colorless Golem artifact creature token with vigilance, and a 3/3 colorless Golem artifact creature token with trample.', power='9', toughness='9', keywords=['Flying', 'Vigilance', 'Trample']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- helpers ---------------------------------------------------------------------------------------------------
def saved(s):
    """The table saved and loaded again (a restart): play goes on from the loaded one."""
    return GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def stack_names(s):
    return [s.state.cards[c].name if c in s.state.cards else c for c in s.state.zones.get("stack", [])]


def cov(name):
    c = next(x for x in EXTRA if x["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


def pt(s, c):
    from app.rules.plan import Plan

    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id]).pt


def confirm_triggers(s):
    """Triggers wait for the table's OK (AUTO TRIGGER STACKING off): the waiting triggers' names can be read."""
    act(s, "p1", type="configure", automation_options={"auto_trigger_stacking": False})


def triggered(s):
    """Play on to the "Triggered: …" confirmation; the names of the triggered abilities (one per instance), then put
    them on the stack."""
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "confirm" and d.prompt.startswith("Triggered: "):
            names = d.prompt[len("Triggered: "):].split(", ")
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
            return names
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("nothing triggered")


# -- the wording -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "level"), [
    ("Teysa Karlov", "FULL"), ("Harmonic Prodigy", "FULL"), ("Veyran, Voice of Duality", "FULL"),
    ("Delney, Streetwise Lookout", "FULL"),
    ("Krang, the All-Powerful", "FULL"), ("Annie Joins Up", "FULL"),
    # -- review (wave 43A) -- an entering cause is read again (trigger_multipliers.py), and so are an attack's cause, a colorless spell's abilities and a
    # condition on the multiplier (tests/test_rules_wave43a_trigger_multipliers.py)
    ("Panharmonicon", "FULL"), ("Ancient Greenwarden", "FULL"), ("Yarok, the Desecrated", "FULL"),
    ("Naban, Dean of Iteration", "FULL"),
    ("Isshin, Two Heavens as One", "FULL"), ("Echoes of Eternity", "FULL"), ("Sanctum of All", "FULL"),
])
def test_multiplier_coverage(name, level):
    assert cov(name) == level


def test_multiplier_wordings():
    d = trigger_multipliers.static_definition
    assert d("If a creature dying causes a triggered ability of a permanent you control to trigger, that ability "
             "triggers an additional time.")["cause"] == "die"
    assert d("If a triggered ability of a Shaman or another Wizard you control triggers, that ability triggers an "
             "additional time.")["source"] == ['sel:{"controller":"you","subtypes":["Shaman"]}',
                                               'sel:{"controller":"you","other":true,"subtypes":["Wizard"]}']
    assert d("If a creature attacking causes a triggered ability of a permanent you control to trigger, that ability "
             "triggers an additional time.")["cause"] == "attack"
    # (still unread, so the card stays manual: a creature being dealt damage, a permanent turned face up, a creature that isn't "a creature you control")
    assert d("If a creature you control being dealt damage causes a triggered ability of a permanent you control to trigger, that ability triggers an "
             "additional time.") is None
    assert d("If turning a face-down permanent face up causes a triggered ability of a permanent you control to trigger, that ability triggers an "
             "additional time.") is None
    assert d("If a Goblin attacking causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.") is None


# -- entering (Panharmonicon, Yarok, Greenwarden, Naban) -----------------------------------------------------------
def test_panharmonicon_doubles_enters_triggers(cards):
    """Its own enters ability and Soul Warden's "another creature enters" each trigger twice (rulings)."""
    s = build(cards, "Panharmonicon", "Elvish Visionary", "Soul Warden")
    put(s, "Panharmonicon")
    put(s, "Soul Warden")
    visionary = to_hand(s, "Elvish Visionary")
    s = saved(s)
    before, gained = hand_size(s), life(s)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=visionary.id)
    settle(s)
    assert hand_size(s) == before - 1 + 2
    assert life(s) == gained + 2
    replay_matches(s)


def test_two_panharmonicons_three_times_and_not_for_an_opponent(cards):
    """Two multipliers: three times, not four (rulings). An opponent's Panharmonicon doesn't count for your
    abilities (603.2d: "a permanent you control")."""
    s = build(cards, "Panharmonicon", "Panharmonicon", "Grizzly Bears", "Soul Warden", p2=("Panharmonicon",))
    for c in [c for c in s.state.cards.values() if c.name == "Panharmonicon"]:
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "battlefield"})
    put(s, "Soul Warden")
    bears = to_hand(s, "Grizzly Bears")
    gained = life(s)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert life(s) == gained + 3
    replay_matches(s)


def test_each_instance_has_its_own_target(cards):
    """Rulings: the instances are separate abilities — each target is chosen as it's put on the stack (603.3d)."""
    s = build(cards, "Panharmonicon", "Flametongue Kavu", p2=("Grizzly Bears", "Soul Warden"))
    put(s, "Panharmonicon")
    bears, warden = put(s, "Grizzly Bears", "p2"), put(s, "Soul Warden", "p2")
    kavu = to_hand(s, "Flametongue Kavu")
    mana(s, R=1, G=3)
    act(s, "p1", type="cast_spell", card_id=kavu.id)
    chosen = []
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        if d.prompt.endswith("choose a target"):
            pick = next(o.id for o in d.options if o.id == (bears.id if not chosen else warden.id))
            chosen.append(pick)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert chosen == [bears.id, warden.id]
    s = saved(s)
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[warden.id].zone == "p2:graveyard"
    replay_matches(s)


def test_greenwarden_lands_and_panharmonicon_not(cards):
    """A land entering: Ancient Greenwarden adds an instance of a landfall ability; Panharmonicon doesn't (not an
    artifact or creature)."""
    for multiplier, expected in (("Ancient Greenwarden", 2), ("Panharmonicon", 1), ("Yarok, the Desecrated", 2)):
        s = build(cards, multiplier, "Evolution Sage")
        put(s, multiplier)
        put(s, "Evolution Sage")
        confirm_triggers(s)
        forest = to_hand(s, "Forest")
        act(s, "p1", type="play_land", card_id=forest.id)
        assert triggered(s) == ["Evolution Sage"] * expected, multiplier
        settle(s)
        replay_matches(s)


# -- dying (Teysa) ----------------------------------------------------------------------------------------------------
def test_teysa_doubles_dies_triggers_and_looks_back(cards):
    """A creature dying: its own "when this creature dies" ability triggers twice — also when Teysa dies at the same
    time (rulings: 603.10a looks back in time)."""
    s = build(cards, "Teysa Karlov", "Perilous Myr", "Wrath of God")
    put(s, "Teysa Karlov")
    put(s, "Perilous Myr")
    wrath = to_hand(s, "Wrath of God")
    s = saved(s)
    confirm_triggers(s)
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    assert triggered(s) == ["Perilous Myr"] * 2
    settle(s)
    replay_matches(s)


def test_teysa_not_for_a_creature_entering(cards):
    s = build(cards, "Teysa Karlov", "Elvish Visionary")
    put(s, "Teysa Karlov")
    visionary = to_hand(s, "Elvish Visionary")
    before = hand_size(s)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=visionary.id)
    settle(s)
    assert hand_size(s) == before - 1 + 1
    replay_matches(s)


# -- by source (Delney, Harmonic Prodigy, Annie) and by casting (Veyran) -----------------------------------------------
def test_delney_power_two_or_less(cards):
    s = build(cards, "Delney, Streetwise Lookout", "Elvish Visionary", "Flametongue Kavu", p2=("Grizzly Bears",))
    put(s, "Delney, Streetwise Lookout")
    put(s, "Grizzly Bears", "p2")
    visionary, kavu = to_hand(s, "Elvish Visionary"), to_hand(s, "Flametongue Kavu")
    before = hand_size(s)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=visionary.id)
    settle(s)
    assert hand_size(s) == before - 1 + 2  # (a 1/1: twice)
    confirm_triggers(s)
    mana(s, R=1, G=3)
    act(s, "p1", type="cast_spell", card_id=kavu.id)
    assert triggered(s) == ["Flametongue Kavu"]  # (a 4/2: once)
    settle(s)
    replay_matches(s)


def test_veyran_and_harmonic_prodigy(cards):
    """Casting an instant: Veyran's magecraft triggers three times (itself, and Harmonic Prodigy for another Wizard);
    Harmonic Prodigy's prowess twice (Veyran; Prodigy doesn't count itself: "another Wizard")."""
    s = build(cards, "Veyran, Voice of Duality", "Harmonic Prodigy", "Lightning Bolt", p2=("Grizzly Bears",))
    veyran = put(s, "Veyran, Voice of Duality")
    prodigy = put(s, "Harmonic Prodigy")
    bears = put(s, "Grizzly Bears", "p2")
    bolt = to_hand(s, "Lightning Bolt")
    s = saved(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bears.id])
    settle(s)
    assert pt(s, veyran) == (5, 5)
    assert pt(s, prodigy) == (3, 5)
    replay_matches(s)


def test_krang_draw_cause(cards):
    """A player drawing a card caused "draws their second card each turn": it triggers an additional time."""
    s = build(cards, "Krang, the All-Powerful", "Opt", "Opt")
    krang = put(s, "Krang, the All-Powerful")
    opts = [c for c in s.state.cards.values() if c.name == "Opt" and c.owner == "p1"]
    for o in opts:
        act(s, "p1", type="move", card_ids=[o.id], to={"zone": "hand"})
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=opts[0].id)
    settle(s)
    act(s, "p1", type="cast_spell", card_id=opts[1].id)
    settle(s)
    assert s.state.cards[krang.id].counters.get("+1/+1", 0) == 2
    replay_matches(s)


# -- death and draw triggers: coverage ----------------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "level"), [
    ("Sheoldred, the Apocalypse", "FULL"), ("Massacre Wurm", "FULL"), ("Howling Mine", "FULL"),
    ("Loran of the Third Path", "FULL"), ("Secret Rendezvous", "FULL"), ("Goldvein Hydra", "FULL"),
    ("Lifeblood Hydra", "FULL"), ("Murderous Rider // Swift End", "FULL"), ("Ichor Wellspring", "FULL"),
    ("Wurmcoil Engine", "FULL"), ("Brainstorm", "FULL"), ("Kederekt Parasite", "FULL"), ("Disciple of the Vault", "FULL"),
    ("Suture Priest", "FULL"), ("Conch Horn", "FULL"), ("Triplicate Titan", "FULL"), ("Orcish Bowmasters", "FULL"),
    ("Mirkwood Bats", "FULL"),
    # (wave 19B: "that creature's controller may draw": that player is asked, 608.2d)
    ("Fecundity", "FULL"),
])
def test_death_and_draw_coverage(name, level):
    assert cov(name) == level


def kill(s, c, pid="p1"):
    """Lethal damage, then the state-based actions (704.5g) — the engine moves it (not by hand)."""
    act(s, pid, type="set_damage", card_ids=[c.id], delta=20)
    act(s, s.state.rules.priority or pid, type="pass_priority")
    settle(s)


# -- "they" / "that player" (Sheoldred, Massacre Wurm, Suture Priest) ----------------------------------------------------
def test_sheoldred_they_lose_and_you_and_target_opponent_each_draw(cards):
    """Secret Rendezvous: both draw three (121.2c: the active player first). Sheoldred: Alice gains 2 per card, Bob
    ("they": the opponent who drew) loses 2 per card."""
    s = build(cards, "Sheoldred, the Apocalypse", "Secret Rendezvous")
    put(s, "Sheoldred, the Apocalypse")
    spell = to_hand(s, "Secret Rendezvous")
    s = saved(s)
    hands, lives = (hand_size(s), hand_size(s, "p2")), (life(s), life(s, "p2"))
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    settle(s)
    assert (hand_size(s), hand_size(s, "p2")) == (hands[0] - 1 + 3, hands[1] + 3)
    assert (life(s), life(s, "p2")) == (lives[0] + 6, lives[1] - 6)
    replay_matches(s)


def test_loran_you_and_target_opponent(cards):
    from tests.test_rules_conditionals import to_turn

    s = build(cards, "Loran of the Third Path")
    loran = put(s, "Loran of the Third Path")
    to_turn(s, 3)  # (no longer summoning sick)
    hands = (hand_size(s), hand_size(s, "p2"))
    act(s, "p1", type="activate_ability", card_id=loran.id, ability=2, targets=["p2"])
    settle(s)
    assert (hand_size(s), hand_size(s, "p2")) == (hands[0] + 1, hands[1] + 1)
    replay_matches(s)


def test_massacre_wurm_that_player_is_the_creatures_controller(cards):
    """Bob's creatures die to the -2/-2: Bob loses 2 for each; Alice's own creature dying costs her nothing."""
    s = build(cards, "Massacre Wurm", "Grizzly Bears", p2=("Grizzly Bears", "Soul Warden"))
    put(s, "Grizzly Bears", "p2")
    put(s, "Soul Warden", "p2")
    mine = put(s, "Grizzly Bears")
    wurm = to_hand(s, "Massacre Wurm")
    s = saved(s)
    lives = (life(s), life(s, "p2"))
    mana(s, B=3, C=3)
    act(s, "p1", type="cast_spell", card_id=wurm.id)
    settle(s)
    assert life(s, "p2") == lives[1] - 4 + 1  # (Bob's Soul Warden saw the Wurm enter)
    kill(s, mine)
    assert life(s) == lives[0]
    replay_matches(s)


def test_suture_priest_may_have_that_player_lose(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, "Suture Priest", p2=("Grizzly Bears",))
    put(s, "Suture Priest")
    bears = to_hand(s, "Grizzly Bears", "p2")
    before = life(s, "p2")
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    mana(s, "p2", G=2)
    act(s, "p2", type="cast_spell", card_id=bears.id)
    settle(s)  # (Alice's "you may": yes, the first option)
    assert life(s, "p2") == before - 1
    replay_matches(s)


# -- draw-step and draw triggers (Howling Mine, Kederekt Parasite) --------------------------------------------------------
@pytest.mark.parametrize("tapped", [False, True])
def test_howling_mine_each_players_draw_step_if_untapped(cards, tapped):
    """At the beginning of each player's draw step, if this artifact is untapped (603.4: as it triggers and resolves),
    that player draws an additional card."""
    from tests.test_rules_conditionals import until

    s = build(cards, "Howling Mine")
    mine = put(s, "Howling Mine")
    if tapped:
        act(s, "p1", type="tap", card_ids=[mine.id], tapped=True)
    before = hand_size(s, "p2")
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    settle(s)
    assert hand_size(s, "p2") == before + (1 if tapped else 2)
    replay_matches(s)


@pytest.mark.parametrize("red", [False, True])
def test_kederekt_parasite_if_you_control_a_red_permanent(cards, red):
    s = build(cards, "Kederekt Parasite", "Secret Rendezvous")
    put(s, "Kederekt Parasite")
    spell = to_hand(s, "Secret Rendezvous")
    if red:
        from tests.test_rules_conditionals import token_of

        token_of(s, "p1", "Red Thing", "Token Creature — Elemental", colors=("R",))
    before = life(s, "p2")
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    settle(s)  # (three cards drawn: three triggers, "you may": yes)
    assert life(s, "p2") == before - (3 if red else 0)
    replay_matches(s)


# -- dies: last known information (Goldvein Hydra, Lifeblood Hydra), the card's new object (Murderous Rider) -------------
def test_goldvein_and_lifeblood_read_the_power_it_last_had(cards):
    s = build(cards, "Goldvein Hydra", "Lifeblood Hydra")
    gold, blood = put(s, "Goldvein Hydra"), put(s, "Lifeblood Hydra")
    act(s, "p1", type="counter", card_ids=[gold.id], kind="+1/+1", delta=3)
    act(s, "p1", type="counter", card_ids=[blood.id], kind="+1/+1", delta=2)
    s = saved(s)
    before_hand, before_life = hand_size(s), life(s)
    kill(s, gold)
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    assert len(treasures) == 3 and all(c.tapped for c in treasures)
    kill(s, blood)
    assert (hand_size(s), life(s)) == (before_hand + 2, before_life + 2)
    replay_matches(s)


def test_dark_revenant_goes_on_top_of_its_owners_library(cards):
    """"put it on top of its owner's library": the card's new object in the graveyard (400.7e, 603.6c)."""
    s = build(cards, "Dark Revenant")
    revenant = put(s, "Dark Revenant")
    kill(s, revenant)
    assert s.state.zones["p1:library"][0] == revenant.id
    replay_matches(s)


def test_ichor_wellspring_enters_and_goes_to_the_graveyard(cards):
    """"When ~ enters or is put into a graveyard from the battlefield" (603.2: one ability, each event); Disciple of the
    Vault sees the artifact go too."""
    s = build(cards, "Ichor Wellspring", "Shatter", "Disciple of the Vault")
    put(s, "Disciple of the Vault")
    well, shatter = to_hand(s, "Ichor Wellspring"), to_hand(s, "Shatter")
    before = hand_size(s)
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=well.id)
    settle(s)
    assert hand_size(s) == before - 1 + 1
    s = saved(s)
    lives = life(s, "p2")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=shatter.id, targets=[well.id])
    settle(s)
    assert hand_size(s) == before - 2 + 2
    assert life(s, "p2") == lives - 1
    replay_matches(s)


def test_wurmcoil_and_triplicate_titan_make_each_kind(cards):
    s = build(cards, "Wurmcoil Engine", "Triplicate Titan")
    wurm, titan = put(s, "Wurmcoil Engine"), put(s, "Triplicate Titan")
    kill(s, wurm)
    wurms = sorted(c.token.text for c in s.state.cards.values() if c.name == "Phyrexian Wurm" and c.zone == "p1:battlefield")
    assert wurms == ["Deathtouch", "Lifelink"]
    s = saved(s)
    kill(s, titan)
    golems = sorted(c.token.text for c in s.state.cards.values() if c.name == "Golem" and c.zone == "p1:battlefield")
    assert golems == ["Flying", "Trample", "Vigilance"]
    replay_matches(s)


# -- Brainstorm: a private choice, a private order (401.4), nothing named to the other players ----------------------------
def test_brainstorm_puts_back_two_in_the_chosen_order_privately(cards):
    import json

    from app.rules.view import rules_view

    s = build(cards, "Brainstorm", "Opt", "Lightning Bolt", "Counterspell", "Giant Growth")
    storm = to_hand(s, "Brainstorm")
    for name in ("Opt", "Lightning Bolt", "Counterspell", "Giant Growth"):  # (on top of the library)
        c = named(s, name)
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    s = saved(s)
    before = hand_size(s)
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=storm.id)
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and d.min_choices == d.max_choices == 2
    assert "Giant Growth" not in json.dumps(rules_view(s.state, "p2", s.cards)["decision"])  # (Bob: "choosing")
    picked = [o.id for o in d.options if o.label in ("Giant Growth", "Counterspell")]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=picked)
    d = s.state.rules.decision
    assert d is not None and d.kind == "order" and d.player == "p1"
    growth = next(o.id for o in d.options if o.label == "Giant Growth")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[growth, *[o.id for o in d.options if o.id != growth]])
    settle(s)
    assert hand_size(s) == before - 1 + 3 - 2
    top = s.state.zones["p1:library"][:2]
    assert [s.state.cards[c].name for c in top] == ["Giant Growth", "Counterspell"]
    seen_by_bob = json.dumps(s.view("p2"))
    for name in ("Giant Growth", "Counterspell", "Lightning Bolt", "Opt"):
        assert name not in seen_by_bob
    replay_matches(s)


def test_conch_horn_one_card_back_without_an_order(cards):
    s = build(cards, "Conch Horn")
    horn = put(s, "Conch Horn")
    before = hand_size(s)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=horn.id, ability=0)
    d = s.state.rules.decision
    for _ in range(4):
        if d is not None and d.kind == "choose_cards":
            break
        act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
    assert d is not None and d.max_choices == 1
    chosen = d.options[0].id
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[chosen])
    settle(s)
    assert hand_size(s) == before + 2 - 1 and s.state.zones["p1:library"][0] == chosen
    replay_matches(s)


# -- Orcish Bowmasters: "When ~ enters and whenever an opponent draws a card except the first one they draw in each of
# their draw steps" (one ability, two trigger conditions, 603.2) -----------------------------------------------------------
def test_orcish_bowmasters(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, "Orcish Bowmasters", "Secret Rendezvous", "Howling Mine")
    bow, spell = to_hand(s, "Orcish Bowmasters"), to_hand(s, "Secret Rendezvous")
    put(s, "Howling Mine")

    def army():
        found = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name.startswith("Orc Army")]
        return found[0].counters.get("+1/+1", 0) if found else 0

    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bow.id)
    settle(s)
    assert army() == 1  # (it entered)
    mana(s, W=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    settle(s)
    assert army() == 1 + 3  # (Bob drew three; Alice's own draws don't count)
    s = saved(s)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    settle(s)
    assert army() == 4 + 1  # (Bob's draw step: his first card doesn't count, Howling Mine's does)
    replay_matches(s)


def test_mirkwood_bats_create_or_sacrifice_a_token(cards):
    """Either action, each token its own event (603.2c, 111.2): two Soldiers made, then a Treasure sacrificed for
    mana (701.21a, a cost) — three triggers. A token made by hand triggers nothing (the table handles it)."""
    s = build(cards, "Mirkwood Bats", "Raise the Alarm")
    put(s, "Mirkwood Bats")
    alarm = to_hand(s, "Raise the Alarm")
    from tests.test_rules_conditionals import token_of

    treasure = token_of(s, "p1", "Treasure", "Token Artifact — Treasure", pt="0/0",
                        text="{T}, Sacrifice this token: Add one mana of any color.")
    before = life(s, "p2")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=alarm.id)
    settle(s)
    assert life(s, "p2") == before - 2
    s = saved(s)
    act(s, "p1", type="activate_ability", card_id=treasure.id, ability=0, mana_choice="B")
    settle(s)
    assert life(s, "p2") == before - 3
    replay_matches(s)


def test_panharmonicon_each_token_entering(cards):
    """Raise the Alarm: two creatures entering, each one an event Soul Warden triggers on — twice each."""
    s = build(cards, "Panharmonicon", "Soul Warden", "Raise the Alarm")
    put(s, "Panharmonicon")
    put(s, "Soul Warden")
    alarm = to_hand(s, "Raise the Alarm")
    before = life(s)
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=alarm.id)
    settle(s)
    assert life(s) == before + 4
    replay_matches(s)


# -- conditions with commas, "that many", "enters or dies" of other objects ----------------------------------------------
EXTRA += [
    card('Sram, Senior Edificer', set_code='tst', number='T5D46', mana_cost='{1}{W}', cmc=2.0, type_line='Legendary Creature — Dwarf Advisor', oracle_text='Whenever you cast an Aura, Equipment, or Vehicle spell, draw a card.', power='2', toughness='2', colors=['W'], color_identity=['W']),
    card('Old Gnawbone', set_code='tst', number='T5D47', mana_cost='{5}{G}{G}', cmc=7.0, type_line='Legendary Creature — Dragon', oracle_text='Flying\nWhenever a creature you control deals combat damage to a player, create that many Treasure tokens.', power='7', toughness='7', colors=['G'], color_identity=['G'], keywords=['Flying', 'Treasure']),
    card('Daxos, Blessed by the Sun', set_code='tst', number='T5D48', mana_cost='{W}{W}', cmc=2.0, type_line='Legendary Enchantment Creature — Demigod', oracle_text="Daxos's toughness is equal to your devotion to white. (Each {W} in the mana costs of permanents you control counts toward your devotion to white.)\nWhenever another creature you control enters or dies, you gain 1 life.", power='2', toughness='*', colors=['W'], color_identity=['W']),
]


@pytest.mark.parametrize("name", ["Sram, Senior Edificer", "Old Gnawbone", "Daxos, Blessed by the Sun"])
def test_more_trigger_wordings_are_automated(name):
    assert cov(name) == "FULL"


def test_sram_an_aura_equipment_or_vehicle_spell(cards):
    s = build(cards, "Sram, Senior Edificer", "Holy Strength", "Grizzly Bears")
    put(s, "Sram, Senior Edificer")
    bears = put(s, "Grizzly Bears")
    aura = to_hand(s, "Holy Strength")
    before = hand_size(s)
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bears.id])
    settle(s)
    assert hand_size(s) == before - 1 + 1
    replay_matches(s)


def test_old_gnawbone_that_many_treasures(cards):
    from tests.test_rules_conditionals import attack, combat_step, creature, sandbox, through_combat

    s = sandbox(cards, "Old Gnawbone")
    gnaw = named(s, "Old Gnawbone")
    act(s, "p1", type="move", card_ids=[gnaw.id], to={"player": "p1", "zone": "battlefield"})
    bear = creature(s, "p1", "Bear", pt="3/3")
    combat_step(s)
    attack(s, (bear, "p2"))
    through_combat(s)
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    assert len(treasures) == 3
    replay_matches(s)


def test_daxos_another_creature_enters_or_dies(cards):
    s = build(cards, "Daxos, Blessed by the Sun", "Grizzly Bears")
    put(s, "Daxos, Blessed by the Sun")
    bears = to_hand(s, "Grizzly Bears")
    before = life(s)
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert life(s) == before + 1
    s = saved(s)
    kill(s, s.state.cards[bears.id])
    assert life(s) == before + 2
    replay_matches(s)
