import argparse
from engine.hypothesis_research import run_hypothesis_research

p = argparse.ArgumentParser()
p.add_argument("csv_file")
p.add_argument("--out", required=True)
p.add_argument("--stop", type=float, default=0.01)
p.add_argument("--rr", type=float, default=2.0)
p.add_argument("--cost", type=float, default=0.0)
a = p.parse_args()
run_hypothesis_research(a.csv_file, a.out, stop=a.stop, rr=a.rr, round_trip_cost=a.cost)
print(f"PASS: hypothesis research -> {a.out}")
