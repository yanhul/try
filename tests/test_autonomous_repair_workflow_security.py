from pathlib import Path


def test_privileged_repair_runs_trusted_controller_not_failed_revision():
    workflow = Path(".github/workflows/try-autonomous-repair.yml").read_text(encoding="utf-8")
    trusted_checkout = workflow.index("name: Checkout trusted repair controller")
    target_checkout = workflow.index("name: Checkout exact failed TRY revision")
    runner = workflow.index("name: Run bounded research-aware repair loop")
    assert trusted_checkout < runner
    assert target_checkout < runner
    assert "ref: 12fcabcf350655c61fdf6c9c88a63991679f5b5d" in workflow
    assert "ref: cb38387f2dd0785136fcc6434a49e43233bad648" in workflow
    assert "uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in workflow
    assert "uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert "uses: actions/checkout@v4" not in workflow
    assert "uses: actions/upload-artifact@v4" not in workflow
    assert "PYTHONPATH: ${{ github.workspace }}/trusted-try:${{ github.workspace }}/trusted-aios:${{ github.workspace }}/target" in workflow
    assert 'run: python "${{ github.workspace }}/trusted-try/research/autonomous_repair.py"' in workflow


def test_privileged_repair_never_uses_target_as_first_python_import_root():
    workflow = Path(".github/workflows/try-autonomous-repair.yml").read_text(encoding="utf-8")
    line = next(line for line in workflow.splitlines() if "PYTHONPATH:" in line)
    assert "trusted-try" in line.split(":", 1)[1].split(":", 1)[0]
    assert line.index("trusted-try") < line.index("trusted-aios") < line.index("/target")


def test_privileged_repair_cannot_self_issue_commit_authority_or_push():
    workflow = Path(".github/workflows/try-autonomous-repair.yml").read_text(encoding="utf-8")
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "ci_repair_publish.py" not in workflow
    assert "git push" not in workflow
    assert "gh pr create" not in workflow
    assert "no independently authorized AIOS COMMIT adapter is configured" in workflow
    assert "AIOS_REPAIR_AUTHORITY_DIR: ${{ secrets.AIOS_REPAIR_AUTHORITY_DIR }}" in workflow
    assert "AIOS_REPAIR_CONTRACT_ID: ${{ secrets.AIOS_REPAIR_CONTRACT_ID }}" in workflow
    assert "AIOS_REPAIR_PERMIT_ID: ${{ secrets.AIOS_REPAIR_PERMIT_ID }}" in workflow
    assert "AIOS_REPAIR_ATTESTATION_SECRET: ${{ secrets.AIOS_REPAIR_ATTESTATION_SECRET }}" in workflow
    assert "exit 2" in workflow
