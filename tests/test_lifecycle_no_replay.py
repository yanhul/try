import json
from pathlib import Path

def test_lifecycle_source_has_no_bc5_fallback():
    src=Path('run_bc_lifecycle.py').read_text()
    assert 'or "BC5"' not in src

def test_queue_has_strict_no_oos_selection_rule():
    q=json.loads(Path('research/bc_queue.json').read_text())
    assert q['rules']['oos_selection'] is False
    assert q['rules']['one_conceptual_change'] is True
    assert q['rules']['no_automatic_hypothesis_invention'] is True
