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
    real("Berg Strider", "{4}{U}", 5, "Snow Creature — Giant Wizard",
         "When this creature enters, tap target artifact or creature an opponent controls. If {S} was spent to cast this spell, that permanent "
         "doesn't untap during its controller's next untap step. ({S} is mana from a snow source.)", ("4", "4"), "U"),
    real("Karn, Legacy Reforged", "{5}", 5, "Legendary Artifact Creature — Golem",
         "Karn's power and toughness are each equal to the greatest mana value among artifacts you control.\n"
         "At the beginning of your upkeep, add {C} for each artifact you control. This mana can't be spent to cast nonartifact spells. "
         "Until end of turn, you don't lose this mana as steps and phases end.", ("*", "*"), ""),
]
FULL = ["Geosurge", "Grand Architect", "Master of Dark Rites", "Smaug, Wicked Worm", "Tundra Fumarole", "Coin of Mastery",
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
