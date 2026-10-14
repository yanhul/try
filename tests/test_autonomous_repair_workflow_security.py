from pathlib import Path


def test_privileged_repair_runs_trusted_controller_not_failed_revision():
    workflow = Path(".github/workflows/try-autonomous-repair.yml").read_text(encoding="utf-8")
    trusted_checkout = workflow.index("name: Checkout trusted repair controller")
    target_checkout = workflow.index("name: Checkout exact failed TRY revision")
    runner = workflow.index("name: Run bounded research-aware repair loop")
    assert trusted_checkout < runner
    assert target_checkout < runner
    assert "ref: 308fd9fe7c1b3b52f9d9b0d4d301fcfcfa680dbe" in workflow
    assert "PYTHONPATH: ${{ github.workspace }}/trusted-try:${{ github.workspace }}/trusted-aios:${{ github.workspace }}/target" in workflow
    assert 'run: python "${{ github.workspace }}/trusted-try/research/autonomous_repair.py"' in workflow


def test_privileged_repair_never_uses_target_as_first_python_import_root():
    workflow = Path(".github/workflows/try-autonomous-repair.yml").read_text(encoding="utf-8")
    line = next(line for line in workflow.splitlines() if "PYTHONPATH:" in line)
    assert "trusted-try" in line.split(":", 1)[1].split(":", 1)[0]
    assert line.index("trusted-try") < line.index("trusted-aios") < line.index("/target")
