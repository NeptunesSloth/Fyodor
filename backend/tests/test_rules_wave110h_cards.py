"""Wave 110H: one-card builds on real Oracle text (every scenario checks replay and a save/load round trip).

* Carom: the shared "next N damage ... is dealt to another target" redirection with N = 1 (614.9), then its own draw line.
* Bewitching Leechcraft: the host's untap step swaps the untap for a +1/+1 counter; none left, it stays tapped (502.3, 614.1a).
* Psychotic Episode: reveal hand and top card, you choose one revealed card, its owner puts it on the bottom (701.20a, 401.4).
* Kosei, Penitent Warlord: a static grant needing three conditions at once (604.2, 611.3a): enchanted, equipped, a counter.
* Immard, the Stormcleaver: put a counter or remove one (the removal starts the reflexive modal trigger, 603.12, 700.2).
* Xenosquirrels: the roll-adjust foundation with a counter cost, one adjustment per die and no once-a-turn limit (706.2, 614.1).
* Frantic Scapegoat: optional pick among the entering batch; suspecting it ends the Goat's own suspect (701.60a, 603.4).
* Welcome to the Fold: "gain control ... if its toughness is N or less" (608.2b) with the madness X replacement bound (702.35, 107.3b).
* Aetherplasm: a hand creature put onto the battlefield blocking the creature it blocked (509.4: never "blocked", enters_blocking).
* Dire Blunderbuss (back of Dire Flail): "an artifact other than <granter>" excludes the Equipment itself, not the creature (607.1a, 603.12).
* Dralnu, Lich Lord: damage to it is replaced by sacrificing that many permanents (614.6, 701.21).
* Lava Burst: damage to a creature ignores Carom's redirection (614.9, 615.12); to a player it is plain damage.
* Temporal Firestorm: chosen as it resolves (not targeted), up to X = times kicked, those permanents phase out before the 5 damage (608.2d, 702.26).
* Binding Negotiation: "Otherwise" after an optional choice (608.2c), a face-up exiled card to its owner's graveyard (406.3, 400.3).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, to_hand

EXTRA = [
    real("Binding Negotiation", "{1}{B}", 2, "Sorcery",
         "Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it. Otherwise, you may put a "
         "face-up exiled card they own into their graveyard.", None, "B"),
]
EXTRA.append(real("Carom", "{1}{W}", 2, "Instant", "The next 1 damage that would be dealt to target creature this turn is dealt to another target creature "
                  "instead.\nDraw a card.", None, "W"))
EXTRA.append(real("Hill Giant", "{3}{R}", 4, "Creature \u2014 Giant", "", ("3", "3"), "R"))
EXTRA.append(real("Bewitching Leechcraft", "{1}{U}", 2, "Enchantment \u2014 Aura",
                  "Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature has \"If this creature would untap during your "
                  "untap step, remove a +1/+1 counter from it instead. If you do, untap it.\" (Otherwise, it doesn't untap.)", None, "U"))
EXTRA.append(real("Psychotic Episode", "{2}{B}", 3, "Sorcery",
                  "Target player reveals their hand and the top card of their library. You choose a card revealed this way. That player puts the "
                  "chosen card on the bottom of their library.\nMadness {1}{B} (If you discard this card, discard it into exile. When you do, cast it "
                  "for its madness cost or put it into your graveyard.)", None, "B"))
EXTRA += [
    real("Kosei, Penitent Warlord", "{3}{B}", 4, "Legendary Creature \u2014 Human Samurai",
         "As long as Kosei is enchanted, equipped, and has a counter on it, Kosei has \"Whenever Kosei deals combat damage to an opponent, you "
         "draw that many cards and Kosei deals that much damage to each other opponent.\"", ("3", "3"), "B"),
    real("Plain Halo", "{W}", 1, "Enchantment \u2014 Aura", "Enchant creature", None, "W"),
    real("Plain Blade", "{1}", 1, "Artifact \u2014 Equipment", "Equip {1}", None, ""),
]
EXTRA.append(real("Immard, the Stormcleaver", "{1}{U}{R}{W}", 4, "Legendary Creature \u2014 Human Soldier",
                  "Whenever Immard, the Stormcleaver enters or attacks, put a charge counter on it or remove one from it. When you remove a counter "
                  "this way, choose one \u2014\n\u2022 Immard deals 4 damage to any target.\n\u2022 Immard gains lifelink and indestructible until end "
                  "of turn.", ("4", "4"), "RUW"))
EXTRA.append(real("Xenosquirrels", "{2}{R}{G}", 4, "Creature \u2014 Squirrel",
                  "After you roll a die, you may remove a +1/+1 counter from this creature. If you do, increase or decrease the result by 1.",
                  ("2", "2"), "RG"))
EXTRA.append(real("Roll Probe", "{R}", 1, "Sorcery", "Roll a d6. You gain life equal to the result.", None, "R"))
EXTRA.append(real("Frantic Scapegoat", "{R}", 1, "Creature \u2014 Goat",
                  "Haste\nWhen this creature enters, suspect it. (It has menace and can't block.)\nWhenever one or more other creatures you control enter, "
                  "if this creature is suspected, you may suspect one of the other creatures. If you do, this creature is no longer suspected.",
                  ("1", "1"), "R"))
EXTRA.append(real("Welcome to the Fold", "{2}{U}{U}", 4, "Sorcery",
                  "Madness {X}{U}{U} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your "
                  "graveyard.)\nGain control of target creature if its toughness is 2 or less. If this spell's madness cost was paid, instead gain control "
                  "of that creature if its toughness is X or less.", None, "U"))
EXTRA.append(real("Discard Probe", "{B}", 1, "Sorcery", "Discard a card.", None, "B"))
EXTRA.append(real("Aetherplasm", "{2}{U}{U}", 4, "Creature \u2014 Illusion",
                  "Whenever this creature blocks a creature, you may return this creature to its owner's hand. If you do, you may put a creature card "
                  "from your hand onto the battlefield blocking that creature.", ("1", "1"), "U"))
EXTRA.append(real("Dire Blunderbuss", "{3}{R}{R}", 5, "Artifact \u2014 Equipment",
                  "Equipped creature gets +3/+0 and has \"Whenever this creature attacks, you may sacrifice an artifact other than Dire Blunderbuss. "
                  "When you do, this creature deals damage equal to its power to target creature.\"\nEquip {1}", None, "R"))
EXTRA.append(real("Spare Rock", "{1}", 1, "Artifact", "", None))
EXTRA.append(real("Dralnu, Lich Lord", "{3}{U}{B}", 5, "Legendary Creature \u2014 Zombie Wizard",
                  "If damage would be dealt to Dralnu, sacrifice that many permanents instead.\n{T}: Target instant or sorcery card in your graveyard "
                  "gains flashback until end of turn. The flashback cost is equal to its mana cost. (You may cast that card from your graveyard for "
                  "its flashback cost. Then exile it.)", ("3", "3"), "UB"))
EXTRA.append(real("Lava Burst", "{X}{R}", 1, "Sorcery",
                  "Lava Burst deals X damage to any target. If Lava Burst would deal damage to a creature, that damage can't be prevented or dealt "
                  "instead to another permanent or player.", None, "R"))
EXTRA.append(real("Temporal Firestorm", "{5}{R}", 6, "Sorcery",
                  "Kicker {1}{W} and/or {1}{U} (You may pay an additional {1}{W} and/or {1}{U} as you cast this spell.)\nChoose up to X creatures "
                  "and/or planeswalkers you control, where X is the number of times this spell was kicked. Those permanents phase out.\n"
                  "Temporal Firestorm deals 5 damage to each creature and each planeswalker.", None, "R"))
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.fixture(autouse=True)
def _fresh_definitions():
    """The staged-untap tests (test_rules_untap_attempts45) swap in their own Leechcraft grammar and only clear the definition cache on teardown."""
    from app.rules import scripts

    yield
    scripts._cached.cache_clear()
    scripts.granted_ability.cache_clear()


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn, else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def move(s, name, zone, pid="p2"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})
    return s.state.cards[c.id]


@pytest.mark.parametrize("take", [True, False])
def test_binding_negotiation(cards, take):
    """Choosing a nonland card discards it and does nothing else; choosing none puts a face-up exiled card of theirs into their graveyard."""
    s = build(cards, ["Binding Negotiation"], ["Lightning Bolt", "Grizzly Bears"])
    bolt = move(s, "Lightning Bolt", "hand")
    move(s, "Grizzly Bears", "hand")
    exiled = move(s, "Island", "exile")
    mana(s, B=1, C=1)
    cast(s, "Binding Negotiation", ["p2"])
    answer(s, bolt.id if take else [])
    assert s.state.cards[bolt.id].zone == ("p2:graveyard" if take else "p2:hand")
    if not take:
        answer(s, exiled.id)
    assert s.state.cards[exiled.id].zone == ("p2:exile" if take else "p2:graveyard")
    check(s)


def test_carom(cards):
    """1 of Bolt's 3 damage to the Giant goes to the Bears instead (Giant 2, Bears 1); Carom draws a card."""
    s = build(cards, ["Carom", "Lightning Bolt", "Hill Giant", "Grizzly Bears"])
    giant, bears = (to_hand(s, n) for n in ("Hill Giant", "Grizzly Bears"))
    for c in (giant, bears):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    hand = len(s.state.zones["p1:hand"])
    mana(s, W=1, C=1, R=1)
    cast(s, "Carom", [giant.id, bears.id], target_counts=[1, 1])
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # Carom cast from hand, one card drawn
    cast(s, "Lightning Bolt", [giant.id])
    answer(s)
    assert (s.state.cards[giant.id].damage, s.state.cards[bears.id].damage) == (2, 1)
    check(s)


def test_bewitching_leechcraft(cards):
    """Two counters: untaps twice, spending one each time; with none left the host stays tapped through its untap step."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Bewitching Leechcraft", "Grizzly Bears"])
    bears = to_hand(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=2)
    mana(s, U=1, C=1)
    cast(s, "Bewitching Leechcraft", [bears.id])
    answer(s)
    assert s.state.cards[bears.id].tapped
    for turn, (tapped, counters) in zip((3, 5, 7), [(False, 1), (False, 0), (True, 0)], strict=True):
        until(s, lambda s, t=turn: s.state.turn.number == t and s.state.turn.phase == "main1")
        got = s.state.cards[bears.id]
        assert (got.tapped, got.counters.get("+1/+1", 0)) == (tapped, counters), turn
        if not tapped:
            act(s, "p1", type="tap", card_ids=[bears.id])
    check(s)


def test_leechcraft_stun_wins(cards):
    """616.1/614.5: the controller may order stun (122.1d) and Leechcraft; Leechcraft first still ends tapped with the stun counter gone AND a +1/+1 counter lost, so stun first (counter kept) is the only sensible pick."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Bewitching Leechcraft", "Grizzly Bears"])
    bears = to_hand(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=2)
    mana(s, U=1, C=1)
    cast(s, "Bewitching Leechcraft", [bears.id])
    answer(s)
    act(s, "p1", type="counter", card_ids=[bears.id], kind="stun", delta=1)
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    got = s.state.cards[bears.id]
    assert (got.tapped, got.counters.get("+1/+1", 0), got.counters.get("stun", 0)) == (True, 2, 0)


@pytest.mark.parametrize("pick", ["hand", "top"])
def test_psychotic_episode(cards, pick):
    """The chosen revealed card (hand or top of library) goes to the bottom of its owner's library; the other cards stay."""
    s = build(cards, ["Psychotic Episode"], ["Lightning Bolt", "Grizzly Bears"])
    bolt = move(s, "Lightning Bolt", "hand")
    lib = s.state.zones["p2:library"]
    top = lib[0]
    mana(s, B=1, C=2)
    cast(s, "Psychotic Episode", ["p2"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and {o.id for o in d.options} == {bolt.id, top}
    answer(s, bolt.id if pick == "hand" else top)
    chosen = bolt.id if pick == "hand" else top
    assert s.state.zones["p2:library"][-1] == chosen
    assert (bolt.id in s.state.zones["p2:hand"]) == (pick == "top")
    check(s)


def test_kosei_needs_all_three(cards):
    """The granted trigger shows up only once Kosei is enchanted and equipped and has a counter."""
    from app.rules.plan import Plan

    s = build(cards, ["Kosei, Penitent Warlord", "Plain Halo", "Plain Blade"])

    def granted():
        p = Plan(s.state, "p1", s.cards, None)
        return any(a.index >= 100 for a in p.ch(s.state.cards[kosei.id]).abilities)  # (granted abilities are indexed 100+)

    kosei, halo, blade = (to_hand(s, n) for n in ("Kosei, Penitent Warlord", "Plain Halo", "Plain Blade"))
    for c in (kosei, blade):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[halo.id], to={"player": "p1", "zone": "battlefield"})
    states = []
    for step in ("halo", "blade", "counter"):
        if step == "counter":
            act(s, "p1", type="counter", card_ids=[kosei.id], kind="+1/+1", delta=1)
        else:
            act(s, "p1", type="attach", card_ids=[halo.id if step == "halo" else blade.id], to=kosei.id)
        states.append(granted())
    assert states == [False, False, True]
    check(s)


def test_immard(cards):
    """Enters with none to remove: gains one. Attacks: removes it and (reflexive) deals 4 on top of combat damage; next attack none to remove, gains one, no reflexive damage."""
    from tests.test_rules_conditionals import attack, through_combat, until

    s = build(cards, ["Immard, the Stormcleaver"])
    mana(s, U=1, R=1, W=1, C=1)
    imm = cast(s, "Immard, the Stormcleaver")
    answer(s)
    assert s.state.cards[imm.id].counters.get("charge") == 1
    for turn, want, counters in ((3, 32, 0), (5, 28, 1)):
        until(s, lambda s, t=turn: s.state.turn.number == t and (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
        attack(s, (s.state.cards[imm.id], "p2"))
        answer(s, "pay", "0:0", "p2")  # pay to remove, mode 1, Bob (turn 5: nothing to remove, so no question at all)
        through_combat(s)
        assert (s.state.cards[imm.id].counters.get("charge", 0), life(s, "p2")) == (counters, want), turn
    check(s)


def test_xenosquirrels(cards, monkeypatch):
    """Each roll can be adjusted by removing a +1/+1 counter, repeatedly in one turn; the adjusted result is what the roll reads (706.2)."""
    from tests.test_rules_random_consequences import answer as pick
    from tests.test_rules_random_consequences import faces

    s = build(cards, ["Xenosquirrels", "Roll Probe"])
    sq = to_hand(s, "Xenosquirrels")
    act(s, "p1", type="move", card_ids=[sq.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="counter", card_ids=[sq.id], kind="+1/+1", delta=2)
    faces(monkeypatch, [3, 4])
    for direction in ("plus", "minus"):  # twice in one turn: no once-a-turn limit
        mana(s, R=1)
        cast(s, "Roll Probe")
        d = s.state.rules.decision
        pick(s, [next(o.id for o in d.options if o.id.startswith("roll_adjust42:"))])
        for ids in (["pay"], ["0"], [direction]):
            pick(s, ids)
    assert s.state.cards[sq.id].counters.get("+1/+1", 0) == 0
    assert life(s, "p1") == 40 + 4 + 3
    check(s)


@pytest.mark.parametrize("take", [True, False])
def test_frantic_scapegoat(cards, take):
    """Another creature entering while the Goat is suspected: suspect it instead (Goat no longer suspected), or decline and nothing changes."""
    s = build(cards, ["Frantic Scapegoat", "Hill Giant"])
    mana(s, R=1)
    cast(s, "Frantic Scapegoat")
    answer(s)
    mana(s, R=1, C=3)
    giant = cast(s, "Hill Giant")
    d = None
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and "Suspect one" in d.prompt:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and [o.id for o in d.options] == [giant.id]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[giant.id] if take else [])
    answer(s)
    names = {c.name for c in s.state.cards.values() if any(m.name == "Suspected" for m in c.effects)}
    assert names == ({"Hill Giant"} if take else {"Frantic Scapegoat"})
    check(s)


@pytest.mark.parametrize("madness,toughness,stolen", [(False, 2, True), (False, 3, False), (True, 3, True), (True, 4, False)])
def test_welcome_to_the_fold(cards, madness, toughness, stolen):
    """Hard cast: toughness 2 or less. Madness (discarded, X paid): toughness X or less (X = 3 here). A bigger creature stays put."""
    from tests.test_rules_wave12a_counters_keywords import real as _real  # noqa: F401

    s = build(cards, ["Welcome to the Fold", "Discard Probe"], ["Hill Giant", "Grizzly Bears"])
    victim = card_named(s, "Grizzly Bears" if toughness == 2 else "Hill Giant", "p2")
    act(s, "p2", type="move", card_ids=[victim.id], to={"player": "p2", "zone": "battlefield"})
    if toughness == 4:
        act(s, "p2", type="counter", card_ids=[victim.id], kind="+1/+1", delta=1)
    if not madness:
        mana(s, U=2, C=2)
        cast(s, "Welcome to the Fold", [victim.id])
        answer(s)
    else:
        to_hand(s, "Welcome to the Fold")
        mana(s, B=1)
        cast(s, "Discard Probe")
        mana(s, U=2, C=3)
        for pick in (["yes"], ["x:3"], [victim.id]):
            d = s.state.rules.decision
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        answer(s)
    assert (s.state.cards[victim.id].controller == "p1") == stolen
    check(s)


def test_aetherplasm(cards):
    """Blocks, returns itself to hand, puts Hill Giant from hand blocking the same attacker (509.4)."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Hill Giant"], ["Aetherplasm", "Hill Giant"])
    atk = card_named(s, "Hill Giant", "p1")
    act(s, "p1", type="move", card_ids=[atk.id], to={"player": "p1", "zone": "battlefield"})
    plasm = card_named(s, "Aetherplasm", "p2")
    act(s, "p2", type="move", card_ids=[plasm.id], to={"player": "p2", "zone": "battlefield"})
    big = card_named(s, "Hill Giant", "p2")
    act(s, "p2", type="move", card_ids=[big.id], to={"player": "p2", "zone": "hand"})
    until(s, lambda s: s.state.turn.number == 3 and (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": atk.id, "target": "p2"}])
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": plasm.id, "attacker_id": atk.id}])
    for pick in ("pay", big.id):  # (the trigger resolves: pay, then choose the Giant; stop before combat damage)
        for _ in range(3):
            d = s.state.rules.decision
            if d is None:
                act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
    assert s.state.cards[plasm.id].zone == "p2:hand"
    # the new Giant blocked the attacking Giant (the Aetherplasm was out of combat): combat damage traded them, and Bob took none
    assert (s.state.cards[big.id].zone, s.state.cards[atk.id].zone, life(s, "p2")) == ("p2:graveyard", "p1:graveyard", 40)
    check(s)


def test_dire_blunderbuss(cards):
    """The attack trigger may sacrifice only an artifact other than the Equipment; the reflexive hit deals damage equal to the equipped power (3+3)."""
    from tests.test_rules_conditionals import attack, through_combat, until

    s = build(cards, ["Dire Blunderbuss", "Hill Giant", "Spare Rock"], ["Grizzly Bears"])
    gi, gun, rock = (to_hand(s, n) for n in ("Hill Giant", "Dire Blunderbuss", "Spare Rock"))
    bears = card_named(s, "Grizzly Bears", "p2")
    for c in (gi, gun, rock):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="attach", card_ids=[gun.id], to=gi.id)
    until(s, lambda s: s.state.turn.number == 3 and (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    attack(s, (s.state.cards[gi.id], "p2"))
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["pay"])
    answer(s, bears.id)  # the Rock is the only legal sacrifice (the Equipment is excluded), so it is paid without a question
    through_combat(s)
    assert s.state.cards[rock.id].zone.endswith("graveyard") and s.state.cards[bears.id].zone.endswith("graveyard")
    assert s.state.cards[gun.id].zone.endswith("battlefield")
    check(s)


def test_dralnu(cards):
    """Bolt (3) on Dralnu: no damage is dealt, its controller sacrifices three permanents of their choice instead."""
    s = build(cards, ["Dralnu, Lich Lord", "Hill Giant", "Spare Rock", "Plain Blade", "Lightning Bolt"])
    dr, gi, rock, blade = (to_hand(s, n) for n in ("Dralnu, Lich Lord", "Hill Giant", "Spare Rock", "Plain Blade"))
    for c in (dr, gi, rock, blade):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, R=1)
    cast(s, "Lightning Bolt", [dr.id])
    answer(s, [gi.id, rock.id, blade.id])
    got = s.state.cards
    assert got[dr.id].zone.endswith("battlefield") and got[dr.id].damage == 0
    assert got[gi.id].zone.endswith("graveyard") and got[rock.id].zone.endswith("graveyard")
    check(s)


@pytest.mark.parametrize("spell", ["Lava Burst", "Lightning Bolt"])
def test_lava_burst_not_redirected(cards, spell):
    """Carom redirects 1 damage from the Giant to the Bears; Lava Burst's 3 damage to the Giant stays on the Giant, Bolt's does not."""
    s = build(cards, ["Carom", "Lightning Bolt", "Lava Burst", "Hill Giant", "Grizzly Bears"])
    giant, bears = (to_hand(s, n) for n in ("Hill Giant", "Grizzly Bears"))
    for c in (giant, bears):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, W=1, C=4, R=1)
    cast(s, "Carom", [giant.id, bears.id], target_counts=[1, 1])
    answer(s)
    cast(s, spell, [giant.id], **({"x_value": 3} if spell == "Lava Burst" else {}))
    answer(s)
    got = s.state.cards
    if spell == "Lava Burst":
        assert got[giant.id].zone.endswith("graveyard") and got[bears.id].damage == 0  # all 3 landed on the 3/3 Giant
    else:
        assert (got[giant.id].damage, got[bears.id].damage) == (2, 1)
    check(s)


@pytest.mark.parametrize("kicker,saved", [(0, 0), (1, 1), (3, 2)])
def test_temporal_firestorm(cards, kicker, saved):
    """X = times kicked: that many of your creatures (picked as it resolves) phase out and dodge the 5 damage; the rest die."""
    s = build(cards, ["Temporal Firestorm", "Hill Giant", "Grizzly Bears"])
    giant, bears = (to_hand(s, n) for n in ("Hill Giant", "Grizzly Bears"))
    for c in (giant, bears):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, R=1, W=1, U=1, C=7)
    cast(s, "Temporal Firestorm", kicker=kicker)
    answer(s, [giant.id, bears.id][:saved] if saved else [])
    zones = [s.state.cards[c.id].zone for c in (giant, bears)]
    assert sum(z.endswith("phased") for z in zones) == saved and sum(z.endswith("graveyard") for z in zones) == 2 - saved  # phased out: untouched
    check(s)
