from pathlib import Path


def test_controller_wires_normative_contracts_before_gate():
    text = Path("research/bc_controller.py").read_text(encoding="utf-8")
    assert "from contracts import validate_candidate, validate_evaluation, transition" in text
    assert "cand=validate_candidate(cand)" in text
    assert "evaluation=validate_evaluation(load(evidence,{}),c)" in text
    assert "s=transition(s,PROMOTE,bc,c['candidate_hash'])" in text
    assert "s=transition(s,REJECT,bc,c['candidate_hash'])" in text


def test_central_conformance_pins_current_aios_main():
    text = Path(".github/workflows/aios-central-conformance.yml").read_text(encoding="utf-8")
    assert "AIOS_REF: 8d497c240444571735e1316dbeb8d575e0ceb6e0" in text
