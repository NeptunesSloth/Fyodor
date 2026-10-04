"""-- copy abilities (wave 19E) -- "Copy target activated or triggered ability you control from an enchantment / colorless / creature
source." (Weaver of Harmony, Abstruse Archaic, Echo, Perceptive Prodigy; 707.10b: a copy of an ability has the same source; the
source is read as it last existed, 608.2h). Oracle text transcribed from the card database."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, deck, turn_on, zone
from tests.test_rules_attachments import ch
from tests.test_rules_copy import _card, hold, life, named, on_stack, pay, resolve_top, to_hand
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_trigger_context import responsive

EXTRA = [
    _card("Weaver of Harmony", "W1", "{1}{G}", "Enchantment Creature — Snake Druid",
          "Other enchantment creatures you control get +1/+1.\n{G}, {T}: Copy target activated or triggered ability you control from "
          "an enchantment source. You may choose new targets for the copy. (Mana abilities can't be targeted.)", ["G"],
          power="2", toughness="2"),
    _card("Abstruse Archaic", "W2", "{4}", "Creature — Avatar",
          "Vigilance\n{1}, {T}: Copy target activated or triggered ability you control from a colorless source. You may choose new "
          "targets for the copy. (Mana abilities can't be targeted.)", [], power="3", toughness="4"),
    _card("Angelic Chorus", "W3", "{3}{W}{W}", "Enchantment",
          "Whenever a creature you control enters, you gain life equal to its toughness.", ["W"]),
    _card("Ichor Wellspring", "W5", "{2}", "Artifact",
          "When this artifact enters or is put into a graveyard from the battlefield, draw a card.", []),
    _card("Furnace Brood", "W6", "{3}{R}", "Creature — Elemental", "{R}: Target creature can't be regenerated this turn.", ["R"],
          power="3", toughness="3"),
    _card("Drudge Skeletons", "W7", "{1}{B}", "Creature — Skeleton",
          "{B}: Regenerate this creature. (The next time this creature would be destroyed this turn, instead tap it, remove it from "
          "combat, and heal all damage on it.)", ["B"], power="1", toughness="1"),
    _card("Meek Attack", "W8", "{2}{R}", "Enchantment",
          "{1}{R}: You may put a creature card with total power and toughness 5 or less from your hand onto the battlefield. That "
          "creature gains haste. At the beginning of the next end step, sacrifice that creature.", ["R"]),
    _card("Purphoros, Bronze-Blooded", "W9", "{4}{R}", "Legendary Enchantment Creature — God",
          "Indestructible\nAs long as your devotion to red is less than five, Purphoros isn't a creature.\nOther creatures you control "
          "have haste.\n{2}{R}: You may put a red creature card or an artifact creature card from your hand onto the battlefield. "
          "Sacrifice it at the beginning of the next end step.", ["R"], power="7", toughness="6"),
    _card("Hill Giant", "W10", "{3}{R}", "Creature — Giant", "", ["R"], power="3", toughness="3"),
    _card("Field of Ruin", "W11", "", "Land",
          "{T}: Add {C}.\n{2}, {T}, Sacrifice this land: Destroy target nonbasic land an opponent controls. Each player searches their "
          "library for a basic land card, puts it onto the battlefield, then shuffles.", []),
    _card("Command Tower", "W12", "", "Land", "{T}: Add one mana of any color in your commander's color identity.", []),
    _card("Tree of Perdition", "W13", "{3}{B}", "Creature — Plant",
          "Defender\n{T}: Exchange target opponent's life total with this creature's toughness.", ["B"], power="0", toughness="13"),
    _card("Evra, Halcyon Witness", "W14", "{4}{W}{W}", "Legendary Creature — Avatar",
          "Lifelink\n{4}: Exchange your life total with Evra's power.", ["W"], power="4", toughness="4"),
    _card("Figure of Destiny", "W15", "{R/W}", "Creature — Kithkin",
          "{R/W}: This creature becomes a Kithkin Spirit with base power and toughness 2/2.\n{R/W}{R/W}{R/W}: If this creature is a "
          "Spirit, it becomes a Kithkin Spirit Warrior with base power and toughness 4/4.\n{R/W}{R/W}{R/W}{R/W}{R/W}{R/W}: If this "
          "creature is a Warrior, it becomes a Kithkin Spirit Warrior Avatar with base power and toughness 8/8, flying, and first "
          "strike.", ["R", "W"], power="1", toughness="1"),
    _card("Frostwielder", "W16", "{2}{R}{R}", "Creature — Human Shaman",
          "If a creature dealt damage by this creature this turn would die, exile it instead.\n{T}: This creature deals 1 damage to any "
          "target.", ["R"], power="1", toughness="2"),
    _card("Soul Warden", "W4", "{W}", "Creature — Human Cleric",
          "Whenever another creature enters, you gain 1 life.", ["W"], power="1", toughness="1"),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def table(cards, on_battlefield, hand, bob_on_battlefield=()):
    """Alice's main phase; ``on_battlefield`` was already there (not summoning sick)."""
    names = [*on_battlefield, *hand]
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob_on_battlefield), (10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    for n in on_battlefield:
        act(s, "p1", type="move", card_ids=[named(s, n).id], to={"player": "p1", "zone": "battlefield"})
    for n in bob_on_battlefield:
        act(s, "p2", type="move", card_ids=[named(s, n).id], to={"player": "p2", "zone": "battlefield"})
    turn_on(s)
    act(s, "p1", type="pass_priority")
    responsive(s)
    hold(s)
    for n in hand:
        to_hand(s, n)
    return s


def order_triggers(s):
    d = s.state.rules.decision
    assert d is not None and d.kind == "order"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])


def trigger_on_stack(s, source):
    return next(c for c, e in s.state.rules.stack.items() if e.kind == "trigger" and s.state.cards[e.source_card].name == source)


def test_copy_ability_from_an_enchantment_source(cards):
    """Weaver of Harmony copies Angelic Chorus's trigger (an enchantment source) with its event: the Bears' toughness twice (707.10b,
    603.2) — but not Soul Warden's trigger (a creature source: the target isn't legal) — and the new-targets rider is carried out."""
    s = table(cards, ["Weaver of Harmony", "Angelic Chorus", "Soul Warden"], ["Grizzly Bears"])
    assert all(coverage.of_card_data(cards.resolve(n)).level == "FULL" for n in ("Weaver of Harmony", "Abstruse Archaic"))
    pay(s, G=3)
    act(s, "p1", type="cast_spell", card_id=named(s, "Grizzly Bears").id)
    resolve_top(s)  # the Bears enter: Angelic Chorus and Soul Warden trigger
    order_triggers(s)
    weaver = named(s, "Weaver of Harmony")
    warden = trigger_on_stack(s, "Soul Warden")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=weaver.id, ability=1, targets=[warden])  # a creature source: not legal
    chorus = trigger_on_stack(s, "Angelic Chorus")
    act(s, "p1", type="activate_ability", card_id=weaver.id, ability=1, targets=[chorus])
    resolve_top(s)  # Weaver's ability: a copy of the Chorus trigger
    copy = next(c for c, e in s.state.rules.stack.items() if e.copy_of is not None)
    assert s.state.rules.stack[copy].source_card == s.state.rules.stack[chorus].source_card
    before = life(s, "p1")
    pass_until_stack_empty(s)
    assert life(s, "p1") == before + 2 + 2 + 1  # the Bears' toughness twice, and Soul Warden's 1
    replay_matches(s)
    assert on_stack(s) == []


def test_copy_ability_from_a_colorless_source(cards):
    """Abstruse Archaic copies the draw trigger of a colorless artifact (Ichor Wellspring)."""
    s = table(cards, ["Abstruse Archaic"], ["Ichor Wellspring"])
    pay(s, C=3)
    act(s, "p1", type="cast_spell", card_id=named(s, "Ichor Wellspring").id)
    resolve_top(s)  # the Wellspring enters: its trigger
    archaic = named(s, "Abstruse Archaic")
    act(s, "p1", type="activate_ability", card_id=archaic.id, ability=1, targets=[trigger_on_stack(s, "Ichor Wellspring")])
    hand = len(zone(s.state, "p1", "hand"))
    pass_until_stack_empty(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 2  # the trigger and its copy
    replay_matches(s)


@pytest.mark.parametrize("brood", [False, True])
def test_cant_be_regenerated_this_turn(cards, brood):
    """701.19c: with Furnace Brood's ability resolved, Drudge Skeletons' regeneration shield isn't applied to the lethal damage
    (state-based action, 704.5g); without it the shield saves the Skeletons. The restriction ends at cleanup (514.2)."""
    s = table(cards, ["Furnace Brood", "Drudge Skeletons"], ["Lightning Bolt"])
    skeletons = named(s, "Drudge Skeletons")
    pay(s, B=1)
    act(s, "p1", type="activate_ability", card_id=skeletons.id, ability=0)
    resolve_top(s)
    if brood:
        pay(s, R=1)
        act(s, "p1", type="activate_ability", card_id=named(s, "Furnace Brood").id, ability=0, targets=[skeletons.id])
        resolve_top(s)
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=named(s, "Lightning Bolt").id, targets=[skeletons.id])
    pass_until_stack_empty(s)
    assert s.state.cards[skeletons.id].zone == ("p1:graveyard" if brood else "p1:battlefield")
    replay_matches(s)


@pytest.mark.parametrize(("name", "cost", "offered"), [("Meek Attack", {"R": 2}, "Grizzly Bears"),
                                                       ("Purphoros, Bronze-Blooded", {"R": 3}, "Hill Giant")])
def test_put_from_hand_narrowed_by_the_wording(cards, name, cost, offered):
    """"… card with total power and toughness 5 or less" (Meek Attack: Bears 2+2, not the Giant's 3+3) and "a red creature card or an
    artifact creature card" (Purphoros: the Giant, not the green Bears): only those are offered; it's sacrificed at the next end step."""
    s = table(cards, [name], ["Grizzly Bears", "Hill Giant"])
    pay(s, **cost)
    act(s, "p1", type="activate_ability", card_id=named(s, name).id, ability=3 if name.startswith("Purph") else 0)
    resolve_top(s)
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options] == [offered]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert s.state.cards[named(s, offered).id].zone == "p1:battlefield"
    replay_matches(s)


def test_each_player_searches_for_a_basic_land(cards):
    """Field of Ruin: destroy a nonbasic land an opponent controls, then each player (not "may") searches for a basic land card, puts
    it onto the battlefield and shuffles (701.23, 101.4): the activator and the opponent each get one."""
    s = table(cards, ["Field of Ruin"], [], bob_on_battlefield=["Command Tower"])
    tower = named(s, "Command Tower")
    pay(s, C=2)
    act(s, "p1", type="activate_ability", card_id=named(s, "Field of Ruin").id, ability=1, targets=[tower.id])
    resolve_top(s)
    for _ in range(4):  # each searcher's private choice, the active player first
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert s.state.cards[tower.id].zone == "p2:graveyard"
    on = {p: sorted(s.state.cards[c].name for c in zone(s.state, p, "battlefield")) for p in ("p1", "p2")}
    assert on == {"p1": ["Forest"], "p2": ["Island"]}
    replay_matches(s)


def test_exchange_life_total_with_toughness_and_power(cards):
    """701.12g: the player gains or loses what it takes to equal the stat, and a layer 7b effect with no duration sets the stat to the
    life total they had: Tree of Perdition (target opponent: 40 -> 13, toughness 13 -> 40), Evra ("your": 40 -> 4, power 4 -> 40)."""
    s = table(cards, ["Tree of Perdition", "Evra, Halcyon Witness"], [])
    tree, evra = named(s, "Tree of Perdition"), named(s, "Evra, Halcyon Witness")
    act(s, "p1", type="activate_ability", card_id=tree.id, ability=1, targets=["p2"])
    pass_until_stack_empty(s)
    assert (life(s, "p1"), life(s, "p2")) == (40, 13)
    assert ch(s, tree).pt == (0, 40)
    pay(s, C=4)
    act(s, "p1", type="activate_ability", card_id=evra.id, ability=1)
    pass_until_stack_empty(s)
    assert life(s, "p1") == 4 and ch(s, evra).pt == (40, 4)
    replay_matches(s)


def test_level_up_creature_becomes_with_base_pt_and_keywords(cards):
    """Figure of Destiny: each step only applies if the creature is the previous type (the 8/8's "base power and toughness 8/8, flying,
    and first strike", 613.4b / 613.1d); out of order it does nothing."""
    s = table(cards, ["Figure of Destiny"], [])
    fig = named(s, "Figure of Destiny")
    pay(s, R=6)
    act(s, "p1", type="activate_ability", card_id=fig.id, ability=2)  # not a Warrior yet: nothing
    pass_until_stack_empty(s)
    assert ch(s, fig).pt == (1, 1)
    pay(s, R=4)
    for ability in (0, 1):
        act(s, "p1", type="activate_ability", card_id=fig.id, ability=ability)
        pass_until_stack_empty(s)
    assert ch(s, fig).pt == (4, 4) and "Warrior" in ch(s, fig).subtypes
    pay(s, R=6)
    act(s, "p1", type="activate_ability", card_id=fig.id, ability=2)
    pass_until_stack_empty(s)
    assert ch(s, fig).pt == (8, 8) and {"flying", "first strike"} <= ch(s, fig).keywords and "Avatar" in ch(s, fig).subtypes
    replay_matches(s)


@pytest.mark.parametrize("pinged", [True, False])
def test_creature_dealt_damage_by_this_creature_is_exiled(cards, pinged):
    """Frostwielder: a creature it dealt damage to this turn is exiled instead of dying (614.1a); the same creature dealt damage by
    another source only (Lightning Bolt, no ping) dies and goes to the graveyard."""
    s = table(cards, ["Frostwielder"], ["Lightning Bolt"], bob_on_battlefield=["Grizzly Bears"])
    bears = named(s, "Grizzly Bears")
    if pinged:
        act(s, "p1", type="activate_ability", card_id=named(s, "Frostwielder").id, ability=1, targets=[bears.id])
        pass_until_stack_empty(s)
    pay(s, R=1)
    act(s, "p1", type="cast_spell", card_id=named(s, "Lightning Bolt").id, targets=[bears.id])
    pass_until_stack_empty(s)
    assert s.state.cards[bears.id].zone == ("p2:exile" if pinged else "p2:graveyard")
    replay_matches(s)
