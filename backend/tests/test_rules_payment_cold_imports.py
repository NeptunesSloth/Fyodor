"""Native continuation registries and typed receipts survive real cold import orders."""
import subprocess
import sys

import pytest


@pytest.mark.parametrize('entry', [
    'from app.rules import replace',
    'from app.rules import scripts',
    'from app.rules import payment_continuations',
    "from app.rules.oracle import classify; classify('{T}: Add {U}.', spell=False)",
])
def test_cold_rule_import_order_keeps_registered_handlers_and_typed_payment(entry):
    code = entry + '''
from app.rules import engine, replace, payment_continuations as pc, mana as M
from app.rules.mana_requirement_rows import SpentClass, UnitClass
for key in ('paid_stage', 'mana_riders', 'immediate_mana_done', 'staged_mana_extras', 'noop', 'draw_rest'):
    assert key in replace.THEN and callable(replace.THEN[key]), key
p = M.Payment(allocation=[SpentClass(UnitClass('W', False), 1)], selected_options=[('source', 1)])
assert pc.payment_of(pc.payment_data(p)) == p
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
