from tests.test_rules_wave16c_triggers import card_db, build, cast, act  # noqa: F401


def test_dbg(cards):
    s = build(cards, ["Magister Sphinx"], [])
    cast(s, "Magister Sphinx", W=1, U=1, B=1, C=4)
    for _ in range(4):
        d = s.state.rules.decision
        print("DECISION", d and (d.kind, d.player, [(o.id, o.label) for o in d.options]), "STACK", s.state.zones.get("stack"))
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[-1].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    print("LOG", [e for e in s.state.log[-6:]] if hasattr(s.state, "log") else None, s.state.players["p2"].life, s.state.players["p1"].life)
    assert 0
