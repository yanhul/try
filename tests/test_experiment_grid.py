from engine.experiment_grid import generate_grid, run_grid


def test_generate_grid():
    result = list(generate_grid(
        {"strategy": "reference"},
        {"stop": [0.005, 0.01], "rr": [1.5, 2.0]},
    ))

    assert len(result) == 4
    assert result[0]["strategy"] == "reference"


def test_run_grid(tmp_path):
    result = run_grid(
        {"strategy": "reference"},
        {"stop": [0.005, 0.01], "rr": [1.5, 2.0]},
        tmp_path / "grid.json",
    )

    assert len(result) == 4
    assert (tmp_path / "grid.json").exists()
