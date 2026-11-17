"""-- Teach Fyodor -- mechanics and card lines a player taught the engine with snap-together pieces (docs/TEACH_FYODOR.md).

A taught entry is pure data: a **keyword** ("Plunge N", with its reminder text), an **action** (a keyword action like "dive": what
happens to the creature a card says it of — "it dives", "target creature dives", or "plunge 2" for one with a number) or one **card
line** the engine left manual, and the abilities that stand for it, each a stack of pieces from ``taught_vocab``. ``compile_entry``
writes those abilities out as Oracle sentences; ``apply`` puts the sentences in place of the keyword, the action's phrase (or the
line) in a card's Oracle text, so the engine's own parser reads them into its own definitions — the same path every printed card
takes. Nothing is evaluated: a piece id or a value that isn't in the vocabulary is refused (``clean_entry``).

A game keeps the entries it started with (``GameState.taught``, stamped by ``GameSession``): ``TaughtCards`` serves that game's
card data with its own entries applied, so editing the library later never changes a game in progress or a saved one.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any

from app.rules.taught_vocab import OPTIONS, PIECE

FORMAT = "fyodor-teach"
FORMAT_VERSION = 1
MAX_ABILITIES = 4
MAX_BODY = 12
MAX_CHILDREN = 4
MAX_ENTRIES = 500
NAME_RE = re.compile(r"[A-Z][A-Za-z'\-]{1,23}(?: [A-Za-z'\-]{1,23}){0,2}")
ACTION_RE = re.compile(r"[a-z][a-z\-]{1,23}")  # (one lowercase verb: cards say "it dives", "target creature dives")
# the subjects a card's text gives a keyword action ("it dives", "target creature dives"); the card's own name is added per card
ACTION_SUBJECTS = (r"it|this creature|this permanent|that creature|(?:up to one |another )?target creature(?: you control)?"
                   r"|each (?:other )?(?:attacking |blocking |tapped |untapped )?creature(?: you control)?")
# -- dive (wave DV) -- the plural subjects, which take the bare verb ("creatures you control dive", "up to two target creatures dive"); shared with
# the native dive (app/rules/dive.py), so a taught action and the built-in one read the same subjects
ACTION_GROUP_SUBJECTS = (r"(?:all )?(?:other )?(?:attacking |blocking |tapped |untapped )?creatures you control"
                         r"|(?:up to )?(?:two|three|four|five|any number of) target creatures(?: you control)?|those creatures")
MANA_RE = re.compile(r"(?:\{(?:[0-9]|1[0-9]|20|W|U|B|R|G|C|N|W/U|U/B|B/R|R/G|G/W|W/B|U/R|B/G|R/W|G/U)\}){1,8}")
COLORED_MANA_RE = re.compile(r"(?:\{[WUBRGC]\}){1,6}")
_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
          "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
_TOKEN = re.compile(r"\{(self|[a-z]+)(?::([a-z]+))?\}")


class TeachError(ValueError):
    """A piece, value or shape the vocabulary doesn't allow (``where``: which block)."""

    def __init__(self, message: str, where: str = "") -> None:
        super().__init__(f"{where}: {message}" if where else message)
        self.where = where
        self.plain = message


# ---------------------------------------------------------------------------------------------------------------- reading back
def self_word(type_line: str) -> str:
    """How an ability names its own object ("this creature"), from the card's type line."""
    for t in ("Creature", "Land", "Artifact", "Enchantment", "Planeswalker", "Battle"):
        if re.search(rf"\b{t}\b", type_line or ""):
            return f"this {t.lower()}"
    if re.search(r"\b(Instant|Sorcery)\b", type_line or ""):
        return "this spell"
    return "this permanent"


def _number(value: Any, n: int | None) -> int | None:
    """A number slot's value: the keyword's N when it holds "N" (None: unbound, read as "N")."""
    if value == "N":
        return n
    if value == "-N":
        return -n if n is not None else None
    return int(value)


def _word(v: int) -> str:
    return _WORDS[v] if 0 <= v < len(_WORDS) else str(v)


def render(template: str, values: dict[str, Any], *, n: int | None = None, me: str = "this creature") -> str:
    """One piece's words. Same rules as ``frontend/src/teach/sentence.ts`` (tests/fixtures/teach_sentences.json checks both)."""
    def sub(m: re.Match[str]) -> str:
        key, form = m[1], m[2]
        if key == "self":
            return me
        if key not in values:
            return m[0]
        raw = values[key]
        if isinstance(raw, str) and raw in OPTIONS:
            opt = OPTIONS[raw]
            if form == "vs":
                return "" if opt.get("plural") else "s"
            return str(opt["text"]).replace("{self}", me)
        if isinstance(raw, str) and raw.startswith("{"):  # a mana cost
            return raw.replace("{N}", "{N}" if n is None else "{" + str(n) + "}")
        v = _number(raw, n)
        unbound = v is None
        sign = "-" if raw == "-N" else "+"
        if form == "word":
            return "N" if unbound else _word(v)  # type: ignore[arg-type]
        if form == "a":
            return "N" if unbound else ("a" if v == 1 else _word(v))  # type: ignore[arg-type]
        if form == "s":
            return "s" if unbound or v != 1 else ""
        if form == "signed":
            return f"{sign}N" if unbound else (f"+{v}" if v >= 0 else str(v))  # type: ignore[operator]
        if form == "mana":
            return "{N}" if unbound else "{" + str(v) + "}"
        return "N" if unbound else str(v)

    return _TOKEN.sub(sub, template)


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _piece_text(block: dict[str, Any], n: int | None, me: str) -> str:
    return render(PIECE[block["id"]]["text"], block.get("values") or {}, n=n, me=me)


def _may(text: str) -> str:
    return "you may " + (text[4:] if text.startswith("you ") else text)


def _sentences(stmts: list[dict[str, Any]], n: int | None, me: str) -> list[str]:
    out: list[str] = []
    join = False
    for st in stmts:
        role = PIECE[st["id"]]["role"]
        if role == "then":
            join = True
            continue
        if role == "effect":
            s = _piece_text(st, n, me)
        elif role == "may":
            s = _may(_piece_text(st["body"][0], n, me))
        elif role == "ifdo":
            s = "if you do, " + ", then ".join(_sentences(st.get("body") or [], n, me))
        elif role == "optional_cost":
            out.append(_piece_text(st, n, me))
            s = "if you do, " + ", then ".join(_sentences(st.get("body") or [], n, me))
            join = False
        else:
            continue
        if join and out:
            out[-1] += ", then " + s
        else:
            out.append(s)
        join = False
    return out


def ability_text(ability: dict[str, Any], *, n: int | None = None, me: str = "this creature") -> str:
    """One ability as an Oracle sentence ("When this creature enters, mill two cards. …")."""
    hat = PIECE[ability["hat"]["id"]]
    body = list(ability.get("body") or [])
    if hat["role"] == "action_hat":  # (what happens to the object the card says the action of: "it" — compile_entry)
        return " ".join(_cap(s) + "." for s in _sentences(body, n, me)) or "…"
    cond = body.pop(0) if body and PIECE[body[0]["id"]]["role"] == "condition" else None
    if hat["role"] == "static_hat":
        static = next((b for b in body if PIECE[b["id"]]["role"] == "static"), None)
        if static is not None and cond is None and PIECE[static["id"]].get("bare"):
            return _cap(render(PIECE[static["id"]]["bare"], static.get("values") or {}, n=n, me=me))
        words = _piece_text(static, n, me) if static else "…"
        return _cap(f"as long as {_piece_text(cond, n, me)}, {words}" if cond else words) + "."
    if hat["role"] == "activated":
        costs = [_piece_text(b, n, me) for b in body if PIECE[b["id"]]["role"] == "cost"]
        limits = [_piece_text(b, n, me) for b in body if PIECE[b["id"]]["role"] == "limit"]
        rest = [b for b in body if PIECE[b["id"]]["role"] not in ("cost", "limit")]
        said = " ".join(_cap(s) + "." for s in _sentences(rest, n, me)) or "…"
        return " ".join([f"{', '.join(_cap(c) for c in costs) or '…'}: {said}", *limits])
    head = _piece_text(ability["hat"], n, me)
    if cond is not None:
        head += f", if {_piece_text(cond, n, me)}"
    said = _sentences(body, n, me)
    if not said:
        return head + ", …"
    return f"{head}, {said[0]}." + "".join(f" {_cap(s)}." for s in said[1:])


def compile_entry(entry: dict[str, Any], *, n: int | None = None, me: str = "this creature") -> list[str]:
    """The Oracle lines that stand for a taught keyword (with its number ``n``) or card line; for an action, what happens to "it"
    ("It can't be blocked until it deals combat damage while attacking.")."""
    if entry.get("kind") == "action":
        me = "it"
    return [ability_text(a, n=n, me=me) for a in entry["abilities"]]


def action_phrase(entry: dict[str, Any], *, n: int | None = None, me: str = "it") -> str:
    """How a card says a taught action: "it dives"; with a number, "plunge 2" (the imperative, as "bolster 2" is said)."""
    if entry.get("param"):
        return f"{entry['name']} {'N' if n is None else n}"
    return f"{me} {entry['name']}s"


def action_sentences(entry: dict[str, Any], *, n: int | None = None, me: str = "it") -> str:
    """The action's effects as the clause that replaces its phrase: the first sentence runs on from the card's own words, the rest are
    sentences of their own ("it can't be blocked until it deals combat damage while attacking. Draw a card")."""
    said = [s for a in entry["abilities"] for s in _sentences(list(a.get("body") or []), n, me)]
    if not said:
        return "…"
    return said[0] + "".join(f". {_cap(s)}" for s in said[1:])


# ---------------------------------------------------------------------------------------------------------------- checking shape
def _value(slot: dict[str, Any], raw: Any, where: str, *, allow_param: bool) -> Any:
    kind = slot["kind"]
    if kind == "choice":
        if not isinstance(raw, str) or raw not in slot["options"]:
            raise TeachError("pick one of the offered choices", where)
        return raw
    if kind == "mana":
        pattern = COLORED_MANA_RE if slot.get("colored") else MANA_RE
        if not isinstance(raw, str) or not pattern.fullmatch(raw):
            raise TeachError("a mana cost like {2}{U}" if not slot.get("colored") else "coloured mana like {G}{G}", where)
        if "{N}" in raw and not allow_param:
            raise TeachError("N is only for a keyword with a number", where)
        return raw
    if raw in ("N", "-N") and (raw == "N" or kind == "signed"):
        if not allow_param or not slot.get("param"):
            raise TeachError("N is only for a keyword with a number", where)
        return raw
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TeachError("a whole number", where)
    if not slot["min"] <= raw <= slot["max"]:
        raise TeachError(f"a number from {slot['min']} to {slot['max']}", where)
    return raw


def _block(raw: Any, where: str, *, allow_param: bool, depth: int) -> dict[str, Any]:
    if not isinstance(raw, dict) or not set(raw) <= {"id", "values", "body"}:
        raise TeachError("not a piece", where)
    pid = raw.get("id")
    if not isinstance(pid, str) or pid not in PIECE:
        raise TeachError("unknown piece", where)
    piece = PIECE[pid]
    slots = piece.get("slots") or {}
    values = raw.get("values") or {}
    if not isinstance(values, dict) or not set(values) <= set(slots):
        raise TeachError(f"{piece['label']}: unknown setting", where)
    clean = {k: _value(slots[k], values.get(k, slots[k]["default"]), f"{where} {piece['label']}", allow_param=allow_param) for k in slots}
    out: dict[str, Any] = {"id": pid}
    if clean:
        out["values"] = clean
    if piece["role"] in ("may", "ifdo", "optional_cost"):
        kids = raw.get("body") or []
        if not isinstance(kids, list) or len(kids) > MAX_CHILDREN or depth > 2:
            raise TeachError(f"{piece['label']}: too many pieces inside", where)
        out["body"] = [_block(k, f"{where}.{i + 1}", allow_param=allow_param, depth=depth + 1) for i, k in enumerate(kids)]
    elif raw.get("body"):
        raise TeachError(f"{piece['label']} can't hold other pieces", where)
    return out


def _check_flow(body: list[dict[str, Any]], where: str, *, inside: bool = False) -> None:
    """Effects, "you may", "if you do" and "then" in an order that reads as English."""
    prev: dict[str, Any] | None = None
    for i, st in enumerate(body):
        role = PIECE[st["id"]]["role"]
        at = f"{where}.{i + 1}"
        label = PIECE[st["id"]]["label"]
        if role not in ("effect", "may", "ifdo", "then", "optional_cost"):
            raise TeachError(f"{label} doesn't belong here", at)
        if role in ("may", "ifdo", "optional_cost") and not st.get("body"):
            raise TeachError(f"put a Do piece inside {label}", at)
        if role == "may":
            if len(st["body"]) != 1 or PIECE[st["body"][0]["id"]]["role"] != "effect" or not PIECE[st["body"][0]["id"]].get("may"):
                raise TeachError("\"You may\" holds one Do piece that you do yourself", at)
        if role == "ifdo" and (prev is None or PIECE[prev["id"]]["role"] != "may"):
            raise TeachError("\"If you do\" comes right after \"You may\"", at)
        if role == "optional_cost" and inside:
            raise TeachError(f"{label} can't go inside another piece", at)
        if role in ("ifdo", "optional_cost"):
            _check_flow(st["body"], at, inside=True)
            if any(PIECE[k["id"]]["role"] in ("ifdo", "optional_cost") for k in st["body"]):
                raise TeachError("one \"if you do\" at a time", at)
        if role == "then":
            nxt = body[i + 1] if i + 1 < len(body) else None
            if prev is None or nxt is None or PIECE[nxt["id"]]["role"] not in ("effect", "may") \
                    or PIECE[prev["id"]]["role"] not in ("effect", "may"):
                raise TeachError("\"Then\" goes between two Do pieces", at)
        piece = PIECE[st["id"]] if role == "effect" else (PIECE[st["body"][0]["id"]] if role == "may" else None)
        if piece is not None and piece.get("after"):
            before = [b for b in body[:i] if PIECE[b["id"]]["role"] != "then"]
            last = before[-1] if before else None
            if last is None or last["id"] != piece["after"]:
                raise TeachError(f"{piece['label']} comes right after {PIECE[piece['after']]['label']}", at)
        prev = st
    if not any(PIECE[st["id"]]["role"] in ("effect", "may", "optional_cost") for st in body):
        raise TeachError("add a Do piece: what happens?", where)


def _all_blocks(body: list[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for b in body:
        yield b
        yield from _all_blocks(b.get("body") or [])


def _ability(raw: Any, where: str, *, allow_param: bool, kind: str = "keyword") -> dict[str, Any]:
    if not isinstance(raw, dict) or not set(raw) <= {"hat", "body"}:
        raise TeachError("not an ability", where)
    hat = _block(raw.get("hat"), where, allow_param=allow_param, depth=0)
    role = PIECE[hat["id"]]["role"]
    if role not in ("trigger", "activated", "static_hat", "action_hat"):
        raise TeachError("start with a When piece", where)
    if (role == "action_hat") != (kind == "action"):
        raise TeachError("an action holds what happens; a keyword or a card's line starts with a When piece", where)
    body_raw = raw.get("body") or []
    if not isinstance(body_raw, list) or len(body_raw) > MAX_BODY:
        raise TeachError(f"at most {MAX_BODY} pieces in one ability", where)
    body = [_block(b, f"{where}.{i + 1}", allow_param=allow_param, depth=1) for i, b in enumerate(body_raw)]
    roles = [PIECE[b["id"]]["role"] for b in body]
    for b in _all_blocks(body):  # (a piece whose words only read under some When pieces: "counter that spell or ability …")
        hats = PIECE[b["id"]].get("hats")
        if hats and hat["id"] not in hats:
            raise TeachError(f"{PIECE[b['id']]['label']} only goes under {' or '.join(PIECE[h]['label'] for h in hats)}", where)
    if "condition" in roles[1:]:
        raise TeachError("an If piece goes first, right under When", where)
    rest = body[1:] if roles[:1] == ["condition"] else body
    if role == "action_hat":
        if roles[:1] == ["condition"]:
            raise TeachError("an action has no If piece: the card's own words say when it happens", where)
        _check_flow(rest, where)
    elif role == "trigger":
        _check_flow(rest, where)
    elif role == "activated":
        if roles[:1] == ["condition"]:
            raise TeachError("a Pay-to-use ability has no If piece", where)
        costs = [i for i, r in enumerate(roles) if r == "cost"]
        if not costs:
            raise TeachError("add a Cost piece: what do you pay?", where)
        if costs != list(range(len(costs))):
            raise TeachError("Cost pieces go first, right under Pay to use it", where)
        limits = [i for i, r in enumerate(roles) if r == "limit"]
        if limits and limits != list(range(len(roles) - len(limits), len(roles))):
            raise TeachError("\"Activate only …\" pieces go last", where)
        if len({body[i]["id"] for i in costs}) != len(costs) and any(body[i]["id"] in ("cost_tap", "cost_sac_self") for i in costs):
            raise TeachError("each cost once", where)
        mid = body[len(costs):len(body) - len(limits)]
        if any(PIECE[b["id"]]["role"] == "optional_cost" for b in mid):
            raise TeachError("a Pay-to-use ability already has its cost", where)
        _check_flow(mid, where)
    else:
        statics = [b for b in rest if PIECE[b["id"]]["role"] == "static"]
        if len(rest) != 1 or len(statics) != 1:
            raise TeachError("Always holds one Always piece (and maybe an If piece above it)", where)
        if roles[:1] != ["condition"] and PIECE[statics[0]["id"]].get("needs_condition"):
            raise TeachError(f"{PIECE[statics[0]['id']]['label']} needs an If piece above it", where)
        if roles[:1] == ["condition"] and (PIECE[statics[0]["id"]].get("no_condition")):
            raise TeachError(f"{PIECE[statics[0]['id']]['label']} can't depend on an If piece", where)
        if roles[:1] == ["condition"] and PIECE[body[0]["id"]].get("trigger_only"):
            raise TeachError(f"{PIECE[body[0]['id']]['label']} only works with a When piece", where)
    return {"hat": hat, "body": body}


def _text(raw: Any, field: str, limit: int, *, required: bool = True) -> str:
    if raw is None and not required:
        return ""
    if not isinstance(raw, str) or (required and not raw.strip()) or len(raw) > limit or any(ord(c) < 32 for c in raw):
        raise TeachError(f"{field}: up to {limit} characters of plain text")
    return raw.strip()


def clean_entry(raw: Any) -> dict[str, Any]:
    """A taught entry checked against the vocabulary and rebuilt from scratch (unknown keys, pieces, values: refused)."""
    if not isinstance(raw, dict):
        raise TeachError("not a taught entry")
    kind = raw.get("kind")
    allowed = {"kind", "name", "abilities", "param", "reminder", "oracle_id", "line", "card_name", "type_line"}
    if not set(raw) <= allowed:
        raise TeachError(f"unknown field: {sorted(set(raw) - allowed)[0]}")
    out: dict[str, Any] = {"kind": kind}
    if kind == "keyword":
        name = _text(raw.get("name"), "name", 50)
        if not NAME_RE.fullmatch(name):
            raise TeachError("name: a word or two, starting with a capital letter (like Dive)")
        from app.rules.oracle import keyword_name

        if keyword_name(name) is not None or keyword_name(name + " 1") is not None:
            raise TeachError(f"name: Fyodor already knows {name}")
        param = raw.get("param", False)
        if not isinstance(param, bool):
            raise TeachError("param: yes or no")
        out.update(name=name, param=param, reminder=_text(raw.get("reminder"), "reminder", 400, required=False))
    elif kind == "action":
        name = _text(raw.get("name"), "name", 30).lower()
        if not ACTION_RE.fullmatch(name):
            raise TeachError("name: one word, the verb a card uses (like dive: cards say \"it dives\")")
        from app.rules.analysis import KEYWORD_ACTIONS

        if name in KEYWORD_ACTIONS or name.rstrip("e") in {k.rstrip("e") for k in KEYWORD_ACTIONS}:
            raise TeachError(f"name: Fyodor already knows {name}")
        param = raw.get("param", False)
        if not isinstance(param, bool):
            raise TeachError("param: yes or no")
        out.update(name=name, param=param, reminder=_text(raw.get("reminder"), "reminder", 400, required=False))
    elif kind == "card":
        oid = _text(raw.get("oracle_id"), "card", 64)
        if not re.fullmatch(r"[0-9a-zA-Z\-]{1,64}", oid):
            raise TeachError("card: not a card id")
        out.update(oracle_id=oid, line=_text(raw.get("line"), "line", 1000), card_name=_text(raw.get("card_name"), "card name", 200, required=False),
                   name=_text(raw.get("name") or raw.get("card_name") or "Card line", "name", 200),
                   type_line=_text(raw.get("type_line"), "type line", 200, required=False))
        param = False
    else:
        raise TeachError("kind: a keyword, an action or a card line")
    abilities = raw.get("abilities")
    most = 1 if kind == "action" else MAX_ABILITIES
    if not isinstance(abilities, list) or not 1 <= len(abilities) <= most:
        raise TeachError(f"between 1 and {most} abilities" if most > 1 else "an action is one stack of Do pieces")
    out["abilities"] = [_ability(a, f"Ability {i + 1}", allow_param=bool(param), kind=str(kind)) for i, a in enumerate(abilities)]
    return out


def problems(raw: Any) -> list[dict[str, str]]:
    """What's missing or out of place, for the page ([] when the shape is right)."""
    try:
        clean_entry(raw)
    except TeachError as exc:
        return [{"where": exc.where, "message": exc.plain}]
    return []


def match_key_of(entry: dict[str, Any]) -> str:
    """What makes two entries teach the same thing: a keyword's name, or one card's line."""
    if entry["kind"] in ("keyword", "action"):
        return f"{entry['kind']}:{entry['name'].lower()}"
    return f"{entry['kind']}:{entry.get('oracle_id') or entry.get('card_id')}:{entry.get('line') or ''}"


# ---------------------------------------------------------------------------------------------------------------- the library
_library: tuple[dict[str, Any], ...] = ()


def set_library(entries: Iterable[dict[str, Any]]) -> None:
    """The enabled entries new games start with (the host's library; ``services`` keeps it current)."""
    global _library
    _library = tuple(json.loads(json.dumps(e)) for e in entries)


def snapshot() -> list[dict[str, Any]]:
    """A copy of the library for a new game's state (plain data)."""
    return json.loads(json.dumps(list(_library)))


# ---------------------------------------------------------------------------------------------------------------- applying
def _keyword_line(core: str, keywords: dict[str, dict[str, Any]]) -> tuple[list[str], list[tuple[dict[str, Any], int | None]]] | None:
    """A keyword line naming taught keywords: (the other keywords it lists, [(entry, its number)]); None when it names none."""
    from app.rules.oracle import keyword_name

    pieces = [p.strip() for p in re.split(r"[,;]\s*", core.rstrip(".")) if p.strip()]
    found, rest = [], []
    for p in pieces:
        m = re.fullmatch(r"([A-Za-z'\- ]+?)(?: (\d{1,2}))?", p)
        entry = keywords.get(m[1].lower()) if m else None
        if entry is not None and bool(m[2]) == bool(entry.get("param")):  # type: ignore[index]
            found.append((entry, int(m[2]) if m[2] else None))  # type: ignore[index]
        elif keyword_name(p) is not None:
            rest.append(p)
        else:
            return None
    return (rest, found) if found else None


def action_pattern(entry: dict[str, Any], card_name: str = "") -> re.Pattern[str]:
    """Where a card's text says the action: "it dives" / "Target creature dives" (``subj``), or "plunge 2" (``n``) for one with a number."""
    subjects = ACTION_SUBJECTS + (f"|{re.escape(card_name)}" if card_name else "")
    name = re.escape(entry["name"])
    if entry.get("param"):
        return re.compile(rf"(?<![A-Za-z])(?:(?P<subj>{subjects}) )?{name}s? (?P<n>\d{{1,2}})\b", re.I)
    return re.compile(rf"(?<![A-Za-z])(?:(?P<subj>{subjects}) {name}s|(?P<psubj>{ACTION_GROUP_SUBJECTS}) {name})\b", re.I)  # (dive, wave DV: a plural subject)


def _swap_action(m: re.Match[str], entry: dict[str, Any], type_line: str, card_name: str, used: list[str]) -> str:
    """One phrase of the action → the sentences it stands for, said of the subject the card used (capitalised where the card's words were)."""
    n = int(m["n"]) if m.groupdict().get("n") else None
    subj = m.group("subj") or m.groupdict().get("psubj")
    me = self_word(type_line) if subj is None else subj if subj[:1].islower() or subj == card_name else subj[:1].lower() + subj[1:]
    said = action_sentences(entry, n=n, me=me)
    first = m.start() == 0 or m.string[max(0, m.start() - 2):m.start()] in (". ", "— ") or subj is not None and subj[:1].isupper()
    used.append(f"action:{entry['name']}:{n}")
    return _cap(said) if first else said


def _action_rewrite(core: str, actions: list[dict[str, Any]], type_line: str, card_name: str) -> tuple[str, list[str]]:
    """The line with each taught action's phrase replaced by the sentences it stands for (the subject the card used stays its subject)."""
    used: list[str] = []
    for entry in actions:
        core = action_pattern(entry, card_name).sub(lambda m, e=entry: _swap_action(m, e, type_line, card_name, used), core)
    return core, used


def _rewrite(text: str, type_line: str, keywords: dict[str, dict[str, Any]], lines: dict[str, dict[str, Any]],
             actions: list[dict[str, Any]] | None = None, card_name: str = "") -> tuple[str, list[str]]:
    from app.rules.oracle import strip_reminders

    me = self_word(type_line)
    out: list[str] = []
    used: list[str] = []
    for raw in text.split("\n"):
        core = strip_reminders(raw).strip()
        if core in lines:
            out += compile_entry(lines[core], me=me)
            used.append(f"line:{core}")
            continue
        if actions:
            core2, got = _action_rewrite(core, actions, type_line, card_name)
            if got:  # (the reminder text went with the phrase: the engine never reads one)
                out.append(core2)
                used += got
                continue
        kw = _keyword_line(core, keywords) if keywords and core else None
        if kw is None:
            out.append(raw)
            continue
        rest, found = kw
        if rest:
            out.append(_cap(", ".join(rest).lower()))
        for entry, n in found:
            out += compile_entry(entry, n=n, me=me)
            used.append(f"kw:{entry['name']}:{n}")
    return "\n".join(out), used


def apply(data: dict[str, Any] | None, entries: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Card data with taught keywords and lines written out as the Oracle sentences they stand for (a copy; ``data`` when
    nothing applies). ``"_taught"`` fingerprints the change: the printed-characteristics cache keys on it."""
    entries = list(entries)
    if data is None or not entries:
        return data
    keywords = {e["name"].lower(): e for e in entries if e["kind"] == "keyword"}
    actions = [e for e in entries if e["kind"] == "action"]
    lines = {e["line"]: e for e in entries if e["kind"] == "card" and e.get("oracle_id") == data.get("oracle_id")}
    stand_in = next((e for e in entries if e["kind"] == "stand_in" and e.get("card_id") == data.get("id")), None)
    if not keywords and not lines and not actions and stand_in is None:
        return data
    used: list[str] = []
    out = dict(data)
    if stand_in is not None:  # (a "Try it" table only: a plain creature plays as a card with the taught keyword, apis/teach.py)
        out.update(oracle_text=stand_in["oracle_text"], faces=[], layout="normal")
        used.append(f"stand_in:{stand_in['oracle_text']}")
    if out.get("oracle_text"):
        out["oracle_text"], got = _rewrite(str(out["oracle_text"]), str(out.get("type_line") or ""), keywords, lines, actions,
                                           str(out.get("name") or ""))
        used += got
    if out.get("faces"):
        faces = []
        for face in out["faces"]:
            face = dict(face)
            if face.get("oracle_text"):
                face["oracle_text"], got = _rewrite(str(face["oracle_text"]), str(face.get("type_line") or out.get("type_line") or ""),
                                                    keywords, lines, actions, str(face.get("name") or out.get("name") or ""))
                used += got
            faces.append(face)
        out["faces"] = faces
    if not used:
        return data
    out["_taught"] = hashlib.sha1(json.dumps([used, out.get("oracle_text"), [f.get("oracle_text") for f in out.get("faces") or []]],
                                             sort_keys=True).encode()).hexdigest()[:16]
    return out


class TaughtCards:
    """A game's card source with that game's taught entries applied (every other method: the source's own)."""

    def __init__(self, inner: Any, entries: list[dict[str, Any]]) -> None:
        self.inner = inner
        self.entries = entries
        self._memo: dict[str, tuple[Any, Any]] = {}

    def get(self, card_id: str) -> dict[str, Any] | None:
        data = self.inner.get(card_id)
        hit = self._memo.get(card_id)
        if hit is not None and hit[0] is data:
            return hit[1]  # type: ignore[no-any-return]
        out = apply(data, self.entries)
        self._memo[card_id] = (data, out)
        return out

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def unwrap(cards: Any) -> Any:
    return cards.inner if isinstance(cards, TaughtCards) else cards


def wrap(cards: Any, entries: list[dict[str, Any]] | None) -> Any:
    """The game's card source with its entries (unchanged when it has none)."""
    if cards is None or not entries:
        return cards
    return TaughtCards(cards, entries)


# ---------------------------------------------------------------------------------------------------------------- engine check
def _probe(lines: list[str], type_line: str) -> dict[str, Any]:
    """The engine's own reading of the lines on a plain card of that type: per line, understood (and its definition)?"""
    from app.rules import coverage, scripts
    from app.rules.characteristics import printed_from_data

    text = "\n".join(lines)
    key = hashlib.sha1(f"{type_line}\n{text}".encode()).hexdigest()[:16]
    data = {"id": f"teach-probe-{key}", "oracle_id": None, "name": f"Teach Probe {key}", "type_line": type_line, "mana_cost": "{2}",
            "oracle_text": text, "power": "2" if "Creature" in type_line else None, "toughness": "2" if "Creature" in type_line else None,
            "colors": [], "layout": "normal"}
    ch = printed_from_data(data, 0)
    defs = scripts.definitions(ch)
    level = coverage.of_card_data(data).level
    out = []
    for ab in ch.abilities:
        understood = coverage.ability_supported(ch, ab.index)
        if not understood and ab.kind == "keywords" and ab.keywords:  # (a keyword read with its cost — "Kicker {2}" — as coverage reads it)
            understood = all(coverage._keyword_supported(k, ab.text) for k in ab.keywords)
        out.append({"text": ab.text, "kind": ab.kind, "understood": understood, "definition": defs.get(ab.index)})
    return {"level": level, "abilities": out}


PROBE_TYPES = {"creature": "Creature — Merfolk", "artifact": "Artifact", "enchantment": "Enchantment", "land": "Land"}


def check(raw: Any, *, type_line: str | None = None) -> dict[str, Any]:
    """Everything the page shows about an entry: the pieces' problems, the sentences, and whether the engine reads every one
    (on a creature, with N = 1, 2 and 3 for a keyword with a number). ``ok``: ready to teach."""
    try:
        entry = clean_entry(raw)
    except TeachError as exc:
        return {"ok": False, "problems": [{"where": exc.where, "message": exc.plain}], "lines": [], "abilities": []}
    tl = type_line or entry.get("type_line") or PROBE_TYPES["creature"]
    me = self_word(tl)
    preview = compile_entry(entry, n=None, me=me)
    found: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    phrases: list[dict[str, str]] = []
    for n in ((1, 2, 3) if entry.get("param") else (None,)):
        if entry["kind"] == "action":  # (the line a card would carry, rewritten exactly as ``apply`` rewrites it)
            card_line = f"When {me} enters, {action_phrase(entry, n=n)}."
            lines = [_rewrite(card_line, tl, {}, {}, [entry], "")[0]]
            phrases.append({"card": card_line, "read": lines[0]})
        else:
            lines = compile_entry(entry, n=n, me=me)
        probe = _probe(lines, tl)
        if not found:
            found = probe["abilities"]
        for i, ab in enumerate(probe["abilities"]):
            if not ab["understood"]:
                issues.append({"where": f"Ability {min(i + 1, len(entry['abilities']))}",
                               "message": f"Fyodor can't read “{ab['text']}” yet{f' (with N = {n})' if n is not None else ''}. "
                                          "Try other pieces or settings."})
        if len(probe["abilities"]) != len(lines):
            issues.append({"where": "", "message": "One of the abilities reads as more than one line. Try other pieces."})
    seen: set[str] = set()
    issues = [i for i in issues if not (i["message"] in seen or seen.add(i["message"]))]  # type: ignore[func-returns-value]
    return {"ok": not issues, "problems": issues, "lines": preview, "entry": entry, "phrases": phrases,
            "abilities": [{"text": a["text"], "understood": a["understood"], "definition": a["definition"]} for a in found]}
