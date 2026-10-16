from research.autonomous_repair import terminal_promotion_block_reason


def test_non_pass_does_not_enter_terminal_promotion_gate():
    assert terminal_promotion_block_reason("FAIL", [], {}) is None
    assert terminal_promotion_block_reason("HOLD", [], {}) is None


def test_pass_without_mapping_apply_receipt_is_blocked():
    assert terminal_promotion_block_reason("PASS", ["EV-test"], None) == (
        "terminal_promotion_blocked:apply_result_not_mapping"
    )


def test_pass_without_test_evidence_refs_is_blocked():
    assert terminal_promotion_block_reason("PASS", [], {"effect_id": "EF-test"}) == (
        "terminal_promotion_blocked:test_evidence_refs_missing"
    )


def test_pass_with_only_test_ids_still_requires_independent_aios_resolution():
    assert terminal_promotion_block_reason("PASS", ["EV-test"], {
        "effect_id": "EF-test",
        "attempt_id": "EF-test:attempt:1",
        "provider": "gemini",
        "outcome": "OBSERVED_SUCCESS",
    }) == (
        "terminal_promotion_blocked:independent_aios_effect_and_evidence_resolver_not_integrated"
    )
