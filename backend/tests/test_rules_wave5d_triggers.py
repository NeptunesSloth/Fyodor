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
    ("Panharmonicon", "FULL"), ("Teysa Karlov", "FULL"), ("Harmonic Prodigy", "FULL"), ("Veyran, Voice of Duality", "FULL"),
    ("Delney, Streetwise Lookout", "FULL"), ("Ancient Greenwarden", "FULL"), ("Yarok, the Desecrated", "FULL"),
    ("Krang, the All-Powerful", "FULL"), ("Annie Joins Up", "FULL"), ("Naban, Dean of Iteration", "FULL"),
    # refused: an attack's cause ("attacks and isn't blocked"?), spells' abilities, a condition on the multiplier
    ("Isshin, Two Heavens as One", "PARTIAL"), ("Echoes of Eternity", "PARTIAL"), ("Sanctum of All", "PARTIAL"),
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
             "triggers an additional time.") is None


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
