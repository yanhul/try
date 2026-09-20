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


def test_parameter_variants_preserve_structure_and_change_parameters():
    from research.hypothesis_novelty import parameter_key, parameter_variants
    base = candidate(2.5, 50)
    variants = parameter_variants(base, limit=6)
    assert variants
    assert all(structural_key(v) == structural_key(base) for v in variants)
    assert all(parameter_key(v) != parameter_key(base) for v in variants)
    assert all(v["search_phase"] == "PARAMETER_OPTIMIZATION" for v in variants)
