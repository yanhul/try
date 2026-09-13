from research.hypothesis_novelty import novelty_metadata, structural_key


def candidate(threshold=2.5, window=50, left="vwap_distance"):
    return {
        "hypothesis_id": "discovered_primitive",
        "discovery_spec": {
            "mechanism_family": "mean_reversion",
            "operator": "zscore",
            "left": left,
            "window": window,
            "threshold": threshold,
            "direction": "above",
        },
    }


def test_parameter_changes_are_not_structural_novelty():
    assert structural_key(candidate(2.5, 50)) == structural_key(candidate(1.5, 100))


def test_mechanism_change_is_structural_novelty():
    assert structural_key(candidate()) != structural_key(candidate(left="close"))


def test_metadata_exposes_parameterization_separately():
    meta = novelty_metadata(candidate())
    assert meta["novelty_type"] == "structural_mechanism"
    assert meta["novelty_key"] == "mean_reversion|zscore|vwap_distance||above"
    assert meta["parameterization"] == {"window": 50, "threshold": 2.5}
