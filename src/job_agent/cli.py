"""python -m evals  or  applypilot-evals"""

from __future__ import annotations

import argparse
from pathlib import Path

from job_agent.evalrun import dataset_path, run_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ApplyPilot eval gates on the synthetic pairs.")
    parser.add_argument("--dataset", default="", help="jsonl path, defaults to evals/datasets/pairs.jsonl")
    args = parser.parse_args(argv)
    path = Path(args.dataset) if args.dataset else dataset_path()
    rows = run_dataset(path)
    failed = 0
    for row in rows:
        scores = " ".join(f"{name}={value:.2f}" for name, value in row["scores"].items())
        flag = "PASS" if row["passed"] else "FAIL"
        if not row["passed"]:
            failed += 1
            flag += " (" + ", ".join(row["failures"]) + ")"
        print(f"{row['id']}  {flag}  {scores}")
    print(f"{len(rows) - failed}/{len(rows)} passed")
    return 1 if failed or not rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
