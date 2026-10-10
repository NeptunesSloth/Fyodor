"""Wave 26B review: resolution scenarios the builder's tests didn't play (real Oracle text; replay + save/load each).

* 508.1d / 611.2: "attacks this combat if able" ends with that combat; a requirement the token can't meet is ignored.
* 120 / 510.2: "that many" after combat damage is the damage dealt to that player (trample past a blocker), read even
  when the source died in the same damage step (603.10 isn't needed: the event happened while it was there).
* 603.2c: "Whenever one or more Birds you control attack, look at that many cards": one trigger, counting the Birds only.
* 118.12a / 119.4 / 118.3: "That player may <pay life | sacrifice>. If they don't, <effect>": that player chooses; a
  payment they can't make isn't made, and the effect happens.
* Perplex: "unless its controller discards their hand" — the spell's controller chooses; an empty hand can be discarded.
* 610.3b: Banishment leaving before its enters trigger resolves exiles nothing; 610.3c: the rest return under their owners' control; 111.7: an exiled token never returns.
* 702.16: the Centaur tokens' protection from black prevents a black creature's damage.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import until
from tests.test_rules_wave5j_token_copies import drive
from tests.wave9c_kit import build, card_named, check, life, mana, put

CARDS = [
    ("Legion Warboss", "{2}{R}", "Creature — Goblin Warrior", "2", "2",
     "Mentor\nAt the beginning of combat on your turn, create a 1/1 red Goblin creature token. That token gains haste until end of turn "
     "and attacks this combat if able."),
    ("Howlsquad Heavy", "{2}{R}", "Creature — Goblin Mercenary", "3", "3",
     "Start your engines!\nOther Goblins you control have haste.\nAt the beginning of combat on your turn, create a 1/1 red Goblin "
     "creature token. That token attacks this combat if able.\nMax speed — {T}: Add {R} for each Goblin you control."),
    ("Probe Raker", "{3}{U}", "Creature — Drake", "5", "4",
     "Trample\nWhenever this creature deals combat damage to a player, you may reveal that many cards from the top of your library. "
     "Put an artifact card revealed this way into your hand and the rest into your graveyard."),
    ("Choco, Seeker of Paradise", "{1}{G}", "Legendary Creature — Bird", "2", "2",
     "Whenever one or more Birds you control attack, look at that many cards from the top of your library. You may put one of them into "
     "your hand. Then put any number of land cards from among them onto the battlefield tapped and the rest into your graveyard."),
    ("Probe Bird", "{1}", "Creature — Bird", "1", "1", ""),
    ("Probe Imp", "{1}", "Creature — Imp", "1", "1", ""),
    ("Probe Brute", "{3}", "Creature — Ogre", "4", "4", ""),
    ("Probe Web", "{2}", "Enchantment", None, None,
     "At the beginning of each player's upkeep, that player may sacrifice a creature of their choice. If that player doesn't, you draw a card."),
    ("Probe Tomb", "{2}", "Enchantment", None, None,
     "At the beginning of each player's upkeep, that player may pay 2 life. If they don't, they lose 3 life."),
    ("Perplex", "{1}{U}{B}", "Instant", None, None,
     "Counter target spell unless its controller discards their hand.\nTransmute {1}{U}{B} ({1}{U}{B}, Discard this card: Search your "
     "library for a card with the same mana value as this card, reveal it, put it into your hand, then shuffle. Transmute only as a sorcery.)"),
    ("Probe Bear", "{1}", "Creature — Bear", "2", "2", ""),
    ("Banishment", "{2}{W}{W}", "Enchantment", None, None,
     "Flash\nWhen this enchantment enters, exile target nonland permanent an opponent controls and all other nonland permanents your "
     "opponents control with the same name as that permanent until this enchantment leaves the battlefield."),
    ("Probe Smash", "{W}", "Instant", None, None, "Destroy target enchantment."),
    ("Hunted Horror", "{1}{B}{B}", "Creature — Horror", "4", "4",
     "Trample\nWhen this creature enters, target opponent creates two 3/3 green Centaur creature tokens with protection from black."),
]
EXTRA = [card(n, set_code="r26b", number=f"R{i:02d}", mana_cost=mc, cmc=float(mc.count("}")), type_line=tl,
              colors=["B"] if "{B}" in mc else ["R"], color_identity=["R"], oracle_text=text, power=p, toughness=t)
         for i, (n, mc, tl, p, t, text) in enumerate(CARDS)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def three(cards, mine=(), theirs=(), third=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (30, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (30, "Island")])
    cara = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in third), (30, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Cara", cards=cara)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def ready(s, *cards):
    for c in cards:
        s.state.rules.controlled_since[c.id].turn = 0


def to_attackers(s):
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            return d
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no declare attackers")


def goblins(s):
    return [c for c in s.state.cards.values() if c.is_token and c.name == "Goblin" and c.zone == "p1:battlefield"]


def imposed(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).imposed


# -- attacks this combat if able --------------------------------------------------------------------------------------------
def test_warboss_requirement_ends_with_the_combat(cards):
    s = build(cards, ["Legion Warboss"], forests=30, islands=30)
    ready(s, put(s, "Legion Warboss"))
    to_attackers(s)
    [gob] = goblins(s)
    assert "must_attack" in imposed(s, gob)
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": gob.id, "target": "p2"}])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert "must_attack" not in imposed(s, gob)  # (611.2: "this combat" is over)
    check(s)


def test_heavy_token_without_haste_needn_t_attack(cards):
    """508.1d: a requirement the creature can't obey (summoning sick: the Heavy that gave it haste is gone) asks nothing."""
    s = build(cards, ["Howlsquad Heavy"], forests=30, islands=30)
    heavy = put(s, "Howlsquad Heavy")
    ready(s, heavy)
    to_attackers(s)
    [gob] = goblins(s)
    assert "must_attack" in imposed(s, gob)
    act(s, "p1", type="move", card_ids=[heavy.id], to={"zone": "graveyard"})
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[])
    check(s)


def test_heavy_token_with_haste_must_attack(cards):
    s = build(cards, ["Howlsquad Heavy"], forests=30, islands=30)
    heavy = put(s, "Howlsquad Heavy")
    ready(s, heavy)
    to_attackers(s)
    [gob] = goblins(s)
    to_attackers(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": heavy.id, "target": "p2"}])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": gob.id, "target": "p2"}])
    check(s)


# -- that many --------------------------------------------------------------------------------------------------------------
def test_that_many_is_the_damage_dealt_to_the_player_and_the_source_may_be_gone(cards):
    """Trample past a 4/4: 1 damage to Bob, so one card is revealed; the Raker died in that same damage."""
    s = build(cards, ["Probe Raker"], ["Probe Brute"], forests=30, islands=30)
    raker = put(s, "Probe Raker")
    ready(s, raker)
    brute = put(s, "Probe Brute", "p2")
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": raker.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": brute.id, "attacker_id": raker.id}])
    graveyard = len(s.state.zones["p1:graveyard"])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "divide")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[], amounts=[4 if o.id == brute.id else 1 for o in d.options])  # (lethal to the blocker, 702.19c)
    drive(s, choose=lambda d: ["yes"] if "yes" in {o.id for o in d.options} else None)
    assert life(s, "p2") == 40 - 1
    assert s.state.cards[raker.id].zone == "p1:graveyard"
    assert len(s.state.zones["p1:graveyard"]) == graveyard + 2  # the Raker and the one revealed Forest
    check(s)


def test_choco_counts_the_birds_that_attacked_once_for_all_defenders(cards):
    s = three(cards, ["Choco, Seeker of Paradise", "Probe Bird", "Probe Imp"])
    birds = [put(s, "Choco, Seeker of Paradise"), put(s, "Probe Bird")]
    imp = put(s, "Probe Imp")
    ready(s, *birds, imp)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    library = len(s.state.zones["p1:library"])
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": birds[0].id, "target": "p2"}, {"card_id": birds[1].id, "target": "p3"},
                                                      {"card_id": imp.id, "target": "p2"}])
    assert len(s.state.zones["stack"]) == 1
    drive(s)
    assert len(s.state.zones["p1:library"]) == library - 2  # (one trigger: two Birds; the Imp isn't one)
    check(s)


# -- that player may <cost>. If they don't, <effect> -------------------------------------------------------------------------
def upkeep_choice(s, pid):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == pid
          and s.state.turn.active_player == pid and s.state.rules.decision.kind not in ("declare_attackers", "declare_blockers"), limit=120)
    return s.state.rules.decision


def asked(s, pid):
    d = s.state.rules.decision
    return d is not None and d.player == pid and d.kind == "choose_one"


def answer(s, d, yes):
    assert d.kind == "choose_one" and {o.id for o in d.options} == {"pay", "decline"}
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if yes else "decline"])
    drive(s)


@pytest.mark.parametrize("pay", [True, False])
def test_pay_life_or_lose_life(cards, pay):
    s = build(cards, ["Probe Tomb"], forests=30, islands=30)
    put(s, "Probe Tomb")
    d = upkeep_choice(s, "p2")
    answer(s, d, pay)
    assert life(s, "p2") == (38 if pay else 37)
    check(s)


def test_pay_life_beyond_the_life_total_is_not_offered(cards):
    s = build(cards, ["Probe Tomb"], forests=30, islands=30)
    put(s, "Probe Tomb")
    act(s, "p1", type="set_life", player="p2", value=1)
    until(s, lambda s: s.state.rules.winner is not None or asked(s, "p2"), limit=120)
    assert not asked(s, "p2")
    assert life(s, "p2") == -2 and s.state.rules.winner == "p1"  # (119.4: 1 life can't pay 2; they lose 3)
    check(s)


def test_sacrifice_or_you_draw(cards):
    s = build(cards, ["Probe Web"], ["Probe Bear"], forests=30, islands=30)
    put(s, "Probe Web")
    bear = put(s, "Probe Bear", "p2")
    hand = len(s.state.zones["p1:hand"])
    d = upkeep_choice(s, "p2")
    answer(s, d, True)
    assert s.state.cards[bear.id].zone == "p2:graveyard" and len(s.state.zones["p1:hand"]) == hand
    check(s)


def test_nothing_to_sacrifice_means_you_draw(cards):
    s = build(cards, ["Probe Web"], forests=30, islands=30)
    put(s, "Probe Web")
    hand = len(s.state.zones["p1:hand"])
    until(s, lambda s: asked(s, "p2") or (s.state.turn.active_player == "p2" and s.state.turn.phase == "main1"), limit=120)
    assert not asked(s, "p2") and len(s.state.zones["p1:hand"]) == hand + 1  # (118.3: no creature, no offer)
    check(s)


# -- Perplex ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("hand,pay", [(True, True), (True, False), (False, True)])
def test_perplex_the_spell_s_controller_may_discard_their_hand(cards, hand, pay):
    s = build(cards, ["Probe Bear"], ["Perplex"], forests=30, islands=30)
    bear = card_named(s, "Probe Bear")
    perplex = card_named(s, "Perplex", "p2")
    act(s, "p2", type="move", card_ids=[perplex.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "hand"})
    mana(s, C=1)
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    act(s, "p1", type="cast_spell", card_id=bear.id)
    if not hand and s.state.zones["p1:hand"]:  # (701.9a: a hand of no cards is discarded all the same; Null Brooch / Bomat Courier rulings)
        act(s, "p1", type="move", card_ids=list(s.state.zones["p1:hand"]), to={"zone": "graveyard"})
    kept = list(s.state.zones["p1:hand"])
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    mana(s, "p2", U=1, B=1, C=1)
    act(s, "p2", type="cast_spell", card_id=perplex.id, targets=[bear.id])
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {"pay", "decline"}  # (the spell's controller chooses)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay" if pay else "decline"])
    drive(s)
    assert s.state.cards[bear.id].zone == ("p1:battlefield" if pay else "p1:graveyard")
    assert all(s.state.cards[c].zone == ("p1:graveyard" if pay else "p1:hand") for c in kept)
    check(s)


# -- Banishment -----------------------------------------------------------------------------------------------------------------
def cast_horror(s, opponent="p2"):
    horror = card_named(s, "Hunted Horror")
    act(s, "p1", type="move", card_ids=[horror.id], to={"zone": "hand"})
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=horror.id)
    drive(s, choose=lambda d: [opponent] if opponent in {o.id for o in d.options} else None)
    return horror, [c for c in s.state.cards.values() if c.is_token and c.name == "Centaur" and c.zone == f"{opponent}:battlefield"]


def banish(s, target):
    banishment = card_named(s, "Banishment")
    act(s, "p1", type="move", card_ids=[banishment.id], to={"zone": "hand"})
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=banishment.id)
    return banishment, lambda d: [target.id] if any(o.id == target.id for o in d.options) else None


def smash(s, banishment):
    c = card_named(s, "Probe Smash")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[banishment.id])
    drive(s)


def test_banishment_takes_every_opponent_s_copy_and_returns_them_to_their_controllers(cards):
    s = three(cards, ["Banishment", "Probe Imp", "Probe Smash"], ["Probe Imp"], ["Probe Imp"])
    mine, bobs, caras = put(s, "Probe Imp"), put(s, "Probe Imp", "p2"), put(s, "Probe Imp", "p3")
    act(s, "p1", type="set_controller", card_ids=[caras.id], player="p2")
    banishment, choose = banish(s, bobs)
    drive(s, choose=choose)
    assert s.state.cards[bobs.id].zone == "p2:exile" and s.state.cards[caras.id].zone == "p3:exile"
    assert s.state.cards[mine.id].zone == "p1:battlefield"  # (only the opponents' permanents)
    smash(s, banishment)
    assert s.state.cards[bobs.id].zone == "p2:battlefield" and s.state.cards[caras.id].zone == "p3:battlefield"
    assert s.state.cards[caras.id].controller == "p3"  # (610.3c: under its owner's control)
    check(s)


def test_banished_token_ceases_to_exist(cards):
    s = build(cards, ["Banishment", "Probe Smash", "Hunted Horror"], forests=30, islands=30)
    _, centaurs = cast_horror(s)
    assert len(centaurs) == 2
    banishment, choose = banish(s, centaurs[0])
    drive(s, choose=choose)
    assert not [c for c in s.state.cards.values() if c.is_token and c.name == "Centaur" and c.zone == "p2:battlefield"]
    smash(s, banishment)
    assert not [c for c in s.state.cards.values() if c.is_token and c.name == "Centaur" and c.zone.endswith("battlefield")]  # (111.7)
    check(s)


def test_banishment_gone_before_its_trigger_resolves_exiles_nothing(cards):
    """610.3b: the "until" event happened after it triggered, so nothing is exiled at all."""
    s = build(cards, ["Banishment"], ["Probe Imp"], forests=30, islands=30)
    imp = put(s, "Probe Imp", "p2")
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")
    banishment, choose = banish(s, imp)
    for _ in range(10):  # the enchantment resolves; its trigger goes on the stack, targeting the Imp
        d = s.state.rules.decision
        if s.state.cards[banishment.id].zone == "p1:battlefield" and d is None and s.state.zones.get("stack"):
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=choose(d) or [o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.zones.get("stack") and s.state.cards[banishment.id].zone == "p1:battlefield"
    act(s, "p1", type="move", card_ids=[banishment.id], to={"zone": "graveyard"})
    drive(s, choose=choose)
    assert s.state.cards[imp.id].zone == "p2:battlefield"
    check(s)


# -- Hunted Horror ------------------------------------------------------------------------------------------------------------
def test_centaur_protection_from_black_prevents_the_horror_s_damage(cards):
    s = build(cards, ["Hunted Horror"], forests=30, islands=30)
    horror, centaurs = cast_horror(s)
    centaur = centaurs[0]
    ready(s, horror)
    to_attackers(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": horror.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": centaur.id, "attacker_id": horror.id}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "divide")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[], amounts=[3 if o.id == centaur.id else 1 for o in d.options])
    drive(s)
    assert s.state.cards[centaur.id].zone == "p2:battlefield" and s.state.cards[centaur.id].damage == 0
    assert s.state.cards[horror.id].damage == 3 and life(s, "p2") == 39
    check(s)
