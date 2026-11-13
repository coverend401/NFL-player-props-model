"""Validate experiment archives or backtest externally supplied reviewed quotes."""

import argparse
import json
from pathlib import Path
import pandas as pd
from stage1b.artifacts import validate, validate_results
from stage1b.quote_replay import reprice_quotes
from stage1b.backtest import run_verified_backtest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--quotes", type=Path)
    parser.add_argument("--evidence-manifest", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = validate(args.experiment, root)
    validate_results(args.experiment)
    if args.quotes is None:
        print(
            json.dumps(
                {"validated": manifest["experiment_id"], "final_period_sealed": True}
            )
        )
        return
    if not all([args.evidence_manifest, args.evidence_root, args.output]):
        parser.error("Quotes require evidence manifest/root and a new output directory")
    output = args.output.resolve()
    if (
        output.exists()
        or output == root
        or output in [root / "data", root / "release_candidates"]
        or root / "data" in output.parents
        or root / "release_candidates" in output.parents
    ):
        raise ValueError("Use a new isolated research output directory")
    quotes = pd.read_csv(
        args.quotes,
        dtype={
            "quote_id": "str",
            "player_id": "str",
            "game_id": "str",
            "evidence_id": "str",
        },
    )
    evidence = json.loads(args.evidence_manifest.read_text())
    protocol = json.loads((args.experiment / "protocol.json").read_text())
    forecasts = reprice_quotes(quotes, args.experiment, root)
    bets, summary = run_verified_backtest(
        quotes, evidence, args.evidence_root, forecasts, protocol
    )
    output.mkdir(parents=True)
    bets.to_csv(output / "bets.csv", index=False)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
