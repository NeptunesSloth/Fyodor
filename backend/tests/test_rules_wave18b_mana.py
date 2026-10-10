"""Wave 18B: mana provenance and spending restrictions (CR 2026-09-25).

* 106.6: mana added by a spell (Geosurge) or by an ability activated by hand (Ancient Ziggurat, Grand Architect, Master of Dark Rites) that
  restricts how it can be spent waits in the pool as a unit that remembers the restriction; the payer spends it only where it may.
* 106.3, 107.4h: the source of mana is remembered (a Treasure, a snow source), for "if mana from a Treasure was spent to cast it", "Add {C}
  for each {S} spent to cast this spell" and "mana from an artifact source spent to cast it".
* A unit never leaks: nothing hidden is in a view; old saves (plain counts) load as unrestricted mana.

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import casting, coverage
from app.rules.oracle import AbilityText
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import build, creature, on_field, to_hand
from tests.test_rules_effects import mana, replay_matches


def real(name, cost, cmc, types, text, pt=None, colors=()):
    extra = {"power": pt[0], "toughness": pt[1]} if pt else {}
    return card(name, set_code="tst", number=f"18B-{name[:6]}", mana_cost=cost, cmc=float(cmc), type_line=types, oracle_text=text,
                colors=list(colors), color_identity=list(colors), **extra)


EXTRA = [
    real("Geosurge", "{R}{R}{R}{R}", 4, "Sorcery", "Add {R}{R}{R}{R}{R}{R}{R}. Spend this mana only to cast artifact or creature spells.", None, "R"),
    real("Augury Raven", "{3}{U}", 4, "Creature — Bird", "Flying\nForetell {1}{U} (During your turn, you may pay {2} and exile this card from "
         "your hand face down. Cast it on a later turn for its foretell cost.)", ("3", "1"), "U"),
    real("Grand Architect", "{1}{U}{U}", 3, "Creature — Vedalken Artificer",
         "Other blue creatures you control get +1/+1.\n{U}: Target artifact creature becomes blue until end of turn.\n"
         "Tap an untapped blue creature you control: Add {C}{C}. Spend this mana only to cast artifact spells or activate abilities of artifacts.",
         ("1", "3"), "U"),
    real("Master of Dark Rites", "{B}", 1, "Creature — Vampire Cleric",
         "{T}, Sacrifice another creature: Add {B}{B}{B}. Spend this mana only to cast Vampire, Cleric, and/or Demon spells.", ("1", "1"), "B"),
    real("Smaug, Wicked Worm", "{3}{B}{R}", 5, "Legendary Creature — Dragon",
         "Flying\nWhen Smaug enters, create X tapped Treasure tokens, where X is the number of artifacts your opponents control.\n"
         "Whenever you cast a spell, if mana from a Treasure was spent to cast it, you draw a card and lose 1 life.", ("5", "5"), "BR"),
    real("Tundra Fumarole", "{1}{R}{R}", 3, "Snow Sorcery",
         "Tundra Fumarole deals 4 damage to target creature or planeswalker. Add {C} for each {S} spent to cast this spell. Until end of turn, "
         "you don't lose this mana as steps and phases end. ({S} is mana from a snow source.)", None, "R"),
    real("Snow-Covered Mountain", "", 0, "Basic Snow Land — Mountain", "({T}: Add {R}.)"),
    real("Snow-Covered Island", "", 0, "Basic Snow Land — Island", "({T}: Add {U}.)"),
    real("Coin of Mastery", "{4}", 4, "Artifact",
         "Each creature you control enters with an additional +1/+1 counter on it for each mana from an artifact source spent to cast it.\n"
         "{T}: Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")"),
    real("Jaded Sell-Sword", "{3}{R}", 4, "Creature — Dragon Warrior",
         "When this creature enters, if mana from a Treasure was spent to cast it, it gains first strike and haste until end of turn.", ("4", "3"), "R"),
    real("Spoils of the Hunt", "{2}{G}", 3, "Instant",
         "Target creature you control gets +1/+0 until end of turn for each mana from a Treasure that was spent to cast this spell. Then that "
         "creature deals damage equal to its power to target creature an opponent controls.", None, "G"),
    real("Delighted Halfling", "{G}", 1, "Creature — Halfling Citizen",
         "{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a legendary spell, and that spell can't be countered.",
         ("1", "2"), "G"),
    real("Isamaru, Hound of Konda", "{W}", 1, "Legendary Creature — Dog", "", ("2", "2"), "W"),
    real("Hall of the Bandit Lord", "", 0, "Legendary Land",
         "Hall of the Bandit Lord enters tapped.\n{T}, Pay 3 life: Add {C}. If that mana is spent on a creature spell, it gains haste."),
    real("Scaled Nurturer", "{1}{G}", 2, "Creature — Dragon Druid",
         "{T}: Add {G}. When you spend this mana to cast a Dragon creature spell, you gain 2 life.", ("1", "2"), "G"),
    real("Pyromancer's Goggles", "{5}", 5, "Legendary Artifact",
         "{T}: Add {R}. When that mana is spent to cast a red instant or sorcery spell, copy that spell and you may choose new targets for the copy."),
    real("Opal Palace", "", 0, "Land",
         "{T}: Add {C}.\n{1}, {T}: Add one mana of any color in your commander's color identity. If you spend this mana to cast your commander, "
         "it enters with a number of additional +1/+1 counters on it equal to the number of times it's been cast from the command zone this game."),
    real("Rosheen Meanderer", "{3}{G}", 4, "Legendary Creature — Giant Shaman",
         "{T}: Add {C}{C}{C}{C}. Spend this mana only on costs that contain {X}.", ("4", "4"), "G"),
    real("Blaze", "{X}{R}", 1, "Sorcery", "Blaze deals X damage to any target.", None, "R"),
    real("K'rrik, Son of Yawgmoth", "{4}{B/P}{B/P}{B/P}", 7, "Legendary Creature — Phyrexian Horror Minion",
         "({B/P} can be paid with either {B} or 2 life.)\nLifelink\nFor each {B} in a cost, you may pay 2 life rather than pay that mana.\n"
         "Whenever you cast a black spell, put a +1/+1 counter on K'rrik.", ("2", "2"), "B"),
    real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B"),
    real("Berg Strider", "{4}{U}", 5, "Snow Creature — Giant Wizard",
         "When this creature enters, tap target artifact or creature an opponent controls. If {S} was spent to cast this spell, that permanent "
         "doesn't untap during its controller's next untap step. ({S} is mana from a snow source.)", ("4", "4"), "U"),
    real("Karn, Legacy Reforged", "{5}", 5, "Legendary Artifact Creature — Golem",
         "Karn's power and toughness are each equal to the greatest mana value among artifacts you control.\n"
         "At the beginning of your upkeep, add {C} for each artifact you control. This mana can't be spent to cast nonartifact spells. "
         "Until end of turn, you don't lose this mana as steps and phases end.", ("*", "*"), ""),
]
FULL = ["Opal Palace", "K'rrik, Son of Yawgmoth", "Rosheen Meanderer", "Delighted Halfling", "Hall of the Bandit Lord", "Scaled Nurturer", "Pyromancer's Goggles", "Spoils of the Hunt", "Geosurge", "Grand Architect", "Master of Dark Rites", "Smaug, Wicked Worm", "Tundra Fumarole", "Coin of Mastery",
        "Jaded Sell-Sword", "Berg Strider", "Karn, Legacy Reforged"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


def settle(s, limit=30):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def pool(s, pid="p1"):
    p = s.state.players[pid]
    return dict(p.mana), sorted((u.sym, u.only, tuple(u.tags)) for u in p.mana_units)


def units(s, pid="p1"):
    return [(u.sym, u.only) for u in s.state.players[pid].mana_units]


def ability(s, c, start):
    return next(i for i, a in enumerate(s.cards.resolve(c.name).get("oracle_text", "").split("\n")) if a.startswith(start))


def chars(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def hand_size(s, pid="p1"):
    return len(zone(s.state, pid, "hand"))


@pytest.mark.parametrize("name", FULL)
def test_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_a_spell_adds_restricted_mana_that_pays_only_where_it_may(cards):
    s = build(cards, "Geosurge", "Monastery Swiftspear", "Lightning Bolt")
    to_hand(s, "Geosurge"), to_hand(s, "Monastery Swiftspear"), to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=4)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Geosurge"))
    settle(s)
    assert pool(s)[0] == {} and len(units(s)) == 7 and all(sym == "R" for sym, _ in units(s))  # seven restricted {R}
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt")
    assert not casting.castable(s.state, "p1", bolt, s.cards)  # (not an artifact or creature spell)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Monastery Swiftspear"))
    settle(s)
    assert len(units(s)) == 6 and any(c.name == "Monastery Swiftspear" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    roundtrip(s)


def test_creature_spell_mana_does_not_pay_to_foretell_a_creature_card(cards):
    # Review 19: foretelling is a special action (116.2h), not casting a spell: "Spend this mana only to cast … creature spells" can't pay it
    s = build(cards, "Geosurge", "Augury Raven")
    to_hand(s, "Geosurge")
    raven = to_hand(s, "Augury Raven")
    mana(s, "p1", R=4)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Geosurge"))
    settle(s)
    assert len(units(s)) == 7
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=raven.id, ability=1)
    assert s.state.cards[raven.id].zone == "p1:hand"
    roundtrip(s)


def test_restricted_mana_empties_with_the_step(cards):
    s = build(cards, "Geosurge")
    to_hand(s, "Geosurge")
    mana(s, "p1", R=4)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Geosurge"))
    settle(s)
    assert len(units(s)) == 7
    act(s, "p1", type="pass_priority")  # (to combat: 500.4)
    act(s, "p2", type="pass_priority") if s.state.rules.priority == "p2" else None
    assert s.state.turn.phase != "main1" or units(s) == []
    roundtrip(s)


def test_grand_architect_mana_by_hand_pays_for_artifacts_only(cards):
    s = build(cards, "Grand Architect", "Sol Ring", "Grizzly Bears")
    arch = on_field(s, "Grand Architect")
    to_hand(s, "Sol Ring"), to_hand(s, "Grizzly Bears")
    act(s, "p1", type="activate_ability", card_id=arch.id, ability=ability(s, arch, "Tap an untapped"))
    settle(s)  # (the cost's one choice: the Architect is the one blue creature)
    assert s.state.cards[arch.id].tapped and len(units(s)) == 2
    assert s.state.players["p1"].mana == {}
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    assert not casting.castable(s.state, "p1", bears, s.cards)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Sol Ring"))
    settle(s)
    assert len(units(s)) == 1 and any(c.name == "Sol Ring" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    roundtrip(s)


def test_master_of_dark_rites_mana_pays_for_a_vampire_spell(cards):
    s = build(cards, "Master of Dark Rites")
    master = on_field(s, "Master of Dark Rites")
    s.state.rules.controlled_since[master.id].turn = 0
    victim = creature(s, "p1", "Victim")
    act(s, "p1", type="activate_ability", card_id=master.id, ability=0)
    settle(s)
    assert units(s) and all(sym == "B" for sym, _ in units(s)) and len(units(s)) == 3
    assert victim.id not in s.state.cards  # (sacrificed: a token)
    assert all("Vampire" in (u.only or "") for u in s.state.players["p1"].mana_units)
    roundtrip(s)


def treasure(s, pid="p1"):
    act(s, pid, type="create_token", player=pid, token={"name": "Treasure", "type_line": "Token Artifact — Treasure", "text":
                                                         "{T}, Sacrifice this token: Add one mana of any color."})
    return next(c for c in s.state.cards.values() if c.name == "Treasure" and c.owner == pid)


def bolt(s):
    to_hand(s, "Lightning Bolt")
    return next(c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.zone == "p1:hand")


def test_mana_from_a_treasure_spent_by_the_payer_triggers_smaug(cards):
    s = build(cards, "Smaug, Wicked Worm", "Lightning Bolt")
    on_field(s, "Smaug, Wicked Worm")
    t = treasure(s)
    b = bolt(s)
    hand, life = hand_size(s), s.state.players["p1"].life
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
    settle(s)
    assert t.id not in s.state.cards and hand_size(s) == hand - 1 + 1 and s.state.players["p1"].life == life - 1  # (drew, lost 1)
    roundtrip(s)


def test_mana_from_a_treasure_tapped_by_hand_is_remembered_in_the_pool(cards):
    s = build(cards, "Smaug, Wicked Worm", "Lightning Bolt")
    on_field(s, "Smaug, Wicked Worm")
    t = treasure(s)
    b = bolt(s)
    act(s, "p1", type="activate_ability", card_id=t.id, ability=0, mana_choice="R")
    assert s.state.players["p1"].mana == {} and [(u.sym, u.tags) for u in s.state.players["p1"].mana_units][0][0] == "R"
    assert "Treasure" in s.state.players["p1"].mana_units[0].tags
    hand, life = hand_size(s), s.state.players["p1"].life
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
    settle(s)
    assert hand_size(s) == hand and s.state.players["p1"].life == life - 1 and s.state.players["p1"].mana_units == []
    roundtrip(s)


def test_mana_from_other_sources_does_not_trigger_smaug(cards):
    s = build(cards, "Smaug, Wicked Worm", "Lightning Bolt")
    on_field(s, "Smaug, Wicked Worm")
    treasure(s)  # (there, but not used)
    b = bolt(s)
    mana(s, "p1", R=1)
    hand, life = hand_size(s), s.state.players["p1"].life
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])
    settle(s)
    assert hand_size(s) == hand - 1 and s.state.players["p1"].life == life
    roundtrip(s)


def snow_lands(s, *names):
    for n in names:
        c = next(c for c in s.state.cards.values() if c.name == n and c.owner == "p1" and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})


def test_snow_mana_spent_adds_colorless_for_each_s(cards):
    s = build(cards, "Tundra Fumarole", "Snow-Covered Mountain", "Snow-Covered Island")
    snow_lands(s, "Snow-Covered Mountain", "Snow-Covered Island")
    to_hand(s, "Tundra Fumarole")
    target = creature(s, "p2", "Bob Bear", "3/3")
    # {1}{R}{R}: the snow Mountain's {R}, the snow Island's {U} and a plain {R} from the pool: two of the three mana are from snow sources
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Tundra Fumarole"), targets=[target.id])
    settle(s)
    assert s.state.players["p1"].mana == {"C": 2}  # (the plain {R} isn't from a snow source)
    roundtrip(s)


def test_snow_mana_tapped_by_hand_is_remembered(cards):
    s = build(cards, "Tundra Fumarole", "Snow-Covered Mountain", "Snow-Covered Island")
    snow_lands(s, "Snow-Covered Mountain", "Snow-Covered Island")
    mountain = next(c for c in s.state.cards.values() if c.name == "Snow-Covered Mountain")
    to_hand(s, "Tundra Fumarole")
    target = creature(s, "p2", "Bob Bear", "3/3")
    act(s, "p1", type="activate_ability", card_id=mountain.id, ability=0)
    assert s.state.players["p1"].mana == {} and "Snow" in s.state.players["p1"].mana_units[0].tags
    mana(s, "p1", R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Tundra Fumarole"), targets=[target.id])
    settle(s)
    assert s.state.players["p1"].mana == {"C": 1} and s.state.players["p1"].mana_units == []  # (one {S}: the snow Mountain's {R})
    roundtrip(s)


def test_coin_of_mastery_counts_the_mana_from_artifact_sources(cards):
    s = build(cards, "Coin of Mastery", "Sol Ring", "Grizzly Bears")
    on_field(s, "Coin of Mastery")
    ring = on_field(s, "Sol Ring")
    s.state.rules.controlled_since[ring.id].turn = 0
    to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=1)
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    act(s, "p1", type="cast_spell", card_id=bears.id)  # {1}{G}: the pool's {G} and one of Sol Ring's {C}
    settle(s)
    assert s.state.cards[bears.id].counters.get("+1/+1", 0) == 1
    # Sol Ring's other {C} wasn't needed: it stays in the pool, still remembered as mana from an artifact
    assert s.state.players["p1"].mana == {} and [(u.sym, "Artifact" in u.tags) for u in s.state.players["p1"].mana_units] == [("C", True)]
    roundtrip(s)


def test_jaded_sell_sword_with_treasure_mana(cards):
    s = build(cards, "Jaded Sell-Sword")
    to_hand(s, "Jaded Sell-Sword")
    treasure(s)
    mana(s, "p1", C=3)
    sword = next(c for c in s.state.cards.values() if c.name == "Jaded Sell-Sword")
    act(s, "p1", type="cast_spell", card_id=sword.id)  # {3}{R}: the Treasure's {R}
    settle(s)
    ch = chars(s, sword)
    assert "first strike" in ch.keywords and "haste" in ch.keywords
    roundtrip(s)


def test_jaded_sell_sword_without_treasure_mana(cards):
    s = build(cards, "Jaded Sell-Sword")
    to_hand(s, "Jaded Sell-Sword")
    treasure(s)
    mana(s, "p1", C=3, R=1)
    sword = next(c for c in s.state.cards.values() if c.name == "Jaded Sell-Sword")
    act(s, "p1", type="cast_spell", card_id=sword.id)
    settle(s)
    ch = chars(s, sword)
    assert "first strike" not in ch.keywords and "haste" not in ch.keywords
    roundtrip(s)


def test_spoils_of_the_hunt_counts_each_mana_from_a_treasure(cards):
    s = build(cards, "Spoils of the Hunt")
    to_hand(s, "Spoils of the Hunt")
    mine = creature(s, "p1", "My Bear", "2/2")
    theirs = creature(s, "p2", "Their Bear", "5/5")
    treasure(s), treasure(s)
    mana(s, "p1", C=1)
    spell = next(c for c in s.state.cards.values() if c.name == "Spoils of the Hunt")
    # {2}{G}: two Treasures (any color) and one plain {C}: two mana from Treasures
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[mine.id, theirs.id], target_counts=[1, 1])
    settle(s)
    assert s.state.cards[theirs.id].damage == 4  # (2 + 2: it deals damage equal to its power)
    roundtrip(s)


def to_turn(s, number, player):
    for _ in range(80):
        if s.state.turn.number == number and s.state.turn.active_player == player:
            return
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def test_karns_restricted_mana_is_kept_through_the_steps_and_pays_for_an_artifact(cards):
    s = build(cards, "Karn, Legacy Reforged", "Sol Ring", "Grizzly Bears")
    on_field(s, "Karn, Legacy Reforged")
    on_field(s, "Sol Ring")
    to_hand(s, "Grizzly Bears"), to_hand(s, "Sol Ring") if False else None
    to_turn(s, 3, "p1")
    settle(s)  # (the upkeep trigger: {C} for each of the two artifacts)
    assert len(units(s)) == 2 and s.state.players["p1"].mana == {}
    while s.state.turn.phase not in ("main1",):  # the upkeep and draw steps end: the mana stays (106.4)
        d = s.state.rules.decision
        assert d is None
        act(s, s.state.rules.priority, type="pass_priority")
    assert len(units(s)) == 2
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "hand"})
    assert not casting.castable(s.state, "p1", bears, s.cards)  # ("This mana can't be spent to cast nonartifact spells")
    roundtrip(s)


def test_the_mana_of_delighted_halfling_makes_the_legendary_spell_uncounterable(cards):
    s = build(cards, "Delighted Halfling", "Isamaru, Hound of Konda", p2=("Counterspell",))
    halfling = on_field(s, "Delighted Halfling")
    s.state.rules.controlled_since[halfling.id].turn = 0
    dog = to_hand(s, "Isamaru, Hound of Konda")
    counterspell = to_hand(s, "Counterspell", "p2")
    mana(s, "p2", U=2)
    act(s, "p1", type="cast_spell", card_id=dog.id)  # {W}: the Halfling's restricted mana is the only source
    assert s.state.cards[halfling.id].tapped and s.state.cards[dog.id].zone == "stack"
    act(s, "p2", type="cast_spell", card_id=counterspell.id, targets=[dog.id])
    settle(s)
    assert s.state.cards[dog.id].zone == "p1:battlefield"  # (Counterspell resolved and did nothing: 106.6)
    roundtrip(s)


def test_other_mana_leaves_the_legendary_spell_counterable(cards):
    s = build(cards, "Delighted Halfling", "Isamaru, Hound of Konda", p2=("Counterspell",))
    on_field(s, "Delighted Halfling")
    dog = to_hand(s, "Isamaru, Hound of Konda")
    counterspell = to_hand(s, "Counterspell", "p2")
    mana(s, "p2", U=2)
    mana(s, "p1", W=1)
    act(s, "p1", type="cast_spell", card_id=dog.id)  # (the pool's {W} pays; the Halfling stays untapped)
    act(s, "p2", type="cast_spell", card_id=counterspell.id, targets=[dog.id])
    settle(s)
    assert s.state.cards[dog.id].zone == "p1:graveyard"
    roundtrip(s)


def test_hall_of_the_bandit_lord_gives_a_creature_spell_haste(cards):
    s = build(cards, "Hall of the Bandit Lord", "Grizzly Bears")
    hall = on_field(s, "Hall of the Bandit Lord")
    to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=1)
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    act(s, "p1", type="cast_spell", card_id=bears.id)  # {1}{G}: the pool's {G} and the Hall's {C} (pay 3 life)
    settle(s)
    assert s.state.cards[hall.id].tapped and s.state.players["p1"].life == 37
    assert "haste" in chars(s, bears).keywords
    roundtrip(s)


def test_scaled_nurturer_mana_gains_two_life_for_a_dragon_spell(cards):
    s = build(cards, "Scaled Nurturer", "Jaded Sell-Sword")
    nurturer = on_field(s, "Scaled Nurturer")
    s.state.rules.controlled_since[nurturer.id].turn = 0
    sword = to_hand(s, "Jaded Sell-Sword")
    mana(s, "p1", C=2, R=1)
    act(s, "p1", type="cast_spell", card_id=sword.id)  # {3}{R}: the Nurturer's {G} pays {1}: "When you spend this mana to cast a Dragon creature spell"
    settle(s)
    assert s.state.players["p1"].life == 42
    roundtrip(s)


def test_pyromancers_goggles_copy_the_red_spell(cards):
    s = build(cards, "Pyromancer's Goggles", "Lightning Bolt")
    goggles = on_field(s, "Pyromancer's Goggles")
    b = bolt(s)
    act(s, "p1", type="cast_spell", card_id=b.id, targets=["p2"])  # {R}: the Goggles' mana
    assert s.state.cards[goggles.id].tapped
    settle(s)
    assert s.state.players["p2"].life == 34  # 3 + the copy's 3
    roundtrip(s)


def geosurged(cards, *names):
    s = build(cards, "Geosurge", *names)
    to_hand(s, "Geosurge")
    for n in names:
        to_hand(s, n)
    mana(s, "p1", R=4)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Geosurge"))
    settle(s)
    return s


def test_restricted_units_pay_in_the_tap_your_own_mana_mode(cards):
    s = geosurged(cards, "Monastery Swiftspear")
    s.state.rules.prefs["p1"].payment = "self"  # (the internal mode: the player taps their own mana, the pool pays)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Monastery Swiftspear"))
    settle(s)
    assert len(units(s)) == 6 and any(c.name == "Monastery Swiftspear" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    roundtrip(s)


def test_manual_sources_still_spend_the_pools_restricted_mana_first(cards):
    s = geosurged(cards, "Monastery Swiftspear")
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Monastery Swiftspear"), sources=[])
    settle(s)
    assert len(units(s)) == 6
    roundtrip(s)


def test_old_saves_load_with_plain_counts_and_no_units(cards):
    s = build(cards, "Lightning Bolt")
    mana(s, "p1", R=1)
    dump = s.state.model_dump(mode="json")
    for p in dump["players"].values():  # (a save from before wave 18B)
        p.pop("mana_units", None), p.pop("mana_seq", None)
    dump["rules"].pop("provenance", None)
    loaded = GameSession(GameState.model_validate(dump), cards=s.cards)
    assert loaded.state.players["p1"].mana == {"R": 1} and loaded.state.players["p1"].mana_units == []
    b = bolt(loaded)
    act(loaded, "p1", type="cast_spell", card_id=b.id, targets=["p2"])  # (the plain {R} pays: unrestricted)
    settle(loaded)
    assert loaded.state.players["p2"].life == 37


def test_views_show_the_same_pool_to_everyone_and_nothing_hidden(cards):
    import json

    from app.game.views import SPECTATOR, build_view

    s = geosurged(cards, "Monastery Swiftspear")
    secret = next(c for c in s.state.cards.values() if c.name == "Monastery Swiftspear" and c.zone == "p1:hand")
    views = {v: build_view(s.state, v) for v in ("p1", "p2", SPECTATOR)}
    pools = {v: [p["mana_units"] for p in views[v]["players"] if p["id"] == "p1"][0] for v in views}
    assert pools["p1"] == pools["p2"] == pools[SPECTATOR] and len(pools["p1"]) == 7
    assert set(pools["p2"][0]) == {"id", "sym", "src", "tags", "only", "note", "riders"}
    assert secret.name not in json.dumps(views["p2"]) and secret.name not in json.dumps(views[SPECTATOR])  # (the hand stays hidden)
    d = s.state.rules.decision
    assert d is None


@pytest.mark.parametrize(("sentence", "changes", "own", "ok"), [
    ("Spend this mana only to cast spells with mana value 5 or greater or spells with {X} in their mana costs.", {}, True, False),
    ("Spend this mana only to cast spells with mana value 5 or greater or spells with {X} in their mana costs.", {"mana_value": 5}, True, True),
    ("Spend this mana only to cast spells with mana value 5 or greater or spells with {X} in their mana costs.", {"mana_cost": "{X}{G}"}, True, True),
    ("Spend this mana only to cast creature spells with mana value 4 or greater or creature spells with {X} in their mana costs.",
     {"mana_value": 4}, True, True),
    ("Spend this mana only to cast spells you don't own.", {}, True, False),
    ("Spend this mana only to cast spells you don't own.", {}, False, True),
    ("Spend this mana only to cast a spell with devoid.", {}, True, False),
    ("Spend this mana only to cast a spell with devoid.", {"granted": frozenset({"devoid"})}, True, True),
    ("Spend this mana only to cast creature spells with no abilities.", {}, True, True),
    ("Spend this mana only to cast creature spells with no abilities.", {"abilities": (AbilityText(0, "Trample", "keywords", ("trample",)),)}, True, False),
])
def test_spend_only_by_what_the_spell_is(cards, sentence, changes, own, ok):
    from dataclasses import replace

    s = build(cards, "Grizzly Bears")
    kind = M_parse_spend(sentence)
    assert kind is not None
    bears = chars(s, next(c for c in s.state.cards.values() if c.name == "Grizzly Bears"))
    spell = replace(bears, **changes)
    assert casting.spend_allowed(kind, casting.Purpose(spell=spell, zone="p1:hand", player="p1", own=own)) is ok


def M_parse_spend(sentence):
    from app.rules import mana as M

    return M.spend_kind(sentence.rstrip("."))


def test_rosheens_mana_pays_only_costs_that_contain_x_and_the_rest_stays_restricted(cards):
    s = build(cards, "Rosheen Meanderer", "Blaze", "Lightning Bolt", "Mountain")
    rosheen = on_field(s, "Rosheen Meanderer")
    s.state.rules.controlled_since[rosheen.id].turn = 0
    on_field(s, "Mountain")
    blaze = to_hand(s, "Blaze")
    act(s, "p1", type="cast_spell", card_id=blaze.id, x_value=3, targets=["p2"])  # {X}{R}: X = 3 from Rosheen's {C}{C}{C}{C}, {R} from the Mountain
    settle(s)
    assert s.state.players["p2"].life == 37 and s.state.cards[rosheen.id].tapped
    assert len(units(s)) == 1 and units(s)[0][0] == "C"  # (its fourth {C}: still restricted to costs with {X})
    roundtrip(s)


def test_rosheens_mana_cannot_pay_a_cost_without_x(cards):
    s = build(cards, "Rosheen Meanderer", "Grizzly Bears")
    rosheen = on_field(s, "Rosheen Meanderer")
    s.state.rules.controlled_since[rosheen.id].turn = 0
    bears = to_hand(s, "Grizzly Bears")
    assert not casting.castable(s.state, "p1", bears, s.cards)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=bears.id)


def test_krrik_pays_2_life_for_a_black_symbol(cards):
    s = build(cards, "K'rrik, Son of Yawgmoth", "Murder")
    on_field(s, "K'rrik, Son of Yawgmoth")
    murder = to_hand(s, "Murder")
    victim = creature(s, "p2", "Bob Bear", "2/2")
    mana(s, "p1", C=1, B=1)  # {1}{B}{B}: the pool pays {1} and one {B}; the other {B} is 2 life
    life = s.state.players["p1"].life
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[victim.id])
    settle(s)
    assert victim.id not in s.state.cards and s.state.players["p1"].life == life - 2
    assert s.state.players["p1"].mana == {}
    roundtrip(s)


def test_without_krrik_the_black_mana_is_needed(cards):
    s = build(cards, "Murder")
    murder = to_hand(s, "Murder")
    victim = creature(s, "p2", "Bob Bear", "2/2")
    mana(s, "p1", C=1, B=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=murder.id, targets=[victim.id])


def test_opal_palace_mana_puts_counters_on_the_commander_for_each_cast_from_the_command_zone(cards):
    s = build(cards, "Opal Palace")
    on_field(s, "Opal Palace")
    krenko = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    mana(s, "p1", R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=krenko.id)  # the first cast: plain mana, no counters
    settle(s)
    assert s.state.cards[krenko.id].counters == {}
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "command"})
    mana(s, "p1", C=6, R=1)
    act(s, "p1", type="cast_spell", card_id=krenko.id)  # the second ({2}{R}{R} + {2} tax): the Palace's {R} (paid with {1}) is the second red
    settle(s)
    assert s.state.cards[krenko.id].zone.endswith("battlefield") and s.state.players["p1"].commander_casts[krenko.commander_key] == 2
    assert s.state.cards[krenko.id].counters.get("+1/+1", 0) == 2  # (the count includes the cast being paid for)
    roundtrip(s)
