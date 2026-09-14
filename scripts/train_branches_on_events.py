"""Task 4.2 — train the sequence and graph branches on event-derived matrices.

    python scripts/train_branches_on_events.py --preset full            # 3 worlds
    python scripts/train_branches_on_events.py --preset full --seeds 5  # 5 worlds

Builds several worlds, proposes candidates with blind discovery, computes the
ten event features, attaches labels afterwards, and fits both branches on what
they are actually served. Writes the artifacts the service loads:

    artifacts/cheops_v2_graph.joblib      + cheops_v2_graph_metrics.json
    artifacts/cheops_v2_sequence.joblib   + cheops_v2_sequence_metrics.json

After this, ``/api/v2/explain`` reports both branches as trained instead of
running a heuristic proxy.

Two protocols are measured and both are printed, because they disagree and the
disagreement is itself the finding:

  within-world   time-ordered split inside each world. Pessimistic, because a
                 candidate is dated by its last event, so month-long
                 structures pile up at the end of the timeline and the fraud
                 mix moves from 2.9 % to 33.3 % between fit and test.
  across-worlds  leave-one-world-out. No mix shift, but it does not test
                 order inside a world.

The shipped artifact is fitted on every world but the last and calibrated on
that one.
"""

from __future__ import annotations

import argparse
import time
from datetime import timedelta

from apris.cheops.infrastructure.ml.branch_training_v2 import (
    DEFAULT_PURGE,
    GRAPH_HEURISTIC_WEIGHTS,
    SEQUENCE_HEURISTIC_WEIGHTS,
    assert_feature_contract,
    fit_shipping_artifact,
    leave_one_world_out,
    pool_branch_measurement,
    train_branches,
)
from apris.cheops.infrastructure.ml.case_pipeline import build_case_dataset
from apris.cheops.infrastructure.ml.graph_v2 import (
    DEFAULT_GRAPH_MODEL_PARAMS,
    GRAPH_FEATURE_NAMES,
    save_graph_artifact,
    save_graph_metrics,
)
from apris.cheops.infrastructure.ml.sequence_v2 import (
    DEFAULT_SEQUENCE_MODEL_PARAMS,
    SEQUENCE_FEATURE_NAMES,
    save_sequence_artifact,
    save_sequence_metrics,
)
from apris.cheops.infrastructure.simulation import SimulationConfig, generate_world

PRESETS: dict[str, dict[str, int]] = {
    "quick": {"days": 45},
    "full": {"days": 120},
}

BRANCHES: dict[str, dict[str, object]] = {
    "graph": {
        "features": GRAPH_FEATURE_NAMES,
        "params": DEFAULT_GRAPH_MODEL_PARAMS,
        "weights": GRAPH_HEURISTIC_WEIGHTS,
        "version": "cheops-graph-v2-events",
    },
    "sequence": {
        "features": SEQUENCE_FEATURE_NAMES,
        "params": DEFAULT_SEQUENCE_MODEL_PARAMS,
        "weights": SEQUENCE_HEURISTIC_WEIGHTS,
        "version": "cheops-sequence-v2-events",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=sorted(PRESETS), default="quick")
    parser.add_argument("--seed", type=int, default=42, help="first seed; others follow it")
    parser.add_argument("--seeds", type=int, default=3, help="how many worlds to build")
    parser.add_argument("--purge-days", type=int, default=DEFAULT_PURGE.days)
    args = parser.parse_args()

    assert_feature_contract()

    started = time.time()
    seeds = [args.seed + offset for offset in range(max(1, args.seeds))]
    worlds: list[tuple] = []
    within_fits: dict[str, list] = {"graph": [], "sequence": []}

    for seed in seeds:
        config = SimulationConfig(seed=seed, **PRESETS[args.preset])
        world = generate_world(config)
        dataset = build_case_dataset(world)
        print(
            f"seed {seed}: {len(world.events)} events -> {dataset.size} candidates, "
            f"{dataset.positives} fraudulent ({dataset.base_rate:.1%}), "
            f"coverage {dataset.coverage:.3f}",
            flush=True,
        )
        worlds.append((dataset.features, dataset.labels, dataset.timestamps))

        trained = train_branches(
            dataset.features,
            dataset.labels,
            dataset.timestamps,
            seed=seed,
            purge=timedelta(days=args.purge_days),
        )
        for name, fit in trained.items():
            within_fits[name].append(fit)

    for name, spec in BRANCHES.items():
        within = pool_branch_measurement(within_fits[name])
        across = leave_one_world_out(
            worlds,
            feature_names=spec["features"],  # type: ignore[arg-type]
            model_params=spec["params"],  # type: ignore[arg-type]
            heuristic_weights=spec["weights"],  # type: ignore[arg-type]
            seed=args.seed,
        )
        artifact = fit_shipping_artifact(
            worlds,
            feature_names=spec["features"],  # type: ignore[arg-type]
            model_params=spec["params"],  # type: ignore[arg-type]
            artifact_version=str(spec["version"]),
            seed=args.seed,
        )
        metrics = {
            "artifact_version": spec["version"],
            "generated_at": artifact["generated_at"],
            "trained_on": "events (candidates from blind discovery)",
            "seeds": seeds,
            "preset": args.preset,
            "fit_worlds": artifact["fit_worlds"],
            "calibration_rows": artifact["calibration_rows"],
            "within_world": within,
            "across_worlds": across,
            "note": (
                "within_world is depressed by how a case is dated: a candidate "
                "carries the time of its last event, so month-long structures "
                "pile up at the end of the timeline and the fraud share moves "
                "from 2.9 % to 33.3 % between fit and test. across_worlds has no "
                "such shift but does not test order inside a world. Read both."
            ),
        }

        if name == "graph":
            save_graph_artifact(artifact)
            save_graph_metrics(metrics)
        else:
            save_sequence_artifact(artifact)
            save_sequence_metrics(metrics)

        print(
            f"{name:>9}: across worlds {across['pooled_roc_auc']} vs heuristic "
            f"{across['pooled_heuristic_roc_auc']} (per world {across['per_world_roc_auc']}); "
            f"within world {within['pooled_roc_auc']} vs {within['pooled_heuristic_roc_auc']}"
        )

    print(f"done in {time.time() - started:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
