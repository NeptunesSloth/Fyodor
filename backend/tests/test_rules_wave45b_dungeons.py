"""Wave 45B: dungeons and the initiative (CR 2026-09-25). Real Oracle text (tests/fixtures/wave45b_dungeon_cards.json, from data/cards.sqlite); every
scenario checks the replay and a save and a load.

* 309.4c, 701.49: a venture moves the marker one room (the player chooses at a fork, 701.49b) and the room's ability triggers; the bottommost room
  completes the dungeon once its ability has left the stack (309.6, 309.7). Every room of the four dungeons is automated now: Undercity's Arena,
  "Goad target creature.", was the last one resolved by hand (goad, 701.15, is a combat requirement, 508.1d, since wave 3F).
* 726.2: whoever takes the initiative ventures into Undercity; creatures dealing combat damage to its holder take it (and venture).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.rules_state import DungeonMark
from app.rules import coverage
from app.rules.mana_units import visible_pool
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave30p_combat import attack, three, to_phase
from tests.wave9c_kit import build, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave45b_dungeon_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w45b", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def rules(s):
    return s.state.rules


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def drive(s, want=(), limit=150):
    """Resolve everything: a trigger order as offered, a choice with the next of ``want`` it offers (id or label start) else its first option,
    nobody blocks. A by-hand resolution fails the scenario."""
    for _ in range(limit):
        d = rules(s).decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, rules(s).priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        else:
            assert d.kind != "manual_resolution", d.prompt
            pick = next((o.id for w in want for o in d.options if o.id == w or o.label.startswith(w)), None)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never settled")


def test_the_undercity_and_initiative_cards_are_full():
    """The fifteen cards whose only gap was Undercity's Arena, Secret Door (which ventures into every dungeon) and the cards of the same family that
    wave 45B reads too: Loot Dispute, Undercellar Sweep, Sarevok's Tome, Undermountain Adventurer, Kick in the Door, You Find a Cursed Idol, Acererak the Archlich, Ellywick Tumblestrum, Keen-Eared Sentry."""
    assert len(DATA) == 25
    for c in DATA:
        assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", c["name"]


PATHS = [
    ("Lost Mine of Phandelver", ("Cave Entrance", "Goblin Lair", "Storeroom", "Temple of Dumathoin")),
    ("Lost Mine of Phandelver", ("Cave Entrance", "Mine Tunnels", "Fungi Cavern", "Temple of Dumathoin")),
    ("Lost Mine of Phandelver", ("Cave Entrance", "Goblin Lair", "Dark Pool", "Temple of Dumathoin")),
    ("Dungeon of the Mad Mage", ("Yawning Portal", "Dungeon Level", "Goblin Bazaar", "Lost Level", "Runestone Caverns", "Deep Mines",
                                 "Mad Wizard's Lair")),
    ("Dungeon of the Mad Mage", ("Yawning Portal", "Dungeon Level", "Twisted Caverns", "Lost Level", "Muiral's Graveyard", "Deep Mines",
                                 "Mad Wizard's Lair")),
    ("Tomb of Annihilation", ("Trapped Entry", "Veils of Fear", "Sandfall Cell", "Cradle of the Death God")),
    ("Tomb of Annihilation", ("Trapped Entry", "Oubliette", "Cradle of the Death God")),
    ("Undercity", ("Secret Entrance", "Forge", "Trap!", "Archives", "Throne of the Dead Three")),
    ("Undercity", ("Secret Entrance", "Lost Well", "Arena", "Catacombs", "Throne of the Dead Three")),
    ("Undercity", ("Secret Entrance", "Forge", "Arena", "Archives", "Throne of the Dead Three")),
    ("Undercity", ("Secret Entrance", "Lost Well", "Stash", "Catacombs", "Throne of the Dead Three")),
]


@pytest.mark.parametrize(("dungeon", "path"), PATHS, ids=[f"{d}:{p[1]}-{p[-2]}" for d, p in PATHS])
def test_a_venture_walks_a_path_to_completion_with_every_room_resolved(cards, dungeon, path):
    """Secret Door ({4}{U}: venture into the dungeon) once per room: the first chooses the dungeon (Undercity is entered only by the initiative,
    701.49d, 726.2: Goliath Paladin), each next one a room at a fork; every room ability resolves with no by-hand step, and the bottommost room
    completes the dungeon (309.6, 309.7: it is Alice's, and the marker is gone)."""
    s = build(cards, ["Secret Door"] * 3 + ["Grizzly Bears", "Goliath Paladin"], ["Grizzly Bears"])
    for c in [c for c in s.state.cards.values() if c.name in ("Secret Door", "Grizzly Bears")]:
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "battlefield"})
    season(s)
    for i, room in enumerate(path):
        if i == 0 and dungeon == "Undercity":
            mana(s, "p1", W=1, C=4)
            act(s, "p1", type="cast_spell", card_id=to_hand(s, "Goliath Paladin").id)
        else:
            door = next(c for c in s.state.cards.values() if c.name == "Secret Door" and c.zone == "p1:battlefield")
            mana(s, "p1", U=1, C=4)
            act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
        drive(s, want=([dungeon] if i == 0 else [room]))
        if room != path[-1]:
            assert rules(s).dungeons["p1"].dungeon == dungeon and rules(s).dungeons["p1"].room == room
    assert "p1" not in rules(s).dungeons and rules(s).completed_dungeons["p1"] == [dungeon]
    check(s)


def season(s):
    """The cards put onto the battlefield by hand have been there since before the turn."""
    for c in s.state.cards.values():
        if c.zone.endswith(":battlefield"):
            rules(s).controlled_since[c.id].turn = 0


def test_undercity_arena_goads_a_creature_until_alices_next_turn(cards):
    """Undercity, Arena: "Goad target creature." Alice (who owns the dungeon and controls the room ability) goads Bob's Bears; on Bob's turn it must
    attack, and not Alice (701.15b-c: a player other than the goading player, if able) -- Carol."""
    s = three(cards, ["Goliath Paladin"], ["Grizzly Bears"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    season(s)
    rules(s).dungeons["p1"] = DungeonMark(dungeon="Undercity", room="Lost Well")  # (a venture away from Arena)
    mana(s, "p1", W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Goliath Paladin").id)
    drive(s, want=["Arena", bears.id])  # she takes the initiative, so she ventures into Undercity: to Arena, then its target
    assert s.state.table.initiative == "p1" and rules(s).dungeons["p1"].room == "Arena"
    assert ch(s, bears).imposed >= {"goaded:p1"}
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError, match="attacks each combat if able"):
        act(s, "p2", type="declare_attackers", attackers=[])
    with pytest.raises(ActionError, match="other than Alice"):
        attack(s, (bears, "p1"), pid="p2")
    attack(s, (bears, "p3"), pid="p2")
    check(s)


def test_combat_damage_to_the_initiative_holder_takes_it_and_ventures_into_undercity(cards):
    """726.2: Alice takes the initiative with Avenging Hunter and ventures (Secret Entrance); Bob's unblocked Bears deal combat damage to her, so he
    takes it and ventures into Undercity himself -- his own Secret Entrance, Alice's marker unmoved."""
    s = build(cards, ["Avenging Hunter"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    season(s)
    mana(s, "p1", G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Avenging Hunter").id)
    drive(s, want=["Forest"])
    assert s.state.table.initiative == "p1" and rules(s).dungeons["p1"].room == "Secret Entrance"
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (bears, "p1"), pid="p2")
    drive(s, want=["Forest"])
    assert s.state.players["p1"].life == 38 and s.state.table.initiative == "p2"
    assert rules(s).dungeons["p2"].dungeon == "Undercity" and rules(s).dungeons["p2"].room == "Secret Entrance"
    assert rules(s).dungeons["p1"].room == "Secret Entrance"
    check(s)


@pytest.mark.parametrize("name", [c["name"] for c in DATA[:15] if c["name"] != "Dungeoneer's Pack"])
def test_each_initiative_card_takes_the_initiative_and_ventures_into_undercity_when_it_is_cast(cards, name):
    """The fifteen real cards of the cluster (Dungeoneer's Pack is below): cast, "you take the initiative" (726.2) ventures into Undercity, Secret
    Entrance fetches a Forest."""
    s = build(cards, [name])
    mana(s, "p1", W=1, U=1, B=1, R=1, G=1, C=6)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, name).id)
    drive(s, want=["Forest"])
    assert s.state.table.initiative == "p1" and rules(s).dungeons["p1"].room == "Secret Entrance"
    assert any(c.zone == "p1:hand" and c.name == "Forest" for c in s.state.cards.values())  # (the room's basic land card)
    check(s)


def test_dungeoneers_pack_enters_tapped_and_its_sacrifice_takes_the_initiative(cards):
    """"This artifact enters tapped. {2}, {T}, Sacrifice this artifact: You take the initiative, gain 3 life, draw a card, and create a Treasure token.
    Activate only as a sorcery." -- untapped by hand for the activation, since it enters tapped."""
    s = build(cards, ["Dungeoneer's Pack"])
    mana(s, "p1", C=3)
    pack = to_hand(s, "Dungeoneer's Pack")
    act(s, "p1", type="cast_spell", card_id=pack.id)
    drive(s)
    assert s.state.cards[pack.id].zone == "p1:battlefield" and s.state.cards[pack.id].tapped
    act(s, "p1", type="tap", card_ids=[pack.id], tapped=False)
    index = next(ab.index for ab in ch(s, pack).abilities if ab.kind == "activated")
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=pack.id, ability=index)
    drive(s, want=["Forest"])
    assert s.state.table.initiative == "p1" and s.state.players["p1"].life == 43 and len(treasures(s)) == 1
    assert s.state.cards[pack.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize(("name", "after"), [("Feywild Caretaker", lambda s: [c for c in s.state.cards.values()
                                                                              if c.name == "Faerie Dragon" and c.zone == "p1:battlefield"]),
                                             ("Passageway Seer", lambda s: [c for c in s.state.cards.values()
                                                                            if c.name == "Passageway Seer" and c.counters.get("+1/+1") == 1])])
def test_the_end_step_ability_of_an_initiative_creature_checks_that_you_have_it(cards, name, after):
    """"At the beginning of your end step, if you have the initiative, …" (Feywild Caretaker: a 1/1 Faerie Dragon with flying; Passageway Seer: a
    +1/+1 counter): 603.4 -- the holder's end step."""
    s = build(cards, [name])
    mana(s, "p1", W=1, U=1, B=1, R=1, G=1, C=6)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, name).id)
    drive(s, want=["Forest"])
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")  # (her end step passes on the way)
    assert s.state.table.initiative == "p1" and len(after(s)) == 1
    check(s)


def two_bears(s, pid="p1"):
    """Move the player's two Grizzly Bears onto the battlefield (they have been there since before the turn)."""
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == pid]
    for c in bears:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    season(s)
    return bears


def mana_ability(s, c):
    """(the ability index, the mana ability) of the card's only mana ability."""
    from app.rules.casting import mana_abilities

    ((index, ab),) = mana_abilities(s.state, s.state.cards[c.id], s.cards)
    return index, ab


def treasures(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == f"{pid}:battlefield"]


def test_loot_dispute_makes_a_treasure_only_for_an_attack_on_the_player_with_the_initiative(cards):
    """508.3a, 726.1: "Whenever you attack the player who has the initiative, create a Treasure token." Bob has it; one Bears attacks Bob, the other
    Carol: one Treasure. Its combat damage to Bob then takes the initiative from him (726.2)."""
    s = three(cards, ["Loot Dispute", "Grizzly Bears", "Grizzly Bears"])
    put(s, "Loot Dispute")
    first, second = two_bears(s)
    act(s, "p2", type="set_initiative", player="p2")  # (by hand: no venture)
    to_phase(s, "declare_attackers", turn=1)
    attack(s, (first, "p2"), (second, "p3"))
    drive(s, want=["Forest"])
    assert len(treasures(s)) == 1
    assert s.state.table.initiative == "p1" and rules(s).dungeons["p1"].room == "Secret Entrance"
    check(s)


def test_loot_dispute_does_not_trigger_for_an_attack_on_a_player_without_it(cards):
    s = three(cards, ["Loot Dispute", "Grizzly Bears", "Grizzly Bears"])
    put(s, "Loot Dispute")
    first, _ = two_bears(s)
    act(s, "p3", type="set_initiative", player="p3")
    to_phase(s, "declare_attackers", turn=1)
    attack(s, (first, "p2"))
    drive(s)
    assert not treasures(s) and s.state.table.initiative == "p3"
    check(s)


@pytest.mark.parametrize(("holder", "soldiers"), [(None, 0), ("p3", 0), ("p2", 2), ("p1", 2)])
def test_undercellar_sweep_needs_the_initiative_for_you_or_the_player_you_attack(cards, holder, soldiers):
    """"Whenever you attack, if you or a player you're attacking has the initiative, you create two 1/1 white Soldier creature tokens that are
    tapped and attacking." Alice attacks Bob: she or Bob has it (two Soldiers), Carol has it or nobody does (none)."""
    s = three(cards, ["Undercellar Sweep", "Grizzly Bears", "Grizzly Bears"])
    put(s, "Undercellar Sweep")
    first, _ = two_bears(s)
    if holder:
        act(s, holder, type="set_initiative", player=holder)
    to_phase(s, "declare_attackers", turn=1)
    attack(s, (first, "p2"))
    drive(s, want=["p2", "Forest"])
    made = [c for c in s.state.cards.values() if c.name == "Soldier" and c.zone == "p1:battlefield"]
    assert len(made) == soldiers
    assert all(c.tapped and c.attacking is not None or s.state.turn.phase != "declare_attackers" for c in made)
    check(s)


def test_sarevok_tome_adds_two_with_the_initiative(cards):
    """"{T}: Add {C}. If you have the initiative, add {C}{C} instead." (605.3a: checked as the mana ability resolves)."""
    s = build(cards, ["Sarevok's Tome"])
    tome = put(s, "Sarevok's Tome")
    index, ab = mana_ability(s, tome)
    assert ab.options == (("C",),)
    act(s, "p1", type="set_initiative", player="p1")
    assert mana_ability(s, tome)[1].options == (("C", "C"),)
    act(s, "p1", type="activate_ability", card_id=tome.id, ability=index)
    assert dict(visible_pool(s.state, "p1")) == {"C": 2}
    check(s)


def test_undermountain_adventurer_adds_six_once_a_dungeon_is_completed(cards):
    """"{T}: Add {G}{G}. If you've completed a dungeon, add six {G} instead." -- completed by Secret Door through Lost Mine of Phandelver (Cave
    Entrance, Goblin Lair, Storeroom, Temple of Dumathoin)."""
    s = build(cards, ["Undermountain Adventurer", "Secret Door"])
    adventurer, door = put(s, "Undermountain Adventurer"), put(s, "Secret Door")
    season(s)
    assert mana_ability(s, adventurer)[1].options == (("G", "G"),)
    for room in ("Lost Mine of Phandelver", "Goblin Lair", "Storeroom", "Temple of Dumathoin"):
        mana(s, "p1", U=1, C=4)
        act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
        drive(s, want=[room])
    assert rules(s).completed_dungeons["p1"] == ["Lost Mine of Phandelver"]
    assert mana_ability(s, adventurer)[1].options == (("G",) * 6,)
    act(s, "p1", type="activate_ability", card_id=adventurer.id, ability=mana_ability(s, adventurer)[0])
    assert dict(visible_pool(s.state, "p1")).get("G") == 6
    check(s)


def test_kick_in_the_door_a_counter_haste_no_wall_can_block_and_a_venture(cards):
    """"Put a +1/+1 counter on target creature. That creature gains haste until end of turn and can't be blocked by Walls this turn. Venture into
    the dungeon." Bob's Wall (Secret Door) may not block the hasty Bears, his Bears may."""
    from tests.test_rules_wave30p_combat import block

    s = build(cards, ["Kick in the Door", "Grizzly Bears"], ["Secret Door", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")  # (summoning sick: haste is what lets it attack)
    wall, blocker = put(s, "Secret Door", "p2"), put(s, "Grizzly Bears", "p2")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Kick in the Door").id, targets=[bears.id])
    drive(s, want=["Lost Mine of Phandelver"])
    assert s.state.cards[bears.id].counters.get("+1/+1") == 1 and "haste" in ch(s, bears).keywords
    assert rules(s).dungeons["p1"].room == "Cave Entrance"
    to_phase(s, "declare_attackers", turn=1)
    attack(s, (bears, "p2"))
    for _ in range(12):
        if (d := rules(s).decision) is not None and d.kind == "declare_blockers":
            break
        act(s, rules(s).priority, type="pass_priority")
    with pytest.raises(ActionError, match="can't be blocked"):
        block(s, "p2", (wall, bears))
    block(s, "p2", (blocker, bears))
    check(s)


def test_acererak_returns_to_hand_and_ventures_until_tomb_of_annihilation_is_completed(cards):
    """"When Acererak enters, if you haven't completed Tomb of Annihilation, return Acererak to its owner's hand and venture into the dungeon."
    (603.4: checked as it triggers and as it resolves.) Cast the first time it bounces and ventures; with Tomb completed it stays."""
    s = build(cards, ["Acererak the Archlich"])
    acererak = to_hand(s, "Acererak the Archlich")
    mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=acererak.id)
    drive(s, want=["Tomb of Annihilation"])
    assert s.state.cards[acererak.id].zone == "p1:hand" and rules(s).dungeons["p1"].dungeon == "Tomb of Annihilation"
    rules(s).completed_dungeons["p1"] = ["Tomb of Annihilation"]  # (by hand: completed since)
    mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=acererak.id)
    drive(s)
    assert s.state.cards[acererak.id].zone == "p1:battlefield"
    check(s)


@pytest.mark.parametrize(("bob_pays", "zombies"), [(True, 1), (False, 2)])
def test_acererak_attacks_a_zombie_for_each_opponent_who_does_not_sacrifice_a_creature(cards, bob_pays, zombies):
    """"Whenever Acererak attacks, for each opponent, you create a 2/2 black Zombie creature token unless that player sacrifices a creature of their
    choice." (118.12a) Carol has no creature to sacrifice, so she never pays; Bob sacrifices his Bears or doesn't."""
    s = three(cards, ["Acererak the Archlich"], ["Grizzly Bears"])
    acererak = put(s, "Acererak the Archlich")
    bears = put(s, "Grizzly Bears", "p2")
    season(s)
    to_phase(s, "declare_attackers", turn=1)
    attack(s, (acererak, "p2"))
    drive(s, want=["pay" if bob_pays else "decline"])
    assert len([c for c in s.state.cards.values() if c.name == "Zombie" and c.zone == "p1:battlefield"]) == zombies
    assert (s.state.cards[bears.id].zone == "p2:graveyard") == bob_pays
    check(s)


def test_keen_eared_sentry_lets_an_opponent_venture_once_each_turn(cards):
    """"Each opponent can't venture into the dungeon more than once each turn." (101.2) Alice ventures twice with Secret Door in her turn: only the
    first moves her marker; in her next turn she may venture again."""
    s = build(cards, ["Secret Door"], ["Keen-Eared Sentry"])
    door = put(s, "Secret Door")
    put(s, "Keen-Eared Sentry", "p2")
    season(s)
    for room in ("Lost Mine of Phandelver", "Mine Tunnels"):
        mana(s, "p1", U=1, C=4)
        act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
        drive(s, want=[room])
    assert rules(s).dungeons["p1"].room == "Cave Entrance"  # (the second venture did nothing)
    to_phase(s, "main1", turn=3)
    mana(s, "p1", U=1, C=4)
    act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
    drive(s, want=["Mine Tunnels"])
    assert rules(s).dungeons["p1"].room == "Mine Tunnels"
    check(s)


def test_ellywicks_emblem_counts_the_differently_named_dungeons_you_completed(cards):
    """Ellywick Tumblestrum's -7: "Creatures you control have trample and haste and get +2/+2 for each differently named dungeon you've completed."
    (The ruling: it counts every one completed, before or after the emblem.) Lost Mine of Phandelver is completed through Secret Door after it."""
    s = build(cards, ["Ellywick Tumblestrum", "Grizzly Bears", "Secret Door"])
    walker, bears, door = put(s, "Ellywick Tumblestrum"), put(s, "Grizzly Bears"), put(s, "Secret Door")
    season(s)
    act(s, "p1", type="counter", card_ids=[walker.id], kind="loyalty", delta=7 - s.state.cards[walker.id].counters.get("loyalty", 0))
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=2)
    drive(s)
    assert {"trample", "haste"} <= ch(s, bears).keywords and ch(s, bears).pt == (2, 2)  # (none completed yet)
    for room in ("Lost Mine of Phandelver", "Goblin Lair", "Storeroom", "Temple of Dumathoin"):
        mana(s, "p1", U=1, C=4)
        act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
        drive(s, want=[room, bears.id])
    assert rules(s).completed_dungeons["p1"] == ["Lost Mine of Phandelver"]
    assert ch(s, bears).pt == (5, 5)  # +2/+2 and the Storeroom's +1/+1 counter (it targets the Bears)
    check(s)


def test_you_find_a_cursed_idol_steal_its_eyes_makes_a_treasure_and_ventures(cards):
    """"• Steal Its Eyes — Create a Treasure token and venture into the dungeon." (the third mode)."""
    s = build(cards, ["You Find a Cursed Idol"])
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "You Find a Cursed Idol").id, modes=[2])
    drive(s, want=["Dungeon of the Mad Mage"])
    assert len(treasures(s)) == 1 and rules(s).dungeons["p1"].room == "Yawning Portal"
    check(s)
