# Fangs of Kalonia

The normal spell puts one +1/+1 counter on its target, then doubles counters only on creatures that actually received that put. Overload changes the first instruction to affect each controlled creature without targeting (702.96).

The first instruction uses the native counter probe to record each exact object and its initial counter total. The second checks a positive increase on the same battlefield creature, then puts an additional amount equal to its current total through the counter replacement pipeline (701.10e, 122.6). A prohibited put or Vorinclex reducing one to zero does not qualify a creature merely because it already has counters.

Each instruction independently applies counter replacements and can pause for its own ordering choice. The new primitive preserves its original continuation descriptor when calling the native pipeline; calling a different effect primitive directly would lose the second pause. No custom persistent continuation handler is added.

Canonical tests cover normal and overloaded casting, existing counters, opponents excluded, Doubling Season, Hardened Scales, Solemnity, opposing Vorinclex, opposite-counter state actions after resolution, protection from green, replay and save/load. A fresh Python process resumes a saved first replacement choice, runs the new primitive, and offers the independent second choice.
