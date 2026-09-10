from research import bc_controller


def test_resume_retry_budget_is_durable(tmp_path):
    state_path = tmp_path / "bc_lifecycle_state.json"
    original = bc_controller.STATE
    bc_controller.STATE = state_path
    try:
        state = {"history": [], "resume_retry_count": 0}
        bc_controller.hold(state, "HOLD_PROVIDER_ROUTER", 31)
        assert state["resume_retry_count"] == 1

        # Simulate a fresh workflow process by loading the persisted state.
        reloaded = bc_controller.load(state_path, {})
        bc_controller.hold(reloaded, "HOLD_PROVIDER_ROUTER", 31)
        assert reloaded["resume_retry_count"] == 2
        assert reloaded["retry_count"] == 1
    finally:
        bc_controller.STATE = original
