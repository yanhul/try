import subprocess
import sys

MIN_OOS_TRADES = 60
BOOTSTRAP_CI_MUST_EXCLUDE_ZERO = True
MULTIPLE_TESTING_ALPHA = 0.05


def run(script):
    p = subprocess.run([sys.executable, script], capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(p.returncode)
    return p.stdout


def parse_dict_line(text, prefix):
    for line in text.splitlines():
        if line.startswith(prefix):
            return eval(line[len(prefix):].strip(), {"__builtins__": {}}, {"inf": float("inf")})
    raise RuntimeError(f"missing {prefix}")


def main():
    block = run("audit_block_bootstrap.py")
    multi = run("audit_multiple_testing.py")

    observed = parse_dict_line(block, "OBSERVED_OOS")
    ci = parse_dict_line(block, "BLOCK_BOOTSTRAP_95")
    interp = parse_dict_line(block, "INTERPRETATION_RULES")
    mt = parse_dict_line(multi, "MAXT_PERMUTATION_ADJUSTED_P")

    n = observed["trades"]
    total_ci = ci["total_ci_95"]
    compound_ci = ci["compound_ci_95"]
    multiple_testing_p = float(mt)

    enough_data = n >= MIN_OOS_TRADES
    ci_excludes_zero = total_ci[0] > 0 or total_ci[1] < 0
    compound_ci_excludes_zero = compound_ci[0] > 0 or compound_ci[1] < 0
    multiple_testing_pass = multiple_testing_p < MULTIPLE_TESTING_ALPHA

    if not enough_data:
        decision = "DO_NOT_REPLACE_YET"
        reason = "OOS sample below minimum decision threshold"
    elif ci_excludes_zero and compound_ci_excludes_zero and multiple_testing_pass:
        decision = "REVIEW_REPLACEMENT"
        reason = "all statistical gates passed; replacement requires separate strategy validation"
    else:
        decision = "KEEP_CURRENT_AND_CONTINUE_AUDIT"
        reason = "robustness gates not jointly satisfied"

    print("DECISION_CONFIG", {"min_oos_trades": MIN_OOS_TRADES, "alpha": MULTIPLE_TESTING_ALPHA})
    print("DECISION_INPUT", {"oos_trades": n, "total_ci_95": total_ci, "compound_ci_95": compound_ci, "maxT_adjusted_p": multiple_testing_p})
    print("DECISION_GATES", {"enough_data": enough_data, "total_ci_excludes_zero": ci_excludes_zero, "compound_ci_excludes_zero": compound_ci_excludes_zero, "multiple_testing_pass": multiple_testing_pass})
    print("DECISION", decision)
    print("REASON", reason)


if __name__ == "__main__":
    main()
