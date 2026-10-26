"""Wave 110I s10.

* 702.145c, 701.28, 303.4f: Curse of Leeches turning over (day returns) is attached by its controller to a player they choose, before state-based actions
  (704.5m) could put the unattached Aura into the graveyard; its upkeep trigger then drains the enchanted player.
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import REAL, build, put, resolve, roundtrip
from tests.test_rules_effects import mana, run_until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave110a_kit import answer

CURSE = ("Enchant player\nAs this permanent transforms into Curse of Leeches, attach it to a player.\nAt the beginning of enchanted player's upkeep, "
         "they lose 1 life and you gain 1 life.\nDaybound (If a player casts no spells during their own turn, it becomes night next turn.)")
LURKER = "Lifelink\nNightbound (If a player casts at least two spells during their own turn, it becomes day next turn.)"
EXTRA = [card("Curse of Leeches // Leeching Lurker", set_code="tst", number="L1", layout="transform", mana_cost="{2}{B}", cmc=3.0,
              type_line="Enchantment — Aura Curse // Creature — Leech Horror", colors=["B"], color_identity=["B"], image_uris=None,
              card_faces=[{"object": "card_face", "name": "Curse of Leeches", "mana_cost": "{2}{B}", "type_line": "Enchantment — Aura Curse", "oracle_text": CURSE, "colors": ["B"]},
                          {"object": "card_face", "name": "Leeching Lurker", "mana_cost": "", "type_line": "Creature — Leech Horror", "oracle_text": LURKER,
                           "power": "2", "toughness": "2", "colors": ["B"]}])]
NAME = EXTRA[0]["name"]
HERO = ("Whenever one or more cards are put into exile from your hand or a spell or ability you control exiles one or more permanents from the battlefield, "
        "put that many +1/+1 counters on this creature.\nAs long as this creature has five or more counters on it, it has flying and is an Angel in addition to its "
        "other types.\nAs long as this creature has ten or more counters on it, it has indestructible and is a God in addition to its other types.")
MIRROR = ("{X}, {T}: Change the target of target spell with a single target if that target is you. The new target must be a player. "
          "X is twice the mana value of that spell.")
CAMP = ("Whenever fortified land is tapped for mana, put a +1/+1 counter on target creature you control. If that creature shares a color with the mana that land "
        "produced, create a Junk token. (It's an artifact with \"{T}, Sacrifice this token: Exile the top card of your library. You may play that card this turn. "
        "Activate only as a sorcery.\")\nFortify {3} ({3}: Attach to target land you control. Fortify only as a sorcery. This card enters unattached and stays on the "
        "battlefield if the land leaves.)")
GARRISON = ("Fortified land has indestructible.\nWhenever fortified land becomes tapped, target creature gets +1/+1 until end of turn.\n"
            "Fortify {3} ({3}: Attach to target land you control. Fortify only as a sorcery. This card enters unattached and stays on the battlefield if the land leaves.)")
DAWN = ("Until end of turn, spells and abilities you control that would add colored mana instead add that much white mana. Until end of turn, you may spend "
        "white mana as though it were mana of any color.\nDraw a card.")
PHOENIX = ("Flying\nIf this creature would die, return it to its owner's hand instead. Until that player's next turn, that player plays with that card revealed in "
           "their hand and can't play it.")
EXTRA += [real("Hero of Bretagard", "{2}{W}", 3, "Creature \u2014 Human Warrior", HERO, ("1", "1"), "W"),
          real("Swords to Plowshares", "{W}", 1, "Instant", "Exile target creature. Its controller gains life equal to its power.", None, "W"),
          real("Ignorant Bliss", "{1}{R}", 2, "Instant", "Exile all cards from your hand face down. At the beginning of the next end step, return those cards to your hand, then draw a card.", None, "R"),
          real("Firestorm Phoenix", "{4}{R}{R}", 6, "Creature \u2014 Phoenix", PHOENIX, ("3", "2"), "R"),
          real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B"),
          real("False Dawn", "{1}{W}", 2, "Sorcery", DAWN, None, "W"),
          real("Dark Ritual", "{B}", 1, "Instant", "Add {B}{B}{B}.", None, "B"),
          real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R"),
          real("Reflecting Mirror", "{4}", 4, "Artifact", MIRROR, None, ""),
          real("C.A.M.P.", "{3}", 3, "Artifact \u2014 Fortification", CAMP, None, ""),
          real("Darksteel Garrison", "{3}", 3, "Artifact \u2014 Fortification", GARRISON, None, ""),
          real("Stone Rain", "{2}{R}", 3, "Sorcery", "Destroy target land.", None, "R"),
          real("Probe Goblin", "{R}", 1, "Creature \u2014 Goblin", "", ("1", "1"), "R"),
          real("Probe Bear", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G")]


@pytest.fixture()
def card_db(settings):
    return settings.cards_db_path


@pytest.fixture()
def cards(settings, card_db):
    build_database(fixture_cards() + REAL + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(card_db, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("target", ["p1", "p2"])
def test_curse_of_leeches(cards, target):
    """Night falls (Alice cast nothing), then Bob casts two spells: in Alice's untap step the Lurker turns back into the Curse and Alice picks the player
    it enchants before state-based actions; the Curse stays and drains that player in their upkeep."""
    from tests.wave9c_kit import check

    s = build(cards, [NAME], bob=[(2, "Opt"), (10, "Island")])
    curse = put(s, NAME, "battlefield")
    act(s, "p1", type="attach", card_ids=[curse.id], to="p2")
    run_until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert s.state.table.day_night == "night" and s.state.cards[curse.id].face == 1 and not s.state.cards[curse.id].attached_player
    for opt in [c for c in s.state.cards.values() if c.name == "Opt" and c.owner == "p2"]:
        act(s, "p2", type="move", card_ids=[opt.id], to={"player": "p2", "zone": "hand"})
        mana(s, "p2", U=1)
        act(s, "p2", type="cast_spell", card_id=opt.id)
        resolve(s, [])
    run_until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one" and "attach" in s.state.rules.decision.prompt)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {"p1", "p2"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[target])
    c = s.state.cards[curse.id]
    assert s.state.table.day_night == "day" and c.face == 0 and c.zone == "p1:battlefield" and c.attached_player == target
    roundtrip(s)
    check(s)


def test_hero_of_bretagard(cards):
    """603.2c: one trigger per batch, that many counters: Swords to Plowshares (your spell) on any creature, Ignorant Bliss exiling your hand at once;
    a permanent moved to exile by hand (no spell or ability of yours) adds none."""
    from tests.wave9c_kit import build as kit_build
    from tests.wave9c_kit import cast as kit_cast
    from tests.wave9c_kit import check, life
    from tests.wave9c_kit import mana as kit_mana
    from tests.wave9c_kit import put as kit_put
    from tests.wave9c_kit import to_hand as kit_to_hand
    from tests.wave110a_kit import answer

    s = kit_build(cards, ["Hero of Bretagard", "Swords to Plowshares", "Probe Bear", "Ignorant Bliss"], ["Probe Bear"])
    hero = kit_put(s, "Hero of Bretagard")
    theirs = kit_put(s, "Probe Bear", "p2")

    def counters():
        return s.state.cards[hero.id].counters.get("+1/+1", 0)

    act(s, "p1", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "exile"})
    assert counters() == 0  # moved by hand: no spell or ability
    other = kit_put(s, "Probe Bear")
    kit_to_hand(s, "Swords to Plowshares")
    kit_mana(s, W=1)
    kit_cast(s, "Swords to Plowshares", targets=[other.id])
    answer(s)
    assert counters() == 1 and s.state.cards[other.id].zone.endswith(":exile") and life(s, "p1") == 42
    kit_to_hand(s, "Ignorant Bliss")
    act(s, "p1", type="move", card_ids=s.state.zones["p1:library"][:2], to={"player": "p1", "zone": "hand"})
    n = len(s.state.zones["p1:hand"]) - 1  # every other card in hand is exiled at once: one trigger for the batch
    kit_mana(s, R=1, C=1)
    kit_cast(s, "Ignorant Bliss")
    answer(s)
    assert n == 2 and counters() == 1 + n
    check(s)


def test_firestorm_phoenix(cards):
    """614.1a: destroyed, it goes to its owner's hand instead (it never dies); revealed there and uncastable until that player's next turn begins (500.4)."""
    from app.game.errors import ActionError
    from tests.wave9c_kit import build as kit_build
    from tests.wave9c_kit import cast as kit_cast
    from tests.wave9c_kit import check
    from tests.wave9c_kit import mana as kit_mana
    from tests.wave9c_kit import put as kit_put
    from tests.wave9c_kit import to_hand as kit_to_hand
    from tests.wave100c_kit import to_phase as to_ph
    from tests.wave110a_kit import answer

    s = kit_build(cards, ["Firestorm Phoenix", "Murder"])
    phoenix = kit_put(s, "Firestorm Phoenix")
    kit_to_hand(s, "Murder")
    kit_mana(s, B=2, C=1)
    kit_cast(s, "Murder", targets=[phoenix.id])
    answer(s)
    c = s.state.cards[phoenix.id]
    assert c.zone == "p1:hand" and c.revealed_to == ["*"]
    kit_mana(s, R=2, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=phoenix.id)
    to_ph(s, "main1", turn=2)
    assert s.state.cards[phoenix.id].revealed_to == ["*"] and s.state.cards[phoenix.id].zone == "p1:hand"
    check(s)
    to_ph(s, "main1", turn=3)
    assert s.state.cards[phoenix.id].revealed_to == []
    kit_mana(s, R=2, C=4)
    act(s, "p1", type="cast_spell", card_id=phoenix.id)


@pytest.mark.parametrize("dawn", [True, False])
def test_false_dawn(cards, dawn):
    """106.12b, 609.4b: under False Dawn a Forest and Dark Ritual add white instead of green/black, and white mana pays {R}; without it neither happens."""
    from app.game.errors import ActionError
    from tests.wave9c_kit import build as kit_build
    from tests.wave9c_kit import card_named, check, life
    from tests.wave9c_kit import cast as kit_cast
    from tests.wave9c_kit import mana as kit_mana
    from tests.wave9c_kit import put as kit_put
    from tests.wave9c_kit import to_hand as kit_to_hand
    from tests.wave110a_kit import answer

    s = kit_build(cards, ["False Dawn", "Dark Ritual", "Lightning Bolt"])
    if dawn:
        kit_to_hand(s, "False Dawn")
        kit_mana(s, W=1, C=1)
        kit_cast(s, "False Dawn")
        answer(s)
    forest = kit_put(s, "Forest")
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)
    kit_to_hand(s, "Dark Ritual")
    kit_mana(s, B=1)
    kit_cast(s, "Dark Ritual")
    answer(s)
    units = [u.sym for u in s.state.players["p1"].mana_units]
    assert sorted(units) == (["W"] * 4 if dawn else ["B", "B", "B", "G"])
    kit_to_hand(s, "Lightning Bolt")
    if dawn:
        kit_cast(s, "Lightning Bolt", targets=[card_named(s, "Forest", "p2").id] if False else ["p2"])
        answer(s)
        assert life(s, "p2") == 37
        check(s)
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])


@pytest.mark.parametrize("aim", ["me", "bear"])
def test_reflecting_mirror(cards, aim):
    """115.7, 115.9c, 107.3c: X is twice the spell's mana value (Bolt: 2, a wrong X is refused); a spell aimed at you is redirected to a player (Alice, the only other
    one); aimed at anything else, the ability does nothing."""
    from app.game.errors import ActionError
    from tests.test_rules_conditionals import on_field, settle
    from tests.test_rules_wave5b_stack_interaction import alice_casts
    from tests.test_rules_wave5b_stack_interaction import build as build5b
    from tests.test_rules_wave5b_stack_interaction import roundtrip as roundtrip5b

    s = build5b(cards, ["Lightning Bolt"], ["Reflecting Mirror", "Probe Bear"])
    bear = on_field(s, "Probe Bear", "p2")
    mirror = on_field(s, "Reflecting Mirror", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2" if aim == "me" else bear.id], R=1)
    mana(s, "p2", C=5)
    with pytest.raises(ActionError, match="X is 2"):
        act(s, "p2", type="activate_ability", card_id=mirror.id, ability=0, targets=[bolt.id], x_value=5)
    act(s, "p2", type="activate_ability", card_id=mirror.id, ability=0, targets=[bolt.id])
    settle(s)
    if aim == "me":
        assert s.state.players["p1"].life == 37 and s.state.players["p2"].life == 40
    else:
        assert s.state.players["p1"].life == 40 and s.state.players["p2"].life == 40 and s.state.cards[bear.id].zone.endswith(":graveyard")
    roundtrip5b(s)


def _fortify(s, name, land_owner="p1"):
    from tests.wave9c_kit import mana as kit_mana
    from tests.wave9c_kit import put as kit_put

    fort = kit_put(s, name)
    land = next(c for c in s.state.zones[f"{land_owner}:library"] if s.state.cards[c].name in ("Forest", "Island"))
    act(s, land_owner, type="move", card_ids=[land], to={"player": land_owner, "zone": "battlefield"})
    kit_mana(s, C=3)
    return fort, land


def test_fortify_activation(cards):
    """702.67a, 301.6: Fortify {3} attaches the Fortification to a land you control, at sorcery speed only; not to an opponent's land."""
    from app.game.errors import ActionError
    from tests.wave9c_kit import build as kit_build
    from tests.wave9c_kit import check

    s = kit_build(cards, ["Darksteel Garrison"], ["Probe Bear"])
    fort, land = _fortify(s, "Darksteel Garrison")
    theirs = next(c for c in s.state.zones["p2:library"] if s.state.cards[c].name == "Island")
    act(s, "p2", type="move", card_ids=[theirs], to={"player": "p2", "zone": "battlefield"})
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=fort.id, ability=2, targets=[theirs])
    act(s, "p1", type="activate_ability", card_id=fort.id, ability=2, targets=[land])
    answer(s)
    assert s.state.cards[fort.id].attached_to == land
    check(s)


@pytest.mark.parametrize("fortified", [True, False])
def test_darksteel_garrison(cards, fortified):
    """Fortified land has indestructible (702.12); it becoming tapped pumps a target creature until end of turn (603.2)."""
    from tests.wave9c_kit import build as kit_build
    from tests.wave9c_kit import cast as kit_cast
    from tests.wave9c_kit import check
    from tests.wave9c_kit import mana as kit_mana
    from tests.wave9c_kit import put as kit_put
    from tests.wave9c_kit import to_hand as kit_to_hand

    s = kit_build(cards, ["Darksteel Garrison", "Probe Bear", "Stone Rain"])
    fort, land = _fortify(s, "Darksteel Garrison")
    bear = kit_put(s, "Probe Bear")
    if fortified:
        act(s, "p1", type="activate_ability", card_id=fort.id, ability=2, targets=[land])
        answer(s)
        assert s.state.cards[fort.id].attached_to == land
    kit_to_hand(s, "Stone Rain")
    kit_mana(s, R=1, C=2)
    kit_cast(s, "Stone Rain", targets=[land])
    answer(s)
    assert s.state.cards[land].zone == ("p1:battlefield" if fortified else "p1:graveyard")  # indestructible only while fortified
    if not fortified:
        return
    act(s, "p1", type="activate_ability", card_id=land, ability=0)
    answer(s, bear.id)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    from tests.wave110c_kit import ch

    assert ch(s, s.state.cards[bear.id]).pt == (3, 3)
    check(s)


@pytest.mark.parametrize("creature", ["Probe Bear", "Probe Goblin"])
def test_camp(cards, creature):
    """106.12a: a tapped fortified Forest produced {G}: the counter goes on the target creature; a Junk token only if that creature is green."""
    from tests.wave9c_kit import build as kit_build
    from tests.wave9c_kit import check
    from tests.wave9c_kit import put as kit_put

    s = kit_build(cards, ["C.A.M.P.", creature])
    fort, land = _fortify(s, "C.A.M.P.")
    c = kit_put(s, creature)
    act(s, "p1", type="activate_ability", card_id=fort.id, ability=1, targets=[land])
    answer(s)
    assert s.state.cards[fort.id].attached_to == land
    act(s, "p1", type="activate_ability", card_id=land, ability=0)
    answer(s, c.id)
    assert s.state.cards[c.id].counters.get("+1/+1") == 1
    junk = [x for x in s.state.cards.values() if x.name == "Junk" and x.zone == "p1:battlefield"]
    assert len(junk) == (1 if creature == "Probe Bear" else 0)
    check(s)
