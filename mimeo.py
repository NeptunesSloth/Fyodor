p='app/rules/copying.py'
t=open(p).read()

# constants + define_static
t=t.replace('''def define_static(text: str) -> dict[str, Any] | None:''','''# -- The Mimeoplasm (wave 110C) -- the pair is one choice ("<copied card>|<other card>"), both creature cards in graveyards; both are exiled as it enters (614.12) and
# the other one's power is the number of additional +1/+1 counters (707.9e, 122.6)
MIMEO_TEXT = ("As ~ enters, you may exile two creature cards from graveyards. If you do, it enters as a copy of one of those cards with a number of additional +1/+1 counters "
              "on it equal to the power of the other card.")
MIMEO_WHAT = "two creature cards in graveyards" + TO_COPY


def mimeo_pairs(plan: Plan, controller: str, card_id: str | None) -> list[tuple[str, str]]:
    from app.rules import selectors

    sel = selectors.parse("creature card in a graveyard")
    if sel is None:
        return []
    every = [c for c in selectors.candidates(plan, sel, controller) if c != card_id and plan.state.cards[c].zone.endswith(":graveyard")]
    return [(a, b) for a in every if supported_source(plan, plan.state.cards[a]) is None for b in every if a != b]


def exile_pair(plan: Plan, ep: dict[str, Any], actor: str) -> None:
    """The Mimeoplasm: the two creature cards are exiled as it enters (done with the other choices of the entry, before it moves)."""
    if ids := [c for c in ep.pop("exile110c", None) or [] if c in plan.state.cards]:
        plan.do({"type": "move", "card_ids": ids, "to": {"zone": "exile"}}, actor=actor)


def define_static(text: str) -> dict[str, Any] | None:''',1)
t=t.replace('''    m = _CLONE.match(text)
    until_eot = False''','''    if text == MIMEO_TEXT:
        return {"kind": "replacement", "replacement": "enter_as_copy", "optional": True, "what": MIMEO_WHAT, "effects": [], "mimeo110c": True}
    m = _CLONE.match(text)
    until_eot = False''',1)

# candidates / options
t=t.replace('''    from app.rules import selectors

    phrase = what[: -len(TO_COPY)] if what.endswith(TO_COPY) else what
    limit = None''','''    from app.rules import selectors

    if what == MIMEO_WHAT:  # -- (wave 110C) -- The Mimeoplasm
        return [f"{a}|{b}" for a, b in mimeo_pairs(plan, controller, card_id)]
    phrase = what[: -len(TO_COPY)] if what.endswith(TO_COPY) else what
    limit = None''',1)
t=t.replace('''    ids = entry_candidates(plan, controller, what, card_id)
    if not ids:
        return []
    options = [''','''    ids = entry_candidates(plan, controller, what, card_id)
    if not ids:
        return []
    if what == MIMEO_WHAT:
        cards = plan.state.cards
        options = [DecisionOption(id=i, label=f"Copy {plan.ch(cards[i.split('|')[0]]).name}; exile {plan.ch(cards[i.split('|')[1]]).name} too (+{plan.ch(cards[i.split('|')[1]]).power or 0} counters)"[:200],
                                  card_id=i.split("|")[0]) for i in ids]
        return [*options, DecisionOption(id=NONE, label="Don't exile anything (it enters as itself)")]
    options = [''',1)

# _entering
t=t.replace('''    if cached is not None and cached.copy_entry_source is not None and cached.copy_entry_source.card == answer:
        # This replacement was already applied before another entry/order choice. Its copied values and source condition are fixed.
        if d.get("tapped"):
            out["tapped"] = True
        return False''','''    if cached is not None and cached.copy_entry_source is not None and cached.copy_entry_source.card == (answer or "").split("|")[0]:
        # This replacement was already applied before another entry/order choice. Its copied values and source condition are fixed.
        if d.get("tapped"):
            out["tapped"] = True
        if d.get("mimeo110c") and answer:
            out["exile110c"] = answer.split("|")
        return False''',1)
t=t.replace('''    source = plan.state.cards.get(answer)
    if source is None or answer not in entry_candidates(plan, controller, what, card.id):''','''    source = plan.state.cards.get(answer.split("|")[0])
    if source is None or answer not in entry_candidates(plan, controller, what, card.id):''',1)
t=t.replace('''    add_copy_effect(plan, [plan.oid(card)], recipe, controller, source=ENTERING + card.id, duration=duration, entry_source=source_snapshot)
    if d.get("tapped"):''','''    add_copy_effect(plan, [plan.oid(card)], recipe, controller, source=ENTERING + card.id, duration=duration, entry_source=source_snapshot)
    if d.get("mimeo110c"):  # -- (wave 110C) -- The Mimeoplasm: both cards leave the graveyards as it enters
        out["exile110c"] = answer.split("|")
    if d.get("tapped"):''',1)

# counters
t=t.replace('''    d = enter_definition(plan, card)
    if d is None or not d.get("enter_counters") or not entering_as_copy(plan, card):
        return {}''','''    d = enter_definition(plan, card)
    if d is not None and d.get("mimeo110c") and entering_as_copy(plan, card):  # -- (wave 110C) -- The Mimeoplasm: the other card's power
        other = plan.state.cards.get(((choices or {}).get(str(d["what"])) or "|").split("|")[-1])
        n = int(plan.ch(other).power or 0) if other is not None and (plan.ch(other).power or "").lstrip("-").isdigit() else 0
        return {"+1/+1": n} if n > 0 else {}
    if d is None or not d.get("enter_counters") or not entering_as_copy(plan, card):
        return {}''',1)
open(p,'w').write(t)

p='app/rules/replacements.py'
t=open(p).read()
t=t.replace('''        devour.sacrifice(plan, ep, entry["player"])
''','''        devour.sacrifice(plan, ep, entry["player"])
        from app.rules import copying as _copying  # -- (wave 110C) -- The Mimeoplasm: both graveyard cards are exiled as it enters

        _copying.exile_pair(plan, ep, entry["actor"])
''',1)
open(p,'w').write(t)
