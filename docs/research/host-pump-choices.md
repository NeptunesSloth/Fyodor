# Attached-host and variable pump choices

Pemmin's Aura uses the existing nonmodal pump-choice primitive. The missing grammar case was the native `host` reference: `choice_grants._subject` accepted targets and self but refused enchanted/equipped objects. It now accepts that same host reference used by ordinary pumps, preserving the existing source-object/LKI and bound-subject machinery.

The Aura controller chooses on resolution, including when another player controls its host. Its pending ability reads a currently reattached host when it starts resolving, uses the departed Aura's last known host, and never applies to a new object created by host blink. Once the choice is offered, its subject remains bound to the same rules object. Pump effects retain ordinary layer 7c and end-of-turn duration.

Liliana of the Dark Realms' ±X choice required no new count or signed-value evaluator. The native `where X is ...` binder already visits nested pump alternatives. The remaining parse refusal came from its numeric internal stand-in appearing in public choice labels. Labels now say `+X` or `-X` while that binder is active; numeric effect fields still pass through the existing native substitution and signed-count evaluation.

Canonical tests verify both signs and end-of-turn expiry, resolution-time Swamp counts and current type changes from Urborg, zero, lethal negative toughness, controller/source changes, departed-source and blink identities, and saved-decision replay/JSON load. Liliana's emblem implementation and fixture remain owned by the parent task. No new primitive, callback registration, or casting/payment behavior was added.
