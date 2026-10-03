"""Wave 5R: the independent review of wave 5 (CR 2026-09-25): regressions for what it found, and the seams where
wave-5 features meet. Cards carry their real Oracle text from the card database (made-up cards are named "Probe")."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import creature, life, on_field, pick, settle, to_hand, until_asked
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    # (no real spell has this exact wording yet; Hypothesizzle's "Then you may discard a nonland card." stays manual)
    card('Probe Reflexive Spell', set_code="tst", number="R1", mana_cost='{1}{R}', cmc=2.0, type_line='Sorcery',
         oracle_text='Draw a card. You may sacrifice a creature. When you do, Probe Reflexive Spell deals 4 damage to target creature.',
         colors=['R'], color_identity=['R']),
    card('Hypothesizzle', set_code="tst", number="R2", mana_cost='{3}{U}{R}', cmc=5.0, type_line='Instant',
         oracle_text='Draw two cards. Then you may discard a nonland card. When you do, Hypothesizzle deals 4 damage to target creature.',
         colors=['R', 'U'], color_identity=['R', 'U']),
    card('Grand Abolisher', set_code="tst", number="RC1", mana_cost='{W}{W}', cmc=2.0, type_line='Creature — Human Cleric', oracle_text="During your turn, your opponents can't cast spells or activate abilities of artifacts, creatures, or enchantments.", power='2', toughness='2', colors=['W'], color_identity=['W']),
    card('Simian Spirit Guide', set_code="tst", number="RC2", mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Ape Spirit', oracle_text='Exile this card from your hand: Add {R}.', power='2', toughness='2', colors=['R'], color_identity=['R']),
    card('Drannith Magistrate', set_code="tst", number="RC3", mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Human Wizard', oracle_text="Your opponents can't cast spells from anywhere other than their hands.", power='1', toughness='3', colors=['W'], color_identity=['W']),
    card('Propaganda', set_code="tst", number="RC4", mana_cost='{2}{U}', cmc=3.0, type_line='Enchantment', oracle_text="Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.", colors=['U'], color_identity=['U']),
    card("Mirari's Wake", set_code="tst", number="RC5", mana_cost='{3}{G}{W}', cmc=5.0, type_line='Enchantment', oracle_text='Creatures you control get +1/+1.\nWhenever you tap a land for mana, add one mana of any type that land produced.', colors=['G', 'W'], color_identity=['G', 'W']),
    card('Seedborn Muse', set_code="tst", number="RC6", mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Spirit', oracle_text="Untap all permanents you control during each other player's untap step.", power='2', toughness='4', colors=['G'], color_identity=['G']),
    card('Hardened Scales', set_code="tst", number="RC7", mana_cost='{G}', cmc=1.0, type_line='Enchantment', oracle_text='If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.', colors=['G'], color_identity=['G']),
    card('Renata, Called to the Hunt', set_code="tst", number="RC8", mana_cost='{2}{G}{G}', cmc=4.0, type_line='Legendary Enchantment Creature — Demigod', oracle_text="Renata's power is equal to your devotion to green. (Each {G} in the mana costs of permanents you control counts toward your devotion to green.)\nEach other creature you control enters with an additional +1/+1 counter on it.", power='*', toughness='3', colors=['G'], color_identity=['G']),
    card('Woe Strider', set_code="tst", number="RD1", mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Horror', oracle_text='When this creature enters, create a 0/1 white Goat creature token.\nSacrifice another creature: Scry 1.\nEscape—{3}{B}{B}, Exile four other cards from your graveyard. (You may cast this card from your graveyard for its escape cost.)\nThis creature escapes with two +1/+1 counters on it.', power='3', toughness='2', colors=['B'], color_identity=['B'], keywords=['Escape', 'Scry']),
    card('Memnite', set_code="tst", number="RD2", mana_cost='{0}', cmc=0.0, type_line='Artifact Creature — Construct', power='1', toughness='1'),
    card('Brainstorm', set_code="tst", number="RE1", mana_cost='{U}', cmc=1.0, type_line='Instant', oracle_text='Draw three cards, then put two cards from your hand on top of your library in any order.', colors=['U'], color_identity=['U']),
    card('Growth Spiral', set_code="tst", number="RE2", mana_cost='{G}{U}', cmc=2.0, type_line='Instant', oracle_text='Draw a card. You may put a land card from your hand onto the battlefield.', colors=['G', 'U'], color_identity=['G', 'U']),
    card('Mystic Forge', set_code="tst", number="RF1", mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='You may look at the top card of your library any time.\nYou may cast artifact spells and colorless spells from the top of your library.\n{T}, Pay 1 life: Exile the top card of your library.'),
    card('Blaze', set_code="tst", number="RB2", mana_cost='{X}{R}', cmc=1.0, type_line='Sorcery', oracle_text='Blaze deals X damage to any target.', colors=['R'], color_identity=['R']),
    card('Forbidden Friendship', set_code="tst", number="RA1", mana_cost='{1}{R}', cmc=2.0, type_line='Sorcery', oracle_text='Create a 1/1 red Dinosaur creature token with haste and a 1/1 white Human Soldier creature token.', colors=['R'], color_identity=['R']),
    card('Woodland Champion', set_code="tst", number="RA2", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf Scout', oracle_text='Whenever one or more tokens you control enter, put that many +1/+1 counters on this creature.', power='2', toughness='2', colors=['G'], color_identity=['G']),
    card('Mister Fantastic, Reed Richards', set_code="tst", number="RA3", mana_cost='{3}{U}', cmc=4.0, type_line='Legendary Creature — Human Scientist Hero', oracle_text='Reach\nWhenever one or more tokens you control enter, you may draw a card.', power='2', toughness='4', colors=['U'], color_identity=['U'], keywords=['Reach']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (12, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (12, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def roundtrip(s):
    replay_matches(s)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


# -- 5G: a reflexive trigger with a target inside a spell (603.12) ------------------------------------------------------
def test_reflexive_target_in_a_spell_no_longer_crashes_coverage(cards):
    # (an IndexError: the reflexive ability's "target" was renumbered as one of the spell's own target groups)
    assert coverage.of_card_data(cards.resolve("Probe Reflexive Spell")).level == "FULL"
    assert coverage.of_card_data(cards.resolve("Hypothesizzle")).level != "FULL"


def test_reflexive_target_in_a_spell_chooses_its_target_when_it_triggers(cards):
    s = build(cards, p1=("Probe Reflexive Spell",))
    spell = to_hand(s, "Probe Reflexive Spell")
    mine = creature(s, "p1", "Fodder")
    theirs = creature(s, "p2", "Victim", pt="4/4")
    mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    roundtrip(s)
    assert [o.id for o in d.options] == ["pay", "decline"]
    pick(s, "pay")
    steps = []
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        steps.append((d.kind, [o.id for o in d.options]))
        ids = [o.id for o in d.options]
        pick(s, mine.id if mine.id in ids else theirs.id if theirs.id in ids else ids[0])
    assert steps == [("choose_one", [theirs.id])]  # (the only creature to sacrifice; the target asked as it triggers)
    assert mine.id not in s.state.cards and theirs.id not in s.state.cards  # (tokens: gone)
    roundtrip(s)


def test_reflexive_spell_declined_deals_no_damage(cards):
    s = build(cards, p1=("Probe Reflexive Spell",))
    spell = to_hand(s, "Probe Reflexive Spell")
    mine = creature(s, "p1", "Fodder")
    theirs = creature(s, "p2", "Victim", pt="4/4")
    mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    until_asked(s)
    pick(s, "decline")
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:battlefield" and s.state.cards[theirs.id].zone == "p2:battlefield"
    roundtrip(s)


# -- 5D: "If [a permanent] entering causes a triggered ability … to trigger" is refused (603.2d, 701.7a) -----------
@pytest.mark.parametrize("text", [
    "If an artifact or creature entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
    "If a permanent entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
    "If a land entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
    "If a Wizard you control entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
])
def test_entering_multipliers_stay_manual(text):
    """Whether "Whenever you create a token" triggers on the token entering isn't settled by the CR or a ruling."""
    from app.rules import trigger_multipliers

    assert trigger_multipliers.static_definition(text) is None
    # (the settled causes are still read)
    assert trigger_multipliers.static_definition(
        "If a creature dying causes a triggered ability of a permanent you control to trigger, that ability triggers an "
        "additional time.") is not None


# -- 5D: several kinds of token in one instruction are one event (701.7a, 603.2c) --------------------------------------
def test_two_token_kinds_in_one_instruction_trigger_one_or_more_once(cards):
    s = build(cards, p1=("Forbidden Friendship", "Woodland Champion", "Mister Fantastic, Reed Richards"))
    champion = on_field(s, "Woodland Champion")
    on_field(s, "Mister Fantastic, Reed Richards")
    spell = to_hand(s, "Forbidden Friendship")
    hand_before = len(zone(s.state, "p1", "hand"))
    mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    assert s.state.cards[champion.id].counters.get("+1/+1", 0) == 2  # ("that many": both tokens, one trigger)
    assert len(zone(s.state, "p1", "hand")) == hand_before - 1 + 1  # (Mister Fantastic: one draw, not two)
    roundtrip(s)


# -- 5B: a spell's X counts in its mana value on the stack (202.3e), also in this turn's cast log ------------------------
def test_cast_log_counts_x_in_mana_value(cards):
    s = build(cards, p1=("Blaze",))
    blaze = to_hand(s, "Blaze")
    mana(s, "p1", R=4)
    act(s, "p1", type="cast_spell", card_id=blaze.id, targets=["p2"], x_value=3)
    assert s.state.rules.turn_log.casts[-1].mv == 4  # ("if you've cast a spell with mana value 4 or greater this turn")
    settle(s)
    assert life(s, "p2") == 37
    roundtrip(s)


# -- seams between wave-5 features ---------------------------------------------------------------------------------------
def test_grand_abolisher_doesnt_stop_a_spirit_guide_in_the_hand(cards):
    """5E vs 5A: "activate abilities of … creatures" means creature permanents (109.2; Grand Abolisher ruling: not
    abilities of cards in other zones)."""
    from tests.test_rules_wave5e_cast_limits import bob_gets_priority

    s = build(cards, p1=("Grand Abolisher", "Grizzly Bears"), p2=("Simian Spirit Guide",))
    on_field(s, "Grand Abolisher")
    guide = to_hand(s, "Simian Spirit Guide", "p2")
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p2", type="set_prefs", full_control=True)
    bob_gets_priority(s)
    act(s, "p2", type="activate_ability", card_id=guide.id, ability=0)
    assert s.state.cards[guide.id].zone == "p2:exile" and s.state.players["p2"].mana.get("R") == 1
    roundtrip(s)


def test_drannith_magistrate_stops_escape(cards):
    """5E vs 5I: escape casts from the graveyard (702.138a), which Drannith Magistrate forbids an opponent."""
    from app.game.errors import ActionError
    from app.rules.casting import castable

    s = build(cards, p1=("Woe Strider", "Grizzly Bears", "Memnite", "Lightning Bolt", "Llanowar Elves"),
              p2=("Drannith Magistrate",))
    for name in ("Woe Strider", "Grizzly Bears", "Memnite", "Lightning Bolt", "Llanowar Elves"):
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    strider = next(c for c in s.state.cards.values() if c.name == "Woe Strider")
    mana(s, "p1", B=5)
    assert castable(s.state, "p1", s.state.cards[strider.id], s.cards, check_priority=False)
    on_field(s, "Drannith Magistrate", "p2")
    assert not castable(s.state, "p1", s.state.cards[strider.id], s.cards, check_priority=False)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=strider.id)
    assert s.state.cards[strider.id].zone == "p1:graveyard"
    roundtrip(s)


def test_renata_and_hardened_scales_on_an_entering_creature(cards):
    """5H: Renata's "enters with an additional +1/+1 counter" is a replacement (614.1c) that Hardened Scales then
    modifies (616.1: the affected object's controller orders them) — two counters."""
    s = build(cards, p1=("Renata, Called to the Hunt", "Hardened Scales", "Grizzly Bears"))
    renata = on_field(s, "Renata, Called to the Hunt")
    on_field(s, "Hardened Scales")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=bears.id)
    settle(s)
    assert s.state.cards[bears.id].counters.get("+1/+1", 0) == 2
    assert s.state.cards[renata.id].counters.get("+1/+1", 0) == 0  # ("each other creature")
    roundtrip(s)


def test_seedborn_muse_and_a_stun_counter(cards):
    """5A vs 122.1d: in another player's untap step Seedborn Muse untaps its controller's permanents, and a stunned
    one loses a stun counter instead of untapping."""
    from tests.test_rules_conditionals import to_turn

    s = build(cards, p1=("Seedborn Muse",))
    on_field(s, "Seedborn Muse")
    stunned = creature(s, "p1", "Stunned")
    plain = creature(s, "p1", "Plain")
    act(s, "p1", type="tap", card_ids=[stunned.id, plain.id], tapped=True)
    act(s, "p1", type="counter", card_ids=[stunned.id], kind="stun", delta=1)
    to_turn(s, 2)  # Bob's turn
    assert s.state.turn.active_player == "p2"
    assert not s.state.cards[plain.id].tapped
    assert s.state.cards[stunned.id].tapped and s.state.cards[stunned.id].counters.get("stun", 0) == 0
    roundtrip(s)


def test_propaganda_paid_with_mirraris_wake_extra_mana(cards):
    """5C vs 5A: an attack cost is paid with mana abilities while it's open (508.1i); Mirari's Wake's triggered mana
    ability (605.1b) adds its mana at once, so one Forest pays Propaganda's {2}."""
    from tests.test_rules_wave5c_combat import attacking, declare, lands, old, put, to_attack
    from tests.test_rules_wave5c_combat import build as combat_build

    s = combat_build(cards, "Mirari's Wake", payment="self", bob=["Propaganda"])
    put(s, "Propaganda", "p2")
    put(s, "Mirari's Wake")
    forest = lands(s, 1)[0]
    a = old(s, "p1", "Ogre")
    to_attack(s)
    declare(s, (a, "p2"))
    d = s.state.rules.decision
    assert d is not None and d.display["kind"] == "tap_mana" and d.display["cost"] == "{2}"
    act(s, "p1", type="activate_ability", card_id=forest, ability=0)
    assert attacking(s, a) == "p2"
    assert s.state.players["p1"].mana == {}
    roundtrip(s)


# -- hidden information in wave-5 prompts (400.2, 401.4) -------------------------------------------------------------
SECRET = ("Woe Strider", "Memnite", "Drannith Magistrate")


def _leaks(s):
    import json

    out = []
    for viewer in ("p2", "__spectator__"):
        text = json.dumps(s.view(viewer))
        out += [(viewer, n) for n in SECRET if n in text]
    return out


def _on_top(s, *names):
    for name in reversed(names):
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p1")
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")


def test_brainstorm_put_back_stays_private(cards):
    s = build(cards, p1=("Brainstorm", *SECRET))
    _on_top(s, *SECRET)
    spell = to_hand(s, "Brainstorm")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "choose_cards"
    assert not _leaks(s)
    import json

    assert "Woe Strider" in json.dumps(s.view("p1"))  # (the check would see a leak)
    chosen = [c for c in zone(s.state, "p1", "hand") if s.state.cards[c].name in ("Woe Strider", "Memnite")]
    pick(s, *chosen)
    while s.state.rules.decision is not None:  # (their order on top: also private)
        assert not _leaks(s)
        d = s.state.rules.decision
        pick(s, *[o.id for o in d.options][: max(1, d.min_choices)])
    settle(s)
    assert not _leaks(s)
    assert {s.state.cards[c].name for c in zone(s.state, "p1", "library")[:2]} == {"Woe Strider", "Memnite"}
    roundtrip(s)


def test_growth_spiral_choice_is_private_until_the_land_enters(cards):
    s = build(cards, p1=("Growth Spiral", *SECRET))
    _on_top(s, *SECRET)
    spell = to_hand(s, "Growth Spiral")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    mana(s, "p1", G=1, U=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    assert not _leaks(s)
    import json

    assert forest.id not in json.dumps(s.view("p2")["rules"].get("decision") or {})
    ids = [o.id for o in d.options]
    pick(s, forest.id if forest.id in ids else ids[0])
    settle(s)
    assert not _leaks(s)
    roundtrip(s)


def test_mystic_forge_top_card_and_its_cast_hint_only_for_its_owner(cards):
    """401.5 / 5I: "look at the top card of your library any time" lets its owner see it; the cast-from-top hint
    (Memnite: colorless) is the owner's too."""
    import json

    s = build(cards, p1=("Mystic Forge", *SECRET))
    on_field(s, "Mystic Forge")
    _on_top(s, "Memnite")
    assert "Memnite" in json.dumps(s.view("p1"))
    assert not _leaks(s)
    memnite = next(c for c in s.state.cards.values() if c.name == "Memnite")
    act(s, "p1", type="cast_spell", card_id=memnite.id)
    settle(s)
    assert s.state.cards[memnite.id].zone == "p1:battlefield"
    roundtrip(s)
