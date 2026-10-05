"""Wave 25C: "If that spell would be put into a graveyard, exile it instead." after a cast permission (614.1a): the rider rides on the
permission an effect grants ("You may cast it this turn", "You may cast target … from your graveyard [this turn]") and on a cast
made as the effect resolves with its mana cost paid (608.2g); "Exile an instant or sorcery card at random from your graveyard"
(701.9b-style random choice: the table picks, the move records it) and "mana of any type can be spent to cast that spell" (609.4b).
Real Commander cards, Oracle text from the card database; every scenario replays from history and survives a save/load."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches
from tests.test_rules_refused_look import choose, decision, find, put

REAL = [
    card("Dire Fleet Daredevil", set_code="tst", number="C25-1", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Human Pirate",
         colors=["R"], color_identity=["R"], power="2", toughness="1", keywords=["First strike"],
         oracle_text="First strike\nWhen this creature enters, exile target instant or sorcery card from an opponent's graveyard. You may "
         "cast it this turn, and mana of any type can be spent to cast that spell. If that spell would be put into a graveyard, exile it "
         "instead."),
    card("Chandra, Acolyte of Flame", set_code="tst", number="C25-2", mana_cost="{1}{R}{R}", cmc=3.0,
         type_line="Legendary Planeswalker — Chandra", colors=["R"], color_identity=["R"], loyalty="4",
         oracle_text="0: Put a loyalty counter on each red planeswalker you control.\n0: Create two 1/1 red Elemental creature tokens. "
         "They gain haste. Sacrifice them at the beginning of the next end step.\n−2: You may cast target instant or sorcery card with "
         "mana value 3 or less from your graveyard. If that spell would be put into your graveyard, exile it instead."),
    card("Storm of Memories", set_code="tst", number="C25-3", mana_cost="{2}{R}{R}{R}", cmc=5.0, type_line="Sorcery", colors=["R"],
         color_identity=["R"], keywords=["Storm"], oracle_text="Storm (When you cast this spell, copy it for each spell cast before it "
         "this turn.)\nExile an instant or sorcery card with mana value 3 or less from your graveyard at random. You may cast it without "
         "paying its mana cost. If that spell would be put into a graveyard, exile it instead."),
    card("Sins of the Past", set_code="tst", number="C25-4", mana_cost="{4}{B}{B}", cmc=6.0, type_line="Sorcery", colors=["B"],
         color_identity=["B"], oracle_text="Until end of turn, you may cast target instant or sorcery card from your graveyard without "
         "paying its mana cost. If that spell would be put into your graveyard, exile it instead. Exile Sins of the Past."),
]
REAL += [
    card("Temple of the Dragon Queen", set_code="tst", number="C25-5", mana_cost="", cmc=0.0, type_line="Land",
         oracle_text="As this land enters, you may reveal a Dragon card from your hand. This land enters tapped unless you revealed a "
         "Dragon card this way or you control a Dragon.\n{T}: Add one mana of any color."),
    card("Shivan Dragon", set_code="tst", number="C25-6", mana_cost="{4}{R}{R}", cmc=6.0, type_line="Creature — Dragon", colors=["R"],
         color_identity=["R"], power="5", toughness="5", keywords=["Flying"], oracle_text="Flying\n{R}: This creature gets +1/+0 until "
         "end of turn."),
]
REAL += [
    card("Boonweaver Giant", set_code="tst", number="C25-7", mana_cost="{6}{W}", cmc=7.0, type_line="Creature — Giant Monk", colors=["W"],
         color_identity=["W"], power="4", toughness="4", oracle_text="When this creature enters, you may search your graveyard, hand, "
         "and/or library for an Aura card and put it onto the battlefield attached to this creature. If you search your library this "
         "way, shuffle."),
]
REAL += [
    card("Mission Briefing", set_code="tst", number="C25-8", mana_cost="{U}{U}", cmc=2.0, type_line="Instant", colors=["U"],
         color_identity=["U"], keywords=["Surveil"], oracle_text="Surveil 2, then choose an instant or sorcery card in your graveyard. "
         "You may cast it this turn. If that spell would be put into your graveyard, exile it instead. (To surveil 2, look at the top two "
         "cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)"),
]
REAL += [
    card("Garruk, Caller of Beasts", set_code="tst", number="C25-9", mana_cost="{4}{G}{G}", cmc=6.0, type_line="Legendary Planeswalker — Garruk",
         colors=["G"], color_identity=["G"], loyalty="4", oracle_text="+1: Reveal the top five cards of your library. Put all creature "
         "cards revealed this way into your hand and the rest on the bottom of your library in any order.\n−3: You may put a green creature "
         "card from your hand onto the battlefield.\n−7: You get an emblem with \"Whenever you cast a creature spell, you may search your "
         "library for a creature card, put it onto the battlefield, then shuffle.\""),
    card("Mordor on the March", set_code="tst", number="C25-10", mana_cost="{3}{B}{R}", cmc=5.0, type_line="Sorcery", colors=["B", "R"],
         color_identity=["B", "R"], keywords=["Storm"], oracle_text="Exile a creature card from your graveyard. Create a token that's a copy "
         "of it. It gains haste until end of turn. Exile it at the beginning of the next end step.\nStorm (When you cast this spell, copy it "
         "for each spell cast before it this turn.)"),
]
REAL += [
    card("Retreat to Coralhelm", set_code="tst", number="C25-11", mana_cost="{2}{U}", cmc=3.0, type_line="Enchantment", colors=["U"],
         color_identity=["U"], oracle_text="Landfall — Whenever a land you control enters, choose one —\n• You may tap or untap target creature.\n"
         "• Scry 1. (Look at the top card of your library. You may put that card on the bottom.)"),
]
REAL += [
    card("Dreadhorde Arcanist", set_code="tst", number="C25-12", mana_cost="{1}{R}", cmc=2.0, type_line="Creature — Zombie Wizard", colors=["R"],
         color_identity=["R"], power="1", toughness="3", keywords=["Trample"], oracle_text="Trample\nWhenever this creature attacks, you may "
         "cast target instant or sorcery card with mana value less than or equal to this creature's power from your graveyard without "
         "paying its mana cost. If that spell would be put into your graveyard, exile it instead."),
]
REAL += [
    card("Wildborn Preserver", set_code="tst", number="C25-13", mana_cost="{1}{G}", cmc=2.0, type_line="Creature — Elf Archer", colors=["G"],
         color_identity=["G"], power="2", toughness="2", keywords=["Reach", "Flash"], oracle_text="Flash (You may cast this spell any time you "
         "could cast an instant.)\nReach (This creature can block creatures with flying.)\nWhenever another non-Human creature you control "
         "enters, you may pay {X}. When you do, put X +1/+1 counters on this creature."),
    card("Electro, Assaulting Battery", set_code="tst", number="C25-14", mana_cost="{1}{R}{R}", cmc=3.0,
         type_line="Legendary Creature — Human Villain", colors=["R"], color_identity=["R"], power="2", toughness="3", keywords=["Flying"],
         oracle_text="Flying\nYou don't lose unspent red mana as steps and phases end.\nWhenever you cast an instant or sorcery spell, add "
         "{R}.\nWhen Electro leaves the battlefield, you may pay {X}. When you do, he deals X damage to target player."),
]
OURS = [c["name"] for c in REAL]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, n) for n in OURS] + [(2, "Lightning Bolt"), (1, "Counterspell"), (1, "Pacifism"), (2, "Grizzly Bears"), (20, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Lightning Bolt"), (1, "Counterspell"), (20, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    return s


def reload(s):
    return GameSession(s.history.rebuild(), cards=s.cards)


def test_wordings_read():
    both = scripts.parse_effects("Exile target instant or sorcery card from an opponent's graveyard. You may cast it this turn, and mana "
                                 "of any type can be spent to cast that spell. If that spell would be put into a graveyard, exile it instead.")
    assert both is not None
    grant = both[0][1]
    assert grant["do"] == "grant_play" and grant["spend"] == "type" and grant["exile_gy"] == "all" and "exile_own" not in grant
    mine = scripts.parse_effects("You may cast target instant or sorcery card from your graveyard this turn. If that spell would be put "
                                 "into your graveyard, exile it instead.")
    assert mine is not None and mine[0][0]["who"] == "target" and mine[0][0]["exile_own"] is True
    paid = scripts.parse_effects("You may cast target instant or sorcery card with mana value 3 or less from your graveyard. If that spell "
                                 "would be put into your graveyard, exile it instead.")
    assert paid is not None and paid[0][0]["do"] == "free_cast" and paid[0][0]["paid"] is True
    # mana of any type is for a permission, never a free cast or a bare cast-now; a limit read as it resolves stays refused
    assert scripts.parse_effects("You may cast target instant card from your graveyard without paying its mana cost, and mana of any "
                                 "type can be spent to cast that spell.") is None
    assert scripts.parse_effects("You may cast target instant card from your graveyard, and mana of any type can be spent to cast "
                                 "that spell.") is None
    assert scripts.parse_effects("You may cast target instant or sorcery card with mana value less than or equal to ~'s power from your "
                                 "graveyard.") is not None  # (the source's power: the selector reads it, legal again as it resolves)
    assert scripts.parse_effects("You may cast target instant or sorcery card with mana value less than or equal to that damage from your "
                                 "graveyard.") is None


def test_daredevil_casts_the_opponents_bolt_with_any_mana_and_it_is_exiled(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard", pid="p2")
    daredevil = put(s, "Dire Fleet Daredevil", "hand")
    mana(s, R=2)
    act(s, "p1", type="cast_spell", card_id=daredevil.id)
    pass_until_stack_empty(s)
    for _ in range(4):  # the target, the "may": whichever the engine asks first
        d = s.state.rules.decision
        if d is None:
            break
        choose(s, ["yes"] if d.kind == "confirm" else [bolt.id], resolve=True)
    assert s.state.rules.permissions and s.state.rules.permissions[0].exile_gy == "all"
    assert s.state.rules.permissions[0].spend == "type"
    mana(s, G=1)  # not red: any type may be spent (609.4b)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[bolt.id].zone == "p2:exile"  # exiled, not put into its owner's graveyard
    assert s.state.rules.exile_if_graveyard == []
    replay_matches(s)
    assert reload(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def test_chandra_casts_your_bolt_paying_its_cost_and_exiles_it(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    chandra = put(s, "Chandra, Acolyte of Flame", "battlefield")
    act(s, "p1", type="counter", card_ids=[chandra.id], kind="loyalty", delta=4)
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=chandra.id, ability=2, targets=[bolt.id])
    pass_until_stack_empty(s)
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [bolt.id]
    choose(s, [bolt.id])
    choose(s, ["p2"], resolve=True)
    assert s.state.players["p2"].life == 37 and s.state.players["p1"].mana == {"R": 1}  # (Electro added {R} when the Bolt was cast; X = 3 was paid)  # its mana cost was paid
    assert s.state.cards[bolt.id].zone == "p1:exile"
    replay_matches(s)


def test_chandra_may_decline_and_the_bolt_stays(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    chandra = put(s, "Chandra, Acolyte of Flame", "battlefield")
    act(s, "p1", type="counter", card_ids=[chandra.id], kind="loyalty", delta=4)
    act(s, "p1", type="activate_ability", card_id=chandra.id, ability=2, targets=[bolt.id])
    pass_until_stack_empty(s)
    decision(s, "free_cast_pick")
    choose(s, [])
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    replay_matches(s)


def test_storm_of_memories_exiles_one_card_at_random_and_casts_it_free(cards):
    s = build(cards)
    put(s, "Lightning Bolt", "graveyard")  # (a lone card: the random pick is that one)
    storm = put(s, "Storm of Memories", "hand")
    mana(s, R=3, G=2)
    act(s, "p1", type="cast_spell", card_id=storm.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    if d is not None and d.kind == "confirm":
        choose(s, ["yes"])
    bolt = find(s, "Lightning Bolt")
    d = decision(s, "free_cast_pick")
    assert [o.id for o in d.options] == [bolt.id]
    choose(s, [bolt.id])
    choose(s, ["p2"], resolve=True)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[bolt.id].zone == "p1:exile"
    replay_matches(s)


def test_sins_of_the_past_grants_the_cast_and_exiles_the_spell(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    sins = put(s, "Sins of the Past", "hand")
    mana(s, B=6)
    act(s, "p1", type="cast_spell", card_id=sins.id, targets=[bolt.id])
    pass_until_stack_empty(s)
    assert s.state.rules.permissions and s.state.rules.permissions[0].free and s.state.rules.permissions[0].exile_own
    act(s, "p1", type="cast_spell", card_id=bolt.id, free=True, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[bolt.id].zone == "p1:exile"
    assert s.state.cards[sins.id].zone == "p1:exile"
    replay_matches(s)


# -- 614.12a: "enters tapped unless you revealed a Dragon card this way or you control a Dragon" -------------------
def _temple(s):
    land = find(s, "Temple of the Dragon Queen")
    act(s, "p1", type="move", card_ids=[land.id], to={"zone": "hand", "player": "p1"})
    return land


def test_temple_enters_untapped_when_you_control_a_dragon_without_asking(cards):
    s = build(cards)
    land = _temple(s)
    put(s, "Shivan Dragon", "battlefield")
    put(s, "Forest", "hand")
    act(s, "p1", type="play_land", card_id=land.id)
    assert s.state.rules.decision is None  # public information: nothing to ask, nothing leaked
    assert s.state.cards[land.id].zone == "p1:battlefield" and not s.state.cards[land.id].tapped
    replay_matches(s)


def test_temple_asks_to_reveal_a_dragon_otherwise(cards):
    s = build(cards)
    land = _temple(s)
    dragon = put(s, "Shivan Dragon", "hand")
    act(s, "p1", type="play_land", card_id=land.id)
    d = s.state.rules.decision
    assert d is not None and dragon.id in {o.id for o in d.options}
    choose(s, [dragon.id])
    assert not s.state.cards[land.id].tapped and s.state.cards[dragon.id].zone == "p1:hand"
    replay_matches(s)
    s = build(cards)
    land = _temple(s)
    put(s, "Shivan Dragon", "hand")
    act(s, "p1", type="play_land", card_id=land.id)
    choose(s, ["none"])
    assert s.state.cards[land.id].tapped  # declined, no Dragon on the table
    replay_matches(s)


# -- 701.23 / 303.4f: "search … for an Aura card and put it onto the battlefield attached to this creature" ----------
def test_boonweaver_giant_fetches_an_aura_onto_itself_and_shuffles_the_library(cards):
    s = build(cards)
    pacifism = find(s, "Pacifism")
    giant = put(s, "Boonweaver Giant", "hand")
    mana(s, W=7)
    before = list(s.state.zones["p1:library"])
    act(s, "p1", type="cast_spell", card_id=giant.id)
    pass_until_stack_empty(s)
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            break
        ids = {o.id for o in d.options}
        choose(s, ["yes"] if "yes" in ids else ["library"] if "library" in ids else [pacifism.id], resolve=True)
    assert s.state.cards[pacifism.id].zone == "p1:battlefield"
    assert s.state.cards[pacifism.id].attached_to == giant.id
    assert list(s.state.zones["p1:library"]) != before  # the library was searched, so shuffled (701.24)
    replay_matches(s)


# -- 608.2d: "choose an instant or sorcery card in your graveyard" (nothing moves) then "You may cast it this turn" ---
def test_mission_briefing_chooses_a_graveyard_card_and_grants_its_cast(cards):
    s = build(cards)
    bolt = put(s, "Lightning Bolt", "graveyard")
    briefing = put(s, "Mission Briefing", "hand")
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=briefing.id)
    pass_until_stack_empty(s)
    for _ in range(4):  # the surveil: one card goes to the graveyard
        d = s.state.rules.decision
        if d is None:
            break
        choose(s, [d.options[0].id], resolve=True)
    assert s.state.cards[bolt.id].zone == "p1:graveyard"  # chosen, not moved
    assert [p.card for p in s.state.rules.permissions] == [bolt.id]
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 37 and s.state.cards[bolt.id].zone == "p1:exile"
    replay_matches(s)


# -- "You may put a creature card from your hand onto the battlefield" as a loyalty ability: the "may" is the choice itself --
@pytest.mark.parametrize("take", [True, False])
def test_garruk_may_put_a_green_creature_from_hand_onto_the_battlefield(cards, take):
    s = build(cards)
    garruk = put(s, "Garruk, Caller of Beasts", "battlefield")
    act(s, "p1", type="counter", card_ids=[garruk.id], kind="loyalty", delta=4)
    bear = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="activate_ability", card_id=garruk.id, ability=1)
    pass_until_stack_empty(s)
    d = decision(s)
    assert bear.id in {o.id for o in d.options}
    choose(s, [bear.id] if take else [], resolve=True)
    assert (s.state.cards[bear.id].zone == "p1:battlefield") is take
    replay_matches(s)


# -- 608.2c / 707.2: the exiled card is bound for "Create a token that's a copy of it" -------------------------------
def test_mordor_on_the_march_exiles_the_card_and_copies_it(cards):
    s = build(cards)
    bear = put(s, "Grizzly Bears", "graveyard")
    mordor = put(s, "Mordor on the March", "hand")
    mana(s, B=1, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=mordor.id)
    pass_until_stack_empty(s)
    assert s.state.cards[bear.id].zone == "p1:exile"
    tokens = [c for c in s.state.cards.values() if c.is_token and c.name == "Grizzly Bears" and c.zone == "p1:battlefield"]
    assert len(tokens) == 1
    replay_matches(s)


# -- a mode that is "You may tap or untap target creature": the "may" is choosing neither (modal trigger) -------------
def test_retreat_to_coralhelm_mode_may_tap_or_untap(cards):
    s = build(cards)
    put(s, "Retreat to Coralhelm", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    forest = put(s, "Forest", "hand")
    act(s, "p1", type="play_land", card_id=forest.id)
    seen = []
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            break
        seen.append((d.kind, [o.label for o in d.options]))
        ids = [o.id for o in d.options]
        pick = [bear.id] if bear.id in ids else ids[:1]
        choose(s, pick, resolve=True)
    assert [k for k, _ in seen] == ["choose_cards", "choose_one", "choose_one"] and "Do nothing" in seen[-1][1]  # the "may" is choosing neither
    assert s.state.cards[bear.id].tapped  # (the first option offered: tap it)
    replay_matches(s)


# -- a target whose mana value limit is the source's power (608.2b: legal again as it resolves) ------------------------
def test_dreadhorde_arcanist_only_targets_cards_up_to_its_power_and_exiles_the_cast(cards):
    from app.game.rules_state import ControlMark
    from tests.test_rules_conditionals import attack, until

    s = build(cards)
    arcanist = put(s, "Dreadhorde Arcanist", "battlefield")
    s.state.rules.controlled_since[arcanist.id] = ControlMark(controller="p1", turn=0)
    bolt = put(s, "Lightning Bolt", "graveyard")  # mana value 1
    counter = put(s, "Counterspell", "graveyard")  # mana value 2: more than its power
    act(s, "p1", type="pass_priority")  # → combat
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    attack(s, (arcanist, "p2"))
    d = decision(s)
    assert {o.id for o in d.options} == {bolt.id}  # (a lone legal target: the engine may even pick it)
    choose(s, [bolt.id], resolve=True)
    d = s.state.rules.decision
    if d is not None and (d.resume or {}).get("step") == "free_cast_pick":
        choose(s, [bolt.id])
        choose(s, ["p2"], resolve=True)
    assert s.state.players["p2"].life == 36  # the Bolt (3) and the unblocked Arcanist (1)
    assert s.state.cards[bolt.id].zone == "p1:exile" and s.state.cards[counter.id].zone == "p1:graveyard"
    replay_matches(s)


# -- 107.3f / 603.12: "you may pay {X}. When you do, …": the X paid is the reflexive ability's X ----------------------
def _answer_x(s, n, target=None):
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            break
        ids = {o.id for o in d.options}
        if f"x:{n}" in ids:
            choose(s, [f"x:{n}"], resolve=True)
        elif target is not None and target in ids:
            choose(s, [target], resolve=True)
        elif "yes" in ids or "pay" in ids:
            choose(s, ["yes" if "yes" in ids else "pay"], resolve=True)
        else:
            choose(s, sorted(ids)[:1], resolve=True)


def test_wildborn_preserver_puts_x_counters_on_itself_for_the_x_paid(cards):
    s = build(cards)
    preserver = put(s, "Wildborn Preserver", "battlefield")
    mana(s, G=1, C=3)  # the Bears cost {1}{G}; {2} is left for X
    bear = put(s, "Grizzly Bears", "hand")
    act(s, "p1", type="cast_spell", card_id=bear.id)
    pass_until_stack_empty(s)
    _answer_x(s, 2)
    assert s.state.cards[preserver.id].counters.get("+1/+1") == 2
    assert s.state.players["p1"].mana == {}  # {2} was paid
    replay_matches(s)


def test_electro_deals_x_damage_to_the_target_player_when_it_leaves(cards):
    s = build(cards)
    electro = put(s, "Electro, Assaulting Battery", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=4)  # {R} for the Bolt (Electro keeps unspent red mana), the rest for X
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[electro.id])
    pass_until_stack_empty(s)
    assert s.state.cards[electro.id].zone == "p1:graveyard"
    _answer_x(s, 3, target="p2")
    assert s.state.players["p2"].life == 37 and s.state.players["p1"].mana == {"R": 1}  # (Electro added {R} when the Bolt was cast; X = 3 was paid)
    replay_matches(s)
