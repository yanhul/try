from engine.experiment import run_experiment


def test_experiment_records_hashes(tmp_path):
    data = tmp_path / "data.csv"
    config = tmp_path / "config.json"
    output = tmp_path / "result.json"

    data.write_text("a,b\n1,2\n", encoding="utf-8")
    config.write_text('{"window": 20}', encoding="utf-8")

    payload = run_experiment(
        data,
        config,
        ["python", "-c", "print('experiment-pass')"],
        output,
    )

    assert payload["schema_version"] == 1
    assert payload["returncode"] == 0
    assert len(payload["data_sha256"]) == 64
    assert len(payload["config_sha256"]) == 64
    assert "experiment-pass" in payload["stdout"]

    saved = output.read_text(encoding="utf-8")
    assert "experiment-pass" in saved


def test_experiment_preserves_failure(tmp_path):
    data = tmp_path / "data.csv"
    config = tmp_path / "config.json"
    output = tmp_path / "result.json"

    data.write_text("x\n", encoding="utf-8")
    config.write_text("{}", encoding="utf-8")

    payload = run_experiment(
        data,
        config,
        ["python", "-c", "import sys; print('failed'); sys.exit(3)"],
        output,
    )

    assert payload["returncode"] == 3
    assert "failed" in payload["stdout"]
