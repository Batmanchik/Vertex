"""Task 4.1 — probe the structural features against real labelled fraud.

    python scripts/run_elliptic_probe.py               # every labelled node
    python scripts/run_elliptic_probe.py --limit 5000  # a faster sample

Downloads the Elliptic edge list and labels on first run (about 8 MB), caches
the two columns of the feature file it needs, builds one case per labelled
node, and scores three arms under a purged walk-forward over time steps:
the structural features alone, those plus how busy the node is, and the same
structural arm with labels shuffled as a control.

Writes ``artifacts/elliptic_probe.json``. Whatever it prints is the result:
the figures in the target text (Recall 0.96, Precision 0.92, ROC-AUC 0.99)
are an orientation, not a promise, and the run reports what it reports.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from apris.cheops.infrastructure.experiments.elliptic_probe import (
    DEFAULT_PURGE_STEPS,
    DEFAULT_SPLITS,
    DEFAULT_TARGET_RECALL,
    run_probe,
    write_report,
)
from apris.cheops.infrastructure.external.elliptic import (
    DEFAULT_DATA_DIR,
    download_if_missing,
    ensure_time_steps,
    load_elliptic,
)

OUT = Path("artifacts") / "elliptic_probe.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="sample this many labelled nodes")
    parser.add_argument("--hops", type=int, default=2)
    parser.add_argument("--cap", type=int, default=400)
    parser.add_argument("--splits", type=int, default=DEFAULT_SPLITS)
    parser.add_argument("--purge-steps", type=int, default=DEFAULT_PURGE_STEPS)
    parser.add_argument("--target-recall", type=float, default=DEFAULT_TARGET_RECALL)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    print(f"data: {args.data_dir}")
    download_if_missing(args.data_dir)
    ensure_time_steps(args.data_dir)
    data = load_elliptic(args.data_dir)
    print(f"loaded: {data.summary()}")

    report = run_probe(
        data,
        hops=args.hops,
        cap=args.cap,
        limit=args.limit,
        seed=args.seed,
        n_splits=args.splits,
        purge_steps=args.purge_steps,
        target_recall=args.target_recall,
    )

    cases = report["cases"]
    print(f"cases: {cases['rows']} ({cases['illicit']} illicit, {cases['prevalence']:.2%})")
    for name, arm in report["arms"].items():
        print(f"  {name:>24}: pooled ROC-AUC {arm['pooled_roc_auc']}")
        point = arm.get("operating_point")
        if point:
            print(
                f"  {'':>24}  at recall {point['recall']:.2f}: "
                f"precision {point['precision']:.2f}, F1 {point['f1']:.2f}, "
                f"{int(point['flagged'])} flagged on steps {point['test_steps']}"
            )
    print(f"margin over shuffled control: {report['margin_over_control']}")

    path = write_report(report, OUT)
    print(f"written: {path}  ({report['runtime_seconds']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
