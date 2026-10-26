"""-- if you do (wave 6F) -- "Each opponent may [cost]. Each opponent who doesn't [effect]." and its forms:

* "each opponent may sacrifice a nontoken creature of their choice. Each opponent who doesn't loses 2 life for each
  instant and sorcery card in your graveyard." (Fandaniel, Telophoroi Ascian);
* "Each player may discard a card. Each player who doesn't loses 3 life." (The Death of Gwen Stacy);
* "each opponent may discard a card or sacrifice a permanent of their choice. Zoyowa deals 3 damage to each opponent who
  didn't." (Zoyowa Lava-Tongue); "Each player may sacrifice an artifact or enchantment. Impulsive Destruction deals 3
  damage to each player who didn't sacrifice a permanent this way.";
* "you may sacrifice an artifact, creature, enchantment, land, or planeswalker. If you do, each opponent may sacrifice a
  permanent of their choice that shares a card type with it. For each opponent who doesn't, that player loses 2 life
  and you draw a card." (Braids, Arisen Nightmare).

CR 2026-09-25: 118.12 — "[A player] may [do something]. If [that player] [doesn't], [effect]": the action is a cost,
paid as the ability resolves; 118.12a — the same as "[effect] unless [that player does something]". Each player is
offered their own payment, in turn order (101.4: the active player chooses first, then each other player in turn
order), each privately and only while it is payable in full (118.3; a sacrifice of a permanent the player doesn't
control, or a discard from an empty hand, isn't); then the effect happens for each player who didn't pay. The
payments and the effects are spliced into the resolution as the instruction is reached (designations.each_unless:
one optional payment per player, then each one's effect behind the negation of their payment).

"shares a card type with it" (Braids): "it" is the permanent sacrificed for the payment before ("If you do"), read
as it last existed on the battlefield (608.2h); the cost each opponent is offered is the sacrifice of a permanent with
any of its card types (205.2a), worked out as the instruction is reached.

-- each player may (wave 31B) -- an action that is no cost: "Each player may scry 1." (Eager Construct), "Scry 2. Then each opponent may scry 1." (Myr
Custodian), "…each player may search their library for a card and put that card into their hand. Then each player who searched their library this way
shuffles." (Noble Benefactor), "Each player may draw a card, then each player who drew a card this way gains 1 life." (Kwain), "Each opponent may create
a Treasure token. For each opponent who does, you create a Treasure token." (Tempting Contract). 101.4: every player answers in turn order (the question
of app/rules/tempting.py: a private yes or no), 608.2d: then each who said yes does the action as "you" (``as_player``), and what the answers give follows
(a player who said yes "drew a card this way"; the controller's own instruction once per opponent who did). Only actions whose every choice is the
player's own are read (``_ACT_OK``); a choice from a hand (Kynaios and Tiro of Meletis) and "Each opponent who doesn't …" after an action are not.

Not read: anything after "who doesn't" that names an object, a target or "this way" beyond the plain wording above;
"If no one does" (Browbeat); costs that aren't ones optional_payment pays.
"""

from __future__ import annotations

import copy
import json
import re
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_WHO = {"opponent": "each_opponent", "player": "each_player"}
_MAY = re.compile(r"^(?:then )?(?:if (?P<cond>(?!you do\b)[^,]+), )?(?P<if>if you do, )?(?P<every>each|any) (?P<who>opponent|player) may (?P<cost>.+)$")
# -- trigger other (wave 39A) -- "Any opponent may sacrifice a creature of their choice. If a player does, tap this creature, you gain 3 life, and you draw a
# card." (Clackbridge Troll), "When you cast this spell, any player may sacrifice a creature of their choice. If a player does, counter this spell." (Brain
# Gorgers), "… If no one does, transform this creature." (Innocent Traveler): the same question to every player of the group (101.4, turn order), the
# choices made first and the payments together (the rulings of Clackbridge Troll and Vile Mutilator), then what follows happens once, for the controller
_ANY_DID = re.compile(r"^if (?P<w>a player|an opponent|no one|no player|nobody) does, (?P<rest>.+)$")
_FOR_EACH = re.compile(r"^for each (?P<who>opponent|player) who (?:doesn't|didn't), (?P<rest>.+)$")
_WHO_DOESNT = re.compile(r"^each (?P<who>opponent|player) who (?:doesn't|didn't) (?P<rest>.+)$")
_TO_EACH = re.compile(r"^(?P<lead>.+) to each (?P<who>opponent|player) who (?:doesn't|didn't)(?P<this> sacrifice a permanent(?P<disc> or discard a card)? this way)?$")
# -- each player may (wave 23A) -- "Each player may discard their hand and draw five cards." (Raphael's Technique, Ruin Grinder) and
# "Each player who discarded a card this way draws a card." / "… who does, …": what the players who paid get, once all have paid
_AND_DRAW = re.compile(r"^(?P<cost>discard (?:their|your) hand) and draw (?P<rest>.+)$")
_WHO_DID = re.compile(r"^each (?P<who>opponent|player) who (?:does|did|discarded (?:a card|their hand) this way|drew a card this way),? (?P<rest>.+)$")
_TO_EACH_DID = re.compile(r"^(?P<lead>.+) to each (?P<who>opponent|player) who discarded (?:a card|their hand) this way$")
# -- each player may (wave 31B) -- "Each player may draw a card, then each player who drew a card this way gains 1 life." (Kwain), "each opponent may
# create a Treasure token. For each opponent who does, you create a Treasure token." (Tempting Contract): an action that is no cost, asked of each
# player in turn order (the offer of app/rules/tempting.py), done by each who said yes (they are "you" for it), then what the answers give
_SPLIT_THEN = re.compile(r"^(?P<act>.+?), then (?P<tail>each (?:opponent|player) who .+)$")
_FOR_EACH_DID = re.compile(r"^for each (?P<who>opponent|player) who (?:does|did), (?P<rest>.+)$")
_SHUFFLES = re.compile(r"^each (?:opponent|player) who searched their library this way shuffles$")
_ACT_OK = frozenset({"scry", "draw", "create_token", "search", "shuffle_library"})  # (an action all of whose choices are the player's own, 701.19)
_SHARES = "sacrifice a permanent that shares a card type with it"
_TYPES = ("Artifact", "Battle", "Creature", "Enchantment", "Kindred", "Land", "Planeswalker")


# -- attack restrictions (wave 32B) -- "… and that player may draw a card. If they do, that player can't attack you …": the one player of the trigger
_ONE_MAY = re.compile(r"^that player may (?P<act>.+)$")
_ONE_DID = re.compile(r"^[Ii]f (?:they|that player|the player) do(?:es)?, (?:they|that player) (?P<rest>.+)$")
_AND_ONE = re.compile(r" and (that player may [^.]+\.) (?=[Ii]f (?:they|that player|the player) do(?:es)?, (?:they|that player) )")


def split_one(body: str) -> str:
    """"You draw a card and that player may draw a card. If they do, …" → "You draw a card. That player may draw a card. If they do, …"
    (608.2c: two instructions in order; ``pair`` reads the second and the sentence after it)."""
    return _AND_ONE.sub(lambda m: f". {m[1][:1].upper()}{m[1][1:]} ", body)


def _third_person(rest: str) -> str:
    """"loses 3 life" → "That player loses 3 life" (the player who didn't pay)."""
    return f"That player {rest}"


def _act(phrase: str) -> tuple[list[dict[str, Any]], str] | None:
    """-- each player may (wave 31B) -- the effects of an action every player does for themselves ("scry 1", "draw a card", "create a Treasure
    token", "search their library for a basic land card, reveal it, put it into their hand, then shuffle"), read as the player's own
    instruction ("you"), with its text for the prompt; None for anything else (a choice from a hand or a target isn't read here)."""
    from app.rules import scripts

    if re.search(r"\byou(?:r|rs|rself)?\b", phrase, re.IGNORECASE):
        return None  # ("each opponent may draw a card for each creature you control": "you" is the controller, but they would be "you" for it)
    you = re.sub(r"\bthey control\b", "you control", re.sub(r"\btheir\b", "your", phrase))
    parsed = scripts.parse_effects(you[:1].upper() + you[1:] + ".", "self")
    if parsed is None or parsed[1] is not None or parsed[2] or not parsed[0] or any(
            x["do"] not in _ACT_OK or x.get("as") or x.get("bind") or x.get("did") for x in parsed[0]):
        return None
    dumped = json.dumps(parsed[0])
    if '"ref:' in dumped or '"target' in dumped or '"it"' in dumped or "event_amount" in dumped or "this_way" in dumped:
        return None
    return list(parsed[0]), you


_reading = threading.local()  # (per thread: deck imports and jobs parse cards on other threads, so a shared flag could change a parse)


def _read_alone(text: str) -> bool:
    """-- each player may (wave 31B) -- does the rest of the grammar read this sentence by itself? (``pair`` stands back inside the probe)"""
    from app.rules import scripts

    if getattr(_reading, "on", False):
        return True
    _reading.on = True
    try:
        return scripts.parse_effects(text[:1].upper() + text[1:] + ".", "self", event_player=True) is not None
    finally:
        _reading.on = False


def pair(text: str, following: str | None, effects: list[dict[str, Any]], last_payment: str | None
         ) -> tuple[list[dict[str, Any]], int] | None:
    """The effects of "each opponent may [cost]." and the "who doesn't" sentence after it (``following``, as written), with the
    number of sentences they read (1 or 2), or None (not this grammar, or a form that isn't read)."""
    from app.rules import optional_payment, scripts

    one = False
    if (o := _ONE_MAY.match(text)) is not None and following is not None and (d1 := _ONE_DID.match(following.rstrip(".").strip())) is not None:
        # "That player may draw a card. If they do, that player can't attack you …" (Willie Lumpkin): the one player the trigger is about is the
        # group of one, read as "Each player may …. Each player who does …" for them alone
        text, following, one = f"each player may {o['act']}", f"Each player who does {d1['rest']}", True
    evo = text.startswith("each of that player's opponents may ")  # -- player groups (wave 51G) -- Heartwood Storyteller: every player but the one the trigger names, asked like "each opponent"
    m = _MAY.match("each opponent may " + text[36:] if evo else text)
    if m is None:
        return None
    cost_phrase = m["cost"].replace(" of their choice", "")
    tail = False
    then_texts: list[str] = []
    opp_texts: list[str] = []
    if (inline := _AND_DRAW.match(cost_phrase)) is not None:  # (one optional instruction: the draw is for the players who chose it)
        cost_phrase = "discard your hand"  # (the payer's own: each_may asks every player for theirs)
        then_texts.append(f"That player draws {inline['rest']}")
    nxt = re.sub(r"^then ", "", scripts._lower_first((following or "").rstrip(".").strip()))  # (wave 23A: "Then ~ deals 5 damage to each …")
    entry: dict[str, Any] = {"do": "each_may", "who": "event_player" if one else "event_opponents" if evo else _WHO[m["who"]]}
    if cost_phrase == _SHARES:
        if last_payment is None or not m["if"]:
            return None
        pay = next(e for e in effects if e.get("bind") == last_payment)
        if not re.fullmatch(r"Sacrifice (?:a|an) [a-z]+(?: or [a-z]+)*", str(pay.get("cost") or "")) or pay.get("alts"):
            return None  # (one permanent sacrificed: "it")
        entry["shares_type"] = last_payment
    elif (cost := optional_payment.cost_text(cost_phrase) or optional_payment.cost_text(re.sub(r"\btheir\b", "your", cost_phrase))) is not None:
        entry["cost"] = cost  # (-- trigger other (wave 39A) -- the payer's own: "exile a card from their graveyard" is the cost "exile a card from your graveyard")
    elif (alts := optional_payment.alternatives(cost_phrase)) is not None:
        entry["alts"] = alts
    else:
        sp = _SPLIT_THEN.match(cost_phrase)  # -- each player may (wave 31B) -- "may draw a card, then each player who drew a card this way …"
        if (act := _act(sp["act"] if sp else cost_phrase)) is None or (_read_alone(text) and not one):
            return None  # (a wording the sentence grammar already reads on its own — "each opponent may search their library for a basic land card, …" — stays as it was)
        entry["act"], entry["text"] = act
        if sp:
            nxt, tail = sp["tail"], True
    body: str | None = None
    used = 1 if tail else 2
    acting = "act" in entry
    anyone: str | None = None
    if m["every"] == "any":  # (-- trigger other (wave 39A) -- the one sentence after it is "If a player does, …" / "If no one does, …", for the controller)
        if acting or one or "shares_type" in entry or m["if"] or (ad := _ANY_DID.match(nxt)) is None:
            return None
        anyone, body = ("none" if ad["w"] in ("no one", "no player", "nobody") else "some"), ad["rest"][:1].upper() + ad["rest"][1:]
    if one and not acting:
        return None  # (a cost the one player pays — "That player may discard a card. If they do, …" — is the optional payment's: scripts._that_player_does)
    if acting and "drew a card" in nxt and not any(x["do"] == "draw" for x in entry["act"]):
        return None
    shuffled = acting and _SHUFFLES.match(nxt) is not None and any(x["do"] == "search" for x in entry["act"])
    if shuffled:  # (701.19: each who searched shuffles, once)
        entry["act"] = [*entry["act"], {"do": "shuffle_library", "who": "you", "zones": []}]
    elif acting and (fd := _FOR_EACH_DID.match(nxt)) is not None and fd["who"] == "opponent":
        opp_texts.append(fd["rest"][:1].upper() + fd["rest"][1:])  # ("For each opponent who does, you create a Treasure token.": the controller's own, once each)
    elif (d := _WHO_DID.match(nxt)) is not None and d["who"] == m["who"] and (entry.get("cost", "").startswith("Discard") or acting):
        then_texts.append(_third_person(d["rest"]))
    elif (d := _WHO_DID.match(nxt)) is not None and d["who"] == "opponent" and m["who"] == "player" and acting:
        opp_texts.append(_third_person(d["rest"]))  # -- attack restrictions (wave 32B) -- "Each player may draw a card. Each opponent who does …": not the controller
    elif (td := _TO_EACH_DID.match(nxt)) is not None and td["who"] in (m["who"], "opponent") and entry.get("cost", "").startswith("Discard"):
        opp_texts.append(f"{td['lead']} to that player")  # ("each opponent who …" among each player: not the controller)
    elif then_texts and not opp_texts:
        used = 1  # (the inline form stands alone; the sentence after it is its own)
    elif (f := _FOR_EACH.match(nxt)) is not None and f["who"] == m["who"]:
        body = f["rest"][:1].upper() + f["rest"][1:]
    elif (w := _WHO_DOESNT.match(nxt)) is not None and w["who"] == m["who"]:
        body = _third_person(w["rest"])
    elif (t := _TO_EACH.match(nxt)) is not None and t["who"] == m["who"]:
        if t["this"] and not t["disc"] and not (entry.get("cost") or "").startswith("Sacrifice") and not all(
                a.startswith("Sacrifice") for a in entry.get("alts") or ()):
            return None  # ("who didn't sacrifice a permanent this way": only after a sacrifice)
        if t["disc"] and not (any(x.startswith("Discard") for x in entry.get("alts") or ()) and any(x.startswith("Sacrifice") for x in entry.get("alts") or ())):
            return None  # -- wave 110B -- "who didn't sacrifice a permanent or discard a card this way" (Osseous Sticktwister): only after that choice of two
        body = f"{t['lead']} to that player"
    if body is None and not then_texts and not opp_texts and not acting:
        return None
    if acting and body is not None:
        return None  # ("Each opponent who doesn't …" after an action: not read until a card needs it — Wernog's count of who did is not read either)
    if acting and not (body or then_texts or opp_texts or shuffled):
        used = 1  # (an action alone; the sentence after it is its own)

    def plain(sentence: str) -> list[dict[str, Any]] | None:
        parsed = scripts.parse_effects(sentence + ".", "self", event_player=True)
        if parsed is None or parsed[1] is not None or parsed[2] or not parsed[0]:
            return None
        dumped = json.dumps(parsed[0])
        if '"ref:' in dumped or '"target' in dumped or '"it"' in dumped or "event_amount" in dumped or "this_way" in dumped:
            return None  # (only "that player", "you" and plain counts)
        return list(parsed[0])

    if body is not None:
        if (inner := plain(body)) is None or (anyone and re.search(r"event_player|that_player", json.dumps(inner))):
            return None
        entry["effects"] = inner
        if anyone:
            entry["any"] = anyone
    for key, texts_ in (("then", then_texts), ("then_opp", opp_texts)):  # (-- each player may (wave 23A) -- what the players who paid get)
        if texts_:
            done = [plain(t) for t in texts_]
            if any(x is None for x in done):
                return None
            entry[key] = [e for x in done for e in (x or [])]
    out = [entry]
    if m["if"]:
        if not last_payment:
            return None
        out = [{"do": "only_if", "cond": {"succeeded": last_payment}, "skip": 1}, *out]
    if m["cond"]:  # ("At the beginning of your end step, if you descended this turn, each opponent may …": 603.4)
        from app.rules import conditions

        cond = conditions.parse(m["cond"], objects=True)
        if cond is None:
            return None
        out = [{"do": "only_if", "cond": cond, "skip": len(out)}, *out]
    return out, used


_UNLESS_EACH = re.compile(r"^(?:if (?P<cond>[^,]+), )?each (?P<who>opponent|player) (?P<lead>.+?) unless (?:they|that player) (?P<act>.+)$")
# -- dungeons (wave 45B) -- "For each opponent, you create a 2/2 black Zombie creature token unless that player sacrifices a creature of their choice."
# (Acererak the Archlich): the controller's own instruction, once for each opponent who doesn't (118.12a)
_UNLESS_FOR_EACH = re.compile(r"^for each (?P<who>opponent|player), (?P<lead>you .+?) unless that player (?P<act>.+)$")
# -- cost reductions paid with objects (wave 47C) -- "Then for each blight counter on it, each opponent loses 4 life unless that player sacrifices a nonland permanent of their choice
# or discards a card." (Rottenmouth Viper): the choice is made once for each counter
_UNLESS_TIMES = re.compile(r"^(?:then )?for each (?P<count>[a-z\-]+ counters? on it), (?P<rest>each (?:opponent|player) .+)$")
_REPEAT_X = re.compile(r"^repeat the following process X times$", re.IGNORECASE)


def repeat_sentence(text: str, following: str | None) -> list[dict[str, Any]] | None:
    """-- cost reductions paid with objects (wave 47C) -- "Repeat the following process X times. Each opponent loses 3 life unless that player sacrifices a nonland permanent of their
    choice or discards a card." (Torment of Hailfire): the second sentence, done X times (the X of the spell), one after the other."""
    if _REPEAT_X.match(text) is None or following is None:
        return None
    from app.rules import scripts

    inner = unless_sentence(scripts._lower_first(following.rstrip(".").strip()))
    return [{**inner[0], "rounds": {"x": 1}}] if inner is not None and len(inner) == 1 and inner[0]["do"] == "each_may" and "times" not in inner[0] else None


def unless_sentence(text: str) -> list[dict[str, Any]] | None:
    """-- if you do (wave 15C) -- "Each opponent loses 3 life unless they discard a card." / "… unless that player sacrifices a nonland
    permanent of their choice or discards a card." (Court of Ambition, Nicol Bolas, the Deceiver): 118.12a reads it as "Each
    opponent may [cost]. Each opponent who doesn't [effect]" — the same entry as ``pair`` builds (turn order, 101.4)."""
    from app.rules import optional_payment, scripts

    if (t := _UNLESS_TIMES.match(text)) is not None:  # -- cost reductions paid with objects (wave 47C) -- "Then for each blight counter on it, each opponent loses 4 life unless …"
        from app.rules import values

        count = values.parse_count(t["count"], it="self")
        inner = unless_sentence(t["rest"]) if isinstance(count, dict) and "counters" in count else None
        return [{**inner[0], "times": count}] if inner is not None and len(inner) == 1 and inner[0]["do"] == "each_may" else None
    m = _UNLESS_EACH.match(text)
    mine = None if m else _UNLESS_FOR_EACH.match(text)
    if (m := m or mine) is None:
        return None
    act = re.sub(r"\b(pays?|discards?|sacrifices?|returns?|exiles?)\b", lambda v: v[1].rstrip("s") if v[1] != "pays" else "pay", m["act"])
    if " another " in f" {act} ":
        return None  # ("another" than what: not read)
    act = act.replace(" of their choice", "")
    entry: dict[str, Any] = {"do": "each_may", "who": _WHO[m["who"]]}
    if (cost := optional_payment.cost_text(act)) is not None:
        entry["cost"] = cost
    elif (alts := optional_payment.alternatives(act)) is not None:
        entry["alts"] = alts
    else:
        return None
    if not optional_payment.defers(entry.get("cost"), entry.get("alts")):
        return None  # (a mana payment by each opponent in turn: refused since wave 4C, as before)
    parsed = scripts.parse_effects((m["lead"] if mine else _third_person(m["lead"])) + ".", "self", event_player=True)
    if parsed is None or parsed[1] is not None or parsed[2] or not parsed[0]:
        return None
    dumped = json.dumps(parsed[0])
    if '"ref:' in dumped or '"target' in dumped or '"it"' in dumped or "event_amount" in dumped or "this_way" in dumped:
        return None
    entry["effects"] = parsed[0]
    out = [entry]
    if not mine and m["cond"]:  # ("At the beginning of your end step, if you attacked this turn, each opponent loses …": 603.4)
        from app.rules import conditions

        cond = conditions.parse(m["cond"], objects=True)
        if cond is None:
            return None
        out = [{"do": "only_if", "cond": cond, "skip": 1}, *out]
    return out


def _for(value: Any, pid: str) -> Any:
    """The effects with "that player" (event_player) as ``pid``."""
    if value == "event_player":
        return f"player:{pid}"
    if isinstance(value, str) and value.startswith("controlled:event_player|"):  # -- attack restrictions (wave 32B) -- "creatures that player controls"
        return f"controlled:player:{pid}|{value.partition('|')[2]}"
    if isinstance(value, list):
        return [_for(v, pid) for v in value]
    if isinstance(value, dict):
        return {k: _for(v, pid) for k, v in value.items()}
    return value


def _shared_cost(plan: Plan, ctx: Context, bind: str) -> str | None:
    """"Sacrifice a permanent that shares a card type with it": the card types of the permanent sacrificed (608.2h)."""
    from app.rules import context

    found = context.info(plan, ctx, bind)
    if found is None:
        return None
    types = [t for t in _TYPES if t in found[1].types]
    if not types:
        return None
    words = " or ".join(t.lower() for t in types)
    return f"Sacrifice {'an' if words[0] in 'aeiou' else 'a'} {words}"


def each_may(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """One optional payment per player of the group (turn order, 101.4), then the effect for each who didn't pay."""
    from app.rules import effects, optional_payment

    players = [p for p in plan.apnap() if p in effects._players(plan, ctx, e["who"])]
    cost = e.get("cost")
    if "per" in e:  # Shared “unless any player pays {X}”: fixed for this resolution.
        from app.rules import unless_pays

        cost = unless_pays.concrete_cost(plan, ctx, e)
    if e.get("shares_type"):
        cost = _shared_cost(plan, ctx, e["shares_type"])
        if cost is None:  # (no card type to share: no payment can be made — every player "doesn't")
            cost = ""
    at = ctx["next"]
    if e.get("rounds") is not None:  # -- cost reductions paid with objects (wave 47C) -- "Repeat the following process X times." (Torment of Hailfire): the instruction once for each repetition, one after the other
        # (each repetition is done separately: the choices in turn order, then the actions together, ruling 2017-07-14)
        once = {k: v for k, v in e.items() if k != "rounds"}
        ctx["effects"] = [*ctx["effects"][:at], *(dict(once) for _ in range(max(0, effects._amount(plan, ctx, e["rounds"])))), *ctx["effects"][at:]]
        effects.continue_effects(plan, ctx)
        return False
    tag = f"m{at}_"
    added: list[dict[str, Any]] = []
    # -- review (wave 6R) -- 101.4: every choice first (in turn order), then the payments together (pay_deferred)
    defer = optional_payment.defers(cost, None if cost is not None else e.get("alts"))
    acting = bool(e.get("act"))
    # -- cost reductions paid with objects (wave 47C) -- "for each blight counter on it, each opponent … unless …": each player makes that many choices in a row (the ruling of Rottenmouth
    # Viper: all of a player's, then the next player's, then the actions together), none of the same object twice (optional_payment._choose_next)
    times = 1 if e.get("times") is None else max(0, effects._amount(plan, ctx, e["times"]))
    slots = [(i, p, f"{tag}{i}" if e.get("times") is None else f"{tag}{i}_{k}") for i, p in enumerate(players) for k in range(times)]
    if acting:  # -- each player may (wave 31B) -- 101.4: every player answers in turn order (tempting offers' question), then each who said yes does it as "you"
        n = len(e["act"])
        added += [{"do": "tempt_ask", "player": p, "bind": f"{tag}{i}", "text": e["text"]} for i, p in enumerate(players)]
        for i, p in enumerate(players):
            added += [{"do": "only_if", "cond": {"flag": f"{tag}{i}"}, "skip": n + 2}, {"do": "as_player", "player": p},
                      *copy.deepcopy(e["act"]), {"do": "as_player_end"}]
    else:
        for _, p, name in slots:
            pay: dict[str, Any] = {"do": "optional_payment", "who": f"player:{p}", "cost": cost if cost is not None else e["alts"][0], "bind": name}
            if 'cost_has_x' in e:
                pay['cost_has_x'] = e['cost_has_x']
            if e.get("alts") and cost is None:
                pay["alts"] = list(e["alts"])
            if defer:
                pay["defer"] = True
            added.append(pay)
        if defer and slots:
            added.append({"do": "pay_deferred", "binds": [name for _, _, name in slots]})
    answered = "flag" if acting else "succeeded"  # (the answer of each: a recorded verdict, or a payment made)
    if e.get("verdict"):
        # Flat continuations let the grammar bind pronouns to earlier instructions.
        added.append({"do": "only_if", "cond": {"any": [{answered: name} for _, _, name in slots]},
                      "bind": e["verdict"], "skip": 0})
    if e.get("any") and e.get("effects"):  # -- trigger other (wave 39A) -- once, if any player (or, "none", no player) paid: the controller's own instructions
        paid = {"any": [{answered: f"{tag}{i}"} for i in range(len(players))]}
        added += [{"do": "only_if", "cond": paid if e["any"] == "some" else {"not": paid}, "skip": len(e["effects"])}, *copy.deepcopy(e["effects"])]
    if e.get('group_life_loss'):
        added.append({'do': 'each_unpaid_life', 'slots': [[p, name] for _, p, name in slots],
                      'n': e['effects'][0]['n']})
    for _, p, name in slots:
        inner = [] if e.get("any") or e.get('group_life_loss') else _for(e.get("effects") or [], p)
        if inner:
            added += [{"do": "only_if", "cond": {answered: name, "negate": True}, "skip": len(inner)}, *inner]
        for key in ("then", "then_opp"):  # -- each player may (wave 23A) -- the players who paid: "Each player who discarded a card this way draws a card"
            if e.get(key) and (key == "then" or p != ctx["controller"]):
                done = _for(e[key], p)
                added += [{"do": "only_if", "cond": {answered: name}, "skip": len(done)}, *done]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    effects.continue_effects(plan, ctx)
    return False


def each_unpaid_life(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import conditions, effects, replace

    losses = [(pid, effects._amount(plan, {**ctx, 'recipient': pid}, e['n'])) for pid, binding in e['slots']
              if pid in plan.live() and not conditions.holds(plan, ctx, {'succeeded': binding})]
    return replace.lose_life(plan, losses, actor=ctx['controller'], then=effects._then(ctx, e), ctx=ctx)


PRIMITIVES = {"each_may": each_may, 'each_unpaid_life': each_unpaid_life}


def _pay_deferred(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:  # -- review (wave 6R) --
    from app.rules import optional_payment

    return optional_payment.pay_deferred(plan, ctx, e)


PRIMITIVES["pay_deferred"] = _pay_deferred


def repeated_discard(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Repeat the entire simultaneous opponent operation, not one payer at a time."""
    m = re.fullmatch(r"Each (?P<who>opponent|player) may discard a card\. If they don't, they lose (?P<n>\d+) life\. Repeat this process (?P<times>one|two|three|four|five|six|seven|eight|nine|ten) more times\.", body.strip())
    if m is None:
        return None
    numbers = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
    return ([{'do': 'each_may', 'who': _WHO[m['who']], 'cost': 'Discard a card',
              'effects': [{'do': 'lose_life', 'who': 'event_player', 'n': int(m['n'])}],
              'rounds': numbers[m['times']] + 1, 'group_life_loss': True}], None, False)
