"""Wave 32A: "the same name as" (CR 201.2, 201.2a, 109.1, 608.2c, 707.2) and "choose a [permanent] you control" (608.2d), real Oracle text
(tests/fixtures/wave32a_same_name_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 201.2a: two objects have the same name if they have a name in common; an object with no name (face down, 708.2a) has the same name as nothing, not
  even another nameless one. The name read is the object's own with the layers applied (a copy has the copied name, 707.2): Evil Twin's, Callidus
  Assassin's and Mocking Doppelganger's text name "this creature", which is whatever it copied.
* "all tokens that player controls with the same name as that permanent" (Legions to Ashes), "all other nonland permanents that player controls with
  the same name … until this creature leaves the battlefield" (Deputy of Detention), "all other cards with the same name as that card from your
  graveyard" (Echoing Return, Rat King): the others are not targets, they are whatever bears that name as the instruction is carried out.
* "that doesn't have the same name as a token you control" is a target restriction (The Apprentice's Folly); as an intervening "if" (Guardian Project) it
  looks at every other creature you control and every creature card in your graveyard; "a card in their graveyard" is the caster's (Dragonlord Kolaghan);
  "the exiled card" is the linked ability's (607.2a: Strata Scythe).
* 608.2d / 608.2c: "Then you may choose a token you control. If you do, each other token you control becomes a copy of that token." (Brudiclad) — the choice is
  made on resolution, it is declined by choosing nothing, and what follows runs only if something was chosen; "Choose a Giant creature you control. It deals
  damage equal to its power to target creature." (Crush Underfoot)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import card_names, coverage, mana_units, scripts, selectors
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave32a_same_name_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w32a", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
GAINED = [c["name"] for c in DATA if c["name"] not in ("Hill Giant", "Runeclaw Bear", "Vampire of the Dire Moon", "Gideon Jura")]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def settle(s, prefer=(), limit=60):
    """Resolve everything; a decision is answered with the first of ``prefer`` it offers (card names or option ids), else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for p in prefer for o in d.options if p in (o.id, o.label, s.state.cards[o.card_id].name if o.card_id in s.state.cards else None)]
            pick = want[: max(1, d.min_choices)] if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_phase(s, phase, turn=None, limit=200):
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
    raise AssertionError(f"never reached {phase} of turn {turn} (at {s.state.turn.phase} of turn {s.state.turn.number})")


def chars(s, c):
    return Plan(s.state, c.controller, s.cards, None).ch(s.state.cards[c.id])


def ab(s, c, do):
    """The index of the ability whose effects do ``do``."""
    return next(i for i, d in scripts.definitions(chars(s, c)).items() if any(e.get("do") == do for e in d.get("effects") or []))


def token(s, pid, name, type_line="Token Creature — Test", pt="1/1", **extra):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": pt.split("/")[0], "toughness": pt.split("/")[1],
                                                         "text": "", **extra})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.is_token)


def on_field(s, name):
    return [c for c in s.state.cards.values() if c.zone.endswith("battlefield") and chars(s, c).name == name]


def seasoned(s, *cs):
    """These creatures have been on the table since before the turn began (302.6: they may use {T} abilities)."""
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


@pytest.mark.parametrize("name", GAINED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# --- 201.2a: what counts as the same name -----------------------------------------------------------------------------------------


def test_names_are_shared_by_one_in_common_and_a_nameless_object_shares_none():
    bears, twin, split, ice = Characteristics(name="Grizzly Bears"), Characteristics(name="Grizzly Bears"), Characteristics(name="Fire // Ice"), Characteristics(name="Ice")
    down = Characteristics(name="", face_down=True)
    assert card_names.share(bears, twin) and card_names.share(split, ice) and not card_names.share(bears, ice)  # 201.2a: one name in common, even with more
    assert not card_names.share(down, down) and not card_names.share(down, bears) and not card_names.share(Characteristics(name=""), Characteristics(name=""))


# --- the source's name: a copy is what it copied (707.2, 201.2a) ----------------------------------------------------------------


def test_evil_twin_destroys_a_creature_with_the_name_it_copied_not_its_own_name(cards):
    s = build(cards, ["Evil Twin", "Grizzly Bears"], ["Grizzly Bears", "Llanowar Elves"])
    mine, theirs, elves = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    twin = to_hand(s, "Evil Twin")
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=twin.id)
    settle(s, prefer=[mine.id, "Yes"])
    assert chars(s, twin).name == "Grizzly Bears"  # (the copy has the copied name: nothing on it is called Evil Twin)
    seasoned(s, twin)
    i = ab(s, twin, "destroy")
    mana(s, U=1, B=1)
    with pytest.raises(ActionError):  # Llanowar Elves has another name
        act(s, "p1", type="activate_ability", card_id=twin.id, ability=i, targets=[elves.id])
    act(s, "p1", type="activate_ability", card_id=twin.id, ability=i, targets=[theirs.id])
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and zone_of(s, "Llanowar Elves", "p2") == "p2:battlefield"
    check(s)


def test_a_face_down_creature_has_no_name_so_it_is_not_the_same_name_as_its_own_card(cards):
    s = build(cards, ["Evil Twin", "Gravel Slinger"], ["Gravel Slinger"])
    mine, theirs = put(s, "Gravel Slinger"), put(s, "Gravel Slinger", "p2")
    twin = to_hand(s, "Evil Twin")
    mana(s, U=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=twin.id)
    settle(s, prefer=[mine.id, "Yes"])
    assert chars(s, twin).name == "Gravel Slinger"
    act(s, "p2", type="face_down", card_ids=[theirs.id], face_down=True)  # 708.2a: a 2/2 with no name
    assert s.state.cards[theirs.id].face_down and chars(s, theirs).name == ""
    seasoned(s, twin)
    mana(s, U=1, B=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=twin.id, ability=ab(s, twin, "destroy"), targets=[theirs.id])
    act(s, "p1", type="activate_ability", card_id=twin.id, ability=ab(s, twin, "destroy"), targets=[mine.id])  # its own card's face-up name does
    settle(s)
    assert zone_of(s, "Gravel Slinger", "p1") == "p1:graveyard" and s.state.cards[theirs.id].zone == "p2:battlefield"
    check(s)


def test_callidus_assassin_enters_tapped_as_a_copy_and_destroys_another_creature_with_that_name(cards):
    s = build(cards, ["Callidus Assassin", "Grizzly Bears"], ["Grizzly Bears", "Llanowar Elves"])
    mine, theirs, elves = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    killer = to_hand(s, "Callidus Assassin")
    mana(s, U=1, B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=killer.id)
    settle(s, prefer=[theirs.id, "Yes", mine.id])
    assert chars(s, killer).name == "Grizzly Bears" and s.state.cards[killer.id].tapped
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and s.state.cards[mine.id].zone == "p1:battlefield"  # (the target: up to one OTHER creature with that name)
    assert s.state.cards[elves.id].zone == "p2:battlefield" and s.state.cards[killer.id].zone == "p1:battlefield"  # (never itself: "other")
    check(s)


def test_mocking_doppelganger_goads_the_other_creatures_that_have_its_copied_name(cards):
    s = build(cards, ["Mocking Doppelganger", "Grizzly Bears"], ["Grizzly Bears", "Llanowar Elves"])
    mine, theirs, elves = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    twin = to_hand(s, "Mocking Doppelganger")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=twin.id)
    settle(s, prefer=[theirs.id, "Yes"])
    assert chars(s, twin).name == "Grizzly Bears"
    goaded = {c.id: bool(chars(s, c).goaded) if hasattr(chars(s, c), "goaded") else None for c in (mine, theirs, elves, twin)}
    from app.rules.keyword_actions import goaded_by

    assert goaded_by(chars(s, theirs)) and goaded_by(chars(s, mine)) and not goaded_by(chars(s, elves)) and not goaded_by(chars(s, twin)), goaded
    check(s)


# --- the target's name: "and all tokens / other cards … with the same name as that …" (608.2h, 608.2b) ------------------------------


def test_legions_to_ashes_exiles_the_target_and_that_players_tokens_with_its_name_only(cards):
    s = build(cards, ["Legions to Ashes", "Grizzly Bears"], ["Grizzly Bears", "Llanowar Elves"])
    target = put(s, "Grizzly Bears", "p2")
    copy_token = token(s, "p2", "Grizzly Bears", "Token Creature — Bear", "2/2")
    other_token = token(s, "p2", "Soldier", "Token Creature — Soldier")
    mine_token = token(s, "p1", "Grizzly Bears", "Token Creature — Bear", "2/2")  # (not that player's)
    mine_card = put(s, "Grizzly Bears")
    spell = to_hand(s, "Legions to Ashes")
    mana(s, W=1, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[target.id])
    settle(s)
    assert s.state.cards[target.id].zone == "p2:exile"
    assert copy_token.id not in s.state.cards or not s.state.cards[copy_token.id].zone.endswith("battlefield")  # (a token that left ceases to exist)
    assert s.state.cards[other_token.id].zone == "p2:battlefield"  # another name
    assert s.state.cards[mine_token.id].zone == "p1:battlefield" and s.state.cards[mine_card.id].zone == "p1:battlefield"  # another controller
    check(s)


def test_echoing_return_returns_every_card_with_the_name_from_your_graveyard_and_no_other(cards):
    s = build(cards, ["Echoing Return", "Grizzly Bears", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    elves = card_named(s, "Llanowar Elves")
    theirs = card_named(s, "Grizzly Bears", "p2")
    for c in (*bears, elves):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[theirs.id], to={"zone": "graveyard"})
    spell = to_hand(s, "Echoing Return")
    mana(s, B=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears[0].id])
    settle(s)
    assert all(s.state.cards[c.id].zone == "p1:hand" for c in bears)
    assert s.state.cards[elves.id].zone == "p1:graveyard" and s.state.cards[theirs.id].zone == "p2:graveyard"
    check(s)


def test_deputy_of_detention_exiles_the_other_permanents_with_the_name_until_it_leaves(cards):
    s = build(cards, ["Deputy of Detention", "Murder"], ["Grizzly Bears", "Llanowar Elves"])
    target, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    twin_token = token(s, "p2", "Grizzly Bears", "Token Creature — Bear", "2/2")
    mine = token(s, "p1", "Grizzly Bears", "Token Creature — Bear", "2/2")  # (not that player's)
    deputy = to_hand(s, "Deputy of Detention")
    mana(s, W=1, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=deputy.id)
    settle(s, prefer=[target.id])
    assert s.state.cards[target.id].zone == "p2:exile" and twin_token.id not in s.state.cards  # (the token went to exile and ceased to exist, 111.8)
    assert s.state.cards[elves.id].zone == "p2:battlefield" and s.state.cards[mine.id].zone == "p1:battlefield"
    check(s)
    murder = to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[deputy.id])  # it leaves: what it exiled returns (the token is gone for good, 111.8)
    settle(s)
    assert s.state.cards[deputy.id].zone == "p1:graveyard" and s.state.cards[target.id].zone == "p2:battlefield" and twin_token.id not in s.state.cards
    check(s)


# --- a target restriction and an intervening "if" on another permanent's name (201.2a, 603.4) ------------------------------------


def test_apprentices_folly_cannot_pick_a_creature_that_has_the_name_of_a_token_you_control(cards):
    s = build(cards, ["The Apprentice's Folly", "Grizzly Bears", "Llanowar Elves"], [])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    token(s, "p1", "Grizzly Bears", "Token Creature — Bear", "2/2")  # (a token with the same name as the nontoken Bears)
    saga = to_hand(s, "The Apprentice's Folly")
    target = next(d["target"]["what"] for d in scripts.definitions(chars(s, saga)).values() if d.get("target"))  # the chapters' "target nontoken creature … that doesn't …"
    plan = Plan(s.state, "p1", s.cards, None)
    legal = [c.id for c in (bears, elves) if selectors.matches(plan, selectors.from_key(target), s.state.cards[c.id], plan.ch(s.state.cards[c.id]), "p1", saga.id)]
    assert legal == [elves.id]  # 201.2a: the nontoken Bears has the name of a token you control
    mana(s, U=1, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=saga.id)
    settle(s, prefer=[elves.id])
    made = [c for c in on_field(s, "Llanowar Elves") if c.is_token]
    assert len(made) == 1 and "Reflection" in chars(s, made[0]).subtypes and "haste" in chars(s, made[0]).keywords  # (a copy of the Elves, the only legal target)
    assert not any(c.is_token and chars(s, c).name == "Grizzly Bears" and "Reflection" in chars(s, c).subtypes for c in s.state.cards.values())
    assert bears.id in s.state.cards
    check(s)


def test_guardian_project_draws_only_for_a_name_no_other_creature_or_graveyard_card_has(cards):
    s = build(cards, ["Guardian Project", "Grizzly Bears", "Grizzly Bears", "Llanowar Elves", "Llanowar Elves"], [])
    put(s, "Guardian Project")
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    elves = [c for c in s.state.cards.values() if c.name == "Llanowar Elves" and c.owner == "p1"]

    def hand():
        return len([c for c in s.state.cards.values() if c.zone == "p1:hand"])

    def enter(c):
        """Hand → battlefield by casting it: how many cards the hand gained (a draw is +1)."""
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
        h = hand()
        mana(s, G=1, C=1)
        act(s, "p1", type="cast_spell", card_id=c.id)
        settle(s)
        assert s.state.cards[c.id].zone == "p1:battlefield"
        return hand() - (h - 1)

    assert enter(bears[0]) == 1  # nothing else called Grizzly Bears: draw
    assert enter(bears[1]) == 0  # another Grizzly Bears on the battlefield: no draw
    act(s, "p1", type="move", card_ids=[elves[0].id], to={"zone": "graveyard"})
    assert enter(elves[1]) == 0  # a creature card with that name in the graveyard: no draw
    check(s)


def test_dragonlord_kolaghan_punishes_a_spell_with_the_name_of_a_card_in_its_casters_graveyard(cards):
    s = build(cards, ["Grizzly Bears", "Grizzly Bears"], ["Dragonlord Kolaghan"])
    put(s, "Dragonlord Kolaghan", "p2")
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[bears[0].id], to={"zone": "graveyard"})
    act(s, "p1", type="move", card_ids=[bears[1].id], to={"zone": "hand"})
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bears[1].id)
    settle(s)
    assert life(s, "p1") == 30  # (40 → 30: a Grizzly Bears is in its caster's graveyard)
    check(s)


# --- the cards a linked ability exiled (607.2a) ------------------------------------------------------------------------------------


def test_strata_scythe_counts_the_lands_on_the_battlefield_with_the_name_of_the_card_it_exiled(cards):
    s = build(cards, ["Strata Scythe", "Grizzly Bears"], ["Island"], forests=9)
    bears = put(s, "Grizzly Bears")
    lib = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"]
    for c in lib[:3]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    isle = put(s, "Island", "p2")
    scythe = to_hand(s, "Strata Scythe")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=scythe.id)
    settle(s, prefer=[c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"])  # (the imprint: a Forest card from the library)
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    assert [c.name for c in exiled] == ["Forest"]
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=scythe.id, ability=2, targets=[bears.id])  # equip {3}
    settle(s)
    assert chars(s, bears).pt == (2 + 3, 2 + 3) and isle.id in s.state.cards  # three Forests; the Island has another name
    fourth = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[fourth.id], to={"player": "p1", "zone": "battlefield"})  # a fourth: the count follows the battlefield
    assert chars(s, bears).pt == (6, 6)
    check(s)


# --- "choose a [permanent] you control" (608.2d), "If you do" (608.2c) ---------------------------------------------------------------


def combat_with_brudiclad(cards):
    s = build(cards, ["Brudiclad, Telchor Engineer"], [])
    put(s, "Brudiclad, Telchor Engineer")
    soldier = token(s, "p1", "Soldier", "Token Creature — Soldier")
    goblin = token(s, "p1", "Goblin", "Token Creature — Goblin", "2/2")
    to_phase(s, "begin_combat")
    return s, soldier, goblin


def myr_of(s):
    return next(c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield" and "Myr" in chars(s, c).subtypes)


def test_brudiclad_makes_a_myr_then_may_make_each_other_token_a_copy_of_the_chosen_token(cards):
    s, soldier, goblin = combat_with_brudiclad(cards)
    d = None
    for _ in range(10):  # the trigger resolves: a 2/1 Myr, then the choice among the tokens
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and {s.state.cards[o.card_id].name for o in d.options} == {"Soldier", "Goblin", "Phyrexian Myr"}
    myr = next(s.state.cards[o.card_id] for o in d.options if s.state.cards[o.card_id].name == "Phyrexian Myr")
    assert d.min_choices == 0  # "you may": it can be declined
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[soldier.id])
    settle(s)
    assert chars(s, soldier).name == "Soldier" and chars(s, goblin).name == "Soldier" and chars(s, myr).name == "Soldier"  # 707.2: the copies
    assert chars(s, goblin).pt == (1, 1) and chars(s, myr).pt == (1, 1) and "Artifact" not in chars(s, myr).types
    assert s.state.cards[s.state.cards[soldier.id].id].zone == "p1:battlefield" and any(chars(s, c).name == "Brudiclad, Telchor Engineer" for c in s.state.cards.values() if c.zone.endswith("battlefield"))  # (Brudiclad is no token)
    check(s)


def test_brudiclad_declined_changes_nothing(cards):
    s, soldier, goblin = combat_with_brudiclad(cards)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])  # nothing chosen: "If you do" is false
    settle(s)
    myr = myr_of(s)
    assert chars(s, goblin).name == "Goblin" and chars(s, soldier).name == "Soldier" and chars(s, myr).name == "Phyrexian Myr" and chars(s, myr).pt == (2, 1)
    check(s)


def test_crush_underfoot_has_the_chosen_giant_deal_damage_equal_to_its_power(cards):
    s = build(cards, ["Crush Underfoot", "Hill Giant", "Grizzly Bears"], ["Llanowar Elves", "Grizzly Bears"])
    giant, bears = put(s, "Hill Giant"), put(s, "Grizzly Bears")
    victim, other = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    spell = to_hand(s, "Crush Underfoot")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:graveyard"  # 3 damage from the Giant (the Bears is no Giant, so never the choice)
    assert s.state.cards[other.id].zone == "p2:battlefield" and s.state.cards[giant.id].damage == 0 and s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_crush_underfoot_with_no_giant_to_choose_does_nothing(cards):
    s = build(cards, ["Crush Underfoot", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Grizzly Bears")
    victim = put(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Crush Underfoot")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    settle(s)
    assert s.state.cards[victim.id].zone == "p2:battlefield" and s.state.cards[victim.id].damage == 0  # (608.2d: chosen as it resolves; none to choose)
    check(s)


def test_sakashima_will_second_mode_turns_the_other_creatures_into_copies_of_the_chosen_one(cards):
    s = build(cards, ["Sakashima's Will", "Grizzly Bears", "Llanowar Elves", "Hill Giant"], [])
    bears, elves, giant = put(s, "Grizzly Bears"), put(s, "Llanowar Elves"), put(s, "Hill Giant")
    spell = to_hand(s, "Sakashima's Will")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, modes=[1])
    settle(s, prefer=[giant.id])
    assert chars(s, bears).name == "Hill Giant" and chars(s, elves).name == "Hill Giant" and chars(s, giant).name == "Hill Giant"
    assert chars(s, elves).pt == (3, 3)
    check(s)


def test_the_elderspell_puts_two_loyalty_counters_per_planeswalker_destroyed_on_the_one_you_choose(cards):
    s = build(cards, ["The Elderspell", "Gideon Jura"], ["Gideon Jura"])
    mine, theirs = put(s, "Gideon Jura"), put(s, "Gideon Jura", "p2")
    for c in (mine, theirs):
        act(s, "p1", type="counter", card_ids=[c.id], kind="loyalty", delta=6)  # (placed by hand: no loyalty came with it)
    before = s.state.cards[mine.id].counters.get("loyalty", 0)
    assert before == 6
    spell = to_hand(s, "The Elderspell")
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[theirs.id], target_counts=[1])  # ("any number of target planeswalkers": one)
    settle(s)
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and s.state.cards[mine.id].zone == "p1:battlefield"
    assert s.state.cards[mine.id].counters.get("loyalty", 0) == before + 2
    check(s)


def test_extraplanar_lens_adds_mana_only_for_lands_with_the_exiled_lands_name(cards):
    s = build(cards, ["Extraplanar Lens", "Mountain"], [])
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:2]
    mountain = put(s, "Mountain")
    for c in forests:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    lens = to_hand(s, "Extraplanar Lens")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=lens.id)
    settle(s, prefer=[forests[0].id, "Yes"])
    assert s.state.cards[forests[0].id].zone == "p1:exile"
    act(s, "p1", type="activate_ability", card_id=forests[1].id, ability=0)
    assert mana_units.visible_pool(s.state, "p1") == {"G": 2}  # (land mana is a provenance unit, wave 18B) a Forest was tapped: one more mana of the type it produced
    act(s, "p1", type="activate_ability", card_id=mountain.id, ability=0)
    assert mana_units.visible_pool(s.state, "p1") == {"G": 2, "R": 1}  # another name: no more
    check(s)


# --- a nonmatching name is not copied from (201.2a) ----------------------------------------------------------------------------


def test_marvin_has_the_activated_abilities_of_creatures_with_other_names_only(cards):
    s = build(cards, ["Marvin, Murderous Mimic", "Llanowar Elves"], [])
    marvin, elves = put(s, "Marvin, Murderous Mimic"), put(s, "Llanowar Elves")
    namesake = token(s, "p1", "Marvin, Murderous Mimic", "Token Artifact Creature — Toy", "2/2", text="{T}: Add {R}.")
    texts = [a.text for a in chars(s, marvin).abilities]
    assert "{T}: Add {G}." in texts  # the Elves' (another name)
    assert "{T}: Add {R}." not in texts  # a creature with Marvin's own name
    assert "{T}: Add {R}." in [a.text for a in chars(s, namesake).abilities] and elves.id in s.state.cards
    check(s)


# --- "all other cards with the same name" from the graveyard onto the battlefield (Rat King) ------------------------------------------


def test_rat_king_returns_every_card_with_the_name_tapped(cards):
    s = build(cards, ["Rat King, Verminister", "Grizzly Bears", "Grizzly Bears", "Llanowar Elves"], [])
    king = put(s, "Rat King, Verminister")
    rats = [token(s, "p1", f"Rat {i}", "Token Creature — Rat") for i in range(3)]
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]
    elves = card_named(s, "Llanowar Elves")
    for c in (*bears, elves):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    seasoned(s, king)
    act(s, "p1", type="activate_ability", card_id=king.id, ability=ab(s, king, "return_card"), targets=[bears[0].id],
        cost_choices=[{"component": 1, "cards": [r.id for r in rats]}])  # ({T}, Sacrifice three Rats)
    settle(s)
    assert all(s.state.cards[c.id].zone == "p1:battlefield" and s.state.cards[c.id].tapped for c in bears)
    assert s.state.cards[elves.id].zone == "p1:graveyard" and all(r.id not in s.state.cards for r in rats)
    check(s)


def test_a_face_down_creature_does_not_have_the_same_name_as_another_permanent_and_a_face_up_twin_does(cards):
    s = build(cards, ["Gravel Slinger", "Gravel Slinger", "Grizzly Bears"], ["Gravel Slinger"])
    a, b = put(s, "Gravel Slinger"), put(s, "Gravel Slinger", "p2")
    plan = Plan(s.state, "p1", s.cards, None)
    unique = selectors.parse("creature that doesn't have the same name as another creature you control")
    assert unique is not None
    c = put(s, "Grizzly Bears")  # (a second creature of yours, not named like the Slinger)
    twin = next(x for x in s.state.cards.values() if x.name == "Gravel Slinger" and x.owner == "p1" and x.id != a.id)
    act(s, "p1", type="move", card_ids=[twin.id], to={"player": "p1", "zone": "battlefield"})
    plan = Plan(s.state, "p1", s.cards, None)
    assert not selectors.matches(plan, unique, s.state.cards[a.id], plan.ch(s.state.cards[a.id]), "p1")  # a face-up twin of yours
    act(s, "p1", type="face_down", card_ids=[twin.id], face_down=True)
    plan = Plan(s.state, "p1", s.cards, None)
    assert selectors.matches(plan, unique, s.state.cards[a.id], plan.ch(s.state.cards[a.id]), "p1")  # the twin no longer has the name (708.2a)
    assert selectors.matches(plan, unique, s.state.cards[twin.id], plan.ch(s.state.cards[twin.id]), "p1")  # nor does it share one
    assert selectors.matches(plan, unique, s.state.cards[c.id], plan.ch(s.state.cards[c.id]), "p1") and b.id in s.state.cards
    check(s)


def test_invader_parasite_looks_at_the_name_of_the_land_it_exiled_while_it_is_on_the_battlefield(cards):
    s = build(cards, ["Invader Parasite"], ["Island", "Mountain"])
    p2_lands = [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"]
    target = p2_lands[0]
    act(s, "p2", type="move", card_ids=[target.id], to={"player": "p2", "zone": "battlefield"})
    parasite = to_hand(s, "Invader Parasite")
    mana(s, R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=parasite.id)
    settle(s, prefer=[target.id])
    assert s.state.cards[target.id].zone == "p2:exile"
    trigger = next(d for d in scripts.definitions(chars(s, parasite)).values() if (d.get("cond") or {}).get("event") == "enter")
    sel = selectors.from_key(trigger["cond"]["sel"])
    plan = Plan(s.state, "p1", s.cards, None)
    other_island, mountain = p2_lands[1], next(c for c in s.state.cards.values() if c.name == "Mountain" and c.owner == "p2")
    hit = lambda c: selectors.matches(plan, sel, s.state.cards[c.id], plan.ch(s.state.cards[c.id]), "p1", parasite.id)  # noqa: E731
    act(s, "p2", type="move", card_ids=[other_island.id, mountain.id], to={"player": "p2", "zone": "battlefield"})
    plan = Plan(s.state, "p1", s.cards, None)
    assert hit(other_island) and not hit(mountain)  # a land an opponent controls with the exiled card's name
    check(s)
