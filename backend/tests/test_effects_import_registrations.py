"""Importing the engine registers every continuation a saved game may be waiting on, in a fresh process, before any card is read.

Two modules are imported by effects.py only for what they register (replace.THEN, payment_continuations): the wave 110
fold-in once dropped those imports, and a saved Immortal Coil prevention then failed to resume in a new process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_a_fresh_process_has_the_import_time_registrations():
    code = (
        "import app.rules.effects\n"
        "from app.rules import payment_continuations, replace\n"
        "assert 'damage_riders' in replace.THEN, sorted(replace.THEN)\n"
        "assert 'opponent_gain_costs44' in payment_continuations._HANDLERS, sorted(payment_continuations._HANDLERS)\n"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr
