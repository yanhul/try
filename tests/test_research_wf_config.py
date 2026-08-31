from engine.evaluation import validate_walk_forward_evidence


def test_bc1_research_grade_configuration():
    validate_walk_forward_evidence(
        dataset_bars=3624,
        train_size=1100,
        test_size=500,
        step=500,
        window_count=5,
    )
