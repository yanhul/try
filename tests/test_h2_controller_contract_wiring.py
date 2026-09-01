from pathlib import Path


def test_controller_imports_and_calls_contracts():
    text = Path('research/bc_controller.py').read_text(encoding='utf-8')
    assert 'from contracts import validate_candidate, validate_evaluation, transition' in text
    assert 'validate_candidate(cand)' in text
    assert 'validate_evaluation(evaluation,c)' in text
    assert 's=transition(s,PROMOTE,bc,c[\'candidate_hash\'])' in text
    assert 's=transition(s,REJECT,bc,c[\'candidate_hash\'])' in text
