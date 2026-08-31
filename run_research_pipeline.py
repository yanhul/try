#!/usr/bin/env python3
import argparse, json
from engine.research_pipeline import run_is_validation_oos


def main():
    p = argparse.ArgumentParser(description="Leakage-resistant IS -> Validation -> OOS pipeline")
    p.add_argument("--data", required=True)
    p.add_argument("--candidates", required=True, help="JSON array of {stop_fraction,reward_multiple}")
    p.add_argument("--out", required=True)
    p.add_argument("--objective", default="profit_factor")
    p.add_argument("--validation-min-pf", type=float, default=1.0)
    p.add_argument("--validation-min-return", type=float, default=0.0)
    a = p.parse_args()
    candidates = json.loads(open(a.candidates, encoding="utf-8").read())
    result = run_is_validation_oos(
        a.data, a.out, candidates,
        objective=a.objective,
        validation_min_profit_factor=a.validation_min_pf,
        validation_min_total_return=a.validation_min_return,
    )
    print(json.dumps({
        "selected_config": result["selected_config"],
        "validation_passed": result["validation"]["passed"],
        "oos": result["oos"],
    }, indent=2))

if __name__ == "__main__":
    main()
