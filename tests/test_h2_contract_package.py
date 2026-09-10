def test_contract_package_exports_normative_checks():
    from contracts import transition, validate_candidate, validate_evaluation
    assert callable(validate_candidate)
    assert callable(validate_evaluation)
    assert callable(transition)
