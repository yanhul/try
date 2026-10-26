from research.bc_controller import candidate_matches_frontier


def test_rejects_provider_candidate_when_family_differs_from_frontier():
    candidate = {
        "discovery_spec": {"mechanism_family": "mean_reversion"},
        "evidence_sources": ["https://example.invalid/mean-reversion"],
    }
    ordered = [{"family": "fvg_imbalance", "source_url": "https://example.invalid/fvg"}]

    assert candidate_matches_frontier(candidate, "fvg_imbalance", ordered) == (
        False,
        "candidate_family_mismatch",
    )


def test_rejects_candidate_source_not_bound_to_frontier_family():
    candidate = {
        "discovery_spec": {"mechanism_family": "mean_reversion"},
        "evidence_sources": ["https://example.invalid/unrelated"],
    }
    ordered = [{"family": "mean_reversion", "source_url": "https://example.invalid/selected"}]

    assert candidate_matches_frontier(candidate, "mean_reversion", ordered) == (
        False,
        "candidate_source_not_bound_to_frontier_family",
    )


def test_accepts_candidate_bound_to_selected_frontier_family_and_source():
    source = "https://example.invalid/selected-mean-reversion"
    candidate = {
        "discovery_spec": {"mechanism_family": "mean_reversion"},
        "evidence_sources": [source],
    }
    ordered = [{"family": "mean_reversion", "source_url": source}]

    assert candidate_matches_frontier(candidate, "mean_reversion", ordered) == (True, "")
