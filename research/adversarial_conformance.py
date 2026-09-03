#!/usr/bin/env python3
"""Runtime adversarial conformance: attacks must fail closed.

This suite deliberately mutates durable controller state in a temporary copy.
It is a security test, not a relaxation of the research policy.
"""
from __future__ import annotations
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_controller():
    spec = importlib.util.spec_from_file_location("bc_controller_under_test", ROOT / "research" / "bc_controller.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_terminal_tamper_is_not_accepted():
    mod = load_controller()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state.json"
        mod.STATE = state
        state.write_text(json.dumps({"terminal": True, "terminal_reason": "FORGED"}))
        rc = mod.main()
        assert rc != 0, "FORGED terminal state was accepted"


def test_contract_like_unknown_authority_is_not_accepted():
    mod = load_controller()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state.json"
        mod.STATE = state
        state.write_text(json.dumps({"terminal": False, "capabilities": ["UNDECLARED_EFFECT"]}))
        rc = mod.main()
        assert rc != 0, "undeclared capability state was accepted"


if __name__ == "__main__":
    tests = [test_terminal_tamper_is_not_accepted, test_contract_like_unknown_authority_is_not_accepted]
    failures = []
    for test in tests:
        try: test()
        except Exception as exc: failures.append(f"{test.__name__}: {exc}")
    if failures:
        print("AIOS_ADVERSARIAL: BLOCKED")
        print("\n".join("- " + x for x in failures))
        raise SystemExit(1)
    print("AIOS_ADVERSARIAL: PASS")
