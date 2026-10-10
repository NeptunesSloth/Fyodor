"""Wave 28D: "where X is" values that depend on an event or a result (CR 2026-09-25). Real Oracle text; every scenario checks the replay and
a save and a load.

* 603.3d / 601.2c: a triggered ability's targets are chosen as it is put on the stack, so "up to X target …, where X is the number of
  cards looked at while scrying this way" (Elrond, Elvish Mariner) and "… the number of nonland cards milled this way" (The Wise Mothman)
  are read from the trigger event then (701.22d, 603.2c); "this way" in a "one or more" batch trigger is that batch.
* 107.3c: the text defines X; 601.2c: the number of targets doesn't change after.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, pick, until_asked
from tests.wave9c_kit import build, card_named, check, mana, put, reloaded, to_hand

REAL = [
    ("Elrond, Master of Healing", "{2}{W}{U}", "Legendary Creature — Elf Noble", "3", "4",
     "Whenever you scry, put a +1/+1 counter on each of up to X target creatures, where X is the number of cards looked at while scrying this way.\n"
     "Whenever a creature you control with a +1/+1 counter on it becomes the target of a spell or ability an opponent controls, you may draw a card."),
    ("Elvish Mariner", "{2}{U}", "Creature — Elf Warrior", "2", "3",
     "Whenever this creature attacks, scry 1.\nWhenever you scry, tap up to X target nonland permanents, where X is the number of cards looked at while scrying this way."),
    ("The Wise Mothman", "{2}{G}{G}", "Legendary Creature — Mutant Insect", "3", "3",
     "Flying\nWhenever The Wise Mothman enters or attacks, each player gets a rad counter.\nWhenever one or more nonland cards are milled, put a +1/+1 "
     "counter on each of up to X target creatures, where X is the number of nonland cards milled this way."),
    ("Preordain", "{U}", "Sorcery", None, None, "Scry 2, then draw a card."),
    ("Thought Scour", "{U}", "Instant", None, None, "Target player mills two cards. Draw a card."),
    ("Opt", "{U}", "Instant", None, None, "Scry 1.\nDraw a card."),
    ("Celestine, the Living Saint", "{3}{W}{W}", "Legendary Creature — Angel", "4", "4",
     "Flying, lifelink\nHealing Tears — At the beginning of your end step, return target creature card with mana value X or less from your "
     "graveyard to the battlefield, where X is the amount of life you gained this turn."),
    ("Rodolf Duskbringer", "{3}{W}{B}", "Legendary Creature — Vampire Knight", "4", "4",
     "Flying, deathtouch, lifelink\nWhenever you gain life, Rodolf Duskbringer gains indestructible until end of turn.\nAt the beginning of your "
     "end step, you may pay {1}{W/B}. When you do, return target creature card with mana value X or less from your graveyard to the "
     "battlefield, where X is the amount of life you gained this turn."),
    ("Venerable Warsinger", "{1}{R}{W}", "Creature — Spirit Cleric", "3", "3",
     "Vigilance, trample\nWhenever this creature deals combat damage to a player, you may return target creature card with mana value X or "
     "less from your graveyard to the battlefield, where X is the amount of damage this creature dealt to that player."),
    ("Astelli Reclaimer", "{3}{W}{W}", "Creature — Human Artificer", "3", "3",
     "Flying\nWhen this creature enters, return target noncreature, nonland permanent card with mana value X or less from your graveyard to "
     "the battlefield, where X is the amount of mana spent to cast this creature.\nWarp {2}{W}"),
    ("Krile Baldesion", "{2}{W}{U}", "Legendary Creature — Human Wizard", "2", "4",
     "Lifelink\nTrace Aether — Whenever you cast a noncreature spell, you may return target creature card with mana value equal to that spell's "
     "mana value from your graveyard to your hand. Do this only once each turn."),
    ("Spellstutter Sprite", "{1}{U}", "Creature — Faerie Wizard", "1", "1",
     "Flash\nFlying\nWhen this creature enters, counter target spell with mana value X or less, where X is the number of Faeries you control."),
    ("Revitalize", "{1}{W}", "Instant", None, None, "You gain 3 life. Draw a card."),
    ("Hill Giant", "{3}{R}", "Creature — Giant", "3", "3", ""),
    ("Sol Ring", "{1}", "Artifact", None, None, "{T}: Add {C}{C}."),
    ("The Great Henge", "{7}{G}{G}", "Legendary Artifact", None, None,
     "This spell costs {X} less to cast, where X is the greatest power among creatures you control.\n{T}: Add {G}{G}. You gain 2 life.\n"
     "Whenever a nontoken creature you control enters, put a +1/+1 counter on it and draw a card."),
    ("Darksteel Plate", "{3}", "Artifact — Equipment", None, None, "Indestructible\nEquipped creature has indestructible.\nEquip {2}"),
]
EXTRA = [card(n, set_code="t28w", number=f"W{i:02d}", mana_cost=mc, cmc=float(len(mc.replace("{", "").split("}")) - 1), type_line=tl,
              colors=["W"] if "{W}" in mc else ["U"], color_identity=[], oracle_text=text, **({"power": p, "toughness": t} if p else {}))
         for i, (n, mc, tl, p, t, text) in enumerate(REAL)]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Elrond, Master of Healing", "Elvish Mariner", "The Wise Mothman"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def cast(s, name):
    spell = to_hand(s, name)
    act(s, "p1", type="cast_spell", card_id=spell.id, **({"targets": ["p1"]} if name == "Thought Scour" else {}))
    return spell


def finish_scry(s):
    """Answer the scry's own prompts (nothing to the bottom, the order as offered); the decision that follows is returned."""
    d = until_asked(s)
    for _ in range(6):
        if d is None or d.resume.get("step") == "trigger_group":
            return d
        if d.kind == "order":
            pick(s, *[o.id for o in d.options])
        else:
            pick(s)
        d = until_asked(s)
    raise AssertionError(d)


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


@pytest.mark.parametrize("scry", [2, 1])
def test_elrond_counts_the_cards_looked_at(cards, scry):
    s = build(cards, ["Elrond, Master of Healing", "Preordain", "Opt"])
    put(s, "Elrond, Master of Healing")
    mine = [creature(s, "p1", n) for n in ("Bear", "Cub", "Elf")]
    mana(s, U=1)
    cast(s, "Preordain" if scry == 2 else "Opt")
    d = finish_scry(s)
    assert d is not None and d.kind == "choose_cards"  # (Elrond's targets: up to X)
    assert d.max_choices == scry  # 603.3d / 601.2c: X = the cards looked at while scrying
    check(s)
    pick(s, mine[0].id)
    until_asked(s)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert counters(s, mine[0]) == 1 and counters(s, mine[1]) == 0
    check(s)


def test_elrond_scrying_with_a_short_library_looks_at_fewer(cards):
    s = build(cards, ["Elrond, Master of Healing", "Preordain"])
    put(s, "Elrond, Master of Healing")
    creature(s, "p1", "Bear")
    spell = to_hand(s, "Preordain")
    for c in list(s.state.zones["p1:library"][1:]):
        act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "graveyard"})  # (one card left)
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = finish_scry(s)
    assert d is not None and d.max_choices == 1  # 701.22d: one card was looked at
    check(s)


def test_elvish_mariner_taps_up_to_that_many(cards):
    s = build(cards, ["Elvish Mariner", "Preordain"], ["Llanowar Elves"])
    put(s, "Elvish Mariner")
    theirs = [creature(s, "p2", n) for n in ("Wolf", "Boar", "Ox")]
    mana(s, U=1)
    cast(s, "Preordain")
    d = finish_scry(s)
    assert d is not None and d.max_choices == 2
    with pytest.raises(ActionError):
        pick(s, *[t.id for t in theirs])
    pick(s, theirs[0].id, theirs[1].id)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert [s.state.cards[t.id].tapped for t in theirs] == [True, True, False]
    check(s)


def test_the_wise_mothman_counts_the_nonland_cards_milled(cards):
    s = build(cards, ["The Wise Mothman", "Thought Scour", "Preordain", "Opt"])
    put(s, "The Wise Mothman")
    mine = [creature(s, "p1", n) for n in ("Bear", "Cub", "Elf")]
    top = [card_named(s, n) for n in ("Preordain", "Opt")]
    for c in top:  # (the top two cards of the library: both nonland)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    mana(s, U=1)
    cast(s, "Thought Scour")
    d = until_asked(s)
    assert d is not None and d.kind == "choose_cards" and d.max_choices == 2  # (X = 2 nonland cards milled this way)
    check(s)
    pick(s, mine[0].id, mine[2].id)
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert [counters(s, m) for m in mine] == [1, 0, 1]
    check(s)


def test_the_wise_mothman_lands_are_not_counted(cards):
    s = build(cards, ["The Wise Mothman", "Thought Scour", "Preordain"])
    put(s, "The Wise Mothman")
    mine = [creature(s, "p1", n) for n in ("Bear", "Cub")]
    act(s, "p1", type="move", card_ids=[card_named(s, "Preordain").id], to={"zone": "library"}, position="top")
    mana(s, U=1)
    cast(s, "Thought Scour")  # (one nonland and one Forest milled)
    d = until_asked(s)
    assert d is not None and d.max_choices == 1
    check(s)


# -- "mana value X or less, where X is …" (107.3c, 603.3d) ------------------------------------------------------------------
BOUND = ["Celestine, the Living Saint", "Rodolf Duskbringer", "Venerable Warsinger", "Astelli Reclaimer", "Krile Baldesion"]


@pytest.mark.parametrize("name", [*BOUND, "Revitalize"])
def test_bound_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def graveyard(s, *names):
    out = []
    for n in names:
        c = card_named(s, n)
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
        out.append(c)
    return out


def until_target_choice(s, limit=80):
    """Pass priority (no attackers, nobody blocks) until a trigger asks its controller for targets."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") in ("trigger_group", "trigger_target"):
            return d
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            return d
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no target choice")


def settle_all(s, limit=40):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def gain(s, n=1):
    """Gain life with real cards (Revitalize: 3 each)."""
    for _ in range(n):
        mana(s, W=1, C=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Revitalize").id)
        settle_all(s)


def test_celestine_returns_a_creature_up_to_the_life_gained(cards):
    s = build(cards, ["Celestine, the Living Saint", "Revitalize", "Llanowar Elves", "Grizzly Bears", "Hill Giant"])
    put(s, "Celestine, the Living Saint")
    elves, bears, giant = graveyard(s, "Llanowar Elves", "Grizzly Bears", "Hill Giant")
    for n in range(1):
        mana(s, W=1, C=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Revitalize").id)
        settle_all(s)
    assert s.state.players["p1"].life == 43
    d = until_target_choice(s)
    assert {o.id for o in d.options} == {elves.id, bears.id}  # (X = 3: Hill Giant has mana value 4)
    assert giant.id not in {o.id for o in d.options}
    check(s)
    pick(s, bears.id)
    settle_all(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[giant.id].zone == "p1:graveyard"
    check(s)


def test_celestine_with_no_life_gained_has_no_legal_target(cards):
    s = build(cards, ["Celestine, the Living Saint", "Llanowar Elves"])
    put(s, "Celestine, the Living Saint")
    (elves,) = graveyard(s, "Llanowar Elves")
    d = until_target_choice(s)
    assert d is None or d.kind != "choose_one" or elves.id not in {o.id for o in d.options}  # (X = 0: nothing has mana value 0 or less)
    assert s.state.cards[elves.id].zone == "p1:graveyard"
    check(s)


def test_rodolf_pays_then_chooses_with_the_life_gained(cards):
    s = build(cards, ["Rodolf Duskbringer", "Revitalize", "Llanowar Elves", "Grizzly Bears", "Hill Giant", "Swamp", "Sol Ring"])
    put(s, "Rodolf Duskbringer")
    for n in ("Swamp", "Sol Ring"):  # (the payment's sources: {1}{W/B})
        put(s, n)
    elves, bears, giant = graveyard(s, "Llanowar Elves", "Grizzly Bears", "Hill Giant")
    gain(s)
    d = until_asked_end_step(s)
    assert [o.id for o in d.options] == ["pay", "decline"], (d.kind, d.prompt)
    pick(s, "pay")
    d = until_target_choice(s)
    assert {o.id for o in d.options} == {elves.id, bears.id}  # (X = 3: the life gained this turn)
    check(s)
    pick(s, elves.id)
    settle_all(s)
    assert s.state.cards[elves.id].zone == "p1:battlefield"
    check(s)


def until_asked_end_step(s, limit=80):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            return d
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never asked")


def test_venerable_warsinger_reads_the_damage_it_dealt(cards):
    s = build(cards, ["Venerable Warsinger", "Llanowar Elves", "Grizzly Bears", "Hill Giant"])
    ws = put(s, "Venerable Warsinger")
    s.state.rules.controlled_since[ws.id].turn = 0
    elves, bears, giant = graveyard(s, "Llanowar Elves", "Grizzly Bears", "Hill Giant")
    act(s, "p1", type="pass_priority")  # → declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ws.id, "target": "p2"}])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None and d.resume.get("step") in ("trigger_target", "trigger_group"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    # (a 3/3 deals 3 damage: mana value 3 or less — not the Hill Giant, 4; review 28D: the card's real power)
    assert {o.id for o in d.options} == {elves.id, bears.id}
    check(s)
    pick(s, bears.id)
    settle_all(s)
    for _ in range(4):
        if s.state.cards[bears.id].zone == "p1:battlefield":
            break
        d = s.state.rules.decision
        if d is not None:
            pick(s, "yes")
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[giant.id].zone == "p1:graveyard"
    check(s)


def test_astelli_reclaimer_reads_the_mana_spent_to_cast_it(cards):
    s = build(cards, ["Astelli Reclaimer", "Sol Ring", "Darksteel Plate", "The Great Henge"])
    sol, plate, henge = graveyard(s, "Sol Ring", "Darksteel Plate", "The Great Henge")
    spell = to_hand(s, "Astelli Reclaimer")
    mana(s, W=2, C=3)  # (five mana spent)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = until_target_choice(s)
    assert {o.id for o in d.options} == {sol.id, plate.id}  # (mana value 5 or less: not The Great Henge, 9)
    check(s)
    pick(s, plate.id)
    settle_all(s)
    assert s.state.cards[plate.id].zone == "p1:battlefield"
    check(s)


def test_astelli_reclaimer_put_onto_the_battlefield_spent_no_mana(cards):
    s = build(cards, ["Astelli Reclaimer", "Sol Ring"])
    (sol,) = graveyard(s, "Sol Ring")
    act(s, "p1", type="move", card_ids=[card_named(s, "Astelli Reclaimer").id], to={"player": "p1", "zone": "battlefield"})
    settle_all(s)
    assert s.state.cards[sol.id].zone == "p1:graveyard"  # (not cast: 0 mana was spent, nothing has mana value 0 or less)
    check(s)


def test_krile_returns_a_creature_with_the_spells_mana_value(cards):
    s = build(cards, ["Krile Baldesion", "Revitalize", "Revitalize", "Llanowar Elves", "Grizzly Bears", "Hill Giant"])
    put(s, "Krile Baldesion")
    elves, bears, giant = graveyard(s, "Llanowar Elves", "Grizzly Bears", "Hill Giant")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Revitalize").id)  # (mana value 2)
    d = until_target_choice(s)
    assert {o.id for o in d.options} == {bears.id}  # (only a creature card with mana value 2)
    check(s)
    pick(s, bears.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            pick(s, "yes") if d.kind == "confirm" else pick(s, *[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[bears.id].zone == "p1:hand" and s.state.cards[elves.id].zone == "p1:graveyard"
    # (603.2h: once each turn: a second spell this turn doesn't trigger it again)
    mana(s, W=1, C=1)
    second = next(c for c in s.state.cards.values() if c.name == "Revitalize" and c.zone in ("p1:hand", "p1:library"))
    act(s, "p1", type="move", card_ids=[second.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=second.id)
    assert s.state.rules.decision is None or (s.state.rules.decision.resume or {}).get("step") not in ("trigger_group", "trigger_target")
    settle_all(s)
    assert s.state.cards[giant.id].zone == "p1:graveyard"
    check(s)


def test_a_bound_target_survives_a_save_and_load(cards):
    s = build(cards, ["Celestine, the Living Saint", "Revitalize", "Llanowar Elves", "Grizzly Bears", "Hill Giant"])
    put(s, "Celestine, the Living Saint")
    elves, bears, giant = graveyard(s, "Llanowar Elves", "Grizzly Bears", "Hill Giant")
    gain(s)
    d = until_target_choice(s)
    assert {o.id for o in d.options} == {elves.id, bears.id}
    t = reloaded(s)  # (a save and a load in the middle of the choice)
    d2 = t.state.rules.decision
    assert d2 is not None and {o.id for o in d2.options} == {elves.id, bears.id}
    pick(t, elves.id)
    settle_all(t)
    assert t.state.cards[elves.id].zone == "p1:battlefield" and t.state.cards[bears.id].zone == "p1:graveyard"
    replay_ok = reloaded(t)
    assert replay_ok.state.cards[elves.id].zone == "p1:battlefield"


# (Jodah, the Unifier, with its real Oracle text — "a legendary nonland card with lesser mana value": tests/test_rules_review28d.py)


@pytest.mark.parametrize("name,countered", [("Llanowar Elves", True), ("Hill Giant", False)])
def test_spellstutter_sprite_counters_a_spell_up_to_the_faeries_it_has(cards, name, countered):
    s = build(cards, [name], ["Spellstutter Sprite"])
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    target_spell = to_hand(s, name)
    sprite = to_hand(s, "Spellstutter Sprite", "p2")
    mana(s, G=1, R=1, C=2)
    mana(s, "p2", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=target_spell.id)
    assert s.state.zones.get("stack") and s.state.rules.priority == "p2"
    act(s, "p2", type="cast_spell", card_id=sprite.id)  # (flash, in response)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and (d.resume or {}).get("step") in ("trigger_target", "trigger_group"):
            assert countered and {o.id for o in d.options} == {target_spell.id}  # (X = 1 Faerie: mana value 1 or less)
            check(s)
            pick(s, target_spell.id, pid="p2")
        elif d is not None:
            pick(s, *[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert (s.state.cards[target_spell.id].zone == "p1:graveyard") is countered
    check(s)
