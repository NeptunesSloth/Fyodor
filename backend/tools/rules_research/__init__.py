"""Development-time Magic rules research (never used at game time; the app stays offline).

* ``update``  — fetch the current official Comprehensive Rules (TXT), store them versioned under
  ``data/rules/comprehensive_rules/<effective date>/`` with metadata and SHA-256, build the
  section index, diff against the previous version, and discover update bulletins / release
  notes.
* ``search``  — search the local rules index ("zone change", "mana ability", "903.9").
* ``cr``      — the parser (numbered rules, subrules, examples, glossary).
* ``diff``    — rule-by-rule comparison and impact on Fyodor's engine components.

Authority order for engine behaviour: current Comprehensive Rules, then current Oracle text,
then official update bulletins / release notes / rulings. Community sources only help find
questions. See ``docs/RULES_RESEARCH.md``.
"""
