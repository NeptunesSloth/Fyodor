"""Review 34 (head): falsifying the cards waves 35C, 35D, 36A and 36B made FULL (CR 2026-09-25). Real Oracle text
(tests/fixtures/review34_cards.json, from data/cards.sqlite); every scenario checks the replay and a save and a load.

* 310.5, 508.5: "Whenever a creature attacks one of your opponents or a planeswalker an opponent controls" (Gahiji, Honored One) and "Whenever one or
  more creatures attack one of your opponents or a planeswalker they control" (Frontier Warmonger) triggered for a creature attacking a battle (its
  controller read as the player attacked): a battle is neither a player nor a planeswalker. Same for "attacks you or a planeswalker you control".
* 514.3a: a trigger of the cleanup step (Rielle, the Everwise's ruling: the first discard of the turn is the discard to hand size) went on the stack in
  the next turn and no second cleanup step followed, so the player kept the cards drawn over their maximum hand size. Now the players get priority in
  the cleanup step when a state-based action is performed or a trigger waits, and another cleanup step follows.
* 406.3a, 708.2: "as long as you own a card in exile that has an Adventure" (Howling Galefang) read the printing of a card exiled face down: wrong (it
  has no characteristics) and it told the table what the hidden card was.
* Pinned as correct: Maha's base toughness under counters and a later setter (its rulings); Divine Visitation's Angels tapped and attacking (its
  ruling); Worship against commander damage and lifelink (its rulings); Phytohydra against deathtouch and lifelink (614.6); Kitt Kanto on another
  player's turn; Gahiji and Frontier Warmonger with three players (the ruling: creatures attacking another opponent); Deflecting Swat on an
  activated ability and keeping an illegal target (115.7d); Aven Warcraft without threshold; Oculus Whelp dying with the transformed permanent (its
  ruling); Lizard, Connors's Curse taking the artifact type (205.1a).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import counters, until
from tests.test_rules_wave30o_layers import to_phase
from tests.test_rules_wave34b_activated import ability, ask, priority_to, stops
from tests.wave9c_kit import build, check, life, mana, pt, put, reloaded, to_hand
from tests.wave35c_kit import alive

DATA = json.loads((Path(__file__).parent / "fixtures" / "review34_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="r34", number=f"R{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
SIEGE = "Invasion of Zendikar // Awakened Skyclave"


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def seasoned(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


def responses(s):
    for p in s.state.players:
        act(s, p, type="set_prefs", response="on")


def drive(s, pick=None, limit=60):
    """Resolve everything; a decision is answered by ``pick`` (an id, or None for its first options); nobody blocks."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            choice = pick(d) if pick is not None else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[choice] if choice else [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never settled")


def bobs_attack(s, plan):
    responses(s)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    to_phase(s, "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in plan])


def three(cards, mine, bobs):
    a = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (9, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [*bobs, (10, "Island")])
    c = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b), PlayerSetup("Carol", cards=c)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    return s


# -- 310.5 / 508.5: an attack on a battle is on no player and no planeswalker -----------------------------------------------------------------
def test_gahiji_and_frontier_warmonger_ignore_an_attack_on_a_battle(cards):
    """Bob attacks his own Siege (Alice protects it): no opponent of Alice and no planeswalker is attacked, so neither trigger."""
    s = build(cards, ["Gahiji, Honored One", "Frontier Warmonger"], [SIEGE, "Walking Corpse"])
    put(s, "Gahiji, Honored One")
    put(s, "Frontier Warmonger")
    corpse = put(s, "Walking Corpse", "p2")
    siege = put(s, SIEGE, "p2")
    act(s, "p2", type="counter", card_ids=[siege.id], kind="defense", delta=4)
    drive(s, lambda d: "p1" if "p1" in [o.id for o in d.options] else None)
    seasoned(s, corpse)
    s = reloaded(s)
    bobs_attack(s, [(corpse, siege.id)])
    assert s.state.rules.protectors[s.state.rules.object_id(siege.id)] == "p1" and not s.state.zones.get("stack")
    drive(s)
    assert ch(s, corpse).pt == (2, 2) and "menace" not in ch(s, corpse).keywords
    check(s)


def test_gahiji_and_frontier_warmonger_with_three_players(cards):
    """The rulings: a creature an opponent controls attacking another opponent counts; one attacking you doesn't (each its own creature)."""
    s = three(cards, ["Gahiji, Honored One", "Frontier Warmonger"], [(2, "Walking Corpse")])
    put(s, "Gahiji, Honored One")
    put(s, "Frontier Warmonger")
    a, b = [c for c in s.state.cards.values() if c.name == "Walking Corpse"]
    act(s, "p2", type="move", card_ids=[a.id, b.id], to={"player": "p2", "zone": "battlefield"})
    seasoned(s, a, b)
    bobs_attack(s, [(a, "p3"), (b, "p1")])
    drive(s)
    assert ch(s, a).pt == (4, 2) and "menace" in ch(s, a).keywords
    assert ch(s, b).pt == (2, 2) and "menace" not in ch(s, b).keywords
    check(s)


# -- 514.3a: a trigger in the cleanup step, then another cleanup step ---------------------------------------------------------------------
def test_rielle_draws_after_the_discard_to_hand_size_and_another_cleanup_step_follows(cards):
    """Rielle's ruling: the first discard of the turn is the one to hand size: Alice (nine cards) discards two, Rielle draws two in that cleanup
    step, and a new cleanup step makes her discard two again (no trigger the second time). She ends the turn with seven cards."""
    s = build(cards, ["Rielle, the Everwise"], [], forests=30)
    put(s, "Rielle, the Everwise")
    hand = len(s.state.zones["p1:hand"])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][: 9 - hand]
    act(s, "p1", type="move", card_ids=[c.id for c in forests], to={"zone": "hand"})
    library = len(s.state.zones["p1:library"])
    discards = 0
    for _ in range(200):
        if s.state.turn.number == 2:
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and "maximum hand size" in d.prompt:
            discards += 1
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])
            if discards == 1:
                assert s.state.turn.phase == "cleanup" and s.state.turn.number == 1
                s = reloaded(s)
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert discards == 2 and len(s.state.zones["p1:hand"]) == 7 and len(s.state.zones["p1:library"]) == library - 2
    assert len(s.state.zones["p1:graveyard"]) == 4 and not s.state.rules.cleanup_again
    check(s)


def test_an_old_save_has_no_second_cleanup_pending():
    from app.game.rules_state import RulesState

    assert RulesState.model_validate({}).cleanup_again is False


# -- 406.3a: a face-down card in exile has no Adventure -----------------------------------------------------------------------------------
def test_howling_galefang_ignores_an_adventure_card_exiled_face_down(cards):
    s = build(cards, ["Howling Galefang", "Bonecrusher Giant // Stomp"], [])
    fang = put(s, "Howling Galefang")
    giant = next(c for c in s.state.cards.values() if c.name.startswith("Bonecrusher") and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[giant.id], to={"player": "p1", "zone": "exile"}, face_down=True, face_down_kind="exile")
    assert s.state.cards[giant.id].face_down and "haste" not in ch(s, fang).keywords
    s = reloaded(s)
    act(s, "p1", type="face_down", card_ids=[giant.id], face_down=False)
    assert "haste" in ch(s, fang).keywords  # face up: it has an Adventure
    check(s)


# -- pinned as correct ----------------------------------------------------------------------------------------------------------------------
def test_maha_sets_base_toughness_under_counters_and_a_later_setter_wins(cards):
    s = build(cards, ["Maha, Its Feathers Night", "Turn to Frog"], ["Grizzly Bears"])
    put(s, "Maha, Its Feathers Night")
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    assert pt(s, "Grizzly Bears", "p2") == (3, 2)
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Turn to Frog").id, targets=[bears.id])
    drive(s)
    assert pt(s, "Grizzly Bears", "p2") == (2, 2)  # 1/1 set later (613.7: timestamp), the counter on top
    check(s)


def test_divine_visitation_angels_enter_tapped_and_attacking(cards):
    s = build(cards, ["Divine Visitation", "Hero of Bladehold"], [])
    put(s, "Divine Visitation")
    hero = put(s, "Hero of Bladehold")
    seasoned(s, hero)
    responses(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hero.id, "target": "p2"}])
    drive(s)
    angels = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.token is not None]
    assert len(angels) == 2 and all(a.name == "Angel" and a.tapped and a.attacking is not None and ch(s, a).pt == (4, 4) for a in angels)
    check(s)


def test_worship_keeps_one_life_but_commander_damage_and_lifelink_count_it_all(cards):
    s = build(cards, ["Worship", "Grizzly Bears"], [])
    put(s, "Worship")
    put(s, "Grizzly Bears")
    atraxa = next(c for c in s.state.cards.values() if c.name == "Atraxa, Praetors' Voice")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"player": "p2", "zone": "battlefield"})
    seasoned(s, atraxa)
    act(s, "p1", type="commander_damage", player="p1", commander=atraxa.commander_key, delta=18, affect_life=False)
    bob = life(s, "p2")
    bobs_attack(s, [(atraxa, "p1")])
    for _ in range(60):
        if not alive(s) or s.state.turn.phase == "main2":
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, "p1", type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert life(s) == 36 and life(s, "p2") == bob + 4 and not alive(s)  # (no floor needed: 22 commander damage, 903.10a)
    check(s)


def test_phytohydra_takes_counters_from_a_deathtouch_lifelink_blocker(cards):
    s = build(cards, ["Phytohydra"], [])
    hydra = put(s, "Phytohydra")
    atraxa = next(c for c in s.state.cards.values() if c.name == "Atraxa, Praetors' Voice")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"player": "p2", "zone": "battlefield"})
    seasoned(s, atraxa, hydra)
    bob = life(s, "p2")
    responses(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hydra.id, "target": "p2"}])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": atraxa.id, "attacker_id": hydra.id}])
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.cards[hydra.id].zone == "p1:battlefield" and counters(s, hydra) == 4 and life(s, "p2") == bob  # 614.6: never dealt
    check(s)


def test_kitt_kanto_on_bobs_turn_pumps_and_goads_bobs_creature(cards):
    s = build(cards, ["Kitt Kanto, Mayhem Diva", "Grizzly Bears"], ["Walking Corpse"])
    responses(s)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    put(s, "Kitt Kanto, Mayhem Diva")
    drive(s)
    put(s, "Grizzly Bears")
    corpse = put(s, "Walking Corpse", "p2")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "begin_combat")
    drive(s, lambda d: corpse.id if corpse.id in [o.id for o in d.options] else None)
    assert pt(s, "Walking Corpse", "p2") == (4, 4) and "trample" in ch(s, corpse).keywords
    check(s)


def test_deflecting_swat_redirects_an_activated_ability(cards):
    s = build(cards, ["Deflecting Swat"], ["Prodigal Pyromancer"])
    stops(s)
    pyro = put(s, "Prodigal Pyromancer", "p2")
    to_phase(s, "main1", turn=2)
    seasoned(s, pyro)
    act(s, "p2", type="activate_ability", card_id=pyro.id, ability=ability(s, "Prodigal Pyromancer", "p2"), targets=["p1"])
    priority_to(s, "p1")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Deflecting Swat").id, targets=[s.state.zones["stack"][-1]])
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    alice, bob = life(s), life(s, "p2")
    drive(s)
    assert life(s) == alice and life(s, "p2") == bob - 1
    check(s)


def test_deflecting_swat_keeps_an_illegal_target_and_changes_the_other(cards):
    """115.7d: the Bears gained hexproof (illegal for Bob's Twinstrike) and stay its target; the Elves' place goes to Bob's Corpse."""
    s = build(cards, ["Deflecting Swat", "Grizzly Bears", "Llanowar Elves", "Blossoming Defense"], ["Twinstrike", "Walking Corpse"])
    stops(s)
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    corpse = put(s, "Walking Corpse", "p2")
    to_phase(s, "main1", turn=2)
    strike = to_hand(s, "Twinstrike", "p2")
    mana(s, "p2", R=1, B=1, C=3)
    act(s, "p2", type="cast_spell", card_id=strike.id, targets=[bears.id, elves.id], target_counts=[2])
    priority_to(s, "p1")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Blossoming Defense").id, targets=[bears.id])
    for _ in range(6):
        if len(s.state.zones["stack"]) == 1:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    priority_to(s, "p1")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Deflecting Swat").id, targets=[strike.id])
    drive(s, lambda d: "keep" if "(1 of 2)" in d.prompt else corpse.id if "(2 of 2)" in d.prompt else None)
    assert s.state.cards[corpse.id].zone == "p2:graveyard" and s.state.cards[bears.id].damage == 0 and s.state.cards[elves.id].damage == 0
    check(s)


def test_aven_warcraft_without_threshold_gives_no_protection(cards):
    s = build(cards, ["Aven Warcraft", "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Aven Warcraft").id)
    drive(s)
    assert pt(s, "Grizzly Bears") == (2, 4) and not any("rotection" in a.text for a in ch(s, bears).abilities)
    check(s)


def test_oculus_whelp_draws_when_it_dies_with_the_transformed_permanent(cards):
    s = build(cards, ["Oculus Whelp", "Delver of Secrets // Insectile Aberration", "Wrath of God"], [])
    put(s, "Oculus Whelp")
    delver = put(s, "Delver of Secrets // Insectile Aberration")
    act(s, "p1", type="set_face", card_id=delver.id, face=1)
    wrath = to_hand(s, "Wrath of God")
    hand = len(s.state.zones["p1:hand"])
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    drive(s)
    assert len(s.state.zones["p1:hand"]) == hand  # Wrath cast, one card drawn (603.10a: the ability as it was)
    check(s)


def test_lizard_makes_an_artifact_creature_a_green_lizard_creature_only(cards):
    s = build(cards, ["Lizard, Connors's Curse"], ["Ornithopter"])
    orn = put(s, "Ornithopter", "p2")
    mana(s, G=2, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lizard, Connors's Curse").id)
    drive(s, lambda d: orn.id if orn.id in [o.id for o in d.options] else None)
    c = ch(s, orn)
    assert c.pt == (4, 4) and c.types == frozenset({"Creature"}) and "Lizard" in c.subtypes and "flying" not in c.keywords
    check(s)
