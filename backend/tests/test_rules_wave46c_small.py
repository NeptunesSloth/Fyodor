"""Wave 46C: single-wording gaps of cards played in many decks (CR 2026-09-25), real Oracle text (tests/fixtures/wave46c_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 613.1b, 303.4e: "You control enchanted enchantment." (Steal Enchantment [6463]) - an Aura on a permanent of another type than a creature already took control;
  the enchantment it enchants is the host.
* 506.3, 508.1b: "Exile target creature that's attacking you or a planeswalker you control." (Soul Snare [6643]) - an attacker's target is the player or a planeswalker
  (a battle or another player's planeswalker is no target of it).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.mana_units import visible_pool
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of
from tests.wave43b_kit import ch, on_top
from tests.wave46c_kit import FULL, cast, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def controller(s, c):
    return s.state.cards[c.id].controller


def walker(s, pid="p1", loyalty=5):
    act(s, pid, type="create_token", player=pid, token={"name": "Walker", "type_line": "Token Legendary Planeswalker — Test"})
    w = card_named(s, "Walker", pid)
    act(s, pid, type="counter", card_ids=[w.id], kind="loyalty", delta=loyalty)
    return w


def test_steal_enchantment_takes_control_of_the_enchantment_it_enchants(cards):
    s = build(cards, ["Steal Enchantment"], ["Ghostly Prison"])
    prison = put(s, "Ghostly Prison", "p2")
    to_hand(s, "Steal Enchantment")
    mana(s, U=2, C=2)
    cast(s, "Steal Enchantment", targets=[prison.id])
    assert controller(s, prison) == "p1"  # 613.1b: layer 2
    check(s)


def attack_at(s, attacker, target):
    """Bob's declare attackers step (turn 2), this attacker declared at that target."""
    stops(s)
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": target}])
    act(s, "p2", type="pass_priority")  # (the active player first, then Alice has priority)


def test_soul_snare_exiles_a_creature_attacking_a_planeswalker_you_control(cards):
    s = build(cards, ["Soul Snare"], ["Grizzly Bears"])
    snare = put(s, "Soul Snare")
    bears = put(s, "Grizzly Bears", "p2")
    w = walker(s)
    attack_at(s, bears, w.id)
    mana(s, W=1)
    activate(s, "p1", snare, targets=[bears.id])
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile" and zone_of(s, "Soul Snare") == "p1:graveyard"
    check(s)


def test_soul_snare_exiles_a_creature_attacking_you(cards):
    s = build(cards, ["Soul Snare"], ["Grizzly Bears"])
    snare = put(s, "Soul Snare")
    bears = put(s, "Grizzly Bears", "p2")
    attack_at(s, bears, "p1")
    mana(s, W=1)
    activate(s, "p1", snare, targets=[bears.id])
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile"
    check(s)


def test_soul_snare_cannot_target_a_creature_attacking_the_opponent(cards):
    s = build(cards, ["Soul Snare", "Hill Giant"], [])
    snare, giant = put(s, "Soul Snare"), put(s, "Hill Giant")
    stops(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p2"}])
    mana(s, W=1)
    with pytest.raises(ActionError):
        activate(s, "p1", snare, targets=[giant.id])  # it attacks Bob, not Alice or a planeswalker of hers
    check(s)


def equip_to(s, equipment, creature, pid="p1"):
    index = next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[equipment.id]).abilities if "equip" in a.keywords)
    act(s, pid, type="activate_ability", card_id=equipment.id, ability=index, targets=[creature.id])
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")


def attached_to(s, equipment):
    return s.state.cards[equipment.id].attached_to


def test_helitrooper_makes_equip_abilities_that_target_it_cost_less_but_not_others(cards):
    # 601.2c, 601.2f: Loxodon Warhammer's Equip {3} costs {2} less when it targets Helitrooper ("Equip abilities you activate that target this creature")
    s = build(cards, ["Helitrooper", "Hill Giant", "Loxodon Warhammer"], [])
    trooper, giant, hammer = put(s, "Helitrooper"), put(s, "Hill Giant"), put(s, "Loxodon Warhammer")
    mana(s, C=1)
    with pytest.raises(ActionError):
        equip_to(s, hammer, giant)  # the Giant is not the Helitrooper: {3}
    equip_to(s, hammer, trooper)
    assert attached_to(s, hammer) == trooper.id and visible_pool(s.state, "p1").get("C", 0) == 0
    check(s)


def cast_with(s, name, picks, pid="p1"):
    """Cast the creature and answer the target choice of its enters ability with these cards."""
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[c.id for c in picks])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def counters(s, c, kind):
    return s.state.cards[c.id].counters.get(kind, 0)


def test_blightbeetle_bars_plus_one_counters_on_the_opponents_creatures_only(cards):
    # 614.17: "Creatures your opponents control can't have +1/+1 counters put on them." - Alice's creatures get none, Bob's own can, and -1/-1 counters are another kind
    s = build(cards, ["Rishkar, Peema Renegade", "Hill Giant", "Skinrender", "Shivan Dragon"], ["Blightbeetle", "Grizzly Bears"])
    giant, bears, dragon = put(s, "Hill Giant"), put(s, "Grizzly Bears", "p2"), put(s, "Shivan Dragon")
    put(s, "Blightbeetle", "p2")
    to_hand(s, "Rishkar, Peema Renegade")
    mana(s, G=1, C=2)
    cast_with(s, "Rishkar, Peema Renegade", [giant, bears])
    assert counters(s, giant, "+1/+1") == 0 and counters(s, bears, "+1/+1") == 1  # Alice's creatures are barred, Bob's isn't
    to_hand(s, "Skinrender")
    mana(s, B=2, C=2)
    cast_with(s, "Skinrender", [dragon])
    assert counters(s, dragon, "-1/-1") == 3  # another kind of counter
    check(s)


def test_darksteel_angel_bars_minus_one_counters_on_its_controllers_creatures(cards):
    s = build(cards, ["Darksteel Angel", "Hill Giant", "Skinrender"], ["Skinrender", "Shivan Dragon"])
    giant, dragon = put(s, "Hill Giant"), put(s, "Shivan Dragon", "p2")
    put(s, "Darksteel Angel")
    to_hand(s, "Skinrender")
    mana(s, B=2, C=2)
    cast_with(s, "Skinrender", [dragon])
    assert counters(s, dragon, "-1/-1") == 3  # Bob's creature is not "a creature you control" of Alice
    to_hand(s, "Skinrender", "p2")
    stops(s)
    to_phase(s, "main1", turn=2)
    mana(s, "p2", B=2, C=2)
    cast_with(s, "Skinrender", [giant], "p2")
    assert counters(s, giant, "-1/-1") == 0  # 614.17: they can't be put on Alice's creature
    check(s)


def test_monastery_siege_taxes_spells_that_target_its_controller_or_their_permanents(cards):
    # 601.2c, 601.2f: Dragons - "Spells your opponents cast that target you or a permanent you control cost {2} more to cast."
    s = build(cards, ["Monastery Siege", "Hill Giant"], ["Shock", "Lightning Bolt", "Grizzly Bears"])
    giant, bears = put(s, "Hill Giant"), put(s, "Grizzly Bears", "p2")
    to_hand(s, "Monastery Siege")
    to_hand(s, "Shock", "p2")
    to_hand(s, "Lightning Bolt", "p2")
    mana(s, U=1, C=2)
    mana(s, "p2", R=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Monastery Siege").id)
    act(s, "p2", type="pass_priority")  # (he holds instants: the Siege resolves once he passes)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "Dragons" in o.label)])
    settle(s)
    stops(s)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=[bears.id])  # his own creature: {R}
    settle(s)
    assert visible_pool(s.state, "p2").get("R", 0) == 1
    act(s, "p1", type="pass_priority")  # (Bob has priority again)
    for target in ("p1", giant.id):
        with pytest.raises(ActionError, match="Not enough mana to pay"):
            act(s, "p2", type="cast_spell", card_id=card_named(s, "Shock", "p2").id, targets=[target])  # {R} is not enough: {2}{R}
    mana(s, "p2", C=2)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Shock", "p2").id, targets=["p1"])
    settle(s)
    assert s.state.players["p1"].life == 38 and visible_pool(s.state, "p2").get("R", 0) == 0
    check(s)


def on_table(s, zone, pid, name):
    return [s.state.cards[c] for c in s.state.zones.get(f"{pid}:{zone}", []) if s.state.cards[c].name == name]


def test_thran_spider_makes_a_tapped_powerstone_for_you_and_the_target_opponent(cards):
    # 608.2c: "you and target opponent each create a tapped Powerstone token" - each of them creates their own token
    s = build(cards, ["Thran Spider"], [])
    to_hand(s, "Thran Spider")
    mana(s, C=3)
    cast(s, "Thran Spider")
    mine, theirs = on_table(s, "battlefield", "p1", "Powerstone"), on_table(s, "battlefield", "p2", "Powerstone")
    assert len(mine) == 1 and len(theirs) == 1 and mine[0].tapped and theirs[0].tapped
    check(s)


def test_oath_of_the_grey_host_chapter_one_makes_a_food_for_each(cards):
    s = build(cards, ["Oath of the Grey Host"], [])
    to_hand(s, "Oath of the Grey Host")
    mana(s, B=1, C=3)
    cast(s, "Oath of the Grey Host")
    assert len(on_table(s, "battlefield", "p1", "Food")) == 1 and len(on_table(s, "battlefield", "p2", "Food")) == 1
    check(s)


def test_ox_drover_gives_the_opponent_an_ox_and_draws_you_a_card(cards):
    s = build(cards, ["Ox Drover"], [])
    to_hand(s, "Ox Drover")
    mana(s, W=1, C=3)
    before = len(s.state.zones["p1:library"])
    cast(s, "Ox Drover")
    assert len(on_table(s, "battlefield", "p2", "Ox")) == 1 and not on_table(s, "battlefield", "p1", "Ox")
    assert len(s.state.zones["p1:library"]) == before - 1  # you draw a card
    check(s)


def test_marina_vendrells_grimoire_keeps_its_controller_in_the_game_at_zero_life_until_it_leaves(cards):
    # 704.5a, 104.3b: "You don't lose the game for having 0 or less life." - checked as a state-based action, so when the Grimoire is gone the player loses at once
    s = build(cards, ["Marina Vendrell's Grimoire", "Shock"], [])
    grimoire = put(s, "Marina Vendrell's Grimoire")
    for cid in s.state.zones["p1:library"][:6]:  # (cards to discard to the Grimoire's "whenever you lose life")
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "hand"})
    to_hand(s, "Shock")
    act(s, "p1", type="life", player="p1", delta=-38)  # 2 left
    mana(s, R=1)
    cast(s, "Shock", targets=["p1"])
    assert s.state.players["p1"].life == 0 and s.state.rules.winner is None
    act(s, "p1", type="move", card_ids=[grimoire.id], to={"zone": "graveyard"})
    act(s, "p1", type="pass_priority")  # (the state-based actions are checked before anyone gets priority)
    assert s.state.rules.winner == "p2"
    check(s)


def test_gideon_blackblade_is_a_creature_only_during_its_controllers_turn(cards):
    # 613.1d, 613.4b, 205.1b: "During your turn, ~ is a 4/4 Human Soldier creature with indestructible that's still a planeswalker."
    s = build(cards, ["Gideon Blackblade"], [])
    gideon = put(s, "Gideon Blackblade")
    mine = ch(s, gideon)
    assert {"Creature", "Planeswalker"} <= set(mine.types) and {"Human", "Soldier"} <= set(mine.subtypes)
    assert pt(s, "Gideon Blackblade") == (4, 4) and "indestructible" in mine.keywords
    stops(s)
    to_phase(s, "upkeep", turn=2)
    theirs = ch(s, gideon)
    assert "Creature" not in theirs.types and "Planeswalker" in theirs.types and "Soldier" not in theirs.subtypes
    check(s)


def test_aggressive_mining_bars_its_controller_from_playing_lands_but_not_the_opponent(cards):
    # 305.1: "You can't play lands." - only the controller of the enchantment
    s = build(cards, ["Aggressive Mining"], [])
    put(s, "Aggressive Mining")
    land = to_hand(s, "Forest")
    with pytest.raises(ActionError, match="you can't play lands"):
        act(s, "p1", type="play_land", card_id=land.id)
    stops(s)
    to_phase(s, "main1", turn=2)
    theirs = to_hand(s, "Island", "p2")
    act(s, "p2", type="play_land", card_id=theirs.id)
    assert zone_of(s, "Island", "p2") == "p2:battlefield"
    check(s)


def test_besmirch_steals_untaps_hastes_and_goads_until_the_turn_ends(cards):
    # 611.2, 701.15a: "Until end of turn, gain control of target creature and it gains haste. Untap and goad that creature." - the control ends at the cleanup step, the goad lasts
    from app.rules.keyword_actions import goaded_by

    s = build(cards, ["Besmirch"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    act(s, "p2", type="tap", card_ids=[giant.id], tapped=True)
    to_hand(s, "Besmirch")
    mana(s, R=2, C=1)
    cast(s, "Besmirch", targets=[giant.id])
    now = s.state.cards[giant.id]
    assert now.controller == "p1" and not now.tapped and "haste" in ch(s, giant).keywords and goaded_by(ch(s, giant)) == {"p1"}
    stops(s)
    for _ in range(40):  # (goaded and hasty, it must attack: Bob, the only player but Alice)
        d = s.state.rules.decision
        if s.state.turn.number == 2 and s.state.turn.phase == "upkeep":
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p2"}])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[giant.id].controller == "p2" and goaded_by(ch(s, giant)) == {"p1"}  # back to Bob, still goaded until Alice's next turn
    check(s)


def test_a_token_with_vanishing_enters_with_its_time_counters(cards):
    # 702.63a: "create a 1/1 white Human Noble creature token with vanishing 3" (The Girl in the Fireplace, chapter I) - three time counters as it enters
    s = build(cards, ["The Girl in the Fireplace"], [])
    to_hand(s, "The Girl in the Fireplace")
    mana(s, W=1, C=2)
    cast(s, "The Girl in the Fireplace")
    noble = card_named(s, "Human Noble")
    assert noble.is_token and s.state.cards[noble.id].counters.get("time") == 3 and zone_of(s, "Human Noble") == "p1:battlefield"
    check(s)


def test_fire_nation_attacks_makes_soldiers_that_add_red_mana_when_they_attack(cards):
    # 702.189a: a token "with firebending 1" - "Whenever this creature attacks, add {R}. This mana lasts until end of combat."
    s = build(cards, ["Fire Nation Attacks"], [])
    to_hand(s, "Fire Nation Attacks")
    mana(s, R=1, C=4)
    cast(s, "Fire Nation Attacks")
    soldiers = [c for c in s.state.cards.values() if c.name == "Soldier" and c.owner == "p1"]
    assert len(soldiers) == 2
    stops(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in soldiers])
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert visible_pool(s.state, "p1").get("R", 0) == 2  # one {R} for each attacking Soldier
    check(s)


def test_ominous_cemetery_shuffles_the_creature_into_its_owners_library(cards):
    # 701.24a: "Target creature's owner shuffles it into their library." - the owner's library, not the activator's
    s = build(cards, ["Ominous Cemetery"], ["Hill Giant"])
    cemetery, giant = put(s, "Ominous Cemetery"), put(s, "Hill Giant", "p2")
    mana(s, C=5)
    activate(s, "p1", cemetery, "Exile", targets=[giant.id])
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert zone_of(s, "Hill Giant", "p2") == "p2:library" and zone_of(s, "Ominous Cemetery") == "p1:exile"
    check(s)


def test_bounty_agent_destroys_a_legendary_creature_but_cannot_target_a_nonlegendary_one(cards):
    # 115.1, 205.4: "Destroy target legendary permanent that's an artifact, creature, or enchantment." - legendary AND one of the three types
    s = build(cards, ["Bounty Agent"], ["Hill Giant"])
    agent = put(s, "Bounty Agent")
    giant = put(s, "Hill Giant", "p2")
    act(s, "p2", type="create_token", player="p2", token={"name": "Hero", "type_line": "Token Legendary Creature — Human", "power": "2", "toughness": "2"})
    hero = card_named(s, "Hero", "p2")
    stops(s)
    to_phase(s, "main1", turn=3)
    with pytest.raises(ActionError):
        activate(s, "p1", agent, targets=[giant.id])  # not legendary
    activate(s, "p1", agent, targets=[hero.id])
    for _ in range(6):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert zone_of(s, "Bounty Agent") == "p1:graveyard" and hero.id not in s.state.zones.get("p2:battlefield", [])
    check(s)


def logged(s, since):
    return [" ".join(p.t or "" for p in e.parts) for e in s.state.log[since:]]


def test_polymorph_replaces_the_creature_with_the_first_creature_of_its_controllers_library_and_shuffles(cards):
    # 701.20b, 701.24a: "Its controller reveals cards from the top of their library until they reveal a creature card. The player puts that card onto the battlefield,
    # then shuffles all other cards revealed this way into their library." - Bob's library, Bob's creature (under his control)
    s = build(cards, ["Polymorph", "Shivan Dragon"], ["Hill Giant", "Shivan Dragon"])
    giant = put(s, "Hill Giant", "p2")
    on_top(s, "Shivan Dragon", "p2")
    to_hand(s, "Polymorph")
    mana(s, U=1, C=3)
    since = len(s.state.log)
    cast(s, "Polymorph", targets=[giant.id])
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard" and zone_of(s, "Shivan Dragon", "p2") == "p2:battlefield"
    assert s.state.cards[card_named(s, "Shivan Dragon", "p2").id].controller == "p2"
    assert any("shuffled" in t for t in logged(s, since)) and zone_of(s, "Shivan Dragon", "p1") == "p1:library"
    check(s)


def test_polymorph_without_a_creature_in_the_library_still_shuffles_it(cards):
    s = build(cards, ["Polymorph"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    to_hand(s, "Polymorph")
    mana(s, U=1, C=3)
    since = len(s.state.log)
    cast(s, "Polymorph", targets=[giant.id])
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard" and not [c for c in s.state.zones["p2:battlefield"]]
    assert len(s.state.zones["p2:library"]) == 10 and any("Bob" in t and "shuffled" in t for t in logged(s, since))  # the whole library was revealed, then shuffled
    check(s)


def test_transmogrify_exiles_the_creature_and_puts_the_first_creature_of_its_controllers_library_onto_the_battlefield(cards):
    s = build(cards, ["Transmogrify"], ["Hill Giant", "Shivan Dragon"])
    giant = put(s, "Hill Giant", "p2")
    on_top(s, "Shivan Dragon", "p2")
    to_hand(s, "Transmogrify")
    mana(s, R=1, C=3)
    cast(s, "Transmogrify", targets=[giant.id])
    assert zone_of(s, "Hill Giant", "p2") == "p2:exile" and zone_of(s, "Shivan Dragon", "p2") == "p2:battlefield"
    check(s)


def test_sirens_ruse_draws_only_when_the_blinked_creature_was_a_pirate(cards):
    # 608.2h: "If a Pirate was exiled this way" - the creature as it last existed; it came back as a new object (400.7)
    s = build(cards, ["Siren's Ruse", "Swab Goblin", "Hill Giant"], [])
    goblin, giant = put(s, "Swab Goblin"), put(s, "Hill Giant")
    to_hand(s, "Siren's Ruse")
    mana(s, U=1, C=1)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Siren's Ruse", targets=[giant.id])
    assert len(s.state.zones["p1:hand"]) == hand - 1  # no draw: Siren's Ruse left the hand, the Giant is no Pirate
    assert len(on_table(s, "battlefield", "p1", "Hill Giant")) == 1
    to_hand(s, "Siren's Ruse")
    mana(s, U=1, C=1)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Siren's Ruse", targets=[goblin.id])
    assert len(s.state.zones["p1:hand"]) == hand  # the Pirate: one card drawn
    assert len(on_table(s, "battlefield", "p1", "Swab Goblin")) == 1
    check(s)


def equip_on_bobs_turn(s, hammer, target):
    """Bob's upkeep (turn 2), Bob passes: Alice has priority and equips."""
    stops(s)
    to_phase(s, "upkeep", turn=2)
    act(s, "p2", type="pass_priority")
    mana(s, C=3)
    equip_to(s, hammer, target)


def test_leonin_shikari_lets_equip_abilities_be_activated_at_instant_speed(cards):
    # 702.6a, 702.6: the sorcery timing of equip is lifted by "You may activate equip abilities any time you could cast an instant."
    s = build(cards, ["Leonin Shikari", "Hill Giant", "Loxodon Warhammer"], [])
    put(s, "Leonin Shikari")
    giant, hammer = put(s, "Hill Giant"), put(s, "Loxodon Warhammer")
    equip_on_bobs_turn(s, hammer, giant)
    assert attached_to(s, hammer) == giant.id
    check(s)


def test_equip_stays_a_sorcery_speed_ability_without_leonin_shikari(cards):
    s = build(cards, ["Hill Giant", "Loxodon Warhammer"], [])
    giant, hammer = put(s, "Hill Giant"), put(s, "Loxodon Warhammer")
    with pytest.raises(ActionError):
        equip_on_bobs_turn(s, hammer, giant)  # 702.6a: only as a sorcery
    check(s)


def test_bladegraft_aspirant_reduces_the_activated_abilities_of_equipment_that_target_it(cards):
    s = build(cards, ["Bladegraft Aspirant", "Loxodon Warhammer"], [])
    aspirant, hammer = put(s, "Bladegraft Aspirant"), put(s, "Loxodon Warhammer")
    mana(s, C=2)
    equip_to(s, hammer, aspirant)  # {3} less {1}
    assert attached_to(s, hammer) == aspirant.id
    check(s)
