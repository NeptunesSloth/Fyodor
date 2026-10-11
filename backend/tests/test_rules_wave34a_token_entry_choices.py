"""Wave 34A: tokens made as copies ask their copied "As this enters, choose …" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave34a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 614.12 / 614.12a / 614.1c: "As this enters, choose …" is a replacement effect that applies as the object enters, and the choice is made before it
  enters: a token enters like any permanent, so a token copy of Metallic Mimic / a Siege / Pithing Needle is asked, by the token's controller.
* 707.2 / 707.5 / 707.6: the copy has the copiable "as enters" ability and makes its own choice, which the original's choice doesn't decide.
* 111.1 / 111.4: tokens are created, then enter; several tokens entering at once each ask for their own choice, in creation order (616.1: APNAP).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, pt, put, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave34a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w34a", number=f"T{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def settle(s, prefer=(), limit=60):
    """Resolve everything; a decision is answered with the first of ``prefer`` it offers, else its first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [p for p in prefer if p in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want[:1] if want else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, pid="p1", prefer=(), **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s, prefer)


def pending(s):
    return s.state.rules.decision


def to_phase(s, phase, turn=None, limit=300):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached."""
    for _ in range(limit):
        d = pending(s)
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn}")


def choose(s, option):
    d = pending(s)
    assert d is not None and option in [o.id for o in d.options], (d.prompt if d else None)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


def cast_until_choice(s, name, **kw):
    """Cast ``name`` and pass priority until a decision opens."""
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id, **kw)
    for _ in range(12):
        if pending(s) is not None:
            return pending(s)
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision opened")


def choices_of(card_):
    return dict(card_.choices)


def tokens(s, name):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == "p1:battlefield"]


def mimic_on_table(cards_, *rest, kind="Goblin"):
    """Alice has cast a Metallic Mimic choosing ``kind``."""
    s = build(cards_, ["Metallic Mimic", *rest, "Llanowar Elves"])
    to_hand(s, "Metallic Mimic")
    mana(s, C=2)
    cast(s, "Metallic Mimic", prefer=(kind,))
    assert choices_of(card_named(s, "Metallic Mimic")) == {"Chosen creature type": kind}
    return s


def test_rite_of_replication_token_copy_of_metallic_mimic_chooses_its_own_type(cards):
    """Rite of Replication: "Create a token that's a copy of target creature." The token Mimic is asked its creature type as it enters
    (614.12a, 707.6) by Alice, and the type the original chose (Goblin) doesn't decide it: an Elf entering now gets the token's +1/+1 counter."""
    s = mimic_on_table(cards, "Rite of Replication")
    original = card_named(s, "Metallic Mimic")
    to_hand(s, "Rite of Replication")
    mana(s, U=2, C=2)
    d = cast_until_choice(s, "Rite of Replication", targets=[original.id])
    assert d.player == "p1" and "creature type" in d.prompt and "Elf" in [o.id for o in d.options]
    check(s)  # (a replay and a save while the question is open)
    s = reloaded(s)
    choose(s, "Elf")
    settle(s)
    [copy] = tokens(s, "Metallic Mimic")
    assert choices_of(copy) == {"Chosen creature type": "Elf"} and choices_of(card_named(s, "Metallic Mimic")) == {"Chosen creature type": "Goblin"}
    to_hand(s, "Llanowar Elves")
    mana(s, G=1)
    cast(s, "Llanowar Elves")
    assert pt(s, "Llanowar Elves") == (2, 2)  # 1/1 + the one counter (Elf: the token's type, not the original's Goblin)
    check(s)


def test_helm_of_the_host_token_copy_asks_at_the_beginning_of_combat(cards):
    """Helm of the Host: "At the beginning of combat on your turn, create a token that's a copy of equipped creature, except the token isn't
    legendary if it's legendary. That token gains haste." The token copy of the equipped Metallic Mimic chooses its own type."""
    s = mimic_on_table(cards, "Helm of the Host")
    helm = put(s, "Helm of the Host")
    act(s, "p1", type="attach", card_ids=[helm.id], to=card_named(s, "Metallic Mimic").id)
    act(s, "p1", type="set_stops", own=["begin_combat"], others=[], smart_pass=False)
    for _ in range(12):
        if pending(s) is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = pending(s)
    assert d is not None and d.player == "p1" and "creature type" in d.prompt
    choose(s, "Elf")
    settle(s)
    [copy] = tokens(s, "Metallic Mimic")
    assert choices_of(copy) == {"Chosen creature type": "Elf"} and copy.is_token
    check(s)


def test_several_tokens_entering_together_each_ask_in_creation_order(cards):
    """Second Harvest: "For each token you control, create a token that's a copy of that permanent." Two token Metallic Mimics are copied at once: each
    new token asks its own creature type (111.4, 614.12a), one question after the other, the first answer going to the first token created."""
    s = mimic_on_table(cards, "Rite of Replication", "Cackling Counterpart", "Second Harvest")
    original = card_named(s, "Metallic Mimic")
    to_hand(s, "Rite of Replication")
    mana(s, U=2, C=2)
    cast_until_choice(s, "Rite of Replication", targets=[original.id])
    choose(s, "Elf")
    settle(s)
    to_hand(s, "Cackling Counterpart")
    mana(s, U=2, C=1)
    cast_until_choice(s, "Cackling Counterpart", targets=[original.id])
    choose(s, "Wizard")
    settle(s)
    assert sorted(choices_of(t)["Chosen creature type"] for t in tokens(s, "Metallic Mimic")) == ["Elf", "Wizard"]
    to_hand(s, "Second Harvest")
    mana(s, G=2, C=2)
    d = cast_until_choice(s, "Second Harvest")
    assert d.player == "p1" and "creature type" in d.prompt
    first = d.id
    check(s)
    choose(s, "Human")
    d = pending(s)
    assert d is not None and d.id != first and d.player == "p1" and "creature type" in d.prompt  # (the second token's own question)
    s = reloaded(s)
    choose(s, "Zombie")
    settle(s)
    made = sorted(choices_of(t)["Chosen creature type"] for t in tokens(s, "Metallic Mimic"))
    assert made == ["Elf", "Human", "Wizard", "Zombie"]
    check(s)


def test_populate_a_token_with_an_entering_choice_asks_again(cards):
    """Wake the Reflections: "Populate. (Create a token that's a copy of a creature token you control.)" The populated token Metallic Mimic is a
    new token entering: it chooses its own creature type."""
    s = mimic_on_table(cards, "Rite of Replication", "Wake the Reflections")
    to_hand(s, "Rite of Replication")
    mana(s, U=2, C=2)
    cast_until_choice(s, "Rite of Replication", targets=[card_named(s, "Metallic Mimic").id])
    choose(s, "Elf")
    settle(s)
    to_hand(s, "Wake the Reflections")
    mana(s, W=1)
    d = cast_until_choice(s, "Wake the Reflections")
    assert d.player == "p1" and "creature type" in d.prompt and "Metallic Mimic" in d.prompt
    check(s)
    choose(s, "Human")
    settle(s)
    assert sorted(choices_of(t)["Chosen creature type"] for t in tokens(s, "Metallic Mimic")) == ["Elf", "Human"]
    check(s)


def test_spark_double_entering_as_a_copy_of_metallic_mimic_chooses_a_type_and_gets_its_counter(cards):
    """Spark Double: "You may have this creature enter as a copy of a creature or planeswalker you control, except it enters with an additional +1/+1
    counter on it if it's a creature …" (707.5, 707.9e). As the Mimic copy it enters, it chooses its own creature type (614.12a): the copy question first."""
    s = mimic_on_table(cards, "Spark Double")
    original = card_named(s, "Metallic Mimic")
    to_hand(s, "Spark Double")
    mana(s, U=1, C=3)
    d = cast_until_choice(s, "Spark Double")
    assert d.prompt.endswith("to copy")
    choose(s, original.id)
    for _ in range(6):
        d = pending(s)
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and "creature type" in d.prompt
    check(s)
    choose(s, "Elf")
    settle(s)
    double = card_named(s, "Spark Double")
    assert choices_of(double) == {"Chosen creature type": "Elf"} and double.counters == {"+1/+1": 1}
    assert pt(s, "Spark Double") == (3, 2)
    check(s)


def test_a_clone_blinked_back_in_as_metallic_mimic_chooses_a_type_again(cards):
    """Clone ("You may have this creature enter as a copy of any creature on the battlefield.") entering as a copy of Metallic Mimic, cast and then put
    back by Cloudshift: both times it is asked to copy, then to choose a type (614.12a, 707.5); the new object kept nothing of the first choice (400.7)."""
    s = mimic_on_table(cards, "Clone", "Cloudshift")
    mimic = card_named(s, "Metallic Mimic")
    to_hand(s, "Clone")
    mana(s, U=1, C=3)
    d = cast_until_choice(s, "Clone")
    assert d.prompt.endswith("to copy")
    choose(s, mimic.id)
    for _ in range(6):
        if pending(s) is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert "creature type" in pending(s).prompt
    choose(s, "Elf")
    settle(s)
    clone = card_named(s, "Clone")
    assert choices_of(clone) == {"Chosen creature type": "Elf"}
    to_hand(s, "Cloudshift")
    mana(s, W=1)
    d = cast_until_choice(s, "Cloudshift", targets=[clone.id])
    assert d.prompt.endswith("to copy")
    choose(s, mimic.id)
    assert "creature type" in pending(s).prompt
    check(s)
    s = reloaded(s)
    choose(s, "Human")
    settle(s)
    assert choices_of(card_named(s, "Clone")) == {"Chosen creature type": "Human"}
    check(s)


def test_a_token_copy_of_sorcerous_spyglass_shows_the_hand_to_its_chooser_alone(cards):
    """Sorcerous Spyglass: "As this artifact enters, look at an opponent's hand, then choose any card name." (701.20e) A token copy looks at the one
    opponent's hand as it enters: only its controller's decision shows the cards; no other viewer, the log or the revealed set learns them."""
    from app.game.views import SPECTATOR, build_view
    from app.rules.view import decision_view

    s = build(cards, ["Sorcerous Spyglass", "Flash Photography"], ["Lightning Bolt", "Counterspell"])
    bolt, spell = to_hand(s, "Lightning Bolt", "p2"), to_hand(s, "Counterspell", "p2")
    to_hand(s, "Sorcerous Spyglass")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Sorcerous Spyglass").id)
    while pending(s) is None:
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="choose", decision_id=pending(s).id, name="Giant Growth")
    settle(s)
    original = card_named(s, "Sorcerous Spyglass")
    d = photograph(s, original)
    assert d.player == "p1" and d.options[0].id == "__name__" and {o.card_id for o in d.options[1:]} == {bolt.id, spell.id}
    mine, theirs = json.dumps(decision_view(s.state, d, "p1")), json.dumps(decision_view(s.state, d, "p2"))
    assert "Lightning Bolt" in mine and bolt.id in mine
    assert "Lightning Bolt" not in theirs and bolt.id not in theirs and decision_view(s.state, d, "p2")["kind"] == "waiting"
    watching = json.dumps(build_view(s.state, SPECTATOR))
    assert "Lightning Bolt" not in watching and "Counterspell" not in watching
    log = " ".join(p.t or "" for e in s.state.log for p in e.parts)
    assert "Lightning Bolt" not in log and "Counterspell" not in log and not (s.state.cards[bolt.id].revealed_to or s.state.cards[spell.id].revealed_to)
    check(s)
    act(s, "p1", type="choose", decision_id=d.id, name="Counterspell")
    settle(s)
    [token] = tokens(s, "Sorcerous Spyglass")
    assert choices_of(token) == {"Chosen card name": "Counterspell"} and choices_of(s.state.cards[original.id]) == {"Chosen card name": "Giant Growth"}
    assert not (s.state.cards[bolt.id].revealed_to or s.state.cards[spell.id].revealed_to)  # (still in their hand, still hidden)
    check(s)


def test_a_copy_of_a_metallic_mimic_spell_chooses_its_own_type_as_the_token_enters(cards):
    """Lithoform Engine: "{4}, {T}: Copy target permanent spell you control. (The copy becomes a token.)" — pinned: the token the copy becomes
    (608.3f) is asked its creature type, as is the Mimic spell it was copied from; each keeps its own choice."""
    s = build(cards, ["Metallic Mimic", "Lithoform Engine"])
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (everyone stops at each object on the stack)
    act(s, "p1", type="set_prefs", hold_priority=True)
    engine = put(s, "Lithoform Engine")
    mimic = to_hand(s, "Metallic Mimic")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=mimic.id)
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=engine.id, ability=2, targets=[mimic.id])
    asked = []
    for _ in range(20):
        d = pending(s)
        if d is not None:
            assert d.player == "p1" and "creature type" in d.prompt
            asked.append(d.prompt)
            choose(s, "Elf" if len(asked) == 1 else "Human")
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert len(asked) == 2
    [token] = tokens(s, "Metallic Mimic")
    assert choices_of(token) == {"Chosen creature type": "Elf"} and choices_of(s.state.cards[mimic.id]) == {"Chosen creature type": "Human"}
    check(s)


def test_a_permanent_put_onto_the_battlefield_by_an_effect_asks_too(cards):
    """Sneak Attack: "{R}: You may put a creature card from your hand onto the battlefield. …" — pinned: a Metallic Mimic put there is asked its type
    before it enters (614.12a), as one cast is."""
    s = build(cards, ["Sneak Attack", "Metallic Mimic", "Llanowar Elves"])
    put(s, "Sneak Attack")
    to_hand(s, "Metallic Mimic")
    mana(s, R=1)
    attack = card_named(s, "Sneak Attack")
    act(s, "p1", type="activate_ability", card_id=attack.id, ability=0)
    for _ in range(10):
        d = pending(s)
        if d is not None and "creature type" in d.prompt:
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert pending(s) is not None and "creature type" in pending(s).prompt
    check(s)
    choose(s, "Elf")
    settle(s)
    assert choices_of(card_named(s, "Metallic Mimic")) == {"Chosen creature type": "Elf"} and zone_of(s, "Metallic Mimic") == "p1:battlefield"
    check(s)


def photograph(s, target, pid="p1"):
    """Flash Photography: "Create a token that's a copy of target permanent." Returns the open question."""
    to_hand(s, "Flash Photography", pid)
    mana(s, U=2, G=2)
    return cast_until_choice(s, "Flash Photography", targets=[target.id])


@pytest.mark.parametrize(("first", "word", "bonus"), [("Jeskai", "Temur", (3, 2)), ("Temur", "Temur", (4, 2)), ("Jeskai", "Jeskai", (2, 2))])
def test_a_token_copy_of_a_siege_chooses_its_own_word(cards, first, word, bonus):
    """607.2f / 614.12a / 707.6: a token copy of Frostcliff Siege ("As this enchantment enters, choose Jeskai or Temur. • Jeskai — … • Temur — Creatures
    you control get +1/+0 and have trample and haste.") is asked; only its own chosen word's ability is there, whatever the original chose."""
    s = build(cards, ["Frostcliff Siege", "Flash Photography", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    to_hand(s, "Frostcliff Siege")
    mana(s, U=1, R=1, G=1)
    cast(s, "Frostcliff Siege", prefer=(first,))
    original = card_named(s, "Frostcliff Siege")
    d = photograph(s, original)
    assert d.player == "p1" and sorted(o.id for o in d.options) == ["Jeskai", "Temur"] and "Frostcliff Siege" in d.prompt
    check(s)
    s = reloaded(s)
    choose(s, word)
    settle(s)
    [token] = tokens(s, "Frostcliff Siege")
    assert choices_of(token) == {"Chosen word": word} and choices_of(s.state.cards[original.id]) == {"Chosen word": first}
    assert pt(s, "Grizzly Bears") == bonus
    check(s)
    s = reloaded(s)
    assert choices_of(tokens(s, "Frostcliff Siege")[0]) == {"Chosen word": word} and pt(s, "Grizzly Bears") == bonus  # (the choice is saved with it)


def test_palace_siege_token_copy_drains_for_its_dragons_word_only(cards):
    """Palace Siege: "• Khans — At the beginning of your upkeep, return target creature card from your graveyard to your hand. • Dragons — At the
    beginning of your upkeep, each opponent loses 2 life and you gain 2 life." The original chose Khans, its token copy Dragons: the drain is the token's."""
    s = build(cards, ["Palace Siege", "Flash Photography"], forests=30, islands=30)
    to_hand(s, "Palace Siege")
    mana(s, B=2, G=3)
    cast(s, "Palace Siege", prefer=("Khans",))
    photograph(s, card_named(s, "Palace Siege"))
    choose(s, "Dragons")
    settle(s)
    s = reloaded(s)
    act(s, "p1", type="set_stops", own=["upkeep"], others=["upkeep"], smart_pass=False)
    mine, theirs = s.state.players["p1"].life, s.state.players["p2"].life
    to_phase(s, "upkeep", turn=3)
    settle(s)
    assert (s.state.players["p1"].life, s.state.players["p2"].life) == (mine + 2, theirs - 2)  # (the token's; the original's Khans ability has no target)
    check(s)


def test_pithing_needle_token_copy_names_a_card_publicly(cards):
    """201.4 / 614.12a: a token copy of Pithing Needle ("As this artifact enters, choose a card name.") is asked to type a name (a public choice: the
    prompt and options name no hidden card), and the chosen name is recorded on the token alone."""
    s = build(cards, ["Pithing Needle", "Flash Photography"])
    to_hand(s, "Pithing Needle")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Pithing Needle").id)
    for _ in range(6):
        if pending(s) is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="choose", decision_id=pending(s).id, name="Llanowar Elves")
    settle(s)
    original = card_named(s, "Pithing Needle")
    d = photograph(s, original)
    assert d.player == "p1" and [o.id for o in d.options] == ["__name__"] and "card name" in d.prompt
    assert all(c.name not in d.prompt for c in s.state.cards.values() if c.zone.endswith(("hand", "library")) and c.name != "Pithing Needle")
    check(s)
    act(s, "p1", type="choose", decision_id=d.id, name="Grizzly Bears")
    settle(s)
    [token] = tokens(s, "Pithing Needle")
    assert choices_of(token) == {"Chosen card name": "Grizzly Bears"} and choices_of(s.state.cards[original.id]) == {"Chosen card name": "Llanowar Elves"}
    check(s)
