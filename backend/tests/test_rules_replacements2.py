"""Replacement and prevention effects, stage 2 (CR 614, 615, 616; app/rules/replace.py).

Real Commander-legal cards: their Oracle text (from the card database, 2026-09-30 snapshot) is
transcribed below as custom-text permanents named after the card. Every scenario checks the final
table and that replaying the recorded history reproduces it; scenarios with a choice also check
save / load and undo / redo.
"""

from __future__ import annotations

from app.game.session import GameSession
from app.game.state import zone_key
from tests.game_helpers import act, find, turn_on
from tests.test_rules_attachments import build, named, to_hand, token
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_suspend import until

# -- Oracle text (current, from data/cards.sqlite) --------------------------------------------------
PARALLEL_LIVES = ("If an effect would create one or more tokens under your control, it creates twice that many of "
                  "those tokens instead.")  # Parallel Lives
ANOINTED_PROCESSION = PARALLEL_LIVES  # Anointed Procession (same Oracle text)
DOUBLING_SEASON = (PARALLEL_LIVES + "\nIf an effect would put one or more counters on a permanent you control, it puts "
                   "twice that many of those counters on that permanent instead.")  # Doubling Season
HARDENED_SCALES = ("If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 "
                   "counters are put on it instead.")  # Hardened Scales
WINDING_CONSTRICTOR = ("If one or more counters would be put on an artifact or creature you control, that many plus one "
                       "of each of those kinds of counters are put on that permanent instead.\nIf you would get one or "
                       "more counters, you get that many plus one of each of those kinds of counters instead.")  # Winding Constrictor 2/3
VIZIER_OF_REMEDIES = ("If one or more -1/-1 counters would be put on a creature you control, that many -1/-1 counters "
                      "minus one are put on it instead.")  # Vizier of Remedies 2/1
XORN = ("If you would create one or more Treasure tokens, instead create those tokens plus an additional Treasure "
        "token.")  # Xorn 3/2
MARCHING_DUODRONE = "Whenever this creature attacks, each player creates a Treasure token."  # Marching Duodrone 2/2
OJER_TAQ = ("If one or more creature tokens would be created under your control, three times that many of those tokens "
            "are created instead.")  # Ojer Taq, Deepest Foundation (front face, 6/6 vigilance)
LABORATORY_MANIAC = ("If you would draw a card while your library has no cards in it, you win the game "
                     "instead.")  # Laboratory Maniac 2/2
NOTION_THIEF = ("Flash\nIf an opponent would draw a card except the first one they draw in each of their draw steps, "
                "instead that player skips that draw and you draw a card.")  # Notion Thief 3/1
THOUGHT_REFLECTION = "If you would draw a card, draw two cards instead."  # Thought Reflection
BOON_REFLECTION = "If you would gain life, you gain twice that much life instead."  # Boon Reflection
RHOX_FAITHMENDER = "Lifelink\n" + BOON_REFLECTION  # Rhox Faithmender 1/5
ANGEL_OF_VITALITY = "Flying\nIf you would gain life, you gain that much life plus 1 instead."  # Angel of Vitality (first lines)
SULFURIC_VORTEX = "If a player would gain life, that player gains no life instead."  # Sulfuric Vortex (second line)
TAINTED_REMEDY = "If an opponent would gain life, that player loses that much life instead."  # Tainted Remedy
TORBRAN = ("If a red source you control would deal damage to an opponent or a permanent an opponent controls, it deals "
           "that much damage plus 2 instead.")  # Torbran, Thane of Red Fell 2/4
GRATUITOUS_VIOLENCE = ("If a creature you control would deal damage to a permanent or player, it deals double that damage "
                       "instead.")  # Gratuitous Violence
FURNACE_OF_RATH = ("If a source would deal damage to a permanent or player, it deals double that damage to that permanent "
                   "or player instead.")  # Furnace of Rath
URZAS_ARMOR = "If a source would deal damage to you, prevent 1 of that damage."  # Urza's Armor
FIRE_SERVANT = "If a red instant or sorcery spell you control would deal damage, it deals double that damage instead."  # Fire Servant 4/3
AUTHORITY_OF_THE_CONSULS = "Creatures your opponents control enter tapped."  # Authority of the Consuls (first line)
# "Anger of the Gods deals 3 damage to each creature. If a creature dealt damage this way would die this turn, exile
# it instead." (Anger of the Gods) — as an activated ability of a custom permanent (the same effect text)
ANGER = "{1}: Anger deals 3 damage to each creature. If a creature dealt damage this way would die this turn, exile it instead."
# "Lava Coil deals 4 damage to target creature. If that creature would die this turn, exile it instead." (Lava Coil)
COIL = "{1}: Coil deals 1 damage to target creature. If that creature would die this turn, exile it instead."
# "All creatures get -2/-2 until end of turn. If a creature would die this turn, exile it instead." (Flaying Tendrils)
TENDRILS = "{1}: All creatures get -2/-2 until end of turn. If a creature would die this turn, exile it instead."


def rules(s):
    return s.state.rules


def permanent(s, pid, name, kind, text, colors=()):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token {kind} — Test", "text": text,
                                                       "colors": list(colors)})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def red_creature(s, pid, name, pt, text=""):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": p,
                                                       "toughness": t, "text": text, "colors": ["R"]})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def activate(s, card, pid="p1", index=0, **kw):
    act(s, pid, type="add_mana", player=pid, mana={"C": 1})
    act(s, pid, type="activate_ability", card_id=card.id, ability=index, **kw)
    pass_until_stack_empty(s)


def named_all(s, name, pid=None):
    return [c for c in s.state.cards.values() if c.name == name and (pid is None or c.controller == pid)]


def decision(s):
    return rules(s).decision


def answer(s, option):
    d = decision(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


def reload(s, cards):
    """The game saved and loaded (its history replayed into a new session)."""
    return GameSession(s.history.rebuild(), cards=cards)


def hand(s, pid):
    return s.state.zones.get(zone_key(pid, "hand"), [])


def library(s, pid):
    return s.state.zones.get(zone_key(pid, "library"), [])


def empty_library(s, pid):
    act(s, pid, type="move", card_ids=list(library(s, pid)), to={"player": pid, "zone": "graveyard"})


# -- tokens (111.2, 614.16, 616.1) ------------------------------------------------------------------
def test_parallel_lives_and_anointed_procession_commute_without_a_prompt(cards):
    s = build(cards)
    permanent(s, "p1", "Parallel Lives", "Enchantment", PARALLEL_LIVES)
    permanent(s, "p1", "Anointed Procession", "Enchantment", ANOINTED_PROCESSION)
    maker = token(s, "p1", "Maker", text="{1}: Create a 1/1 white Soldier creature token.")
    activate(s, maker)
    assert decision(s) is None  # ×2 ×2 either way: no 616.1 prompt
    assert len(named_all(s, "Soldier")) == 4
    replay_matches(s)


def test_xorn_and_doubling_season_order_is_the_creators(cards):
    s = build(cards)
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    token(s, "p1", "Xorn", "3/2", XORN)
    maker = token(s, "p1", "Maker", text="{1}: Create a Treasure token.")
    activate(s, maker)
    d = decision(s)
    assert d is not None and d.player == "p1" and d.resume["step"] == "replace_order" and d.kind == "confirm"
    labels = {o.id: o.label for o in d.options}
    # Doubling Season first: 1 → 2 → 3; Xorn first: 1 → 2 → 4
    assert "Doubling Season first" in labels["yes"] and "3 Treasure" in labels["yes"] and "4 Treasure" in labels["no"]
    assert not named_all(s, "Treasure")  # nothing is created before the choice (614.6)
    answer(s, "no")
    assert len(named_all(s, "Treasure")) == 4 and decision(s) is None
    replay_matches(s)


def test_each_player_creates_a_treasure_with_their_own_replacements_in_apnap_order(cards):
    """Marching Duodrone: each player's token creation is its own event, modified only by that
    player's effects (Doubling Season "under your control", Xorn "if you would create")."""
    s = table(cards, players=3)
    duo = creature(s, "p1", "Marching Duodrone", "2/2", MARCHING_DUODRONE)
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    creature(s, "p2", "Xorn", "3/2", XORN)
    automate(s)
    attack(s, (duo, "p2"))
    until(s, lambda s: len(named_all(s, "Treasure")) >= 5 or s.state.turn.phase == "main2")
    assert len(named_all(s, "Treasure", "p1")) == 2 and len(named_all(s, "Treasure", "p2")) == 2
    assert len(named_all(s, "Treasure", "p3")) == 1
    replay_matches(s)


def test_ojer_taq_triples_creature_tokens_only(cards):
    s = build(cards)
    token(s, "p1", "Ojer Taq, Deepest Foundation", "6/6", "Vigilance\n" + OJER_TAQ)
    soldiers = token(s, "p1", "Recruiter", text="{1}: Create a 1/1 white Soldier creature token.")
    treasure = token(s, "p1", "Hoarder", text="{1}: Create a Treasure token.")
    activate(s, soldiers)
    activate(s, treasure)
    assert len(named_all(s, "Soldier")) == 3 and len(named_all(s, "Treasure")) == 1 and decision(s) is None
    replay_matches(s)


# -- counters (122.6, 614.16, 616.1) ----------------------------------------------------------------
def test_doubling_season_hardened_scales_order_prompt_survives_reload_undo_and_redo(cards):
    s = build(cards)
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    permanent(s, "p1", "Hardened Scales", "Enchantment", HARDENED_SCALES)
    bear = token(s, "p1", "Bear")
    feeder = token(s, "p1", "Feeder", text="{1}: Put a +1/+1 counter on target creature.")
    activate(s, feeder, targets=[bear.id])
    d = decision(s)
    assert d is not None and d.player == "p1" and d.resume["step"] == "replace_order"
    assert d.kind == "confirm" and "616.1" in d.prompt
    labels = {o.id: o.label for o in d.options}
    # Doubling Season first: 1 → 2 → 3; Hardened Scales first: 1 → 2 → 4
    assert "Doubling Season" in labels["yes"] and "3 +1/+1" in labels["yes"] and "4 +1/+1" in labels["no"], labels
    assert not s.state.cards[bear.id].counters  # nothing happened yet (614.6)
    other = s.view("p2")["rules"]["decision"]
    assert "options" not in other or not other["options"]  # the choice is p1's
    s2 = reload(s, cards)
    act(s2, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    assert s2.state.cards[bear.id].counters == {"+1/+1": 4}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    assert s.state.cards[bear.id].counters == {"+1/+1": 4} and decision(s) is None
    replay_matches(s)
    live = s.state.model_dump(mode="json")
    s.undo("p1")
    assert decision(s) is not None and not s.state.cards[bear.id].counters
    s.redo("p1")
    assert s.state.model_dump(mode="json") == live


def test_the_other_order_and_a_remembered_answer(cards):
    s = build(cards)
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    permanent(s, "p1", "Hardened Scales", "Enchantment", HARDENED_SCALES)
    bear = token(s, "p1", "Bear")
    feeder = token(s, "p1", "Feeder", text="{1}: Put a +1/+1 counter on target creature.")
    activate(s, feeder, targets=[bear.id])
    d = decision(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"], remember="yes_this_turn")
    assert s.state.cards[bear.id].counters == {"+1/+1": 3}
    activate(s, feeder, targets=[bear.id])  # the same two effects again this turn: remembered
    assert decision(s) is None and s.state.cards[bear.id].counters == {"+1/+1": 6}
    replay_matches(s)


def test_commuting_counter_replacements_need_no_prompt(cards):
    """Hardened Scales and Winding Constrictor: +1 and +1 in either order."""
    s = build(cards)
    permanent(s, "p1", "Hardened Scales", "Enchantment", HARDENED_SCALES)
    token(s, "p1", "Winding Constrictor", "2/3", WINDING_CONSTRICTOR)
    bear = token(s, "p1", "Bear")
    theirs = token(s, "p2", "Wolf")
    feeder = token(s, "p1", "Feeder", text="{1}: Put a +1/+1 counter on each creature.")
    activate(s, feeder)
    assert decision(s) is None
    assert s.state.cards[bear.id].counters == {"+1/+1": 3}  # 1 + 1 + 1
    assert s.state.cards[theirs.id].counters == {"+1/+1": 1}  # not theirs: "a creature you control"
    replay_matches(s)


def test_three_effects_choose_one_then_again(cards):
    """616.1e / 616.1f: choose one to apply, then the process repeats with the rest."""
    s = build(cards)
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    permanent(s, "p1", "Hardened Scales", "Enchantment", HARDENED_SCALES)
    token(s, "p1", "Winding Constrictor", "2/3", WINDING_CONSTRICTOR)
    bear = token(s, "p1", "Bear")
    feeder = token(s, "p1", "Feeder", text="{1}: Put a +1/+1 counter on target creature.")
    activate(s, feeder, targets=[bear.id])
    d = decision(s)
    assert d is not None and d.kind == "choose_one" and len(d.options) == 3
    scales = next(o.id for o in d.options if o.label.startswith("Hardened Scales"))
    answer(s, scales)  # 1 → 2
    d = decision(s)  # Doubling Season and Winding Constrictor still don't commute: 4 + 1 = 5 or 3 × 2 = 6
    assert d is not None and d.kind == "confirm"
    labels = {o.id: o.label for o in d.options}
    assert "5" in labels["yes"] and "6" in labels["no"], labels
    answer(s, "no")
    assert s.state.cards[bear.id].counters == {"+1/+1": 6} and decision(s) is None
    replay_matches(s)


def test_counters_a_creature_enters_with_are_asked_about_before_it_enters(cards):
    """614.12a / 616.1: Test Ooze ("enters with a +1/+1 counter on it for each creature card in
    your graveyard") cast under Doubling Season and Hardened Scales: the order is chosen before it
    enters, then it enters with those counters (122.6)."""
    s = build(cards, "Test Ooze", "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[named(s, "Grizzly Bears").id], to={"zone": "graveyard"})
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    permanent(s, "p1", "Hardened Scales", "Enchantment", HARDENED_SCALES)
    ooze = to_hand(s, "Test Ooze")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1, "C": 1})
    act(s, "p1", type="cast_spell", card_id=ooze.id)
    pass_until_stack_empty(s)
    d = decision(s)
    assert d is not None and d.player == "p1" and d.resume["step"] == "stack_enter_choice" and "616.1" in d.prompt
    assert s.state.cards[ooze.id].zone == "stack"  # not yet entered (614.12a)
    scales_first = next(o.id for o in d.options if o.label.startswith("Hardened Scales"))
    answer(s, scales_first)
    assert s.state.cards[ooze.id].zone == "p1:battlefield" and s.state.cards[ooze.id].counters == {"+1/+1": 4}
    replay_matches(s)


def test_persist_under_winding_constrictor_and_vizier_of_remedies(cards):
    """Counters a permanent returns with (702.79a persist: "with a -1/-1 counter on it") are put on
    as it enters: Winding Constrictor adds one; Vizier of Remedies takes one away."""
    s = build(cards, "Test Persist Golem")  # 2/2, "This creature enters tapped.\nPersist"
    golem = named(s, "Test Persist Golem")
    act(s, "p1", type="move", card_ids=[golem.id], to={"zone": "battlefield"})
    constrictor = token(s, "p1", "Winding Constrictor", "2/3", WINDING_CONSTRICTOR)
    act(s, "p1", type="set_damage", card_ids=[golem.id], value=2)
    act(s, "p1", type="pass_priority")  # dies, persist returns it with 1 + 1 -1/-1 counters: a 0/0 (704.5f)
    assert s.state.cards[golem.id].zone == "p1:graveyard" and not s.state.zones.get("stack")
    returned = [e for e in rules(s).events if e.card == golem.id and e.kind == "counters"]
    assert [(e.counter, e.amount) for e in returned] == [("-1/-1", 2)]
    replay_matches(s)
    # with Vizier of Remedies instead: "minus one" → it returns with none (and can persist again)
    act(s, "p1", type="move", card_ids=[constrictor.id], to={"zone": "exile"})
    token(s, "p1", "Vizier of Remedies", "2/1", VIZIER_OF_REMEDIES)
    act(s, "p1", type="move", card_ids=[golem.id], to={"zone": "battlefield"})
    before = rules(s).object_id(golem.id)
    act(s, "p1", type="set_damage", card_ids=[golem.id], value=2)
    act(s, "p1", type="pass_priority")
    golem_now = s.state.cards[golem.id]
    assert golem_now.zone == "p1:battlefield" and rules(s).object_id(golem.id) != before  # it died and returned …
    assert not golem_now.counters  # … with no counter
    replay_matches(s)


def test_proliferate_goes_through_the_counter_replacements(cards):
    s = build(cards)
    permanent(s, "p1", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    bear = token(s, "p1", "Bear")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    prolif = token(s, "p1", "Proliferator", text="{1}: Proliferate.")
    activate(s, prolif)
    d = decision(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bear.id])
    assert s.state.cards[bear.id].counters == {"+1/+1": 3}  # one more, doubled
    replay_matches(s)


def test_winding_constrictor_gives_its_controller_one_more_counter(cards):
    s = build(cards)
    token(s, "p1", "Winding Constrictor", "2/3", WINDING_CONSTRICTOR)
    battery = token(s, "p1", "Battery", text="{1}: You get {E}{E}.")
    activate(s, battery)
    assert s.state.players["p1"].resources.get("energy") == 3
    replay_matches(s)


# -- draw (121, 614.11) -----------------------------------------------------------------------------
def test_laboratory_maniac_wins_instead_of_drawing_from_an_empty_library(cards):
    s = build(cards)
    token(s, "p1", "Laboratory Maniac", "2/2", LABORATORY_MANIAC)
    empty_library(s, "p1")
    drawer = token(s, "p1", "Scholar", text="{1}: Draw a card.")
    activate(s, drawer)
    assert rules(s).winner == "p1" and "p1" not in rules(s).drew_from_empty and "p2" in rules(s).lost
    replay_matches(s)


def test_laboratory_maniac_in_the_draw_step(cards):
    s = build(cards)
    token(s, "p2", "Laboratory Maniac", "2/2", LABORATORY_MANIAC)
    empty_library(s, "p2")
    until(s, lambda s: rules(s).winner is not None or s.state.turn.number == 3)
    assert rules(s).winner == "p2" and s.state.turn.active_player == "p2" and s.state.turn.phase == "draw"
    replay_matches(s)


def test_without_laboratory_maniac_an_empty_library_draw_loses(cards):
    s = build(cards)
    empty_library(s, "p1")
    drawer = token(s, "p1", "Scholar", text="{1}: Draw a card.")
    activate(s, drawer)
    assert "p1" in rules(s).lost and rules(s).winner == "p2"
    replay_matches(s)


def test_notion_thief_takes_the_opponents_draws_but_not_their_first_in_their_draw_step(cards):
    s = build(cards)
    token(s, "p1", "Notion Thief", "3/1", NOTION_THIEF)
    drawer = token(s, "p1", "Oracle", text="{1}: Target player draws a card.")
    mine, theirs = len(hand(s, "p1")), len(hand(s, "p2"))
    activate(s, drawer, targets=["p2"])
    assert len(hand(s, "p2")) == theirs and len(hand(s, "p1")) == mine + 1  # skipped; Alice drew instead
    replay_matches(s)
    # Bob's own draw step: the first card is his (504.1); a second one that step is Alice's
    permanent(s, "p2", "Howling Study", "Enchantment", "At the beginning of your draw step, draw a card.")
    mine, theirs = len(hand(s, "p1")), len(hand(s, "p2"))
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert len(hand(s, "p2")) == theirs + 1 and len(hand(s, "p1")) == mine + 1
    replay_matches(s)


def test_notion_thief_and_laboratory_maniac_the_drawing_player_chooses(cards):
    s = build(cards)
    token(s, "p1", "Notion Thief", "3/1", NOTION_THIEF)
    token(s, "p2", "Laboratory Maniac", "2/2", LABORATORY_MANIAC)
    empty_library(s, "p2")
    drawer = token(s, "p1", "Oracle", text="{1}: Target player draws a card.")
    activate(s, drawer, targets=["p2"])
    d = decision(s)
    assert d is not None and d.player == "p2" and d.resume["step"] == "replace_order"
    lab_first = "yes" if "Laboratory Maniac first" in {o.id: o.label for o in d.options}["yes"] else "no"
    answer(s, lab_first)
    assert rules(s).winner == "p2"
    replay_matches(s)


def test_thought_reflection_doubles_each_draw_and_two_of_them_quadruple(cards):
    s = build(cards)
    permanent(s, "p1", "Thought Reflection", "Enchantment", THOUGHT_REFLECTION)
    drawer = token(s, "p1", "Scholar", text="{1}: Draw a card.")
    before = len(hand(s, "p1"))
    activate(s, drawer)
    assert len(hand(s, "p1")) == before + 2 and decision(s) is None
    permanent(s, "p1", "Thought Reflection II", "Enchantment", THOUGHT_REFLECTION)
    before = len(hand(s, "p1"))
    activate(s, drawer)
    assert len(hand(s, "p1")) == before + 4 and decision(s) is None  # 614.5: each applies once per draw
    replay_matches(s)


# -- life (119.10) ----------------------------------------------------------------------------------
def test_boon_reflection_and_rhox_faithmender_quadruple_a_lifelink_gain(cards):
    s = table(cards)
    rhox = creature(s, "p1", "Rhox Faithmender", "1/5", RHOX_FAITHMENDER)
    act(s, "p1", type="create_token", player="p1", token={"name": "Boon Reflection", "type_line": "Token Enchantment — Test",
                                                          "text": BOON_REFLECTION})
    automate(s)
    attack(s, (rhox, "p2"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 39 and s.state.players["p1"].life == 44  # 1 × 2 × 2, no prompt (they commute)
    replay_matches(s)


def test_boon_reflection_and_angel_of_vitality_order(cards):
    s = build(cards)
    permanent(s, "p1", "Boon Reflection", "Enchantment", BOON_REFLECTION)
    token(s, "p1", "Angel of Vitality", "2/2", ANGEL_OF_VITALITY)
    gainer = token(s, "p1", "Healer", text="{1}: You gain 3 life.")
    activate(s, gainer)
    d = decision(s)
    assert d is not None and d.player == "p1"
    labels = {o.id: o.label for o in d.options}
    assert "Angel of Vitality first" in labels["yes"] and "8 life" in labels["yes"] and "7 life" in labels["no"], labels
    answer(s, "yes")  # (3 + 1) × 2
    assert s.state.players["p1"].life == 48
    replay_matches(s)


def test_sulfuric_vortex_and_boon_reflection_no_life_either_way(cards):
    s = build(cards)
    permanent(s, "p1", "Boon Reflection", "Enchantment", BOON_REFLECTION)
    permanent(s, "p2", "Sulfuric Vortex", "Enchantment", SULFURIC_VORTEX)
    gainer = token(s, "p1", "Healer", text="{1}: You gain 3 life.")
    activate(s, gainer)
    assert decision(s) is None and s.state.players["p1"].life == 40
    replay_matches(s)


def test_tainted_remedy_turns_an_opponents_gain_into_a_loss(cards):
    s = build(cards)
    permanent(s, "p1", "Tainted Remedy", "Enchantment", TAINTED_REMEDY)
    gainer = token(s, "p1", "Healer", text="{1}: Each player gains 2 life.")
    activate(s, gainer)
    assert s.state.players["p1"].life == 42 and s.state.players["p2"].life == 38
    gains = [e for e in rules(s).events if e.kind == "life_gain" and e.player == "p2"]
    assert not gains  # the replaced gain never happened (614.6): nothing to trigger on (603.2g)
    replay_matches(s)


# -- damage (120.4b, 614, 615) ----------------------------------------------------------------------
def test_torbran_and_gratuitous_violence_the_defending_player_chooses(cards):
    s = table(cards)
    brute = red_creature(s, "p1", "Brute", "2/2")
    red_creature(s, "p1", "Torbran, Thane of Red Fell", "2/4", TORBRAN)
    act(s, "p1", type="create_token", player="p1", token={"name": "Gratuitous Violence", "type_line": "Token Enchantment — Test",
                                                          "text": GRATUITOUS_VIOLENCE, "colors": ["R"]})
    automate(s)
    attack(s, (brute, "p2"))
    until(s, lambda s: (decision(s) is not None and decision(s).resume.get("step") == "replace_order")
          or s.state.turn.phase == "main2")
    d = decision(s)
    assert d is not None and d.player == "p2" and d.kind == "confirm"  # 616.1: the affected player
    labels = {o.id: o.label for o in d.options}
    # Gratuitous Violence first: 2 × 2 + 2 = 6; Torbran first: (2 + 2) × 2 = 8
    assert "Gratuitous Violence first" in labels["yes"] and "6 damage" in labels["yes"] and "8 damage" in labels["no"], labels
    s2 = reload(s, cards)
    act(s2, "p2", type="choose", decision_id=d.id, option_ids=["yes"])
    until(s2, lambda s: s.state.turn.phase == "main2")
    assert s2.state.players["p2"].life == 34
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["yes"])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 34
    replay_matches(s)


def test_torbran_only_adds_to_damage_to_opponents_and_their_permanents(cards):
    s = build(cards)
    red_creature(s, "p1", "Torbran, Thane of Red Fell", "2/4", TORBRAN)
    mine = token(s, "p1", "Mine", "5/5")
    theirs = token(s, "p2", "Theirs", "5/5")
    pinger = red_creature(s, "p1", "Pinger", "1/1", "{1}: Pinger deals 1 damage to any target.")
    activate(s, pinger, targets=[theirs.id])
    activate(s, pinger, targets=[mine.id])
    activate(s, pinger, targets=["p2"])
    assert s.state.cards[theirs.id].damage == 3 and s.state.cards[mine.id].damage == 1
    assert s.state.players["p2"].life == 37
    replay_matches(s)


def test_fire_servant_doubles_a_red_instant(cards):
    s = build(cards, "Lightning Bolt")
    red_creature(s, "p1", "Fire Servant", "4/3", FIRE_SERVANT)
    bolt = to_hand(s, "Lightning Bolt")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 34
    replay_matches(s)


def test_prevention_and_doubling_order_is_the_damaged_players(cards):
    """615.10 "prevent 1 of that damage" and 614 "double that damage" apply to the same event: its
    recipient chooses the order (616.1): (2 − 1) × 2 = 2 or 2 × 2 − 1 = 3."""
    s = build(cards)
    permanent(s, "p2", "Urza's Armor", "Artifact", URZAS_ARMOR)
    permanent(s, "p1", "Furnace of Rath", "Enchantment", FURNACE_OF_RATH)
    shock = token(s, "p1", "Shocker", text="{1}: Shocker deals 2 damage to any target.")
    activate(s, shock, targets=["p2"])
    d = decision(s)
    assert d is not None and d.player == "p2" and d.kind == "confirm"
    prevent_first = "yes" if "Urza's Armor first" in {o.id: o.label for o in d.options}["yes"] else "no"
    answer(s, prevent_first)
    assert s.state.players["p2"].life == 38
    replay_matches(s)


def test_doubled_lifelink_damage_gains_the_doubled_amount(cards):
    s = build(cards)
    permanent(s, "p1", "Furnace of Rath", "Enchantment", FURNACE_OF_RATH)
    leech = token(s, "p1", "Leech", "2/2", "Lifelink\n{1}: Leech deals 1 damage to any target.")
    activate(s, leech, index=1, targets=["p2"])
    assert s.state.players["p2"].life == 38 and s.state.players["p1"].life == 42
    replay_matches(s)


# -- "would die this turn, exile it instead" (614.1a, 611.2a) -------------------------------------------
def test_anger_of_the_gods_exiles_only_creatures_it_dealt_damage(cards):
    s = build(cards)
    permanent(s, "p1", "Mourner", "Enchantment", "Whenever a creature dies, you gain 1 life.")
    small = token(s, "p1", "Small", "2/2")
    big = token(s, "p2", "Big", "5/5")
    sheltered = token(s, "p2", "Sheltered", "1/1", "Prevent all damage that would be dealt to Sheltered.")
    anger = token(s, "p1", "Anger", "0/9", ANGER)
    activate(s, anger)
    assert small.id not in s.state.cards  # (a token: exiled, then it ceased to exist)
    assert s.state.players["p1"].life == 40  # it didn't die (614.6): no dies trigger (603.2g)
    assert s.state.cards[big.id].damage == 3 and s.state.cards[sheltered.id].damage == 0
    killer = token(s, "p1", "Killer", text="{1}: Destroy target creature.")
    activate(s, killer, targets=[sheltered.id])  # not dealt damage by it (prevented): dies normally
    assert sheltered.id not in s.state.cards and s.state.players["p1"].life == 41
    activate(s, killer, targets=[big.id])  # dealt damage by it: exiled instead, later this turn too
    assert big.id not in s.state.cards and s.state.players["p1"].life == 41
    replay_matches(s)


def test_that_creature_is_exiled_instead_this_turn_only(cards):
    s = build(cards)
    permanent(s, "p1", "Mourner", "Enchantment", "Whenever a creature dies, you gain 1 life.")
    coil = token(s, "p1", "Coil", "0/1", COIL)
    atraxa = find(s.state, "Atraxa, Praetors' Voice", "p2")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"zone": "battlefield"})
    activate(s, coil, targets=[atraxa.id])
    killer = token(s, "p1", "Killer", text="{1}: Destroy target creature.")
    activate(s, killer, targets=[atraxa.id])
    # 903.9a still applies: the commander was put into exile (not into a graveyard: no dies trigger)
    assert s.state.cards[atraxa.id].zone == "p2:exile" and s.state.players["p1"].life == 40
    d = decision(s)
    assert d is not None and d.player == "p2" and d.resume["step"] == "commander_zone"
    answer(s, "yes")
    assert s.state.cards[atraxa.id].zone == "p2:command"
    replay_matches(s)


def test_a_record_ends_with_the_turn(cards):
    s = build(cards)
    permanent(s, "p1", "Mourner", "Enchantment", "Whenever a creature dies, you gain 1 life.")
    coil = token(s, "p1", "Coil", "0/1", COIL)
    ogre = token(s, "p2", "Ogre", "4/4")
    activate(s, coil, targets=[ogre.id])
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    killer = token(s, "p2", "Killer", text="{1}: Destroy target creature.")
    activate(s, killer, pid="p2", targets=[ogre.id])
    assert ogre.id not in s.state.cards and s.state.players["p1"].life == 41  # it died this time
    replay_matches(s)


def test_if_a_creature_would_die_this_turn_applies_to_every_creature(cards):
    s = build(cards)
    permanent(s, "p1", "Mourner", "Enchantment", "Whenever a creature dies, you gain 1 life.")
    tendrils = token(s, "p1", "Tendrils", "5/5", TENDRILS)
    small = token(s, "p2", "Small", "2/2")
    activate(s, tendrils)
    assert small.id not in s.state.cards and s.state.players["p1"].life == 40
    later = token(s, "p2", "Later", "4/4")  # a creature that wasn't there: still covered (611.2c)
    killer = token(s, "p1", "Killer", text="{1}: Destroy target creature.")
    activate(s, killer, targets=[later.id])
    assert later.id not in s.state.cards and s.state.players["p1"].life == 40
    replay_matches(s)


# "All creatures lose trample until end of turn. If a creature would deal combat damage to a creature this turn, it
# deals double that damage to that creature instead." (Blind Fury) — as an activated ability (the same effect text)
BLIND_FURY = ("{1}: All creatures lose trample until end of turn. If a creature would deal combat damage to a creature this "
              "turn, it deals double that damage to that creature instead.")


def test_a_this_turn_replacement_record(cards):
    """611.2a: a replacement effect of a resolved ability lasts the turn: double combat damage to
    creatures (not to players), and not next turn."""
    s = table(cards)
    fury = creature(s, "p1", "Fury", "0/1", BLIND_FURY)
    brute = creature(s, "p1", "Brute", "2/2")
    runner = creature(s, "p1", "Runner", "1/1")
    wall = creature(s, "p2", "Wall", "0/5")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main 1
    activate(s, fury)
    assert [rec["event"] for rec in rules(s).replacements if rec.get("kind") == "replace"] == ["damage"]
    until(s, lambda s: s.state.turn.phase == "declare_attackers")
    attack(s, (brute, "p2"), (runner, "p2"))
    until(s, lambda s: decision(s) is not None and decision(s).kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": brute.id}])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.cards[wall.id].damage == 4 and s.state.players["p2"].life == 39  # 2 × 2 to the Wall; 1 to Bob
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "declare_attackers")
    act(s, "p1", type="set_damage", card_ids=[wall.id], value=0)
    attack(s, (brute, "p2"))
    until(s, lambda s: decision(s) is not None and decision(s).kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": wall.id, "attacker_id": brute.id}])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.cards[wall.id].damage == 2  # the record ended with its turn
    assert fury.id in s.state.cards
    replay_matches(s)


# -- others enter tapped (614.1d, 614.12) -----------------------------------------------------------
def test_authority_of_the_consuls_opponents_creatures_enter_tapped(cards):
    s = build(cards)
    permanent(s, "p1", "Authority of the Consuls", "Enchantment", AUTHORITY_OF_THE_CONSULS)
    maker = token(s, "p1", "Maker", text="{1}: Each player creates a 1/1 white Soldier creature token.")
    activate(s, maker)
    mine = named_all(s, "Soldier", "p1")
    theirs = named_all(s, "Soldier", "p2")
    assert len(mine) == 1 and len(theirs) == 1 and not mine[0].tapped and theirs[0].tapped
    assert not [e for e in rules(s).events if e.card == theirs[0].id and e.kind == "tapped"]  # entered tapped (614.1d)
    replay_matches(s)


# -- several players' choices at once (616.1: APNAP) ------------------------------------------------
def test_each_players_choice_in_apnap_order(cards):
    s = table(cards, players=3)
    for pid in ("p1", "p2", "p3"):
        act(s, pid, type="create_token", player=pid, token={"name": f"Boon Reflection {pid}", "type_line": "Token Enchantment — Test",
                                                            "text": BOON_REFLECTION})
        creature(s, pid, f"Angel of Vitality {pid}", "2/2", ANGEL_OF_VITALITY)
    healer = creature(s, "p2", "Healer", "1/1", "{1}: Each player gains 2 life.")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main phase (turn 1: Alice is the active player)
    act(s, "p2", type="add_mana", player="p2", mana={"C": 1})
    for prefs in rules(s).prefs.values():
        prefs.response = "on"
    act(s, "p1", type="pass_priority")  # (Alice passes; Bob acts at instant speed)
    act(s, "p2", type="activate_ability", card_id=healer.id, ability=0)
    until(s, lambda s: decision(s) is not None and decision(s).resume.get("step") == "replace_order")
    order = []
    while decision(s) is not None and decision(s).resume.get("step") == "replace_order":
        d = decision(s)
        order.append(d.player)
        answer(s, "yes")  # (Angel of Vitality first: (2 + 1) × 2)
    assert order == ["p1", "p2", "p3"]  # the active player first, then in turn order (101.4)
    assert [s.state.players[p].life for p in ("p1", "p2", "p3")] == [46, 46, 46]
    replay_matches(s)


def test_the_same_counters_on_several_creatures_stay_one_event_batch(cards):
    s = build(cards)
    permanent(s, "p1", "Hardened Scales", "Enchantment", HARDENED_SCALES)
    bears = [token(s, "p1", f"Bear {i}") for i in range(3)]
    feeder = token(s, "p1", "Feeder", text="{1}: Put a +1/+1 counter on each creature you control.")
    activate(s, feeder)
    batches = {e.batch for e in rules(s).events if e.kind == "counters" and e.card in {b.id for b in bears}}
    assert all(s.state.cards[b.id].counters == {"+1/+1": 2} for b in bears) and len(batches) == 1
    replay_matches(s)


def test_wither_counters_go_through_counter_replacements_but_not_effect_only_ones(cards):
    """120.3d: wither damage puts -1/-1 counters as a result of damage, not as an effect (614.16):
    Winding Constrictor adds one to its controller's creature; Doubling Season doesn't double."""
    s = build(cards)
    token(s, "p2", "Winding Constrictor", "2/3", WINDING_CONSTRICTOR)
    permanent(s, "p2", "Doubling Season", "Enchantment", DOUBLING_SEASON)
    ogre = token(s, "p2", "Ogre", "5/5")
    wither = token(s, "p1", "Blighter", "1/1", "Wither\n{1}: Blighter deals 1 damage to target creature.")
    activate(s, wither, index=1, targets=[ogre.id])
    assert s.state.cards[ogre.id].counters == {"-1/-1": 2} and s.state.cards[ogre.id].damage == 0
    replay_matches(s)


def test_a_choice_in_the_draw_step_then_the_step_goes_on(cards):
    """Laboratory Maniac and Living Conundrum ("If you would draw a card while your library has no
    cards in it, skip that draw instead.") both replace the turn-based draw (504.1): its player
    chooses; the step then goes on (its "at the beginning of your draw step" triggers)."""
    s = build(cards)
    token(s, "p2", "Laboratory Maniac", "2/2", LABORATORY_MANIAC)
    token(s, "p2", "Living Conundrum", "10/10", "Hexproof\nIf you would draw a card while your library has no cards in "
                                                 "it, skip that draw instead.")  # Living Conundrum (Oracle)
    permanent(s, "p2", "Reminder", "Enchantment", "At the beginning of your draw step, you gain 1 life.")
    empty_library(s, "p2")
    until(s, lambda s: decision(s) is not None and decision(s).resume.get("step") == "replace_order")
    d = decision(s)
    assert d.player == "p2" and s.state.turn.phase == "draw" and s.state.turn.active_player == "p2"
    skip_first = "yes" if "Living Conundrum first" in {o.id: o.label for o in d.options}["yes"] else "no"
    s2 = reload(s, cards)
    answer(s, skip_first)
    until(s, lambda s: s.state.turn.phase == "main1")
    assert rules(s).winner is None and "p2" not in rules(s).drew_from_empty and s.state.players["p2"].life == 41
    replay_matches(s)
    act(s2, "p2", type="choose", decision_id=d.id, option_ids=["no" if skip_first == "yes" else "yes"])
    assert rules(s2).winner == "p2"


# -- no event bypasses the choke points --------------------------------------------------------------
# Table actions that make a replaceable event happen, and the places allowed to emit them directly.
# Everything else must go through app/rules/replace.py. A removal (negative delta) isn't replaceable.
_REPLACEABLE = {"counter", "resource", "create_token", "draw", "life", "rules_damage"}
_ALLOWED = {
    # outside wave 2E's ownership, to be rerouted at integration (UNVERIFIED how the lead reroutes them):
    ("casting.py", "activate_to_stack"): "a loyalty ability's cost (606.4: a cost, not an effect; agent A's region)",
    ("casting.py", "suspend"): "time counters on a card in exile (not a permanent: no counter replacement applies)",
    ("recursion.py", "spell_self_move"): "wave 7C: a spell's time counters as it exiles itself (a card in exile, as above)",
    ("replacements.py", "move_instead"): "wave 50J: the counter an exiling replacement puts on the card it exiled (Rayami: a card in exile, not a permanent)",
    ("replacements.py", "replace_move"): "wave 50J: the same, for the batch path",
    ("designations.py", "emblem"): "wave 13A: an emblem is not a token (114.1, 111.7): no token-creation replacement applies",
}


def _direct_table_actions():
    import ast
    from pathlib import Path

    import app.rules as rules_pkg

    root = Path(rules_pkg.__file__).parent
    found = []
    for path in sorted(root.glob("*.py")):
        if path.name == "replace.py":
            continue
        tree = ast.parse(path.read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Dict):
                    continue
                fields = {k.value: v for k, v in zip(node.keys, node.values, strict=True) if isinstance(k, ast.Constant)}
                kind = fields.get("type")
                if not isinstance(kind, ast.Constant) or kind.value not in _REPLACEABLE:
                    continue
                delta = fields.get("delta")
                removal = isinstance(delta, ast.UnaryOp) and isinstance(delta.op, ast.USub)
                if kind.value in ("counter", "resource", "life") and removal:
                    continue
                found.append((path.name, fn.name, kind.value, node.lineno))
    return found


def test_no_replaceable_event_bypasses_the_choke_points():
    stray = [(f, fn, kind, line) for f, fn, kind, line in _direct_table_actions() if (f, fn) not in _ALLOWED]
    assert not stray, f"table actions that bypass app/rules/replace.py: {stray}"
    # (and the list of exceptions is honest: each still exists)
    present = {(f, fn) for f, fn, _, _ in _direct_table_actions()}
    assert set(_ALLOWED) <= present, set(_ALLOWED) - present


# -- coverage and what stays manual ---------------------------------------------------------------------
def _card(name, type_line, text, **extra):
    from tests.fixtures.cards import card

    return card(name, type_line=type_line, oracle_text=text, **extra)


def test_the_real_cards_are_full():
    from app.rules import coverage

    for name, type_line, text in [
        ("Doubling Season", "Enchantment", DOUBLING_SEASON), ("Hardened Scales", "Enchantment", HARDENED_SCALES),
        ("Parallel Lives", "Enchantment", PARALLEL_LIVES), ("Anointed Procession", "Enchantment", ANOINTED_PROCESSION),
        ("Winding Constrictor", "Creature — Snake", WINDING_CONSTRICTOR), ("Xorn", "Creature — Elemental", XORN),
        ("Vizier of Remedies", "Creature — Human Cleric", VIZIER_OF_REMEDIES),
        ("Laboratory Maniac", "Creature — Human Wizard", LABORATORY_MANIAC),
        ("Notion Thief", "Creature — Human Rogue", NOTION_THIEF), ("Thought Reflection", "Enchantment", THOUGHT_REFLECTION),
        ("Boon Reflection", "Enchantment", BOON_REFLECTION), ("Rhox Faithmender", "Creature — Rhino Monk", RHOX_FAITHMENDER),
        ("Tainted Remedy", "Enchantment", TAINTED_REMEDY), ("Gratuitous Violence", "Enchantment", GRATUITOUS_VIOLENCE),
        ("Torbran, Thane of Red Fell", "Legendary Creature — Dwarf Noble", TORBRAN),
        ("Furnace of Rath", "Enchantment", FURNACE_OF_RATH), ("Urza's Armor", "Artifact", URZAS_ARMOR),
        ("Fire Servant", "Creature — Elemental", FIRE_SERVANT),
        ("Anger of the Gods", "Sorcery", "Anger of the Gods deals 3 damage to each creature. If a creature dealt damage "
                                         "this way would die this turn, exile it instead."),
        ("Lava Coil", "Sorcery", "Lava Coil deals 4 damage to target creature. If that creature would die this turn, "
                                 "exile it instead."),
        ("Flaying Tendrils", "Instant", "Devoid (This card has no color.)\nAll creatures get -2/-2 until end of turn. If a "
                                        "creature would die this turn, exile it instead."),
    ]:
        cov = coverage.of_card_data(_card(name, type_line, text, power="2", toughness="2"))
        assert cov.level == "FULL", (name, cov.manual_parts)


def test_wordings_that_stay_manual():
    from app.rules import scripts
    from tests.test_rules_scripts import ch

    for text in [
        # ("you would put" is automated since wave 22C: tests/test_rules_wave22c_replacements.py)
        # "may instead" (Jinnie Fay) — (wave 3R2: a different token added, Chatterfang, and redirection, Pariah, are
        # automated: tests/test_rules_refused_grants.py)
        "If you would create one or more tokens, you may instead create that many 2/2 green Cat creature tokens with haste "
        "or that many 3/1 green Dog creature tokens with vigilance.",
        # (a rider after prevention, 615.5, is automated since wave 17A: tests/test_rules_wave17a_prevention.py)
        # ("would lose life" doubling is automated since wave 28B: tests/test_rules_wave28b_replace.py) / "can't" (614.17, 119.8) /
        # a draw replaced by a choice of land or nonland (Abundance)
        "If you would draw a card, you may instead choose land or nonland and reveal cards from the top of your library "
        "until you reveal a card of the chosen kind. Put that card into your hand and put all other cards revealed this "
        "way on the bottom of your library in any order.",
        # (Kalitas: exile and a token is automated since wave 22C: tests/test_rules_wave22c_zones.py)
        "If a nontoken creature an opponent controls would die, instead exile that card and create a 2/2 black Zombie "
        "creature token and draw a card.",
        # damage: a union that isn't one of the two properties ("a red or artifact source" is read since wave 9B:
        # tests/test_rules_wave9b_damage_plus.py)
        "If a red or artifact and white source you control would deal damage to an opponent or a permanent an opponent "
        "controls, it deals that much damage plus 1 instead.",
    ]:
        assert not scripts.definitions(ch("X", "Enchantment", text)), text


def test_a_levelers_conditional_line_is_never_applied(cards):
    """Hedron-Field Purists' "LEVEL 1-4 … prevent 1 of that damage" applies only at that level,
    which the engine doesn't track: the line is not applied (never a guess)."""
    s = build(cards)
    token(s, "p2", "Purists", "0/3", "Level up {2}{W}\nLEVEL 1-4\n1/4\n" + "If a source would deal damage to you or a "
                                     "creature you control, prevent 1 of that damage.")
    pinger = token(s, "p1", "Pinger", "1/1", "{1}: Pinger deals 2 damage to any target.")
    activate(s, pinger, targets=["p2"])
    assert s.state.players["p2"].life == 38
