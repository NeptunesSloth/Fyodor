"""Wave 41B: the x_value family, second pass, commanders first (CR 2026-09-25), real Oracle text (tests/fixtures/wave41b_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 107.3c / 608.2h: an X the text defines ("where X is …") of a triggered ability is worked out as the effect is carried out, so a count that
  changes while the trigger waits changes the X.
* 702.45a bushido, 702.189a firebending, 702.181a mobilize with a defined X (Fumiko's ruling 2005-02-01: "calculated each time Fumiko's bushido
  trigger resolves"); soulshift X (Kodama of the Center Tree) stays manual — its ruling reads the state before the trigger.
* 701.50d connive X on "target attacking creature"; 601.2c "up to one hundred target creatures"; "if he's equipped"; 608.2h "Then up to one other
  target attacking creature" after an attach (the "other" is other than the source).
* 603.12, 608.2h, 113.7a: a reflexive "When you do" whose X is the stat of the card/creature the first instruction exiled, as it last existed (Venom:
  a card from a graveyard; Yannik: a creature exiled "until", a token included, 111.7), and "distribute X … among any number of target creatures" with
  none chosen (115.6; Yannik's ruling of 2020-04-17).
* 605.3b: "Add X {G} or X {W}, where X is the number of other creatures you control" (Brigid, Doun's Mind). 608.2h: the colors among "those creatures"
  (General Tazri), this turn's creatures exiled under an opponent's control (Vren) and opponents dealt combat damage by ~ or a Dragon (Estinien).
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
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, until
from tests.test_rules_conditionals import settle as settle_stack
from tests.test_rules_wave12a_counters_keywords import answer
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave41b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w41b", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Sun Warriors", "Firebending Student", "Tend the Pests", "Estinien Varlineau", "General Tazri", "Vren, the Relentless", "Brigid, Clachan's Heart // Brigid, Doun's Mind", "Venom, Deadly Devourer", "Yannik, Scavenging Sentinel", "Fumiko the Lowblood", "Fire Lord Zuko", "Avenger of the Fallen", "Whiplash, Vengeful Engineer", "Raffine, Scheming Seer",
        "Baldin, Century Herdmaster", "Amy Rose"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", FULL)
def test_the_cards_with_a_defined_x_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_soulshift_x_is_full_since_wave_110g(cards):
    # Kodama of the Center Tree: X is read from the state just before it died (ruling 2005-02-01), its own count included: test_rules_wave110g_s15.py
    assert coverage.of_card_data(cards.resolve("Kodama of the Center Tree")).level == "FULL"


def hold(s):
    """Ask for priority with a trigger on the stack (so something can change before it resolves)."""
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"


def declare(s, pid, *attackers, turn=1):
    until(s, lambda s: s.state.turn.number >= turn and s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, pid, type="declare_attackers", attackers=[{"card_id": a.id, "target": "p2" if pid == "p1" else "p1"} for a in attackers])


def held(s, color, pid="p1"):
    """Mana of a color in the pool: plain pool plus provenance units (every source is remembered as a unit, mana_units.needs_unit)."""
    p = s.state.players[pid]
    return p.mana.get(color, 0) + sum(1 for u in p.mana_units if u.sym == color)


def resolve(s):
    """Resolve the stack, stopping at a decision (the blockers')."""
    while s.state.zones.get("stack") and s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")


def zone_names(s, zone, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones.get(f"{pid}:{zone}", [])]


# -- bushido X (Fumiko) ----------------------------------------------------------------------------------------------
def fumiko_blocks(cards, remove_one=False):
    s = build(cards, ["Fumiko the Lowblood"])
    fumiko = put(s, "Fumiko the Lowblood")
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    a = creature(s, "p2", "Raider A", "2/2", text="Haste")
    b = creature(s, "p2", "Raider B", "2/2", text="Haste")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": a.id, "target": "p1"}, {"card_id": b.id, "target": "p1"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    hold(s)
    act(s, "p1", type="declare_blockers", blocks=[{"blocker_id": fumiko.id, "attacker_id": a.id}])
    return s, fumiko, a, b


def test_fumiko_blocks_and_gets_the_number_of_attacking_creatures(cards):
    s, fumiko, a, b = fumiko_blocks(cards)
    assert s.state.zones.get("stack")  # the bushido trigger waits
    settle_stack(s)
    assert pt(s, "Fumiko the Lowblood") == (5, 4)  # X = 2 attackers (702.45a: +X/+X)
    check(s)


def test_fumiko_reads_the_attackers_as_the_bushido_trigger_resolves(cards):
    s, fumiko, a, b = fumiko_blocks(cards)
    act(s, "p1", type="move", card_ids=[b.id], to={"zone": "graveyard"})  # an attacker leaves before it resolves (608.2h)
    settle_stack(s)
    assert pt(s, "Fumiko the Lowblood") == (4, 3)  # X = 1
    check(s)


def test_fumiko_attacking_and_blocked_gets_the_number_of_attacking_creatures_too(cards):
    s = build(cards, ["Fumiko the Lowblood"])
    fumiko = put(s, "Fumiko the Lowblood")
    pal = creature(s, "p1", "Pal", "1/1", text="Haste")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (Bob's creatures must attack on his turn, so his Ogre comes now)
    ogre = creature(s, "p2", "Ogre", "3/3")
    declare(s, "p1", fumiko, pal, turn=3)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": ogre.id, "attacker_id": fumiko.id}])
    settle_stack(s)
    assert pt(s, "Fumiko the Lowblood") == (5, 4)  # "becomes blocked": X = 2 attackers (702.45a)
    check(s)


# -- firebending X (Fire Lord Zuko) and mobilize X (Avenger of the Fallen) -----------------------------------------
def test_zuko_firebending_adds_red_mana_equal_to_his_power(cards):
    s = build(cards, ["Fire Lord Zuko"])
    zuko = put(s, "Fire Lord Zuko")
    creature(s, "p2", "Ogre", "3/3")  # (Bob may block: combat waits for his declaration, with the firebending mana still there)
    declare(s, "p1", zuko, turn=3)
    resolve(s)
    assert held(s, "R") == 2  # 702.189a: X = Zuko's power (2)
    check(s)


def test_zuko_firebending_reads_his_power_as_the_trigger_resolves(cards):
    s = build(cards, ["Fire Lord Zuko"])
    zuko = put(s, "Fire Lord Zuko")
    creature(s, "p2", "Ogre", "3/3")
    hold(s)
    declare(s, "p1", zuko, turn=3)
    assert s.state.zones.get("stack")
    act(s, "p1", type="counter", card_ids=[zuko.id], kind="+1/+1", delta=2)  # it grows while the trigger waits
    resolve(s)
    assert held(s, "R") == 4  # 608.2h: the power when it resolves
    check(s)


def test_zuko_with_no_power_adds_nothing(cards):
    s = build(cards, ["Fire Lord Zuko"])
    zuko = put(s, "Fire Lord Zuko")
    act(s, "p1", type="counter", card_ids=[zuko.id], kind="-1/-1", delta=2)  # a 0/2
    creature(s, "p2", "Ogre", "3/3")  # (Bob may block: combat waits for his declaration, with the firebending mana still there)
    declare(s, "p1", zuko, turn=3)
    resolve(s)
    assert held(s, "R") == 0  # X = 0
    check(s)


def test_sun_warriors_firebending_counts_the_creatures_you_control_as_the_trigger_resolves(cards):
    s = build(cards, ["Sun Warriors"])
    sun = put(s, "Sun Warriors")
    creature(s, "p2", "Ogre", "3/3")
    pal = creature(s, "p1", "Pal", "1/1")
    hold(s)
    declare(s, "p1", sun, turn=3)
    act(s, "p1", type="move", card_ids=[pal.id], to={"zone": "graveyard"})  # one of the two leaves while the trigger waits
    creature(s, "p1", "Pal B", "1/1")
    creature(s, "p1", "Pal C", "1/1")
    resolve(s)
    assert held(s, "R") == 3  # X = 3 creatures (Sun Warriors, Pal B, Pal C) when it resolves
    check(s)


def test_firebending_student_adds_red_mana_equal_to_its_power(cards):
    s = build(cards, ["Firebending Student"])
    student = put(s, "Firebending Student")
    creature(s, "p2", "Ogre", "3/3")
    declare(s, "p1", student, turn=3)
    resolve(s)
    assert held(s, "R") == 1  # X = its power (1)
    check(s)


def test_tend_the_pests_makes_a_pest_for_the_power_of_the_sacrificed_creature(cards):
    s = build(cards, ["Tend the Pests"])
    spell = card_named(s, "Tend the Pests")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    giant = creature(s, "p1", "Giant", "3/3")
    mana(s, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s, [giant.id])
    pests = [c for c in s.state.cards.values() if c.name == "Pest" and c.zone == "p1:battlefield"]
    assert len(pests) == 3 and giant.id not in s.state.cards  # X = 3, its power as it last existed (608.2h)
    before = life(s)
    act(s, "p1", type="counter", card_ids=[pests[0].id], kind="-1/-1", delta=1)  # it dies (704.5f): "When this token dies, you gain 1 life" (the token's own ability)
    until(s, lambda s: life(s) != before or s.state.turn.number >= 2)
    assert life(s) == before + 1 and len([c for c in s.state.cards.values() if c.name == "Pest" and c.zone == "p1:battlefield"]) == 2
    check(s)


def test_avenger_of_the_fallen_mobilizes_one_warrior_per_creature_card_in_the_graveyard(cards):
    s = build(cards, ["Avenger of the Fallen", "Fire Lord Zuko", "Fumiko the Lowblood"])
    avenger = put(s, "Avenger of the Fallen")
    for name in ("Fire Lord Zuko", "Fumiko the Lowblood"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"zone": "graveyard"})
    creature(s, "p2", "Ogre", "3/3")
    declare(s, "p1", avenger, turn=3)
    resolve(s)
    warriors = [c for c in s.state.cards.values() if c.name == "Warrior" and c.zone == "p1:battlefield"]
    assert len(warriors) == 2 and all(c.attacking is not None and c.tapped for c in warriors)  # 702.181a: tapped and attacking
    check(s)


def test_avenger_of_the_fallen_with_an_empty_graveyard_makes_no_warriors(cards):
    s = build(cards, ["Avenger of the Fallen"])
    avenger = put(s, "Avenger of the Fallen")
    creature(s, "p2", "Ogre", "3/3")
    declare(s, "p1", avenger, turn=3)
    resolve(s)
    assert not [c for c in s.state.cards.values() if c.name == "Warrior"]  # X = 0
    check(s)


# -- Whiplash: "if he's equipped", X = the Equipment attached to him ----------------------------------------------------
def whiplash_attacks(cards, equipment=("Bonesplitter", "Short Sword")):
    s = build(cards, ["Whiplash, Vengeful Engineer", *equipment])
    whiplash = put(s, "Whiplash, Vengeful Engineer")
    gear = [put(s, n) for n in equipment]
    for g in gear:
        act(s, "p1", type="attach", card_ids=[g.id], to=whiplash.id)
    return s, whiplash, gear


def test_whiplash_drains_for_each_equipment_attached_to_him(cards):
    s, whiplash, _ = whiplash_attacks(cards)
    creature(s, "p2", "Ogre", "3/3")
    hold(s)
    declare(s, "p1", whiplash, turn=3)
    assert s.state.zones.get("stack")
    before = life(s, "p1"), life(s, "p2")
    resolve(s)
    assert (life(s, "p1") - before[0], life(s, "p2") - before[1]) == (2, -2)  # X = 2 Equipment
    check(s)


def test_whiplash_reads_the_equipment_attached_as_the_trigger_resolves(cards):
    s, whiplash, (bone, sword) = whiplash_attacks(cards)
    creature(s, "p2", "Ogre", "3/3")
    hold(s)
    declare(s, "p1", whiplash, turn=3)
    before = life(s, "p1"), life(s, "p2")
    act(s, "p1", type="detach", card_ids=[sword.id])  # one falls off while the trigger waits
    resolve(s)
    assert (life(s, "p1") - before[0], life(s, "p2") - before[1]) == (1, -1)  # 608.2h: X = 1 when it resolves
    check(s)


def test_whiplash_does_nothing_when_he_is_not_equipped(cards):
    s = build(cards, ["Whiplash, Vengeful Engineer"])
    whiplash = put(s, "Whiplash, Vengeful Engineer")
    creature(s, "p2", "Ogre", "3/3")
    declare(s, "p1", whiplash, turn=3)
    assert not s.state.zones.get("stack")  # 603.4: no equipment, no trigger
    check(s)


def test_whiplash_does_nothing_when_every_equipment_fell_off_before_it_resolves(cards):
    s, whiplash, gear = whiplash_attacks(cards)
    creature(s, "p2", "Ogre", "3/3")
    hold(s)
    declare(s, "p1", whiplash, turn=3)
    before = life(s, "p1"), life(s, "p2")
    act(s, "p1", type="detach", card_ids=[g.id for g in gear])
    resolve(s)
    assert (life(s, "p1"), life(s, "p2")) == before  # 603.4: the intervening "if" is checked again as it resolves
    check(s)


# -- Raffine: "target attacking creature connives X, where X is the number of attacking creatures" --------------------
def raffine_attacks(cards):
    s = build(cards, ["Raffine, Scheming Seer", "Sol Ring", "Bonesplitter", "Arcane Signet"])
    raffine = put(s, "Raffine, Scheming Seer")
    a = creature(s, "p1", "Raider A", "2/2", text="Haste")
    b = creature(s, "p1", "Raider B", "2/2", text="Haste")
    hold(s)
    return s, raffine, a, b


def target_and_empty_hand(s, target):
    """Pick the connive target, then empty the hand while the trigger waits: whatever connive draws, it draws only to discard."""
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[target.id])
    for c in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "graveyard"})
    for n in ("Sol Ring", "Bonesplitter", "Arcane Signet"):  # on top of the library: the three nonland cards connive draws
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "library"})


def test_raffine_makes_an_attacker_connive_for_the_number_of_attackers(cards):
    s, raffine, a, b = raffine_attacks(cards)
    declare(s, "p1", raffine, a, b, turn=3)
    target_and_empty_hand(s, a)
    answer(s)
    assert pt(s, "Raider A") == (5, 5)  # X = 3 attackers: draw 3, discard 3 (all nonland), three +1/+1 counters (701.50d)
    assert len(s.state.zones["p1:hand"]) == 0
    check(s)


def test_raffine_reads_the_attackers_as_the_connive_trigger_resolves(cards):
    s, raffine, a, b = raffine_attacks(cards)
    declare(s, "p1", raffine, a, b, turn=3)
    target_and_empty_hand(s, a)
    act(s, "p1", type="move", card_ids=[b.id], to={"zone": "graveyard"})  # an attacker leaves before it resolves
    answer(s)
    assert pt(s, "Raider A") == (4, 4)  # X = 2
    check(s)


# -- Baldin: "up to one hundred target creatures each get +0/+X, where X is the number of cards in your hand" ----------
def test_baldin_gives_up_to_one_hundred_creatures_toughness_for_the_cards_in_hand(cards):
    s = build(cards, ["Baldin, Century Herdmaster"])
    baldin = put(s, "Baldin, Century Herdmaster")
    a = creature(s, "p1", "Raider A", "2/2")
    b = creature(s, "p2", "Ogre", "3/3")
    hand = len(s.state.zones["p1:hand"])
    declare(s, "p1", baldin, turn=3)
    d = s.state.rules.decision
    assert d is not None and d.max_choices >= 3 and d.min_choices == 0  # 601.2c: up to one hundred, so every creature may be chosen
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id, b.id])
    resolve(s)  # (Bob's Ogre may block: combat waits for his declaration)
    hand_now = len(s.state.zones["p1:hand"])
    assert pt(s, "Raider A")[1] == 2 + hand_now and pt(s, "Ogre", "p2")[1] == 3 + hand_now  # 608.2h: the hand as it resolves
    assert hand_now >= hand  # (the turn's draw)
    check(s)


def test_baldin_reads_the_hand_as_the_trigger_resolves_and_zero_adds_nothing(cards):
    s = build(cards, ["Baldin, Century Herdmaster"])
    baldin = put(s, "Baldin, Century Herdmaster")
    a = creature(s, "p1", "Raider A", "2/2")
    hold(s)
    declare(s, "p1", baldin, turn=3)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id])
    for c in list(s.state.zones["p1:hand"])[1:]:  # all but one card leave the hand while the trigger waits
        act(s, "p1", type="move", card_ids=[c], to={"zone": "graveyard"})
    answer(s)
    assert pt(s, "Raider A") == (2, 3)  # X = 1
    check(s)


def test_baldin_with_an_empty_hand_adds_nothing(cards):
    s = build(cards, ["Baldin, Century Herdmaster"])
    baldin = put(s, "Baldin, Century Herdmaster")
    a = creature(s, "p1", "Raider A", "2/2")
    declare(s, "p1", baldin, turn=3)
    d = s.state.rules.decision
    for c in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[c], to={"zone": "graveyard"})
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[a.id])
    answer(s)
    assert pt(s, "Raider A") == (2, 2)  # X = 0
    check(s)


# -- Amy Rose: attach an Equipment, then "up to one other target attacking creature gets +X/+0, where X is Amy Rose's power" --
def test_amy_rose_attaches_then_pumps_another_attacker_by_her_power_with_the_equipment(cards):
    s = build(cards, ["Amy Rose", "Bonesplitter"])
    amy = put(s, "Amy Rose")
    bonesplitter = put(s, "Bonesplitter")
    runner = creature(s, "p1", "Runner", "1/1", text="Haste")
    declare(s, "p1", amy, runner)
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == [bonesplitter.id]  # the Equipment
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[bonesplitter.id])
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == [runner.id]  # "other": not Amy Rose herself
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[runner.id])
    answer(s)
    assert s.state.cards[bonesplitter.id].attached_to == amy.id
    assert pt(s, "Amy Rose") == (5, 3) and pt(s, "Runner") == (6, 1)  # X = her power as it resolves: 3 + 2 from the Equipment just attached
    check(s)


def test_amy_rose_without_an_equipment_still_pumps_another_attacker(cards):
    s = build(cards, ["Amy Rose"])
    amy = put(s, "Amy Rose")
    runner = creature(s, "p1", "Runner", "1/1", text="Haste")
    declare(s, "p1", amy, runner)
    d = s.state.rules.decision
    if d is not None and d.options and runner.id in [o.id for o in d.options]:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[runner.id])
    answer(s)
    assert pt(s, "Runner") == (4, 1)  # X = 3
    check(s)


# -- Venom / Yannik: a reflexive "When you do" whose X is the exiled card's stat ------------------------------------------
def venom_exiles(cards, victim, owner="p1"):
    s = build(cards, ["Venom, Deadly Devourer", victim] if owner == "p1" else ["Venom, Deadly Devourer"], theirs=[victim] if owner == "p2" else [])
    venom = put(s, "Venom, Deadly Devourer")
    gone = card_named(s, victim, owner)
    act(s, owner, type="move", card_ids=[gone.id], to={"zone": "graveyard"})
    mana(s, G=3)
    act(s, "p1", type="activate_ability", card_id=venom.id, ability=1)
    return s, venom, gone


def test_venom_puts_counters_equal_to_the_exiled_cards_toughness(cards):
    s, venom, gone = venom_exiles(cards, "Baldin, Century Herdmaster")
    answer(s, gone.id)
    assert s.state.cards[gone.id].zone == "p1:exile"
    assert s.state.cards[venom.id].counters == {"+1/+1": 7}  # X = Baldin's toughness (7), 608.2h
    check(s)


def test_venom_exiling_a_card_with_no_toughness_puts_no_counters(cards):
    s, venom, gone = venom_exiles(cards, "Endless One")
    answer(s, gone.id)
    assert s.state.cards[gone.id].zone == "p1:exile" and not s.state.cards[venom.id].counters.get("+1/+1")  # X = 0
    check(s)


def test_venom_can_exile_a_card_from_an_opponents_graveyard(cards):
    s, venom, gone = venom_exiles(cards, "Fire Lord Zuko", owner="p2")
    answer(s, gone.id)
    assert s.state.cards[gone.id].zone == "p2:exile" and s.state.cards[venom.id].counters == {"+1/+1": 4}
    check(s)


def drive(s, answers, limit=40):
    """Answer each decision by its step (``answers``: option ids, or amounts for a division); the others take their first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        pick = answers.get((d.resume or {}).get("step"), answers.get(d.kind))
        if d.kind == "divide":
            act(s, d.player, type="choose", decision_id=d.id, amounts=pick)
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick if pick is not None else [o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never settled")


def yannik_enters(cards, exiled_power_counters=2):
    s = build(cards, ["Yannik, Scavenging Sentinel"])
    yannik = card_named(s, "Yannik, Scavenging Sentinel")
    act(s, "p1", type="move", card_ids=[yannik.id], to={"zone": "hand"})
    bear = creature(s, "p1", "Bear", "2/2")
    pal = creature(s, "p1", "Pal", "1/1")
    if exiled_power_counters:
        act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=exiled_power_counters)
    mana(s, G=3, W=1)
    act(s, "p1", type="cast_spell", card_id=yannik.id)
    return s, yannik, bear, pal


def test_yannik_exiles_a_creature_and_distributes_counters_equal_to_its_power(cards):
    s, yannik, bear, pal = yannik_enters(cards)  # a 4/4 token when it is exiled
    drive(s, {"sacrifice_choice": [bear.id], "trigger_group": [yannik.id, pal.id], "divide": [3, 1], "search_may": ["no"]})
    assert bear.id not in s.state.cards  # (a token that was exiled ceases to exist, 111.7: the power it last had still counts, 608.2h)
    assert s.state.cards[yannik.id].counters == {"+1/+1": 3} and s.state.cards[pal.id].counters == {"+1/+1": 1}  # X = 4
    check(s)


def test_yannik_may_choose_no_targets_for_the_counters(cards):
    s, yannik, bear, pal = yannik_enters(cards)
    drive(s, {"sacrifice_choice": [bear.id], "trigger_group": [], "search_may": ["no"]})
    assert not s.state.cards[yannik.id].counters and not s.state.cards[pal.id].counters  # (the ruling of 2020-04-17: zero targets are allowed)
    check(s)


def test_yannik_exiling_a_creature_with_no_power_distributes_nothing(cards):
    s, yannik, bear, pal = yannik_enters(cards, exiled_power_counters=0)
    wall = creature(s, "p1", "Wall", "0/3")
    drive(s, {"sacrifice_choice": [wall.id], "search_may": ["no"]})
    assert wall.id not in s.state.cards and not s.state.cards[yannik.id].counters and not s.state.cards[pal.id].counters  # X = 0: no targets, nothing to divide (601.2d)
    check(s)


# -- General Tazri: "Ally creatures you control get +X/+X, where X is the number of colors among those creatures" ------------------
def ally(s, name, colors):
    act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": "Token Creature — Ally", "power": "2", "toughness": "2", "colors": colors})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1")


def tazri_table(cards, colors):
    s = build(cards, ["General Tazri"])
    tazri = put(s, "General Tazri")
    return s, tazri, ally(s, "Scout", colors)


def test_tazri_gives_the_allies_the_number_of_colors_among_them(cards):
    s, tazri, scout = tazri_table(cards, ["R"])
    mana(s, W=1, U=1, B=1, R=1, G=1)
    base = pt(s, "General Tazri")
    act(s, "p1", type="activate_ability", card_id=tazri.id, ability=1)
    settle_stack(s)
    assert pt(s, "Scout") == (4, 4)  # X = 2: white (Tazri herself, one of "those creatures") and red (the Scout)
    assert pt(s, "General Tazri") == (base[0] + 2, base[1] + 2)
    check(s)


def test_tazri_counts_the_colors_as_the_ability_resolves(cards):
    s, tazri, scout = tazri_table(cards, ["R"])
    mana(s, W=1, U=1, B=1, R=1, G=1)
    hold(s)
    act(s, "p1", type="activate_ability", card_id=tazri.id, ability=1)
    act(s, "p1", type="move", card_ids=[tazri.id], to={"zone": "graveyard"})  # the white Ally leaves while the ability waits
    settle_stack(s)
    assert pt(s, "Scout") == (3, 3)  # X = 1: the red Scout is all that's left (608.2h)
    check(s)


def test_tazri_with_only_colorless_allies_left_gives_nothing(cards):
    s, tazri, scout = tazri_table(cards, [])
    mana(s, W=1, U=1, B=1, R=1, G=1)
    hold(s)
    act(s, "p1", type="activate_ability", card_id=tazri.id, ability=1)
    act(s, "p1", type="move", card_ids=[tazri.id], to={"zone": "graveyard"})
    settle_stack(s)
    assert pt(s, "Scout") == (2, 2)  # X = 0
    check(s)


# -- Estinien Varlineau: "you draw X cards and lose X life, where X is the number of your opponents who were dealt combat damage by Estinien or a Dragon" --
def estinien_attack(cards, attacker):
    s = build(cards, ["Estinien Varlineau"])
    estinien = put(s, "Estinien Varlineau")
    other = creature(s, "p1", "Dragon", "2/2", "Token Creature — Dragon", "Haste") if attacker == "dragon" else creature(s, "p1", "Bear", "2/2", text="Haste")
    return s, estinien, other


def test_estinien_draws_and_loses_for_the_opponent_he_dealt_combat_damage(cards):
    s, estinien, _ = estinien_attack(cards, "dragon")
    hold(s)
    declare(s, "p1", estinien, turn=3)
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.turn.number == 3 and s.state.zones.get("stack"))
    hand, before = len(s.state.zones["p1:hand"]), life(s, "p1")
    settle_stack(s)
    assert (len(s.state.zones["p1:hand"]) - hand, before - life(s, "p1")) == (1, 1)  # X = 1 (Bob was dealt combat damage by Estinien)
    check(s)


def test_estinien_counts_a_dragon_that_dealt_combat_damage(cards):
    s, estinien, dragon = estinien_attack(cards, "dragon")
    hold(s)
    declare(s, "p1", dragon, turn=3)
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.turn.number == 3 and s.state.zones.get("stack"))
    hand, before = len(s.state.zones["p1:hand"]), life(s, "p1")
    settle_stack(s)
    assert (len(s.state.zones["p1:hand"]) - hand, before - life(s, "p1")) == (1, 1)  # X = 1: a Dragon dealt it
    check(s)


def test_estinien_ignores_combat_damage_dealt_by_anything_else(cards):
    s, estinien, bear = estinien_attack(cards, "bear")
    hold(s)
    declare(s, "p1", bear, turn=3)
    until(s, lambda s: s.state.turn.phase == "main2" and s.state.turn.number == 3 and s.state.zones.get("stack"))
    hand, before = len(s.state.zones["p1:hand"]), life(s, "p1")
    settle_stack(s)
    assert (len(s.state.zones["p1:hand"]), life(s, "p1")) == (hand, before)  # X = 0: a Bear isn't Estinien or a Dragon
    check(s)


# -- Vren, the Relentless: "create X … Rat tokens, where X is the number of creatures that were exiled under your opponents' control this turn" --
def vren_table(cards, victims=2):
    s = build(cards, ["Vren, the Relentless", "Murder", "Swords to Plowshares"])
    put(s, "Vren, the Relentless")
    return s, [creature(s, "p2", f"Goblin {i}", "2/2") for i in range(victims)]


def remove(s, spell, body, **cost):
    card = card_named(s, spell)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "hand"})
    mana(s, **cost)
    act(s, "p1", type="cast_spell", card_id=card.id, targets=[body.id])
    settle_stack(s)


def rats(s):
    return [c for c in s.state.cards.values() if c.name == "Rat" and c.zone == "p1:battlefield"]


def test_vren_makes_a_rat_for_each_creature_exiled_under_an_opponents_control(cards):
    s, (a, b) = vren_table(cards)
    remove(s, "Murder", a, B=3)  # Vren's replacement: it would die, so it is exiled instead (614.1a)
    remove(s, "Swords to Plowshares", b, W=1)  # exiled outright
    until(s, lambda s: s.state.turn.number >= 2)  # (the end step trigger of turn 1)
    assert len(rats(s)) == 2 and pt(s, "Rat") == (3, 3)  # X = 2; each Rat token gets +1/+1 for the other Rat token and for Vren, a Rat
    check(s)


def test_vren_makes_no_rats_when_nothing_was_exiled(cards):
    s, _ = vren_table(cards)
    until(s, lambda s: s.state.turn.number >= 2)
    assert not rats(s)  # X = 0
    check(s)


def test_vren_counts_what_is_exiled_while_the_end_step_trigger_waits(cards):
    s, (a, b) = vren_table(cards)
    hold(s)
    until(s, lambda s: s.state.turn.phase == "end" and s.state.zones.get("stack"))
    remove_in_response = card_named(s, "Swords to Plowshares")
    act(s, "p1", type="move", card_ids=[remove_in_response.id], to={"zone": "hand"})
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=remove_in_response.id, targets=[a.id])
    settle_stack(s)
    assert len(rats(s)) == 1  # 608.2h: the count as the trigger resolves (X = 1)
    check(s)


# -- Brigid, Doun's Mind: "{T}: Add X {G} or X {W}, where X is the number of other creatures you control" ----------------------
BRIGID = "Brigid, Clachan's Heart // Brigid, Doun's Mind"


def brigid_with_others(cards, others):
    s = build(cards, [BRIGID])
    brigid = put(s, BRIGID)
    for i in range(others):
        creature(s, "p1", f"Elf {i}", "1/1")
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (no longer summoning sick)
    act(s, "p1", type="set_face", card_id=brigid.id, face=1)  # Brigid, Doun's Mind
    return s, brigid


def test_brigid_adds_one_color_for_each_other_creature(cards):
    s, brigid = brigid_with_others(cards, 3)
    act(s, "p1", type="activate_ability", card_id=brigid.id, ability=0)
    d = s.state.rules.decision
    if d is not None:  # the color: green or white
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "G" in o.label)])
    assert held(s, "G") == 3 and held(s, "W") == 0  # X = 3 (Brigid herself is not an "other" creature)
    check(s)


def test_brigid_with_no_other_creature_adds_no_mana(cards):
    s, brigid = brigid_with_others(cards, 0)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=brigid.id, ability=0)  # X = 0: nothing to add (as Gaea's Cradle with no creature)
    check(s)
