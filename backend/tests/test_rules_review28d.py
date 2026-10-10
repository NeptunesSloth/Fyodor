"""Review of wave 28D (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 107.3c: "the value of X may change while that spell or ability is on the stack"; 608.2b: a target is checked again as the ability
  resolves. "Counter target spell with mana value X or less, where X is the number of Faeries you control" (Spellstutter Sprite) counts
  the Faeries as the target is chosen and again as it resolves: a Faerie that died meanwhile can make the spell an illegal target. A
  value settled when the ability triggers (an event's amount, the mana spent to cast the source) is read once.
* 601.2c: "up to X target creatures, where X is the number of nonland cards milled this way" (The Wise Mothman) has X as its only limit.
* 605.3a: a mana ability's chosen cost nested in a payment never silently hides an object: what the payment already uses is named.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, pick, until_asked
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

REAL = [
    ("Spellstutter Sprite", "{1}{U}", "Creature — Faerie Wizard", "1", "1",
     "Flash\nFlying\nWhen this creature enters, counter target spell with mana value X or less, where X is the number of Faeries you control."),
    ("Go-Shintai of Hidden Cruelty", "{3}{B}", "Legendary Enchantment Creature — Shrine", "2", "2",
     "Deathtouch\nAt the beginning of your end step, you may pay {1}. When you do, destroy target creature with toughness X or less, where X "
     "is the number of Shrines you control."),
    ("Unforgiving One", "{2}{B}", "Creature — Spirit", "2", "3",
     "Menace (This creature can't be blocked except by two or more creatures.)\nWhenever this creature attacks, return target creature card "
     "with mana value X or less from your graveyard to the battlefield, where X is the number of modified creatures you control. (Equipment, "
     "Auras you control, and counters are modifications.)"),
    ("The Wise Mothman", "{1}{B}{G}{U}", "Legendary Creature — Insect Mutant", "3", "3",
     "Flying\nWhenever The Wise Mothman enters or attacks, each player gets a rad counter.\nWhenever one or more nonland cards are milled, put a "
     "+1/+1 counter on each of up to X target creatures, where X is the number of nonland cards milled this way."),
    ("Traumatize", "{3}{U}{U}", "Sorcery", None, None, "Target player mills half their library, rounded down."),
    ("Ghoulcaller's Bell", "{1}", "Artifact", None, None, "{T}: Each player mills a card."),
    ("Jodah, the Unifier", "{W}{U}{B}{R}{G}", "Legendary Creature — Human Wizard", "5", "5",
     "Legendary creatures you control get +X/+X, where X is the number of legendary creatures you control.\nWhenever you cast a legendary spell "
     "from your hand, exile cards from the top of your library until you exile a legendary nonland card with lesser mana value. You may cast "
     "that card without paying its mana cost. Put the rest on the bottom of your library in a random order."),
    ("Krile Baldesion", "{W}{U}", "Legendary Creature — Dwarf Wizard", "2", "1",
     "Lifelink\nTrace Aether — Whenever you cast a noncreature spell, you may return target creature card with mana value equal to that spell's "
     "mana value from your graveyard to your hand. Do this only once each turn."),
    ("Celestine, the Living Saint", "{4}{W}", "Legendary Creature — Human Warrior", "3", "4",
     "Flying, lifelink\nHealing Tears — At the beginning of your end step, return target creature card with mana value X or less from your "
     "graveyard to the battlefield, where X is the amount of life you gained this turn."),
    ("Hill Giant", "{3}{R}", "Creature — Giant", "3", "3", ""),
    ("Ashnod's Altar", "{3}", "Artifact", None, None, "Sacrifice a creature: Add {C}{C}."),
    ("Doom Blade", "{1}{B}", "Instant", None, None, "Destroy target nonblack creature."),
    ("Blood Artist", "{1}{B}", "Creature — Vampire", "0", "1",
     "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life."),
    ("Giant Opportunity", "{2}{G}", "Sorcery", None, None,
     "You may sacrifice two Foods. If you do, create a 7/7 green Giant creature token. Otherwise, create three Food tokens. "
     "(They're artifacts with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")"),
]
EXTRA = [card(n, set_code="r28d", number=f"R{i:02d}", mana_cost=mc, cmc=float(sum(int(p) if p.isdigit() else 1 for p in mc[1:-1].split("}{"))),
              type_line=tl, colors=["B"] if "{B}" in mc else ["U"], color_identity=[], oracle_text=text,
              **({"power": p, "toughness": t} if p else {}))
         for i, (n, mc, tl, p, t, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Spellstutter Sprite", "Go-Shintai of Hidden Cruelty", "Unforgiving One", "The Wise Mothman",
                                  "Jodah, the Unifier"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def respond_on(s):
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"


def stack_names(s):
    return [s.state.cards[c].name if c in s.state.cards else c for c in s.state.zones.get("stack", [])]


def target_step(s):
    d = s.state.rules.decision
    return d is not None and (d.resume or {}).get("step") in ("trigger_target", "trigger_group")


# -- 107.3c / 608.2b: a count read again as the ability resolves ----------------------------------------------------------------
@pytest.mark.parametrize("faerie_dies", [False, True])
def test_spellstutter_sprite_counts_the_faeries_again_as_it_resolves(cards, faerie_dies):
    """Bob flashes in Spellstutter Sprite with another Faerie: X = 2, so Grizzly Bears (mana value 2) is a legal target. If Alice
    Lightning Bolts the other Faerie in response, X is 1 as the ability resolves and the Bears are an illegal target (608.2b)."""
    s = build(cards, ["Grizzly Bears", "Lightning Bolt"], ["Spellstutter Sprite"])
    respond_on(s)
    pixie = creature(s, "p2", "Pixie", "1/1", "Token Creature — Faerie")
    bears = to_hand(s, "Grizzly Bears")
    sprite = to_hand(s, "Spellstutter Sprite", "p2")
    mana(s, G=1, C=1)
    mana(s, "p2", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="cast_spell", card_id=sprite.id)
    for _ in range(10):
        if target_step(s):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {bears.id}  # (two Faeries: mana value 2 or less)
    pick(s, bears.id, pid="p2")
    assert stack_names(s)[-1] != "Grizzly Bears"  # (the ability is on the stack above the Bears)
    check(s)
    if faerie_dies:
        while s.state.rules.priority != "p1":
            act(s, s.state.rules.priority, type="pass_priority")
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[pixie.id])
        act(s, s.state.rules.priority, type="pass_priority")
        act(s, s.state.rules.priority, type="pass_priority")
        assert pixie.id not in s.state.cards or s.state.cards[pixie.id].zone != "p2:battlefield"
    for _ in range(10):
        if not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert (s.state.cards[bears.id].zone == "p1:battlefield") is faerie_dies  # (one Faerie left: 2 > 1, an illegal target)
    assert (s.state.cards[bears.id].zone == "p1:graveyard") is not faerie_dies
    check(s)


def until_decision(s, limit=80):
    """Pass priority (no attackers, nobody blocks) until someone is asked something."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers" and not target_step(s):
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            return d
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def resolve_all(s, limit=12):
    for _ in range(limit):
        if not s.state.zones.get("stack"):
            return
        act(s, s.state.rules.priority, type="pass_priority")


def shrine(s, name):
    act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": "Token Enchantment — Shrine"})
    return next(c for c in s.state.cards.values() if c.name == name)


@pytest.mark.parametrize("shrine_leaves", [False, True])
def test_go_shintai_counts_its_shrines_as_the_target_is_chosen_and_as_it_resolves(cards, shrine_leaves):
    """Go-Shintai of Hidden Cruelty and another Shrine: X = 2 as the reflexive ability is put on the stack (603.12), so a 2/2 is a legal
    target and a 3/3 isn't; if the other Shrine leaves before it resolves, X is 1 and the 2/2 is an illegal target (107.3c, 608.2b)."""
    s = build(cards, ["Go-Shintai of Hidden Cruelty", "Sol Ring"])
    go = put(s, "Go-Shintai of Hidden Cruelty")
    put(s, "Sol Ring")
    other = shrine(s, "Little Shrine")
    bear = creature(s, "p2", "Bear", "2/2")
    ogre = creature(s, "p2", "Ogre", "3/3")
    d = until_decision(s)
    assert [o.id for o in d.options] == ["pay", "decline"], d.prompt
    pick(s, "pay")
    d = until_decision(s)
    # (toughness 2 or less: the Bear, and Go-Shintai itself, a 2/2; not the 3/3)
    assert target_step(s) and {o.id for o in d.options} == {bear.id, go.id}, [o.label for o in d.options]
    respond_on(s)
    pick(s, bear.id)
    assert s.state.zones.get("stack")
    check(s)
    if shrine_leaves:
        act(s, "p1", type="move", card_ids=[other.id], to={"player": "p1", "zone": "graveyard"})
    resolve_all(s)
    assert (bear.id in s.state.cards and s.state.cards[bear.id].zone == "p2:battlefield") is shrine_leaves
    assert s.state.cards[ogre.id].zone == "p2:battlefield"
    check(s)


def test_unforgiving_one_counts_the_modified_creatures(cards):
    """X is the number of modified creatures Alice controls (700.9: a counter, an Equipment, an Aura she controls): one creature with a
    +1/+1 counter makes X 1 — Llanowar Elves (mana value 1) can come back, Merfolk Looter (2) can't."""
    s = build(cards, ["Unforgiving One", "Llanowar Elves", "Merfolk Looter"])
    one = put(s, "Unforgiving One")
    s.state.rules.controlled_since[one.id].turn = 0
    helper = creature(s, "p1", "Helper", "1/1")
    act(s, "p1", type="counter", card_ids=[helper.id], kind="+1/+1", delta=1)
    elves, looter = card_named(s, "Llanowar Elves"), card_named(s, "Merfolk Looter")
    for c in (elves, looter):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="pass_priority")  # → declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p2"}])
    d = until_decision(s)
    assert target_step(s) and {o.id for o in d.options} == {elves.id}
    check(s)
    pick(s, elves.id)
    resolve_all(s)
    assert s.state.cards[elves.id].zone == "p1:battlefield" and s.state.cards[looter.id].zone == "p1:graveyard"
    check(s)


def test_unforgiving_one_with_nothing_modified_has_no_target(cards):
    s = build(cards, ["Unforgiving One", "Llanowar Elves"])
    one = put(s, "Unforgiving One")
    s.state.rules.controlled_since[one.id].turn = 0
    elves = card_named(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": one.id, "target": "p2"}])
    assert not target_step(s)  # (X = 0: no creature card has mana value 0 or less; removed, 603.3d)
    assert s.state.cards[elves.id].zone == "p1:graveyard"
    check(s)


# -- 601.2c: X is the only limit -----------------------------------------------------------------------------------------------
def test_the_wise_mothman_can_target_more_than_twenty(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(1, "The Wise Mothman"), (1, "Traumatize"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(60, "Grizzly Bears")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    put(s, "The Wise Mothman")
    resolve_all(s)
    mine = [creature(s, "p1", f"Soldier {i}", "1/1") for i in range(24)]
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Traumatize").id, targets=["p2"])
    d = until_decision(s)
    milled = sum(1 for c in s.state.zones["p2:graveyard"] if s.state.cards[c].name == "Grizzly Bears")
    assert milled == 30 and target_step(s) and d.max_choices == len(mine) + 1  # (X = 30: every creature, the Mothman too)
    pick(s, *[c.id for c in mine[:22]])
    resolve_all(s)
    assert sum(s.state.cards[c.id].counters.get("+1/+1", 0) for c in mine) == 22
    check(s)


def test_the_wise_mothman_triggers_once_for_cards_milled_from_several_libraries_at_once(cards):
    """Ghoulcaller's Bell: "Each player mills a card." — one event (603.2c: "one or more" triggers once), X = both nonland cards."""
    s = build(cards, ["The Wise Mothman", "Ghoulcaller's Bell", "Grizzly Bears"], ["Hill Giant"])
    put(s, "The Wise Mothman")
    resolve_all(s)
    bell = put(s, "Ghoulcaller's Bell")
    for pid, name in (("p1", "Grizzly Bears"), ("p2", "Hill Giant")):
        act(s, pid, type="move", card_ids=[card_named(s, name, pid).id], to={"zone": "library"}, position="top")
    mine = [creature(s, "p1", f"Soldier {i}", "1/1") for i in range(3)]
    act(s, "p1", type="activate_ability", card_id=bell.id, ability=0)
    d = until_decision(s)
    assert target_step(s) and d.max_choices == 2, d.prompt
    pick(s, mine[0].id, mine[1].id)
    assert not target_step(s)  # (no second trigger)
    resolve_all(s)
    assert not target_step(s)
    assert [s.state.cards[c.id].counters.get("+1/+1", 0) for c in mine] == [1, 1, 0]
    check(s)


# -- Jodah, the Unifier (real Oracle text): "a legendary nonland card with lesser mana value" -------------------------------------
@pytest.mark.parametrize("cast_it", [True, False])
def test_jodah_finds_a_legendary_card_with_lesser_mana_value(cards, cast_it):
    """Alice casts Celestine (legendary, mana value 5) from her hand. From the top: Hill Giant (not legendary: exiled, passed over),
    then Go-Shintai (legendary, 4): found. It's cast free, or declined and put on the bottom with the rest."""
    s = build(cards, ["Jodah, the Unifier", "Celestine, the Living Saint", "Hill Giant", "Go-Shintai of Hidden Cruelty"])
    put(s, "Jodah, the Unifier")
    giant, shintai = card_named(s, "Hill Giant"), card_named(s, "Go-Shintai of Hidden Cruelty")
    act(s, "p1", type="move", card_ids=[shintai.id], to={"zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[giant.id], to={"zone": "library"}, position="top")
    mana(s, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Celestine, the Living Saint").id)
    asked = []
    for _ in range(16):
        d = s.state.rules.decision
        if d is not None:
            asked.append((d.kind, d.prompt, [o.id for o in d.options]))
            ids = [o.id for o in d.options]
            if "without paying" in d.prompt:
                assert ids == [shintai.id]  # (the legendary card with lesser mana value, not the Hill Giant)
                pick(s, *(ids if cast_it else []))
                continue
            pick(s, *ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    lib = s.state.zones["p1:library"]
    assert s.state.cards[giant.id].zone == "p1:library" and giant.id in lib[:2] + lib[-2:], asked
    assert s.state.cards[shintai.id].zone == ("p1:battlefield" if cast_it else "p1:library"), asked
    check(s)


# -- 605.3a: what a nested payment choice leaves out is said, never silently hidden ------------------------------------------------
def self_payment(s):
    for prefs in s.state.rules.prefs.values():
        prefs.payment = "self"


def test_the_altar_names_the_creature_the_payment_already_uses(cards):
    s = build(cards, ["Doom Blade", "Ashnod's Altar"])
    self_payment(s)
    put(s, "Ashnod's Altar")
    bear = creature(s, "p1", "Bear")
    cub = creature(s, "p1", "Cub")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Doom Blade").id, targets=[bear.id])
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Ashnod's Altar").id, ability=0)
    d = s.state.rules.decision  # (only the Cub is left: still asked, with the note, never chosen for her)
    assert d.kind == "choose_cards" and [o.id for o in d.options] == [cub.id] and "not offered: Bear" in d.prompt
    assert s.state.cards[cub.id].zone == "p1:battlefield"
    check(s)
    pick(s)  # (none: back to the payment)
    act(s, "p1", type="move", card_ids=[cub.id], to={"player": "p1", "zone": "graveyard"})
    with pytest.raises(ActionError, match="not offered: Bear"):
        act(s, "p1", type="activate_ability", card_id=card_named(s, "Ashnod's Altar").id, ability=0)
    check(s)


def test_a_death_trigger_from_the_nested_sacrifice_waits_until_the_spell_is_cast(cards):
    """605.4a-style timing: the creature sacrificed mid-payment dies now, but Blood Artist's ability waits until a player would receive
    priority (117.5, 603.3): after the spell is cast (601.2i), so it goes on the stack above the spell and the payment isn't interrupted."""
    s = build(cards, ["Giant Opportunity", "Ashnod's Altar", "Blood Artist"])
    self_payment(s)
    respond_on(s)
    put(s, "Ashnod's Altar")
    put(s, "Blood Artist")
    bear, cub = creature(s, "p1", "Bear"), creature(s, "p1", "Cub")
    spell = to_hand(s, "Giant Opportunity")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Ashnod's Altar").id, ability=0)
    pick(s, bear.id)
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "pay_mana" and s.state.rules.payment_outer is None  # (back in the payment, not a trigger)
    assert not s.state.zones.get("stack") and s.state.cards[spell.id].zone == "p1:hand"
    check(s)
    mana(s, G=1)
    d = s.state.rules.decision
    if d is not None and d.resume.get("step") == "pay_mana":
        pick(s, "pay")
    d = s.state.rules.decision
    assert target_step(s) and s.state.cards[spell.id].zone == "stack", (d and d.prompt)  # (the spell is cast; then the trigger is put)
    pick(s, "p2")
    assert stack_names(s)[0] == "Giant Opportunity" and len(s.state.zones["stack"]) == 2
    assert cub.id in s.state.cards
    check(s)


def test_a_controlled_player_s_altar_is_used_by_the_controller(cards):
    """723.5: Bob controls Alice's turn: he casts her spell and, mid-payment, sacrifices her creature to her Altar — the nested choice is
    his to make; Alice can't answer it."""
    from app.game.rules_state import PlayerControl

    s = build(cards, ["Giant Opportunity", "Ashnod's Altar"])
    self_payment(s)
    put(s, "Ashnod's Altar")
    bear, cub = creature(s, "p1", "Bear"), creature(s, "p1", "Cub")
    spell = to_hand(s, "Giant Opportunity")
    s.state.rules.player_control = [PlayerControl(controlled="p1", controller="p2", status="active", turn=s.state.turn.number)]
    act(s, "p2", type="cast_spell", card_id=spell.id)
    act(s, "p2", type="activate_ability", card_id=card_named(s, "Ashnod's Altar").id, ability=0)
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and d.player == "p1" and s.state.rules.payment_outer is not None
    with pytest.raises(Exception):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[cub.id])
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[bear.id])
    assert bear.id not in s.state.cards and s.state.players["p1"].mana.get("C") == 2
    assert s.state.rules.decision.resume["step"] == "pay_mana" and s.state.rules.payment_outer is None
    check(s)


def test_nothing_else_can_be_activated_while_the_nested_choice_is_open(cards):
    """No re-entrancy: while the Altar's creature is being chosen, that choice is answered first (a second activation, a land: refused)."""
    s = build(cards, ["Doom Blade", "Ashnod's Altar"])
    self_payment(s)
    put(s, "Ashnod's Altar")
    forest = card_named(s, "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    bear, cub, elf = creature(s, "p1", "Bear"), creature(s, "p1", "Cub"), creature(s, "p1", "Elf")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Doom Blade").id, targets=[bear.id])
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Ashnod's Altar").id, ability=0)
    nested = s.state.rules.decision
    for again in ({"card_id": card_named(s, "Ashnod's Altar").id, "ability": 0}, {"card_id": forest.id, "ability": 0}):
        with pytest.raises(ActionError):
            act(s, "p1", type="activate_ability", **again)
    assert s.state.rules.decision.id == nested.id and not s.state.cards[forest.id].tapped
    pick(s, cub.id)
    assert s.state.players["p1"].mana.get("C") == 2 and s.state.rules.decision.resume["step"] == "pay_mana"
    assert elf.id in s.state.cards and s.state.rules.payment_outer is None
    check(s)
