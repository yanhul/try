"""Small, dependency-free HMM primitives with explicit causal boundaries.

This module implements inference only. Training is intentionally not included yet:
fold-local fitting and provenance contracts must be established before promotion.
All public algorithms consume a frozen model and an observation sequence.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite, log, exp
from typing import Hashable, Sequence

State = Hashable
Observation = Hashable
_NEG_INF = float("-inf")
_EPS = 1e-12


def _check_row(row: dict[State, float], states: Sequence[State], name: str) -> None:
    if any(s not in row for s in states):
        raise ValueError(f"{name}_missing_state")
    if any(isinstance(row[s], bool) or not isfinite(float(row[s])) or row[s] < 0 for s in states):
        raise ValueError(f"{name}_invalid_probability")
    total = sum(float(row[s]) for s in states)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"{name}_must_sum_to_one")


@dataclass(frozen=True)
class HMM:
    states: tuple[State, ...]
    observations: tuple[Observation, ...]
    initial: dict[State, float]
    transition: dict[State, dict[State, float]]
    emission: dict[State, dict[Observation, float]]

    def __post_init__(self) -> None:
        if not self.states:
            raise ValueError("states_required")
        if not self.observations:
            raise ValueError("observations_required")
        _check_row(self.initial, self.states, "initial")
        for s in self.states:
            _check_row(self.transition.get(s, {}), self.states, f"transition[{s!r}]")
            _check_row(self.emission.get(s, {}), self.observations, f"emission[{s!r}]")

    def transition_log(self, a: State, b: State) -> float:
        p = float(self.transition[a][b])
        return log(p) if p > 0 else _NEG_INF

    def emission_log(self, state: State, obs: Observation) -> float:
        p = float(self.emission[state][obs])
        return log(p) if p > 0 else _NEG_INF


def _logsum(values):
    vals = [v for v in values if v != _NEG_INF]
    if not vals:
        return _NEG_INF
    m = max(vals)
    return m + log(sum(exp(v - m) for v in vals))


def forward(model: HMM, sequence: Sequence[Observation], *, log_space: bool = True) -> float:
    """Return P(O|model), using O(N^2 T) dynamic programming."""
    if not sequence:
        raise ValueError("observation_sequence_required")
    states = model.states
    alpha = {s: log(model.initial[s]) + model.emission_log(s, sequence[0]) if model.initial[s] > 0 and model.emission[s][sequence[0]] > 0 else _NEG_INF for s in states}
    for obs in sequence[1:]:
        nxt = {}
        for j in states:
            nxt[j] = model.emission_log(j, obs) + _logsum(alpha[i] + model.transition_log(i, j) for i in states)
        alpha = nxt
    result = _logsum(alpha.values())
    return result if log_space else (0.0 if result == _NEG_INF else exp(result))


def viterbi(model: HMM, sequence: Sequence[Observation]) -> tuple[float, list[State]]:
    """Return log P(best path, O) and the corresponding hidden-state path."""
    if not sequence:
        raise ValueError("observation_sequence_required")
    states = model.states
    score = {s: log(model.initial[s]) + model.emission_log(s, sequence[0]) if model.initial[s] > 0 and model.emission[s][sequence[0]] > 0 else _NEG_INF for s in states}
    back = []
    for obs in sequence[1:]:
        nxt, ptr = {}, {}
        for j in states:
            candidates = [(score[i] + model.transition_log(i, j), i) for i in states]
            best, prev = max(candidates, key=lambda x: x[0])
            nxt[j] = best + model.emission_log(j, obs) if best != _NEG_INF and model.emission[j][obs] > 0 else _NEG_INF
            ptr[j] = prev
        score, back = nxt, back + [ptr]
    last, best_score = max(score.items(), key=lambda x: x[1])
    path = [last]
    for ptr in reversed(back):
        last = ptr[path[-1]]
        path.append(last)
    path.reverse()
    return best_score, path


def backward(model: HMM, sequence: Sequence[Observation]) -> dict[State, list[float]]:
    """Return beta_t(i) in log space; beta_t uses observations after t."""
    if not sequence:
        raise ValueError("observation_sequence_required")
    states = model.states
    beta = {s: 0.0 for s in states}
    rows = [None] * len(sequence)
    rows[-1] = beta
    for t in range(len(sequence) - 2, -1, -1):
        obs = sequence[t + 1]
        beta = {i: _logsum(model.transition_log(i, j) + model.emission_log(j, obs) + beta[j] for j in states) for i in states}
        rows[t] = beta
    return {s: [rows[t][s] for t in range(len(sequence))] for s in states}


def posterior(model: HMM, sequence: Sequence[Observation]) -> tuple[dict[State, list[float]], dict[tuple[State, State], list[float]]]:
    """Return gamma and xi posteriors. This is retrospective/smoothing inference."""
    if not sequence:
        raise ValueError("observation_sequence_required")
    states = model.states
    # Recompute alpha in log space so posterior() has one deterministic contract.
    alpha_rows = []
    alpha = {s: log(model.initial[s]) + model.emission_log(s, sequence[0]) if model.initial[s] > 0 and model.emission[s][sequence[0]] > 0 else _NEG_INF for s in states}
    alpha_rows.append(alpha)
    for obs in sequence[1:]:
        alpha = {j: model.emission_log(j, obs) + _logsum(alpha_rows[-1][i] + model.transition_log(i, j) for i in states) for j in states}
        alpha_rows.append(alpha)
    beta = backward(model, sequence)
    logp = _logsum(alpha_rows[-1].values())
    if logp == _NEG_INF:
        raise ValueError("observation_sequence_has_zero_probability")
    gamma = {s: [] for s in states}
    for t in range(len(sequence)):
        vals = {s: alpha_rows[t][s] + beta[s][t] for s in states}
        z = _logsum(vals.values())
        for s in states:
            gamma[s].append(exp(vals[s] - z) if vals[s] != _NEG_INF else 0.0)
    xi = {(i, j): [] for i in states for j in states}
    for t in range(len(sequence) - 1):
        vals = {(i, j): alpha_rows[t][i] + model.transition_log(i, j) + model.emission_log(j, sequence[t + 1]) + beta[j][t + 1] for i in states for j in states}
        z = _logsum(vals.values())
        for key, value in vals.items():
            xi[key].append(exp(value - z) if value != _NEG_INF else 0.0)
    return gamma, xi


def causal_viterbi(model: HMM, sequence: Sequence[Observation]) -> list[State]:
    """Causal state labels: each label only uses observations through time t."""
    if not sequence:
        raise ValueError("observation_sequence_required")
    labels = []
    for end in range(1, len(sequence) + 1):
        _, path = viterbi(model, sequence[:end])
        labels.append(path[-1])
    return labels
