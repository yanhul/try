import pytest
from research.latent_state.hmm import HMM, backward, causal_viterbi, forward, posterior, viterbi


@pytest.fixture
def model():
    return HMM(
        states=("F", "B"),
        observations=("w", "s"),
        initial={"F": 0.6, "B": 0.4},
        transition={"F": {"F": 0.7, "B": 0.3}, "B": {"F": 0.4, "B": 0.6}},
        emission={"F": {"w": 0.8, "s": 0.2}, "B": {"w": 0.3, "s": 0.7}},
    )


def test_forward_probability_matches_known_fixture(model):
    assert forward(model, ["w", "s", "w"], log_space=False) == pytest.approx(0.12552)


def test_viterbi_returns_valid_path(model):
    score, path = viterbi(model, ["w", "s", "w"])
    assert len(path) == 3
    assert path == ["F", "F", "F"]
    assert score < 0


def test_forward_and_backward_agree_on_sequence_likelihood(model):
    sequence=["w", "s", "w"]
    beta=backward(model, sequence)
    from math import exp
    start=sum(model.initial[s] * model.emission[s][sequence[0]] * exp(beta[s][0]) for s in model.states)
    assert start == pytest.approx(forward(model, sequence, log_space=False))


def test_gamma_and_xi_normalize(model):
    gamma, xi = posterior(model, ["w", "s", "w"])
    for t in range(3):
        assert sum(gamma[s][t] for s in model.states) == pytest.approx(1.0)
    for t in range(2):
        assert sum(xi[(i, j)][t] for i in model.states for j in model.states) == pytest.approx(1.0)


def test_causal_viterbi_has_one_label_per_prefix(model):
    labels=causal_viterbi(model, ["w", "s", "w"])
    assert len(labels) == 3


def test_posterior_is_explicitly_retrospective_in_api(model):
    assert "retrospective" in posterior.__doc__.lower()


def test_zero_probability_model_is_rejected():
    with pytest.raises(ValueError, match="initial_must_sum_to_one"):
        HMM(
            states=("F",), observations=("w",), initial={"F": 0.0},
            transition={"F": {"F": 1.0}}, emission={"F": {"w": 1.0}},
        )


def test_forward_long_sequence_remains_finite_in_log_space(model):
    score = forward(model, ["w", "s"] * 1000)
    assert score != float("-inf")
    assert score < 0


def test_causal_viterbi_prefix_invariance(model):
    prefix = ["w", "s", "w"]
    extended = prefix + ["s", "s"]
    assert causal_viterbi(model, prefix) == causal_viterbi(model, extended)[:len(prefix)]


def test_posterior_and_backward_require_nonempty_sequence(model):
    for fn in (backward, posterior):
        with pytest.raises(ValueError, match="observation_sequence_required"):
            fn(model, [])


def test_unknown_observation_is_rejected(model):
    for fn in (forward, viterbi, backward, posterior, causal_viterbi):
        with pytest.raises(ValueError, match="unknown_observation"):
            fn(model, ["unknown"])
