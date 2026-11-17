"""-- Teach Fyodor -- the abilities the piece matrix checks: every piece, and every choice of its main setting, in a sentence."""

from __future__ import annotations

from typing import Any

from app.rules.taught_vocab import PIECES


def _b(pid: str, **values: Any) -> dict[str, Any]:
    return {"id": pid, **({"values": values} if values else {})}


def _choices(piece: dict[str, Any]) -> list[dict[str, Any]]:
    """The piece once per option of each choice slot (others at their defaults)."""
    out = [{}]
    for key, slot in (piece.get("slots") or {}).items():
        if slot["kind"] == "choice":
            out += [{key: o} for o in slot["options"] if o != slot["default"]]
    return out


def matrix() -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    draw = _b("draw")

    def add(name: str, *abilities: dict[str, Any], **extra: Any) -> None:
        cases.append((name, {"kind": "keyword", "name": "Probe", "abilities": list(abilities), **extra}))

    for p in PIECES:
        role = p["role"]
        for values in _choices(p):
            tag = f"{p['id']}{values or ''}"
            if role == "trigger":
                add(tag, {"hat": _b(p["id"], **values), "body": [draw]})
            elif role == "condition":
                add(f"when/{tag}", {"hat": _b("etb"), "body": [_b(p["id"], **values), draw]})
                if not p.get("trigger_only"):
                    add(f"always/{tag}", {"hat": _b("static"), "body": [_b(p["id"], **values), _b("has_kw")]})
            elif role == "cost":
                add(tag, {"hat": _b("activated"), "body": [_b("cost_mana"), _b(p["id"], **values), draw]} if p["id"] != "cost_mana"
                    else {"hat": _b("activated"), "body": [_b(p["id"], **values), draw]})
            elif role == "limit":
                add(tag, {"hat": _b("activated"), "body": [_b("cost_mana"), draw, _b(p["id"])]})
            elif role == "optional_cost":
                add(tag, {"hat": _b("attacks"), "body": [{**_b(p["id"], **values), "body": [draw]}]})
            elif role == "effect":
                if p.get("after"):
                    add(tag, {"hat": _b("etb"), "body": [_b(p["after"]), _b(p["id"], **values)]})
                    add(f"may/{tag}", {"hat": _b("etb"), "body": [_b(p["after"]), {"id": "may", "body": [_b(p["id"], **values)]}]})
                    continue
                add(tag, {"hat": _b("etb"), "body": [_b(p["id"], **values)]})
                if not values:
                    add(f"activated/{tag}", {"hat": _b("activated"), "body": [_b("cost_mana"), _b("cost_tap"), _b(p["id"])]})
                if p.get("may") and not values:
                    add(f"may/{tag}", {"hat": _b("etb"), "body": [{"id": "may", "body": [_b(p["id"])]}]})
            elif role == "static":
                if not p.get("needs_condition"):
                    add(tag, {"hat": _b("static"), "body": [_b(p["id"], **values)]})
                if not p.get("no_condition") and not values:
                    add(f"if/{tag}", {"hat": _b("static"), "body": [_b("if_your_turn"), _b(p["id"])]})
    # flow
    add("then", {"hat": _b("etb"), "body": [draw, _b("then"), _b("discard")]})
    add("ifdo", {"hat": _b("etb"), "body": [{"id": "may", "body": [_b("discard")]}, {"id": "ifdo", "body": [_b("draw", n=2)]}]})
    add("pay-then", {"hat": _b("attacks"), "body": [{"id": "pay_mana", "body": [draw, _b("then"), _b("discard")]}]})
    add("if+pay", {"hat": _b("etb"), "body": [_b("if_control"), {"id": "pay_mana", "body": [draw]}]})
    add("two sentences", {"hat": _b("etb"), "body": [_b("mill"), draw]})
    add("plunge", {"hat": _b("etb"), "body": [_b("mill", n="N"), {"id": "may", "body": [_b("from_milled", n="N")]}]}, param=True)
    add("N everywhere", {"hat": _b("activated"), "body": [_b("cost_mana", mana="{N}"), _b("pump", p="N", t="N")]},
        {"hat": _b("static"), "body": [_b("enters_counters", n="N")]}, param=True)
    # actions (dive, wave DV): what happens to the creature a card says the action of
    cases.append(("action/dive", {"kind": "action", "name": "dive", "reminder": "It can't be blocked until it deals combat damage while attacking.",
                                  "abilities": [{"hat": _b("action"), "body": [_b("unblockable_for", who="t_self", dur="rdur_combat_attacking")]}]}))
    cases.append(("action/two sentences", {"kind": "action", "name": "surface",
                                           "abilities": [{"hat": _b("action"), "body": [_b("pump", who="t_self", p=2, t=0, dur="dur_next_turn"), _b("draw")]}]}))
    cases.append(("action/may", {"kind": "action", "name": "forage-deep",
                                 "abilities": [{"hat": _b("action"), "body": [{"id": "may", "body": [_b("gain", n=2)]}]}]}))
    cases.append(("action/N", {"kind": "action", "name": "plunge", "param": True,
                               "abilities": [{"hat": _b("action"), "body": [_b("counters", n="N", on="t_self"), _b("then"), _b("draw")]}]}))
    return cases


FIXTURE = "tests/fixtures/teach_sentences.json"
VOCABULARY_FIXTURE = "tests/fixtures/teach_vocabulary.json"


def sentences() -> list[dict[str, Any]]:
    """Every matrix case with the sentences the backend reads it back as (N unbound, then N = 2 for a keyword with a number):
    ``frontend/src/teach/sentence.test.ts`` checks that the page says exactly the same words."""
    from app.rules import taught

    out = []
    for name, entry in matrix():
        clean = taught.clean_entry(entry)
        case: dict[str, Any] = {"name": name, "entry": clean, "lines": taught.compile_entry(clean, me="this creature")}
        if clean.get("param"):
            case["lines_n2"] = taught.compile_entry(clean, n=2, me="this creature")
        case["lines_artifact"] = taught.compile_entry(clean, me="this artifact")
        if clean["kind"] == "action":  # (the page shows how a card says it and what Fyodor reads instead: both ports agree word for word)
            case["phrase"] = taught.action_phrase(clean)
            case["said"] = taught.action_sentences(clean, me="it")
            case["said_target"] = taught.action_sentences(clean, n=2 if clean.get("param") else None, me="target creature")
        out.append(case)
    return out


if __name__ == "__main__":  # python -m tests.teach_matrix  (regenerates the shared fixture)
    import json
    from pathlib import Path

    from app.rules.taught_vocab import vocabulary

    root = Path(__file__).resolve().parent.parent
    path = root / FIXTURE
    path.write_text(json.dumps(sentences(), indent=1, ensure_ascii=False) + "\n", "utf-8")
    voc = root / VOCABULARY_FIXTURE  # (the page's tests read the vocabulary from here too)
    voc.write_text(json.dumps(vocabulary(), indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(f"wrote {path} and {voc}")
