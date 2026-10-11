"""Wave 34B: activated abilities whose effect, cost or timing wasn't read (CR 2026-09-25), real Oracle text
(tests/fixtures/wave34b_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 602.2: an ability is announced, its targets chosen, then its costs paid (601.2c-h); a cost that can't be paid in full can't be paid at all
  (118.3), so the activation is refused and nothing is spent. 602.5: a restriction ("only as a sorcery", Boast) is checked before it begins.
* "Exile Mangara and target permanent." / "Destroy this creature and target creature it's blocking." (Wall of Vipers: any player may activate it,
  602.2a) / "Exile this creature and target creature without flying that's attacking you.": the source is no target (115.1); both leave together.
* 301.5, 303.4: "Destroy all Auras attached to Hakim." and the cost "Sacrifice an Equipment attached to Ronin" (the cost can be paid only with what is
  attached to the source; 701.21a).
* "Each opponent with no cards in hand loses 10 life." / "Each player with exactly 13 life loses the game" (Tinybones, Triskaidekaphobia): "with" is "who has".
* 702.3b / 510.1a: "gets +1/+0, gains "…", and can attack as though it didn't have defender" (The Pride of Hull Clade), "gains haste, can attack as though
  it didn't have defender, and assigns combat damage equal to its toughness rather than its power" (Walking Bulwark: only as a sorcery), Roving Keep.
* 608.2d: "You may have Arni's base power become …" is asked as the (Boast) ability resolves. 605.3b: "If you control another Mutant, you gain 1 life." is part
  of the mana ability's own resolution.
* 608.2c: "Then if your library has no cards in it, you win the game." (Doctor Doom), Gandalf's owner shuffles him and draws, Red Death's "You add {R}" and "that
  player" (the goaded creature's controller).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave34b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w34b", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, answer="yes", limit=60):
    """Resolve everything; an optional ability is answered ``answer``, any other choice with its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer] if answer in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_phase(s, phase, turn=None, limit=200):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase}")


def next_turn(s):
    """To the main phase of Alice's next turn: what was put onto the table before has been there since the turn began (no summoning sickness)."""
    to_phase(s, "main1", turn=s.state.turn.number + 2)


def stops(s):
    """Both players get priority at every step (a combat trick can be played)."""
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")


def attack(s, *attackers):
    """Alice attacks Bob with these creatures; stops with the attack declared."""
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])


def ability(s, name, pid="p1", contains=""):
    """The index of the first activated (or mana) ability of this card whose text contains ``contains``."""
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id])
    return next(a.index for a in ch.abilities if a.kind in ("activated", "mana", "loyalty") and contains in a.text)


def activate(s, pid, c, contains="", **kw):
    act(s, pid, type="activate_ability", card_id=c.id, ability=ability(s, c.name, c.owner, contains), **kw)


def attach(s, aura, host, pid="p1"):
    act(s, pid, type="attach", card_ids=[aura.id], to=host.id)


def ask(s, limit=40):
    """Pass priority until a decision is asked (returned)."""
    for _ in range(limit):
        if s.state.rules.decision is not None:
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("nothing was asked")


def priority_to(s, pid, limit=20):
    for _ in range(limit):
        if s.state.rules.priority == pid and s.state.rules.decision is None:
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"{pid} never got priority")


def test_the_wordings_are_covered(cards):
    for name in ("Mangara of Corondor", "Giant Trap Door Spider", "Hunting Kavu", "Wall of Vipers", "Hakim, Loreweaver", "Ronin, Shadow Stalker",
                 "Tinybones, Trinket Thief", "The Pride of Hull Clade", "Walking Bulwark", "Roving Keep", "Gandalf, Wandering Wizard",
                 "Arni Brokenbrow", "Black Tom Cassidy", "Avid Reclaimer", "Doctor Doom, Unrivaled", "Red Death, Shipwrecker",
                 "Triskaidekaphobia", "Dalek Drone", "Suspended Sentence", "Shackles of Treachery", "Jace, Wielder of Mysteries",
                 "Kellan, Planar Trailblazer", "Vhati il-Dal", "Mannichi, the Fevered Dream", "Glass-Cast Heart", "Brotherhood Headquarters",
                 "Master's Guide-Mural // Master's Manufactory", "Wishmonger", "Pale Wayfarer",
                 "Balthor the Defiled", "Twilight's Call", "Roar of Reclamation", "Empty the Catacombs"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# -- Mangara of Corondor: "{T}: Exile Mangara and target permanent." ---------------------------------------------------------------------
def test_mangara_exiles_itself_and_the_target_together(cards):
    s = build(cards, ["Mangara of Corondor"], ["Hill Giant"])
    mangara = put(s, "Mangara of Corondor")
    giant = put(s, "Hill Giant", "p2")
    next_turn(s)
    activate(s, "p1", mangara, targets=[giant.id])
    settle(s)
    assert zone_of(s, "Mangara of Corondor") == "p1:exile" and zone_of(s, "Hill Giant", "p2") == "p2:exile"
    check(s)


def test_mangara_cannot_be_activated_while_tapped_and_pays_nothing(cards):
    s = build(cards, ["Mangara of Corondor"], ["Hill Giant"])
    mangara = put(s, "Mangara of Corondor")
    giant = put(s, "Hill Giant", "p2")
    next_turn(s)
    act(s, "p1", type="tap", card_ids=[mangara.id], tapped=True)
    with pytest.raises(ActionError):
        activate(s, "p1", mangara, targets=[giant.id])  # 118.3: the {T} can't be paid
    assert zone_of(s, "Mangara of Corondor") == "p1:battlefield" and zone_of(s, "Hill Giant", "p2") == "p2:battlefield" and not s.state.zones.get("stack")
    check(s)


def block(s, *pairs):
    """Bob blocks (blocker, attacker) pairs once he is asked."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": a.id} for b, a in pairs])
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked to block")


# -- Wall of Vipers: "{3}: Destroy this creature and target creature it's blocking. Any player may activate this ability." -------------
def test_wall_of_vipers_any_player_destroys_it_and_the_creature_it_blocks(cards):
    s = build(cards, ["Hill Giant"], ["Wall of Vipers"])
    giant = put(s, "Hill Giant")
    wall = put(s, "Wall of Vipers", "p2")
    stops(s)
    next_turn(s)
    attack(s, giant)
    block(s, (wall, giant))
    priority_to(s, "p1")
    mana(s, C=3)
    activate(s, "p1", wall, targets=[giant.id])  # Alice, not its controller, activates it (602.2a)
    settle(s)
    assert zone_of(s, "Wall of Vipers", "p2") == "p2:graveyard" and zone_of(s, "Hill Giant") == "p1:graveyard"
    check(s)


def test_wall_of_vipers_needs_a_creature_it_is_blocking(cards):
    s = build(cards, ["Hill Giant"], ["Wall of Vipers"])
    giant = put(s, "Hill Giant")
    wall = put(s, "Wall of Vipers", "p2")
    next_turn(s)
    mana(s, "p2", C=3)
    with pytest.raises(ActionError):
        activate(s, "p2", wall, targets=[giant.id])  # not blocking anything: no legal target (115.1)
    assert zone_of(s, "Wall of Vipers", "p2") == "p2:battlefield"
    check(s)


# -- Giant Trap Door Spider: "{1}{R}{G}, {T}: Exile this creature and target creature without flying that's attacking you." -------------
def spider_table(cards, attacker):
    s = build(cards, [attacker], ["Giant Trap Door Spider"])
    t = put(s, attacker)
    spider = put(s, "Giant Trap Door Spider", "p2")
    stops(s)
    next_turn(s)
    attack(s, t)
    block(s)
    priority_to(s, "p2")
    mana(s, "p2", R=1, G=1, C=1)
    return s, t, spider


def test_the_spider_and_the_attacker_without_flying_are_exiled(cards):
    s, giant, spider = spider_table(cards, "Hill Giant")
    activate(s, "p2", spider, targets=[giant.id])
    settle(s)
    assert zone_of(s, "Giant Trap Door Spider", "p2") == "p2:exile" and zone_of(s, "Hill Giant") == "p1:exile"
    assert life(s, "p2") == 40  # (the Giant never got to deal its damage)
    check(s)


def test_the_spider_cannot_exile_a_flier_or_pay_while_tapped(cards):
    s, raptor, spider = spider_table(cards, "Cloudfin Raptor")
    with pytest.raises(ActionError):
        activate(s, "p2", spider, targets=[raptor.id])  # "without flying"
    act(s, "p2", type="tap", card_ids=[spider.id], tapped=True)
    with pytest.raises(ActionError):
        activate(s, "p2", spider, targets=[raptor.id])  # {T} can't be paid (118.3)
    assert zone_of(s, "Giant Trap Door Spider", "p2") == "p2:battlefield" and zone_of(s, "Cloudfin Raptor") == "p1:battlefield"
    check(s)


# -- Hakim: "{U}{U}, {T}: Destroy all Auras attached to Hakim." ------------------------------------------------------------------------
def test_hakim_destroys_only_the_auras_attached_to_him(cards):
    s = build(cards, ["Hakim, Loreweaver", "Pacifism", "Pacifism", "Grizzly Bears"])
    hakim, bears = put(s, "Hakim, Loreweaver"), put(s, "Grizzly Bears")
    on_hakim = put(s, "Pacifism")
    on_bears = next(c for c in s.state.cards.values() if c.name == "Pacifism" and c.owner == "p1" and c.id != on_hakim.id)
    act(s, "p1", type="move", card_ids=[on_bears.id], to={"player": "p1", "zone": "battlefield"})
    attach(s, on_hakim, hakim)
    attach(s, on_bears, bears)
    next_turn(s)
    mana(s, U=2)
    activate(s, "p1", hakim, "Destroy all Auras")
    settle(s)
    assert s.state.cards[on_hakim.id].zone == "p1:graveyard"
    assert s.state.cards[on_bears.id].zone == "p1:battlefield" and s.state.cards[on_bears.id].attached_to == bears.id
    check(s)


# -- Ronin: "{T}, Sacrifice an Equipment attached to Ronin: Target creature gets -4/-4 until end of turn. Activate only as a sorcery." ---
def ronin_table(cards):
    s = build(cards, ["Ronin, Shadow Stalker", "Bonesplitter", "Hill Giant"], ["Hill Giant"])
    ronin, bonesplitter, mine = put(s, "Ronin, Shadow Stalker"), put(s, "Bonesplitter"), put(s, "Hill Giant")
    theirs = put(s, "Hill Giant", "p2")
    return s, ronin, bonesplitter, mine, theirs


def test_ronin_sacrifices_the_equipment_attached_to_him(cards):
    s, ronin, bonesplitter, _, theirs = ronin_table(cards)
    attach(s, bonesplitter, ronin)
    next_turn(s)
    activate(s, "p1", ronin, "Sacrifice an Equipment", targets=[theirs.id])
    settle(s)
    assert s.state.cards[bonesplitter.id].zone == "p1:graveyard"  # sacrificed as a cost (701.21a)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard"  # -4/-4 on a 3/3
    check(s)


def test_ronin_cannot_pay_with_an_equipment_attached_to_another_creature_or_at_instant_speed(cards):
    s, ronin, bonesplitter, mine, theirs = ronin_table(cards)
    attach(s, bonesplitter, mine)
    next_turn(s)
    with pytest.raises(ActionError):
        activate(s, "p1", ronin, "Sacrifice an Equipment", targets=[theirs.id])  # 118.3: not attached to Ronin
    assert not s.state.cards[ronin.id].tapped and s.state.cards[bonesplitter.id].zone == "p1:battlefield"
    attach(s, bonesplitter, ronin)
    stops(s)
    to_phase(s, "begin_combat")
    with pytest.raises(ActionError, match="sorcery"):
        activate(s, "p1", ronin, "Sacrifice an Equipment", targets=[theirs.id])  # 602.5d: "Activate only as a sorcery"
    assert s.state.cards[bonesplitter.id].zone == "p1:battlefield"
    check(s)


# -- Tinybones, Trinket Thief: "{4}{B}{B}: Each opponent with no cards in hand loses 10 life." -------------------------------------------
def test_tinybones_only_hurts_an_opponent_with_an_empty_hand(cards):
    s = build(cards, ["Tinybones, Trinket Thief"], ["Hill Giant"])
    tinybones = put(s, "Tinybones, Trinket Thief")
    empty = [c for c in s.state.zones["p2:hand"]]
    if empty:
        act(s, "p2", type="move", card_ids=empty, to={"player": "p2", "zone": "library"}, position="top")
    mana(s, B=2, C=4)
    activate(s, "p1", tinybones, "loses 10 life")
    settle(s)
    assert life(s, "p2") == 30  # no cards in hand
    to_hand(s, "Hill Giant", "p2")
    mana(s, B=2, C=4)
    activate(s, "p1", tinybones, "loses 10 life")
    settle(s)
    assert life(s, "p2") == 30  # a card in hand: not "an opponent with no cards in hand"
    check(s)


# -- The Pride of Hull Clade: "… gets +1/+0, gains "Whenever this creature deals combat damage to a player, draw cards equal to its toughness," and can attack
# as though it didn't have defender." ------------------------------------------------------------------------------------------------------
def test_a_defender_cannot_attack_until_the_pride_of_hull_clade_lets_it(cards):
    s = build(cards, ["The Pride of Hull Clade", "Hill Giant"], forests=40)
    pride = put(s, "The Pride of Hull Clade")
    put(s, "Hill Giant")
    next_turn(s)
    to_phase(s, "declare_attackers")
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": pride.id, "target": "p2"}])  # defender (702.3b)
    check(s)


def test_the_pride_of_hull_clade_attacks_and_draws_cards_equal_to_its_toughness(cards):
    s = build(cards, ["The Pride of Hull Clade"], forests=40)
    pride = put(s, "The Pride of Hull Clade")
    next_turn(s)
    mana(s, U=2, C=2)
    activate(s, "p1", pride, targets=[pride.id])
    settle(s)
    assert pt(s, "The Pride of Hull Clade") == (3, 15)
    hand = len(s.state.zones["p1:hand"])
    attack(s, pride)
    settle(s)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 3
    assert len(s.state.zones["p1:hand"]) == hand + 15  # "draw cards equal to its toughness" (the granted triggered ability)
    check(s)


# -- Walking Bulwark: "{2}: Until end of turn, target creature with defender gains haste, can attack as though it didn't have defender, and assigns combat
# damage equal to its toughness rather than its power. Activate only as a sorcery." --------------------------------------------------------
def test_walking_bulwark_attacks_and_assigns_damage_by_toughness(cards):
    s = build(cards, ["Walking Bulwark"])
    bulwark = put(s, "Walking Bulwark")
    next_turn(s)
    mana(s, C=2)
    activate(s, "p1", bulwark, targets=[bulwark.id])
    settle(s)
    attack(s, bulwark)
    settle(s)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 3  # 510.1a: its toughness, not its 0 power
    check(s)


def test_walking_bulwark_is_only_a_sorcery(cards):
    s = build(cards, ["Walking Bulwark"])
    bulwark = put(s, "Walking Bulwark")
    stops(s)
    next_turn(s)
    to_phase(s, "begin_combat")
    mana(s, C=2)
    with pytest.raises(ActionError, match="sorcery"):
        activate(s, "p1", bulwark, targets=[bulwark.id])  # 602.5d
    check(s)


# -- Roving Keep: "{7}: This creature gets +2/+0 and gains trample until end of turn. It can attack this turn as though it didn't have defender." -----
def test_roving_keep_gets_bigger_and_may_attack(cards):
    s = build(cards, ["Roving Keep"])
    keep = put(s, "Roving Keep")
    next_turn(s)
    mana(s, C=7)
    activate(s, "p1", keep)
    settle(s)
    assert pt(s, "Roving Keep") == (7, 7)
    attack(s, keep)
    settle(s)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 7
    check(s)


# -- Gandalf, Wandering Wizard: "{6}: Gandalf's owner shuffles him into their library and draws three cards." ----------------------------
def test_gandalf_goes_into_the_library_and_his_owner_draws_three(cards):
    s = build(cards, ["Gandalf, Wandering Wizard"], forests=30)
    gandalf = put(s, "Gandalf, Wandering Wizard")
    hand, library = len(s.state.zones["p1:hand"]), len(s.state.zones["p1:library"])
    mana(s, C=6)
    activate(s, "p1", gandalf, "shuffles")
    settle(s)
    assert zone_of(s, "Gandalf, Wandering Wizard") == "p1:library"
    assert len(s.state.zones["p1:hand"]) == hand + 3 and len(s.state.zones["p1:library"]) == library + 1 - 3
    check(s)


# -- Arni Brokenbrow: "Boast — {1}: You may have Arni's base power become 1 plus the greatest power among other creatures you control until end of turn." ---
def arni_table(cards):
    s = build(cards, ["Arni Brokenbrow", "Hill Giant"])
    arni, _ = put(s, "Arni Brokenbrow"), put(s, "Hill Giant")
    stops(s)
    next_turn(s)
    return s, arni


def test_arni_is_asked_as_the_boast_resolves_and_takes_the_greatest_power(cards):
    s, arni = arni_table(cards)
    attack(s, arni)
    mana(s, C=1)
    activate(s, "p1", arni)
    d = ask(s)
    assert d.kind == "confirm" and {o.id for o in d.options} == {"yes", "no"} and d.player == "p1"  # 608.2d: asked on resolution
    assert pt(s, "Arni Brokenbrow") == (3, 3)  # nothing yet
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s)
    assert pt(s, "Arni Brokenbrow") == (4, 3)  # 1 plus the Hill Giant's 3
    mana(s, C=1)
    with pytest.raises(ActionError):
        activate(s, "p1", arni)  # Boast: only once each turn (702.142a)
    check(s)


def test_arni_may_decline(cards):
    s, arni = arni_table(cards)
    attack(s, arni)
    mana(s, C=1)
    activate(s, "p1", arni)
    settle(s, "no")
    assert pt(s, "Arni Brokenbrow") == (3, 3)
    check(s)


def test_arni_cannot_boast_before_attacking(cards):
    s, arni = arni_table(cards)
    mana(s, C=1)
    with pytest.raises(ActionError):
        activate(s, "p1", arni)  # 702.142a: only if this creature attacked this turn
    check(s)


# -- Black Tom Cassidy: "{T}: Add {G}. If you control another Mutant, you gain 1 life." ---------------------------------------------------
def test_black_tom_gains_life_only_with_another_mutant(cards):
    s = build(cards, ["Black Tom Cassidy", "Cloudfin Raptor"])
    tom = put(s, "Black Tom Cassidy")
    next_turn(s)
    activate(s, "p1", tom)
    assert s.state.players["p1"].mana.get("G") == 1 and life(s) == 40  # he is a Mutant, but not "another"
    put(s, "Cloudfin Raptor")
    act(s, "p1", type="tap", card_ids=[tom.id], tapped=False)
    activate(s, "p1", tom)
    assert life(s) == 41
    check(s)


# -- Doctor Doom, Unrivaled: "{T}: You draw a card and lose 1 life. Then if your library has no cards in it, you win the game." -----------
def test_doctor_doom_wins_when_the_draw_empties_the_library(cards):
    s = build(cards, ["Doctor Doom, Unrivaled"])
    doom = put(s, "Doctor Doom, Unrivaled")
    next_turn(s)
    activate(s, "p1", doom)
    settle(s)
    assert s.state.rules.winner is None and life(s) == 39  # the library still has cards
    check(s)


def test_doctor_doom_wins_the_game_with_one_card_left(cards):
    s = build(cards, ["Doctor Doom, Unrivaled"])
    doom = put(s, "Doctor Doom, Unrivaled")
    next_turn(s)
    library = list(s.state.zones["p1:library"])
    act(s, "p1", type="move", card_ids=library[1:], to={"player": "p1", "zone": "exile"})
    activate(s, "p1", doom)
    settle(s)
    assert s.state.rules.winner == "p1"
    check(s)


# -- Red Death, Shipwrecker: "{T}: Goad target creature an opponent controls. That player draws a card. You add {R}." --------------------
def test_red_death_goads_gives_its_controller_a_card_and_adds_red(cards):
    s = build(cards, ["Red Death, Shipwrecker"], ["Hill Giant"])
    red_death = put(s, "Red Death, Shipwrecker")
    giant = put(s, "Hill Giant", "p2")
    next_turn(s)
    hand = len(s.state.zones["p2:hand"])
    activate(s, "p1", red_death, targets=[giant.id])
    settle(s)
    assert len(s.state.zones["p2:hand"]) == hand + 1  # "that player": the goaded creature's controller
    assert s.state.players["p1"].mana.get("R") == 1
    assert "goaded:p1" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[giant.id]).imposed
    check(s)


# -- the spells and triggers the same readings freed ------------------------------------------------------------------------------------------
def test_suspended_sentence_makes_the_creatures_controller_lose_life(cards):
    s = build(cards, ["Suspended Sentence"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    to_hand(s, "Suspended Sentence")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Suspended Sentence").id, targets=[giant.id])
    settle(s)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard" and life(s, "p2") == 37 and life(s) == 40  # "That player": Bob
    check(s)


def test_dalek_drone_trigger_makes_the_destroyed_creatures_controller_lose_life(cards):
    s = build(cards, ["Dalek Drone"], ["Hill Giant"])
    put(s, "Hill Giant", "p2")
    to_hand(s, "Dalek Drone")
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Dalek Drone").id)
    settle(s)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard" and life(s, "p2") == 37
    check(s)


def test_triskaidekaphobia_removes_a_player_with_exactly_13_life(cards):
    s = build(cards, ["Triskaidekaphobia"])
    put(s, "Triskaidekaphobia")
    act(s, "p2", type="set_life", player="p2", value=13)
    to_phase(s, "upkeep", turn=3)
    settle(s)  # the first mode: "Each player with exactly 13 life loses the game, then each player gains 1 life."
    assert s.state.rules.winner == "p1"
    check(s)


def test_shackles_of_treachery_grants_a_trigger_that_destroys_the_equipment_attached_to_it(cards):
    s = build(cards, ["Shackles of Treachery"], ["Hill Giant", "Bonesplitter"])
    giant, bonesplitter = put(s, "Hill Giant", "p2"), put(s, "Bonesplitter", "p2")
    attach(s, bonesplitter, giant, "p2")
    next_turn(s)
    to_hand(s, "Shackles of Treachery")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Shackles of Treachery").id, targets=[giant.id])
    settle(s)
    attack(s, giant)
    settle(s)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 3 - 2  # the stolen Giant, equipped with Bob's Bonesplitter, hit him
    assert s.state.cards[bonesplitter.id].zone == "p2:graveyard"  # "Whenever this creature deals damage, destroy target Equipment attached to it."
    check(s)


# -- Kellan, Planar Trailblazer: 'If Kellan is a Scout, it becomes a Human Faerie Detective and gains "Whenever Kellan deals combat damage …"' ----
def test_kellan_becomes_a_detective_with_a_trigger_that_names_him(cards):
    s = build(cards, ["Kellan, Planar Trailblazer"])
    kellan = put(s, "Kellan, Planar Trailblazer")
    next_turn(s)
    mana(s, R=1, C=1)
    activate(s, "p1", kellan, "Scout")
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[kellan.id])
    assert set(ch.subtypes) == {"Human", "Faerie", "Detective"}  # replaces the creature types (205.1a), no duration (611.2a)
    exiled, library = len(s.state.zones["p1:exile"]), len(s.state.zones["p1:library"])
    attack(s, kellan)
    settle(s)
    to_phase(s, "main2")
    assert life(s, "p2") == 38
    assert len(s.state.zones["p1:exile"]) == exiled + 1 and len(s.state.zones["p1:library"]) == library - 1  # the granted trigger ("Kellan" is the grantee)
    check(s)


# -- Vhati il-Dal: "{T}: Until end of turn, target creature has base power 1 or base toughness 1." ----------------------------------------
@pytest.mark.parametrize("option, expected", [("0", (1, 3)), ("1", (3, 1))])
def test_vhati_il_dal_sets_the_base_power_or_the_base_toughness_as_it_resolves(cards, option, expected):
    s = build(cards, ["Vhati il-Dal", "Hill Giant"])
    vhati, giant = put(s, "Vhati il-Dal"), put(s, "Hill Giant")
    next_turn(s)
    activate(s, "p1", vhati, targets=[giant.id])
    d = ask(s)
    assert d.kind == "choose_one" and [o.label for o in d.options] == ["Base power 1", "Base toughness 1"]  # 608.2d: chosen as it resolves
    assert pt(s, "Hill Giant") == (3, 3)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[option])
    settle(s)
    assert pt(s, "Hill Giant") == expected
    check(s)
    next_turn(s)
    assert pt(s, "Hill Giant") == (3, 3)  # until end of turn
    check(s)


# -- Mannichi, the Fevered Dream: "{1}{R}: Switch each creature's power and toughness until end of turn." ------------------------------------
def test_mannichi_switches_every_creatures_power_and_toughness_until_end_of_turn(cards):
    s = build(cards, ["Mannichi, the Fevered Dream"], ["Wall of Vipers"])
    mannichi = put(s, "Mannichi, the Fevered Dream")
    put(s, "Wall of Vipers", "p2")
    mana(s, R=1, C=1)
    activate(s, "p1", mannichi)
    settle(s)
    assert pt(s, "Mannichi, the Fevered Dream") == (2, 1) and pt(s, "Wall of Vipers", "p2") == (4, 2)  # 613.4d: layer 7d
    check(s)
    next_turn(s)
    assert pt(s, "Mannichi, the Fevered Dream") == (1, 2) and pt(s, "Wall of Vipers", "p2") == (2, 4)
    check(s)


# -- Glass-Cast Heart: "{B}{B}, {T}, Sacrifice this artifact and thirteen Blood tokens: Each opponent loses 13 life and you gain 13 life." -------------
def heart_table(cards, tokens):
    s = build(cards, ["Glass-Cast Heart"])
    heart = put(s, "Glass-Cast Heart")
    for _ in range(tokens):
        act(s, "p1", type="create_token", player="p1", token={"name": "Blood", "type_line": "Token Artifact — Blood", "text": ""})
    next_turn(s)
    mana(s, B=2)
    return s, heart


def test_glass_cast_heart_sacrifices_itself_and_thirteen_blood_tokens(cards):
    s, heart = heart_table(cards, 13)
    activate(s, "p1", heart, "thirteen Blood")
    settle(s)
    assert zone_of(s, "Glass-Cast Heart") == "p1:graveyard" and not [c for c in s.state.cards.values() if c.name == "Blood" and c.zone == "p1:battlefield"]
    assert life(s, "p2") == 27 and life(s) == 53
    check(s)


def test_glass_cast_heart_cannot_be_paid_with_twelve_blood_tokens(cards):
    s, heart = heart_table(cards, 12)
    with pytest.raises(ActionError):
        activate(s, "p1", heart, "thirteen Blood")  # 118.3: a cost that can't be paid in full isn't paid at all
    assert zone_of(s, "Glass-Cast Heart") == "p1:battlefield" and len([c for c in s.state.cards.values() if c.name == "Blood" and c.zone == "p1:battlefield"]) == 12
    assert s.state.players["p1"].mana.get("B") == 2 and not s.state.cards[heart.id].tapped
    check(s)


# -- the readings that only needed a word: a comma, a restriction's "this artifact or another artifact" -----------------------------------------
def test_a_mana_ability_may_name_a_cast_and_an_activation_after_a_comma():
    from app.rules import mana

    said = "Spend this mana only to cast an Assassin spell or a spell that has freerunning{}or to activate an ability of an Assassin source"
    assert mana.spend_kind(said.format(", ")) == mana.spend_kind(said.format(" ")) is not None  # Brotherhood Headquarters


def test_master_manufactorys_restriction_counts_the_artifact_itself():
    from app.rules import restrictions

    text = ("{T}: Create a 4/4 white and blue Golem artifact creature token. "
            "Activate only if ~ or another artifact entered the battlefield under your control this turn.")
    got = restrictions.parse(text)
    assert got is not None and [x["kind"] for x in got] == ["if"] and got[0]["cond"]["history"] == "entered"


# -- Jace, Wielder of Mysteries: "−8: Draw seven cards. Then if your library has no cards in it, you win the game." ---------------------------
def jace_table(cards, library):
    s = build(cards, ["Jace, Wielder of Mysteries"], forests=30)
    jace = put(s, "Jace, Wielder of Mysteries")
    act(s, "p1", type="counter", card_ids=[jace.id], kind="loyalty", delta=8)
    next_turn(s)
    cards_in = list(s.state.zones["p1:library"])
    act(s, "p1", type="move", card_ids=cards_in[library:], to={"player": "p1", "zone": "exile"})
    return s, jace


def test_jace_wins_when_the_seven_cards_empty_the_library(cards):
    s, jace = jace_table(cards, 7)
    activate(s, "p1", jace, "Draw seven cards")
    settle(s)
    assert s.state.rules.winner == "p1"
    check(s)


def test_jace_does_not_win_with_cards_left(cards):
    s, jace = jace_table(cards, 8)
    activate(s, "p1", jace, "Draw seven cards")
    settle(s)
    assert s.state.rules.winner is None and len(s.state.zones["p1:library"]) == 1
    check(s)


@pytest.mark.parametrize("name", ["Soraya the Falconer", "Asmodeus the Archfiend", "Tinder Wall", "Ice Cream Kitty", "Diaochan, Artful Beauty"])
def test_still_manual(cards, name):
    """Banding isn't modelled (Soraya); Asmodeus' "exiled with" link needs the draw replacement to be the exiling ability; Tinder Wall's target is the creature the
    sacrificed source blocks (its block is gone when the ability resolves); "another creature or token" doesn't say whether the Kitty's token copy could pay with
    itself; Diaochan's second target is chosen by an opponent."""
    assert coverage.of_card_data(cards.resolve(name)).level == "PARTIAL", name


# -- Wishmonger: "{2}: Target creature gains protection from the color of its controller's choice until end of turn. Any player may activate this ability." --
@pytest.mark.parametrize("victim, chooser", [("Hill Giant", "p2"), ("Grizzly Bears", "p1")])
def test_wishmonger_lets_the_targets_controller_choose_the_color(cards, victim, chooser):
    s = build(cards, ["Wishmonger", "Grizzly Bears"], ["Hill Giant"])
    wishmonger, bears, giant = put(s, "Wishmonger"), put(s, "Grizzly Bears"), put(s, "Hill Giant", "p2")
    target = giant if victim == "Hill Giant" else bears
    mana(s, C=2)
    activate(s, "p1", wishmonger, targets=[target.id])
    d = ask(s)
    assert d.player == chooser and [o.id for o in d.options] == ["White", "Blue", "Black", "Red", "Green"]  # 608.2d: its controller, as it resolves
    assert "protection" not in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[target.id]).keywords
    act(s, chooser, type="choose", decision_id=d.id, option_ids=["Red"])
    settle(s)
    assert "protection" in Plan.view(s.state, "p1", s.cards).ch(s.state.cards[target.id]).keywords
    check(s)


# -- "Each player returns all … cards from their graveyard to the battlefield / their hand" (Twilight's Call, Balthor the Defiled, Empty the Catacombs) ------
def bury(s, *names):
    """These cards (of whoever owns them) into their owners' graveyards."""
    for name, pid in names:
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})


def test_twilights_call_returns_every_players_creature_cards_under_their_owners(cards):
    s = build(cards, ["Twilight's Call", "Grizzly Bears", "Bonesplitter"], ["Hill Giant"])
    bury(s, ("Grizzly Bears", "p1"), ("Bonesplitter", "p1"), ("Hill Giant", "p2"))
    to_hand(s, "Twilight's Call")
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Twilight's Call").id)
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, "Hill Giant", "p2") == "p2:battlefield"  # each under its owner's control (400.3)
    assert zone_of(s, "Bonesplitter") == "p1:graveyard"  # not a creature card
    check(s)


def test_balthor_returns_the_black_and_red_creature_cards_and_exiles_himself_to_pay(cards):
    s = build(cards, ["Balthor the Defiled", "Wall of Vipers", "Grizzly Bears"], ["Hill Giant"])
    balthor = put(s, "Balthor the Defiled")
    bury(s, ("Wall of Vipers", "p1"), ("Grizzly Bears", "p1"), ("Hill Giant", "p2"))
    mana(s, B=3)
    activate(s, "p1", balthor, "Each player returns")
    settle(s)
    assert zone_of(s, "Balthor the Defiled") == "p1:exile"
    assert zone_of(s, "Wall of Vipers") == "p1:battlefield" and zone_of(s, "Hill Giant", "p2") == "p2:battlefield"  # black / red
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard"  # green
    check(s)


def test_empty_the_catacombs_returns_creature_cards_to_their_owners_hands(cards):
    s = build(cards, ["Empty the Catacombs", "Grizzly Bears"], ["Hill Giant"])
    bury(s, ("Grizzly Bears", "p1"), ("Hill Giant", "p2"))
    to_hand(s, "Empty the Catacombs")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Empty the Catacombs").id)
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:hand" and zone_of(s, "Hill Giant", "p2") == "p2:hand"
    check(s)


def test_the_library_wording_is_the_condition_the_grammar_already_read():
    from app.rules import conditions

    assert conditions.parse("your library has no cards in it") == conditions.parse("there are no cards in your library") is not None

